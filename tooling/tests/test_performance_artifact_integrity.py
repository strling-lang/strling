from __future__ import annotations

import unittest
from unittest.mock import patch

from tooling import performance_artifact_integrity as integrity


class PerformanceArtifactIntegrityTests(unittest.TestCase):
    def test_only_pure_contract_validation_no_performance_producer(self) -> None:
        with (
            patch.object(
                integrity,
                "validate_repository_contract",
                return_value={"status": "passed"},
            ) as check,
            patch(
                "tooling.performance_resource_certification.certify",
                side_effect=AssertionError("performance forbidden"),
            ),
        ):
            result = integrity.check_integrity()
        check.assert_called_once_with(root=integrity.ROOT)
        self.assertEqual("passed", result["status"])
        self.assertFalse(result["authoritative"])
        self.assertEqual(0, result["authenticated_performance_samples"])
        self.assertNotIn("evidence_kind", result)

    def test_invalid_static_contract_fails_without_producer(self) -> None:
        with (
            patch.object(
                integrity,
                "validate_repository_contract",
                side_effect=ValueError("stale identity"),
            ),
            patch(
                "tooling.performance_resource_certification.certify",
                side_effect=AssertionError("performance forbidden"),
            ),
        ):
            result = integrity.check_integrity()
        self.assertEqual("failed", result["status"])
        self.assertEqual("stale identity", result["reason"])
        self.assertEqual(0, result["authenticated_performance_samples"])


if __name__ == "__main__":
    unittest.main()
