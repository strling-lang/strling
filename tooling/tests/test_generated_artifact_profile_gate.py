from __future__ import annotations

import copy
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch

from tooling.certification import profile_definition_fingerprint, repository_state
from tooling.profile_composition import (
    ProfileCompositionError,
    profile_prefix,
    resolve_profile,
    resolve_profiles,
)
from tooling.tests.test_profile_certification import configured_policy
from tooling.tests.test_quality import (
    ConfigurationError,
    Execution,
    QualityRunner,
    Toolchain,
    quality_main,
)


ROOT = Path(__file__).resolve().parents[2]
GATE = "generated_integrity"
RESULT_ID = "certification.generated-artifact-integrity"
COMMAND = [
    "python3",
    "tooling/generated_artifacts.py",
    "--check",
    "--complete",
    "--json",
]


def gated_policy() -> dict[str, object]:
    data = configured_policy()
    policy = cast(dict[str, object], data["policy"])
    policy["profile_prefix"] = [{"operation": GATE}]
    registry = cast(dict[str, object], policy["operation_registry"])
    registry[GATE] = {
        "kind": "repository",
        "component": "alpha",
        "command": COMMAND,
        "network": "offline",
        "result_contract": "certification-result-v1",
        "result_operation_id": RESULT_ID,
    }
    return data


def execution(status: str) -> Execution:
    code = {"passed": 0, "failed": 1, "waived": 0, "unavailable": 2, "incomplete": 3}[
        status
    ]
    return Execution(code, json.dumps({"operation_id": RESULT_ID, "status": status}))


