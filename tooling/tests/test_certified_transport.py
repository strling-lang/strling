"""Synthetic transport fixtures never represent accepted release certification."""

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from tooling import certified_transport as transport


SOURCE = "a" * 40
ROOT_HASH = "b" * 64
PACKAGE = "signed-release-" + SOURCE + "/attestation.json"
SUBJECT = "certified-rust-" + SOURCE + "/fixture.crate"


def capsule_fixture(tmp_path, monkeypatch):
    files = {PACKAGE: b"synthetic certificate", SUBJECT: b"exact fixture bytes"}
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    authentication = Mock(return_value=({}, expected))
    monkeypatch.setattr(transport, "authenticate", authentication)
    capsule = tmp_path / "capsule.zip"
    write_capsule(capsule, files)
    return capsule, files, authentication


def write_capsule(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def restore(capsule, output, **extra):
    return transport.restore(
        capsule=capsule,
        capsule_sha256=transport.digest(capsule),
        source_root=output.parent / "source",
        trust=output.parent / "trusted",
        source=SOURCE,
        evidence_root=ROOT_HASH,
        closure=output.parent / "closure",
        output=output,
        **extra,
    )


def test_exact_transport_restores_without_building_or_publishing(tmp_path, monkeypatch):
    capsule, files, authentication = capsule_fixture(tmp_path, monkeypatch)
    output = tmp_path / "out"
    result = restore(capsule, output)
    assert result["status"] == "passed-certified-byte-restoration"
    assert result["rebuilt"] is result["publication_authorized"] is False
    assert result["registry_requests"] == 0
    assert transport.inventory(output) == {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }
    authentication.assert_called_once()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "changed",
        "wrong-source-name",
        "traversal",
        "windows-path",
        "symlink",
        "duplicate",
        "digest",
    ],
)
def test_corrupt_transport_never_produces_accepted_exports(
    tmp_path, monkeypatch, mutation
):
    capsule, files, authentication = capsule_fixture(tmp_path, monkeypatch)
    if mutation == "missing":
        files.pop(SUBJECT)
    elif mutation == "extra":
        files["unexpected.txt"] = b"extra"
    elif mutation == "changed":
        files[SUBJECT] = b"substituted"
    elif mutation == "wrong-source-name":
        files[SUBJECT.replace(SOURCE, "c" * 40)] = files.pop(SUBJECT)
    elif mutation in {"traversal", "windows-path"}:
        files["../escape" if mutation == "traversal" else "C:\\escape"] = b"bad"
    write_capsule(capsule, files)
    if mutation in {"symlink", "duplicate"}:
        with zipfile.ZipFile(capsule, "a") as archive:
            entry = zipfile.ZipInfo("link" if mutation == "symlink" else SUBJECT)
            entry.external_attr = (
                0o120777 if mutation == "symlink" else 0o100644
            ) << 16
            archive.writestr(entry, b"alias")
    if mutation == "digest":
        monkeypatch.setattr(transport, "digest", lambda _: "c" * 64)
        with pytest.raises(ValueError, match="protected digest"):
            transport.restore(
                capsule=capsule,
                capsule_sha256="d" * 64,
                source_root=tmp_path / "source",
                trust=tmp_path / "trusted",
                source=SOURCE,
                evidence_root=ROOT_HASH,
                closure=tmp_path / "closure",
                output=tmp_path / "out",
            )
        authentication.assert_not_called()
    else:
        with pytest.raises(ValueError):
            restore(capsule, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not (tmp_path.parent / "escape").exists()


def test_signature_failure_cannot_restore_exports(tmp_path, monkeypatch):
    capsule, _, authentication = capsule_fixture(tmp_path, monkeypatch)
    authentication.side_effect = ValueError("invalid original-authority signature")
    with pytest.raises(ValueError, match="signature"):
        restore(capsule, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_seal_is_lossless_and_rejects_unregistered_export(tmp_path, monkeypatch):
    _, files, authentication = capsule_fixture(tmp_path, monkeypatch)
    exports, bundle = tmp_path / "exports", tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "attestation.json").write_bytes(files[PACKAGE])
    path = exports / SUBJECT
    path.parent.mkdir(parents=True)
    path.write_bytes(files[SUBJECT])
    output = tmp_path / "sealed.zip"
    result = transport.seal(
        source_root=tmp_path / "source",
        trust=tmp_path / "trusted",
        bundle=bundle,
        exports=exports,
        source=SOURCE,
        evidence_root=ROOT_HASH,
        closure=tmp_path / "closure",
        output=output,
    )
    assert transport.archive_files(output) == files
    assert result["publication_authorized"] is False
    (exports / "unregistered").write_bytes(b"extra")
    with pytest.raises(ValueError, match="complete signed"):
        transport.seal(
            source_root=tmp_path / "source",
            trust=tmp_path / "trusted",
            bundle=bundle,
            exports=exports,
            source=SOURCE,
            evidence_root=ROOT_HASH,
            closure=tmp_path / "closure",
            output=tmp_path / "bad.zip",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "public",
        "published-date",
        "source",
        "release-id",
        "missing-asset",
        "digest",
        "name",
        "oversized",
    ],
)
def test_private_staging_metadata_cannot_redirect_to_public_or_substituted_assets(
    tmp_path, monkeypatch, mutation
):
    metadata = dict(
        id=12,
        draft=True,
        published_at=None,
        target_commitish=SOURCE,
        assets=[
            dict(
                id=34,
                name="strling-certified-" + SOURCE + ".zip",
                state="uploaded",
                size=10,
                digest="sha256:" + ROOT_HASH,
            )
        ],
    )
    if mutation == "public":
        metadata["draft"] = False
    elif mutation == "published-date":
        metadata["published_at"] = "2026-11-14T00:00:00Z"
    elif mutation == "source":
        metadata["target_commitish"] = "main"
    elif mutation == "release-id":
        metadata["id"] = 13
    elif mutation == "missing-asset":
        metadata["assets"] = []
    elif mutation == "digest":
        metadata["assets"][0]["digest"] = "sha256:" + "d" * 64
    elif mutation == "name":
        metadata["assets"][0]["name"] = "replacement.zip"
    else:
        metadata["assets"][0]["size"] = transport.MAX_TOTAL + 1
    reader = Mock(return_value=json.dumps(metadata).encode())
    download = Mock()
    monkeypatch.setattr(transport.subprocess, "check_output", reader)
    monkeypatch.setattr(transport.subprocess, "run", download)
    monkeypatch.setenv("NPM_TOKEN", "must-not-inherit")
    with pytest.raises(ValueError):
        transport.fetch_draft(
            release_id="12",
            asset_id="34",
            source=SOURCE,
            capsule_sha256=ROOT_HASH,
            output=tmp_path / "capsule",
        )
    assert "NPM_TOKEN" not in reader.call_args.kwargs["env"]
    assert all("POST" not in arg for arg in reader.call_args.args[0])
    download.assert_not_called()


