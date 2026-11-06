"""Assemble source and API-documentation classifiers for certified JVM subjects.

The host packages remain thin adapters. No Maven deployment or signing happens
here; protected publication adds detached signatures over these exact bytes.
"""

from __future__ import annotations

import html
import hashlib
import io
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def central_files(
    root: Path, artifact: dict, version: str, members: list[dict]
) -> dict[str, bytes]:
    """Map exact certified files to the standard Maven repository layout."""
    expected = (
        {"strling", "strling-jvm"}
        if artifact["id"] == "release:java"
        else {"strling-kotlin"}
    )
    coordinates = {}
    files = {}
    for member in members:
        path = root / member["name"]
        if path.suffix != ".xml":
            continue
        document = ET.fromstring(path.read_bytes())
        fields = {}
        for child in document:
            key = child.tag.split("}")[-1]
            if key in fields:
                raise ValueError("duplicate Maven POM field: " + key)
            fields[key] = child
        for element in document.iter():
            element.tag = element.tag.split("}")[-1]
        group = fields["groupId"].text
        name = fields["artifactId"].text
        if (
            group != "com.strling"
            or name not in expected
            or fields["version"].text != version
        ):
            raise ValueError("Maven publication coordinate mismatch")
        for key in ("name", "description", "url", "licenses", "developers", "scm"):
            if key not in fields or (
                key in {"name", "description", "url"}
                and not (fields[key].text or "").strip()
            ):
                raise ValueError("Maven Central POM metadata is incomplete: " + key)
        for field_path in (
            "licenses/license/name",
            "licenses/license/url",
            "developers/developer/name",
            "scm/connection",
            "scm/developerConnection",
            "scm/url",
        ):
            element = document.find(field_path)
            if element is None or not (element.text or "").strip():
                raise ValueError(
                    "Maven Central POM metadata is incomplete: " + field_path
                )
        dependencies = document.findall("dependencies/dependency")
        bridge_dependencies = []
        for dependency in dependencies:
            if (
                dependency.find("systemPath") is not None
                or dependency.findtext("scope") == "system"
            ):
                raise ValueError(
                    "Maven publication cannot depend on local system paths"
                )
            if dependency.findtext("groupId") == "com.strling":
                bridge_dependencies.append(dependency)
        if name in {"strling", "strling-kotlin"}:
            if len(bridge_dependencies) != 1 or (
                bridge_dependencies[0].findtext("artifactId") != "strling-jvm"
                or bridge_dependencies[0].findtext("version")
                not in {version, "[" + version + "]"}
                or bridge_dependencies[0].findtext("scope", "compile") != "compile"
            ):
                raise ValueError(
                    "Maven adapter must declare its exact coordinated JVM companion"
                )
        elif bridge_dependencies:
            raise ValueError(
                "The shared JVM companion cannot depend on another product package"
            )
        prefix = "com/strling/" + name + "/" + version + "/" + name + "-" + version
        if name in coordinates:
            raise ValueError("duplicate Maven coordinate")
        coordinates[name] = prefix
        files[prefix + ".pom"] = path.read_bytes()
    if set(coordinates) != expected:
        raise ValueError(
            "Maven release set omits its primary package or shared companion"
        )
    for member in members:
        path = root / member["name"]
        if path.suffix == ".xml":
            continue
        match = next(
            (
                (name, prefix)
                for name, prefix in coordinates.items()
                if path.name
                in {
                    name + "-" + version + suffix
                    for suffix in (".jar", "-sources.jar", "-javadoc.jar")
                }
            ),
            None,
        )
        if match is None:
            raise ValueError("unregistered Maven publication payload: " + path.name)
        name, prefix = match
        target = prefix + path.name[len(name + "-" + version) :]
        if target in files:
            raise ValueError("duplicate Maven publication file")
        files[target] = path.read_bytes()
    for name, prefix in coordinates.items():
        if any(
            prefix + suffix not in files
            for suffix in (".pom", ".jar", "-sources.jar", "-javadoc.jar")
        ):
            raise ValueError(
                "Maven release set requires binary, source and documentation classifiers"
            )
    return files


