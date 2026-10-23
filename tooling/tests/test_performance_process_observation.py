"""Actual counter journaling must not manufacture continuous isolation proof."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tooling import performance_process_observation as observation


def snapshot(index: int, child: bool) -> dict:
    row = {
        "query_begin_ns": index * 100,
        "query_end_ns": index * 100 + 10,
        "processors": [
            {
                k: index * 10
                for k in (
                    "idle",
                    "kernel",
                    "user",
                    "dpc",
                    "interrupt",
                    "interrupt_count",
                )
            }
            for _ in range(2)
        ],
        "observer": {
            "pid": 2,
            "birth": "20",
            "exit": "0",
            "exited_before_query": False,
            "kernel": index,
            "user": index,
        },
        "child": None,
    }
    if child:
        row["child"] = {
            "pid": 3,
            "birth": "30",
            "exit": "0",
            "exited_before_query": False,
            "kernel": index,
            "user": index,
        }
    return row


class FakeChild:
    pid = 3
    _handle = 123
    returncode = None

    def poll(self):
        return self.returncode


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "timeline.jsonl"
        self.child = FakeChild()
        self.items = [snapshot(1, False), snapshot(2, True), snapshot(3, True)]
        self.items[-1]["child"]["exit"] = "40"
        self.items[-1]["child"]["exited_before_query"] = True

    def reader(self, count, child):
        self.assertEqual(count, 2)
        row = self.items.pop(0)
        self.assertEqual(row["child"] is not None, child is not None)
        return row

    def rows(self):
        return [
            json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()
        ]

    def journal(self):
        return observation.ProcessCounterJournal(self.path, 2, reader=self.reader)

    def test_complete_retains_every_cpu_and_observer(self):
        with self.journal() as journal:
            journal.sample(self.child)
            self.child.returncode = 0
            journal.finish(self.child)
        rows = self.rows()
        self.assertEqual(
            [r["event"] for r in rows],
            ["header", "before-launch", "running", "after-exit", "complete"],
        )
        self.assertEqual(rows[0]["authoritative"], False)
        self.assertEqual(len(rows[2]["snapshot"]["processors"]), 2)
        self.assertEqual(rows[3]["snapshot"]["observer"]["user"], 3)
        self.assertEqual(rows[-1]["exit_code"], 0)

    def test_collision_has_no_native_observation(self):
        self.path.write_bytes(b"prior attempt")
        with self.assertRaises(FileExistsError):
            self.journal()
        self.assertEqual(len(self.items), 3)
        self.assertEqual(self.path.read_bytes(), b"prior attempt")

    def test_running_child_cannot_finish(self):
        with self.assertRaisesRegex(ValueError, "exited"):
            with self.journal() as journal:
                journal.sample(self.child)
                journal.finish(self.child)
        self.assertEqual(self.rows()[-1]["event"], "incomplete")

    def test_finish_requires_prior_child_observation(self):
        with self.assertRaisesRegex(ValueError, "prior"):
            with self.journal() as journal:
                self.child.returncode = 0
                journal.finish(self.child)

    def test_failure_preserves_prefix_and_offending_snapshot(self):
        self.items[1]["processors"][1]["user"] = -1
        with self.assertRaises(ValueError):
            with self.journal() as journal:
                journal.sample(self.child)
        self.assertEqual(self.rows()[-2]["snapshot"]["processors"][1]["user"], -1)
        self.assertEqual(self.rows()[-1]["event"], "incomplete")

    def test_identity_drift_rejected(self):
        self.items[-1]["child"]["birth"] = "31"
        with self.assertRaisesRegex(ValueError, "identity"):
            with self.journal() as journal:
                journal.sample(self.child)
                self.child.returncode = 0
                journal.finish(self.child)

    def test_caught_bad_snapshot_cannot_be_followed_by_complete(self):
        self.items[1]["processors"][0]["user"] = -1
        with self.journal() as journal:
            with self.assertRaises(ValueError):
                journal.sample(self.child)
            with self.assertRaisesRegex(ValueError, "failed"):
                journal.sample(self.child)
        self.assertNotIn("complete", [r["event"] for r in self.rows()])

    def test_counter_or_bracket_drift_rejected(self):
        cases = [
            ("count", None),
            ("regression", None),
            ("bool", None),
            ("overlap", None),
        ]
        for case, _ in cases:
            with self.subTest(case=case):
                before, after = snapshot(1, True), snapshot(2, True)
                if case == "count":
                    after["processors"].pop()
                elif case == "regression":
                    after["processors"][0]["kernel"] = 1
                elif case == "bool":
                    after["child"]["user"] = True
                else:
                    after["query_begin_ns"] = 105
                with self.assertRaises(ValueError):
                    observation.validate_snapshot(after, 2, before)

    def test_interrupt_wrap_preserved_not_normalized(self):
        before, after = snapshot(1, True), snapshot(2, True)
        before["processors"][0]["interrupt_count"] = 2**32 - 1
        after["processors"][0]["interrupt_count"] = 0
        expected = copy.deepcopy(after)
        observation.validate_snapshot(after, 2, before)
        self.assertEqual(after, expected)

    def test_long_gap_and_unfavorable_activity_not_filtered(self):
        before, after = snapshot(1, True), snapshot(20000, True)
        expected = copy.deepcopy(after)
        observation.validate_snapshot(after, 2, before)
        self.assertEqual(after, expected)

    def test_running_exit_field_is_undefined_not_a_failure(self):
        row = snapshot(1, True)
        row["observer"]["exit"] = "12345"
        row["child"]["exit"] = "7890"
        observation.validate_snapshot(row, 2, None)

    def test_missing_exit_time_is_incomplete(self):
        self.items[-1]["child"]["exit"] = "0"
        with self.assertRaisesRegex(ValueError, "exit"):
            with self.journal() as journal:
                journal.sample(self.child)
                self.child.returncode = 0
                journal.finish(self.child)

    def test_nonzero_exit_retained_without_passing_claim(self):
        with self.journal() as journal:
            journal.sample(self.child)
            self.child.returncode = 7
            journal.finish(self.child)
        self.assertEqual(self.rows()[-1]["exit_code"], 7)
        self.assertFalse(self.rows()[-1]["authoritative"])

    def test_native_query_failure_keeps_incomplete_header(self):
        def failed(count, child):
            raise OSError("native query failed")

        with self.assertRaises(OSError):
            observation.ProcessCounterJournal(self.path, 2, reader=failed)
        self.assertEqual([r["event"] for r in self.rows()], ["header", "incomplete"])


class SnapshotHandleTests(unittest.TestCase):
    def setUp(self):
        self.kernel = mock.Mock()
        self.kernel.OpenProcess.return_value = 123
        self.kernel.CloseHandle.return_value = 1
        self.identity = snapshot(1, True)["child"]
        self.native = mock.patch.object(
            observation.live, "_kernel32", return_value=self.kernel
        )
        self.native.start()
        self.addCleanup(self.native.stop)
        times_patch = mock.patch.object(
            observation, "_process_times", return_value=self.identity
        )
        self.times = times_patch.start()
        self.addCleanup(times_patch.stop)

    def test_required_read_only_rights_and_exact_identity(self):
        with observation.open_snapshot_process(3, "30") as (handle, identity):
            self.assertEqual((handle, identity), (123, self.identity))
            self.kernel.OpenProcess.assert_called_once_with(0x100410, False, 3)
            self.times.assert_called_once_with(123, 3)
            self.kernel.CloseHandle.assert_not_called()
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_invalid_identity_never_opens(self):
        for pid, birth in (
            (True, "30"),
            (0, "30"),
            (2**32, "30"),
            (3, "0"),
            (3, "030"),
            (3, 30),
        ):
            with self.subTest(pid=pid, birth=birth), self.assertRaises(ValueError):
                with observation.open_snapshot_process(pid, birth):
                    self.fail("invalid identity yielded")
        self.kernel.OpenProcess.assert_not_called()

    def test_running_undefined_exit_field_is_retained(self):
        self.identity["exit"] = "987654321"
        with observation.open_snapshot_process(3, "30") as (_, identity):
            self.assertEqual(identity["exit"], "987654321")

    def test_reuse_or_signaled_identity_closes_before_yield(self):
        for change in ({"birth": "31"}, {"exited_before_query": True}):
            self.times.return_value = self.identity | change
            self.kernel.CloseHandle.reset_mock()
            with self.subTest(change=change), self.assertRaises(ValueError):
                with observation.open_snapshot_process(3, "30"):
                    self.fail("wrong process yielded")
            self.kernel.CloseHandle.assert_called_once_with(123)

    def test_native_query_failure_closes_handle(self):
        self.times.side_effect = OSError("query failure")
        with self.assertRaisesRegex(OSError, "query failure"):
            with observation.open_snapshot_process(3, "30"):
                self.fail("failed query yielded")
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_caller_failure_closes_handle(self):
        with self.assertRaisesRegex(RuntimeError, "caller failure"):
            with observation.open_snapshot_process(3, "30"):
                raise RuntimeError("caller failure")
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_failed_open_does_not_close_null(self):
        self.kernel.OpenProcess.return_value = None
        with mock.patch.object(
            observation.live, "_raise_last_error", side_effect=OSError("open failed")
        ):
            with self.assertRaisesRegex(OSError, "open failed"):
                with observation.open_snapshot_process(3, "30"):
                    self.fail("failed open yielded")
        self.kernel.CloseHandle.assert_not_called()
        self.times.assert_not_called()

    def test_failed_close_is_reported(self):
        self.kernel.CloseHandle.return_value = 0
        with mock.patch.object(
            observation.live, "_raise_last_error", side_effect=OSError("close failed")
        ):
            with self.assertRaisesRegex(OSError, "close failed"):
                with observation.open_snapshot_process(3, "30"):
                    pass


@unittest.skipUnless(sys.platform == "win32", "native Windows handle contract")
class NativeSnapshotHandleTests(unittest.TestCase):
    def test_self_process_open_wait_times_close_without_product_execution(self):
        expected = observation._process_times(
            observation.live._current_process_handle(), os.getpid()
        )
        with observation.open_snapshot_process(os.getpid(), expected["birth"]) as (
            handle,
            identity,
        ):
            self.assertTrue(handle)
            self.assertEqual(identity["pid"], os.getpid())
            self.assertEqual(identity["birth"], expected["birth"])
            self.assertFalse(identity["exited_before_query"])


if __name__ == "__main__":
    unittest.main()