def test_authentication_is_fail_closed_before_certificate_or_subject_use(
    tmp_path, monkeypatch
):
    verifier = Mock()
    monkeypatch.setattr(transport, "verify_attestation", verifier)
    monkeypatch.setattr(transport, "git", lambda root, *args: "c" * 40)
    with pytest.raises(ValueError, match="clean immutable"):
        transport.authenticate(
            tmp_path, tmp_path, tmp_path, SOURCE, ROOT_HASH, tmp_path
        )
    verifier.assert_not_called()


@pytest.mark.parametrize("overflow", [False, True])
def test_private_staging_download_is_bounded_and_read_only(
    tmp_path, monkeypatch, overflow
):
    payload = b"synthetic private capsule"
    checksum = hashlib.sha256(payload).hexdigest()
    metadata = dict(
        id=12,
        draft=True,
        published_at=None,
        target_commitish=SOURCE,
        assets=[
            dict(
                id=34,
                name="strling-certified-" + SOURCE + ".zip",
                state="uploaded",
                size=len(payload),
                digest="sha256:" + checksum,
            )
        ],
    )
    monkeypatch.setattr(
        transport.subprocess,
        "check_output",
        Mock(return_value=json.dumps(metadata).encode()),
    )
    process = Mock(stdout=io.BytesIO(payload + (b"unexpected" if overflow else b"")))
    process.poll.return_value = 0
    process.wait.return_value = 0
    runner = Mock(return_value=process)
    monkeypatch.setattr(transport.subprocess, "Popen", runner)
    output = tmp_path / "capsule"
    if overflow:
        with pytest.raises(ValueError, match="exceeds approved size"):
            transport.fetch_draft(
                release_id="12",
                asset_id="34",
                source=SOURCE,
                capsule_sha256=checksum,
                output=output,
            )
    else:
        transport.fetch_draft(
            release_id="12",
            asset_id="34",
            source=SOURCE,
            capsule_sha256=checksum,
            output=output,
        )
        assert output.read_bytes() == payload
    assert runner.call_args.args[0][-1] == "Accept: application/octet-stream"
    assert not any(
        arg in {"POST", "PUT", "DELETE", "PATCH"} for arg in runner.call_args.args[0]
    )


