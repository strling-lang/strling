from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tooling.architecture_fitness import profile_operation_coverage_findings


PROFILE_IDS = ("local", "pull-request", "full", "release")


class ArchitectureProfileCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configuration = {
            "toolchain": "toolchain.json",
            "producer_manifest": "producer-manifest.json",
            "required_operations": ["generated_integrity", "architecture_check"],
        }
        self.toolchain = {
            "policy": {
                "profile_prefix": [{"operation": "generated_integrity"}],
                "operation_registry": {
                    "generated_integrity": {},
                    "architecture_check": {},
                },
                "profiles": {
                    profile: {"operations": [{"operation": "architecture_check"}]}
                    for profile in PROFILE_IDS
                },
            }
        }
        self.producer = {
            "producers": [
                {"operation_id": "generated_integrity"},
                {"operation_id": "architecture_check"},
            ]
        }

    def findings(self):
        with patch.object(
            Path,
            "read_text",
            side_effect=[json.dumps(self.toolchain), json.dumps(self.producer)],
        ):
            return profile_operation_coverage_findings(
                Path("fixture-only"), self.configuration
            )

    def test_shared_prefix_satisfies_required_coverage_without_mutating_policy(
        self,
    ) -> None:
        original = deepcopy(self.toolchain)
        self.assertEqual([], self.findings())
        self.assertEqual(original, self.toolchain)
        self.assertTrue(
            all(
                profile["operations"] == [{"operation": "architecture_check"}]
                for profile in self.toolchain["policy"]["profiles"].values()
            )
        )

    def test_missing_prefix_fails_each_effective_profile(self) -> None:
        del self.toolchain["policy"]["profile_prefix"]
        findings = self.findings()
        self.assertEqual(4, len(findings))
        for profile in PROFILE_IDS:
            self.assertTrue(
                any(
                    f"profile {profile}" in message
                    and "generated_integrity" in message
                    and "observed 0" in message
                    for message, _path in findings
                )
            )

    def test_duplicate_shared_gate_in_individual_profile_is_rejected(self) -> None:
        self.toolchain["policy"]["profiles"]["local"]["operations"].insert(
            0, {"operation": "generated_integrity"}
        )
        findings = self.findings()
        self.assertEqual(1, len(findings))
        self.assertIn("profile local", findings[0][0])
        self.assertIn("generated_integrity", findings[0][0])
        self.assertIn("observed 2", findings[0][0])

    def test_malformed_composition_fails_closed(self) -> None:
        for prefix in (
            "generated_integrity",
            [{"operation": "generated_integrity", "targets": []}],
        ):
            with self.subTest(prefix=prefix):
                self.toolchain["policy"]["profile_prefix"] = prefix
                findings = self.findings()
                self.assertEqual(1, len(findings))
                self.assertIn("registry is malformed", findings[0][0])

    def test_required_registry_and_product_producer_cover_shared_gate(self) -> None:
        del self.toolchain["policy"]["operation_registry"]["generated_integrity"]
        findings = self.findings()
        self.assertEqual(1, len(findings))
        self.assertIn("generated_integrity is unregistered", findings[0][0])
        self.toolchain["policy"]["operation_registry"]["generated_integrity"] = {}
        self.producer["producers"].pop(0)
        findings = self.findings()
        self.assertEqual(1, len(findings))
        self.assertIn("product certification", findings[0][0])
        self.assertIn("generated_integrity", findings[0][0])
        self.assertIn("observed 0", findings[0][0])

    def test_nonobject_policy_fails_closed_with_malformed_diagnostic(self) -> None:
        for policy in (None, [], "malformed-policy", 1):
            with self.subTest(policy=policy):
                self.toolchain["policy"] = policy
                findings = self.findings()
                self.assertEqual(1, len(findings))
                self.assertIn("registry is malformed", findings[0][0])
                self.assertIn("policy must be an object", findings[0][0])

    def test_legacy_fixture_without_prefix_retains_its_valid_membership(self) -> None:
        del self.toolchain["policy"]["profile_prefix"]
        self.configuration["required_operations"] = ["architecture_check"]
        del self.toolchain["policy"]["operation_registry"]["generated_integrity"]
        self.producer["producers"].pop(0)
        self.assertEqual([], self.findings())

    def test_registered_architecture_rule_requires_generated_integrity(self) -> None:
        root = Path(__file__).resolve().parents[2]
        rules = json.loads(
            (root / "governance/architecture-rules.json").read_text(encoding="utf-8")
        )
        rule = next(
            item
            for item in rules["rules"]
            if item["id"] == "architecture-hardgate-profile-coverage"
        )
        self.assertIn(
            "generated_integrity", rule["configuration"]["required_operations"]
        )


if __name__ == "__main__":
    unittest.main()
