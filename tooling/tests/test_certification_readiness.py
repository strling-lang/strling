from __future__ import annotations

import copy
import json
import sys
import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from tooling.certification import CertificationError, validate_certification_artifact
from tooling.certification_readiness import (
    ARTIFACT_KIND,
    ReadinessRunner,
    main,
    performance_stage,
    quality,
    readiness_artifact,
    selection,
)
from tooling import nonperformance_production_readiness as independent

ROOT = Path(__file__).resolve().parents[2]
SOURCE = {"commit": "a" * 40, "dirty": False}


class CertificationReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = ReadinessRunner(quality.Toolchain.load(ROOT / "toolchain.json"))

    def results(self, profile: str) -> list[quality.OperationResult]:
        return [
            quality.OperationResult(
                operation=stage.operation,
                component=stage.component,
                status="passed",
                command=None,
                exit_code=0,
                reason=None,
            )
            for stage in self.runner._profile_stages(profile, None)
        ]

    def test_exact_governed_membership_only_performance_is_deferred(self) -> None:
        for profile, total, deferred in (
            ("local", 37, 1),
            ("pull-request", 79, 2),
            ("full", 125, 3),
            ("release", 125, 3),
        ):
            with self.subTest(profile=profile):
                plan = selection(self.runner, profile)
                stages = quality.QualityRunner._profile_stages(
                    self.runner, profile, None
                )
                self.assertEqual(len(plan["governed_result_ids"]), total)
                self.assertEqual(len(plan["deferred_operations"]), deferred)
                self.assertEqual(len(plan["selected_result_ids"]), total - deferred)
                self.assertEqual(
                    plan["selected_result_ids"],
                    [
                        f"{s.operation}@{s.component}"
                        for s in stages
                        if not performance_stage(s)
                    ],
                )

    def test_ambiguous_performance_metadata_fails_closed(self) -> None:
        stage = next(
            stage
            for stage in quality.QualityRunner._profile_stages(
                self.runner, "full", None
            )
            if performance_stage(stage)
        )
        definition = copy.deepcopy(stage.definition)
        definition["command"] = ["python3", "some_other_producer.py"]
        with self.assertRaises(quality.ConfigurationError):
            performance_stage(replace(stage, definition=definition))

    def test_artifact_cannot_validate_as_authoritative_full_or_release(self) -> None:
        for profile in ("full", "release"):
            artifact = readiness_artifact(
                runner=self.runner,
                profile=profile,
                results=self.results(profile),
                source=SOURCE,
            )
            self.assertEqual(artifact["artifact_kind"], ARTIFACT_KIND)
            self.assertFalse(artifact["authoritative"])
            self.assertTrue(artifact["performance_deferred"])
            self.assertFalse(artifact["closure_authorized"])
            self.assertEqual(
                artifact["deterministic_evidence"]["readiness_status"], "passed"
            )
            with self.assertRaises(CertificationError):
                validate_certification_artifact(ROOT, artifact)

    def test_nonpassing_or_missing_operation_is_never_ready(self) -> None:
        for status in ("failed", "unavailable", "incomplete", "not_applicable"):
            results = self.results("local")
            results[0].status = status
            results[0].reason = "controlled nonpassing operation"
            results[0].exit_code = {
                "failed": 1,
                "unavailable": 2,
                "incomplete": 3,
                "not_applicable": None,
            }[status]
            artifact = readiness_artifact(
                runner=self.runner, profile="local", results=results, source=SOURCE
            )
            self.assertEqual(
                artifact["deterministic_evidence"]["readiness_status"], "failed"
            )
        artifact = readiness_artifact(
            runner=self.runner,
            profile="local",
            results=self.results("local")[:1],
            source=SOURCE,
        )
        self.assertEqual(
            artifact["deterministic_evidence"]["readiness_status"], "failed"
        )
        self.assertEqual(
            len(artifact["deterministic_evidence"]["unexecuted_result_ids"]), 35
        )

    def test_fail_fast_and_no_performance_producer_called(self) -> None:
        with patch.object(self.runner, "run_repository_operation") as execute:
            execute.return_value = quality.OperationResult(
                operation="security_dependency_integrity",
                component="repository",
                status="failed",
                command=None,
                exit_code=1,
                reason="controlled failure",
            )
            results = self.runner.run_profile("full", None)
            self.assertEqual(len(results), 1)
            execute.assert_called_once()
            self.assertNotIn("performance", execute.call_args.args[0])
        self.assertTrue(
            all(
                not performance_stage(s)
                for s in self.runner._profile_stages("full", None)
            )
        )

    def test_source_change_during_execution_fails_the_cli_artifact(self) -> None:
        module = sys.modules[main.__module__]
        with TemporaryDirectory() as temporary:
            artifact_path = Path(temporary) / "readiness.json"
            with (
                patch.object(
                    module,
                    "repository_state",
                    side_effect=[SOURCE, {**SOURCE, "dirty": True}],
                ),
                patch.object(module.quality, "_preflight_profile_environment"),
                patch.object(module.quality, "ProfileProgress"),
                patch.object(module.quality, "_render_profile_failure_details"),
                patch.object(
                    ReadinessRunner, "run_profile", return_value=self.results("local")
                ),
            ):
                self.assertEqual(
                    main(["--profile", "local", "--artifact", str(artifact_path)]), 1
                )
            artifact = json.loads(artifact_path.read_text())
            self.assertFalse(artifact["authoritative"])
            self.assertEqual(
                artifact["deterministic_evidence"]["readiness_status"], "failed"
            )
            self.assertTrue(
                artifact["deterministic_evidence"]["source_changed_during_execution"]
            )

    def test_independent_release_has_fresh_setup_and_development_receipt(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            identity = {"sha": SOURCE["commit"], "status_porcelain": ""}
            with (
                patch.object(independent.production, "ROOT", root),
                patch.object(
                    independent.production, "repository_identity", return_value=identity
                ),
                patch.object(
                    independent.production,
                    "build_certification_environment",
                    return_value={},
                ),
                patch.object(
                    independent.production, "load_capacity_contract", return_value={}
                ),
                patch.object(
                    independent.production,
                    "storage_capacity_evidence",
                    return_value={"status": "passed"},
                ),
                patch.object(independent.production, "create_worktree") as create,
                patch.object(
                    independent.production,
                    "materialize_governed_production_inputs",
                    return_value=[],
                ),
                patch.object(independent.production, "run_capacity_checked") as run,
                patch.object(
                    independent.production,
                    "preserve_execution_evidence",
                    return_value=[],
                ),
            ):
                self.assertEqual(
                    independent.main(["--artifact-directory", str(output)]), 0
                )
            create.assert_called_once()
            self.assertEqual(create.call_args.kwargs["source_sha"], SOURCE["commit"])
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn(["./strling", "setup", "all"], commands)
            self.assertIn(["./strling", "generate"], commands)
            self.assertIn("tooling.certification_readiness", commands[-1])
            self.assertFalse(
                any(
                    "tooling.performance_resource_certification" in command
                    for command in commands
                )
            )
            receipt = json.loads(
                (output / "nonperformance-production-receipt.json").read_text()
            )
            self.assertFalse(receipt["authoritative"])
            self.assertFalse(receipt["closure_authorized"])
            self.assertTrue(receipt["performance_deferred"])
            self.assertTrue(receipt["independent_no_reuse"])

    def test_independent_release_rejects_evidence_reuse_before_execution(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch.object(
                    independent.production,
                    "repository_identity",
                    return_value={"sha": SOURCE["commit"], "status_porcelain": ""},
                ),
                patch.object(independent.production, "create_worktree") as create,
                self.assertRaises(SystemExit),
            ):
                independent.main(["--artifact-directory", temporary])
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
