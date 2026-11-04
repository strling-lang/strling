"""Adversarial checks for the deterministic resource obligation boundary."""

import copy
import unittest
import contextlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from tooling import functional_resource_certification as subject


class ResourceContractTests(unittest.TestCase):
    def test_runner_transport_roundtrip_and_rejection(self):
        from tooling.structured_operation_execution import (
            StructuredExecutionError,
            execution_context,
            validate_result_directory,
        )

        sha = "a" * 40
        import json

        registry = json.loads(Path("toolchain.json").read_text())["policy"][
            "operation_registry"
        ]["functional_resource_certification"]
        command = registry["command"]
        registered_profile = command[command.index("--profile") + 1]
        for profile, producer_profile in (
            ("pull-request", "pull-request"),
            ("full", registered_profile),
            ("release", registered_profile),
            ("full", "full"),
            ("release", "full"),
        ):
            for failed in (False, True):
                with tempfile.TemporaryDirectory() as directory:
                    checks = self.evidence()
                    if failed:
                        checks["checks"][0]["steps"][0]["exit_code"] = 1
                    context = execution_context(
                        producer_id="functional_resource_certification@repository",
                        operation_id="certification.functional-resource",
                        source_sha=sha,
                        invocation_id="b" * 32,
                        certification_profile=profile,
                        producer_profile=producer_profile,
                    )
                    argv = [
                        "--profile",
                        producer_profile,
                        "--json",
                        "--execution-directory",
                        directory,
                        "--certification-invocation-id",
                        "b" * 32,
                        "--certification-profile",
                        profile,
                        "--expected-source-sha",
                        sha,
                        "--producer-id",
                        context["producer_id"],
                    ]
                    with (
                        patch(
                            "subprocess.check_output",
                            side_effect=[sha.encode(), b"", sha.encode()],
                        ),
                        patch.object(subject, "execute_checks", return_value=checks),
                        contextlib.redirect_stdout(io.StringIO()),
                    ):
                        code = subject.main(argv)
                    self.assertEqual(code, int(failed))
                    artifact = validate_result_directory(
                        Path(directory),
                        expected_context=context,
                        result_contract="certification-result-v1",
                        actual_exit_code=code,
                    )
                    self.assertEqual(
                        artifact["sample_consumption"]["authenticated_sample_count"], 0
                    )
                    for key in ("source_sha", "invocation_id", "certification_profile"):
                        altered = {**context, key: "wrong"}
                        with self.assertRaises(StructuredExecutionError):
                            validate_result_directory(
                                Path(directory),
                                expected_context=altered,
                                result_contract="certification-result-v1",
                                actual_exit_code=code,
                            )
                    with self.assertRaises(StructuredExecutionError):
                        validate_result_directory(
                            Path(directory),
                            expected_context=context,
                            result_contract="certification-result-v1",
                            actual_exit_code=1 - code,
                        )

    def test_partial_transport_arguments_rejected_before_execution(self):
        with (
            patch.object(subject, "execute_checks") as execute,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit):
                subject.main(["--profile", "full", "--execution-directory", "unused"])
            execute.assert_not_called()

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
        self.assertEqual(subject.COMMANDS, original)

    def test_recorder_diagnostics_and_old_resource_contract_are_excluded(self):
        self.assertNotIn("resource:native-memory-lifetime", subject.COMMANDS)
        old = self.evidence()
        old["contract"] = "strling-functional-resource-v1"
        with self.assertRaises(ValueError):
            subject.validate_checks(old)
        mixed = self.evidence()
        mixed["checks"].append({"id": "resource:native-memory-lifetime", "steps": []})
        with self.assertRaises(ValueError):
            subject.validate_checks(mixed)

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
