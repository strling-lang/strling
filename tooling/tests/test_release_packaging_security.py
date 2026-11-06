"""Credential-free adversarial checks for release assembly and exact-byte upload."""

import io
import json
import struct
import tarfile

import pytest
import yaml

from tooling import publish_certified_artifact as publisher
from tooling.local_certification_attestation import AttestationError, load_trust_policy
from tooling.release_packaging import build_environment, host_scope
from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ROOT,
    ReleaseSupplyChainError,
    load_json,
    qualify_workflow,
)


def test_packaging_environment_drops_credentials_and_shared_build_cache(
    monkeypatch, tmp_path
):
    for name in (
        "NPM_TOKEN",
        "NODE_AUTH_TOKEN",
        "PAUSE_PASSWORD",
        "GITHUB_TOKEN",
        "CARGO_REGISTRY_TOKEN",
        "CARGO_TARGET_DIR",
        "RUSTC",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_BUILD_RUSTC",
        "CARGO_PROFILE_RELEASE_PANIC",
        "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER",
        "CUSTOM_API_KEY",
    ):
        monkeypatch.setenv(name, "fixture-sensitive-value")
    environment = build_environment(tmp_path, "12345", load_json(MANIFEST_PATH))
    assert "fixture-sensitive-value" not in environment.values()
    assert environment["SOURCE_DATE_EPOCH"] == "12345"
    assert environment["CARGO_INCREMENTAL"] == "0"


def test_release_trust_preserves_original_key_and_waiver_authority():
    original = load_trust_policy(ROOT)
    release = load_trust_policy(ROOT, "release-certification-trust.json")
    for field in (
        "authorized_certifiers",
        "allowed_waivers",
        "required_profiles",
        "signature_namespace",
    ):
        assert original[field] == release[field]
    assert original["bundle_path"] != release["bundle_path"]
    assert not any("hardened-core" in path for path in release["closure_paths"])
    with pytest.raises(AttestationError, match="unknown"):
        load_trust_policy(ROOT, "../candidate.json")


@pytest.mark.parametrize(
    "system,machine", [("Darwin", "x86_64"), ("Linux", "aarch64"), ("Windows", "ARM64")]
)
def test_unknown_packaging_platform_is_rejected(monkeypatch, system, machine):
    monkeypatch.setattr("tooling.release_packaging.platform.system", lambda: system)
    monkeypatch.setattr("tooling.release_packaging.platform.machine", lambda: machine)
    with pytest.raises(ReleaseSupplyChainError, match="platform"):
        host_scope()


