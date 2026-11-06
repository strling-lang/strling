"""Upload an exact approved subject; default operation is a credential-free plan.

Only the protected, reviewed workflow may request execution. This module never
compiles, installs dependencies, runs package lifecycle scripts, or creates a
replacement distribution. The release_supply_chain handoff is mandatory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import shutil
import tarfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# An isolated invocation admits only this reviewed tools directory for imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ROOT,
    ReleaseSupplyChainError,
    _surface_members,
    canonical_json,
    load_json,
    verify_publication_handoff,
)


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ReleaseSupplyChainError(
            "publication-credential",
            "required protected credential is unavailable: " + name,
        )
    return value


def _http(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ReleaseSupplyChainError(
            "publication-transport",
            "registry transport requires HTTPS without embedded credentials",
        )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, new_url):
            return None

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"User-Agent": "STRling-release-engineering", **(headers or {})},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
        payload = response.read(128 * 1024 * 1024 + 1)
        if len(payload) > 128 * 1024 * 1024:
            raise ReleaseSupplyChainError(
                "publication-response", "oversized registry response"
            )
        return payload


def multipart_file(
    path: Path, field: str, fields: dict[str, str] | None = None
) -> tuple[bytes, str]:
    payload = path.read_bytes()
    if any(character in path.name for character in ('"', "\r", "\n")):
        raise ReleaseSupplyChainError(
            "publication-payload", "unsafe multipart filename"
        )
    boundary = "strling-" + hashlib.sha256(payload).hexdigest()
    parts = []
    for name, value in (fields or {}).items():
        if any(character in name for character in ('"', "\r", "\n")):
            raise ReleaseSupplyChainError(
                "publication-payload", "unsafe multipart field"
            )
        parts.append(
            (
                "--"
                + boundary
                + '\r\nContent-Disposition: form-data; name="'
                + name
                + '"\r\n\r\n'
                + value
                + "\r\n"
            ).encode()
        )
    parts.append(
        (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="'
            + field
            + '"; filename="'
            + path.name
            + '"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + payload
        + b"\r\n"
    )
    parts.append(("--" + boundary + "--\r\n").encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def python_registry_receipt(version: str, members: list[dict]) -> bytes:
    """Read back exact PyPI file identities after the trusted action succeeds."""
    response = _http("https://pypi.org/pypi/STRling/" + version + "/json")
    document = json.loads(response)
    expected = {Path(row["name"]).name: row["sha256"] for row in members}
    rows = document.get("urls", [])
    observed = {row["filename"]: row["digests"]["sha256"] for row in rows}
    if (
        len(rows) != len(observed)
        or observed != expected
        or document.get("info", {}).get("version") != version
    ):
        raise ReleaseSupplyChainError(
            "publication-receipt",
            "PyPI did not retain the exact approved release file set",
        )
    return canonical_json(
        {
            "registry": "pypi.org",
            "version": version,
            "file_sha256": observed,
            "metadata_response_sha256": hashlib.sha256(response).hexdigest(),
            "public_installation_verified": False,
        }
    )


def _require_absent(url: str) -> None:
    try:
        _http(url)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise ReleaseSupplyChainError(
            "publication-availability", "registry availability check failed"
        ) from None
    raise ReleaseSupplyChainError(
        "publication-collision", "immutable destination already exists"
    )


def _crate_frame(path: Path, version: str) -> bytes:
    """Cargo registry upload framing, assembled solely from the approved crate."""
    with tarfile.open(path, "r:*") as archive:
        prefix = "strling-" + version + "/"
        manifest_file = archive.extractfile(prefix + "Cargo.toml")
        if manifest_file is None:
            raise ReleaseSupplyChainError(
                "publication-payload", "crate manifest is missing"
            )
        document = tomllib.loads(manifest_file.read().decode())
        package = document["package"]
        if (package["name"], package["version"]) != ("strling", version):
            raise ReleaseSupplyChainError(
                "publication-payload", "crate coordinate differs from approval"
            )
        dependencies = []
        sections = [(None, document), *document.get("target", {}).items()]
        for target, section in sections:
            for key, kind in (
                ("dependencies", "normal"),
                ("dev-dependencies", "dev"),
                ("build-dependencies", "build"),
            ):
                for name, value in section.get(key, {}).items():
                    value = {"version": value} if isinstance(value, str) else value
                    if any(field in value for field in ("path", "git", "registry")):
                        raise ReleaseSupplyChainError(
                            "publication-payload", "crate has an unpublished dependency"
                        )
                    dependencies.append(
                        {
                            "name": value.get("package", name),
                            "version_req": value["version"],
                            "features": value.get("features", []),
                            "optional": value.get("optional", False),
                            "default_features": value.get("default-features", True),
                            "target": target,
                            "kind": kind,
                            "registry": None,
                            "explicit_name_in_toml": name
                            if "package" in value
                            else None,
                        }
                    )
        metadata = {
            key: package.get(key)
            for key in (
                "name",
                "authors",
                "description",
                "documentation",
                "homepage",
                "keywords",
                "categories",
                "license",
                "license_file",
                "repository",
                "links",
                "rust_version",
            )
        }
        metadata["vers"] = version
        metadata["deps"] = dependencies
        metadata["features"] = document.get("features", {})
        metadata["rust_version"] = package.get("rust-version")
        metadata["license_file"] = package.get("license-file")
        metadata["readme_file"] = package.get("readme")
        readme = (
            archive.extractfile(prefix + package["readme"])
            if isinstance(package.get("readme"), str)
            else None
        )
        metadata["readme"] = readme.read().decode() if readme else None
    encoded, crate = canonical_json(metadata), path.read_bytes()
    return (
        struct.pack("<I", len(encoded))
        + encoded
        + struct.pack("<I", len(crate))
        + crate
    )


def publication_plan(artifact: dict, version: str, members: list[dict]) -> dict:
    slug = artifact["id"].removeprefix("release:")
    return {
        "artifact_id": artifact["id"],
        "version": version,
        "registry": artifact["registry"],
        "package_name": artifact["package_name"],
        "transport": artifact["credential_policy"]["mode"],
        "route": "exact-source-ref"
        if artifact["delivery_kind"] == "source-tag"
        else "certified-payload-upload",
        "subjects": [
            {"name": item["name"], "sha256": item["sha256"]} for item in members
        ],
        "publication_authorized": False,
        "surface": slug,
    }


def _companion_checksums(evidence: Path, surface: str) -> dict[str, str]:
    """Read only after the signed bundle and checksum companions were verified."""
    rows = {}
    for line in (
        (evidence.parent / "checksums" / (surface + ".sha256"))
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        if line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\\\x00]+)", line)
        if match is None or match[2] in rows:
            raise ReleaseSupplyChainError(
                "publication-companion", "invalid signed companion checksum set"
            )
        rows[match[2]] = match[1]
    return rows


def verify_nuget_registry_payload(payload: bytes, sbom: dict) -> dict:
    """Check exact certified content plus NuGet.org's mandatory repository seal.

    This is a registry transformation check, not build normalization. No archive
    content other than the verified repository signature may be added or changed.
    """
    from tooling.release_payload import archive_files

    files = archive_files(io.BytesIO(payload))
    expected = {}
    for row in sbom["files"]:
        _, name = row["fileName"].split("!/", 1)
        checksums = {
            item["algorithm"]: item["checksumValue"] for item in row["checksums"]
        }
        if name in expected or "SHA256" not in checksums:
            raise ReleaseSupplyChainError(
                "publication-companion", "invalid certified NuGet file graph"
            )
        expected[name] = checksums["SHA256"]
    observed = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
        if name != ".signature.p7s"
    }
    if ".signature.p7s" not in files or observed != expected:
        raise ReleaseSupplyChainError(
            "publication-companion",
            "public NuGet content differs from the certified package",
        )
    index_bytes = _http(
        "https://api.nuget.org/v3-index/repository-signatures/5.0.0/index.json"
    )
    index = json.loads(index_bytes)
    fingerprints = [
        row["fingerprints"]["2.16.840.1.101.3.4.2.1"]
        for row in index.get("signingCertificates", [])
    ]
    if (
        index.get("allRepositorySigned") is not True
        or not fingerprints
        or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in fingerprints)
    ):
        raise ReleaseSupplyChainError(
            "publication-companion",
            "NuGet.org repository signing identities are unavailable",
        )
    with tempfile.TemporaryDirectory(prefix="strling-public-nuget-") as temporary:
        package = Path(temporary) / "package.nupkg"
        package.write_bytes(payload)
        command = ["dotnet", "nuget", "verify", str(package), "--all"]
        for fingerprint in fingerprints:
            command.extend(["--certificate-fingerprint", fingerprint])
        environment = {
            name: value
            for name, value in os.environ.items()
            if not re.search(
                r"(?:TOKEN|PASSWORD|PASSPHRASE|API_KEY|PRIVATE_KEY)$", name, re.I
            )
        }
        environment.update(DOTNET_CLI_HOME=temporary, NUGET_PLUGIN_PATHS="")
        subprocess.run(
            command, cwd=temporary, env=environment, check=True, capture_output=True
        )
    return {
        "file_sha256": observed,
        "repository_signature_sha256": hashlib.sha256(
            files[".signature.p7s"]
        ).hexdigest(),
        "signing_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
    }


def upload(
    root: Path,
    artifact: dict,
    version: str,
    source_sha: str,
    members: list[dict],
    *,
    authorization: dict | None = None,
    verified_evidence: Path | None = None,
) -> bytes:
    """The caller must authenticate approval immediately before entering here."""
    slug = artifact["id"].removeprefix("release:")
    paths = [root / item["name"] for item in members]

    def one(suffix):
        matched = [path for path in paths if path.name.endswith(suffix)]
        if len(matched) != 1:
            raise ReleaseSupplyChainError(
                "publication-payload",
                "exactly one approved " + suffix + " payload is required",
            )
        return matched[0]

    def run(arguments, cwd=None):
        with tempfile.TemporaryDirectory(
            prefix="strling-approved-upload-"
        ) as temporary:
            completed = subprocess.run(
                arguments, cwd=cwd or temporary, check=True, capture_output=True
            )
            return completed.stdout

    if artifact["delivery_kind"] == "source-tag":
        tag = (
            artifact["registry"].removeprefix("github-tag:").replace("VERSION", version)
        )
        _require_absent(
            "https://api.github.com/repos/strling-lang/strling/git/ref/tags/"
            + urllib.parse.quote(tag, safe="")
        )
        return _http(
            "https://api.github.com/repos/strling-lang/strling/git/refs",
            method="POST",
            data=canonical_json({"ref": "refs/tags/" + tag, "sha": source_sha}),
            headers={
                "Authorization": "Bearer " + _secret("GITHUB_TOKEN"),
                "Content-Type": "application/json",
            },
        )
    if slug == "rust":
        _require_absent("https://crates.io/api/v1/crates/strling/" + version)
        return _http(
            "https://crates.io/api/v1/crates/new",
            method="PUT",
            data=_crate_frame(one(".crate"), version),
            headers={
                "Authorization": _secret("CARGO_REGISTRY_TOKEN"),
                "Content-Type": "application/octet-stream",
            },
        )
    if slug == "typescript":
        _require_absent("https://registry.npmjs.org/@strling-lang%2fstrling/" + version)
        return run(
            [
                "npm",
                "publish",
                str(one(".tgz")),
                "--ignore-scripts",
                "--registry=https://registry.npmjs.org",
                "--userconfig=" + os.devnull,
                "--globalconfig=" + os.devnull,
                "--provenance",
                "--access",
                "public",
                "--tag",
                "next" if "-" in version else "latest",
            ]
        )
    if slug == "fsharp":
        if verified_evidence is None:
            raise ReleaseSupplyChainError(
                "publication-companion", "signed primary package checksums are required"
            )
        remote = _http(
            "https://api.nuget.org/v3-flatcontainer/strling/"
            + version
            + "/strling."
            + version
            + ".nupkg"
        )
        verify_nuget_registry_payload(
            remote, load_json(verified_evidence.parent / "sbom/csharp.spdx.json")
        )
    if slug in {"csharp", "fsharp"}:
        name = artifact["package_name"].lower()
        _require_absent(
            f"https://api.nuget.org/v3-flatcontainer/{name}/{version}/{name}.nuspec"
        )
        return run(
            [
                "dotnet",
                "nuget",
                "push",
                str(one(".nupkg")),
                "--api-key",
                _secret("NUGET_KEY"),
                "--source",
                "https://api.nuget.org/v3/index.json",
            ]
        )
    if slug == "ruby":
        _require_absent(
            "https://rubygems.org/api/v2/rubygems/strling/versions/" + version + ".json"
        )
        return run(["gem", "push", str(one(".gem")), "--host", "https://rubygems.org"])
    if slug == "perl":
        owner = _secret("PAUSE_USERNAME")
        if authorization is None or owner != next(
            row["registry_owner"]
            for row in authorization["destinations"]
            if row["artifact_id"] == artifact["id"]
        ):
            raise ReleaseSupplyChainError(
                "publication-destination",
                "PAUSE credential does not match the approved uploader",
            )
        if re.fullmatch(r"[A-Z][A-Z0-9]+", owner) is None:
            raise ReleaseSupplyChainError(
                "publication-destination", "PAUSE requires an exact uppercase uploader"
            )
        _require_absent(
            "https://fastapi.metacpan.org/v1/release/" + owner + "/STRling-" + version
        )
        archive = one(".tar.gz")
        payload, content_type = multipart_file(
            archive,
            "pause99_add_uri_httpupload",
            {
                "HIDDENNAME": owner,
                "CAN_MULTIPART": "1",
                "pause99_add_uri_upload": archive.name,
                "pause99_add_uri_uri": "",
                "SUBMIT_pause99_add_uri_httpupload": " Upload this file from my disk ",
            },
        )
        token = base64.b64encode(
            (owner + ":" + _secret("PAUSE_PASSWORD")).encode()
        ).decode()
        return _http(
            "https://pause.perl.org/pause/authenquery?ACTION=add_uri",
            method="POST",
            data=payload,
            headers={"Authorization": "Basic " + token, "Content-Type": content_type},
        )
    if slug == "lua":
        if authorization is None:
            raise ReleaseSupplyChainError(
                "publication-destination", "LuaRocks requires an approved uploader"
            )
        destination = next(
            row
            for row in authorization["destinations"]
            if row["artifact_id"] == artifact["id"]
        )
        owner = destination["registry_owner"]
        if re.fullmatch(r"[A-Za-z0-9_-]+", owner) is None:
            raise ReleaseSupplyChainError(
                "publication-destination",
                "LuaRocks uploader is not operationally verified",
            )
        headers = {"Authorization": "Bearer " + _secret("LUAROCKS_API_KEY")}
        status = json.loads(
            _http("https://luarocks.org/api/1/bearer/status", headers=headers)
        )
        if (
            type(status.get("user_id")) is not int
            or status["user_id"] != destination["registry_user_id"]
        ):
            raise ReleaseSupplyChainError(
                "publication-destination",
                "LuaRocks credential belongs to a different approved uploader",
            )
        coordinate = version + "-1"
        available = json.loads(
            _http(
                "https://luarocks.org/api/1/bearer/check_rockspec?"
                + urllib.parse.urlencode({"package": "strling", "version": coordinate}),
                headers=headers,
            )
        )
        if (
            not {"module", "version"}.issubset(available)
            or available.get("errors")
            or available["version"] is not None
        ):
            raise ReleaseSupplyChainError(
                "publication-collision", "LuaRocks coordinate is present or unqualified"
            )
        _require_absent(
            "https://luarocks.org/manifests/"
            + owner
            + "/strling-"
            + coordinate
            + ".rockspec"
        )

        def send_file(endpoint, field, path):
            body, content_type = multipart_file(path, field)
            return json.loads(
                _http(
                    "https://luarocks.org/api/1/bearer/" + endpoint,
                    method="POST",
                    data=body,
                    headers={**headers, "Content-Type": content_type},
                )
            )

        first = send_file("upload", "rockspec_file", one(".rockspec"))
        version_record = first.get("version", {})
        expected_url = "https://luarocks.org/modules/" + owner + "/strling"
        if (
            first.get("errors")
            or first.get("module_url") != expected_url
            or version_record.get("version_name") != coordinate
            or type(version_record.get("id")) is not int
            or version_record["id"] <= 0
        ):
            raise ReleaseSupplyChainError(
                "publication-receipt",
                "LuaRocks did not confirm the exact approved owner and coordinate",
            )
        second = send_file(
            "upload_rock/" + str(version_record["id"]), "rock_file", one(".src.rock")
        )
        if (
            second.get("errors")
            or second.get("module_url") != expected_url
            or second.get("rock", {}).get("arch") != "src"
        ):
            raise ReleaseSupplyChainError(
                "publication-receipt",
                "LuaRocks did not confirm the preassembled source rock",
            )
        return canonical_json({"rockspec": first, "source_rock": second})
    if slug == "cpp":
        from tooling.conan_release import upload as conan_upload

        if authorization is None:
            raise ReleaseSupplyChainError(
                "publication-destination", "owner-approved Conan endpoint is missing"
            )
        destination = next(
            item
            for item in authorization["destinations"]
            if item["artifact_id"] == artifact["id"]
        )
        return conan_upload(
            paths,
            version,
            destination["registry_endpoint"],
            _secret("CONAN_USERNAME"),
            _secret("CONAN_PASSWORD"),
        )
    if slug in {"java", "kotlin"}:
        from tooling.maven_release import central_files, signed_envelope

        if authorization is None:
            raise ReleaseSupplyChainError(
                "publication-signing", "owner-approved signing identity is missing"
            )
        destination = next(
            item
            for item in authorization["destinations"]
            if item["artifact_id"] == artifact["id"]
        )
        files = central_files(root, artifact, version, members)
        for name in files:
            if name.endswith(".pom"):
                _require_absent("https://repo1.maven.org/maven2/" + name)
        if slug == "kotlin":
            # The shared bridge is released with Java, never as an unpublished
            # workspace-only runtime dependency.
            if verified_evidence is None:
                raise ReleaseSupplyChainError(
                    "publication-companion",
                    "signed primary package checksums are required",
                )
            expected = _companion_checksums(verified_evidence, "java")
            for extension in ("pom", "jar"):
                name = (
                    "bindings/jvm/pom.xml"
                    if extension == "pom"
                    else "bindings/jvm/target/strling-jvm-" + version + ".jar"
                )
                remote = _http(
                    "https://repo1.maven.org/maven2/com/strling/strling-jvm/"
                    + version
                    + "/strling-jvm-"
                    + version
                    + "."
                    + extension
                )
                if hashlib.sha256(remote).hexdigest() != expected[name]:
                    raise ReleaseSupplyChainError(
                        "publication-companion",
                        "public JVM companion differs from the certified primary artifact",
                    )
        data, envelope_sha256 = signed_envelope(
            files,
            _secret("GPG_PRIVATE_KEY"),
            os.environ.get("GPG_PASSPHRASE", ""),
            destination["signing_key_fingerprint"],
        )
        boundary = "strling-" + envelope_sha256
        payload = (
            (
                "--"
                + boundary
                + '\r\nContent-Disposition: form-data; name="bundle"; filename="bundle.zip"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + data
            + ("\r\n--" + boundary + "--\r\n").encode()
        )
        token = base64.b64encode(
            (_secret("SONATYPE_USERNAME") + ":" + _secret("SONATYPE_PASSWORD")).encode()
        ).decode()
        response = _http(
            "https://central.sonatype.com/api/v1/publisher/upload?publishingType=AUTOMATIC",
            method="POST",
            data=payload,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
            },
        )
        deployment_id = response.decode("ascii").strip()

        if re.fullmatch(r"[0-9a-fA-F-]{36}", deployment_id) is None:
            raise ReleaseSupplyChainError(
                "publication-receipt", "unexpected Central deployment receipt"
            )
        return canonical_json(
            {
                "deployment_id": deployment_id,
                "upload_envelope_sha256": envelope_sha256,
                "certified_file_sha256": {
                    name: hashlib.sha256(payload).hexdigest()
                    for name, payload in files.items()
                },
            }
        )
    if slug == "dart":
        # The exact source assembly is the registered subject for this route.
        # Validation/resolution already ran without credentials during certification.
        # Relocate the authenticated assembly verbatim so ancestor checkout
        # ignores cannot change Pub's file selection. This runs no build code.
        with tempfile.TemporaryDirectory(prefix="strling-pub-approved-") as temporary:
            directory = Path(temporary) / "package"
            shutil.copytree(one("dart"), directory)
            return run(
                ["dart", "pub", "publish", "--force", "--skip-validation"],
                cwd=directory,
            )
    if slug == "python":
        raise ReleaseSupplyChainError(
            "publication-route",
            "Python uploads must use the pinned PyPI trusted-publishing action after handoff verification",
        )
    raise ReleaseSupplyChainError("publication-route", "no approved upload adapter")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--trust-root", type=Path, required=True)
    parser.add_argument("--certification-bundle", type=Path)
    parser.add_argument("--certification-root", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--download-root", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--record-external-upload", action="store_true")
    args = parser.parse_args()
    args.execute = args.execute or args.record_external_upload
    root = args.source_root.resolve()
    upload_started = False
    try:
        manifest = load_json(root / MANIFEST_PATH.relative_to(ROOT))
        artifact = next(
            item for item in manifest["artifacts"] if item["id"] == args.artifact_id
        )
        version = load_json(root / "governance/release-policy.json")["product"][
            "version"
        ]
        approval = None
        if args.execute:
            if not all(
                (
                    args.certification_bundle,
                    args.evidence,
                    args.authorization,
                    args.receipt,
                )
            ):
                raise ReleaseSupplyChainError(
                    "publication-authorization",
                    "execution requires the complete approved handoff and receipt path",
                )
            if args.receipt.exists():
                raise ReleaseSupplyChainError(
                    "publication-receipt", "receipt path already exists"
                )
            approval = verify_publication_handoff(
                root=root,
                trust_root=args.trust_root.resolve(),
                certification_bundle=args.certification_bundle.resolve(),
                evidence_path=args.evidence.resolve(),
                authorization_path=args.authorization.resolve(),
                artifact_id=args.artifact_id,
                certification_root=args.certification_root.resolve()
                if args.certification_root
                else None,
                download_root=args.download_root.resolve()
                if args.download_root
                else None,
            )
        members = _surface_members(root, artifact, version)
        result = publication_plan(artifact, version, members)
        if args.execute:
            authorization = load_json(args.authorization)
            if (
                hashlib.sha256(canonical_json(authorization)).hexdigest()
                != approval["authorization_sha256"]
            ):
                raise ReleaseSupplyChainError(
                    "publication-authorization",
                    "owner authorization changed after verification",
                )
            # Persist an authenticated attempt before the first registry call.
            # A partial multi-file upload must never disappear or appear complete.
            result = {
                **result,
                "publication_authorized": True,
                "authorization_sha256": approval["authorization_sha256"],
                "source_sha": authorization["source_sha"],
                "public_installation_verified": False,
                "status": "upload-started-unverified",
            }
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            with args.receipt.open("xb") as retained:
                retained.write(canonical_json(result) + b"\n")
                retained.flush()
                os.fsync(retained.fileno())
            upload_started = True
            if args.record_external_upload:
                if artifact["id"] != "release:python":
                    raise ReleaseSupplyChainError(
                        "publication-route",
                        "external upload receipts are restricted to the pinned PyPI action",
                    )
                response = python_registry_receipt(version, members)
            else:
                response = upload(
                    root,
                    artifact,
                    version,
                    authorization["source_sha"],
                    members,
                    authorization=authorization,
                    verified_evidence=args.evidence,
                )
            result = {
                **result,
                "publication_authorized": True,
                "authorization_sha256": approval["authorization_sha256"],
                "registry_response_sha256": hashlib.sha256(response).hexdigest(),
                "status": "uploaded-unverified",
                "source_sha": authorization["source_sha"],
                "public_installation_verified": False,
                "verification_handoff": {
                    "consumer_command": "python -m tooling.release_consumers --artifact-id "
                    + artifact["id"],
                    "supported_scopes": artifact["distribution_contract"]["platforms"],
                    "evidence_fingerprint": authorization["evidence_fingerprint"],
                },
            }
            if artifact["id"] in {
                "release:java",
                "release:kotlin",
                "release:cpp",
                "release:python",
                "release:lua",
            }:
                result["registry_receipt"] = json.loads(response)
            staged_receipt = args.receipt.with_name("." + args.receipt.name + ".tmp")
            staged_receipt.write_bytes(canonical_json(result) + b"\n")
            os.replace(staged_receipt, args.receipt)
        else:
            result["status"] = "plan-only"
    except (
        ReleaseSupplyChainError,
        OSError,
        StopIteration,
        ValueError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        # Do not echo subprocess commands, HTTP request headers, or credential values.
        if upload_started:
            retained_result = {
                **result,
                "status": "upload-failed-or-indeterminate",
                "error_type": type(error).__name__,
            }
            staged_receipt = args.receipt.with_name("." + args.receipt.name + ".tmp")
            staged_receipt.write_bytes(canonical_json(retained_result) + b"\n")
            os.replace(staged_receipt, args.receipt)
        result = {
            "status": "failed",
            "publication_authorized": False,
            "error": str(error)
            if isinstance(error, ReleaseSupplyChainError)
            else type(error).__name__,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"plan-only", "uploaded-unverified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
