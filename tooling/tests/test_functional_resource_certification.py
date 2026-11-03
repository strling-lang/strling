"""Adversarial checks for the deterministic resource obligation boundary."""

import copy
import unittest
from tooling import functional_resource_certification as subject


class ResourceContractTests(unittest.TestCase):
    def evidence(self):
        return subject.execute_checks(
            lambda command: {"command": command, "exit_code": 0}
        )

    def test_complete_without_performance(self):
        self.assertTrue(subject.validate_checks(self.evidence()))

    def test_every_functional_failure_blocks(self):
        base = self.evidence()
        for i, check in enumerate(base["checks"]):
            for j in range(len(check["steps"])):
                changed = copy.deepcopy(base)
                changed["checks"][i]["steps"][j]["exit_code"] = 1
                with self.assertRaises(ValueError):
                    subject.validate_checks(changed)

    def test_missing_duplicate_stale_and_tampered(self):
        base = self.evidence()
        variants = []
        v = copy.deepcopy(base)
        v["checks"].pop()
        variants.append(v)
        v = copy.deepcopy(base)
        v["checks"][0] = v["checks"][1]
        variants.append(v)
        v = copy.deepcopy(base)
        v["contract"] = "certification-result-v1"
        variants.append(v)
        v = copy.deepcopy(base)
        v["checks"][0]["steps"][0]["command"] = ["echo", "passed"]
        variants.append(v)
        v = copy.deepcopy(base)
        v["checks"][0]["steps"][0]["exit_code"] = False
        variants.append(v)
        for v in variants:
            with self.assertRaises(ValueError):
                subject.validate_checks(v)

    def test_execution_continues_after_failure(self):
        calls = []

        def run(command):
            calls.append(command)
            return {"command": command, "exit_code": 1}

        result = subject.execute_checks(run)
        self.assertEqual(len(calls), sum(map(len, subject.COMMANDS.values())))
        with self.assertRaises(ValueError):
            subject.validate_checks(result)

    def test_preserves_original_functional_commands(self):
        import ast
        from pathlib import Path

        tree = ast.parse(
            Path(subject.__file__)
            .with_name("performance_resource_certification.py")
            .read_text()
        )
        original = next(
            ast.literal_eval(n.value)
            for n in tree.body
            if isinstance(n, ast.AnnAssign)
            and getattr(n.target, "id", "") == "RESOURCE_COMMANDS"
        )
        self.assertEqual({k: subject.COMMANDS[k] for k in original}, original)
        self.assertIn("resource:native-memory-lifetime", subject.COMMANDS)

    def test_envelope_rejects_old_scope_stale_and_tampered(self):
        value = subject.make_evidence("a" * 40, "full", self.evidence())
        self.assertTrue(
            subject.validate_evidence(value, source_sha="a" * 40, profile="full")
        )
        for key, bad in [
            ("certification_contract", "performance-inclusive"),
            ("commit", "b" * 40),
            ("profile", "release"),
            ("status", "failed"),
            ("evidence_fingerprint", "0" * 64),
        ]:
            changed = copy.deepcopy(value)
            changed[key] = bad
            with self.assertRaises(ValueError):
                subject.validate_evidence(changed, source_sha="a" * 40, profile="full")

    def test_failed_evidence_cannot_be_signed_as_success(self):
        checks = self.evidence()
        checks["checks"][0]["steps"][0]["exit_code"] = 1
        value = subject.make_evidence("a" * 40, "full", checks)
        self.assertEqual(value["status"], "failed")
        with self.assertRaises(ValueError):
            subject.validate_evidence(value, source_sha="a" * 40, profile="full")

    def test_attestation_scope_accepts_absent_performance_only(self):
        from tooling import local_certification_attestation as attestation

        artifact = {
            "deterministic_evidence": {
                "certification_contract": subject.CERTIFICATION_CONTRACT,
                "profile": {"id": "full"},
                "operations": [],
            }
        }
        attestation._require_deterministic_scope((artifact,))
        zero = copy.deepcopy(artifact)
        zero["deterministic_evidence"]["operations"] = [
            {
                "operation_id": "functional_resource_certification",
                "execution_integrity": {
                    "sample_consumption": {
                        "state": "zero",
                        "authenticated_sample_count": 0,
                    }
                },
            }
        ]
        self.assertEqual(attestation._sample_counts((zero,)), {})
        attestation._require_deterministic_scope((zero,))
        for count in (-1, 1):
            changed = copy.deepcopy(zero)
            changed["deterministic_evidence"]["operations"][0]["execution_integrity"][
                "sample_consumption"
            ]["authenticated_sample_count"] = count
            with self.assertRaises(attestation.AttestationError):
                attestation._require_deterministic_scope((changed,))
        for scope in (None, "historical-performance-inclusive"):
            changed = copy.deepcopy(artifact)
            changed["deterministic_evidence"]["certification_contract"] = scope
            with self.assertRaises(attestation.AttestationError):
                attestation._require_deterministic_scope((changed,))
        changed = copy.deepcopy(artifact)
        changed["deterministic_evidence"]["operations"] = [
            {
                "operation_id": "performance_resource_full_certification",
            }
        ]
        with self.assertRaises(attestation.AttestationError):
            attestation._require_deterministic_scope((changed,))
