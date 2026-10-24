"""Exact, bounded snapshot reads using disposable filesystem fixtures only."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tooling import generated_artifacts as generated
from tooling.tests.test_generated_artifact_preparation import preparation_registry


class BoundedArtifactSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = [
            "binary.bin",
            "nested/with spaces.txt",
            "missing.txt",
            "empty.txt",
        ]
        (self.root / "nested").mkdir()
        (self.root / "binary.bin").write_bytes(bytes(range(256)) * 13)
        (self.root / "nested/with spaces.txt").write_bytes(
            b"exact CRLF\r\nUTF8:\xc3\xa9\n"
        )
        (self.root / "empty.txt").write_bytes(b"")

    def sequential_reference(self, paths: list[str]) -> dict[str, str]:
        result = {}
        for relative in paths:
            path = self.root / relative
            if path.is_symlink():
                payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
            elif path.is_file():
                payload = path.read_bytes()
            else:
                payload = b"<missing>"
            mode = stat.S_IMODE(path.lstat().st_mode) if path.exists() else 0
            result[relative] = hashlib.sha256(
                str(mode).encode("ascii") + b"\0" + payload
            ).hexdigest()
        return result

    def test_parallel_snapshot_equals_original_full_byte_mode_path_reference(
        self,
    ) -> None:
        expected = self.sequential_reference(self.paths)

        def reader(path: str) -> tuple[str, str]:
            return generated._snapshot_tracked_path(self.root, path)

        self.assertEqual(
            expected, generated._snapshot_entries(self.paths, reader, workers=1)
        )
        parallel = generated._snapshot_entries(self.paths, reader)
        self.assertEqual(expected, parallel)
        self.assertEqual(self.paths, list(parallel))
        self.assertEqual(parallel, generated._snapshot_entries(self.paths, reader))

    def test_repository_census_reads_every_path_including_duplicate_and_missing(
        self,
    ) -> None:
        paths = [*self.paths, "binary.bin"]
        output = b"\0".join(path.encode() for path in paths) + b"\0"
        calls = []
        native = generated._snapshot_tracked_path

        def reader(root, relative):
            calls.append(relative)
            return native(root, relative)

        with (
            patch.object(
                generated.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, output, b""),
            ) as git,
            patch.object(generated, "_snapshot_tracked_path", side_effect=reader),
        ):
            actual = generated.snapshot_repository(self.root)
        self.assertEqual(self.sequential_reference(paths), actual)
        self.assertCountEqual(paths, calls)
        self.assertEqual(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            git.call_args.args[0],
        )

    def test_governed_ignored_output_census_is_complete_and_alias_guard_is_retained(
        self,
    ) -> None:
        registry = preparation_registry()
        registry["artifacts"][0]["outputs"] = ["ignored/**"]
        registry["inventory"]["governed_output_patterns"] = [
            "ignored/**",
            "**/Cargo.lock",
        ]
        ignored = self.root / "ignored"
        ignored.mkdir()
        for name in ("one.json", "two.json"):
            (ignored / name).write_bytes(name.encode())
        before = {path: path.read_bytes() for path in ignored.iterdir()}
        result = generated.integrity_snapshot(
            registry, self.root, lambda _root: {"tracked-source": "preserved"}
        )
        self.assertEqual(
            {"tracked-source", "ignored/one.json", "ignored/two.json"}, set(result)
        )
        self.assertEqual(
            before, {path: path.read_bytes() for path in ignored.iterdir()}
        )
        path = ignored / "one.json"
        native = Path.resolve

        def resolve(candidate, *args, **kwargs):
            return (
                self.root.parent
                if candidate == path
                else native(candidate, *args, **kwargs)
            )

        with (
            patch.object(Path, "resolve", resolve),
            self.assertRaisesRegex(generated.RegistryError, "regular repository file"),
        ):
            generated.integrity_snapshot(registry, self.root, lambda _root: {})

    def test_tracked_symlink_payload_semantics_are_preserved_portably(self) -> None:
        path = self.root / "missing.txt"
        native = Path.is_symlink
        with (
            patch.object(
                Path,
                "is_symlink",
                lambda candidate: candidate == path or native(candidate),
            ),
            patch.object(generated.os, "readlink", return_value="nonexistent-target"),
        ):
            expected = self.sequential_reference(["missing.txt"])
            actual = generated._snapshot_entries(
                ["missing.txt"],
                lambda relative: generated._snapshot_tracked_path(self.root, relative),
            )
        self.assertEqual(expected, actual)

    def test_worker_and_outstanding_future_bounds_are_fixed(self) -> None:
        maximum = 0
        outstanding = 0
        workers = 0

        class FixtureFuture:
            def __init__(self, reader, item):
                self.reader, self.item = reader, item

            def result(self):
                nonlocal outstanding
                outstanding -= 1
                return self.reader(self.item)

        class FixturePool:
            def __init__(self, max_workers):
                nonlocal workers
                workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def submit(self, reader, item):
                nonlocal outstanding, maximum
                outstanding += 1
                maximum = max(maximum, outstanding)
                return FixtureFuture(reader, item)

        paths = [str(index) for index in range(29)]
        with patch.object(generated, "ThreadPoolExecutor", FixturePool):
            result = generated._snapshot_entries(
                paths, lambda path: (path, "fixture-digest")
            )
        self.assertEqual(8, workers)
        self.assertEqual(16, maximum)
        self.assertEqual(0, outstanding)
        self.assertEqual(paths, list(result))
        for invalid in (0, -1, 9):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(generated.RegistryError),
            ):
                generated._snapshot_entries(
                    paths, lambda path: (path, "unused"), workers=invalid
                )

    def test_read_ahead_keeps_workers_busy_behind_a_blocked_first_path(self) -> None:
        ninth_started = threading.Event()

        def reader(index):
            if index == 0 and not ninth_started.wait(timeout=1):
                raise AssertionError("ordered first path starved the ninth read")
            if index == 8:
                ninth_started.set()
            return str(index), "exact-fixture-digest"

        result = generated._snapshot_entries(range(31), reader)
        self.assertEqual([str(index) for index in range(31)], list(result))

    def test_read_ahead_with_one_worker_preserves_exact_order_and_duplicates(
        self,
    ) -> None:
        calls = []

        def reader(item):
            calls.append(item)
            return None if item == "skip" else (item, str(len(calls)))

        result = generated._snapshot_entries(
            ["first", "skip", "first", "last"], reader, workers=1
        )
        self.assertEqual(["first", "skip", "first", "last"], calls)
        self.assertEqual([("first", "3"), ("last", "4")], list(result.items()))

    def test_regular_fast_path_keeps_every_full_read_and_fresh_final_mode(self) -> None:
        native_stat = os.stat
        native_read = Path.read_bytes
        metadata_calls = []
        byte_reads = []

        def metadata(*args, **kwargs):
            metadata_calls.append(kwargs.get("follow_symlinks", True))
            return native_stat(*args, **kwargs)

        def read(path):
            byte_reads.append(path)
            return native_read(path)

        expected = self.sequential_reference(["binary.bin"])["binary.bin"]
        with patch.object(os, "stat", metadata), patch.object(Path, "read_bytes", read):
            for _ in range(2):
                self.assertEqual(
                    ("binary.bin", expected),
                    generated._snapshot_tracked_path(self.root, "binary.bin"),
                )
        self.assertEqual([False] * 4, metadata_calls)
        self.assertEqual([self.root / "binary.bin"] * 2, byte_reads)

    def test_regular_fast_path_uses_post_read_mode_not_initial_metadata(self) -> None:
        native = Path.lstat
        calls = 0

        def metadata(path):
            nonlocal calls
            calls += 1
            values = list(native(path))
            values[0] = stat.S_IFREG | (0o640 if calls == 1 else 0o444)
            return os.stat_result(values)

        with patch.object(Path, "lstat", metadata):
            actual = generated._snapshot_tracked_path(self.root, "binary.bin")
        self.assertEqual(2, calls)
        expected = hashlib.sha256(
            b"292\0" + (self.root / "binary.bin").read_bytes()
        ).hexdigest()
        self.assertEqual(("binary.bin", expected), actual)

    def test_metadata_absence_policy_matches_public_pathlib_on_every_os_error(
        self,
    ) -> None:
        errors = [OSError(code, "fixture metadata") for code in errno.errorcode]
        for code in (21, 123, 1921, 999999):
            error = OSError("fixture Windows metadata")
            error.winerror = code
            errors.append(error)
        errors.extend([OSError("unspecified I/O"), ValueError("non-encodable path")])
        path = self.root / "binary.bin"
        for error in errors:
            with self.subTest(
                error=repr(error), winerror=getattr(error, "winerror", None)
            ):
                expected = []
                for method in ("is_symlink", "exists"):
                    with (
                        patch.object(Path, "lstat", side_effect=error),
                        patch.object(Path, "stat", side_effect=error),
                    ):
                        try:
                            expected.append(("returned", getattr(path, method)()))
                        except (OSError, ValueError) as seen:
                            expected.append(("raised", seen))
                self.assertEqual(expected[0], expected[1])
                with patch.object(Path, "lstat", side_effect=error):
                    try:
                        actual = generated._snapshot_metadata(path)
                    except (OSError, ValueError) as seen:
                        outcome = ("raised", seen)
                    else:
                        self.assertIsNone(actual)
                        outcome = ("returned", False)
                self.assertEqual(expected[0], outcome)

    def test_initial_transient_permission_or_io_error_is_never_retried(self) -> None:
        native = Path.lstat
        for error in (PermissionError(13, "initial denied"), OSError(5, "initial I/O")):
            calls = 0

            def metadata(path):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise error
                return native(path)

            with (
                self.subTest(error=error),
                patch.object(Path, "lstat", metadata),
                self.assertRaises(type(error)) as seen,
            ):
                generated._snapshot_tracked_path(self.root, "binary.bin")
            self.assertIs(error, seen.exception)
            self.assertEqual(1, calls)

    def test_final_transient_permission_or_io_error_is_never_retried(self) -> None:
        native = Path.lstat
        for error in (PermissionError(13, "final denied"), OSError(5, "final I/O")):
            calls = 0

            def metadata(path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise error
                return native(path)

            with (
                self.subTest(error=error),
                patch.object(Path, "lstat", metadata),
                self.assertRaises(type(error)) as seen,
            ):
                generated._snapshot_tracked_path(self.root, "binary.bin")
            self.assertIs(error, seen.exception)
            self.assertEqual(2, calls)

    def test_regular_read_disappearance_and_directory_replacement_match_reference(
        self,
    ) -> None:
        for replacement in ("missing", "directory"):
            fingerprints = []
            for reader in ("reference", "fast"):
                directory = self.root / f"{replacement}-{reader}"
                directory.mkdir()
                path = directory / "file"
                path.write_bytes(b"complete original bytes")
                native = Path.read_bytes

                def read(candidate):
                    payload = native(candidate)
                    if candidate == path:
                        candidate.unlink()
                        if replacement == "directory":
                            candidate.mkdir()
                    return payload

                with patch.object(Path, "read_bytes", read):
                    if reader == "reference":
                        original_root = self.root
                        self.root = directory
                        try:
                            fingerprints.append(
                                self.sequential_reference(["file"])["file"]
                            )
                        finally:
                            self.root = original_root
                    else:
                        fingerprints.append(
                            generated._snapshot_tracked_path(directory, "file")[1]
                        )
            self.assertEqual(fingerprints[0], fingerprints[1])

    @unittest.skipIf(os.name == "nt", "real POSIX symlink and mode semantics")
    def test_real_tracked_links_keep_target_string_and_dangling_zero_mode(self) -> None:
        (self.root / "directory").mkdir()
        (self.root / "file-link").symlink_to("binary.bin")
        (self.root / "directory-link").symlink_to("directory")
        (self.root / "dangling-link").symlink_to("does-not-exist")
        (self.root / "loop-link").symlink_to("loop-link")
        for name in ("file-link", "directory-link", "dangling-link", "loop-link"):
            with self.subTest(name=name):
                self.assertEqual(
                    (name, self.sequential_reference([name])[name]),
                    generated._snapshot_tracked_path(self.root, name),
                )

    @unittest.skipIf(os.name == "nt", "real POSIX symlink and mode transitions")
    def test_regular_read_link_replacements_keep_original_final_mode_policy(
        self,
    ) -> None:
        for dangling in (False, True):
            fingerprints = []
            for reader in ("reference", "fast"):
                directory = self.root / f"link-{dangling}-{reader}"
                directory.mkdir()
                path = directory / "file"
                path.write_bytes(b"original bytes")
                (directory / "target").write_bytes(b"different target bytes")
                native = Path.read_bytes

                def read(candidate):
                    payload = native(candidate)
                    if candidate == path:
                        candidate.unlink()
                        candidate.symlink_to("absent" if dangling else "target")
                    return payload

                with patch.object(Path, "read_bytes", read):
                    if reader == "reference":
                        original_root = self.root
                        self.root = directory
                        try:
                            fingerprints.append(
                                self.sequential_reference(["file"])["file"]
                            )
                        finally:
                            self.root = original_root
                    else:
                        fingerprints.append(
                            generated._snapshot_tracked_path(directory, "file")[1]
                        )
            self.assertEqual(fingerprints[0], fingerprints[1])

    def test_real_worker_parallelism_remains_bounded_and_output_ordered(self) -> None:
        barrier = threading.Barrier(8)
        mutex = threading.Lock()
        active = 0
        maximum = 0

        def reader(index):
            nonlocal active, maximum
            with mutex:
                active += 1
                maximum = max(maximum, active)
            try:
                if index < 8:
                    barrier.wait(timeout=5)
                return str(index), "exact-fixture-digest"
            finally:
                with mutex:
                    active -= 1

        result = generated._snapshot_entries(list(range(31)), reader)
        self.assertEqual(8, maximum)
        self.assertEqual(0, active)
        self.assertEqual([str(index) for index in range(31)], list(result))

    def test_read_error_fails_closed_without_a_partial_snapshot(self) -> None:
        def reader(relative):
            if relative == "missing.txt":
                raise PermissionError("fixture filesystem denial")
            return generated._snapshot_tracked_path(self.root, relative)

        with self.assertRaisesRegex(
            generated.RegistryError, "fixture filesystem denial"
        ) as failure:
            generated._snapshot_entries(self.paths, reader)
        self.assertIsInstance(failure.exception.__cause__, PermissionError)

    def reference_fixture(self) -> Path:
        directory = self.root / "git-authority"
        directory.mkdir()
        (directory / "HEAD").write_bytes(b"ref: refs/heads/main\n")
        for relative in (
            "refs/heads/main",
            "refs/tags/release",
            "refs/remotes/origin/main",
            "refs/replace/fixture",
            "refs/notes/commits",
            "refs/codex/other",
            "refs/codex/turn-diffs/other",
            "refs/codex/turn-diffs/captures-other/fixture",
            "refs/codex/turn-diffs/captures/fixture",
            "refs/codex/turn-diffs/checkpoints/fixture",
        ):
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"1" * 40 + b"\n")
        return directory

    def test_reference_parallel_reads_preserve_exact_digests_census_and_order(
        self,
    ) -> None:
        directory = self.reference_fixture()
        nodes = list((directory / "refs").rglob("*"))
        expected = {}
        for path in nodes:
            relative = path.relative_to(directory).as_posix()
            if relative in {"refs/codex", "refs/codex/turn-diffs"}:
                continue
            if any(
                relative == namespace or relative.startswith(namespace + "/")
                for namespace in (
                    "refs/codex/turn-diffs/captures",
                    "refs/codex/turn-diffs/checkpoints",
                )
            ):
                continue
            expected[f"@git/{relative}"] = generated.git_authority_digest(
                path, allow_directory=True
            )
        native = generated.git_authority_digest
        reads = []
        mutex = threading.Lock()

        def digest(path, **kwargs):
            with mutex:
                reads.append(path)
            return native(path, **kwargs)

        with patch.object(generated, "git_authority_digest", side_effect=digest):
            for _ in range(2):
                actual = generated.git_reference_snapshot(directory, "@git")
                self.assertEqual(expected, actual)
                self.assertEqual(list(expected), list(actual))
        self.assertCountEqual([directory / "HEAD", *nodes] * 2, reads)

    def test_reference_census_is_lazy_and_uses_same_bounded_reader(self) -> None:
        directory = self.reference_fixture()
        native = generated._snapshot_entries
        calls = []

        def entries(inputs, reader, **kwargs):
            self.assertNotIsInstance(inputs, (list, tuple))
            self.assertIs(iter(inputs), inputs)
            calls.append(kwargs)
            return native(inputs, reader, **kwargs)

        with patch.object(generated, "_snapshot_entries", side_effect=entries):
            generated.git_reference_snapshot(directory, "@git")
        self.assertEqual([{"wrap_os_errors": False}], calls)

    def test_reference_nodes_including_excluded_receipts_use_eight_real_workers(
        self,
    ) -> None:
        directory = self.reference_fixture()
        barrier = threading.Barrier(8)
        mutex = threading.Lock()
        native = generated.git_authority_digest
        started = 0
        active = 0
        maximum = 0

        def digest(path, **kwargs):
            nonlocal started, active, maximum
            if path == directory / "HEAD":
                return native(path, **kwargs)
            with mutex:
                started += 1
                ordinal = started
                active += 1
                maximum = max(maximum, active)
            try:
                if ordinal <= 8:
                    barrier.wait(timeout=5)
                return native(path, **kwargs)
            finally:
                with mutex:
                    active -= 1

        with patch.object(generated, "git_authority_digest", side_effect=digest):
            generated.git_reference_snapshot(directory, "@git")
        self.assertEqual(len(list((directory / "refs").rglob("*"))), started)
        self.assertEqual(8, maximum)
        self.assertEqual(0, active)

    def test_reference_head_alias_fails_before_any_parallel_work(self) -> None:
        directory = self.reference_fixture()
        (directory / "HEAD").write_bytes(
            b"ref: refs/codex/turn-diffs/captures/fixture\n"
        )
        with (
            patch.object(generated, "_snapshot_entries") as readers,
            self.assertRaisesRegex(generated.RegistryError, "cannot alias"),
        ):
            generated.git_reference_snapshot(directory, "@git")
        readers.assert_not_called()

    def test_reference_raw_read_failure_preserves_original_exception(self) -> None:
        directory = self.reference_fixture()
        path = directory / "refs/heads/main"
        native = Path.read_bytes
        for error in (PermissionError("exact permission"), OSError(5, "exact I/O")):
            calls = 0

            def read(candidate):
                nonlocal calls
                if candidate == path:
                    calls += 1
                    if calls == 2:
                        raise error
                return native(candidate)

            with (
                self.subTest(error=error),
                patch.object(Path, "read_bytes", read),
                self.assertRaises(type(error)) as failure,
            ):
                generated.git_reference_snapshot(directory, "@git")
            self.assertIs(error, failure.exception)
            self.assertIsNone(failure.exception.__cause__)

    def test_ordered_reader_keeps_first_input_error_and_joins_all_started_work(
        self,
    ) -> None:
        first = PermissionError("first census item")
        second = OSError(5, "second census item")
        later_failed = threading.Event()
        completed = []
        mutex = threading.Lock()

        def reader(index):
            try:
                if index == 0:
                    if not later_failed.wait(timeout=5):
                        raise AssertionError("second worker never started")
                    raise first
                if index == 1:
                    later_failed.set()
                    raise second
                return str(index), "exact"
            finally:
                with mutex:
                    completed.append(index)

        with self.assertRaises(PermissionError) as failure:
            generated._snapshot_entries(range(29), reader, wrap_os_errors=False)
        self.assertIs(first, failure.exception)
        self.assertCountEqual(range(16), completed)

    def test_reference_same_size_same_mtime_edit_is_reread_without_cache(self) -> None:
        directory = self.reference_fixture()
        path = directory / "refs/heads/main"
        before = generated.git_reference_snapshot(directory, "@git")
        metadata = path.stat()
        path.write_bytes(b"2" * 40 + b"\n")
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        after = generated.git_reference_snapshot(directory, "@git")
        self.assertNotEqual(
            before["@git/refs/heads/main"], after["@git/refs/heads/main"]
        )
        for key in set(before) - {"@git/refs/heads/main"}:
            self.assertEqual(before[key], after[key])

    def test_complete_cli_snapshot_filesystem_error_is_machine_readable_failure(
        self,
    ) -> None:
        for error in (
            generated.RegistryError("fixture snapshot error"),
            OSError("fixture Git authority read error"),
        ):
            with (
                self.subTest(error=error),
                patch.object(
                    generated, "load_registry", return_value=preparation_registry()
                ),
                patch.object(generated, "run_registry", side_effect=error),
                redirect_stdout(StringIO()) as output,
            ):
                code = generated.main(["--check", "--complete", "--json"])
            result = json.loads(output.getvalue())
            self.assertEqual(1, code)
            self.assertEqual("failed", result["status"])
            self.assertEqual(
                "certification.generated-artifact-integrity", result["operation_id"]
            )
            self.assertFalse(result["authoritative"])
            self.assertEqual([], result["results"])
            self.assertIn("fixture", result["reason"])

    def test_every_repeated_snapshot_rereads_same_size_bytes_without_a_cache(
        self,
    ) -> None:
        def reader(path: str) -> tuple[str, str]:
            return generated._snapshot_tracked_path(self.root, path)

        original = generated._snapshot_entries(self.paths, reader)
        path = self.root / "binary.bin"
        metadata = path.stat()
        path.write_bytes(bytes(reversed(range(256))) * 13)
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        updated = generated._snapshot_entries(self.paths, reader)
        self.assertNotEqual(original["binary.bin"], updated["binary.bin"])
        for relative in self.paths[1:]:
            self.assertEqual(original[relative], updated[relative])

    def test_global_lock_census_uses_repository_paths_without_cache_traversal(
        self,
    ) -> None:
        registry = preparation_registry()
        registry["artifacts"][0]["outputs"] = ["ignored/**"]
        registry["inventory"]["governed_output_patterns"] = [
            "ignored/**",
            "**/Cargo.lock",
        ]
        ignored = self.root / "ignored"
        ignored.mkdir()
        (ignored / "ordinary.txt").write_bytes(b"existing governed output")
        native = generated.expand_paths
        patterns = []

        def expand(root, declared):
            patterns.extend(declared)
            self.assertNotIn("**/Cargo.lock", declared)
            return native(root, declared)

        with patch.object(generated, "expand_paths", side_effect=expand):
            state = generated.integrity_snapshot(
                registry,
                self.root,
                lambda _root: {"new/Cargo.lock": "retained tracked census digest"},
            )
        self.assertEqual("retained tracked census digest", state["new/Cargo.lock"])
        self.assertEqual(["ignored/**", "ignored/**"], patterns)
        with self.assertRaisesRegex(
            generated.RegistryError, "unregistered governed derived output"
        ):
            generated.validate_inventory(registry, self.root, state)

    def test_governed_directory_links_aliases_and_nonregular_nodes_fail_before_skip_or_read(
        self,
    ) -> None:
        registry = preparation_registry()
        registry["artifacts"][0]["outputs"] = ["governed/**"]
        registry["inventory"]["governed_output_patterns"] = ["governed/**"]
        directory = self.root / "governed"
        directory.mkdir()
        native_symlink = Path.is_symlink
        native_resolve = Path.resolve
        for kind in ("link", "alias"):

            def is_symlink(path):
                return (kind == "link" and path == directory) or native_symlink(path)

            def resolve(path, *args, **kwargs):
                return (
                    self.root.parent
                    if kind == "alias" and path == directory
                    else native_resolve(path, *args, **kwargs)
                )

            with (
                self.subTest(kind=kind),
                patch.object(Path, "is_symlink", is_symlink),
                patch.object(Path, "resolve", resolve),
                self.assertRaisesRegex(
                    generated.RegistryError, "regular repository file"
                ),
            ):
                generated.integrity_snapshot(registry, self.root, lambda _root: {})
        nonregular = directory / "nonregular-node"
        nonregular.write_bytes(b"must not be read")
        native_lstat = Path.lstat
        native_read = Path.read_bytes
        reads = []

        def read(path):
            reads.append(path)
            return native_read(path)

        def metadata(path):
            observed = native_lstat(path)
            if path == nonregular:
                fields = list(observed)
                fields[0] = stat.S_IFIFO | 0o600
                return os.stat_result(fields)
            return observed

        with (
            patch.object(Path, "lstat", metadata),
            patch.object(Path, "read_bytes", read),
            self.assertRaisesRegex(generated.RegistryError, "regular repository file"),
        ):
            generated.integrity_snapshot(registry, self.root, lambda _root: {})
        self.assertNotIn(nonregular, reads)

    def test_governed_classification_reads_once_and_keeps_fresh_mode_and_bytes(
        self,
    ) -> None:
        path = self.root / "binary.bin"
        native_metadata = generated._snapshot_metadata
        native_lstat = Path.lstat
        native_read = Path.read_bytes
        classifications = []
        reads = []
        classified = False

        def classify(candidate):
            nonlocal classified
            classifications.append(candidate)
            result = native_metadata(candidate)
            classified = True
            return result

        def metadata(candidate):
            result = native_lstat(candidate)
            if candidate == path and classified:
                fields = list(result)
                fields[0] = stat.S_IFREG | 0o444
                return os.stat_result(fields)
            return result

        def read(candidate):
            reads.append(candidate)
            return native_read(candidate)

        expected = hashlib.sha256(b"292\0" + native_read(path)).hexdigest()
        with (
            patch.object(generated, "_snapshot_metadata", classify),
            patch.object(Path, "lstat", metadata),
            patch.object(Path, "read_bytes", read),
            patch.object(Path, "is_dir", side_effect=AssertionError("extra stat")),
            patch.object(Path, "is_file", side_effect=AssertionError("extra stat")),
        ):
            self.assertEqual(
                ("binary.bin", expected),
                generated._snapshot_governed_path(self.root, path),
            )
        self.assertEqual([path], classifications)
        self.assertEqual([path], reads)

    def test_governed_classification_denies_missing_and_every_nonregular_type(
        self,
    ) -> None:
        path = self.root / "binary.bin"
        initial = list(path.lstat())
        for kind in (
            None,
            stat.S_IFIFO,
            stat.S_IFSOCK,
            stat.S_IFCHR,
            stat.S_IFBLK,
            stat.S_IFLNK,
        ):
            fields = initial[:]
            fields[0] = (kind or 0) | 0o600
            metadata = None if kind is None else os.stat_result(fields)
            with (
                self.subTest(kind=kind),
                patch.object(generated, "_snapshot_metadata", return_value=metadata),
                patch.object(Path, "read_bytes") as read,
                self.assertRaisesRegex(
                    generated.RegistryError, "regular repository file"
                ),
            ):
                generated._snapshot_governed_path(self.root, path)
            read.assert_not_called()

    def test_governed_classification_errors_are_not_retried_or_read(self) -> None:
        path = self.root / "binary.bin"
        for error in (PermissionError(13, "denied"), OSError(5, "I/O")):
            with (
                self.subTest(error=error),
                patch.object(
                    generated, "_snapshot_metadata", side_effect=error
                ) as metadata,
                patch.object(Path, "read_bytes") as read,
                self.assertRaises(type(error)) as seen,
            ):
                generated._snapshot_governed_path(self.root, path)
            self.assertIs(error, seen.exception)
            metadata.assert_called_once_with(path)
            read.assert_not_called()

    def test_governed_snapshots_reread_same_size_and_mtime_content(self) -> None:
        path = self.root / "binary.bin"
        before = generated._snapshot_governed_path(self.root, path)
        metadata = path.stat()
        path.write_bytes(bytes(reversed(range(256))) * 13)
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        after = generated._snapshot_governed_path(self.root, path)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
