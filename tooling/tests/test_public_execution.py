"""Protected public execution cannot promote synthetic or incomplete evidence."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tooling.public_distribution import obligations, strict_json
from tooling.public_retrieval import RetrievalError
from tooling.release_supply_chain import canonical_json, document_fingerprint
from tooling.verify_public_release import aggregate, protected_execution

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "policy",
    [
        "release-certification-trust.json",
        "public-verification-certification-trust.json",
    ],
)
def test_authentication_uses_only_governed_policy_and_rejects_bad_signature(
    tmp_path, monkeypatch, policy
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tooling import public_authentication as authentication

    verifier, implementation, closure = [
        tmp_path / name for name in ("verifier", "source", "closure")
    ]
    identities = {verifier: "a" * 40, implementation: "b" * 40, closure: "c" * 40}
    monkeypatch.setattr(
        authentication,
        "git",
        lambda root, *args: identities[root] if args[0] == "rev-parse" else "",
    )
    runner = Mock(
        return_value=SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"invalid signature"
        )
    )
    monkeypatch.setattr(authentication.subprocess, "run", runner)
    monkeypatch.setenv("PUBLICATION_TOKEN", "fixture")
    with pytest.raises(RetrievalError, match="rejected evidence"):
        authentication.authenticate_release(
            verifier=verifier,
            implementation_source=implementation,
            certification_source=closure,
            bundle=tmp_path / "bundle",
            evidence=tmp_path / "evidence.json",
            expected_source=identities[implementation],
            expected_closure=identities[closure],
            expected_root="d" * 64,
            contract={
                "certification_verifier": identities[verifier],
                "certification_trust": "governance/" + policy,
            },
            output=tmp_path / "result",
        )
    command = runner.call_args.args[0]
    assert command[command.index("--trust-policy") + 1] == policy
    assert command[1] == "-I"
    assert "PUBLICATION_TOKEN" not in runner.call_args.kwargs["env"]
    assert (
        tmp_path / "result/verification.stderr"
    ).read_bytes() == b"invalid signature"


def test_missing_scope_evidence_retains_unverified_incident(tmp_path, monkeypatch):
    from tooling import public_aggregate

    request = tmp_path / "request.json"
    request.write_text("{}")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    output = tmp_path / "incident.json"
    monkeypatch.setattr(
        public_aggregate, "protected_execution", lambda: {"run_id": "1"}
    )
    monkeypatch.setattr(
        public_aggregate,
        "reconcile",
        lambda *args: (_ for _ in ()).throw(FileNotFoundError("missing scope receipt")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "public_aggregate",
            "--request",
            str(request),
            "--manifest",
            str(manifest),
            "--scope-result",
            str(tmp_path / "missing.json"),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(FileNotFoundError):
        public_aggregate.main()
    incident = json.loads(output.read_text())
    assert incident["status"] == "INDETERMINATE"
    assert incident["release_transition"] is None
    assert incident["observed"]["available_scope_results"] == []
    assert incident["publication_authorized"] is False


def fixture_reports():
    manifest = json.loads(
        (
            ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
        ).read_text()
    )
    control = {
        "verifier_sha": "a" * 40,
        "request_sha256": "b" * 64,
        "run_id": "42",
        "run_attempt": "1",
    }
    reports = []
    for scope in ("windows-x86_64", "linux-x86_64"):
        observations = [
            {
                **row,
                "authority": "public",
                "status": "VERIFIED"
                if row["platform"] in (None, scope)
                else "VERIFYING",
                "retrieval_sha256": "c" * 64,
            }
            for row in obligations(manifest)
        ]
        receipts = {}
        for row in observations:
            if row["platform"] != scope:
                continue
            identity = row["artifact_id"]
            receipt = {
                "artifact_id": identity,
                "scope": scope,
                "authority": "public",
                "status": "VERIFIED",
            }
            receipt["receipt_fingerprint"] = hashlib.sha256(
                canonical_json(receipt)
            ).hexdigest()
            receipts[identity] = receipt
            row["consumer_receipt_sha256"] = hashlib.sha256(
                canonical_json(receipt)
            ).hexdigest()
        reports.append(
            {
                "scope": scope,
                "authority": "public",
                "execution": control.copy(),
                "source": "d" * 40,
                "manifest_fingerprint": document_fingerprint(manifest),
                "observations": observations,
                "consumers": list(receipts.values()),
            }
        )
    return manifest, reports, control


def test_complete_public_scope_reconciliation():
    result = aggregate(*fixture_reports())
    assert result["status"] == "VERIFIED"
    assert result["required"] == 256
    assert result["publication_authorized"] is False
    assert result["registry_mutation_authorized"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-scope",
        "duplicate-scope",
        "missing-obligation",
        "duplicate-obligation",
        "synthetic",
        "wrong-run",
        "wrong-source",
        "wrong-manifest",
        "consumer-absent",
        "consumer-changed",
        "consumer-duplicate",
        "consumer-staged",
        "consumer-wrong-scope",
        "consumer-unbound",
    ],
)
def test_scope_mutations_cannot_produce_verified(mutation):
    manifest, reports, control = fixture_reports()
    first = reports[0]
    if mutation == "missing-scope":
        reports.pop()
    elif mutation == "duplicate-scope":
        reports.append(copy.deepcopy(first))
    elif mutation == "missing-obligation":
        first["observations"].pop()
    elif mutation == "duplicate-obligation":
        first["observations"].append(first["observations"][0])
    elif mutation == "synthetic":
        first["authority"] = "synthetic"
    elif mutation == "wrong-run":
        first["execution"]["run_id"] = "41"
    elif mutation == "wrong-source":
        first["source"] = "e" * 40
    elif mutation == "wrong-manifest":
        for report in reports:
            report["manifest_fingerprint"] = "e" * 64
    elif mutation == "consumer-absent":
        first["consumers"].pop(0)
    elif mutation == "consumer-changed":
        first["consumers"][0]["unexpected"] = "tamper"
    elif mutation == "consumer-duplicate":
        first["consumers"].append(first["consumers"][0])
    elif mutation == "consumer-staged":
        first["consumers"][0]["authority"] = "staged"
    elif mutation == "consumer-wrong-scope":
        first["consumers"][0]["scope"] = "linux-x86_64"
    elif mutation == "consumer-unbound":
        next(row for row in first["observations"] if row["platform"] == first["scope"])[
            "consumer_receipt_sha256"
        ] = "e" * 64
    with pytest.raises(RetrievalError):
        aggregate(manifest, reports, control)


@pytest.mark.parametrize("state", ["FAILED", "NOT_PUBLISHED", "INDETERMINATE"])
def test_one_failed_registry_observation_prevents_release_transition(state):
    manifest, reports, control = fixture_reports()
    reports[0]["observations"][0]["status"] = state
    result = aggregate(manifest, reports, control)
    assert result["status"] == state
    assert result["release_transition"] is None


def test_local_or_dispatch_selected_verifier_cannot_execute(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RetrievalError, match="protected"):
        protected_execution()


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_registry_json_is_rejected(constant):
    with pytest.raises(RetrievalError):
        strict_json(('{"value":' + constant + "}").encode())


def test_gradle_user_configuration_is_not_a_dependency_cache(tmp_path):
    from tooling.release_consumers import public_consumer_environment
    from tooling.release_supply_chain import ReleaseSupplyChainError

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "init.gradle").write_text("executeUntrustedCode()")
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(ReleaseSupplyChainError, match="executable user"):
        public_consumer_environment(work, {"STRLING_GRADLE_CACHE": str(cache)})


def test_post_publication_workflow_is_protected_read_only_and_pinned():
    import re

    text = (ROOT / ".github/workflows/public-verification.yml").read_text()
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert not workflow["on"]["workflow_dispatch"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert "secrets." not in text
    assert "id-token" not in text
    assert "publish_certified_artifact" not in text
    assert "inputs." not in text
    for job in workflow["jobs"].values():
        assert job["environment"] == "public-verification"
        assert "default_branch" in job["if"]
        assert job.get("permissions", {"contents": "read"}) in (
            {"contents": "read"},
            {"contents": "read", "actions": "read"},
        )
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
            assert step.get("working-directory") != "candidate"
    verify = workflow["jobs"]["verify"]
    assert set(row["scope"] for row in verify["strategy"]["matrix"]["include"]) == {
        "windows-x86_64",
        "linux-x86_64",
    }
    assert "PUBLIC_VERIFICATION_ENABLED" in verify["steps"][0]["run"]
    assert "python -I verifier/tooling/verify_public_release.py" in text
    assert "python -I verifier/tooling/public_aggregate.py" in text


def test_public_certification_trust_is_separate_from_historical_bundles():
    from tooling.local_certification_attestation import load_trust_policy

    public = load_trust_policy(ROOT, "public-verification-certification-trust.json")
    packaging = load_trust_policy(ROOT, "release-certification-trust.json")
    hardened = load_trust_policy(ROOT, "local-certification-trust.json")
    assert (
        len({public["bundle_path"], packaging["bundle_path"], hardened["bundle_path"]})
        == 3
    )
    assert public["authorized_certifiers"] == packaging["authorized_certifiers"]
    assert public["allowed_waivers"] == ["WVR-SEC-VSCE-LICENSE-001"]
    assert all(
        "hardened-core" not in path and "release-packaging" not in path
        for path in public["closure_paths"]
    )


def test_readme_installation_command_is_checked_in_context():
    from tooling.public_metadata import verify_readme_commands

    artifact = {
        "id": "release:typescript",
        "registry": "npmjs.org",
        "package_name": "@strling-lang/strling",
    }
    good = b"```bash\nnpm install @strling-lang/strling@4.0.0\n```\n"
    assert (
        verify_readme_commands(good, artifact, "4.0.0")["exact_install_commands_found"]
        == 1
    )
    for wrong in (
        b"npm install @strling-lang/strling",
        b"npm install @strling-lang/strling@3.0.0",
        b"npm install @untrusted/strling@4.0.0",
    ):
        with pytest.raises(RetrievalError):
            verify_readme_commands(b"```bash\n" + wrong + b"\n```", artifact, "4.0.0")