def test_hosted_export_is_exact_source_protected_and_cannot_publish():
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.load(
        (root / ".github/workflows/certification-integrity.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["export-certified-bytes"]
    assert set(job["needs"]) == {
        "verify-release-candidate-certification",
        "verify-public-distribution-certification",
        "verify-release-packaging-certification",
        "verify-local-certification",
    }
    assert job["permissions"] == {"contents": "read"}
    assert job["environment"] == "release-attestation"
    for condition in (
        "workflow_dispatch",
        "RELEASE_EXPORT_ENABLED",
        "github.sha == vars.RELEASE_EXPORT_CLOSURE_SHA",
        "github.workflow_sha == vars.RELEASE_EXPORT_WORKFLOW_SHA",
    ):
        assert condition in job["if"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert (
        "certified_transport.py fetch" in commands
        and "certified_transport.py restore" in commands
    )
    for forbidden in (
        "cargo ",
        "npm ",
        "mvn ",
        "publish_certified_artifact",
        "secrets.",
        "id-token",
    ):
        assert forbidden not in json.dumps(job)
    artifacts = json.loads(
        (
            root / "tests/certification/release-supply-chain/1.0/manifest.json"
        ).read_text()
    )["artifacts"]
    retained = {
        step["with"]["name"]
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    }
    expected = {
        "certified-"
        + a["id"].removeprefix("release:")
        + "-${{ vars.RELEASE_EXPORT_SOURCE_SHA }}"
        for a in artifacts
    }
    assert retained == expected | {
        "signed-release-${{ vars.RELEASE_EXPORT_SOURCE_SHA }}",
        "certified-export-verification-${{ github.run_id }}",
    }
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "CLOSURE_SHA",
        "REVIEWED_WORKFLOW_SHA",
        "CAPSULE_SHA256",
        "STAGING_ASSET_ID",
    ],
)
def test_hosted_identity_guard_executes_against_actual_event_and_workflow(
    monkeypatch, mutation
):
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.load(
        (root / ".github/workflows/certification-integrity.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    script = (
        workflow["jobs"]["export-certified-bytes"]["steps"][0]["run"]
        .split("<<'PY'\n", 1)[1]
        .rsplit("\nPY", 1)[0]
    )
    values = dict(
        SOURCE_SHA=SOURCE,
        CLOSURE_SHA="c" * 40,
        REVIEWED_WORKFLOW_SHA="d" * 40,
        PACKAGE_ROOT=ROOT_HASH,
        CAPSULE_SHA256="e" * 64,
        STAGING_RELEASE_ID="12",
        STAGING_ASSET_ID="34",
        GITHUB_SHA="c" * 40,
        GITHUB_WORKFLOW_SHA="d" * 40,
    )
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    if mutation:
        monkeypatch.setenv(
            mutation,
            "1" if mutation == "STAGING_ASSET_ID" else "f" * len(values[mutation]),
        )
        if mutation == "STAGING_ASSET_ID":
            monkeypatch.setenv(mutation, "12; unsafe")
        elif mutation == "CAPSULE_SHA256":
            monkeypatch.setenv(mutation, "g" * 64)
        with pytest.raises(AssertionError):
            exec(compile(script, "protected-export-identity-guard", "exec"), {})
    else:
        exec(compile(script, "protected-export-identity-guard", "exec"), {})


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "candidate-source",
        "package-source",
        "package-root",
        "nested-certificate",
        "extra-file",
        "wrong-profile",
        "signature",
    ],
)
def test_authentication_binds_both_original_certificates_and_complete_graph(
    tmp_path, monkeypatch, mutation
):
    # The signature primitive is independently qualified; this synthetic bridge
    # fixture checks that neither its identities nor its nested bytes are lost.
    source, trust, closure, bundle = [
        tmp_path / name for name in ("source", "trusted", "closure", "bundle")
    ]
    for path in (source, trust, closure, bundle):
        path.mkdir()
    monkeypatch.setattr(transport, "ROOT", trust)
    monkeypatch.setattr(transport, "MANIFEST_PATH", trust / "manifest.json")
    monkeypatch.setattr(
        transport, "git", lambda root, *args: SOURCE if args[0] == "rev-parse" else ""
    )
    evidence_name = "evidence/release-supply-chain/release-supply-chain-evidence.json"
    evidence = bundle / evidence_name
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"synthetic release metadata")
    payload = {
        "evidence_files": [
            {"path": evidence_name, "sha256": transport.digest(evidence)}
        ]
    }
    certificate = json.dumps({"signed_payload": payload}).encode()
    (bundle / "attestation.json").write_bytes(certificate)
    candidate_bundle = closure / "tests/certification/release-candidate/1.0/current"
    nested = candidate_bundle / "evidence/original-package.json"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(certificate)
    (candidate_bundle / "attestation.json").write_text(
        json.dumps(
            {
                "signed_payload": {
                    "evidence_files": [
                        {
                            "role": "staged-package-attestation",
                            "path": "evidence/original-package.json",
                        }
                    ]
                }
            }
        )
    )
    (source / "manifest.json").write_text("{}")
    candidate_facts = dict(certified_source_sha=SOURCE)
    package_facts = dict(certified_source_sha=SOURCE, evidence_root_sha256=ROOT_HASH)
    supply = dict(
        source={"commit": SOURCE},
        status="passed",
        profile="release",
        evidence_authority="live-dry-run",
    )
    if mutation == "candidate-source":
        candidate_facts["certified_source_sha"] = "c" * 40
    elif mutation == "package-source":
        package_facts["certified_source_sha"] = "c" * 40
    elif mutation == "package-root":
        package_facts["evidence_root_sha256"] = "c" * 64
    elif mutation == "nested-certificate":
        nested.write_bytes(b"different certificate")
    elif mutation == "extra-file":
        (bundle / "unregistered").write_bytes(b"extra")
    elif mutation == "wrong-profile":
        supply["profile"] = "full"
    verifier = (
        Mock(side_effect=ValueError("bad signature"))
        if mutation == "signature"
        else Mock(
            side_effect=lambda **kw: (
                candidate_facts
                if kw["policy_name"] == "release-candidate-certification-trust.json"
                else package_facts
            )
        )
    )
    monkeypatch.setattr(transport, "verify_attestation", verifier)
    monkeypatch.setattr(transport, "verify_bundle", Mock(return_value=supply))
    graph = Mock(return_value={SUBJECT: "d" * 64})
    monkeypatch.setattr(transport, "export_graph", graph)
    if mutation:
        with pytest.raises(ValueError):
            transport.authenticate(source, trust, bundle, SOURCE, ROOT_HASH, closure)
        graph.assert_not_called()
    else:
        facts, expected = transport.authenticate(
            source, trust, bundle, SOURCE, ROOT_HASH, closure
        )
        assert facts == package_facts
        assert expected[SUBJECT] == "d" * 64
        assert [c.kwargs["policy_name"] for c in verifier.call_args_list] == [
            "release-candidate-certification-trust.json",
            "release-certification-trust.json",
        ]
        assert expected[PACKAGE] == hashlib.sha256(certificate).hexdigest()