def signed_envelope(
    files: dict[str, bytes], private_key: str, passphrase: str, fingerprint: str
) -> tuple[bytes, str]:
    """Sign existing distribution bytes; create only registry transport metadata."""
    if re.fullmatch(r"[A-F0-9]{40}", fingerprint) is None:
        raise ValueError("owner-approved PGP fingerprint is required")
    if "\n" in passphrase or "\r" in passphrase:
        raise ValueError("invalid signing passphrase framing")
    with tempfile.TemporaryDirectory(prefix="strling-pgp-envelope-") as temporary:
        home = Path(temporary)
        home.chmod(0o700)

        def gpg(*arguments, input=None):
            return subprocess.run(
                ["gpg", "--homedir", str(home), "--batch", "--no-tty", *arguments],
                input=input,
                capture_output=True,
                check=True,
            ).stdout

        try:
            gpg("--import", input=private_key.encode())
            keys = gpg("--with-colons", "--list-secret-keys").decode()
            fingerprints = [
                line.split(":")[9]
                for line in keys.splitlines()
                if line.startswith("fpr:")
            ]
            if fingerprint not in fingerprints:
                raise ValueError(
                    "protected signing key differs from owner authorization"
                )
            envelope = dict(files)
            for name, payload in files.items():
                # Input on stdin is the passphrase only; distribution bytes are
                # read from an exact temporary copy and verified below.
                path = home / "payload"
                signature = home / "payload.asc"
                path.write_bytes(payload)
                signature.unlink(missing_ok=True)
                gpg(
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "--local-user",
                    fingerprint + "!",
                    "--armor",
                    "--detach-sign",
                    "--output",
                    str(signature),
                    str(path),
                    input=(passphrase + "\n").encode(),
                )
                status = gpg(
                    "--status-fd", "1", "--verify", str(signature), str(path)
                ).decode()
                if (
                    "[GNUPG:] VALIDSIG " + fingerprint + " " not in status
                    or path.read_bytes() != payload
                ):
                    raise ValueError("detached signature verification failed")
                envelope[name + ".asc"] = signature.read_bytes()
                # Central requires these compatibility checksums. Release
                # authorization and artifact authentication continue to use SHA-256.
                for algorithm in ("md5", "sha1", "sha256", "sha512"):
                    envelope[name + "." + algorithm] = (
                        hashlib.new(algorithm, payload, usedforsecurity=False)
                        .hexdigest()
                        .encode()
                    )
            buffer = io.BytesIO()
            with zipfile.ZipFile(
                buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for name, payload in sorted(envelope.items()):
                    info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
                    info.external_attr = 0o100644 << 16
                    info.create_system = 3
                    archive.writestr(info, payload)
            data = buffer.getvalue()
            return data, hashlib.sha256(data).hexdigest()
        finally:
            subprocess.run(
                ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
                capture_output=True,
                check=False,
            )


def deterministic_jar(path: Path, files: dict[str, bytes]) -> None:
    if not files or any(
        name.startswith("/") or ".." in Path(name).parts for name in files
    ):
        raise ValueError("invalid JVM classifier contents")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(
            files.items(), key=lambda item: (item[0] != "META-INF/MANIFEST.MF", item[0])
        ):
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def canonical_binary_jar(path: Path) -> None:
    """Assemble portable JAR metadata before certification, retaining every byte.

    Maven inherits host filesystem permission bits. Package files are data with
    mode 0644 regardless of NTFS/Unix source modes; this fixes assembly rather
    than adding any verification-time reproducibility normalization.
    """
    from tooling.release_payload import archive_files

    files = archive_files(path)
    if "META-INF/MANIFEST.MF" not in files or any(
        name.startswith("META-INF/") and name.endswith((".SF", ".RSA", ".DSA", ".EC"))
        for name in files
    ):
        raise ValueError("binary JAR must be an unsigned canonical assembly")
    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=".canonical.jar", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        deterministic_jar(temporary, files)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def classifiers(root: Path, slug: str, version: str) -> None:
    from tooling.jvm_adapter_package import EXTERNAL_PACKAGES

    if slug not in {"java", "jvm", "kotlin"}:
        raise ValueError("unknown JVM release surface")
    binding = root / "bindings" / slug
    artifact = {"java": "strling", "jvm": "strling-jvm", "kotlin": "strling-kotlin"}[
        slug
    ]
    output = binding / ("build/libs" if slug == "kotlin" else "target")
    source_root = binding / "src/main" / ("kotlin" if slug == "kotlin" else "java")
    tracked = subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--",
            source_root.relative_to(root).as_posix(),
        ]
    )
    sources = {}
    source_paths = []
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        path = root / raw.decode("utf-8")
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid JVM release source")
        sources[path.relative_to(source_root).as_posix()] = path.read_bytes()
        if path.suffix == ".java":
            source_paths.append(path)
    license_bytes = (root / "LICENSE").read_bytes()
    deterministic_jar(
        output / f"{artifact}-{version}-sources.jar",
        {**sources, "META-INF/LICENSE": license_bytes},
    )
    docs = output / "release-api-docs"
    if slug == "kotlin":
        readme = (binding / "README.md").read_bytes()
        files = {
            "README.md": readme,
            "index.html": (
                "<!doctype html><meta charset=utf-8><title>STRling Kotlin API</title><pre>"
                + html.escape(readme.decode())
                + "</pre>"
            ).encode(),
        }
    else:
        repository = Path(
            os.environ.get(
                "STRLING_MAVEN_REPOSITORY", str(Path.home() / ".m2/repository")
            )
        )
        dependencies = []
        for coordinate, release, _ in EXTERNAL_PACKAGES:
            if coordinate.startswith(("org.jetbrains.kotlin:", "org.jetbrains:")):
                continue
            group, name = coordinate.split(":")
            path = (
                repository
                / Path(*group.split("."))
                / name
                / release
                / f"{name}-{release}.jar"
            )
            if not path.is_file():
                raise ValueError(
                    "missing published JVM dependency for API documentation"
                )
            dependencies.append(path)
        if slug == "java":
            dependencies.append(
                root / "bindings/jvm/target" / f"strling-jvm-{version}.jar"
            )
        subprocess.run(
            [
                "javadoc",
                "-quiet",
                "-notimestamp",
                "-Xdoclint:all,-missing",
                "--release",
                "11",
                "-encoding",
                "UTF-8",
                "-classpath",
                os.pathsep.join(str(path) for path in dependencies),
                "-d",
                str(docs),
                *map(str, source_paths),
            ],
            cwd=binding,
            check=True,
        )
        files = {
            path.relative_to(docs).as_posix(): path.read_bytes()
            for path in docs.rglob("*")
            if path.is_file()
        }
        if "index.html" not in files:
            raise ValueError("JVM API documentation is incomplete")
    deterministic_jar(
        output / f"{artifact}-{version}-javadoc.jar",
        {**files, "META-INF/LICENSE": license_bytes},
    )
