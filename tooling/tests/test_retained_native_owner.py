"""Pure negative lifecycle guards; no real child or performance sample starts."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from tooling import retained_native_owner as owner

TEMP_ROOT = Path(__file__).resolve().parents[2] / "target/codex-tools"


class RetainedNativeOwnerTests(unittest.TestCase):
    def setUp(self):
        self.clear = dict(
            platform="windows", administrator=False, in_job=False, job_limit_flags=None
        )
        self.permitted = dict(
            platform="windows", administrator=False, in_job=True, job_limit_flags=0x2800
        )

    def test_exact_flags_and_worker_check(self):
        self.assertEqual(
            owner.creation_flags(self.clear, approved_native_launch=True), 0x08000000
        )
        self.assertEqual(
            owner.creation_flags(self.permitted, approved_native_launch=True),
            0x09000000,
        )
        self.assertEqual(owner.require_independent_owner(self.clear), self.clear)
        with self.assertRaises(owner.NativeOwnerError):
            owner.require_independent_owner(self.permitted)

    def test_context_rejection_matrix(self):
        invalid = []
        for key, values in {
            "platform": ["linux", None],
            "administrator": [True, 0, None],
            "in_job": [0, None],
            "job_limit_flags": [False, -1, 0, 0x2000, 0x2801, 0x3800, None],
        }.items():
            for value in values:
                invalid.append({**self.permitted, key: value})
        invalid.extend(
            [
                {k: v for k, v in self.clear.items() if k != "in_job"},
                {**self.clear, "extra": True},
                {**self.clear, "job_limit_flags": 0},
            ]
        )
        for context in invalid:
            with (
                self.subTest(context=context),
                self.assertRaises(owner.NativeOwnerError),
            ):
                owner.creation_flags(context, approved_native_launch=True)
        for approval in (False, None, 1, "approved"):
            with (
                self.subTest(approval=approval),
                self.assertRaises(owner.NativeOwnerError),
            ):
                owner.creation_flags(self.permitted, approved_native_launch=approval)

    def test_launch_bindings_exclusive_receipts_and_failure(self):
        with tempfile.TemporaryDirectory(
            prefix="native-owner-unit-", dir=TEMP_ROOT
        ) as temporary:
            root = Path(temporary)
            tools = root / "target/codex-tools"
            tools.mkdir(parents=True)
            script = tools / "worker.py"
            script.write_bytes(b"# sample-free unit fixture\n")
            digest = hashlib.sha256(script.read_bytes()).hexdigest()
            kwargs = dict(
                script=script,
                script_sha256=digest,
                root=root,
                evidence_prefix=tools / "proof",
                approved_native_launch=True,
            )
            with (
                patch.object(owner, "lifecycle_context", return_value=self.permitted),
                patch.object(owner, "NATIVE_PYTHON", Path(owner.sys.executable)),
                patch.object(
                    owner.subprocess, "Popen", return_value=Mock(pid=123)
                ) as launched,
            ):
                for field, value in (
                    ("script_sha256", "wrong"),
                    ("script_sha256", True),
                    ("evidence_prefix", root / "escape"),
                    ("approved_native_launch", False),
                ):
                    with (
                        self.subTest(field=field),
                        self.assertRaises(owner.NativeOwnerError),
                    ):
                        owner.launch_retained_python_owner(**{**kwargs, field: value})
                launched.assert_not_called()
                result = owner.launch_retained_python_owner(**kwargs)
                self.assertEqual(result["status"], "launched-not-completed")
                self.assertFalse(result["producer_terminal"])
                self.assertEqual(launched.call_args.kwargs["creationflags"], 0x09000000)
                self.assertNotIn("shell", launched.call_args.kwargs)
                with self.assertRaises(owner.NativeOwnerError):
                    owner.launch_retained_python_owner(**kwargs)
                self.assertEqual(launched.call_count, 1)
                failed = {**kwargs, "evidence_prefix": tools / "failed"}
                launched.side_effect = OSError("synthetic launch failure")
                with self.assertRaises(OSError):
                    owner.launch_retained_python_owner(**failed)
                self.assertIn(
                    "synthetic launch failure",
                    Path(
                        str(failed["evidence_prefix"]) + ".lifecycle-launch.json"
                    ).read_text(),
                )
                with self.assertRaises(owner.NativeOwnerError):
                    owner.launch_retained_python_owner(**failed)

    def test_script_escape_foreign_python_and_unknown_worker(self):
        with tempfile.TemporaryDirectory(
            prefix="native-owner-unit-", dir=TEMP_ROOT
        ) as temporary:
            root = Path(temporary)
            tools = root / "target/codex-tools"
            tools.mkdir(parents=True)
            script = root / "foreign.py"
            script.write_bytes(b"# fixture\n")
            kwargs = dict(
                script=script,
                script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                root=root,
                evidence_prefix=tools / "proof",
                approved_native_launch=True,
            )
            with (
                patch.object(owner, "lifecycle_context", return_value=self.clear),
                patch.object(owner.subprocess, "Popen") as launched,
            ):
                with self.assertRaises(owner.NativeOwnerError):
                    owner.launch_retained_python_owner(**kwargs)
                script = tools / "worker.py"
                script.write_bytes(b"# fixture\n")
                with (
                    patch.object(owner, "NATIVE_PYTHON", Path("foreign-python")),
                    self.assertRaises(owner.NativeOwnerError),
                ):
                    owner.launch_retained_python_owner(**{**kwargs, "script": script})
                launched.assert_not_called()
        with (
            patch.object(owner, "lifecycle_context", return_value=self.permitted),
            self.assertRaises(owner.NativeOwnerError),
        ):
            owner.require_independent_owner()


if __name__ == "__main__":
    unittest.main()
