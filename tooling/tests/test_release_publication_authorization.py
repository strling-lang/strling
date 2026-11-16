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
    "endpoint", ["https://center2.conan.io", "https://private.example.test"]
)
def test_cpp_cannot_authorize_direct_upload_even_with_an_approved_digest(
    approval, endpoint
):
    manifest = approval["manifest"]
    cpp = next(item for item in manifest["artifacts"] if item["id"] == "release:cpp")
    cpp["distribution_contract"].update(
        ownership_status="verified", registry_owner="fixture-owner"
    )
    auth = approval["authorization"]
    auth["destinations"][0].update(
        artifact_id=cpp["id"],
        registry=cpp["registry"],
        package_name=cpp["package_name"],
        registry_owner="fixture-owner",
        registry_endpoint=endpoint,
    )
    approval["evidence"]["artifacts"][0]["id"] = cpp["id"]
    auth["manifest_fingerprint"] = document_fingerprint(manifest)
    approval["expected_sha256"] = document_fingerprint(auth)
    with pytest.raises(ReleaseSupplyChainError, match="Conan Center Index"):
        verify_publication_authorization(**approval)


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


@pytest.mark.parametrize("operation", ["handoff", "attestation-subjects"])
@pytest.mark.parametrize("separate_closure", [False, True])
def test_package_certificate_verifies_implementation_not_candidate_closure(
    tmp_path, monkeypatch, operation, separate_closure
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tooling import release_supply_chain as supply

    source = tmp_path / "implementation"
    closure = tmp_path / "candidate-closure" if separate_closure else source
    trust = tmp_path / "immutable-verifier"
    bundle = tmp_path / "original-package"
    output = tmp_path / "subjects.sha256"
    monkeypatch.setattr(supply, "verify_bundle", lambda **kwargs: {})
    monkeypatch.setattr(
        supply,
        "load_json",
        lambda path: (
            {"product": {"version": "4.0.0"}}
            if path.name == "release-policy.json"
            else {"version": "4.0.0"}
        ),
    )
    runner = Mock(
        return_value=SimpleNamespace(returncode=1, stdout="", stderr="bad signature")
    )
    monkeypatch.setattr(supply.subprocess, "run", runner)
    with pytest.raises(
        ReleaseSupplyChainError, match="signed Release verification failed"
    ):
        if operation == "handoff":
            supply.verify_publication_handoff(
                root=source,
                trust_root=trust,
                certification_root=closure,
                certification_bundle=bundle,
                evidence_path=bundle / "evidence.json",
                authorization_path=tmp_path / "authorization.json",
                artifact_id="release:c",
            )
        else:
            supply.certified_subject_checksums(
                root=source,
                trust_root=trust,
                certification_root=closure,
                certification_bundle=bundle,
                evidence_path=bundle / "evidence.json",
                output=output,
            )
    command = runner.call_args.args[0]
    assert command[command.index("--repository-root") + 1] == str(source)
    assert command[command.index("--trust-root") + 1] == str(trust)
    assert (
        command[command.index("--trust-policy") + 1]
        == "release-certification-trust.json"
    )
    assert command[command.index("--bundle") + 1] == str(bundle)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing-ref",
        "wrong-ref",
        "wrong-version",
        "dispatch",
        "unapproved-attempt",
    ],
)
def test_separate_publication_control_tag_is_explicit_and_run_bound(approval, mutation):
    auth = approval["authorization"]
    auth["publication_ref"] = "refs/tags/publication-v4.0.0"
    approval["context"].update(event_name="push", ref=auth["publication_ref"])
    if mutation == "missing-ref":
        auth.pop("publication_ref")
    elif mutation == "wrong-ref":
        auth["publication_ref"] = "refs/tags/other-v4.0.0"
        approval["context"]["ref"] = auth["publication_ref"]
    elif mutation == "wrong-version":
        auth["publication_ref"] = "refs/tags/publication-v4.0.1"
        approval["context"]["ref"] = auth["publication_ref"]
    elif mutation == "dispatch":
        approval["context"].update(
            event_name="workflow_dispatch", ref="refs/heads/main"
        )
    elif mutation == "unapproved-attempt":
        approval["context"]["run_attempt"] = "2"
    approval["expected_sha256"] = hashlib.sha256(canonical_json(auth)).hexdigest()
    if mutation:
        with pytest.raises(ReleaseSupplyChainError):
            verify_publication_authorization(**approval)
    else:
        assert verify_publication_authorization(**approval)["status"] == "passed"


@pytest.mark.parametrize("tagged_source", ["b" * 40, "c" * 40, None])
def test_control_tag_preserves_original_official_product_tag(
    tmp_path, monkeypatch, tagged_source
):
    from unittest.mock import Mock
    from tooling import release_supply_chain as supply

    auth = {
        "publication_ref": "refs/tags/publication-v4.0.0",
        "version": "4.0.0",
        "source_sha": "b" * 40,
    }
    runner = Mock(return_value=((tagged_source or "") + "\n").encode())
    if tagged_source is None:
        runner.side_effect = ReleaseSupplyChainError(
            "source-git", "missing version tag"
        )
    monkeypatch.setattr(supply, "_git_output", runner)
    if tagged_source == auth["source_sha"]:
        supply._verify_publication_source_tag(tmp_path, auth)
    else:
        with pytest.raises(ReleaseSupplyChainError):
            supply._verify_publication_source_tag(tmp_path, auth)
    assert runner.call_args.args == (
        tmp_path,
        ["rev-parse", "--verify", "refs/tags/v4.0.0^{commit}"],
    )