class GeneratedArtifactProfileGateTests(unittest.TestCase):
    def test_all_profiles_share_one_first_gate_without_duplicate_membership(
        self,
    ) -> None:
        data = gated_policy()
        before = copy.deepcopy(data)
        policy = cast(dict[str, object], data["policy"])
        toolchain = Toolchain(data, ROOT)
        for profile_id, definition in resolve_profiles(policy).items():
            with self.subTest(profile=profile_id):
                members = cast(list[dict[str, object]], definition["operations"])
                self.assertEqual({"operation": GATE}, members[0])
                self.assertEqual(
                    1, sum(member["operation"] == GATE for member in members)
                )
                self.assertEqual(definition, toolchain.profile(profile_id))
                raw = cast(
                    dict[str, object],
                    cast(dict[str, object], policy["profiles"])[profile_id],
                )
                self.assertNotIn({"operation": GATE}, raw["operations"])
        self.assertEqual(before, data)

    def test_shared_composition_is_fingerprinted_and_legacy_identity_is_unchanged(
        self,
    ) -> None:
        legacy = cast(dict[str, object], configured_policy()["policy"])
        raw = cast(
            dict[str, object], cast(dict[str, object], legacy["profiles"])["full"]
        )
        self.assertEqual(raw, resolve_profile(legacy, "full"))
        self.assertEqual(
            profile_definition_fingerprint(raw),
            profile_definition_fingerprint(resolve_profile(legacy, "full")),
        )
        legacy["profile_prefix"] = [{"operation": GATE}]
        self.assertNotEqual(
            profile_definition_fingerprint(raw),
            profile_definition_fingerprint(resolve_profile(legacy, "full")),
        )

    def test_resolved_memberships_are_independent_copies(self) -> None:
        data = gated_policy()
        policy = cast(dict[str, object], data["policy"])
        first = resolve_profile(policy, "local")
        cast(list[dict[str, object]], first["operations"])[0]["operation"] = "mutated"
        self.assertEqual([{"operation": GATE}], profile_prefix(policy))
        self.assertEqual(
            {"operation": GATE}, resolve_profile(policy, "local")["operations"][0]
        )

    def test_malformed_duplicate_or_component_prefix_is_rejected(self) -> None:
        data = gated_policy()
        policy = cast(dict[str, object], data["policy"])
        for prefix in (
            {},
            [{"operation": GATE, "targets": ["alpha"]}],
            [{"operation": 3}],
        ):
            with self.subTest(prefix=prefix):
                policy["profile_prefix"] = prefix
                with self.assertRaises(ProfileCompositionError):
                    resolve_profiles(policy)
        policy["profile_prefix"] = [{"operation": "lint"}]
        with self.assertRaisesRegex(ConfigurationError, "immutable complete-check"):
            Toolchain(data, ROOT)
        policy["profile_prefix"] = [{"operation": GATE}, {"operation": GATE}]
        with self.assertRaisesRegex(ConfigurationError, "repeats operation"):
            Toolchain(data, ROOT)

    def test_registered_integrity_cannot_be_omitted_or_changed_to_mutation(
        self,
    ) -> None:
        for defect in ("missing-prefix", "mutating-command", "wrong-identity"):
            with self.subTest(defect=defect):
                data = gated_policy()
                policy = cast(dict[str, object], data["policy"])
                registry = cast(dict[str, object], policy["operation_registry"])
                gate = cast(dict[str, object], registry[GATE])
                if defect == "missing-prefix":
                    policy.pop("profile_prefix")
                elif defect == "mutating-command":
                    gate["command"] = [
                        "python3",
                        "tooling/generated_artifacts.py",
                        "--prepare",
                        "--json",
                    ]
                else:
                    gate["result_operation_id"] = "certification.fixture"
                with self.assertRaisesRegex(
                    ConfigurationError, "immutable complete-check"
                ):
                    Toolchain(data, ROOT)

    def test_stale_authoritative_gate_fails_before_every_later_executor(self) -> None:
        for profile in ("local", "pull-request", "full", "release"):
            with self.subTest(profile=profile):
                calls: list[tuple[str, list[str]]] = []

                def gate(operation: str, command: list[str]) -> Execution:
                    calls.append((operation, command))
                    return execution("failed")

                runner = QualityRunner(
                    Toolchain(gated_policy(), ROOT),
                    executor=lambda *_args: self.fail("later component executed"),
                    hardgate_executor=gate,
                    source_snapshotter=lambda: {},
                )
                results = runner.run_profile(
                    profile,
                    None,
                    preflight=lambda: self.fail("build-capable preflight executed"),
                )
                self.assertEqual([(GATE, COMMAND)], calls)
                self.assertEqual(["failed"], [result.status for result in results])
                self.assertNotIn("--prepare", calls[0][1])
                self.assertNotIn("--write", calls[0][1])

    def test_explicit_profile_preflight_runs_only_after_fresh_integrity_gate(
        self,
    ) -> None:
        for status in ("passed", "failed", "incomplete"):
            with self.subTest(status=status):
                calls: list[str] = []

                def gate(_operation: str, _command: list[str]) -> Execution:
                    calls.append("integrity")
                    return execution(status)

                def component(*_args: object) -> Execution:
                    calls.append("component")
                    # Keep this a deliberately failed synthetic prefix, never
                    # an actual complete or green certification profile.
                    return Execution(1)

                runner = QualityRunner(
                    Toolchain(gated_policy(), ROOT),
                    executor=component,
                    hardgate_executor=gate,
                    source_snapshotter=lambda: {},
                )
                stdout, stderr = StringIO(), StringIO()
                with (
                    patch("quality.Toolchain.load", return_value=runner.toolchain),
                    patch("quality.QualityRunner", return_value=runner),
                    patch(
                        "quality.repository_state",
                        return_value={"commit": "c" * 40, "dirty": False},
                    ),
                    patch("quality.ProfileProgress"),
                    patch(
                        "quality._profile_output_guard", return_value=lambda _path: None
                    ),
                    patch(
                        "quality._preflight_profile_environment",
                        side_effect=lambda profile: calls.append(
                            f"preflight:{profile}"
                        ),
                    ),
                    patch(
                        "quality._preflight_profile_inputs",
                        side_effect=lambda profile: calls.append(f"inputs:{profile}"),
                    ),
                    patch(
                        "quality.build_certification_artifact",
                        return_value={"synthetic_fixture_only": True},
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    code = quality_main(["profile", "pull-request", "--json"])
                self.assertEqual(1, code)
                self.assertEqual(
                    [
                        "inputs:pull-request",
                        "integrity",
                        "preflight:pull-request",
                        "component",
                    ]
                    if status == "passed"
                    else ["inputs:pull-request", "integrity"],
                    calls,
                )

    def test_missing_inputs_fail_before_integrity_or_any_build(self) -> None:
        calls: list[str] = []
        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("expensive integrity executed"),
            source_snapshotter=lambda: {},
        )

        def missing() -> None:
            calls.append("inputs")
            raise ConfigurationError("missing exact input")

        with self.assertRaisesRegex(ConfigurationError, "missing exact input"):
            runner.run_profile(
                "pull-request",
                None,
                input_preflight=missing,
                preflight=lambda: self.fail("build-capable preflight executed"),
            )
        self.assertEqual(["inputs"], calls)

    def test_early_input_check_does_not_reuse_or_omit_a_single_profile_stage(
        self,
    ) -> None:
        calls: list[str] = []
        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: calls.append("component") or Execution(1),
            hardgate_executor=lambda *_args: (
                calls.append("integrity") or execution("passed")
            ),
            source_snapshotter=lambda: {},
        )
        results = runner.run_profile(
            "pull-request",
            None,
            input_preflight=lambda: calls.append("inputs"),
            preflight=lambda: calls.append("full-preflight"),
        )
        self.assertEqual(["inputs", "integrity", "full-preflight", "component"], calls)
        self.assertEqual([GATE, "lint"], [r.operation for r in results])
        self.assertEqual(["passed", "failed"], [r.status for r in results])

    def test_even_read_only_input_hook_is_guarded_against_source_mutation(self) -> None:
        state = {"candidate.txt": "frozen"}
        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("integrity executed"),
            source_snapshotter=lambda: dict(state),
        )
        with self.assertRaisesRegex(
            ConfigurationError, "input preflight changed frozen"
        ):
            runner.run_profile(
                "pull-request",
                None,
                input_preflight=lambda: state.update({"candidate.txt": "changed"}),
            )

    def test_unavailable_snapshot_after_input_hook_never_reaches_integrity(
        self,
    ) -> None:
        captures = 0

        def snapshot() -> dict[str, str]:
            nonlocal captures
            captures += 1
            if captures == 2:
                raise OSError("input-boundary snapshot unavailable")
            return {}

        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("integrity executed"),
            source_snapshotter=snapshot,
        )
        with self.assertRaisesRegex(
            ConfigurationError, "input-boundary snapshot unavailable"
        ):
            runner.run_profile("pull-request", None, input_preflight=lambda: None)

    def test_failed_deferred_preflight_never_starts_later_stage(self) -> None:
        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: execution("passed"),
            source_snapshotter=lambda: {},
        )

        def fail_preflight() -> None:
            raise ConfigurationError("fixture preflight failure")

        with self.assertRaisesRegex(ConfigurationError, "fixture preflight failure"):
            runner.run_profile("pull-request", None, preflight=fail_preflight)

    def test_legacy_without_shared_gate_retains_eager_preflight(self) -> None:
        calls: list[str] = []

        def component(*_args: object) -> Execution:
            calls.append("component")
            return Execution(1)

        runner = QualityRunner(
            Toolchain(configured_policy(), ROOT),
            executor=component,
            source_snapshotter=lambda: self.fail("legacy source guard executed"),
        )
        runner.run_profile(
            "pull-request", None, preflight=lambda: calls.append("preflight")
        )
        self.assertEqual(["preflight", "component"], calls)

    def test_diagnostic_prefix_pass_or_fail_runs_only_gate_without_profile_authority(
        self,
    ) -> None:
        for status in ("passed", "failed", "incomplete"):
            for profile in ("local", "pull-request", "full", "release"):
                with self.subTest(status=status, profile=profile):
                    runner = QualityRunner(
                        Toolchain(gated_policy(), ROOT),
                        executor=lambda *_args: self.fail("later component executed"),
                        hardgate_executor=lambda operation, command: (
                            execution(status)
                            if (operation, command) == (GATE, COMMAND)
                            else self.fail("later repository operation executed")
                        ),
                        source_snapshotter=lambda: self.fail(
                            "diagnostic source guard executed"
                        ),
                    )
                    stdout, stderr = StringIO(), StringIO()
                    with (
                        patch("quality.Toolchain.load", return_value=runner.toolchain),
                        patch("quality.QualityRunner", return_value=runner),
                        patch(
                            "quality.repository_state",
                            side_effect=AssertionError("source identity produced"),
                        ),
                        patch(
                            "quality._preflight_profile_environment",
                            side_effect=AssertionError("profile preflight executed"),
                        ),
                        patch(
                            "quality.build_certification_artifact",
                            side_effect=AssertionError(
                                "certification artifact produced"
                            ),
                        ),
                        patch(
                            "quality.ProfileProgress",
                            side_effect=AssertionError("authoritative ledger produced"),
                        ),
                        patch(
                            "quality._profile_output_guard",
                            side_effect=AssertionError(
                                "profile receipt guard executed"
                            ),
                        ),
                        redirect_stdout(stdout),
                        redirect_stderr(stderr),
                    ):
                        code = quality_main(
                            ["profile", profile, "--through", GATE, "--json"]
                        )
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(0 if status == "passed" else 1, code)
                    self.assertEqual("profile-prefix", payload["operation"])
                    self.assertEqual("diagnostic-only", payload["evidence_role"])
                    self.assertFalse(payload["authoritative"])
                    self.assertFalse(payload["profile_complete"])
                    self.assertNotIn("deterministic_evidence", payload)
                    self.assertEqual(status, payload["status"])
                    self.assertEqual(
                        [GATE], [result["operation"] for result in payload["results"]]
                    )

    def test_diagnostic_boundary_cannot_select_performance_or_write_profile_artifact(
        self,
    ) -> None:
        arguments = [
            ["profile", "full", "--through", "performance_resource_full_certification"],
            ["profile", "full", "--through", GATE, "--artifact", "profile.json"],
            ["certify", "--through", GATE],
            ["profile", "local", "--through", GATE, "--through", GATE],
            ["profile", "local", "--through"],
        ]
        for args in arguments:
            with (
                self.subTest(args=args),
                patch(
                    "quality.Toolchain.load",
                    side_effect=AssertionError("execution started"),
                ),
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(2, quality_main(args))

    def test_canonical_repo_gate_has_exact_check_only_contract_and_new_denominators(
        self,
    ) -> None:
        toolchain = Toolchain.load(ROOT / "toolchain.json")
        definition = toolchain.operation(GATE)
        self.assertEqual(COMMAND, definition["command"])
        self.assertEqual(RESULT_ID, definition["result_operation_id"])
        self.assertEqual("certification-result-v1", definition["result_contract"])
        profiles = ("local", "pull-request", "full", "release")
        runner = QualityRunner(toolchain)
        for profile in profiles:
            stages = runner._profile_stages(profile, None)
            self.assertEqual(GATE, stages[0].operation)
            self.assertEqual(
                len({(s.operation, s.component) for s in stages}), len(stages)
            )
            from tooling.profile_composition import resolve_profile

            policy = json.loads((ROOT / "toolchain.json").read_text())["policy"]
            expected = []
            for member in resolve_profile(policy, profile)["operations"]:
                operation = member["operation"]
                registered = policy["operation_registry"][operation]
                targets = (
                    [registered["component"]]
                    if registered["kind"] == "repository"
                    else member["targets"]
                )
                expected.extend((operation, component) for component in targets)
            self.assertEqual(expected, [(s.operation, s.component) for s in stages])

    def test_integrity_producer_cannot_waive_or_defer_mandatory_gate(self) -> None:
        for status in ("waived", "unavailable", "incomplete"):
            with self.subTest(status=status):
                runner = QualityRunner(
                    Toolchain(gated_policy(), ROOT),
                    executor=lambda *_args: self.fail("later component executed"),
                    hardgate_executor=lambda *_args: execution(status),
                    source_snapshotter=lambda: {},
                )
                results = runner.run_profile(
                    "pull-request",
                    None,
                    preflight=lambda: self.fail("preflight executed"),
                )
                self.assertEqual(["incomplete"], [result.status for result in results])
                self.assertIn("requires passed or failed", results[0].reason)
                self.assertEqual(status, results[0].structured_result["status"])

    def test_frozen_source_guard_stops_later_build_mutation_without_rewriting_child(
        self,
    ) -> None:
        for profile in ("local", "pull-request", "full", "release"):
            with self.subTest(profile=profile), TemporaryDirectory() as directory:
                source = Path(directory) / "candidate.txt"
                source.write_text("frozen")
                calls: list[str] = []

                def component(*_args: object) -> Execution:
                    calls.append("component")
                    source.write_text("changed")
                    return Execution(
                        0, "original child stdout", "original child stderr"
                    )

                runner = QualityRunner(
                    Toolchain(gated_policy(), ROOT),
                    executor=component,
                    hardgate_executor=lambda *_args: execution("passed"),
                    source_snapshotter=lambda: {
                        "candidate.txt": source.read_bytes().hex()
                    },
                )
                results = runner.run_profile(profile, None)
                self.assertEqual(["component"], calls)
                self.assertEqual(
                    ["passed", "failed"], [result.status for result in results]
                )
                blocked = results[-1]
                self.assertEqual(0, blocked.exit_code)
                guard = blocked.execution_integrity["profile_source_guard"]
                self.assertEqual(["candidate.txt"], guard["changed_paths"])
                self.assertEqual("passed", guard["observed_child"]["status"])
                self.assertEqual(0, guard["observed_child"]["exit_code"])
                self.assertEqual(
                    "original child stdout", guard["observed_child"]["stdout"]
                )
                self.assertEqual(
                    "original child stderr", guard["observed_child"]["stderr"]
                )
                self.assertEqual("changed", source.read_text())

    def test_frozen_source_guard_blocks_mutating_preflight_before_component(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "candidate.txt"
            source.write_text("frozen")
            runner = QualityRunner(
                Toolchain(gated_policy(), ROOT),
                executor=lambda *_args: self.fail("component executed"),
                hardgate_executor=lambda *_args: execution("passed"),
                source_snapshotter=lambda: {"candidate.txt": source.read_bytes().hex()},
            )
            with self.assertRaisesRegex(
                ConfigurationError, "stage lint was not executed"
            ):
                runner.run_profile(
                    "pull-request",
                    None,
                    preflight=lambda: source.write_text("changed"),
                )
            self.assertEqual("changed", source.read_text())

    def test_frozen_source_guard_preserves_structured_gate_child_receipt(self) -> None:
        state = {"candidate.txt": "frozen"}

        def mutating_gate(*_args: object) -> Execution:
            state["candidate.txt"] = "changed"
            return execution("passed")

        runner = QualityRunner(
            Toolchain(gated_policy(), ROOT),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=mutating_gate,
            source_snapshotter=lambda: dict(state),
        )
        results = runner.run_profile(
            "pull-request",
            None,
            preflight=lambda: self.fail("preflight executed"),
        )
        self.assertEqual(["failed"], [result.status for result in results])
        self.assertEqual("passed", results[0].structured_result["status"])
        self.assertEqual(0, results[0].exit_code)
        child = results[0].execution_integrity["profile_source_guard"]["observed_child"]
        self.assertEqual("passed", child["status"])
        self.assertEqual(execution("passed").stdout, child["stdout"])

    def test_frozen_source_snapshot_failure_fails_closed(self) -> None:
        for failure_at in (1, 2, 3, 4):
            with self.subTest(failure_at=failure_at):
                captures = 0
                executions: list[str] = []

                def snapshot() -> dict[str, str]:
                    nonlocal captures
                    captures += 1
                    if captures == failure_at:
                        raise OSError("fixture snapshot unavailable")
                    return {"candidate.txt": "frozen"}

                def gate(*_args: object) -> Execution:
                    executions.append("gate")
                    return execution("passed")

                def component(*_args: object) -> Execution:
                    executions.append("component")
                    return Execution(
                        0, "original child stdout", "original child stderr"
                    )

                runner = QualityRunner(
                    Toolchain(gated_policy(), ROOT),
                    executor=component,
                    hardgate_executor=gate,
                    source_snapshotter=snapshot,
                )
                if failure_at in (1, 3):
                    with self.assertRaisesRegex(
                        ConfigurationError, "snapshot unavailable"
                    ):
                        runner.run_profile("pull-request", None, preflight=lambda: None)
                else:
                    results = runner.run_profile(
                        "pull-request", None, preflight=lambda: None
                    )
                    expected = ["failed"] if failure_at == 2 else ["passed", "failed"]
                    self.assertEqual(expected, [result.status for result in results])
                    self.assertIn("snapshot unavailable", results[-1].reason)
                expected_calls = (
                    []
                    if failure_at == 1
                    else ["gate", "component"]
                    if failure_at == 4
                    else ["gate"]
                )
                self.assertEqual(expected_calls, executions)

    def test_repository_identity_git_queries_are_read_only_without_host_env_change(
        self,
    ) -> None:
        with (
            patch.dict(
                os.environ,
                {"GIT_OPTIONAL_LOCKS": "1", "STRLING_UNIT_SENTINEL": "present"},
            ),
            patch(
                "tooling.certification.subprocess.run",
                side_effect=[
                    subprocess.CompletedProcess(["git"], 0, "c" * 40 + "\n", ""),
                    subprocess.CompletedProcess(["git"], 0, "", ""),
                ],
            ) as commands,
        ):
            self.assertEqual(
                {"commit": "c" * 40, "dirty": False}, repository_state(ROOT)
            )
            self.assertEqual("1", os.environ["GIT_OPTIONAL_LOCKS"])
            self.assertEqual(2, commands.call_count)
            for call in commands.call_args_list:
                self.assertEqual("0", call.kwargs["env"]["GIT_OPTIONAL_LOCKS"])
                self.assertEqual("present", call.kwargs["env"]["STRLING_UNIT_SENTINEL"])

    def test_profile_lsp_build_is_real_isolated_build_check_not_candidate_assemble(
        self,
    ) -> None:
        toolchain = Toolchain.load(ROOT / "toolchain.json")
        _, command = toolchain.resolve_command(toolchain.targets["lsp"], "build")
        self.assertEqual(
            ["python3", "package_extension.py", "build-check", "--target", "auto"],
            command,
        )
        self.assertNotIn("assemble", command)


if __name__ == "__main__":
    unittest.main()
