from __future__ import annotations

import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tooling.tests.test_generated_artifact_profile_gate import execution, gated_policy
from tooling.tests.test_quality import (
    ConfigurationError,
    ProfileProgress,
    QualityRunner,
    Toolchain,
    quality_main,
)
from quality import OperationResult
from quality import _profile_output_guard, _render_profile_failure_details


class ProfileReceiptDestinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "checkout"
        self.root.mkdir()
        (self.root / ".git").mkdir()
        (self.root / "source.txt").write_text("frozen source", encoding="utf-8")
        self.tracked = {"source.txt", "target/tracked.json"}
        self.common_dir = self.root / ".git"
        self.commands: list[tuple[list[str], dict[str, object]]] = []
        self.registry = {
            "artifacts": [{"outputs": ["target/governed/*.json"]}],
            "inventory": {"governed_output_patterns": ["target/unregistered/*.json"]},
        }

    def git(
        self, arguments: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append((arguments, options))
        if arguments[1:] == ["rev-parse", "--git-dir"]:
            return subprocess.CompletedProcess(
                arguments, 0, str(self.root / ".git"), ""
            )
        if arguments[1:] == ["rev-parse", "--git-common-dir"]:
            return subprocess.CompletedProcess(arguments, 0, str(self.common_dir), "")
        if arguments[1:3] == ["ls-files", "--error-unmatch"]:
            return subprocess.CompletedProcess(
                arguments, 0 if arguments[-1] in self.tracked else 1, "", ""
            )
        if arguments[1] == "check-ignore":
            return subprocess.CompletedProcess(
                arguments, 0 if arguments[-1].startswith("target/") else 1, "", ""
            )
        self.fail(f"unexpected Git command: {arguments!r}")

    def guard(self):
        with patch("generated_artifacts.load_registry", return_value=self.registry):
            return _profile_output_guard(self.root)

    def test_source_governed_missing_inventory_and_git_destinations_fail_closed(
        self,
    ) -> None:
        self.common_dir = self.base / "common-git"
        for path in (
            self.root / "source.txt",
            self.root / "new-source.json",
            self.root / "target/tracked.json",
            self.root / "target/governed/output.json",
            self.root / "target/unregistered/output.json",
            self.root / ".git/index",
            self.common_dir / "refs/heads/main",
        ):
            with (
                self.subTest(path=path),
                patch("quality.subprocess.run", side_effect=self.git),
            ):
                with self.assertRaises(ConfigurationError):
                    self.guard()(path)
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())
        self.assertFalse((self.root / "new-source.json").exists())

    def test_outside_and_ignored_nongoverned_receipts_are_allowed_with_readonly_git(
        self,
    ) -> None:
        with patch("quality.subprocess.run", side_effect=self.git):
            guard = self.guard()
            guard(self.base / "outside-result.json")
            guard(self.root / "target/receipts/result.json")
            guard(self.root / "target/receipts/result.progress.jsonl")
        self.assertFalse((self.base / "outside-result.json").exists())
        for _command, options in self.commands:
            self.assertEqual("0", options["env"]["GIT_OPTIONAL_LOCKS"])

    def test_symlink_and_hardlink_aliases_are_rejected_without_source_write(
        self,
    ) -> None:
        alias = self.base / "outside-alias.json"
        try:
            alias.symlink_to(self.root / "source.txt")
        except OSError as error:
            self.skipTest(f"fixture symlink unavailable: {error}")
        with patch("quality.subprocess.run", side_effect=self.git):
            with self.assertRaisesRegex(ConfigurationError, "alias"):
                self.guard()(alias)
        alias.unlink()
        os.link(self.root / "source.txt", alias)
        with patch("quality.subprocess.run", side_effect=self.git):
            with self.assertRaisesRegex(ConfigurationError, "receipt file"):
                self.guard()(alias)
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_unsafe_artifact_argument_is_rejected_before_profile_or_progress_write(
        self,
    ) -> None:
        runner = QualityRunner(
            Toolchain(gated_policy(), self.root),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("artifact gate executed"),
            source_snapshotter=lambda: {},
        )
        with (
            patch("quality.Toolchain.load", return_value=runner.toolchain),
            patch("quality.QualityRunner", return_value=runner),
            patch(
                "quality.repository_state",
                return_value={"commit": "a" * 40, "dirty": False},
            ),
            patch("quality._profile_output_guard", return_value=self.guard()),
            patch("quality.subprocess.run", side_effect=self.git),
            patch(
                "quality.ProfileProgress",
                side_effect=AssertionError("progress write began"),
            ),
            patch(
                "quality.write_certification_artifact",
                side_effect=AssertionError("artifact write began"),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                2,
                quality_main(
                    [
                        "profile",
                        "local",
                        "--artifact",
                        str(self.root / "source.txt"),
                        "--json",
                    ]
                ),
            )
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_artifact_destination_is_rechecked_after_failed_fixture_gate(self) -> None:
        path = self.root / "target/receipts/result.json"
        path.parent.mkdir(parents=True)
        probe = path.parent / "symlink-probe"
        try:
            probe.symlink_to(self.root / "source.txt")
        except OSError as error:
            self.skipTest(f"fixture symlink unavailable: {error}")
        probe.unlink()
        runner = QualityRunner(
            Toolchain(gated_policy(), self.root),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: execution("failed"),
            source_snapshotter=lambda: {},
        )

        def fixture_artifact(**_arguments: object) -> dict[str, bool]:
            path.symlink_to(self.root / "source.txt")
            return {"synthetic_fixture_only": True}

        with (
            patch("quality.Toolchain.load", return_value=runner.toolchain),
            patch("quality.QualityRunner", return_value=runner),
            patch(
                "quality.repository_state",
                return_value={"commit": "a" * 40, "dirty": False},
            ),
            patch("quality._profile_output_guard", return_value=self.guard()),
            patch("quality.subprocess.run", side_effect=self.git),
            patch("quality.ProfileProgress"),
            patch("quality.build_certification_artifact", side_effect=fixture_artifact),
            patch(
                "quality.write_certification_artifact",
                side_effect=AssertionError("unsafe artifact write began"),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                2,
                quality_main(
                    [
                        "profile",
                        "local",
                        "--artifact",
                        str(path),
                        "--json",
                    ]
                ),
            )
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_progress_destination_is_guarded_before_creation_and_every_append(
        self,
    ) -> None:
        path = self.root / "target/receipts/profile.progress.jsonl"
        with patch("quality.subprocess.run", side_effect=self.git):
            guard = self.guard()
            with self.assertRaises(ConfigurationError):
                ProfileProgress(
                    profile="local",
                    source={"commit": "a" * 40, "dirty": False},
                    ledger_path=self.root / "new-source.progress.jsonl",
                    display_path="unsafe",
                    stream=StringIO(),
                    heartbeat_enabled=False,
                    destination_guard=guard,
                )
            self.assertFalse((self.root / "new-source.progress.jsonl").exists())
            progress = ProfileProgress(
                profile="local",
                source={"commit": "a" * 40, "dirty": False},
                ledger_path=path,
                display_path="target/receipts/profile.progress.jsonl",
                stream=StringIO(),
                heartbeat_enabled=False,
                destination_guard=guard,
            )
            progress.profile_started(1)
            self.assertEqual(
                "certification_started", json.loads(path.read_text())["event"]
            )
            path.unlink()
            try:
                path.symlink_to(self.root / "source.txt")
            except OSError as error:
                self.skipTest(f"fixture symlink unavailable: {error}")
            with self.assertRaises(ConfigurationError):
                progress.stage_started(
                    ordinal=1,
                    count=1,
                    operation_id="fixture",
                    result_id="fixture@repository",
                )
            with self.assertRaises(ConfigurationError):
                progress.stage_terminal(progress._active[-1], "passed")
            progress.close()
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_unsafe_stage_ledger_retains_child_receipt_in_failed_parent_artifact(
        self,
    ) -> None:
        artifact_path = self.root / "target/receipts/result.json"
        ledger_path = artifact_path.with_suffix(".progress.jsonl")
        artifact_path.parent.mkdir(parents=True)
        probe = artifact_path.parent / "symlink-probe"
        try:
            probe.symlink_to(self.root / "source.txt")
        except OSError as error:
            self.skipTest(f"fixture symlink unavailable: {error}")
        probe.unlink()
        observed = execution("passed")
        observed = type(observed)(
            observed.returncode, observed.stdout, "retained child stderr"
        )
        parsed = json.loads(observed.stdout)
        written: list[dict[str, object]] = []

        def child(_operation: str, _command: list[str]):
            ledger_path.unlink()
            ledger_path.symlink_to(self.root / "source.txt")
            return observed

        runner = QualityRunner(
            Toolchain(gated_policy(), self.root),
            executor=lambda *_args: self.fail("later component executed"),
            hardgate_executor=child,
            source_snapshotter=lambda: {},
        )

        def artifact(**arguments: object) -> dict[str, object]:
            return {
                "synthetic_fixture_only": True,
                "status": arguments["aggregate_status"],
                "results": arguments["results"],
            }

        output = StringIO()
        with (
            patch("quality.Toolchain.load", return_value=runner.toolchain),
            patch("quality.QualityRunner", return_value=runner),
            patch(
                "quality.repository_state",
                return_value={"commit": "a" * 40, "dirty": False},
            ),
            patch("quality._profile_output_guard", return_value=self.guard()),
            patch("quality.subprocess.run", side_effect=self.git),
            patch("quality.build_certification_artifact", side_effect=artifact),
            patch(
                "quality.write_certification_artifact",
                side_effect=lambda _path, result: written.append(result),
            ),
            redirect_stdout(output),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                1,
                quality_main(
                    [
                        "profile",
                        "local",
                        "--artifact",
                        str(artifact_path),
                        "--json",
                    ]
                ),
            )
        result = json.loads(output.getvalue())
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, len(result["results"]))
        parent = result["results"][0]
        self.assertEqual("failed", parent["status"])
        self.assertEqual(0, parent["exit_code"])
        self.assertEqual(parsed, parent["structured_result"])
        child_receipt = parent["execution_integrity"]["profile_receipt_guard"][
            "observed_child"
        ]
        self.assertEqual("passed", child_receipt["status"])
        self.assertEqual(0, child_receipt["exit_code"])
        self.assertEqual(observed.stdout, child_receipt["stdout"])
        self.assertEqual(observed.stderr, child_receipt["stderr"])
        self.assertEqual(parsed, child_receipt["structured_result"])
        self.assertEqual([result], written)
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_terminal_ledger_guard_fails_parent_before_artifact_is_built(self) -> None:
        child_result = OperationResult(
            operation="generated_integrity",
            component="repository",
            status="passed",
            command=["fixture-child"],
            exit_code=0,
            reason=None,
            structured_result={"synthetic_child_only": True},
            stdout="retained fixture child stdout",
            stderr="retained fixture child stderr",
        )
        runner = QualityRunner(
            Toolchain(gated_policy(), self.root),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("actual gate executed"),
            source_snapshotter=lambda: {},
        )
        written: list[dict[str, object]] = []

        class TerminalGuardFailure(ProfileProgress):
            def _record(self, record):
                if record["event"] == "certification_terminal":
                    raise ConfigurationError("synthetic terminal receipt rejection")
                return super()._record(record)

        def artifact(**arguments: object) -> dict[str, object]:
            self.assertEqual("failed", arguments["aggregate_status"])
            return {
                "synthetic_fixture_only": True,
                "status": arguments["aggregate_status"],
                "results": arguments["results"],
            }

        artifact_path = self.root / "target/receipts/terminal-result.json"
        with (
            patch("quality.Toolchain.load", return_value=runner.toolchain),
            patch("quality.QualityRunner", return_value=runner),
            patch.object(runner, "run_profile", return_value=[child_result]),
            patch(
                "quality.repository_state",
                return_value={"commit": "a" * 40, "dirty": False},
            ),
            patch("quality._profile_output_guard", return_value=self.guard()),
            patch("quality.subprocess.run", side_effect=self.git),
            patch("quality.ProfileProgress", TerminalGuardFailure),
            patch("quality.build_certification_artifact", side_effect=artifact),
            patch(
                "quality.write_certification_artifact",
                side_effect=lambda _path, result: written.append(result),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(
                1,
                quality_main(
                    [
                        "profile",
                        "local",
                        "--artifact",
                        str(artifact_path),
                        "--json",
                    ]
                ),
            )
        self.assertEqual(1, len(written))
        self.assertEqual("failed", written[0]["status"])
        observed = child_result.execution_integrity["profile_receipt_guard"][
            "observed_child"
        ]
        self.assertEqual("passed", observed["status"])
        self.assertEqual(0, observed["exit_code"])
        self.assertEqual("retained fixture child stdout", observed["stdout"])
        self.assertEqual({"synthetic_child_only": True}, observed["structured_result"])

    def test_aliased_failure_stream_parent_cannot_write_source_or_git_authority(
        self,
    ) -> None:
        parent = self.root / "target/failure-output"
        parent.parent.mkdir()
        protected = self.root / "protected-source"
        protected.mkdir()
        result = OperationResult(
            operation="fixture-child",
            component="repository",
            status="failed",
            command=["fixture-child"],
            exit_code=7,
            reason="actual fixture failure",
            structured_result={"synthetic_child_only": True},
            stdout="original child stdout\n" * 1000,
            stderr="original child stderr\n" * 1000,
        )
        original = (
            result.status,
            result.exit_code,
            result.reason,
            result.stdout,
            result.stderr,
            result.structured_result.copy(),
        )
        for target in (protected, self.root / ".git"):
            with self.subTest(target=target):
                try:
                    parent.symlink_to(target, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"fixture directory symlink unavailable: {error}")
                before = list(target.iterdir())
                stdout, stderr = StringIO(), StringIO()
                with (
                    patch("quality.PROFILE_FAILURE_OUTPUT_ROOT", parent),
                    patch("quality.subprocess.run", side_effect=self.git),
                    patch(
                        "quality.atomic_write_stream",
                        side_effect=AssertionError("unsafe child stream write began"),
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    _render_profile_failure_details(
                        [result], destination_guard=self.guard()
                    )
                self.assertEqual(before, list(target.iterdir()))
                self.assertIn(
                    "preservation failed: unsafe certification receipt alias",
                    stdout.getvalue(),
                )
                self.assertIn(
                    "preservation failed: unsafe certification receipt alias",
                    stderr.getvalue(),
                )
                parent.unlink()
        self.assertEqual(
            original,
            (
                result.status,
                result.exit_code,
                result.reason,
                result.stdout,
                result.stderr,
                result.structured_result,
            ),
        )
        self.assertEqual("frozen source", (self.root / "source.txt").read_text())

    def test_failure_stream_paths_are_guarded_before_mkdir_and_write(self) -> None:
        parent = self.root / "target/failure-output"
        result = OperationResult(
            operation="fixture-child",
            component="repository",
            status="failed",
            command=["fixture-child"],
            exit_code=7,
            reason="fixture failure",
            stdout="retained stdout\n" * 1000,
            stderr="retained stderr\n" * 1000,
        )
        captures: list[tuple[Path, bool]] = []
        with patch("quality.subprocess.run", side_effect=self.git):
            guard = self.guard()

            def guarded(path: Path) -> None:
                captures.append((path, path.parent.exists()))
                guard(path)

            with (
                patch("quality.PROFILE_FAILURE_OUTPUT_ROOT", parent),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                _render_profile_failure_details([result], destination_guard=guarded)
        self.assertEqual(
            [False, True, False, True], [exists for _path, exists in captures]
        )
        self.assertEqual(captures[0][0], captures[1][0])
        self.assertEqual(captures[2][0], captures[3][0])
        self.assertEqual(result.stdout, captures[1][0].read_text())
        self.assertEqual(result.stderr, captures[3][0].read_text())
        self.assertEqual(("failed", 7), (result.status, result.exit_code))

    def test_shared_profile_human_failure_stream_rejection_remains_fatal(self) -> None:
        parent = self.root / "target/failure-output"
        parent.parent.mkdir()
        protected = self.root / "protected-source"
        protected.mkdir()
        try:
            parent.symlink_to(protected, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"fixture directory symlink unavailable: {error}")
        child = OperationResult(
            operation="fixture-child",
            component="repository",
            status="failed",
            command=["fixture-child"],
            exit_code=7,
            reason="actual fixture failure",
            stdout="original stdout\n" * 1000,
            stderr="original stderr\n" * 1000,
        )
        runner = QualityRunner(
            Toolchain(gated_policy(), self.root),
            executor=lambda *_args: self.fail("component executed"),
            hardgate_executor=lambda *_args: self.fail("actual gate executed"),
            source_snapshotter=lambda: {},
        )
        with (
            patch("quality.Toolchain.load", return_value=runner.toolchain),
            patch("quality.QualityRunner", return_value=runner),
            patch.object(runner, "run_profile", return_value=[child]),
            patch(
                "quality.repository_state",
                return_value={"commit": "a" * 40, "dirty": False},
            ),
            patch("quality._profile_output_guard", return_value=self.guard()),
            patch("quality.subprocess.run", side_effect=self.git),
            patch("quality.ProfileProgress"),
            patch("quality.PROFILE_FAILURE_OUTPUT_ROOT", parent),
            patch(
                "quality.build_certification_artifact",
                return_value={"synthetic_fixture_only": True},
            ),
            patch(
                "quality.render_certification_summary",
                return_value="fixture parent failed",
            ),
            patch(
                "quality.atomic_write_stream",
                side_effect=AssertionError("unsafe stream write began"),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(1, quality_main(["profile", "local"]))
        self.assertEqual([], list(protected.iterdir()))
        self.assertEqual(("failed", 7), (child.status, child.exit_code))
        self.assertEqual("original stdout\n" * 1000, child.stdout)
        self.assertEqual("original stderr\n" * 1000, child.stderr)

    def test_destination_git_failure_fails_closed(self) -> None:
        with patch(
            "quality.subprocess.run",
            return_value=subprocess.CompletedProcess(["git"], 128, "", "unavailable"),
        ):
            with self.assertRaises(ConfigurationError):
                self.guard()(self.root / "target/receipts/result.json")


if __name__ == "__main__":
    unittest.main()
