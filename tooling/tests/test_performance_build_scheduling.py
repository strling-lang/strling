from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import ast
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tooling import performance_resource_certification as performance


class MeasurementBoundaryReached(Exception):
    """Stop a mocked Full before any environment acquisition or sampling."""


class PerformanceBuildSchedulingTests(unittest.TestCase):
    def run_full_prefix(self, *, failure: str | None = None) -> list[str]:
        events: list[str] = []
        baseline = performance.load_json(performance.BASELINE_PATH)
        manifest = performance.load_json(performance.MANIFEST_PATH)
        selected = manifest["measurement_policy"]["selected_logical_cpu"]

        def probe(*args, **kwargs):
            events.append("isolated-probe")
            if failure == "probe":
                raise performance.PerformanceResourceError("affinity-control", "probe")
            return [selected]

        def build(*args, **kwargs):
            events.append("build")
            if failure == "build":
                return "failed", {"reason": "compiler"}
            return "passed", {"artifacts": baseline["artifact_fingerprints"]}

        def pin(*args, **kwargs):
            events.append("measurement-pin")
            if failure == "pin":
                raise performance.PerformanceResourceError("affinity-control", "pin")
            return [selected]

        def environment(*args, **kwargs):
            events.append("environment")
            if failure == "environment":
                raise performance.PerformanceResourceError(
                    "environment-unavailable", "fixture"
                )
            raise MeasurementBoundaryReached

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    performance.performance_windows,
                    "enforce_current_process_power_policy",
                )
            )
            stack.enter_context(
                patch.object(
                    performance, "validate_repository_contract", return_value={}
                )
            )
            stack.enter_context(
                patch.object(
                    performance, "_git_identity", return_value=("f" * 40, False)
                )
            )
            stack.enter_context(
                patch.object(
                    performance,
                    "_preflight_governed_cpu_affinity",
                    create=True,
                    side_effect=probe,
                )
            )
            stack.enter_context(
                patch.object(performance, "_build_release_artifacts", side_effect=build)
            )
            stack.enter_context(
                patch.object(
                    performance, "_enforce_governed_cpu_affinity", side_effect=pin
                )
            )
            stack.enter_context(
                patch.object(performance, "live_environment", side_effect=environment)
            )
            if failure is None:
                with self.assertRaises(MeasurementBoundaryReached):
                    performance.certify("full")
            else:
                result = performance.certify("full")
                self.last_result = result
                self.assertNotEqual(result["status"], "passed")
        return events

    def test_full_build_is_between_isolated_probe_and_measurement_pin(self):
        self.assertEqual(
            self.run_full_prefix(),
            ["isolated-probe", "build", "measurement-pin", "environment"],
        )

    def test_failed_probe_stops_before_expensive_build(self):
        self.assertEqual(self.run_full_prefix(failure="probe"), ["isolated-probe"])

    def test_failed_build_stops_before_measurement_placement(self):
        self.assertEqual(
            self.run_full_prefix(failure="build"), ["isolated-probe", "build"]
        )

    def test_failed_post_build_pin_stops_before_environment(self):
        self.assertEqual(
            self.run_full_prefix(failure="pin"),
            ["isolated-probe", "build", "measurement-pin"],
        )

    def test_placement_receipt_keeps_exact_attestation_shape_and_order(self):
        self.run_full_prefix(failure="environment")
        selected = performance.load_json(performance.MANIFEST_PATH)[
            "measurement_policy"
        ]["selected_logical_cpu"]
        self.assertEqual(
            self.last_result["checks"][0],
            {
                "id": "environment:single-fixed-logical-cpu",
                "status": "passed",
                "details": {
                    "selected_logical_cpu": selected,
                    "effective_cpu_affinity": [selected],
                    "effective_cpuset": performance._format_cpu_set([selected]),
                },
            },
        )
        self.assertEqual(
            self.last_result["checks"][1]["id"], "build:release-performance-artifacts"
        )

    def test_failed_parent_pin_never_emits_passing_placement_receipt(self):
        self.run_full_prefix(failure="pin")
        self.assertFalse(
            any(
                row["id"] == "environment:single-fixed-logical-cpu"
                and row["status"] == "passed"
                for row in self.last_result["checks"]
            )
        )

    def test_every_build_caller_uses_probe_then_build_then_measurement_gate(self):
        tree = ast.parse(inspect.getsource(performance))
        raw_callers = set()
        guarded_callers = set()
        for function in tree.body:
            if not isinstance(function, ast.FunctionDef):
                continue
            calls = sorted(
                (node.lineno, node.func.id)
                for node in ast.walk(function)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            )
            names = [name for _, name in calls]
            if "_build_release_artifacts" in names:
                raw_callers.add(function.name)
            if "_build_and_enforce_measurement_affinity" in names:
                guarded_callers.add(function.name)
                self.assertLess(
                    names.index("_preflight_governed_cpu_affinity"),
                    names.index("_build_and_enforce_measurement_affinity"),
                )
                self.assertNotIn("_enforce_governed_cpu_affinity", names)
        self.assertEqual(raw_callers, {"_build_and_enforce_measurement_affinity"})
        self.assertEqual(
            guarded_callers,
            {
                "certify",
                "_migrate_cli_launch_control_command",
                "_migrate_cli_normalization_command",
                "_migrate_stationary_warmups_command",
                "_migrate_conditioning_cpu_command",
                "_baseline_command",
                "_qualification_command",
            },
        )


