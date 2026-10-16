"""Real canonical source-identity commands in isolated, non-Git fixture trees."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tooling import deep_quality_certification as deep
from tooling import generated_artifacts as generated


ROOT = Path(__file__).resolve().parents[2]
FAMILY = "deep-quality-source-identities"
MANIFEST = "tests/certification/deep-quality/1.0/manifest.json"
FIXTURE = "tests/certification/deep-quality/1.0/fixtures/valid-evidence.json"


def source_paths(manifest: dict) -> set[str]:
    paths = {
        source["path"]
        for row in manifest["property_suites"]
        for source in row["sources"]
    }
    for row in manifest["fuzz_targets"]:
        paths.add(row["source_path"])
        if "corpus_seed_path" in row:
            paths.add(row["corpus_seed_path"])
    for row in manifest["mutants"]:
        paths.add(row["source_path"])
        paths.update(source["path"] for source in row["test_sources"])
    return paths


class DeepQualityArtifactFamilyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.current = generated.load_registry()
        self.family = next(
            row for row in self.current["artifacts"] if row["id"] == FAMILY
        )
        manifest = deep.load_json(ROOT / MANIFEST)
        paths = source_paths(manifest) | {
            MANIFEST,
            FIXTURE,
            "bindings/interop/fuzz/Cargo.toml",
            "governance/schemas/deep-quality-certification.schema.json",
            "tooling/deep_quality_certification.py",
            "tooling/tests/test_deep_quality_certification.py",
        }
        for relative in paths:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        # Own the fixture package even if an inherited PYTHONPATH contains the repo.
        (self.root / "tooling/__init__.py").write_text("", encoding="utf-8")
        self.registry = copy.deepcopy(self.current)
        self.registry["artifacts"] = [copy.deepcopy(self.family)]
        self.registry["inventory"] = {
            "required_families": [FAMILY],
            "governed_output_patterns": [MANIFEST, FIXTURE],
        }
        hygiene = generated.load_json(ROOT / "governance/repository-hygiene.json")
        group = next(
            row for row in hygiene["generated_paths"] if MANIFEST in row["paths"]
        )
        (self.root / "governance/repository-hygiene.json").write_text(
            json.dumps({"generated_paths": [group]}), encoding="utf-8"
        )
        self.assertEqual(
            0, self.execute(self.family["generator"]["command"]).returncode
        )

    def execute(self, command) -> generated.CommandResult:
        return generated.execute_command(command, self.root)

    def snapshot(self, _root=None) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): deep.file_fingerprint(path)
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def check(self, *, executor=None):
        return generated.run_registry(
            self.registry,
            self.root,
            check=True,
            complete=True,
            executor=executor or generated.execute_command,
            snapshotter=self.snapshot,
        )

    def stale(self) -> None:
        source = self.root / "core/src/safety_analysis.rs"
        source.write_bytes(source.read_bytes() + b"\n")

    def test_registry_and_independent_census_cover_outputs_and_every_source(self):
        self.assertIn(FAMILY, self.current["inventory"]["required_families"])
        self.assertEqual([MANIFEST, FIXTURE], self.family["outputs"])
        formatting = generated.load_json(ROOT / "governance/formatting.json")
        step = formatting["enforcement"]["targets"]["repository"][0]
        ownership = next(
            row
            for row in formatting["generated_or_serialized"]
            if row["paths"] == [MANIFEST, FIXTURE]
        )
        self.assertEqual(
            "Registered deep-quality source-identity serializer", ownership["strategy"]
        )
        for relative in (MANIFEST, FIXTURE):
            self.assertTrue(generated.matches_path(relative, step["exclude"]))
        for relative in source_paths(deep.load_json(ROOT / MANIFEST)):
            with self.subTest(source=relative):
                self.assertTrue(
                    generated.matches_path(
                        relative,
                        self.family["authoritative_sources"]
                        + self.family["generator_inputs"],
                    )
                )
        removed = copy.deepcopy(self.current)
        removed["artifacts"] = [
            row for row in removed["artifacts"] if row["id"] != FAMILY
        ]
        removed["inventory"]["required_families"].remove(FAMILY)
        for relative in (MANIFEST, FIXTURE):
            removed["inventory"]["governed_output_patterns"].remove(relative)
        with self.assertRaisesRegex(
            generated.RegistryError, "unregistered hygiene-derived output"
        ):
            generated.validate_inventory(removed, self.root, self.snapshot())

    def test_fresh_canonical_family_passes_without_mutation(self):
        before = self.snapshot()
        results = self.check()
        self.assertEqual(
            [(FAMILY, "passed")], [(x.artifact, x.status) for x in results]
        )
        self.assertEqual(before, self.snapshot())

    def test_stale_family_fails_before_build_backed_work_without_mutation(self):
        self.stale()
        expensive = copy.deepcopy(self.family)
        expensive["id"] = "fixture-build-backed"
        expensive["outputs"] = ["expensive-output.txt"]
        expensive["verification"] = {
            "method": "command-check",
            "phase": "build-backed",
            "command": ["forbidden-build"],
        }
        self.registry["artifacts"].insert(0, expensive)
        self.registry["inventory"]["required_families"].append(expensive["id"])
        (self.root / "expensive-output.txt").write_text("fresh", encoding="utf-8")
        calls = []

        def execute(command, cwd):
            calls.append(list(command))
            self.assertNotEqual(["forbidden-build"], list(command))
            return generated.execute_command(command, cwd)

        before = self.snapshot()
        results = self.check(executor=execute)
        self.assertEqual(
            [(FAMILY, "failed")], [(x.artifact, x.status) for x in results]
        )
        self.assertIn("source fingerprint changed", results[0].stderr)
        self.assertEqual([self.family["verification"]["command"]], calls)
        self.assertEqual(before, self.snapshot())

    def test_preparation_blocks_mixed_authority_then_explicit_refresh_is_idempotent(
        self,
    ):
        self.stale()
        before = self.snapshot()
        self.assertFalse(generated.preparation_allowed(self.family))
        report = generated.prepare_registry(
            self.registry, self.root, snapshotter=self.snapshot
        )
        self.assertEqual("blocked", report["status"])
        self.assertEqual([FAMILY], report["blocked_families"])
        self.assertEqual([], report["repairs"])
        self.assertEqual(before, self.snapshot())
        command = self.family["generator"]["command"]
        self.assertEqual(0, self.execute(command).returncode)
        after = self.snapshot()
        self.assertEqual([FIXTURE, MANIFEST], generated.changed_paths(before, after))
        self.assertEqual(0, self.execute(command).returncode)
        self.assertEqual(after, self.snapshot())
        self.assertEqual(["passed"], [row.status for row in self.check()])

    def test_missing_output_and_malformed_output_fail_without_writes(self):
        for relative in (MANIFEST, FIXTURE):
            path = self.root / relative
            original = path.read_bytes()
            for content in (None, b"{malformed"):
                with self.subTest(path=relative, content=content):
                    if content is None:
                        path.unlink()
                    else:
                        path.write_bytes(content)
                    before = self.snapshot()
                    self.assertEqual(["failed"], [row.status for row in self.check()])
                    self.assertNotEqual(
                        0,
                        self.execute(self.family["verification"]["command"]).returncode,
                    )
                    self.assertEqual(before, self.snapshot())
                    path.write_bytes(original)

    def test_check_and_refresh_cannot_rewrite_live_or_historical_evidence(self):
        path = self.root / FIXTURE
        fixture = deep.load_json(path)
        for kind in ("live", "historical"):
            with self.subTest(kind=kind):
                changed = copy.deepcopy(fixture)
                changed["evidence_kind"] = kind
                path.write_text(json.dumps(changed), encoding="utf-8")
                before = self.snapshot()
                self.assertNotEqual(
                    0, self.execute(self.family["verification"]["command"]).returncode
                )
                self.assertNotEqual(
                    0, self.execute(self.family["generator"]["command"]).returncode
                )
                self.assertEqual(before, self.snapshot())

    def test_noncanonical_serialization_fails_without_mutation(self):
        for relative in (MANIFEST, FIXTURE):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_text(json.dumps(deep.load_json(path)), encoding="utf-8")
                before = self.snapshot()
                execution = self.execute(self.family["verification"]["command"])
                self.assertNotEqual(0, execution.returncode)
                self.assertIn("not canonically serialized", execution.stderr)
                self.assertEqual(["failed"], [row.status for row in self.check()])
                self.assertEqual(before, self.snapshot())
                path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