@pytest.fixture
def workflow(tmp_path):
    document = yaml.safe_load(
        (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    )
    path = tmp_path / ".github/workflows/cd.yml"
    path.parent.mkdir(parents=True)
    return document, path, tmp_path


def _reject_workflow(fixture):
    document, path, root = fixture
    path.write_text(yaml.safe_dump(document, indent=4, sort_keys=False))
    with pytest.raises(ReleaseSupplyChainError):
        qualify_workflow(root, load_json(MANIFEST_PATH))


def test_workflow_rejects_build_credentials(workflow):
    workflow[0]["jobs"]["compile-python"]["env"] = {
        "TOKEN": "${{ secrets.PYPI_TOKEN }}"
    }
    _reject_workflow(workflow)


def test_workflow_rejects_build_oidc_authority(workflow):
    workflow[0]["jobs"]["compile-python"]["permissions"]["id-token"] = "write"
    _reject_workflow(workflow)


def test_attester_requires_read_access_to_the_approved_artifact_run(workflow):
    workflow[0]["jobs"]["attest-release-subjects"]["permissions"].pop("actions")
    _reject_workflow(workflow)


def test_workflow_rejects_persistent_npm_token(workflow):
    workflow[0]["jobs"]["publish-typescript"]["env"]["NODE_AUTH_TOKEN"] = (
        "${{ secrets.NPM_TOKEN }}"
    )
    _reject_workflow(workflow)


def test_workflow_rejects_publication_rebuild(workflow):
    workflow[0]["jobs"]["publish-python"]["steps"].append({"run": "dotnet pack"})
    _reject_workflow(workflow)


def test_workflow_rejects_unsafe_dispatch_default(workflow):
    triggers = workflow[0].get("on", workflow[0].get(True))
    triggers["workflow_dispatch"]["inputs"]["dry_run"]["default"] = False
    _reject_workflow(workflow)


def test_current_workflow_has_isolated_exact_handoff():
    assert (
        qualify_workflow(ROOT, load_json(MANIFEST_PATH))["exact_artifact_handoff"]
        is True
    )


def test_workflow_release_outputs_are_separate_github_output_lines(
    tmp_path, monkeypatch
):
    document = yaml.safe_load(
        (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    )
    command = document["jobs"]["verify-release"]["steps"][-1]["run"]
    script = command.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("PUBLICATION_ENABLED", "false")
    monkeypatch.setenv("REQUESTED_DRY_RUN", "")
    monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
    monkeypatch.chdir(ROOT)
    exec(compile(script, "release_state", "exec"), {})
    lines = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert set(lines) == {
        "version",
        "tag_version",
        "release_ref",
        "is_release",
        "is_dry_run",
    }
    assert lines["version"] == "4.0.0" and lines["is_dry_run"] == "true"


def test_workflow_rejects_missing_registered_platform(workflow):
    workflow[0]["jobs"]["compile-python"]["strategy"]["matrix"]["include"].pop()
    _reject_workflow(workflow)


def test_workflow_rejects_hidden_file_omission(workflow):
    for step in workflow[0]["jobs"]["compile-dart"]["steps"]:
        if step.get("with", {}).get("include-hidden-files") is True:
            step["with"]["include-hidden-files"] = False
    _reject_workflow(workflow)


def test_workflow_rejects_companion_rebuild(workflow):
    workflow[0]["jobs"]["compile-fsharp"]["needs"] = ["verify-release"]
    _reject_workflow(workflow)


def test_pypi_receipt_rejects_missing_or_substituted_registry_files(monkeypatch):
    response = {
        "info": {"version": "4.0.0"},
        "urls": [{"filename": "strling-4.0.0.tar.gz", "digests": {"sha256": "a" * 64}}],
    }
    monkeypatch.setattr(publisher, "_http", lambda url: json.dumps(response).encode())
    members = [
        {"name": "bindings/python/dist/strling-4.0.0.tar.gz", "sha256": "a" * 64}
    ]
    assert (
        json.loads(publisher.python_registry_receipt("4.0.0", members))[
            "public_installation_verified"
        ]
        is False
    )
    response["urls"][0]["digests"]["sha256"] = "b" * 64
    with pytest.raises(ReleaseSupplyChainError, match="exact approved"):
        publisher.python_registry_receipt("4.0.0", members)


def test_certified_export_rejects_synthetic_evidence(monkeypatch, tmp_path):
    from tooling import release_supply_chain as supply

    monkeypatch.setattr(
        supply,
        "verify_bundle",
        lambda **kwargs: {
            "profile": "contract",
            "evidence_authority": "synthetic-contract",
            "status": "passed",
        },
    )
    with pytest.raises(ReleaseSupplyChainError, match="exact-source Release"):
        supply.prepare_certified_upload(
            root=tmp_path,
            evidence_path=tmp_path / "evidence.json",
            output=tmp_path / "export",
            artifact_id="release:python",
            manifest=load_json(MANIFEST_PATH),
        )


def test_workflow_rejects_candidate_publisher_checkout(workflow):
    for step in workflow[0]["jobs"]["publish-rust"]["steps"]:
        if step.get("with", {}).get("path") == ".cert/publisher":
            step["with"]["ref"] = "${{ github.sha }}"
    _reject_workflow(workflow)


def _crate(tmp_path, extra=""):
    path = tmp_path / "strling-4.0.0.crate"
    manifest = (
        '[package]\nname="strling"\nversion="4.0.0"\nreadme="README.md"\n'
        'license="Apache-2.0"\n[dependencies]\n' + extra
    ).encode()
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in (
            ("Cargo.toml", manifest),
            ("README.md", b"fixture README"),
        ):
            entry = tarfile.TarInfo("strling-4.0.0/" + name)
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
    return path


def test_crates_upload_frame_contains_exact_certified_crate_bytes(tmp_path):
    crate = _crate(tmp_path, 'serde="1.0"\n')
    frame = publisher._crate_frame(crate, "4.0.0")
    metadata_size = struct.unpack("<I", frame[:4])[0]
    metadata = json.loads(frame[4 : 4 + metadata_size])
    assert metadata["name"] == "strling" and metadata["vers"] == "4.0.0"
    assert (
        struct.unpack("<I", frame[4 + metadata_size : 8 + metadata_size])[0]
        == crate.stat().st_size
    )
    assert frame[8 + metadata_size :] == crate.read_bytes()


def test_crates_frame_rejects_unpublished_dependency(tmp_path):
    crate = _crate(tmp_path, 'local={version="1.0",path="/developer/workspace"}\n')
    with pytest.raises(ReleaseSupplyChainError, match="unpublished"):
        publisher._crate_frame(crate, "4.0.0")


def test_crates_frame_rejects_wrong_coordinate(tmp_path):
    crate = _crate(tmp_path)
    with pytest.raises((ReleaseSupplyChainError, KeyError)):
        publisher._crate_frame(crate, "3.0.0")


@pytest.mark.parametrize(
    "tool,banner",
    [
        ("node", "v18.20.8"),
        ("python", "Python 3.13.1"),
        ("conan", "Conan version 2.31.1"),
        ("maven", "Apache Maven 3.6.3"),
        ("cargo", "cargo 1.80.0"),
        ("gradle", "Gradle 9.0"),
    ],
)
def test_release_toolchain_rejects_wrong_and_transitional_versions(tool, banner):
    from tooling.release_supply_chain import _validate_toolchain_version

    with pytest.raises(ValueError):
        _validate_toolchain_version(ROOT, tool, banner)


@pytest.mark.parametrize(
    "tool,banner",
    [
        ("node", "v22.23.2"),
        ("python", "Python 3.12.3"),
        ("conan", "Conan version 2.31.2"),
        ("maven", "Apache Maven 3.8.7"),
        ("cargo", "cargo 1.75.0"),
        ("gradle", "Gradle 8.5"),
    ],
)
def test_release_toolchain_accepts_governed_versions(tool, banner):
    from tooling.release_supply_chain import _validate_toolchain_version

    _validate_toolchain_version(ROOT, tool, banner)


def test_nuget_public_payload_rejects_content_substitution_before_signature_verification(
    monkeypatch,
):
    import zipfile

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("lib/net9.0/STRling.dll", b"changed library")
        archive.writestr(".signature.p7s", b"signature fixture")
    sbom = {
        "files": [
            {
                "fileName": "STRling.nupkg!/lib/net9.0/STRling.dll",
                "checksums": [{"algorithm": "SHA256", "checksumValue": "a" * 64}],
            }
        ]
    }
    monkeypatch.setattr(
        publisher,
        "_http",
        lambda *args, **kwargs: pytest.fail(
            "substituted package must not reach signature lookup"
        ),
    )
    with pytest.raises(ReleaseSupplyChainError, match="content differs"):
        publisher.verify_nuget_registry_payload(payload.getvalue(), sbom)


def test_nuget_public_payload_requires_repository_signature(monkeypatch):
    import zipfile
    import hashlib

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("lib/net9.0/STRling.dll", b"exact library")
    sbom = {
        "files": [
            {
                "fileName": "STRling.nupkg!/lib/net9.0/STRling.dll",
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": hashlib.sha256(b"exact library").hexdigest(),
                    }
                ],
            }
        ]
    }
    with pytest.raises(ReleaseSupplyChainError, match="content differs"):
        publisher.verify_nuget_registry_payload(payload.getvalue(), sbom)


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.example/upload",
        "https://" + "user:password@" + "registry.example/upload",
        "file:///local/payload",
    ],
)
def test_registry_transport_rejects_plaintext_and_url_credentials(url):
    with pytest.raises(ReleaseSupplyChainError, match="HTTPS"):
        publisher._http(url)


