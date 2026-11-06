"""Transport approved Conan cache bytes without importing candidate recipes.

The ordinary Conan upload command imports recipes to evaluate upload policy.
Builds materialize standard registry files before certification; protected
publication uses only the pinned client's REST methods. No cache restoration,
loader, graph, compression, build, signing plugin, or recipe hook runs there.
"""

from __future__ import annotations

import contextlib
import hashlib
import gzip
import importlib.metadata
import io
import json
import os
import re
import tempfile
import tarfile
import zipfile
from pathlib import Path

from tooling.release_payload import archive_files
from tooling.sync_versions import unique_json


def cache_inventory(path: Path, version: str) -> dict:
    files = archive_files(path)
    document = unique_json(files["pkglist.json"].decode())
    if set(document) != {"strling/" + version}:
        raise ValueError("Conan cache coordinate mismatch")
    revisions = document["strling/" + version]["revisions"]
    if len(revisions) != 1:
        raise ValueError("Conan cache requires one exact recipe revision")
    for revision, recipe in revisions.items():
        if re.fullmatch(r"[0-9a-f]{32}", revision) is None:
            raise ValueError("invalid Conan recipe revision")
        if re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", recipe["recipe_folder"]) is None:
            raise ValueError("unsafe Conan recipe cache alias")
        for package_id, package in recipe["packages"].items():
            if re.fullmatch(r"[0-9a-f]{40}", package_id) is None:
                raise ValueError("invalid Conan package identity")
            for package_revision, binary in package["revisions"].items():
                if re.fullmatch(r"[0-9a-f]{32}", package_revision) is None:
                    raise ValueError("invalid Conan package revision")
                if (
                    re.fullmatch(r"b/[a-zA-Z0-9_-]{1,80}/p", binary["package_folder"])
                    is None
                ):
                    raise ValueError("unsafe Conan binary cache alias")
                metadata = binary.get("metadata_folder")
                if (
                    metadata is not None
                    and metadata != binary["package_folder"][:-1] + "d/metadata"
                ):
                    raise ValueError("unsafe Conan metadata cache alias")
    return document


def _canonical_manifest(data: bytes) -> bytes:
    first, separator, rest = data.partition(b"\n")
    if not separator or re.fullmatch(rb"[0-9]+(?:\.[0-9]+)?", first) is None:
        raise ValueError("unknown Conan manifest creation timestamp")
    return b"0\n" + rest


def _canonical_tgz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(
        fileobj=buffer, mode="wb", mtime=0, filename="", compresslevel=9
    ) as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive:
            for name, payload in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode, entry.mtime = len(payload), 0o644, 0
                archive.addfile(entry, io.BytesIO(payload))
    return buffer.getvalue()


