"""Exact temporary risk acceptance; the real vulnerability remains visible."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tooling.security import Finding, SecurityCheck, SecurityEngine, SecurityOperation


ROOT = Path(__file__).resolve().parents[2]
WAIVER = "WVR-SEC-PICOMATCH-REDOS-001"
ADVISORY = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"


class PicomatchWaiverTests(unittest.TestCase):
    def operation(self) -> SecurityOperation:
        def finding(version: str) -> Finding:
            return Finding(
                "SEC-VULN-BLOCKING",
                "Unresolved single-branch repeated-extglob ReDoS",
                package="picomatch",
                version=version,
                advisory=ADVISORY,
                severity="high",
            )

        return SecurityOperation(
            "security.dependency-risk",
            "network",
            [
                SecurityCheck(
                    "security.vulnerability.lsp-npm",
                    "vulnerability",
                    "failed",
                    [
                        "tooling/lsp-server/package.json",
                        "tooling/lsp-server/package-lock.json",
                    ],
                    findings=[finding("4.0.7")],
                ),
                SecurityCheck(
                    "security.vulnerability.typescript-npm",
                    "vulnerability",
                    "failed",
                    [
                        "bindings/typescript/package.json",
                        "bindings/typescript/package-lock.json",
                    ],
                    findings=[finding("2.3.2"), finding("4.0.7")],
                ),
            ],
        )

    def apply(
        self,
        operation: SecurityOperation,
        *,
        today: date = date(2026, 11, 17),
        record_change=None,
    ) -> SecurityOperation:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = "governance/schemas/waiver.schema.json"
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes((ROOT / relative).read_bytes())
            record = yaml.safe_load(
                (ROOT / f"governance/waivers/{WAIVER}.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual("retired", record["status"])
            record["status"] = "accepted"
            if record_change:
                record_change(record)
            target = root / f"governance/waivers/{WAIVER}.yaml"
            target.parent.mkdir(parents=True)
            target.write_text(yaml.safe_dump(record), encoding="utf-8")
            engine = SecurityEngine(
                root,
                {"security_waivers": [WAIVER], "waiver_schema": relative},
                tracked_files=[],
                today=today,
            )
            return engine._apply_security_waivers(operation)

    def test_exact_three_findings_are_waived_and_keep_high_severity(self):
        result = self.apply(self.operation())
        self.assertEqual("waived", result.status)
        findings = [finding for check in result.checks for finding in check.findings]
        self.assertEqual(3, len(findings))
        self.assertEqual({WAIVER}, {finding.waiver_id for finding in findings})
        self.assertEqual({"high"}, {finding.severity for finding in findings})
        self.assertEqual({ADVISORY}, {finding.advisory for finding in findings})

    def test_expiry_is_inclusive_utc_date(self):
        self.assertEqual(
            "waived", self.apply(self.operation(), today=date(2026, 11, 24)).status
        )
        self.assertEqual(
            "failed", self.apply(self.operation(), today=date(2026, 11, 25)).status
        )

    def test_default_expiry_clock_uses_utc_even_when_local_date_is_previous_day(self):
        class LocalDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 24)

        with (
            patch("tooling.security.date", LocalDate),
            patch("tooling.security.datetime") as clock,
        ):
            clock.now.return_value = datetime(2026, 11, 25, 0, 1, tzinfo=timezone.utc)
            engine = SecurityEngine(ROOT, {}, tracked_files=[])
            self.assertEqual(date(2026, 11, 25), engine.today)
            clock.now.assert_called_once_with(timezone.utc)

    def test_advisory_package_version_severity_and_root_drift_fail(self):
        for field, value in (
            ("advisory", "https://advisories.invalid/unrelated"),
            ("package", "unrelated-package"),
            ("version", "4.0.8"),
            ("severity", "critical"),
        ):
            with self.subTest(field=field):
                operation = self.operation()
                operation.checks[0].findings[0] = replace(
                    operation.checks[0].findings[0], **{field: value}
                )
                self.assertEqual("failed", self.apply(operation).status)
        operation = self.operation()
        operation.checks[0].check_id = "security.vulnerability.repository-npm"
        self.assertEqual("failed", self.apply(operation).status)

    def test_missing_or_duplicate_findings_fail_closed(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                operation = self.operation()
                if duplicate:
                    operation.checks[0].findings.append(operation.checks[0].findings[0])
                else:
                    operation.checks[0].findings.clear()
                    operation.checks[0].status = "passed"
                self.assertEqual("failed", self.apply(operation).status)

    def test_unrelated_high_finding_is_never_waived(self):
        operation = self.operation()
        operation.checks[0].findings.append(
            replace(
                operation.checks[0].findings[0],
                advisory="https://advisories.invalid/new-high",
            )
        )
        result = self.apply(operation)
        self.assertEqual("failed", result.status)
        self.assertIsNone(result.checks[0].findings[-1].waiver_id)

    def test_extra_input_path_and_missing_input_path_fail(self):
        for remove in (False, True):
            with self.subTest(remove=remove):
                operation = self.operation()
                if remove:
                    operation.checks[0].inputs.pop()
                else:
                    operation.checks[0].inputs.append("package.json")
                self.assertEqual("failed", self.apply(operation).status)

    def test_duplicate_match_and_unaccepted_record_fail(self):
        def duplicate(record):
            record["security"]["matches"].append(
                deepcopy(record["security"]["matches"][0])
            )

        self.assertEqual(
            "failed", self.apply(self.operation(), record_change=duplicate).status
        )
        self.assertEqual(
            "failed",
            self.apply(
                self.operation(),
                record_change=lambda record: record.update(status="requested"),
            ).status,
        )

    def test_frozen_runtime_sources_and_development_closures_remain_exact(self):
        assessment = json.loads(
            (ROOT / "docs/migration/picomatch-402-exposure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "DEVELOPMENT_ONLY_NO_DEMONSTRATED_PUBLISHED_RUNTIME_PATH",
            assessment["status"],
        )
        self.assertEqual(
            "61fb4141faa5034964c5de17eb8b39a559b6cec9", assessment["source"]
        )
        version = json.loads((ROOT / "governance/release-policy.json").read_bytes())[
            "product"
        ]["version"]
        for relative, expected in assessment["runtime_source_sha256"].items():
            with self.subTest(path=relative):
                data = (ROOT / relative).read_bytes()
                if relative == "bindings/typescript/src/STRling/product_version.ts":
                    data = data.replace(version.encode(), b"4.0.2")
                self.assertEqual(expected, hashlib.sha256(data).hexdigest())
        for dependency in assessment["dependency_roots"]:
            path = ROOT / dependency["root"]
            manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest.get("dependencies"))
            self.assertFalse(manifest.get("optionalDependencies"))
            lock_bytes = (path / "package-lock.json").read_bytes()
            if dependency["root"] == "bindings/typescript":
                lock_bytes = lock_bytes.replace(
                    f'"version": "{version}"'.encode(), b'"version": "4.0.2"', 2
                )
            self.assertEqual(
                dependency["lock_sha256"], hashlib.sha256(lock_bytes).hexdigest()
            )
            lock = json.loads((path / "package-lock.json").read_text(encoding="utf-8"))
            for item in dependency["affected"]:
                entry = lock["packages"][item["path"]]
                self.assertTrue(entry["dev"])
                self.assertEqual(item["version"], entry["version"])
                self.assertEqual(item["integrity"], entry["integrity"])
        self.assertTrue(assessment["lsp"]["equals_prepared_payload"])
        self.assertFalse(
            any(
                "/picomatch/" in item or "/tinyglobby/" in item
                for item in assessment["lsp"]["inputs"]
            )
        )
        self.assertFalse(
            any(
                "node_modules/" in item
                for item in assessment["typescript"]["package_files"]
            )
        )

    def test_retired_advisory_has_no_active_security_or_trust_registration(self):
        expected = {"WVR-SEC-VSCE-LICENSE-001"}
        policy = json.loads(
            (ROOT / "governance/security-policy.json").read_text(encoding="utf-8")
        )
        trust = json.loads(
            (ROOT / "governance/local-certification-trust.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(expected, set(policy["security_waivers"]))
        self.assertEqual(expected, set(trust["allowed_waivers"]))
        self.assertEqual(
            "retired",
            yaml.safe_load((ROOT / f"governance/waivers/{WAIVER}.yaml").read_bytes())[
                "status"
            ],
        )
        self.assertEqual(
            ["high", "critical"], policy["vulnerability_policy"]["blocking_severities"]
        )


if __name__ == "__main__":
    unittest.main()
