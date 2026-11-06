"""Offline policy tests; fixture approval never grants real publication authority."""

import hashlib

import pytest

from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ReleaseSupplyChainError,
    canonical_json,
    document_fingerprint,
    load_json,
    verify_publication_authorization,
    restore_artifact_upload,
)


@pytest.fixture
def approval():
    manifest = load_json(MANIFEST_PATH)
    artifact = next(a for a in manifest["artifacts"] if a["id"] == "release:python")
    artifact["distribution_contract"]["ownership_status"] = "verified"
    context = dict(
        event_name="workflow_dispatch",
        repository="strling-lang/strling",
        ref="refs/heads/main",
        environment="release",
        workflow_sha="a" * 40,
        reviewed_workflow_sha="a" * 40,
        run_id="123",
        run_attempt="1",
        dry_run="false",
        artifact_run_id="122",
        certification_ref="f" * 40,
    )
    evidence = dict(
        profile="release",
        evidence_authority="live-dry-run",
        status="passed",
        source={"commit": "b" * 40},
        evidence_fingerprint="c" * 64,
        artifacts=[
            dict(id="release:python", status="passed", subject={"sha256": "d" * 64})
        ],
    )
    auth = {
        k: context[k]
        for k in ("repository", "workflow_sha", "run_id", "run_attempt", "environment")
    }
    auth.update(
        document_kind="release-publication-authorization",
        artifact_run_id=context["artifact_run_id"],
        certification_ref=context["certification_ref"],
        version="4.0.0",
        channel="stable",
        source_sha="b" * 40,
        certification_evidence_root="e" * 64,
        evidence_fingerprint="c" * 64,
        manifest_fingerprint=document_fingerprint(manifest),
        destinations=[
            dict(
                artifact_id=artifact["id"],
                registry=artifact["registry"],
                package_name=artifact["package_name"],
                tier="Supported",
                registry_owner=artifact["distribution_contract"]["registry_owner"],
                subject_sha256="d" * 64,
            )
        ],
    )
    return dict(
        authorization=auth,
        expected_sha256=hashlib.sha256(canonical_json(auth)).hexdigest(),
        evidence=evidence,
        manifest=manifest,
        context=context,
        certified_source_sha="b" * 40,
        certified_evidence_root="e" * 64,
    )


def test_exact_protected_approval_passes_policy_only(approval):
    assert verify_publication_authorization(**approval)["status"] == "passed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_name", "pull_request"),
        ("event_name", "workflow_run"),
        ("repository", "attacker/strling"),
        ("ref", "refs/heads/dev"),
        ("environment", ""),
        ("dry_run", "true"),
        ("reviewed_workflow_sha", ""),
        ("workflow_sha", "f" * 40),
        ("run_id", "124"),
        ("run_attempt", "2"),
        ("artifact_run_id", "999"),
        ("certification_ref", "a" * 40),
    ],
)
def test_untrusted_or_unapproved_context_fails(approval, field, value):
    approval["context"][field] = value
    with pytest.raises(ReleaseSupplyChainError):
        verify_publication_authorization(**approval)


def test_missing_owner_approval_fails(approval):
    approval["expected_sha256"] = ""
    with pytest.raises(ReleaseSupplyChainError, match="authorization"):
        verify_publication_authorization(**approval)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "3.0.0"),
        ("source_sha", "f" * 40),
        ("certification_evidence_root", "f" * 64),
        ("evidence_fingerprint", "f" * 64),
        ("channel", "release-candidate"),
    ],
)
def test_approved_but_inconsistent_release_metadata_fails(approval, field, value):
    approval["authorization"][field] = value
    approval["expected_sha256"] = hashlib.sha256(
        canonical_json(approval["authorization"])
    ).hexdigest()
    with pytest.raises(ReleaseSupplyChainError):
        verify_publication_authorization(**approval)


@pytest.mark.parametrize(
    "field,value",
    [
        ("registry", "test.pypi.org"),
        ("package_name", "strling-replacement"),
        ("registry_owner", "personal-account"),
        ("tier", "Preview"),
        ("subject_sha256", "f" * 64),
    ],
)
def test_substituted_destination_or_subject_fails(approval, field, value):
    approval["authorization"]["destinations"][0][field] = value
    approval["expected_sha256"] = hashlib.sha256(
        canonical_json(approval["authorization"])
    ).hexdigest()
    with pytest.raises(ReleaseSupplyChainError):
        verify_publication_authorization(**approval)


def test_duplicate_coordinate_fails(approval):
    approval["authorization"]["destinations"] *= 2
    approval["expected_sha256"] = hashlib.sha256(
        canonical_json(approval["authorization"])
    ).hexdigest()
    with pytest.raises(ReleaseSupplyChainError, match="duplicate"):
        verify_publication_authorization(**approval)


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "full"),
        ("evidence_authority", "synthetic-contract"),
        ("status", "incomplete"),
    ],
)
def test_nonrelease_or_incomplete_evidence_fails(approval, field, value):
    approval["evidence"][field] = value
    with pytest.raises(ReleaseSupplyChainError):
        verify_publication_authorization(**approval)


def test_unverified_external_ownership_fails(approval):
    next(a for a in approval["manifest"]["artifacts"] if a["id"] == "release:python")[
        "distribution_contract"
    ]["ownership_status"] = "externally-pending"
    approval["authorization"]["manifest_fingerprint"] = document_fingerprint(
        approval["manifest"]
    )
    approval["expected_sha256"] = hashlib.sha256(
        canonical_json(approval["authorization"])
    ).hexdigest()
    with pytest.raises(ReleaseSupplyChainError):
        verify_publication_authorization(**approval)


@pytest.mark.parametrize(
    "name", ["../outside", "/outside", "C:\\outside", "bindings/../../outside"]
)
def test_download_receipt_cannot_escape_staging(tmp_path, name):
    with pytest.raises(ReleaseSupplyChainError, match="unsafe"):
        restore_artifact_upload(
            artifact_root=tmp_path / "downloads",
            target_root=tmp_path / "first",
            receipt={
                "subject": {"members": [{"name": name, "sha256": "0" * 64, "bytes": 1}]}
            },
        )
    assert not (tmp_path / "outside").exists()