class IsolatedPlacementProbeTests(unittest.TestCase):
    policy = {
        "cpu_affinity_policy": "single-fixed-logical-cpu",
        "selected_logical_cpu": 1,
    }

    @staticmethod
    def execute_probe(command, **kwargs):
        """Execute the production child program with mocked native operations."""
        output = io.StringIO()
        try:
            with patch.object(sys, "argv", ["-c", command[4]]), redirect_stdout(output):
                exec(compile(command[3], "<isolated-probe>", "exec"), {})
        except performance.performance_windows.WindowsQualificationError as error:
            return subprocess.CompletedProcess(
                command, 1, output.getvalue(), str(error)
            )
        return subprocess.CompletedProcess(command, 0, output.getvalue(), "")

    def test_probe_quota_rejection_stops_full_before_placement_and_build(self):
        for observation in (
            {"effective_cpu_quota": "unknown"},
            {"effective_cpu_quota": "limited"},
            performance.performance_windows.WindowsQualificationError("query failed"),
        ):
            with (
                self.subTest(observation=observation),
                patch.object(performance.platform, "system", return_value="Windows"),
                patch.object(
                    performance, "validate_repository_contract", return_value={}
                ),
                patch.object(
                    performance, "_git_identity", return_value=("f" * 40, False)
                ),
                patch.object(
                    performance.subprocess, "run", side_effect=self.execute_probe
                ) as run,
                patch.object(
                    performance.performance_windows,
                    "cpu_quota_state",
                    side_effect=[observation],
                ) as quota,
                patch.object(
                    performance, "_enforce_governed_cpu_affinity", return_value=[1]
                ) as pin,
                patch.object(
                    performance,
                    "_build_and_enforce_measurement_affinity",
                    return_value=("failed", {"reason": "unexpected build"}),
                ) as build,
                patch.object(performance, "live_environment") as environment,
            ):
                result = performance.certify("full")
                self.assertNotEqual(result["status"], "passed")
                quota.assert_called_once_with()
                run.assert_called_once()
                pin.assert_not_called()
                build.assert_not_called()
                environment.assert_not_called()

    def test_probe_unlimited_quota_precedes_placement_without_changing_output(self):
        events = []
        with (
            patch.object(performance.platform, "system", return_value="Windows"),
            patch.object(performance.subprocess, "run", side_effect=self.execute_probe),
            patch.object(
                performance.performance_windows,
                "cpu_quota_state",
                side_effect=lambda: (
                    events.append("quota") or {"effective_cpu_quota": "unlimited"}
                ),
            ),
            patch.object(
                performance,
                "_enforce_governed_cpu_affinity",
                side_effect=lambda manifest: events.append("pin") or [1],
            ),
        ):
            self.assertEqual(
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": self.policy}
                ),
                [1],
            )
        self.assertEqual(events, ["quota", "pin"])

    def test_non_windows_probe_does_not_query_windows_quota(self):
        with (
            patch.object(performance.platform, "system", return_value="Linux"),
            patch.object(performance.subprocess, "run", side_effect=self.execute_probe),
            patch.object(performance.performance_windows, "cpu_quota_state") as quota,
            patch.object(
                performance, "_enforce_governed_cpu_affinity", return_value=[1]
            ) as pin,
        ):
            self.assertEqual(
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": self.policy}
                ),
                [1],
            )
        quota.assert_not_called()
        pin.assert_called_once_with({"measurement_policy": self.policy})

    def test_exact_runtime_bounded_data_only_child_and_no_parent_placement(self):
        root = Path("fixture-root")
        with (
            patch.object(performance.subprocess, "run") as run,
            patch.object(performance, "_enforce_governed_cpu_affinity") as parent_pin,
        ):
            run.return_value = subprocess.CompletedProcess(
                [], 0, '{"effective_cpu_affinity":[1]}', ""
            )
            self.assertEqual(
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": self.policy}, root=root
                ),
                [1],
            )
        parent_pin.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual(command[:3], [sys.executable, "-B", "-c"])
        self.assertEqual(len(command), 5)
        self.assertEqual(json.loads(command[4]), {"measurement_policy": self.policy})
        self.assertIn(
            "_enforce_governed_cpu_affinity(json.loads(sys.argv[1]))", command[3]
        )
        self.assertEqual(
            run.call_args.kwargs,
            {
                "cwd": root,
                "capture_output": True,
                "text": True,
                "check": False,
                "timeout": 30,
            },
        )

    def test_rejects_malformed_wrong_or_ambiguous_probe_results(self):
        outputs = [
            "",
            "noise\n{}",
            "null",
            "[]",
            "{}",
            '{"effective_cpu_affinity":[0]}',
            '{"effective_cpu_affinity":[true]}',
            '{"effective_cpu_affinity":[1.0]}',
            '{"effective_cpu_affinity":[1,2]}',
            '{"effective_cpu_affinity":1}',
            '{"effective_cpu_affinity":[]}',
            '{"effective_cpu_affinity":[1],"extra":true}',
        ]
        for output in outputs:
            with (
                self.subTest(output=output),
                patch.object(
                    performance.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, output, ""),
                ),
                self.assertRaises(performance.PerformanceResourceError) as raised,
            ):
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": self.policy}
                )
            self.assertEqual(raised.exception.code, "affinity-preflight")

    def test_failed_child_cannot_pass_with_valid_stdout(self):
        with (
            patch.object(
                performance.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 1, '{"effective_cpu_affinity":[1]}', "denied"
                ),
            ),
            self.assertRaises(performance.PerformanceResourceError) as raised,
        ):
            performance._preflight_governed_cpu_affinity(
                {"measurement_policy": self.policy}
            )
        self.assertIn("exited 1", str(raised.exception))

    def test_missing_runtime_and_timeout_fail_closed_without_retry(self):
        for failure in (OSError("missing"), subprocess.TimeoutExpired(["python"], 30)):
            with (
                self.subTest(failure=failure),
                patch.object(performance.subprocess, "run", side_effect=failure) as run,
                self.assertRaises(performance.PerformanceResourceError) as raised,
            ):
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": self.policy}
                )
            self.assertEqual(raised.exception.code, "affinity-preflight")
            run.assert_called_once()

    def test_invalid_policy_never_launches_child(self):
        for change in (
            {"selected_logical_cpu": True},
            {"selected_logical_cpu": -1},
            {"selected_logical_cpu": "1"},
            {"selected_logical_cpu": None},
            {"cpu_affinity_policy": "any"},
        ):
            with (
                self.subTest(change=change),
                patch.object(performance.subprocess, "run") as run,
                self.assertRaises(performance.PerformanceResourceError),
            ):
                performance._preflight_governed_cpu_affinity(
                    {"measurement_policy": {**self.policy, **change}}
                )
            run.assert_not_called()


