"""Boundary checks for opt-in diagnostic runner-body instrumentation."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/certification/performance-resource/1.0/runner/src/main.rs"


class PhaseTimelineBoundaryTests(unittest.TestCase):
    def test_missing_windows_cpu_fails_before_work(self):
        runner = RUNNER.read_text(encoding="utf-8")
        run = runner.split("fn run()", 1)[1].split("fn run_inherited_memory_parent", 1)[
            0
        ]
        guard = (
            'if cfg!(target_os = "windows") && arguments.expected_logical_cpu.is_none()'
        )
        self.assertTrue(guard in run, "Windows missing-CPU guard is absent")
        self.assertLess(run.index(guard), run.index("let mut phase_timeline"))
        self.assertLess(run.index(guard), run.index("materialize_fixture("))
        self.assertIn(
            "verify_execution_resource(&execution_resource, arguments.expected_logical_cpu)?",
            run,
        )

    def test_sidecar_is_explicit_and_exclusive(self):
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--diagnostic-phase-log"', runner)
        self.assertIn("phase_timeline::validate_selection", runner)
        self.assertIn("phase_timeline::Timeline::open", runner)

    def test_all_phase_boundaries_outside_measure_closure(self):
        runner = RUNNER.read_text(encoding="utf-8")
        for phase in (
            "preparation",
            "primary-warmups",
            "sample-setup",
            "control-warmups",
            "measurement",
            "post-measurement",
            "serialization",
        ):
            self.assertIn(
                f'phase_timeline::close(&mut phase_timeline, "{phase}")?', runner
            )
        closure = runner.split("let mut measure =", 1)[1].split(
            "if let Some(control) = &control_operation", 1
        )[0]
        self.assertNotIn("phase_timeline", closure)

    def test_original_stdout_does_not_gain_diagnostic_authority(self):
        runner = RUNNER.read_text(encoding="utf-8")
        result = runner.split("let mut result = json!({", 1)[1].split("Ok(())", 1)[0]
        self.assertNotIn('result["phase', result)
        self.assertNotIn('result["diagnostic', result)
        self.assertIn("timeline.finish()", result)


if __name__ == "__main__":
    unittest.main()
