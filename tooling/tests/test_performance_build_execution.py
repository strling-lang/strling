"""Owned concurrent build execution; all fixtures are sample-free."""

from __future__ import annotations

import json
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_build_execution as execution
from tooling import performance_resource_certification as performance


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.events = []
        self.now = 0.0
        self.specs = [
            execution.Build(
                ("fixture", str(i)), self.root, {}, {str(i): self.root / str(i)}
            )
            for i in range(3)
        ]

    def run_case(
        self,
        *,
        fail=None,
        launch_error=None,
        poll_error=None,
        cancel_error=None,
        timeout=False,
        interrupt=False,
    ):
        owner = self

        class Worker:
            def __init__(self, spec, directory):
                self.index = int(spec.command[1])
                self.count = 0
                owner.events.append(("launch", self.index))
                if self.index == launch_error:
                    raise OSError("launch fixture")

            def poll(self):
                owner.events.append(("poll", self.index))
                if self.index == poll_error:
                    raise OSError("poll fixture")
                if interrupt:
                    raise KeyboardInterrupt
                self.count += 1
                if timeout or self.count < (3 - self.index):
                    return None
                return {
                    "status": "failed" if self.index == fail else "passed",
                    "return_code": 7 if self.index == fail else 0,
                }

            def cancel(self):
                owner.events.append(("cancel", self.index))
                if self.index == cancel_error:
                    raise OSError("cleanup fixture")
                return {"quiescent": True}

        def sleep(seconds):
            self.now += 2000 if timeout else seconds

        return execution.execute(
            self.specs,
            self.root / "receipt",
            launch=Worker,
            monotonic=lambda: self.now,
            sleep=sleep,
        )

    def test_all_launch_before_poll_and_results_keep_command_order(self):
        status, details = self.run_case()
        self.assertEqual("passed", status)
        self.assertEqual([("launch", i) for i in range(3)], self.events[:3])
        self.assertEqual(
            [list(s.command) for s in self.specs],
            [r["command"] for r in details["steps"]],
        )
        self.assertEqual(["passed"] * 3, [r["status"] for r in details["steps"]])
        self.assertEqual(
            details, json.loads((self.root / "receipt/terminal.json").read_bytes())
        )

    def test_each_failed_command_is_retained_and_peers_cancelled(self):
        for index in range(3):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as name:
                self.root = Path(name).resolve()
                self.events = []
                status, result = self.run_case(fail=index)
                self.assertEqual("failed", status)
                self.assertEqual(7, result["steps"][index]["return_code"])
                self.assertEqual(
                    {0, 1, 2}, {i for action, i in self.events if action == "cancel"}
                )

    def test_launch_failure_retains_unstarted_denominator_and_cleans_prefix(self):
        status, result = self.run_case(launch_error=1)
        self.assertEqual("failed", status)
        self.assertEqual(3, len(result["steps"]))
        self.assertEqual("incomplete", result["steps"][2]["status"])
        self.assertIn(("cancel", 0), self.events)
        self.assertNotIn(("launch", 2), self.events)

    def test_poll_error_cancels_all_owned_workers(self):
        status, result = self.run_case(poll_error=0)
        self.assertEqual("failed", status)
        self.assertIn("poll fixture", result["error"])
        self.assertEqual(3, len([e for e in self.events if e[0] == "cancel"]))

    def test_cleanup_error_never_stops_other_cleanup_or_passes(self):
        status, result = self.run_case(fail=2, cancel_error=0)
        self.assertEqual("failed", status)
        self.assertIn("cleanup fixture", result["cleanup"][0]["error"])
        self.assertEqual(3, len(result["cleanup"]))

    def test_envelope_timeout_is_bounded_and_not_retried(self):
        status, result = self.run_case(timeout=True)
        self.assertEqual("failed", status)
        self.assertIn("timeout", result["error"])
        self.assertEqual(3, len([e for e in self.events if e[0] == "launch"]))

    def test_interruption_preserved_and_all_owned_workers_cleaned(self):
        status, result = self.run_case(interrupt=True)
        self.assertEqual("failed", status)
        self.assertIn("KeyboardInterrupt", result["error"])
        self.assertEqual(3, len(result["cleanup"]))

    def test_existing_receipt_is_not_overwritten_or_retried(self):
        self.run_case()
        old = (self.root / "receipt/terminal.json").read_bytes()
        self.events = []
        with self.assertRaises(FileExistsError):
            self.run_case()
        self.assertEqual([], self.events)
        self.assertEqual(old, (self.root / "receipt/terminal.json").read_bytes())

    def test_invalid_plan_never_launches(self):
        for specs in ([], self.specs * 2, [self.specs[0]] * 2):
            with (
                self.subTest(specs=specs),
                patch.object(execution, "NativeBuild") as launch,
            ):
                with self.assertRaises(ValueError):
                    execution.execute(specs, self.root / "unused")
                launch.assert_not_called()


