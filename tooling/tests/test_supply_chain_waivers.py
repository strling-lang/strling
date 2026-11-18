"""The SBOM gate reconstructs, rather than trusts, waivers from scan results."""

from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
import json
import shutil
from unittest.mock import patch

import pytest
import yaml

from tooling.release_supply_chain import ROOT, _dependency_resolution, _spdx_document
from tooling.security import load_policy


@pytest.fixture
def risk():
    policy = load_policy()
    roots = {root["id"]: root for root in policy["dependency_roots"]}
    rows = {}
    for waiver in policy["security_waivers"]:
        record = yaml.safe_load(
            (ROOT / f"governance/waivers/{waiver}.yaml").read_bytes()
        )
        for scope in record["security"]["matches"]:
            check_id = scope["check_id"]
            _, kind, root_id = check_id.split(".")
            root = roots[root_id]
            fields = {
                "packages": "package",
                "versions": "version",
                "advisories": "advisory",
                "severities": "severity",
                "licenses": "license",
                "paths": "path",
            }
            scope_fields = [key for key in fields if key in scope]
            row = rows.setdefault(
                check_id,
                {
                    "check_id": check_id,
                    "category": kind,
                    "ecosystem": root["ecosystem"],
                    "status": "waived",
                    "inputs": sorted(root["locks"] + root["manifests"]),
                    "findings": [],
                    "scanner": {
                        "name": "npm audit",
                        "source": "npm-registry",
                        "retrieval": "completed",
                        "version": "10.9.8",
                    },
                },
            )
            for values in product(*(scope[key] for key in scope_fields)):
                row["findings"].append(
                    {
                        "code": record["security"]["finding_code"],
                        "message": "Synthetic scanner finding",
                        "waiver_id": waiver,
                        **{
                            fields[key]: value
                            for key, value in zip(scope_fields, values)
                        },
                    }
                )
    ts = roots["typescript-npm"]
    return {
        "operation_id": "security.dependency-risk",
        "status": "waived",
        "summary": {
            "passed": 2,
            "waived": len(rows),
            "failed": 0,
            "incomplete": 0,
            "unavailable": 0,
        },
        "checks": [
            rows.pop("security.vulnerability.typescript-npm"),
            *rows.values(),
            {"check_id": "security.waivers", "status": "passed"},
            {
                "check_id": "security.license.typescript-npm",
                "category": "license",
                "ecosystem": "npm",
                "inputs": sorted(ts["locks"] + ts["manifests"]),
                "status": "passed",
                "findings": [],
                "scanner": {"components": []},
            },
        ],
    }


def resolve(risk, day=24, root=ROOT):
    with patch("tooling.security.datetime") as clock:
        clock.now.return_value = datetime(2026, 11, day, tzinfo=timezone.utc)
        return _dependency_resolution(
            root,
            {"security_policy": "governance/security-policy.json"},
            {"dependency_roots": ["typescript-npm"]},
            risk,
        )


def test_exact_waiver_preserves_public_sbom_trace(risk):
    original = deepcopy(risk)
    dependencies, unresolved = resolve(risk)
    assert unresolved == 0
    assert risk == original
    dependency = dependencies[0]
    assert dependency["waived_vulnerability_evidence"] == risk["checks"][0]
    assert len(dependency["risk_evidence_sha256"]) == 64
    document = _spdx_document(
        {
            "id": "release:typescript",
            "surface": "typescript",
            "package_name": "strling",
        },
        [{"name": "fixture.tgz", "sha256": "a" * 64}],
        "a" * 64,
        dependencies,
    )
    assert "WVR-SEC-PICOMATCH-REDOS-001" in document["annotations"][0]["comment"]
    assert '"status":"waived"' in document["annotations"][0]["comment"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("advisory", "https://example.invalid/advisory"),
        ("version", "4.0.8"),
        ("package", "unrelated"),
        ("severity", "critical"),
        ("waiver_id", "WVR-SEC-VSCE-LICENSE-001"),
    ],
)
def test_finding_scope_and_assignment_drift_rejected(risk, field, value):
    risk["checks"][0]["findings"][0][field] = value
    assert resolve(risk)[1] == 1


@pytest.mark.parametrize("status", ["failed", "unavailable", "incomplete", "passed"])
def test_waived_finding_cannot_be_reclassified(risk, status):
    risk["checks"][0]["status"] = status
    assert resolve(risk)[1] == 1


def test_expired_scope_rejected(risk):
    assert resolve(risk, day=25)[1] == 1


def test_missing_scanner_and_wrong_input_rejected(risk):
    risk["checks"][0]["scanner"]["retrieval"] = "failed"
    assert resolve(risk)[1] == 1
    risk["checks"][0]["scanner"]["retrieval"] = "completed"
    risk["checks"][0]["inputs"].append("package.json")
    assert resolve(risk)[1] == 1


def test_locked_runtime_copy_or_altered_authority_rejected(risk, tmp_path):
    paths = ["governance/security-policy.json"]
    paths.extend(
        f"governance/waivers/{identity}.yaml"
        for identity in load_policy()["security_waivers"]
    )
    for directory in ("tooling/lsp-server", "bindings/typescript"):
        paths.extend(
            f"{directory}/{name}" for name in ("package.json", "package-lock.json")
        )
    for relative in paths:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    assert resolve(risk, root=tmp_path)[1] == 0
    lock_path = tmp_path / "bindings/typescript/package-lock.json"
    original = lock_path.read_bytes()
    lock = json.loads(original)
    lock["packages"]["node_modules/picomatch"]["dev"] = False
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert resolve(risk, root=tmp_path)[1] == 1
    lock_path.write_bytes(original)
    record = tmp_path / "governance/waivers/WVR-SEC-PICOMATCH-REDOS-001.yaml"
    record.write_bytes(record.read_bytes() + b"\n# substituted source authority\n")
    assert resolve(risk, root=tmp_path)[1] == 1
