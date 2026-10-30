"""Build routing and read-only Git identity; no native workload executes."""

import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_resource_certification as authority
from tooling import workstation_builds as builds
from tooling import workstation_campaign as campaign
from tooling import workstation_certification as gateway

ROOT = Path(__file__).resolve().parents[2]


class CanonicalBuildExecutionTests(unittest.TestCase):
    def test_commands_use_one_canonical_lane_and_keep_external_tool_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as temporary:
            lane = Path(temporary) / "physical-lane"
            lane.mkdir()
            canonical = Path(temporary) / "canonical-lane"
            tool = Path(temporary) / "pinned-cargo.exe"
            command = [
                str(tool),
                "build",
                "--manifest-path",
                str(lane / "harness/Cargo.toml"),
            ]

            @contextmanager
            def mapping(directory):
                self.assertEqual(directory, lane)
                yield canonical

            with (
                patch.object(authority, "_canonical_build_root", mapping),
                patch.object(
                    builds.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as run,
            ):
                builds._run(
                    command,
                    root=ROOT,
                    directory=lane,
                    name="probe",
                    environment={"PIN": "kept"},
                )
            self.assertEqual(
                run.call_args.args[0],
                [
                    str(tool),
                    "build",
                    "--manifest-path",
                    str(canonical / "harness/Cargo.toml"),
                ],
            )
            self.assertEqual(run.call_args.kwargs["cwd"], canonical)
            self.assertEqual(run.call_args.kwargs["env"], {"PIN": "kept"})

    def test_busy_canonical_root_fails_before_any_compiler_launch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as temporary:
            lane = Path(temporary)

            @contextmanager
            def busy(_directory):
                raise ValueError("canonical root occupied")
                yield  # pragma: no cover

            with (
                patch.object(authority, "_canonical_build_root", busy),
                patch.object(
                    builds.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as run,
            ):
                with self.assertRaisesRegex(ValueError, "canonical root occupied"):
                    builds._run(
                        ["cargo", "build"],
                        root=ROOT,
                        directory=lane,
                        name="busy",
                        environment={},
                    )
                run.assert_not_called()


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


class ReadOnlyIdentityTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(
            ["git", "--no-optional-locks", *args], cwd=self.root, env=self.env
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            dir=ROOT / "target", prefix="atomic-readonly-index-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(os.environ, GIT_OPTIONAL_LOCKS="1")
        self.env.pop("GIT_INDEX_FILE", None)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Atomic fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        (self.root / "tracked.txt").write_bytes(b"original\n")
        self.git("add", "tracked.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture")
        self.commit = self.git("rev-parse", "HEAD").decode().strip()
        self.index = self.root / ".git/index"

    def probe(self, dirty):
        before = self.index.read_bytes()
        identity = self.index.stat().st_ino
        with patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(authority._git_identity(self.root), (self.commit, dirty))
        self.assertEqual(self.index.read_bytes(), before)
        self.assertEqual(self.index.stat().st_ino, identity)

    def test_clean_identity_does_not_refresh_stale_index_stat_cache(self):
        data = bytearray(self.index.read_bytes())
        self.assertEqual(struct.unpack(">I", data[4:8])[0], 2)
        # Invalidate cached filesystem metadata without changing entry mode,
        # object identity, path, flags or source bytes. Optional status refresh
        # would replace this index even though it reports a clean worktree.
        for offset in (12, 16, 20, 24, 28, 32):
            data[offset : offset + 4] = b"\0" * 4
        data[-20:] = hashlib.sha1(data[:-20]).digest()
        self.index.write_bytes(data)
        self.probe(False)

    def test_unstaged_source_change_remains_dirty_without_index_write(self):
        (self.root / "tracked.txt").write_bytes(b"changed\n")
        self.probe(True)

    def test_staged_blob_change_remains_dirty_without_index_write(self):
        (self.root / "tracked.txt").write_bytes(b"changed\n")
        self.git("add", "tracked.txt")
        self.probe(True)

    def test_staged_mode_change_remains_dirty_without_index_write(self):
        self.git("update-index", "--chmod=+x", "tracked.txt")
        self.probe(True)

    def test_staged_removal_remains_dirty_without_index_write(self):
        self.git("update-index", "--force-remove", "tracked.txt")
        self.probe(True)


class NativeBuildPathTests(unittest.TestCase):
    def test_isolated_release_prefix_leaves_room_for_failed_linker_outputs(self):
        root = Path(
            "D:/Projects/strling-lang/strling/.cert/production-certification/"
            "0123456789ab-20260101T000000Z/source"
        )
        first = gateway.acquisition_directory(root)
        second = gateway.acquisition_directory(root)
        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, root / "target")
        for target in (
            "reference/harness/target",
            "reference/source/core/internal/target",
            "reference/source/bindings/interop/target",
        ):
            with self.subTest(target=target):
                output = (
                    first
                    / target
                    / (
                        "release/build/proc-macro2-cd35bd4de16d1eb6/"
                        "build_script_build-cd35bd4de16d1eb6.exe"
                    )
                )
                self.assertLess(len(str(output)), 260)


if __name__ == "__main__":
    unittest.main()