def materialize_upload(cache_archive: Path, output: Path, version: str) -> None:
    """Materialize exact registry upload files during the credential-free build.

    Only transport metadata is canonicalized: tar/gzip creation metadata, read
    permissions for this static-only package, and Conan manifest creation times.
    Compiler, recipe, header, source, dependency and license bytes remain exact.
    """
    inventory = cache_inventory(cache_archive, version)
    files = archive_files(cache_archive)
    revision, recipe = next(iter(inventory["strling/" + version]["revisions"].items()))
    prefix = recipe["recipe_folder"]
    exports = {
        name[len(prefix + "/e/") :]: data
        for name, data in files.items()
        if name.startswith(prefix + "/e/")
    }
    sources = {
        name[len(prefix + "/es/") :]: data
        for name, data in files.items()
        if name.startswith(prefix + "/es/")
    }
    payloads = {
        "recipe/conanfile.py": exports.pop("conanfile.py"),
        "recipe/conanmanifest.txt": _canonical_manifest(
            exports.pop("conanmanifest.txt")
        ),
    }
    if exports:
        payloads["recipe/conan_export.tgz"] = _canonical_tgz(exports)
    if sources:
        payloads["recipe/conan_sources.tgz"] = _canonical_tgz(sources)
    packages = {}
    for package_id, package in recipe["packages"].items():
        if len(package["revisions"]) != 1:
            raise ValueError("one binary package must have one exact revision")
        package_revision, binary = next(iter(package["revisions"].items()))
        base = binary["package_folder"] + "/"
        data = {
            name[len(base) :]: payload
            for name, payload in files.items()
            if name.startswith(base)
        }
        target = "packages/" + package_id + "/"
        payloads[target + "conaninfo.txt"] = data.pop("conaninfo.txt")
        payloads[target + "conanmanifest.txt"] = _canonical_manifest(
            data.pop("conanmanifest.txt")
        )
        payloads[target + "conan_package.tgz"] = _canonical_tgz(data)
        packages[package_id] = package_revision
    from tooling.release_supply_chain import _normalized_conan_sha256

    metadata = {
        "schema_version": "1.0.0",
        "product_version": version,
        "cache_name": cache_archive.name,
        "cache_normalized_sha256": _normalized_conan_sha256(cache_archive),
        "recipe_revision": revision,
        "packages": packages,
        "file_sha256": {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in payloads.items()
        },
    }
    payloads["upload.json"] = json.dumps(
        metadata, sort_keys=True, separators=(",", ":")
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    staged_output = output.with_name("." + output.name + ".tmp")
    with zipfile.ZipFile(
        staged_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, payload in sorted(payloads.items()):
            entry = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            entry.create_system, entry.external_attr = 3, 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, payload)
    os.replace(staged_output, output)


def upload_inventory(path: Path, version: str) -> tuple[dict, dict[str, bytes]]:
    files = archive_files(path)
    metadata = unique_json(files.pop("upload.json").decode())
    if set(metadata) != {
        "schema_version",
        "product_version",
        "cache_name",
        "cache_normalized_sha256",
        "recipe_revision",
        "packages",
        "file_sha256",
    }:
        raise ValueError("invalid Conan upload envelope fields")
    if metadata["schema_version"] != "1.0.0" or metadata["product_version"] != version:
        raise ValueError("Conan upload envelope version mismatch")
    if re.fullmatch(r"[0-9a-f]{32}", metadata["recipe_revision"]) is None:
        raise ValueError("invalid Conan upload recipe revision")
    if not metadata["packages"] or any(
        re.fullmatch(r"[0-9a-f]{40}", key) is None
        or re.fullmatch(r"[0-9a-f]{32}", value) is None
        for key, value in metadata["packages"].items()
    ):
        raise ValueError("invalid Conan upload binary identities")
    allowed = {
        "recipe/conanfile.py",
        "recipe/conanmanifest.txt",
        "recipe/conan_sources.tgz",
        "recipe/conan_export.tgz",
    }
    for package_id in metadata["packages"]:
        allowed.update(
            "packages/" + package_id + "/" + name
            for name in ("conaninfo.txt", "conanmanifest.txt", "conan_package.tgz")
        )
    required = allowed - {"recipe/conan_sources.tgz", "recipe/conan_export.tgz"}
    if (
        not required.issubset(files)
        or set(files) - allowed
        or metadata["file_sha256"]
        != {
            name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()
        }
    ):
        raise ValueError("Conan upload payload set or bytes changed")
    return metadata, files


def verify_upload_archive(upload_path: Path, cache_archive: Path, version: str) -> None:
    metadata, uploaded = upload_inventory(upload_path, version)
    from tooling.release_supply_chain import _normalized_conan_sha256

    if metadata["cache_name"] != cache_archive.name or metadata[
        "cache_normalized_sha256"
    ] != _normalized_conan_sha256(cache_archive):
        raise ValueError(
            "Conan registry files differ from their certified source cache"
        )
    inventory = cache_inventory(cache_archive, version)
    cached = archive_files(cache_archive)
    revision, recipe = next(iter(inventory["strling/" + version]["revisions"].items()))
    if revision != metadata["recipe_revision"]:
        raise ValueError("Conan registry recipe revision differs from source cache")
    prefix = recipe["recipe_folder"]
    exports = {
        name[len(prefix + "/e/") :]: data
        for name, data in cached.items()
        if name.startswith(prefix + "/e/")
    }
    if uploaded["recipe/conanfile.py"] != exports.pop("conanfile.py") or uploaded[
        "recipe/conanmanifest.txt"
    ] != _canonical_manifest(exports.pop("conanmanifest.txt")):
        raise ValueError("Conan registry recipe content changed")

    def compare_archive(name, expected):
        if not expected:
            if name in uploaded:
                raise ValueError("unexpected Conan transport archive")
        elif (
            name not in uploaded
            or archive_files(io.BytesIO(uploaded[name])) != expected
        ):
            raise ValueError(
                "Conan transport archive omits or substitutes certified files"
            )

    compare_archive("recipe/conan_export.tgz", exports)
    sources = {
        name[len(prefix + "/es/") :]: data
        for name, data in cached.items()
        if name.startswith(prefix + "/es/")
    }
    compare_archive("recipe/conan_sources.tgz", sources)
    expected_packages = {}
    for package_id, package in recipe["packages"].items():
        package_revision, binary = next(iter(package["revisions"].items()))
        expected_packages[package_id] = package_revision
        base = binary["package_folder"] + "/"
        files = {
            name[len(base) :]: data
            for name, data in cached.items()
            if name.startswith(base)
        }
        target = "packages/" + package_id + "/"
        if uploaded[target + "conaninfo.txt"] != files.pop("conaninfo.txt") or uploaded[
            target + "conanmanifest.txt"
        ] != _canonical_manifest(files.pop("conanmanifest.txt")):
            raise ValueError("Conan binary metadata differs from source cache")
        compare_archive(target + "conan_package.tgz", files)
    if metadata["packages"] != expected_packages:
        raise ValueError("Conan upload binary denominator changed")


def _upload(
    archives: list[Path], version: str, endpoint: str, username: str, password: str
) -> bytes:
    if importlib.metadata.version("conan") != "2.31.2":
        raise ValueError("Conan transport requires the governed 2.31.2 client")
    from conan.api.conan_api import ConanAPI
    from conan.api.model import Remote, RecipeReference, PkgReference
    from conan.internal.errors import NotFoundException

    inventories = [
        upload_inventory(path, version)
        for path in archives
        if path.name.endswith(".upload.zip")
    ]
    if not inventories:
        raise ValueError("certified preassembled Conan upload files are missing")
    recipes, packages = {}, {}
    for metadata, files in inventories:
        recipe = {
            name.removeprefix("recipe/"): payload
            for name, payload in files.items()
            if name.startswith("recipe/")
        }
        recipe_hash = {
            name: hashlib.sha256(data).hexdigest() for name, data in recipe.items()
        }
        if recipes and recipes["sha256"] != recipe_hash:
            raise ValueError("Conan platform upload envelopes disagree on recipe bytes")
        recipes = {
            "sha256": recipe_hash,
            "files": recipe,
            "revision": metadata["recipe_revision"],
        }
        for package_id, revision in metadata["packages"].items():
            if package_id in packages:
                raise ValueError("duplicate approved Conan upload binary")
            prefix = "packages/" + package_id + "/"
            packages[package_id] = (
                revision,
                {
                    name[len(prefix) :]: data
                    for name, data in files.items()
                    if name.startswith(prefix)
                },
            )
    with tempfile.TemporaryDirectory(prefix="strling-conan-upload-") as temporary:
        directory = Path(temporary)
        with (
            contextlib.chdir(directory),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            # The protected path never restores a cache or invokes preparators:
            # every outbound artifact was already assembled and certified.
            api = ConanAPI(cache_folder=str(directory / "home"))
            remote = Remote("strling-release", endpoint, verify_ssl=True)
            api.remotes.user_login(remote, username, password)
            manager = api._api_helpers.remote_manager
            try:
                existing = manager.get_recipe_revisions(
                    RecipeReference.loads("strling/" + version), remote
                )
            except NotFoundException:
                existing = []
            if existing:
                raise ValueError("immutable Conan product version already exists")

            def staged(group, files):
                result = {}
                for name, payload in files.items():
                    path = directory / group / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                    result[name] = str(path)
                return result

            ref = RecipeReference.loads(
                "strling/" + version + "#" + recipes["revision"]
            )
            manager.upload_recipe(ref, staged("recipe", recipes["files"]), remote)
            receipts = []
            for package_id, (revision, files) in packages.items():
                pref = PkgReference(ref, package_id, revision)
                manager.upload_package(pref, staged(package_id, files), remote)
                receipts.append(
                    {
                        "package_id": package_id,
                        "package_revision": revision,
                        "upload_files_sha256": {
                            name: hashlib.sha256(data).hexdigest()
                            for name, data in files.items()
                        },
                    }
                )
            return json.dumps(
                {
                    "registry_endpoint": endpoint,
                    "version": version,
                    "recipe_revision": recipes["revision"],
                    "packages": receipts,
                },
                sort_keys=True,
            ).encode()


def upload(
    archives: list[Path], version: str, endpoint: str, username: str, password: str
) -> bytes:
    try:
        return _upload(archives, version, endpoint, username, password)
    except Exception:
        raise ValueError("approved Conan data transport failed") from None
