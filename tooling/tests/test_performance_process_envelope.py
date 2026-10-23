"""Whole-process acquisition: synthetic children, never product samples."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_process_envelope as envelope


class _Fixture(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.exe = Path(sys.executable).resolve()
        self.spec = envelope.Command(
            command=(str(self.exe), "-I", "-B", "-c", "print('fixture')"),
            cwd=self.root,
            environment=dict(os.environ),
            inputs={self.exe: hashlib.sha256(self.exe.read_bytes()).hexdigest()},
            source_sha="a" * 40,
            selected_cpu=1,
            timeout_seconds=10,
        )
        self.events = []


class EnvelopeTests(_Fixture):
    def fake(self, *, fail=None, exit_code=0, change=False):
        owner = self

        class Child:
            def __init__(self, spec, directory):
                self.spec = spec
                owner.events.append("created-suspended")
                (directory / "stdout.bin").write_bytes(b"raw\x00stdout\xff")
                (directory / "stderr.bin").write_bytes(b"raw stderr")

            def step(self, stage):
                owner.events.append(stage)
                if stage == fail:
                    raise OSError(stage)

            def configure(self):
                self.step("configure")
                return {"synthetic": True}

            def resume(self):
                self.step("resume")

            def wait(self, timeout):
                self.step("wait")
                if change:
                    (owner.root / "input").write_bytes(b"changed")
                return exit_code

            def finish(self):
                self.step("finish")
                return dict(
                    total_processes=2,
                    active_processes=0,
                    limit_terminated_processes=0,
                    user_100ns=17,
                    kernel_100ns=9,
                )

            def close(self):
                self.step("close")
                return {"quiescent": True}

        return Child

    def run_fake(self, **kwargs):
        return envelope.capture(
            self.spec, self.root / "receipt", factory=self.fake(**kwargs)
        )

    def test_complete_raw_envelope_no_authority(self):
        result = self.run_fake()
        self.assertEqual(result["status"], "observed")
        self.assertEqual(
            self.events,
            ["created-suspended", "configure", "resume", "wait", "finish", "close"],
        )
        self.assertFalse(result["certification_eligible"])
        self.assertEqual(result["accounting"]["user_100ns"], 17)
        self.assertGreaterEqual(result["whole_action_ns"], 0)
        self.assertEqual(
            (self.root / "receipt" / "stdout.bin").read_bytes(), b"raw\x00stdout\xff"
        )
        self.assertEqual(
            json.loads((self.root / "receipt" / "terminal.json").read_bytes()), result
        )

    def test_every_stage_failure_retains_terminal_and_cleans_up(self):
        for stage in ("configure", "resume", "wait", "finish", "close"):
            with self.subTest(stage=stage):
                result = envelope.capture(
                    self.spec, self.root / stage, factory=self.fake(fail=stage)
                )
                self.assertEqual(result["status"], "failed")
                self.assertIn("close", self.events)
                self.assertTrue((self.root / stage / "terminal.json").is_file())
                if stage == "configure":
                    self.assertNotIn("resume", self.events)
                self.events.clear()

    def test_nonzero_exit_never_observed_success(self):
        self.assertEqual(self.run_fake(exit_code=7)["status"], "failed")

    def test_changed_input_rejects_after_execution(self):
        path = self.root / "input"
        path.write_bytes(b"before")
        self.spec = replace(
            self.spec,
            inputs={**self.spec.inputs, path: hashlib.sha256(b"before").hexdigest()},
        )
        self.assertEqual(self.run_fake(change=True)["status"], "failed")

    def test_replay_never_overwrites(self):
        self.run_fake()
        before = (self.root / "receipt" / "terminal.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_fake()
        self.assertEqual(before, (self.root / "receipt" / "terminal.json").read_bytes())

    def test_bad_inputs_rejected_before_launch(self):
        plans = [
            replace(self.spec, selected_cpu=True),
            replace(self.spec, selected_cpu=64),
            replace(self.spec, timeout_seconds=True),
            replace(self.spec, timeout_seconds=1801),
            replace(self.spec, command=("python",)),
            replace(self.spec, inputs={}),
            replace(self.spec, source_sha="x" * 40),
            replace(self.spec, environment={"PATH": "x", "Path": "y"}),
            replace(self.spec, environment={"bad=x": "value"}),
            replace(self.spec, inputs={self.exe: "0" * 64}),
        ]
        for index, plan in enumerate(plans):
            with self.subTest(index=index), self.assertRaises(ValueError):
                envelope.capture(plan, self.root / str(index), factory=self.fake())
        self.assertEqual(self.events, [])

    def test_launch_failure_preserved(self):
        def fail(*args):
            raise OSError("launch")

        result = envelope.capture(self.spec, self.root / "launch", factory=fail)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("whole_action_ns", result)

    def test_incomplete_accounting_cannot_pass(self):
        for field, value in (
            ("active_processes", 1),
            ("limit_terminated_processes", 1),
            ("total_processes", 0),
            ("user_100ns", -1),
            ("kernel_100ns", True),
        ):
            factory = self.fake()
            original = factory.finish

            def finish(child, field=field, value=value):
                row = original(child)
                row[field] = value
                return row

            factory.finish = finish
            result = envelope.capture(self.spec, self.root / field, factory=factory)
            self.assertEqual(result["status"], "failed")


@unittest.skipUnless(os.name == "nt", "native suspended-process/job APIs")
class NativeEnvelopeTests(_Fixture):
    # Run native-specific methods only, not the inherited fake suite twice.
    def native(self, code, *, timeout=10):
        spec = replace(
            self.spec,
            command=(str(self.exe), "-I", "-B", "-c", code),
            timeout_seconds=timeout,
        )
        return envelope.capture(spec, self.root / "native")

    def test_native_exact_output_and_controls(self):
        self.spec = replace(
            self.spec,
            environment={
                **self.spec.environment,
                "ENVELOPE_TEST": "explicit-environment",
            },
        )
        result = self.native(
            "import os,sys; sys.stdout.buffer.write(b'raw\\x00\\xff'); print(os.environ['ENVELOPE_TEST'],file=sys.stderr)"
        )
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(
            (self.root / "native" / "stdout.bin").read_bytes(), b"raw\x00\xff"
        )
        self.assertEqual(result["controls"]["affinity_mask"], 2)
        self.assertGreaterEqual(result["accounting"]["total_processes"], 1)
        self.assertEqual(result["accounting"]["active_processes"], 0)

    def test_native_exited_grandchild_accounted(self):
        code = "import subprocess,sys; subprocess.run([sys.executable,'-I','-B','-c','sum(i*i for i in range(1000000))'],check=True)"
        result = self.native(code)
        self.assertEqual(result["status"], "observed", result)
        self.assertGreaterEqual(result["accounting"]["total_processes"], 2)
        self.assertGreater(result["accounting"]["user_100ns"], 0)

    def test_native_whole_action_includes_unsampled_sleep(self):
        result = self.native(
            "import time; print('before'); time.sleep(0.25); print('after')"
        )
        self.assertEqual(result["status"], "observed", result)
        self.assertGreaterEqual(result["whole_action_ns"], 250_000_000)

    def test_native_timeout_cleans_owned_job(self):
        result = self.native("import time; time.sleep(20)", timeout=1)
        self.assertEqual(result["status"], "failed")
        self.assertIn("TimeoutError", result["error"])
        self.assertTrue(result["cleanup"]["quiescent"])

    def test_native_surviving_descendant_fails(self):
        result = self.native(
            "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(20)'])",
            timeout=1,
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("TimeoutError", result["error"])
        self.assertTrue(result["cleanup"]["quiescent"])

    def test_native_nonzero_exit_retained(self):
        result = self.native("raise SystemExit(7)")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 7)

    def test_native_control_failure_never_executes_child(self):
        marker = self.root / "must-not-exist"
        with patch.object(
            envelope._Native, "configure", side_effect=OSError("control failed")
        ):
            result = self.native(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')"
            )
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanup"]["quiescent"])
        self.assertFalse(marker.exists())

    def test_native_assignment_failure_never_executes_child(self):
        marker = self.root / "must-not-exist"
        with patch.object(
            envelope._Job, "assign", side_effect=OSError("assignment failed")
        ):
            result = self.native(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')"
            )
        self.assertEqual(result["status"], "failed")
        cleanup = json.loads(
            (self.root / "native" / "launch-cleanup.json").read_bytes()
        )
        self.assertTrue(cleanup["quiescent"])
        self.assertFalse(marker.exists())

    def test_native_job_affinity_cannot_be_widened(self):
        result = self.native(
            "import ctypes as c; k=c.WinDLL('kernel32',use_last_error=True); k.GetCurrentProcess.restype=c.c_void_p; k.SetProcessAffinityMask.argtypes=[c.c_void_p,c.c_size_t]; k.GetProcessAffinityMask.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p]; h=k.GetCurrentProcess(); k.SetProcessAffinityMask(h,3); a=c.c_size_t(); b=c.c_size_t(); assert k.GetProcessAffinityMask(h,c.byref(a),c.byref(b)); print(a.value); assert a.value==2"
        )
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual((self.root / "native" / "stdout.bin").read_text().strip(), "2")

    def test_native_unrelated_inheritable_handle_not_leaked(self):
        import ctypes as c

        k = c.WinDLL("kernel32", use_last_error=True)
        k.CreateEventW.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_wchar_p]
        k.CreateEventW.restype = c.c_void_p
        k.WaitForSingleObject.argtypes = [c.c_void_p, c.c_uint32]
        k.CloseHandle.argtypes = [c.c_void_p]
        handle = k.CreateEventW(None, True, False, None)
        self.assertTrue(handle)
        try:
            os.set_handle_inheritable(handle, True)
            result = self.native(
                f"import ctypes as c; k=c.WinDLL('kernel32'); k.SetEvent.argtypes=[c.c_void_p]; print(k.SetEvent(c.c_void_p({handle})))"
            )
            self.assertEqual(result["status"], "observed", result)
            self.assertEqual(k.WaitForSingleObject(handle, 0), 258)
            self.assertEqual(
                (self.root / "native" / "stdout.bin").read_text().strip(), "0"
            )
        finally:
            k.CloseHandle(handle)

    def test_native_missing_completion_is_not_silent_success(self):
        class LostNotification(envelope._Native):
            def finish(child):
                with (
                    patch.object(child.k, "GetQueuedCompletionStatus", return_value=0),
                    patch.object(child.job, "active", return_value=1),
                ):
                    return super(LostNotification, child).finish()

        result = envelope.capture(
            self.spec, self.root / "native", factory=LostNotification
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("completion unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
