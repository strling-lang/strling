"""Whole-process acquisition: synthetic children, never product samples."""

from dataclasses import replace
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tooling import performance_process_envelope as envelope
from tooling import performance_envelope_receipts as reader


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
    def test_job_wait_rechecks_accounting_after_bounded_timeout(self):
        child = envelope._Native.__new__(envelope._Native)
        child.directory, child.port, child.events = self.root, 17, []
        child.deadline = 10.0
        active = iter((1, 1, 0))
        child.job = SimpleNamespace(active=lambda: next(active))
        waits = []

        def timeout(port, message, key, pid, milliseconds):
            waits.append(milliseconds)
            return 0

        child.k = SimpleNamespace(GetQueuedCompletionStatus=timeout)
        with (
            patch.object(envelope.time, "monotonic", return_value=1.0),
            patch.object(envelope.c, "get_last_error", return_value=258, create=True),
        ):
            child.await_job_exit()
        self.assertEqual(waits, [100, 100])
        self.assertEqual([e["kind"] for e in child.events], ["wait-timeout"] * 2)

    def test_job_wait_never_accepts_post_deadline_empty_job(self):
        child = envelope._Native.__new__(envelope._Native)
        child.directory, child.port, child.events = self.root, 17, []
        child.deadline = 10.0
        child.job = SimpleNamespace(active=lambda: 0, snapshot=lambda: {"active": 0})
        with patch.object(envelope.time, "monotonic", return_value=10.0):
            with self.assertRaisesRegex(TimeoutError, "deadline"):
                child.await_job_exit()
        self.assertTrue((self.root / "survivors.json").exists())

    def fake(self, *, fail=None, exit_code=0, change=False):
        owner = self

        class Child:
            def __init__(self, spec, directory):
                self.spec = spec
                self.directory = directory
                owner.events.append("created-suspended")
                (directory / "stdout.bin").write_bytes(b"raw\x00stdout\xff")
                (directory / "stderr.bin").write_bytes(b"raw stderr")
                envelope._save(
                    directory / "suspended.json",
                    dict(
                        pid=17,
                        birth="1000",
                        exit="0",
                        kernel=0,
                        user=0,
                        exited_before_query=False,
                    ),
                )

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
                envelope._save(
                    self.directory / "root-exit.json",
                    dict(
                        pid=17,
                        birth="1000",
                        exit="2000",
                        kernel=9,
                        user=17,
                        exited_before_query=True,
                    ),
                )
                envelope._save(self.directory / "lifecycle-wakeups.json", [])
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

    def test_identity_and_lifecycle_bytes_are_bound(self):
        result = self.run_fake()
        self.assertEqual(result["contract"], "unqualified-process-tree-envelope-v2")
        self.assertEqual(
            set(result["artifacts"]),
            {"suspended.json", "root-exit.json", "lifecycle-wakeups.json"},
        )
        for name, pin in result["artifacts"].items():
            data = (self.root / "receipt" / name).read_bytes()
            self.assertEqual(
                pin, dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            )

    def test_missing_identity_snapshot_retains_failed_terminal(self):
        factory = self.fake()
        original = factory.close

        def close(child):
            value = original(child)
            (child.directory / "root-exit.json").unlink()
            return value

        factory.close = close
        result = envelope.capture(self.spec, self.root / "missing", factory=factory)
        self.assertEqual(result["status"], "failed")
        self.assertIn("artifact", result["artifact_error"])
        self.assertEqual(
            json.loads((self.root / "missing/terminal.json").read_bytes()), result
        )

    def test_snapshot_sealing_error_retains_failure_and_other_pins(self):
        original = envelope._hash

        def fail(path):
            if path.name == "suspended.json":
                raise OSError("fixture read failure")
            return original(path)

        with patch.object(envelope, "_hash", side_effect=fail):
            result = self.run_fake()
        self.assertEqual(result["status"], "failed")
        self.assertIn("root-exit.json", result["artifacts"])
        self.assertIn("stdout.bin", result["logs"])
        self.assertIn("fixture read failure", result["artifact_error"])

    def test_same_size_artifact_change_during_sealing_fails(self):
        original = envelope._hash

        def change(path):
            value = original(path)
            if path.name == "stdout.bin":
                path.write_bytes(b"X" * path.stat().st_size)
                os.utime(path, ns=(1, 1))
            return value

        with patch.object(envelope, "_hash", side_effect=change):
            result = self.run_fake()
        self.assertEqual(result["status"], "failed")
        self.assertIn("changed during sealing", result["artifact_error"])

    def test_hardlinked_artifact_fails_without_deleting_either_file(self):
        factory = self.fake()
        original = factory.close

        def close(child):
            value = original(child)
            os.link(child.directory / "stdout.bin", owner.root / "alias.bin")
            return value

        owner = self
        factory.close = close
        result = envelope.capture(self.spec, self.root / "linked", factory=factory)
        self.assertEqual(result["status"], "failed")
        self.assertIn("regular unlinked", result["artifact_error"])
        self.assertTrue((self.root / "alias.bin").is_file())
        self.assertTrue((self.root / "linked/stdout.bin").is_file())

    def test_failure_only_auxiliary_artifacts_remain_pinned(self):
        factory = self.fake(exit_code=7)
        original = factory.close

        def close(child):
            value = original(child)
            envelope._save(child.directory / "survivors.json", {"fixture": True})
            return value

        factory.close = close
        result = envelope.capture(self.spec, self.root / "failed", factory=factory)
        self.assertEqual(result["status"], "failed")
        data = (self.root / "failed/survivors.json").read_bytes()
        self.assertEqual(
            result["artifacts"]["survivors.json"],
            dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)),
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
        directory = self.root / "native"
        expected = dict(
            command=list(spec.command),
            cwd=str(spec.cwd),
            source_sha=spec.source_sha,
            inputs={str(p): h for p, h in spec.inputs.items()},
            environment_sha256=hashlib.sha256(
                json.dumps(spec.environment, sort_keys=True).encode()
            ).hexdigest(),
            selected_cpu=spec.selected_cpu,
            timeout_seconds=spec.timeout_seconds,
        )
        for key, module in (
            ("implementation_sha256", envelope),
            ("controls_implementation_sha256", envelope.windows),
            ("observation_implementation_sha256", envelope.observation),
        ):
            expected[key] = hashlib.sha256(
                Path(module.__file__).read_bytes()
            ).hexdigest()
        expected["job_implementation_sha256"] = hashlib.sha256(
            Path(envelope.__file__)
            .with_name("performance_build_execution.py")
            .read_bytes()
        ).hexdigest()
        result = envelope.capture(spec, directory)
        terminal_pin = hashlib.sha256(
            (directory / "terminal.json").read_bytes()
        ).hexdigest()
        if result["status"] == "observed":
            files = {name: (directory / name).read_bytes() for name in reader.FILES}
            verified = reader.verify_process_receipt(files, terminal_pin, expected)
            self.assertEqual(verified["whole_action_ns"], result["whole_action_ns"])
            self.assertFalse(verified["certification_eligible"])
        else:
            for group in ("logs", "artifacts"):
                for name, pin in result[group].items():
                    data = (directory / name).read_bytes()
                    self.assertEqual(
                        pin,
                        dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)),
                    )
        return result

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
                def unavailable(*args):
                    ctypes.set_last_error(6)  # Invalid handle, not a normal timeout.
                    return 0

                with (
                    patch.object(
                        child.k, "GetQueuedCompletionStatus", side_effect=unavailable
                    ),
                    patch.object(child.job, "active", return_value=1),
                ):
                    return super(LostNotification, child).finish()

        result = envelope.capture(
            self.spec, self.root / "native", factory=LostNotification
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("completion unavailable", result["error"])

    def test_native_lost_wakeups_still_observe_natural_whole_job_exit(self):
        class LostWakeups(envelope._Native):
            def finish(child):
                def lost(port, message, key, pid, milliseconds):
                    time.sleep(milliseconds / 1000)
                    ctypes.set_last_error(258)
                    return 0

                with patch.object(
                    child.k, "GetQueuedCompletionStatus", side_effect=lost
                ):
                    return super(LostWakeups, child).finish()

        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(0.3)'])"
        result = envelope.capture(
            replace(self.spec, command=(str(self.exe), "-I", "-B", "-c", code)),
            self.root / "native",
            factory=LostWakeups,
        )
        self.assertEqual(result["status"], "observed", result)
        self.assertFalse(result["cleanup"]["terminated"])
        events = json.loads((self.root / "native/lifecycle-wakeups.json").read_bytes())
        self.assertTrue(any(e["kind"] == "wait-timeout" for e in events))
        self.assertTrue(all(e["wait_milliseconds"] <= 100 for e in events))
        self.assertEqual(result["accounting"]["active_processes"], 0)

    def test_native_lost_wakeups_do_not_excuse_live_descendants(self):
        class LostWakeups(envelope._Native):
            def finish(child):
                def lost(port, message, key, pid, milliseconds):
                    time.sleep(milliseconds / 1000)
                    ctypes.set_last_error(258)
                    return 0

                with patch.object(
                    child.k, "GetQueuedCompletionStatus", side_effect=lost
                ):
                    return super(LostWakeups, child).finish()

        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(20)'])"
        result = envelope.capture(
            replace(
                self.spec,
                timeout_seconds=1,
                command=(str(self.exe), "-I", "-B", "-c", code),
            ),
            self.root / "native",
            factory=LostWakeups,
        )
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("deadline", result["error"])
        self.assertTrue(result["cleanup"]["quiescent"])
        events = json.loads((self.root / "native/lifecycle-wakeups.json").read_bytes())
        self.assertTrue(events)
        self.assertTrue(all(e["kind"] == "wait-timeout" for e in events))


if __name__ == "__main__":
    unittest.main()