def test_luarocks_transport_uploads_exact_files_without_executing_sdk(
    monkeypatch, tmp_path
):
    artifact = next(
        a for a in load_json(MANIFEST_PATH)["artifacts"] if a["id"] == "release:lua"
    )
    spec, rock = (
        tmp_path / "strling-4.0.0-1.rockspec",
        tmp_path / "strling-4.0.0-1.src.rock",
    )
    spec.write_bytes(b"exact certified rockspec bytes")
    rock.write_bytes(b"exact certified source-rock bytes")
    monkeypatch.setenv("LUAROCKS_API_KEY", "fixture-only-token")
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail(
            "publication must not evaluate rockspec or run a builder"
        ),
    )
    requests = []

    def http(url, **kwargs):
        requests.append((url, kwargs))
        assert kwargs["headers"]["Authorization"] == "Bearer fixture-only-token"
        if url.endswith("/status"):
            return b'{"user_id":42}'
        if "/check_rockspec?" in url:
            return b'{"module":null,"version":null}'
        assert kwargs["method"] == "POST"
        if url.endswith("/upload"):
            assert spec.read_bytes() in kwargs["data"]
            return b'{"module_url":"https://luarocks.org/modules/approved/strling","version":{"id":10,"version_name":"4.0.0-1"}}'
        assert url.endswith("/upload_rock/10") and rock.read_bytes() in kwargs["data"]
        return b'{"module_url":"https://luarocks.org/modules/approved/strling","rock":{"arch":"src"}}'

    monkeypatch.setattr(publisher, "_http", http)
    result = publisher.upload(
        tmp_path,
        artifact,
        "4.0.0",
        "a" * 40,
        [{"name": spec.name}, {"name": rock.name}],
        authorization={
            "destinations": [
                {
                    "artifact_id": "release:lua",
                    "registry_owner": "approved",
                    "registry_user_id": 42,
                }
            ]
        },
    )
    assert len(requests) == 4 and b"fixture-only-token" not in result