class PostBuildPlacementTests(unittest.TestCase):
    def test_windows_build_retains_high_qos_before_build_then_actual_pin(self):
        events = []
        details = {"artifacts": {"runner": "unchanged"}, "steps": ["all-builds"]}
        manifest = {"measurement_policy": IsolatedPlacementProbeTests.policy}
        with (
            patch.object(performance.platform, "system", return_value="Windows"),
            patch.object(
                performance.performance_windows,
                "enforce_current_process_power_policy",
                side_effect=lambda: events.append("high-qos"),
            ),
            patch.object(
                performance,
                "_build_release_artifacts",
                side_effect=lambda root: (events.append("build") or "passed", details),
            ),
            patch.object(
                performance,
                "_enforce_governed_cpu_affinity",
                side_effect=lambda manifest: events.append("pin") or [1],
            ),
        ):
            status, result = performance._build_and_enforce_measurement_affinity(
                manifest
            )
        self.assertEqual(events, ["high-qos", "build", "pin"])
        self.assertEqual(status, "passed")
        self.assertEqual(result["artifacts"], details["artifacts"])
        self.assertEqual(result["steps"], details["steps"])
        self.assertNotIn("measurement_affinity", details)
        self.assertEqual(
            result["measurement_affinity"],
            {
                "status": "passed",
                "effective_cpu_affinity": [1],
                "scope": "measurement-parent-after-build",
            },
        )

    def test_power_policy_failure_stops_before_build(self):
        with (
            patch.object(performance.platform, "system", return_value="Windows"),
            patch.object(
                performance.performance_windows,
                "enforce_current_process_power_policy",
                side_effect=performance.performance_windows.WindowsQualificationError(
                    "denied"
                ),
            ),
            patch.object(performance, "_build_release_artifacts") as build,
            patch.object(performance, "_enforce_governed_cpu_affinity") as pin,
        ):
            status, result = performance._build_and_enforce_measurement_affinity({})
        self.assertEqual(status, "unavailable")
        self.assertEqual(result["code"], "build-power-policy")
        build.assert_not_called()
        pin.assert_not_called()

    def test_linux_does_not_apply_windows_power_policy(self):
        with (
            patch.object(performance.platform, "system", return_value="Linux"),
            patch.object(
                performance.performance_windows, "enforce_current_process_power_policy"
            ) as power,
            patch.object(
                performance, "_build_release_artifacts", return_value=("passed", {})
            ),
            patch.object(
                performance, "_enforce_governed_cpu_affinity", return_value=[1]
            ) as pin,
        ):
            status, _ = performance._build_and_enforce_measurement_affinity({})
        self.assertEqual(status, "passed")
        power.assert_not_called()
        pin.assert_called_once_with({})


if __name__ == "__main__":
    unittest.main()
