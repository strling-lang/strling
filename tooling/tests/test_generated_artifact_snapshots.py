"""Exact, bounded snapshot reads using disposable filesystem fixtures only."""

from __future__ import annotations

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
        self.assertEqual(8, maximum)
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
        native_is_file = Path.is_file
        native_read = Path.read_bytes
        reads = []

        def read(path):
            reads.append(path)
            return native_read(path)

        with (
            patch.object(
                Path,
                "is_file",
                lambda path: path != nonregular and native_is_file(path),
            ),
            patch.object(Path, "read_bytes", read),
            self.assertRaisesRegex(generated.RegistryError, "regular repository file"),
        ):
            generated.integrity_snapshot(registry, self.root, lambda _root: {})
        self.assertNotIn(nonregular, reads)


if __name__ == "__main__":
    unittest.main()