def test_luarocks_transport_rejects_wrong_credential_owner_before_upload(
    monkeypatch, tmp_path
):
    artifact = next(
        a for a in load_json(MANIFEST_PATH)["artifacts"] if a["id"] == "release:lua"
    )
    monkeypatch.setenv("LUAROCKS_API_KEY", "fixture-only-token")
    monkeypatch.setattr(publisher, "_http", lambda url, **kwargs: b'{"user_id":41}')
    with pytest.raises(ReleaseSupplyChainError, match="different approved uploader"):
        publisher.upload(
            tmp_path,
            artifact,
            "4.0.0",
            "a" * 40,
            [],
            authorization={
                "destinations": [
                    {
                        "artifact_id": "release:lua",
                        "registry_owner": "approved",
                        "registry_user_id": 42,
                    }
                ]
            },
        )


def test_pause_transport_rejects_wrong_uploader_before_network(monkeypatch, tmp_path):
    artifact = next(
        a for a in load_json(MANIFEST_PATH)["artifacts"] if a["id"] == "release:perl"
    )
    monkeypatch.setenv("PAUSE_USERNAME", "OTHER")
    monkeypatch.setattr(
        publisher,
        "_http",
        lambda *args, **kwargs: pytest.fail("wrong owner must fail before network"),
    )
    with pytest.raises(ReleaseSupplyChainError, match="approved uploader"):
        publisher.upload(
            tmp_path,
            artifact,
            "4.0.0",
            "a" * 40,
            [],
            authorization={
                "destinations": [
                    {"artifact_id": "release:perl", "registry_owner": "APPROVED"}
                ]
            },
        )


def test_failed_upload_retains_authenticated_attempt_without_false_completion(
    monkeypatch, tmp_path, capsys
):
    import hashlib
    import sys

    manifest = load_json(MANIFEST_PATH)
    authorization = {"source_sha": "a" * 40}
    approval = {
        "authorization_sha256": hashlib.sha256(
            publisher.canonical_json(authorization)
        ).hexdigest()
    }
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publisher",
            "--execute",
            "--artifact-id",
            "release:cpp",
            "--source-root",
            str(tmp_path),
            "--trust-root",
            str(tmp_path),
            "--certification-bundle",
            str(tmp_path),
            "--evidence",
            str(tmp_path / "evidence.json"),
            "--authorization",
            str(tmp_path / "authorization.json"),
            "--receipt",
            str(receipt),
        ],
    )
    monkeypatch.setattr(
        publisher,
        "load_json",
        lambda path: (
            authorization
            if path.name == "authorization.json"
            else {"product": {"version": "4.0.0"}}
            if path.name == "release-policy.json"
            else manifest
        ),
    )
    monkeypatch.setattr(
        publisher, "verify_publication_handoff", lambda **kwargs: approval
    )
    monkeypatch.setattr(
        publisher,
        "_surface_members",
        lambda *args: [{"name": "exact.tgz", "sha256": "b" * 64, "bytes": 12}],
    )

    def fail_after_partial_upload(*args, **kwargs):
        assert json.loads(receipt.read_text())["status"] == "upload-started-unverified"
        raise RuntimeError("fixture-sensitive-value")

    monkeypatch.setattr(publisher, "upload", fail_after_partial_upload)
    assert publisher.main() == 1
    retained = json.loads(receipt.read_text())
    assert retained["publication_authorized"] is True
    assert retained["status"] == "upload-failed-or-indeterminate"
    assert retained["public_installation_verified"] is False
    assert (
        "fixture-sensitive-value" not in receipt.read_text() + capsys.readouterr().out
    )
