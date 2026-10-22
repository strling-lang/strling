from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_resource_certification as performance


class PerformanceBuildArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.paths = {
            **performance._release_artifacts(self.root),
            "memory_worker": performance._memory_worker_artifact(self.root),
        }
        self.groups = (("runner", "memory_worker"), ("kernel",), ("interop",))
        self.calls = []
        self.cleaned = False

    def materialize(self, role):
        path = self.paths[role]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((role + "-test-fixture").encode())

    def invoke(
        self, *, omit=(), directory=(), failure=None, remove_later=None, gate=False
    ):
        @contextmanager
        def canonical(root):
            self.assertEqual(root, self.root)
            try:
                yield root
            finally:
                self.cleaned = True

        def command(argv, *, root, timeout_seconds):
            index = len(self.calls)
            self.calls.append(list(argv))
            self.assertEqual(root, self.root)
            self.assertEqual(timeout_seconds, 1800)
            self.assertEqual(argv[:4], ["cargo", "+1.75.0", "build", "--release"])
            self.assertIn("--locked", argv)
            self.assertIn("--offline", argv)
            for role in self.groups[index]:
                if role in directory:
                    self.paths[role].mkdir(parents=True, exist_ok=True)
                elif role not in omit:
                    self.materialize(role)
            if index == 2 and remove_later is not None:
                self.paths[remove_later].unlink()
            status = failure if failure is not None else "passed"
            return status, {
                "command": list(argv),
                "return_code": 0 if status == "passed" else None,
            }

        with (
            patch.object(performance, "_canonical_build_root", canonical),
            patch.object(performance, "_run_command", side_effect=command),
            patch.object(
                performance.performance_windows, "enforce_current_process_power_policy"
            ),
            patch.object(performance, "_enforce_governed_cpu_affinity") as placement,
        ):
            result = (
                performance._build_and_enforce_measurement_affinity({}, root=self.root)
                if gate
                else performance._build_release_artifacts(self.root)
            )
        self.placement_calls = placement.call_count
        self.assertTrue(self.cleaned)
        return result

    def test_all_outputs_keep_complete_success_and_original_commands(self):
        status, details = self.invoke()
        self.assertEqual(status, "passed")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(
            self.calls[0][4:],
            [
                "--manifest-path",
                str(performance.RUNNER_MANIFEST_PATH.relative_to(performance.ROOT)),
                "--locked",
                "--offline",
            ],
        )
        self.assertEqual(
            self.calls[1][4:],
            [
                "--manifest-path",
                "core/internal/Cargo.toml",
                "--locked",
                "--offline",
                "--bin",
                "strling-kernel",
            ],
        )
        self.assertEqual(
            self.calls[2][4:],
            [
                "--manifest-path",
                "bindings/interop/Cargo.toml",
                "--locked",
                "--offline",
                "--lib",
            ],
        )
        self.assertEqual([s["status"] for s in details["steps"]], ["passed"] * 3)
        for row in details["artifacts"].values():
            raw = (self.root / row["path"]).read_bytes()
            self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row["bytes"], len(raw))
        bundle = json.loads(
            (self.root / details["artifacts"]["runner"]["path"]).read_bytes()
        )
        self.assertEqual(
            [a["role"] for a in bundle["artifacts"]],
            ["measurement-runner", "peak-rss-worker"],
        )

    def assert_missing(self, roles, expected_commands, **kwargs):
        status, details = self.invoke(omit=roles, **kwargs)
        self.assertEqual(status, "failed")
        self.assertEqual(len(self.calls), expected_commands)
        self.assertEqual(details["steps"][-1]["status"], "failed")
        self.assertEqual(details["steps"][-1]["code"], "missing-release-artifacts")
        self.assertCountEqual(
            details["steps"][-1]["missing_artifacts"],
            [str(self.paths[r]) for r in roles],
        )
        self.assertFalse(
            (
                self.paths["runner"].parent / "strling-performance-runner-bundle.json"
            ).exists()
        )

    def test_missing_runner_stops_first(self):
        self.assert_missing(("runner",), 1)

    def test_missing_memory_worker_stops_first(self):
        self.assert_missing(("memory_worker",), 1)

    def test_missing_kernel_stops_second(self):
        self.assert_missing(("kernel",), 2)

    def test_missing_interop_stops_third(self):
        self.assert_missing(("interop",), 3)

    def test_all_missing_first_outputs_retained(self):
        self.assert_missing(("runner", "memory_worker"), 1)

    def test_directory_does_not_satisfy_required_file(self):
        self.assert_missing(("memory_worker",), 1, directory=("memory_worker",))

    def test_missing_outputs_never_reach_measurement_pin(self):
        self.assert_missing(("runner",), 1, gate=True)
        self.assertEqual(self.placement_calls, 0)

    def test_command_failure_not_hidden_by_existing_artifacts(self):
        for role in self.paths:
            self.materialize(role)
        status, details = self.invoke(failure="failed")
        self.assertEqual(status, "failed")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(details["steps"][0]["return_code"], None)

    def test_unavailable_command_not_reclassified_by_missing_outputs(self):
        status, details = self.invoke(omit=tuple(self.paths), failure="unavailable")
        self.assertEqual(status, "unavailable")
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("code", details["steps"][0])

    def test_final_recheck_rejects_removed_earlier_output(self):
        status, details = self.invoke(remove_later="runner")
        self.assertEqual(status, "failed")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(details["missing_artifacts"], [str(self.paths["runner"])])


if __name__ == "__main__":
    unittest.main()
