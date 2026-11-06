"""Inspect bounded release payloads without executing package-provided code."""

from __future__ import annotations

import email.parser
import configparser
import fnmatch
import gzip
import hashlib
import io
import re
import tarfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile

from tooling.sync_versions import unique_json
from tooling.release_native import inspect_native
from pathlib import Path, PurePosixPath

MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_FILES = 20000
MARKER = b"\0STRLING-PRODUCT-VERSION:"


def unique_yaml(data: bytes) -> dict:
    import yaml

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if not isinstance(key, str) or key in result:
                raise ValueError("duplicate or non-string package metadata key")
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping
    )
    if len(data) > 65536:
        raise ValueError("oversized package metadata")
    result = yaml.load(data, Loader=UniqueLoader)
    if not isinstance(result, dict):
        raise ValueError("package metadata must be a mapping")
    return result


def _name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or re.search(r"[\x00-\x1f\x7f]", value)
        or len(value) > 4096
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError("unsafe package member: " + value)
    return value


def archive_files(path: Path | io.BytesIO) -> dict[str, bytes]:
    """Read regular members only; reject aliases, bombs, encryption, and links."""
    if isinstance(path, Path) and path.stat().st_size > MAX_TOTAL:
        raise ValueError("oversized package archive")
    files: dict[str, bytes] = {}
    total = 0

    def add(name: str, size: int, data: bytes) -> None:
        nonlocal total
        name = _name(name)
        total += size
        if (
            name in files
            or len(files) >= MAX_FILES
            or size > MAX_FILE
            or total > MAX_TOTAL
        ):
            raise ValueError("duplicate or oversized package content")
        if len(data) != size:
            raise ValueError("truncated package content")
        files[name] = data

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for index, entry in enumerate(archive.infolist()):
                if index >= MAX_FILES:
                    raise ValueError("too many package members")
                if entry.orig_filename != entry.filename:
                    raise ValueError("unsafe package member normalization")
                if entry.is_dir():
                    _name(entry.filename.rstrip("/"))
                    continue
                if (
                    entry.flag_bits & 1
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("encrypted or linked package content")
                if entry.file_size > MAX_FILE or total + entry.file_size > MAX_TOTAL:
                    raise ValueError("oversized package content")
                add(entry.filename, entry.file_size, archive.read(entry))
    else:
        if hasattr(path, "seek"):
            path.seek(0)
        with tarfile.open(
            fileobj=path if hasattr(path, "read") else None,
            name=None if hasattr(path, "read") else path,
            mode="r:*",
        ) as archive:
            for index, entry in enumerate(archive):
                if index >= MAX_FILES:
                    raise ValueError("too many package members")
                if entry.isdir():
                    _name(entry.name.rstrip("/"))
                    continue
                if (
                    not entry.isfile()
                    or entry.size > MAX_FILE
                    or total + entry.size > MAX_TOTAL
                ):
                    raise ValueError("linked, special, or oversized package content")
                stream = archive.extractfile(entry)
                if stream is None:
                    raise ValueError("missing package content")
                add(entry.name, entry.size, stream.read(MAX_FILE + 1))
    if not files:
        raise ValueError("empty package")
    return files


def native_identity(data: bytes, version: str) -> str:
    expected = MARKER + version.encode("ascii") + b"\0"
    if len(data) > MAX_FILE or data.count(MARKER) != 1 or data.count(expected) != 1:
        raise ValueError("native product identity mismatch")
    if data[:6] == b"\x7fELF\x02\x01" and data[18:20] == b"\x3e\0":
        return "linux-x86_64"
    if data[:2] == b"MZ" and len(data) >= 64:
        offset = int.from_bytes(data[60:64], "little")
        if data[offset : offset + 6] == b"PE\0\0\x64\x86":
            return "windows-x86_64"
    raise ValueError("unregistered native binary format or architecture")


def _metadata(files: dict[str, bytes], pattern: str) -> bytes:
    selected = [
        data for name, data in files.items() if fnmatch.fnmatchcase(name, pattern)
    ]
    if len(selected) != 1:
        raise ValueError("package must contain exactly one " + pattern)
    return selected[0]


def _python_metadata(data: bytes, name: str, version: str) -> None:
    message = email.parser.BytesParser().parsebytes(data)
    for field, expected in (("Name", name), ("Version", version)):
        if message.get_all(field) != [expected]:
            raise ValueError("Python distribution coordinate mismatch")
    if message.get("Requires-Python") != "<3.13,>=3.12":
        raise ValueError("Python runtime scope mismatch")
    if message.get("License-Expression") != "Apache-2.0":
        raise ValueError("Python distribution license mismatch")


def inspect_payload(
    root: Path, artifact: dict, version: str, members: list[dict]
) -> list[dict]:
    """Validate metadata and required content, returning the full content graph."""
    slug = artifact["id"].removeprefix("release:")
    all_files: dict[str, bytes] = {}
    graph = []
    for member in members:
        path = root / member["name"]
        packed = False
        if path.is_dir():
            files = {
                row["name"]: (root / row["name"]).read_bytes()
                for row in member["files"]
            }
        elif artifact["artifact_policy"]["subject_kind"] == "source-tree":
            files = {member["name"]: path.read_bytes()}
        elif path.suffix.lower() in {".xml", ".rockspec"}:
            files = {path.name: path.read_bytes()}
            packed = True
        else:
            files = archive_files(path)
            packed = True
        if slug in {"java", "kotlin"} and path.suffix == ".jar":
            if any(
                name.startswith(
                    (
                        "com/strling/core/",
                        "com/strling/emitters/",
                        "strling/core/",
                        "strling/emitters/",
                    )
                )
                or name.endswith((".dll", ".so", ".dylib"))
                for name in files
            ):
                raise ValueError(
                    "JVM distribution contains retired semantic or native payload"
                )
        if slug == "lua":
            from tooling.lua_rockspec import render_rockspec, rockspec_name

            expected = render_rockspec(
                (root / "bindings/lua/strling-template.rockspec").read_text(), version
            ).encode()
            if _metadata(files, rockspec_name(version)) != expected:
                raise ValueError(
                    "Lua source rock and rockspec disagree with the canonical template"
                )
        if slug == "ruby":
            # RubyGems is an outer tar containing compressed metadata/data tars.
            data = _metadata(files, "data.tar.gz")
            nested = archive_files(io.BytesIO(data))
            with gzip.GzipFile(
                fileobj=io.BytesIO(_metadata(files, "metadata.gz"))
            ) as stream:
                metadata = stream.read(MAX_FILE + 1)
            if len(metadata) > MAX_FILE:
                raise ValueError("oversized Ruby package metadata")
            if not re.search(rb"(?m)^name: strling\s*$", metadata) or not re.search(
                rb"(?m)^  version: "
                + re.escape(version.replace("-", ".").encode())
                + rb"\s*$",
                metadata,
            ):
                raise ValueError("RubyGems coordinate mismatch")
            files.update(
                {"data.tar.gz!/" + key: value for key, value in nested.items()}
            )
        if slug == "python":
            wheel = path.name.endswith(".whl")
            _python_metadata(
                _metadata(
                    files,
                    "*.dist-info/METADATA"
                    if wheel
                    else path.name.removesuffix(".tar.gz") + "/PKG-INFO",
                ),
                "STRling",
                version,
            )
            if wheel:
                native = [
                    data
                    for name, data in files.items()
                    if name.endswith(("/strling_interop.dll", "/libstrling_interop.so"))
                ]
                if len(native) != 1:
                    raise ValueError("wheel has no unique native payload")
                native_scope = native_identity(native[0], version)
                inspect_native(native[0])
                if (
                    artifact.get("assembly_scope") is not None
                    and native_scope != artifact["assembly_scope"]
                ):
                    raise ValueError(
                        "wheel native architecture differs from its registered build scope"
                    )
                identity = unique_json(
                    _metadata(files, "*STRling/_native/kernel-identity.json").decode()
                )
                if (
                    identity.get("product_version") != version
                    or identity.get("native_sha256")
                    != hashlib.sha256(native[0]).hexdigest()
                ):
                    raise ValueError("wheel native identity differs from payload")
            elif not any(
                name.endswith("/_native_source/bindings/interop/src/product_version.rs")
                for name in files
            ):
                raise ValueError("sdist omits canonical native sources")
        elif slug == "typescript":
            package = unique_json(_metadata(files, "package/package.json").decode())
            if package.get("license") != "Apache-2.0" or package.get("publishConfig"):
                raise ValueError("unapproved npm license or publication configuration")
            if (package.get("name"), package.get("version")) != (
                artifact["package_name"],
                version,
            ):
                raise ValueError("npm coordinate mismatch")
            from tooling.interop_wasm import WasmContractError, verify_product_identity

            wasm = _metadata(files, "package/dist/strling_interop.wasm")
            try:
                verify_product_identity(wasm, version)
            except WasmContractError as error:
                raise ValueError(str(error)) from error
            for target in (
                "package/dist/index.js",
                "package/dist/index.d.ts",
                "package/dist/node.js",
                "package/dist/node.d.ts",
            ):
                _metadata(files, target)
        elif slug == "rust":
            package = tomllib.loads(
                _metadata(files, "strling-" + version + "/Cargo.toml").decode()
            )["package"]
            if (
                package.get("name"),
                package.get("version"),
                package.get("rust-version"),
                package.get("license"),
            ) != ("strling", version, "1.75", "Apache-2.0"):
                raise ValueError("crate coordinate or runtime metadata mismatch")
            manifest = tomllib.loads(_metadata(files, "*/Cargo.toml").decode())
            if manifest.get("lib", {}).get(
                "path"
            ) != "core/src/lib_public.rs" or not any(
                name.endswith("/core/src/lib_public.rs") for name in files
            ):
                raise ValueError("crate omits the canonical public facade sources")
        elif slug in {"csharp", "fsharp"}:
            nuspec = ET.fromstring(_metadata(files, "*.nuspec"))
            metadata = next(
                child for child in nuspec if child.tag.split("}")[-1] == "metadata"
            )
            fields = {child.tag.split("}")[-1]: child.text for child in metadata}
            if (fields.get("id"), fields.get("version")) != (
                artifact["package_name"],
                version,
            ):
                raise ValueError("NuGet coordinate mismatch")
            _metadata(files, "lib/net9.0/" + artifact["package_name"] + ".dll")
            if slug == "fsharp":
                references = [
                    element.attrib.get("version")
                    for element in metadata.iter()
                    if element.tag.split("}")[-1] == "dependency"
                    and element.attrib.get("id") == "STRling"
                ]
                if references != ["[" + version + "]"] or any(
                    name.startswith("runtimes/") for name in files
                ):
                    raise ValueError(
                        "F# requires the exact coordinated C# dependency and its single native owner"
                    )
            if slug == "csharp":
                native_payload = _metadata(
                    files, "runtimes/win-x64/native/strling_interop.dll"
                )
                native_identity(native_payload, version)
                inspect_native(native_payload)
                _metadata(files, "THIRD_PARTY_NOTICES.txt")
        elif slug == "cpp" and path.name.endswith(".upload.zip"):
            from tooling.conan_release import upload_inventory, verify_upload_archive

            metadata, _ = upload_inventory(path, version)
            cache_name = metadata["cache_name"]
            if cache_name != path.name.removesuffix(".upload.zip") + ".tgz":
                raise ValueError("unsafe Conan cache source filename")
            verify_upload_archive(path, path.with_name(cache_name), version)
        elif slug == "cpp":
            from tooling.conan_release import cache_inventory

            package_list = cache_inventory(path, version)
            if set(package_list) != {"strling/" + version}:
                raise ValueError("Conan coordinate mismatch")
            revisions = package_list["strling/" + version]["revisions"]
            package_folders = [
                binary["package_folder"] + "/"
                for revision in revisions.values()
                for package in revision["packages"].values()
                for binary in package["revisions"].values()
            ]
            if len(package_folders) != 1:
                raise ValueError("Conan archive must identify one exact binary package")
            package_files = {
                name: data
                for name, data in files.items()
                if name.startswith(package_folders[0])
            }
            if artifact.get("assembly_scope") is not None:
                info = configparser.ConfigParser(interpolation=None)
                profile = configparser.ConfigParser(interpolation=None)
                try:
                    info.read_string(
                        _metadata(package_files, "*/conaninfo.txt").decode()
                    )
                    profile.read_string(
                        (
                            root / "bindings/cpp/profiles" / artifact["assembly_scope"]
                        ).read_text(encoding="utf-8")
                    )
                    if dict(info["settings"]) != dict(profile["settings"]):
                        raise ValueError(
                            "Conan binary settings differ from the registered build profile"
                        )
                except configparser.Error as error:
                    raise ValueError("invalid Conan binary settings") from error
            for pattern in (
                "*/include/strling/native.hpp",
                "*/include/strling.h",
                "*/licenses/LICENSE",
                "*/licenses/THIRD_PARTY_NOTICES.txt",
            ):
                _metadata(package_files, pattern)
            for base in ("strling_cpp", "strling", "strling_interop"):
                if not any(
                    name.endswith(("/lib" + base + ".a", "/" + base + ".lib"))
                    for name in package_files
                ):
                    raise ValueError("Conan omits required static archive: " + base)
        # Sidecar POMs are validated as data; class and dependency content is
        # checked by the registered JVM package consumer and release graph.
        elif slug in {"java", "kotlin"} and path.suffix == ".xml":
            document = ET.fromstring(next(iter(files.values())))
            fields = {child.tag.split("}")[-1]: child.text for child in document}
            if (
                fields.get("groupId"),
                fields.get("artifactId"),
                fields.get("version"),
            ) != (
                ("com.strling", "strling-jvm", version)
                if slug == "java" and member["name"] == "bindings/jvm/pom.xml"
                else (*artifact["package_name"].split(":"), version)
            ):
                raise ValueError("Maven coordinate mismatch")
        for name, data in files.items():
            key = member["name"] + "!/" + name if packed else name
            graph.append(
                {
                    "name": key,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "sha1": hashlib.sha1(data, usedforsecurity=False).hexdigest(),
                    "bytes": len(data),
                }
            )
            all_files[key] = data
    if slug in {"java", "kotlin"}:
        from tooling.maven_release import central_files

        central_files(root, artifact, version, members)
    if slug == "php":
        package = unique_json(
            _metadata(all_files, "bindings/php/composer.json").decode()
        )
        if (package.get("name"), package.get("version"), package.get("license")) != (
            artifact["package_name"],
            version,
            "Apache-2.0",
        ):
            raise ValueError("Composer coordinate or license mismatch")
    elif slug == "r":
        description = email.parser.Parser().parsestr(
            _metadata(all_files, "bindings/r/DESCRIPTION").decode()
        )
        if (
            description.get_all("Package") != [artifact["package_name"]]
            or description.get_all("Version") != [version]
            or description.get_all("License") != ["Apache License (== 2.0)"]
        ):
            raise ValueError("R package coordinate or license mismatch")
    elif slug == "go":
        modules = re.findall(
            r"(?m)^module\s+(\S+)\s*$",
            _metadata(all_files, "bindings/go/go.mod").decode(),
        )
        if modules != [artifact["package_name"]]:
            raise ValueError("Go module coordinate mismatch")
    elif slug == "swift":
        names = re.findall(
            r'let package\s*=\s*Package\s*\(\s*name:\s*"([^"]+)"',
            _metadata(all_files, "bindings/swift/Package.swift").decode(),
        )
        if names != [artifact["package_name"]]:
            raise ValueError("Swift package coordinate mismatch")
    elif slug == "dart":
        package = unique_yaml(_metadata(all_files, "*/pubspec.yaml"))
        if (package.get("name"), package.get("version")) != (
            artifact["package_name"],
            version,
        ):
            raise ValueError("Pub package coordinate mismatch")
    elif slug == "perl":
        package = unique_json(
            _metadata(all_files, "*!/STRling-" + version + "/META.json").decode()
        )
        if (package.get("name"), str(package.get("version"))) != (
            artifact["package_name"],
            "v" + version,
        ):
            raise ValueError("CPAN distribution coordinate mismatch")
    for alternatives in artifact["payload_contract"]["required_file_groups"]:
        if not any(
            fnmatch.fnmatchcase(name, pattern.replace("VERSION", version))
            for pattern in alternatives
            for name in all_files
        ):
            raise ValueError("required package content absent: " + repr(alternatives))
    return sorted(graph, key=lambda row: row["name"])
