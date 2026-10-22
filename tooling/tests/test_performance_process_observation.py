"""Actual counter journaling must not manufacture continuous isolation proof."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
