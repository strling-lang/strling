"""Sample-free preparation/integrity guards using synthetic canonical generators."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Sequence
from unittest.mock import patch

from tooling import generated_artifacts as generated
from tooling.security import KNOWN_LOCK_NAMES, SecurityEngine
from tooling.tests.test_generated_artifacts import fixture_registry


FAMILY = "fixture-output"
WRITE = ["fixture-generator", "--write"]
CHECK = ["fixture-generator", "--check"]
DEPENDENT = ["fixture-dependent"]


def preparation_registry() -> dict[str, object]:
    registry = fixture_registry()
    family = registry["artifacts"][0]
    family["preparation"] = {
        "automatic_regeneration": "canonical",
        "direct_dependents": [DEPENDENT],
    }
    registry["inventory"] = {
        "required_families": [FAMILY],
        "governed_output_patterns": ["output*"],
    }
    return registry


class GeneratedArtifactPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "source.txt").write_text("source", encoding="utf-8")
        (self.root / "generator.py").write_text(
            "# synthetic registered generator\n", encoding="utf-8"
        )
        self.registry = preparation_registry()
        self.calls: list[list[str]] = []
        self.authority_state = {"@git/HEAD": "old-head", "@git/index": "old-index"}
        self.write_output()

    def expected(self) -> str:
        return (
            json.dumps(
                {"source": (self.root / "source.txt").read_text(encoding="utf-8")},
                sort_keys=True,
            )
            + "\n"
        )

    def write_output(self) -> None:
        (self.root / "output.txt").write_text(self.expected(), encoding="utf-8")

    def stale(self) -> None:
        (self.root / "output.txt").write_text(
            '{"source": "previous"}\n', encoding="utf-8"
        )

    def snapshot(self, _root: Path) -> dict[str, str]:
        return {
            **self.authority_state,
            **{
                path.relative_to(self.root).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts
            },
        }

    def execute(self, command: Sequence[str], cwd: Path) -> generated.CommandResult:
        self.calls.append(list(command))
        self.assertEqual(self.root, cwd)
        if list(command) == WRITE:
            self.write_output()
            return generated.CommandResult(0)
        if list(command) == CHECK:
            try:
                text = (self.root / "output.txt").read_text(encoding="utf-8")
                json.loads(text)
            except (OSError, json.JSONDecodeError):
                return generated.CommandResult(
                    1, stderr="malformed or missing generated output"
                )
            return generated.CommandResult(
                0 if text == self.expected() else 1,
                stderr="" if text == self.expected() else "stale generated output",
            )
        if list(command) == DEPENDENT:
            return generated.CommandResult(0)
        self.fail(f"unregistered fixture command executed: {command}")

    def check(self) -> list[generated.ArtifactResult]:
        return generated.run_registry(
            self.registry,
            self.root,
            check=True,
            complete=True,
            executor=self.execute,
            snapshotter=self.snapshot,
        )

    def prepare(self, executor=None) -> dict[str, object]:
        return generated.prepare_registry(
            self.registry,
            self.root,
            executor=executor or self.execute,
            snapshotter=self.snapshot,
        )

    def test_fresh_complete_registered_state_passes_without_regeneration(self) -> None:
        before = self.snapshot(self.root)
        self.assertEqual(["passed"], [result.status for result in self.check()])
        report = self.prepare()
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["repairs"])
        self.assertFalse(report["authoritative"])
        self.assertFalse(report["candidate_frozen"])
        self.assertEqual(before, self.snapshot(self.root))
        self.assertNotIn(WRITE, self.calls)

    def test_stale_ordinary_family_is_detected_without_mutation(self) -> None:
        self.stale()
        before = self.snapshot(self.root)
        result = self.check()[0]
        self.assertEqual("failed", result.status)
        self.assertEqual("stale generated output", result.stderr)
        self.assertEqual([CHECK], self.calls)
        self.assertEqual(before, self.snapshot(self.root))

    def test_preparation_canonical_regeneration_recheck_and_dependents_are_idempotent(
        self,
    ) -> None:
        self.stale()
        report = self.prepare()
        self.assertEqual("passed", report["status"])
        self.assertEqual([CHECK, WRITE, WRITE, CHECK, DEPENDENT], self.calls)
        repair = report["repairs"][0]
        self.assertEqual(FAMILY, repair["artifact"])
        self.assertEqual(WRITE, repair["command"])
        self.assertEqual(["output.txt"], repair["changed_paths"])
        self.assertEqual([], repair["unexpected_paths"])
        self.assertTrue(repair["idempotent"])
        self.assertEqual(["passed"], [row["status"] for row in report["final_check"]])
        after = self.snapshot(self.root)
        self.calls.clear()
        second = self.prepare()
        self.assertEqual("passed", second["status"])
        self.assertEqual([], second["repairs"])
        self.assertEqual([CHECK, CHECK], self.calls)
        self.assertEqual(after, self.snapshot(self.root))

    def test_missing_registered_output_fails_check_and_is_canonically_repaired(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        result = self.check()[0]
        self.assertEqual("failed", result.status)
        self.assertIn("missing expected output", result.reason)
        self.assertEqual([], self.calls)
        self.assertEqual("passed", self.prepare()["status"])
        self.assertEqual([WRITE, WRITE, CHECK, DEPENDENT], self.calls)

    def test_missing_output_never_executes_an_escaping_or_missing_directory(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        for declared in (
            str(self.root),
            "../outside",
            "nested/../outside",
            "C:outside",
            "C:/outside",
            "\\outside",
            "//server/share",
            "missing-directory",
        ):
            with self.subTest(declared=declared):
                self.registry["artifacts"][0]["generator"]["working_directory"] = (
                    declared
                )
                with self.assertRaisesRegex(
                    generated.RegistryError, "working directory"
                ):
                    self.prepare()
                self.assertEqual([], self.calls)
                self.assertFalse((self.root / "output.txt").exists())

    def test_check_never_executes_an_unconfined_registered_directory(self) -> None:
        self.registry["artifacts"][0]["generator"]["working_directory"] = "C:outside"
        with self.assertRaisesRegex(generated.RegistryError, "working directory"):
            self.check()
        self.assertEqual([], self.calls)

    def test_missing_output_symlink_directory_is_rejected_before_regeneration(
        self,
    ) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        directory = self.root / "generator-directory"
        try:
            directory.symlink_to(outside.name, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        (self.root / "output.txt").unlink()
        self.registry["artifacts"][0]["generator"]["working_directory"] = (
            "generator-directory"
        )
        with self.assertRaisesRegex(generated.RegistryError, "working directory"):
            self.prepare()
        self.assertEqual([], self.calls)
        self.assertFalse((self.root / "output.txt").exists())

    def test_missing_output_resolved_directory_escape_is_rejected_portably(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        directory = self.root / "generator-directory"
        directory.mkdir()
        self.registry["artifacts"][0]["generator"]["working_directory"] = (
            "generator-directory"
        )
        native_resolve = Path.resolve

        def resolve(path, *arguments, **keywords):
            if path == directory:
                return self.root.parent
            return native_resolve(path, *arguments, **keywords)

        with (
            patch.object(Path, "resolve", resolve),
            self.assertRaisesRegex(generated.RegistryError, "working directory"),
        ):
            self.prepare()
        self.assertEqual([], self.calls)

    def test_generator_directory_is_revalidated_before_idempotence_execution(
        self,
    ) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        probe = self.root / "symlink-capability-probe"
        try:
            probe.symlink_to(outside.name, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        probe.unlink()
        directory = self.root / "generator-directory"
        directory.mkdir()
        self.registry["artifacts"][0]["generator"]["working_directory"] = (
            "generator-directory"
        )
        (self.root / "output.txt").unlink()

        def execute(command, cwd):
            self.calls.append(list(command))
            self.assertEqual(directory, cwd)
            self.assertEqual(WRITE, list(command))
            self.write_output()
            directory.rmdir()
            directory.symlink_to(outside.name, target_is_directory=True)
            return generated.CommandResult(0)

        with self.assertRaisesRegex(generated.RegistryError, "working directory"):
            self.prepare(execute)
        self.assertEqual([WRITE], self.calls)

    def test_idempotence_resolved_directory_escape_is_rejected_portably(self) -> None:
        directory = self.root / "generator-directory"
        directory.mkdir()
        self.registry["artifacts"][0]["generator"]["working_directory"] = (
            "generator-directory"
        )
        (self.root / "output.txt").unlink()
        native_resolve = Path.resolve
        escaped = False

        def resolve(path, *arguments, **keywords):
            if escaped and path == directory:
                return self.root.parent
            return native_resolve(path, *arguments, **keywords)

        def execute(command, cwd):
            nonlocal escaped
            self.calls.append(list(command))
            self.assertEqual(directory, cwd)
            self.assertEqual(WRITE, list(command))
            self.write_output()
            escaped = True
            return generated.CommandResult(0)

        with (
            patch.object(Path, "resolve", resolve),
            self.assertRaisesRegex(generated.RegistryError, "working directory"),
        ):
            self.prepare(execute)
        self.assertEqual([WRITE], self.calls)

    def test_complete_check_detects_output_mode_mutation_without_byte_changes(
        self,
    ) -> None:
        output = self.root / "output.txt"
        original = stat.S_IMODE(output.stat().st_mode)
        changed = original & ~stat.S_IWRITE
        output.chmod(changed)
        if stat.S_IMODE(output.stat().st_mode) == original:
            self.skipTest("filesystem cannot represent a file write-mode change")
        output.chmod(original)
        before = output.read_bytes()

        def execute(command, cwd):
            result = self.execute(command, cwd)
            output.chmod(changed)
            return result

        try:
            results = generated.run_registry(
                self.registry,
                self.root,
                check=True,
                complete=True,
                executor=execute,
                snapshotter=self.snapshot,
            )
            self.assertEqual("repository-state", results[-1].artifact)
            self.assertEqual("failed", results[-1].status)
            self.assertIn("output.txt", results[-1].reason)
            self.assertEqual(before, output.read_bytes())
            self.assertEqual([CHECK], self.calls)
        finally:
            output.chmod(original)

    def test_governed_output_symlink_is_rejected_before_any_command(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "same-bytes.txt"
        target.write_bytes((self.root / "output.txt").read_bytes())
        output = self.root / "output.txt"
        output.unlink()
        try:
            output.symlink_to(target)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"file symlink unavailable: {error}")
        with self.assertRaisesRegex(generated.RegistryError, "regular repository"):
            self.check()
        self.assertEqual([], self.calls)

    def test_governed_output_link_classification_is_rejected_portably(self) -> None:
        output = self.root / "output.txt"
        native_is_symlink = Path.is_symlink

        def is_symlink(path):
            return path == output or native_is_symlink(path)

        with (
            patch.object(Path, "is_symlink", is_symlink),
            self.assertRaisesRegex(generated.RegistryError, "regular repository"),
        ):
            self.check()
        self.assertEqual([], self.calls)

    def test_malformed_output_fails_and_ordinary_preparation_can_repair_it(
        self,
    ) -> None:
        (self.root / "output.txt").write_text("not JSON", encoding="utf-8")
        result = self.check()[0]
        self.assertEqual("failed", result.status)
        self.assertIn("malformed", result.stderr)
        self.assertEqual("passed", self.prepare()["status"])

    def test_governed_family_removed_from_registry_fails_before_execution(self) -> None:
        self.registry["artifacts"] = []
        with self.assertRaisesRegex(
            generated.RegistryError, "complete governed inventory"
        ):
            self.check()
        with self.assertRaises(generated.RegistryError):
            self.prepare()
        self.assertEqual([], self.calls)

    def test_unregistered_governed_output_fails_before_execution(self) -> None:
        (self.root / "output-rogue.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            generated.RegistryError, "unregistered governed derived output"
        ):
            self.check()
        self.assertEqual([], self.calls)

    def test_independent_hygiene_census_prevents_silent_registry_removal(self) -> None:
        path = self.root / "governance"
        path.mkdir()
        (path / "repository-hygiene.json").write_text(
            json.dumps(
                {
                    "generated_paths": [
                        {
                            "owner": "fixture governed outputs",
                            "paths": ["derived/*.json"],
                            "text_normalization": "serializer_owned",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.root / "derived").mkdir()
        (self.root / "derived/output.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            generated.RegistryError, "unregistered hygiene-derived"
        ):
            self.check()
        self.assertEqual([], self.calls)

    def test_historical_hygiene_metadata_excludes_only_noncurrent_archaeology(
        self,
    ) -> None:
        governance = self.root / "governance"
        governance.mkdir()
        hygiene_path = governance / "repository-hygiene.json"
        historical = {
            "owner": "Explicit non-normative migration-history fixture set",
            "paths": ["historical/*.json"],
            "text_normalization": "serializer_owned",
        }
        (self.root / "historical").mkdir()
        (self.root / "historical/retained.json").write_text("{}", encoding="utf-8")
        hygiene_path.write_text(
            json.dumps({"generated_paths": [historical]}), encoding="utf-8"
        )
        self.assertEqual(["passed"], [result.status for result in self.check()])
        self.assertEqual([CHECK], self.calls)
        self.calls.clear()
        historical["text_normalization"] = "repository_owned"
        hygiene_path.write_text(
            json.dumps({"generated_paths": [historical]}), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            generated.RegistryError, "historical fixture classification changed"
        ):
            self.check()
        self.assertEqual([], self.calls)

    def test_authority_bearing_stale_families_cannot_be_auto_regenerated(self) -> None:
        for authority in (
            "certification-evidence",
            "compatibility-evidence",
            "normative",
        ):
            with self.subTest(authority=authority):
                family = self.registry["artifacts"][0]
                family["authority"] = authority
                self.stale()
                before = self.snapshot(self.root)
                self.calls.clear()
                report = self.prepare()
                self.assertEqual("blocked", report["status"])
                self.assertEqual([FAMILY], report["blocked_families"])
                self.assertNotIn(WRITE, self.calls)
                self.assertEqual(before, self.snapshot(self.root))

    def test_protected_lock_license_and_performance_families_remain_denied(
        self,
    ) -> None:
        family = self.registry["artifacts"][0]
        for identity in (
            "package-manager-lockfiles",
            "dependency-license-evidence",
            "performance-resource-source-identities",
        ):
            with self.subTest(identity=identity):
                family["id"] = identity
                self.registry["inventory"]["required_families"] = [identity]
                self.stale()
                self.calls.clear()
                report = self.prepare()
                self.assertEqual("blocked", report["status"])
                self.assertEqual([identity], report["blocked_families"])
                self.assertEqual([CHECK], self.calls)

    def test_protected_failure_blocks_other_ordinary_regeneration_before_writes(
        self,
    ) -> None:
        protected = copy.deepcopy(self.registry["artifacts"][0])
        protected["id"] = "fixture-authority"
        protected["authority"] = "certification-evidence"
        protected["outputs"] = ["authority.json"]
        protected["verification"]["command"] = ["fixture-authority-check"]
        self.registry["artifacts"].append(protected)
        self.registry["inventory"]["required_families"].append(protected["id"])
        (self.root / "authority.json").write_text(
            "historical evidence", encoding="utf-8"
        )
        self.stale()

        def execute(command, cwd):
            if list(command) == ["fixture-authority-check"]:
                self.calls.append(list(command))
                return generated.CommandResult(1)
            return self.execute(command, cwd)

        before = self.snapshot(self.root)
        report = self.prepare(execute)
        self.assertEqual("blocked", report["status"])
        self.assertEqual(["fixture-authority"], report["blocked_families"])
        self.assertNotIn(WRITE, self.calls)
        self.assertEqual(before, self.snapshot(self.root))

    def test_preexisting_unrelated_dirty_work_and_authority_bytes_are_preserved(
        self,
    ) -> None:
        unrelated = self.root / "notes.txt"
        unrelated.write_text("owner edits", encoding="utf-8")
        authority = self.root / "historical-certification.json"
        authority.write_text("old authenticated attempt", encoding="utf-8")
        self.stale()
        report = self.prepare()
        self.assertEqual("passed", report["status"])
        self.assertEqual("owner edits", unrelated.read_text(encoding="utf-8"))
        self.assertEqual(
            "old authenticated attempt", authority.read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"@git/HEAD": "old-head", "@git/index": "old-index"}, self.authority_state
        )

    def test_broad_output_glob_cannot_admit_certification_authority_mutation(
        self,
    ) -> None:
        authority = (
            self.root / "tests/certification/performance-resource/1.0/baseline.json"
        )
        authority.parent.mkdir(parents=True)
        authority.write_text("historical baseline authority", encoding="utf-8")
        self.registry["artifacts"][0]["outputs"].append("tests/**")
        self.stale()

        def execute(command, cwd):
            result = self.execute(command, cwd)
            if list(command) == WRITE:
                authority.write_text("unauthorized authority change", encoding="utf-8")
            return result

        report = self.prepare(execute)
        self.assertIn(report["status"], {"blocked", "failed"})
        self.assertNotIn(DEPENDENT, self.calls)
        if report["status"] == "failed":
            self.assertIn(
                "tests/certification/performance-resource/1.0/baseline.json",
                report["repairs"][0]["unexpected_paths"],
            )

    def test_generator_unrelated_mutation_is_rejected_and_not_silently_rolled_back(
        self,
    ) -> None:
        self.stale()

        def execute(command, cwd):
            result = self.execute(command, cwd)
            if list(command) == WRITE:
                (self.root / "source.txt").write_text(
                    "unexpected source mutation", encoding="utf-8"
                )
            return result

        report = self.prepare(execute)
        self.assertEqual("failed", report["status"])
        self.assertEqual(["source.txt"], report["repairs"][0]["unexpected_paths"])
        self.assertEqual([CHECK, WRITE], self.calls)
        self.assertEqual(
            "unexpected source mutation",
            (self.root / "source.txt").read_text(encoding="utf-8"),
        )

    def test_generator_git_authority_mutation_is_rejected_before_dependents(
        self,
    ) -> None:
        for authority in ("@git/HEAD", "@git/index"):
            with self.subTest(authority=authority):
                self.authority_state = {
                    "@git/HEAD": "old-head",
                    "@git/index": "old-index",
                }
                self.stale()
                self.calls.clear()

                def execute(command, cwd):
                    result = self.execute(command, cwd)
                    if list(command) == WRITE:
                        self.authority_state[authority] = "changed"
                    return result

                report = self.prepare(execute)
                self.assertEqual("failed", report["status"])
                self.assertEqual([authority], report["repairs"][0]["unexpected_paths"])
                self.assertNotIn(DEPENDENT, self.calls)

    def test_real_fixture_git_index_staging_is_detected_by_integrity_snapshot(
        self,
    ) -> None:
        subprocess.run(
            ["git", "init", "--quiet"], cwd=self.root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "source.txt"], cwd=self.root, check=True, capture_output=True
        )
        before = generated.integrity_snapshot(self.registry, self.root, self.snapshot)
        self.stale()

        def execute(command, cwd):
            result = self.execute(command, cwd)
            if list(command) == WRITE:
                subprocess.run(
                    ["git", "add", "output.txt"],
                    cwd=self.root,
                    check=True,
                    capture_output=True,
                )
            return result

        report = self.prepare(execute)
        self.assertEqual("failed", report["status"])
        self.assertIn("@git/index", report["repairs"][0]["unexpected_paths"])
        self.assertNotIn(DEPENDENT, self.calls)
        after = generated.integrity_snapshot(self.registry, self.root, self.snapshot)
        self.assertNotEqual(before["@git/index"], after["@git/index"])

    def test_worktree_common_reference_mutation_stops_complete_check(self) -> None:
        def fixture_git(arguments, cwd):
            return subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
                check=True,
                capture_output=True,
                text=True,
            )

        fixture_git(["init", "--quiet"], self.root)
        fixture_git(["add", "source.txt", "generator.py", "output.txt"], self.root)
        fixture_git(
            [
                "-c",
                "user.name=Generated Artifact Fixture",
                "-c",
                "user.email=artifact-fixture@example.invalid",
                "commit",
                "--quiet",
                "--no-verify",
                "--no-gpg-sign",
                "-m",
                "Fixture-only initial state",
            ],
            self.root,
        )
        linked_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(linked_temporary.cleanup)
        linked = Path(linked_temporary.name)
        fixture_git(
            ["worktree", "add", "--quiet", "--detach", str(linked), "HEAD"],
            self.root,
        )
        commit = fixture_git(["rev-parse", "HEAD"], self.root).stdout.strip()
        common_ref = self.root / ".git" / "refs" / "heads" / "fixture-audit-reference"
        before = generated.integrity_snapshot(
            self.registry, linked, generated.snapshot_repository
        )

        def execute(command, cwd):
            self.calls.append(list(command))
            self.assertEqual(linked, cwd)
            self.assertEqual(CHECK, list(command))
            common_ref.write_text(commit + "\n", encoding="ascii")
            return generated.CommandResult(0)

        results = generated.run_registry(
            self.registry,
            linked,
            check=True,
            complete=True,
            executor=execute,
        )
        self.assertEqual("repository-state", results[-1].artifact)
        self.assertEqual("failed", results[-1].status)
        identity = "@git/common/refs/heads/fixture-audit-reference"
        self.assertIn(identity, results[-1].reason)
        self.assertNotIn(identity, before)
        self.assertIn(
            identity,
            generated.integrity_snapshot(
                self.registry, linked, generated.snapshot_repository
            ),
        )
        self.assertEqual([CHECK], self.calls)

    def test_complete_inventory_check_detects_git_authority_mutation(self) -> None:
        def execute(command, cwd):
            result = self.execute(command, cwd)
            if list(command) == CHECK:
                self.authority_state["@git/HEAD"] = "unexpected commit/ref change"
            return result

        results = generated.run_registry(
            self.registry,
            self.root,
            check=True,
            complete=True,
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual("repository-state", results[-1].artifact)
        self.assertEqual("failed", results[-1].status)
        self.assertIn("@git/HEAD", results[-1].reason)

    def test_nondeterministic_second_generation_is_rejected(self) -> None:
        self.stale()
        writes = 0

        def execute(command, cwd):
            nonlocal writes
            result = self.execute(command, cwd)
            if list(command) == WRITE:
                writes += 1
                if writes == 2:
                    (self.root / "output.txt").write_text(
                        "different repeat bytes", encoding="utf-8"
                    )
            return result

        report = self.prepare(execute)
        self.assertEqual("failed", report["status"])
        self.assertTrue(report["repairs"][0]["idempotence_failure"])
        self.assertFalse(report["repairs"][0]["idempotent"])
        self.assertNotIn(DEPENDENT, self.calls)

    def test_mutating_verifier_is_failure_and_blocks_all_regeneration(self) -> None:
        def execute(command, cwd):
            result = self.execute(command, cwd)
            if list(command) == CHECK:
                (self.root / "output.txt").write_text(
                    "verifier mutated output", encoding="utf-8"
                )
            return result

        report = self.prepare(execute)
        self.assertEqual("blocked", report["status"])
        self.assertIn("repository-state", report["blocked_families"])
        self.assertEqual([CHECK], self.calls)

    def test_mutating_verifier_stops_before_any_later_inventory_executor(self) -> None:
        other = copy.deepcopy(self.registry["artifacts"][0])
        other["id"] = "fixture-later"
        other["outputs"] = ["later-output.json"]
        other["verification"]["command"] = ["fixture-later-check"]
        self.registry["artifacts"].append(other)
        self.registry["inventory"]["required_families"].append(other["id"])
        (self.root / "later-output.json").write_text("{}", encoding="utf-8")

        def execute(command, cwd):
            if list(command) != CHECK:
                self.fail("later inventory command ran after a mutating checker")
            result = self.execute(command, cwd)
            (self.root / "output.txt").write_text(
                "unexpected check mutation", encoding="utf-8"
            )
            return result

        results = generated.run_registry(
            self.registry,
            self.root,
            check=True,
            complete=True,
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual("failed", results[-1].status)
        self.assertEqual([CHECK], self.calls)

    def test_dependent_failure_or_mutation_is_rejected(self) -> None:
        for failure in ("failed", "mutated"):
            with self.subTest(failure=failure):
                self.stale()
                self.calls.clear()

                def execute(command, cwd):
                    result = self.execute(command, cwd)
                    if list(command) == DEPENDENT:
                        if failure == "failed":
                            return generated.CommandResult(7)
                        (self.root / "notes.txt").write_text(
                            "unexpected", encoding="utf-8"
                        )
                    return result

                report = self.prepare(execute)
                self.assertEqual("failed", report["status"])
                dependent = report["repairs"][0]["direct_dependents"][0]
                self.assertEqual(
                    7 if failure == "failed" else 0, dependent["exit_code"]
                )
                self.assertEqual(
                    [] if failure == "failed" else ["notes.txt"],
                    dependent["unexpected_paths"],
                )

    def test_missing_generator_input_blocks_preparation_before_writes(self) -> None:
        (self.root / "source.txt").unlink()
        report = self.prepare()
        self.assertEqual("blocked", report["status"])
        self.assertEqual([FAMILY], report["blocked_families"])
        self.assertEqual([], self.calls)

    def test_cli_preparation_is_candidate_only_and_complete_check_is_immutable(
        self,
    ) -> None:
        preparation = {
            "status": "passed",
            "authoritative": False,
            "candidate_frozen": False,
        }
        result = generated.ArtifactResult(FAMILY, "passed", CHECK, 0, None)
        for arguments, expected in (
            (["--prepare", "--json"], "prepare"),
            (["--check", "--complete", "--json"], "check"),
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(generated, "load_registry", return_value=self.registry),
                patch.object(
                    generated, "prepare_registry", return_value=preparation
                ) as prepare,
                patch.object(generated, "run_registry", return_value=[result]) as check,
                redirect_stdout(StringIO()) as stdout,
            ):
                self.assertEqual(0, generated.main(arguments))
                payload = json.loads(stdout.getvalue())
                if expected == "prepare":
                    prepare.assert_called_once()
                    check.assert_not_called()
                    self.assertFalse(payload["authoritative"])
                else:
                    prepare.assert_not_called()
                    check.assert_called_once_with(
                        self.registry,
                        generated.ROOT,
                        check=True,
                        selected=None,
                        complete=True,
                    )

    def test_directory_output_link_rejection_is_portable_and_stops_preparation(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        directory = self.root / "output-directory"
        directory.mkdir()
        self.registry["artifacts"][0]["outputs"] = ["output-directory/**"]
        native_is_symlink = Path.is_symlink

        def is_symlink(path):
            return path == directory or native_is_symlink(path)

        for operation in (self.check, self.prepare):
            with (
                self.subTest(operation=operation.__name__),
                patch.object(Path, "is_symlink", is_symlink),
                self.assertRaisesRegex(generated.RegistryError, "regular repository"),
            ):
                operation()
        self.assertEqual([], self.calls)

    def test_directory_output_symlink_never_reaches_a_checker_or_generator(
        self,
    ) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        sentinel = Path(outside.name) / "sentinel.txt"
        sentinel.write_text("external bytes preserved", encoding="utf-8")
        (self.root / "output.txt").unlink()
        directory = self.root / "output-directory"
        try:
            directory.symlink_to(outside.name, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        self.registry["artifacts"][0]["outputs"] = ["output-directory/**"]
        for operation in (self.check, self.prepare):
            with (
                self.subTest(operation=operation.__name__),
                self.assertRaisesRegex(generated.RegistryError, "regular repository"),
            ):
                operation()
        self.assertEqual([], self.calls)
        self.assertEqual(
            "external bytes preserved", sentinel.read_text(encoding="utf-8")
        )

    def test_snapshot_rejects_directory_output_link_before_directory_skip(
        self,
    ) -> None:
        directory = self.root / "output-directory"
        directory.mkdir()
        self.registry["artifacts"][0]["outputs"] = ["output-directory/**"]
        native_is_symlink = Path.is_symlink

        def is_symlink(path):
            return path == directory or native_is_symlink(path)

        with (
            patch.object(Path, "is_symlink", is_symlink),
            self.assertRaisesRegex(generated.RegistryError, "regular repository file"),
        ):
            generated.integrity_snapshot(self.registry, self.root, self.snapshot)

    def test_registered_input_patterns_are_confined_in_every_role(self) -> None:
        family = self.registry["artifacts"][0]
        for owner, field in (
            (family, "authoritative_sources"),
            (family, "generator_inputs"),
            (family["generator"], "implementation_paths"),
        ):
            original = owner[field]
            for pattern in (
                "../outside.txt",
                "nested/../outside.txt",
                "/outside.txt",
                "C:outside.txt",
                "C:/outside.txt",
                "\\outside.txt",
                "nested\\outside.txt",
                "file.txt:stream",
                "nested/file.txt:stream",
                "//server/share",
            ):
                with self.subTest(role=field, pattern=pattern):
                    owner[field] = [pattern]
                    for operation in (self.check, self.prepare):
                        with self.assertRaisesRegex(
                            generated.RegistryError, "repository-relative"
                        ):
                            operation()
                    self.assertEqual([], self.calls)
            owner[field] = original

    def test_registered_input_alias_resolution_is_rejected_in_every_role(self) -> None:
        family = self.registry["artifacts"][0]
        source = self.root / "source.txt"
        native_resolve = Path.resolve

        def resolve(path, *arguments, **keywords):
            if path == source:
                return self.root.parent / "external-source.txt"
            return native_resolve(path, *arguments, **keywords)

        for owner, field in (
            (family, "authoritative_sources"),
            (family, "generator_inputs"),
            (family["generator"], "implementation_paths"),
        ):
            original = owner[field]
            source = self.root / original[0]
            with (
                self.subTest(role=field),
                patch.object(Path, "resolve", resolve),
                self.assertRaisesRegex(
                    generated.RegistryError, "regular repository path"
                ),
            ):
                self.check()
            owner[field] = original
        self.assertEqual([], self.calls)

    def test_missing_output_literal_or_glob_leaf_cannot_hide_a_parent_alias(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        directory = self.root / "output-directory"
        directory.mkdir()
        native_resolve = Path.resolve

        def resolve(path, *arguments, **keywords):
            if path == directory or directory in path.parents:
                return (
                    self.root.parent
                    / "external-directory"
                    / path.relative_to(directory)
                )
            return native_resolve(path, *arguments, **keywords)

        for output in ("output-directory/missing.h", "output-directory/*.json"):
            self.registry["artifacts"][0]["outputs"] = [output]
            for operation in (self.check, self.prepare):
                with (
                    self.subTest(output=output, operation=operation.__name__),
                    patch.object(Path, "resolve", resolve),
                    self.assertRaisesRegex(
                        generated.RegistryError, "prefix.*regular repository"
                    ),
                ):
                    operation()
        self.assertEqual([], self.calls)

    def test_empty_external_output_directory_link_cannot_receive_missing_outputs(
        self,
    ) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (self.root / "output.txt").unlink()
        directory = self.root / "output-directory"
        try:
            directory.symlink_to(outside.name, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        for output in ("output-directory/missing.h", "output-directory/*.json"):
            self.registry["artifacts"][0]["outputs"] = [output]
            for operation in (self.check, self.prepare):
                with (
                    self.subTest(output=output, operation=operation.__name__),
                    self.assertRaisesRegex(
                        generated.RegistryError, "prefix.*regular repository"
                    ),
                ):
                    operation()
        self.assertEqual([], self.calls)
        self.assertEqual([], list(Path(outside.name).iterdir()))

    def test_git_authority_mode_change_is_detected_without_byte_changes(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet"], cwd=self.root, check=True, capture_output=True
        )
        head = self.root / ".git" / "HEAD"
        original = stat.S_IMODE(head.stat().st_mode)
        changed = original & ~stat.S_IWRITE
        head.chmod(changed)
        if stat.S_IMODE(head.stat().st_mode) == original:
            self.skipTest("filesystem cannot represent authority file mode changes")
        head.chmod(original)
        original_bytes = head.read_bytes()

        def execute(command, cwd):
            result = self.execute(command, cwd)
            head.chmod(changed)
            return result

        try:
            results = generated.run_registry(
                self.registry,
                self.root,
                check=True,
                complete=True,
                executor=execute,
                snapshotter=self.snapshot,
            )
            self.assertEqual("repository-state", results[-1].artifact)
            self.assertEqual("failed", results[-1].status)
            self.assertIn("@git/HEAD", results[-1].reason)
            self.assertEqual(original_bytes, head.read_bytes())
        finally:
            head.chmod(original)

    def test_identical_byte_git_authority_node_replacement_is_detected(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet"], cwd=self.root, check=True, capture_output=True
        )
        head = self.root / ".git" / "HEAD"
        replacement = self.root / ".git" / "HEAD-replacement"
        original_bytes = head.read_bytes()
        replacement.write_bytes(original_bytes)
        replacement.chmod(stat.S_IMODE(head.stat().st_mode))
        if replacement.stat().st_ino == head.stat().st_ino:
            self.skipTest("filesystem cannot expose distinct authority node identities")

        def execute(command, cwd):
            result = self.execute(command, cwd)
            os.replace(replacement, head)
            return result

        results = generated.run_registry(
            self.registry,
            self.root,
            check=True,
            complete=True,
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual("repository-state", results[-1].artifact)
        self.assertEqual("failed", results[-1].status)
        self.assertIn("@git/HEAD", results[-1].reason)
        self.assertEqual(original_bytes, head.read_bytes())

    def test_git_authority_alias_resolution_is_rejected_portably(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet"], cwd=self.root, check=True, capture_output=True
        )
        head = self.root / ".git" / "HEAD"
        native_resolve = Path.resolve

        def resolve(path, *arguments, **keywords):
            if path == head:
                return self.root.parent / "identical-external-HEAD"
            return native_resolve(path, *arguments, **keywords)

        with (
            patch.object(Path, "resolve", resolve),
            self.assertRaisesRegex(
                generated.RegistryError, "Git authority.*regular node"
            ),
        ):
            self.check()
        self.assertEqual([], self.calls)

    def test_falsely_declared_control_outputs_block_before_any_generator(self) -> None:
        (self.root / "output.txt").unlink()
        family = self.registry["artifacts"][0]
        for output in (
            ".git",
            ".git/config",
            ".git/refs/heads/controlled",
            "toolchain.json",
            ".github/workflows/campaign.yml",
            "governance/generated-artifacts.json",
            "governance/schemas/generated-artifact-registry.schema.json",
        ):
            with self.subTest(output=output):
                family["outputs"] = [output]
                self.assertFalse(generated.preparation_allowed(family))
                report = self.prepare()
                self.assertEqual("blocked", report["status"])
                self.assertEqual([FAMILY], report["blocked_families"])
                self.assertEqual([], report["repairs"])
                self.assertEqual([], self.calls)

    def test_broad_control_output_globs_are_denied_even_without_current_matches(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        family = self.registry["artifacts"][0]
        for output in (".github/**", "governance/*.json", ".git/**", "toolchain.*"):
            with self.subTest(output=output):
                family["outputs"] = [output]
                report = self.prepare()
                self.assertEqual("blocked", report["status"])
                self.assertEqual([FAMILY], report["blocked_families"])
                self.assertEqual([], self.calls)

    def test_identity_only_and_unrelated_ordinary_projections_remain_eligible(
        self,
    ) -> None:
        family = self.registry["artifacts"][0]
        for output in (
            "output.txt",
            "governance/profile-source-definitions.json",
            "docs/toolchains.md",
            "derived/ordinary/*.json",
        ):
            with self.subTest(output=output):
                family["outputs"] = [output]
                self.assertTrue(generated.preparation_allowed(family))

    def test_every_native_lock_name_is_protected_before_root_or_nested_write(
        self,
    ) -> None:
        (self.root / "output.txt").unlink()
        family = self.registry["artifacts"][0]
        native = SecurityEngine(
            self.root, {"manifest_names": [], "manifest_suffixes": []}, tracked_files=[]
        )
        self.assertEqual(14, len(KNOWN_LOCK_NAMES))
        self.assertTrue(
            {"go.sum", "Package.resolved", "packages.lock.json"} <= KNOWN_LOCK_NAMES
        )
        for name in sorted(KNOWN_LOCK_NAMES):
            for output in (name, f"nested/{name}"):
                with self.subTest(output=output):
                    self.assertTrue(native._is_dependency_file(output))
                    family["outputs"] = [output]
                    self.assertFalse(generated.preparation_allowed(family))
                    report = self.prepare()
                    self.assertEqual("blocked", report["status"])
                    self.assertEqual([FAMILY], report["blocked_families"])
                    self.assertEqual([], report["repairs"])
                    self.assertEqual([], self.calls)
                    self.assertFalse((self.root / output).exists())

    def test_current_census_covers_every_native_root_and_nested_lock(self) -> None:
        current = generated.load_json(generated.DEFAULT_REGISTRY)
        patterns = current["inventory"]["governed_output_patterns"]
        self.registry["inventory"]["governed_output_patterns"] = ["output*", *patterns]
        for name in sorted(KNOWN_LOCK_NAMES):
            for relative in (name, f"unknown/{name}"):
                with self.subTest(relative=relative):
                    self.assertTrue(generated.matches_path(relative, patterns))
                    unknown = self.root / relative
                    unknown.parent.mkdir(parents=True, exist_ok=True)
                    unknown.write_text("unregistered lock", encoding="utf-8")
                    try:
                        with self.assertRaisesRegex(
                            generated.RegistryError,
                            "unregistered governed derived output",
                        ):
                            self.check()
                        self.assertEqual([], self.calls)
                    finally:
                        unknown.unlink()

    def test_separate_git_control_directory_inside_checkout_is_protected(self) -> None:
        directory = self.root / "authority-data"
        subprocess.run(
            ["git", "init", "--quiet", "--separate-git-dir", str(directory)],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        (self.root / "output.txt").unlink()
        self.registry["artifacts"][0]["outputs"] = ["authority-data/HEAD"]
        patterns = generated.protected_control_patterns(self.root)
        self.assertIn("authority-data", patterns)
        self.assertIn("authority-data/**", patterns)
        self.assertFalse(
            generated.preparation_allowed(
                self.registry["artifacts"][0], protected_patterns=patterns
            )
        )
        report = self.prepare()
        self.assertEqual("blocked", report["status"])
        self.assertEqual([FAMILY], report["blocked_families"])
        self.assertEqual([CHECK], self.calls)
        self.assertNotIn(WRITE, self.calls)

    def test_working_directory_stream_alias_syntax_is_rejected(self) -> None:
        for declared in ("directory:stream", "nested/directory:stream"):
            with (
                self.subTest(declared=declared),
                self.assertRaisesRegex(generated.RegistryError, "escapes repository"),
            ):
                generated.confined_working_directory(self.root, declared, FAMILY)
        self.assertEqual([], self.calls)

    def test_registered_globbed_regular_input_directories_remain_valid(self) -> None:
        directory = self.root / "input-directory"
        directory.mkdir()
        (directory / "child.txt").write_text("ordinary input", encoding="utf-8")
        self.registry["artifacts"][0]["authoritative_sources"].append(
            "input-directory/**"
        )
        self.assertEqual(["passed"], [item.status for item in self.check()])
        self.assertEqual([CHECK], self.calls)

    def phased_registry(self) -> dict[str, object]:
        registry = copy.deepcopy(self.registry)
        build = registry["artifacts"][0]
        build["id"] = "public-contract-snapshots"
        build["verification"]["phase"] = "build-backed"
        build["verification"]["command"] = ["fixture-build-backed"]
        build["outputs"] = ["output-build.txt"]
        cheap_a = copy.deepcopy(self.registry["artifacts"][0])
        cheap_a["id"] = "ordinary-a"
        cheap_a["verification"]["command"] = ["fixture-static-a"]
        cheap_b = copy.deepcopy(cheap_a)
        cheap_b["id"] = "ordinary-b"
        cheap_b["outputs"] = ["output-b.txt"]
        cheap_b["verification"]["command"] = ["fixture-static-b"]
        registry["artifacts"] = [build, cheap_a, cheap_b]
        registry["inventory"]["required_families"] = [
            item["id"] for item in registry["artifacts"]
        ]
        for name in ("output-build.txt", "output-b.txt"):
            (self.root / name).write_text("fresh", encoding="utf-8")
        return registry

    def test_complete_check_stably_places_build_backed_checks_last(self) -> None:
        registry = self.phased_registry()
        before = copy.deepcopy(registry)

        def execute(command, cwd):
            self.calls.append(list(command))
            self.assertEqual(self.root, cwd)
            return generated.CommandResult(0)

        result = generated.run_registry(
            registry,
            self.root,
            check=True,
            complete=True,
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual(
            ["ordinary-a", "ordinary-b", "public-contract-snapshots"],
            [item.artifact for item in result],
        )
        self.assertEqual(before, registry)
        self.assertEqual(
            [["fixture-static-a"], ["fixture-static-b"], ["fixture-build-backed"]],
            self.calls,
        )

    def test_stale_static_check_blocks_build_backed_checks(self) -> None:
        registry = self.phased_registry()

        def execute(command, _cwd):
            self.calls.append(list(command))
            return generated.CommandResult(1, stderr="stale ordinary output")

        result = generated.run_registry(
            registry,
            self.root,
            check=True,
            complete=True,
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual(["ordinary-a"], [item.artifact for item in result])
        self.assertEqual("failed", result[0].status)
        self.assertEqual([["fixture-static-a"]], self.calls)

    def test_missing_static_output_blocks_build_backed_checks(self) -> None:
        registry = self.phased_registry()
        (self.root / "output.txt").unlink()

        def executor(_command, _cwd):
            self.fail("expensive execution started")

        result = generated.run_registry(
            registry,
            self.root,
            check=True,
            complete=True,
            executor=executor,
            snapshotter=self.snapshot,
        )
        self.assertEqual(["ordinary-a"], [item.artifact for item in result])
        self.assertIn("missing expected output", result[0].reason)

    def test_legacy_and_selected_checks_keep_registry_order(self) -> None:
        registry = self.phased_registry()

        def execute(command, _cwd):
            self.calls.append(list(command))
            return generated.CommandResult(0)

        generated.run_registry(
            registry, self.root, check=True, executor=execute, snapshotter=self.snapshot
        )
        self.assertEqual(
            [["fixture-build-backed"], ["fixture-static-a"], ["fixture-static-b"]],
            self.calls,
        )
        self.calls.clear()
        generated.run_registry(
            registry,
            self.root,
            check=True,
            selected="ordinary-b",
            executor=execute,
            snapshotter=self.snapshot,
        )
        self.assertEqual([["fixture-static-b"]], self.calls)

    def test_unknown_verification_phase_fails_before_any_executor(self) -> None:
        registry = self.phased_registry()
        registry["artifacts"][0]["verification"]["phase"] = "skip-build"
        with self.assertRaisesRegex(
            generated.RegistryError, "unknown verification phase"
        ):
            generated.run_registry(
                registry,
                self.root,
                check=True,
                complete=True,
                executor=self.execute,
                snapshotter=self.snapshot,
            )
        self.assertEqual([], self.calls)

    def test_duplicate_and_non_utf8_governance_json_fails_closed(self) -> None:
        path = self.root / "governance.json"
        for payload in (b'{"artifacts": [], "artifacts": []}', b"\xff"):
            with self.subTest(payload=payload):
                path.write_bytes(payload)
                with self.assertRaises(generated.RegistryError):
                    generated.load_json(path)
        governance = self.root / "governance"
        governance.mkdir()
        (governance / "repository-hygiene.json").write_text(
            '{"generated_paths": [], "generated_paths": []}', encoding="utf-8"
        )
        with self.assertRaisesRegex(generated.RegistryError, "duplicate JSON property"):
            self.check()
        self.assertEqual([], self.calls)

    def test_json_preparation_errors_remain_machine_readable_and_non_authoritative(
        self,
    ) -> None:
        for failure_point in ("load_registry", "prepare_registry"):
            with (
                self.subTest(failure_point=failure_point),
                patch.object(
                    generated, "load_registry", return_value=self.registry
                ) as load,
                patch.object(generated, "prepare_registry") as prepare,
                redirect_stdout(StringIO()) as stdout,
                redirect_stderr(StringIO()) as stderr,
            ):
                target = load if failure_point == "load_registry" else prepare
                target.side_effect = generated.RegistryError(
                    "malformed/unregistered fixture"
                )
                self.assertEqual(2, generated.main(["--prepare", "--json"]))
                payload = json.loads(stdout.getvalue())
                self.assertEqual("generated-artifact-preparation", payload["operation"])
                self.assertEqual("failed", payload["status"])
                self.assertFalse(payload["authoritative"])
                self.assertFalse(payload["candidate_frozen"])
                self.assertEqual([], payload["repairs"])
                self.assertIn("malformed/unregistered", payload["reason"])
                self.assertEqual("", stderr.getvalue())
                if failure_point == "load_registry":
                    prepare.assert_not_called()

    def test_complete_check_json_error_keeps_exact_certification_identity(self) -> None:
        with (
            patch.object(
                generated,
                "load_registry",
                side_effect=generated.RegistryError("malformed registry"),
            ),
            redirect_stdout(StringIO()) as stdout,
        ):
            self.assertEqual(1, generated.main(["--check", "--complete", "--json"]))
            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                "certification.generated-artifact-integrity", payload["operation_id"]
            )
            self.assertEqual("certification-result-v1", payload["schema_version"])
            self.assertEqual("failed", payload["status"])

    def test_cli_cannot_mix_preparation_with_check_or_selected_family(self) -> None:
        for arguments in (
            ["--prepare", "--check"],
            ["--prepare", "--artifact", FAMILY],
            ["--prepare", "--complete"],
            [],
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(generated, "load_registry", return_value=self.registry),
                patch.object(
                    generated,
                    "prepare_registry",
                    side_effect=AssertionError("regeneration started"),
                ),
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(2, generated.main(arguments))


if __name__ == "__main__":
    unittest.main()