@unittest.skipUnless(os.name == "nt", "native Windows job API integration")
class NativeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def invoke(self, code, *, timeout=1800):
        spec = execution.Build(
            (sys.executable, "-B", "-c", code),
            self.root,
            os.environ.copy(),
            {"fixture": self.root / "out.bin"},
            timeout,
        )
        return execution.execute([spec], self.root / "receipt")

    def test_actual_worker_and_output(self):
        status, result = self.invoke(
            "from pathlib import Path; Path('out.bin').write_bytes(b'fixture')"
        )
        self.assertEqual("passed", status, result)
        row = result["steps"][0]
        self.assertEqual([], row["retirement"]["snapshots"][-1]["pids"])
        self.assertEqual(
            row["retirement"]["artifacts_before"], row["retirement"]["artifacts_after"]
        )
        self.assertTrue(row["child_exit"]["exited_before_query"])

    def test_actual_child_failure(self):
        status, result = self.invoke("raise SystemExit(7)")
        self.assertEqual("failed", status)
        self.assertEqual(7, result["steps"][0]["return_code"])
        self.assertTrue(result["cleanup"][0]["quiescent"])

    def test_missing_tool_remains_unavailable(self):
        spec = execution.Build(
            (str(self.root / "missing.exe"),),
            self.root,
            os.environ.copy(),
            {"fixture": self.root / "out.bin"},
        )
        status, result = execution.execute([spec], self.root / "receipt")
        self.assertEqual("unavailable", status, result)
        self.assertEqual("unavailable", result["steps"][0]["status"])
        self.assertTrue(result["cleanup"][0]["quiescent"])

    def test_missing_output(self):
        status, result = self.invoke("pass")
        self.assertEqual("failed", status)
        self.assertEqual("missing-release-artifacts", result["steps"][0]["code"])

    def test_actual_timeout(self):
        status, result = self.invoke("import time; time.sleep(30)", timeout=1)
        self.assertEqual("failed", status)
        self.assertIn("TimeoutExpired", result["steps"][0]["error"])
        self.assertTrue(result["cleanup"][0]["quiescent"])

    def test_unknown_survivor_fails_then_owned_cleanup_drains(self):
        status, result = self.invoke(
            "import subprocess,sys; from pathlib import Path; Path('out.bin').write_bytes(b'fixture'); "
            "subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(30)'],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
        )
        self.assertEqual("failed", status)
        self.assertEqual("failed", result["steps"][0]["retirement"]["status"])
        self.assertTrue(result["cleanup"][0]["quiescent"])

    def test_unassigned_worker_eof_never_runs_command(self):
        import subprocess

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "tooling.performance_build_execution",
                "--worker",
                str(self.root),
            ],
            cwd=execution.ROOT,
            input=b"",
            capture_output=True,
            timeout=10,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse((self.root / "result.json").exists())
        self.assertFalse((self.root / "command.stdout.log").exists())

    def test_three_native_commands_overlap_without_serial_fallback(self):
        specs = []
        for i in range(3):
            code = (
                "from pathlib import Path; import time; "
                f"Path('started-{i}').touch(); "
                "deadline=time.monotonic()+10\n"
                "while len(list(Path('.').glob('started-*'))) != 3:\n"
                " assert time.monotonic()<deadline, 'all three must overlap'\n"
                " time.sleep(.05)\n"
                f"Path('out-{i}').write_bytes(b'concurrent fixture')"
            )
            specs.append(
                execution.Build(
                    (sys.executable, "-B", "-c", code),
                    self.root,
                    os.environ.copy(),
                    {str(i): self.root / f"out-{i}"},
                    15,
                )
            )
        status, result = execution.execute(specs, self.root / "receipt")
        self.assertEqual("passed", status, result)
        self.assertLess(
            max(r["launch_ns"] for r in result["steps"]),
            min(r["return_ns"] for r in result["steps"]),
        )
        self.assertTrue(all(c["quiescent"] for c in result["cleanup"]))

    def test_tiny_locked_offline_cargo_retains_artifacts_and_drains(self):
        cargo = shutil.which("cargo")
        self.assertIsNotNone(
            cargo, "native lifecycle integration requires governed Cargo"
        )
        (self.root / "src").mkdir()
        (self.root / "Cargo.toml").write_text(
            '[package]\nname="owned-build-fixture"\nversion="0.0.0"\nedition="2021"\npublish=false\n'
            '[workspace]\n[profile.release]\ncodegen-units=1\nlto="thin"\n',
            encoding="utf-8",
        )
        (self.root / "Cargo.lock").write_text(
            'version = 3\n\n[[package]]\nname = "owned-build-fixture"\nversion = "0.0.0"\n',
            encoding="utf-8",
        )
        (self.root / "src/main.rs").write_text(
            'fn main() { println!("fixture"); }\n', encoding="utf-8"
        )
        command = (
            cargo,
            "+1.75.0",
            "build",
            "--release",
            "--manifest-path",
            str(self.root / "Cargo.toml"),
            "--locked",
            "--offline",
        )
        spec = execution.Build(
            command,
            self.root,
            performance._resolved_environment(["cargo"], root=self.root),
            {"fixture": self.root / "target/release/owned-build-fixture.exe"},
        )
        status, result = execution.execute([spec], self.root / "receipt")
        self.assertEqual("passed", status, result)
        retired = result["steps"][0]["retirement"]
        self.assertEqual(retired["artifacts_before"], retired["artifacts_after"])
        self.assertEqual([], retired["snapshots"][-1]["pids"])


