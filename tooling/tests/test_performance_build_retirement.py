"""Owned compiler-helper retirement policy; no native process or product samples."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tooling import performance_build_retirement as retirement


class RetirementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="strling-build-retirement-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.image = self.root / "vctip.exe"
        self.image.write_bytes(b"explicitly synthetic pinned compiler helper")
        self.artifact = self.root / "required.exe"
        self.artifact.write_bytes(b"required build output")
        self.approvals = {
            str(self.image): hashlib.sha256(self.image.read_bytes()).hexdigest()
        }
        self.actions = []
        self.elapsed = 0.0

    def row(self, **updates):
        value = dict(
            pid=100,
            birth="123456789",
            same_owned_job=True,
            exited_before_query=False,
            image=str(self.image),
        )
        return {**value, **updates}

    def snapshot(self, rows):
        return dict(
            active_accounting=len(rows),
            assigned=len(rows),
            populated=len(rows),
            pids=[r["pid"] for r in rows],
            processes=rows,
            queries_not_atomic=True,
        )

    def sleep(self, duration):
        self.elapsed += duration

    def run_case(self, snapshots, **overrides):
        queue = list(snapshots)

        def observe():
            return queue.pop(0) if len(queue) > 1 else queue[0]

        arguments = dict(
            build_passed=True,
            required_artifacts={"runner": self.artifact},
            approved_background_images=self.approvals,
            snapshot=observe,
            terminate=lambda: self.actions.append("terminate"),
            close=lambda: self.actions.append("close"),
            monotonic=lambda: self.elapsed,
            sleep=self.sleep,
            drain_seconds=0.3,
            poll_seconds=0.1,
        )
        return retirement.retire_after_success(**{**arguments, **overrides})

    def test_empty_closes_without_termination(self):
        result = self.run_case([self.snapshot([])])
        self.assertEqual(["close"], self.actions)
        self.assertEqual("passed", result["status"])
        self.assertEqual(result["artifacts_before"], result["artifacts_after"])

    def test_pinned_owned_helper_is_retired_once(self):
        result = self.run_case(
            [
                self.snapshot([self.row()]),
                self.snapshot([self.row()]),
                self.snapshot([]),
            ]
        )
        self.assertEqual(["terminate", "close"], self.actions)
        self.assertEqual(3, len(result["snapshots"]))
        self.assertEqual("owned-compiler-background-cleanup", result["action"])

    def test_unknown_or_unowned_process_is_rejected(self):
        for changes in (
            {"image": str(self.root / "python.exe")},
            {"same_owned_job": False},
            {"birth": ""},
            {"birth": "0"},
            {"pid": True},
            {"exited_before_query": True},
            {"image_error": 5},
            {"open_error": 5},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(retirement.RetirementError) as raised,
            ):
                self.run_case([self.snapshot([self.row(**changes)])])
            self.assertEqual([], self.actions)
            self.assertEqual("failed", raised.exception.receipt["status"])

    def test_wrong_hash_is_rejected(self):
        with self.assertRaises(retirement.RetirementError):
            self.run_case(
                [self.snapshot([self.row()])],
                approved_background_images={str(self.image): "0" * 64},
            )
        self.assertEqual([], self.actions)

    def test_invalid_approval_pin_is_rejected(self):
        with self.assertRaises(retirement.RetirementError):
            self.run_case(
                [self.snapshot([])], approved_background_images={str(self.image): "bad"}
            )
        self.assertEqual([], self.actions)

    def test_other_image_cannot_be_approved(self):
        other = self.root / "python.exe"
        other.write_bytes(self.image.read_bytes())
        with self.assertRaises(retirement.RetirementError):
            self.run_case(
                [self.snapshot([self.row(image=str(other))])],
                approved_background_images={
                    str(other): self.approvals[str(self.image)]
                },
            )
        self.assertEqual([], self.actions)

    def test_duplicate_pid_is_rejected(self):
        with self.assertRaises(retirement.RetirementError):
            self.run_case([self.snapshot([self.row(), self.row()])])
        self.assertEqual([], self.actions)

    def test_truncated_or_inconsistent_query_is_rejected(self):
        for field in ("active_accounting", "assigned", "populated"):
            value = self.snapshot([self.row()])
            value[field] = 2
            with (
                self.subTest(field=field),
                self.assertRaises(retirement.RetirementError),
            ):
                self.run_case([value])
            self.assertEqual([], self.actions)

    def test_failed_build_never_enters_success_cleanup(self):
        with self.assertRaises(retirement.RetirementError):
            self.run_case([self.snapshot([self.row()])], build_passed=False)
        self.assertEqual([], self.actions)

    def test_missing_or_empty_artifact_rejected(self):
        for content in (None, b""):
            if self.artifact.exists():
                self.artifact.unlink()
            if content is not None:
                self.artifact.write_bytes(content)
            with self.assertRaises(retirement.RetirementError):
                self.run_case([self.snapshot([])])
            self.assertEqual([], self.actions)

    def test_timeout_preserves_observations_without_close(self):
        with self.assertRaises(retirement.RetirementError) as raised:
            self.run_case([self.snapshot([self.row()])])
        self.assertEqual(["terminate"], self.actions)
        self.assertGreaterEqual(len(raised.exception.receipt["snapshots"]), 4)

    def test_artifact_change_during_cleanup_rejected(self):
        def terminate():
            self.actions.append("terminate")
            self.artifact.write_bytes(b"changed during cleanup")

        with self.assertRaises(retirement.RetirementError) as raised:
            self.run_case(
                [self.snapshot([self.row()]), self.snapshot([])], terminate=terminate
            )
        self.assertNotEqual(
            raised.exception.receipt["artifacts_before"],
            raised.exception.receipt["artifacts_after"],
        )
        self.assertEqual(["terminate"], self.actions)

    def test_query_and_termination_errors_preserve_failure(self):
        def fail():
            raise OSError("native fixture error")

        for overrides in ({"snapshot": fail}, {"terminate": fail}):
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(retirement.RetirementError) as raised,
            ):
                self.run_case([self.snapshot([self.row()])], **overrides)
            self.assertIn("native fixture error", raised.exception.receipt["error"])
            self.assertEqual([], self.actions)

    def test_invalid_bounds_fail_without_observation(self):
        for changes in (
            {"drain_seconds": 0},
            {"drain_seconds": 31},
            {"poll_seconds": 0},
            {"poll_seconds": 1},
            {"required_artifacts": {}},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(retirement.RetirementError),
            ):
                self.run_case([self.snapshot([])], **changes)
            self.assertEqual([], self.actions)


if __name__ == "__main__":
    unittest.main()
