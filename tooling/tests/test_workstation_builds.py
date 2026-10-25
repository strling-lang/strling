"""Synthetic Git namespace routing only; no compiler or native worker executes."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_resource_certification as authority
from tooling import workstation_builds as builds
from tooling import workstation_campaign as campaign

ROOT = Path(__file__).resolve().parents[2]


class WorkstationGitRoutingTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(
            dir=ROOT / "target", prefix="synthetic-worktree-routing-"
        )
        root = Path(temporary.name)
        (root / ".git").write_text(
            "gitdir: /mnt/d/synthetic-repository/.git/worktrees/source\n",
            encoding="utf-8",
        )
        return temporary, root

    def test_source_identity_uses_existing_readonly_namespace_translation(self):
        temporary, root = self.fixture()
        with (
            temporary,
            patch.object(authority.platform, "system", return_value="Windows"),
            patch.object(
                campaign.subprocess, "check_output", side_effect=[b"", b"a" * 40]
            ) as run,
        ):
            self.assertEqual(campaign.source_identity(root), "a" * 40)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(
                command[:5],
                [
                    "git",
                    "--git-dir",
                    "D:/synthetic-repository/.git/worktrees/source",
                    "--work-tree",
                    str(root),
                ],
            )
            self.assertIn("--no-optional-locks", command)

    def test_source_archive_uses_explicit_existing_git_invocation(self):
        class StopBeforeGitExec(RuntimeError):
            pass

        temporary, root = self.fixture()
        with (
            temporary,
            patch.object(authority.platform, "system", return_value="Windows"),
            patch.object(
                builds.subprocess, "run", side_effect=StopBeforeGitExec
            ) as run,
        ):
            with self.assertRaises(StopBeforeGitExec):
                builds.build_lane(
                    root,
                    root / "fresh-lane",
                    kernel_revision="a" * 40,
                    harness_root=root,
                    cargo=Path("C:/synthetic/cargo.exe"),
                    rustc=Path("C:/synthetic/rustc.exe"),
                    git_invocation=authority._git_invocation,
                )
        command = run.call_args.args[0]
        self.assertEqual(
            command[:5],
            [
                "git",
                "--git-dir",
                "D:/synthetic-repository/.git/worktrees/source",
                "--work-tree",
                str(root),
            ],
        )
        self.assertEqual(
            command[5:], ["--no-optional-locks", "archive", "--format=zip", "a" * 40]
        )


if __name__ == "__main__":
    unittest.main()