class ControllerIntegrationTests(unittest.TestCase):
    def invoke(self, *, failed=False, omit=None):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            cleaned = []

            @contextmanager
            def canonical(path):
                self.assertEqual(root, path)
                try:
                    yield root
                finally:
                    cleaned.append(True)

            def execute(specs, directory):
                self.assertEqual(3, len(specs))
                self.assertEqual(
                    [{"runner", "memory_worker"}, {"kernel"}, {"interop"}],
                    [set(s.artifacts) for s in specs],
                )
                expected = [
                    [
                        "cargo",
                        "+1.75.0",
                        "build",
                        "--release",
                        "--manifest-path",
                        str(
                            performance.RUNNER_MANIFEST_PATH.relative_to(
                                performance.ROOT
                            )
                        ),
                        "--locked",
                        "--offline",
                    ],
                    [
                        "cargo",
                        "+1.75.0",
                        "build",
                        "--release",
                        "--manifest-path",
                        "core/internal/Cargo.toml",
                        "--locked",
                        "--offline",
                        "--bin",
                        "strling-kernel",
                    ],
                    [
                        "cargo",
                        "+1.75.0",
                        "build",
                        "--release",
                        "--manifest-path",
                        "bindings/interop/Cargo.toml",
                        "--locked",
                        "--offline",
                        "--lib",
                    ],
                ]
                self.assertEqual(
                    [performance._resolved_command(c) for c in expected],
                    [list(s.command) for s in specs],
                )
                for spec, command in zip(specs, expected):
                    self.assertEqual(1800, spec.timeout_seconds)
                    self.assertEqual(root, spec.cwd)
                    self.assertEqual(
                        performance._resolved_environment(command, root=root),
                        spec.environment,
                    )
                    for role, path in spec.artifacts.items():
                        if role != omit:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(b"explicit mock build output")
                status = "failed" if failed else "passed"
                return status, {
                    "status": status,
                    "steps": [{"status": status}],
                    "receipt_directory": str(directory),
                    "cleanup": [{"quiescent": not failed}],
                }

            with (
                patch.object(performance.platform, "system", return_value="Windows"),
                patch.object(performance, "_canonical_build_root", canonical),
                patch.object(execution, "execute", side_effect=execute),
                patch.object(performance, "_run_command") as serial,
                patch.object(
                    performance.performance_windows,
                    "enforce_current_process_power_policy",
                ),
                patch.object(
                    performance, "_enforce_governed_cpu_affinity", return_value=[1]
                ) as pin,
            ):
                status, details = performance._build_and_enforce_measurement_affinity(
                    {}, root=root
                )
            serial.assert_not_called()
            self.assertEqual([True], cleaned)
            self.assertEqual(1 if status == "passed" else 0, pin.call_count)
            return status, details

    def test_exact_three_commands_roles_environments_and_order(self):
        status, details = self.invoke()
        self.assertEqual("passed", status)
        self.assertIn("execution", details)
        self.assertEqual({"runner", "kernel", "interop"}, set(details["artifacts"]))

    def test_failed_execution_prevents_bundle_and_measurement(self):
        status, details = self.invoke(failed=True)
        self.assertEqual("failed", status)
        self.assertNotIn("artifacts", details)
        self.assertFalse(details["cleanup"][0]["quiescent"])

    def test_final_artifact_recheck_remains(self):
        status, details = self.invoke(omit="kernel")
        self.assertEqual("failed", status)
        self.assertEqual(1, len(details["missing_artifacts"]))


if __name__ == "__main__":
    unittest.main()
