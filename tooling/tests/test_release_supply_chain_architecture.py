from __future__ import annotations

import json
import ast
import yaml
import unittest
from pathlib import Path

from tooling.architecture_fitness import certification_checkout_findings


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tooling/release_supply_chain.py"
SCHEMA = ROOT / "governance/schemas/release-supply-chain-certification.schema.json"
MANIFEST = ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
FIXTURE = (
    ROOT / "tests/certification/release-supply-chain/1.0/fixtures/valid-evidence.json"
)
TASK = ROOT / "docs/migration/records/release-supply-chain-certification.yaml"
CHANGE_CONTROL = ROOT / "governance/change-control.json"


class ReleaseSupplyChainArchitectureTests(unittest.TestCase):
    def test_controller_is_verification_only_and_offline_at_cp3(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for forbidden in (
            "from core",
            "import core",
            "from bindings",
            "import bindings",
            "requests",
            "socket",
            "shell=True",
            "git push",
            "npm publish",
            "dotnet nuget push",
            "twine upload",
        ):
            self.assertNotIn(forbidden, source)
        imported = {
            node.name
            for statement in ast.walk(ast.parse(source))
            if isinstance(statement, ast.Import)
            for node in statement.names
        }
        self.assertFalse(imported & {"urllib.request", "requests", "socket"})
        self.assertNotIn("urlopen(", source)
        self.assertIn("publication_authorized", source)
        self.assertIn("synthetic evidence cannot claim live profile authority", source)
        self.assertIn("release evidence requires a clean source tree", source)
        self.assertIn("evidence output directory must not already exist", source)
        self.assertIn("actions/upload-artifact@", source)
        self.assertIn("actions/download-artifact@", source)
        self.assertIn("checksum-subject", source)
        self.assertIn("provenance-subject", source)
        self.assertIn("false-pass", source)

    def test_schema_is_engineering_only_and_uses_locked_standards(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            "https://strling.dev/governance/release-supply-chain-certification.schema.json",
            schema["$id"],
        )
        serialized = json.dumps(schema)
        for required in (
            "SPDX-2.3-json",
            "https://in-toto.io/Statement/v1",
            "https://slsa.dev/provenance/v1",
            "publication_authorized",
            "synthetic-contract-fixture",
        ):
            self.assertIn(required, serialized)
        for forbidden in ("CompileRequest", "TargetArtifact", "language semantics"):
            self.assertNotIn(forbidden, serialized)

    def test_manifest_matches_exact_workflow_release_denominator(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        workflow = (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
        artifacts = manifest["artifacts"]
        self.assertEqual(17, len(artifacts))
        self.assertEqual(
            [
                "release:c",
                "release:cpp",
                "release:csharp",
                "release:dart",
                "release:fsharp",
                "release:go",
                "release:java",
                "release:kotlin",
                "release:lua",
                "release:perl",
                "release:php",
                "release:python",
                "release:r",
                "release:ruby",
                "release:rust",
                "release:swift",
                "release:typescript",
            ],
            [item["id"] for item in artifacts],
        )
        for item in artifacts:
            self.assertIn(f"    {item['compile_job']}:", workflow)
            self.assertIn(f"    {item['publish_job']}:", workflow)
            self.assertTrue(item["sbom_policy"]["required"])
            self.assertTrue(item["provenance_policy"]["required"])
            self.assertFalse(manifest["profile_policy"]["release"]["publication"])

        python_artifact = next(
            item for item in artifacts if item["id"] == "release:python"
        )
        self.assertEqual(
            ["interop-cargo", "python-binding"], python_artifact["dependency_roots"]
        )
        self.assertEqual(
            ["cargo", "python", "rustc"], python_artifact["toolchain_refs"]
        )

    def test_native_package_builds_prefetch_locked_cargo_graphs(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
        )
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            job = workflow["jobs"][artifact["compile_job"]]
            commands = "\n".join(step.get("run", "") for step in job["steps"])
            self.assertIn(
                "cargo +1.75.0 fetch --manifest-path bindings/interop/Cargo.toml --locked",
                commands,
            )
            assembly = [
                (step.get("working-directory"), step["run"])
                for step in job["steps"]
                if step.get("name", "").startswith("Assemble ")
            ]
            expected = " ".join(artifact["build_command"])
            self.assertEqual([(".", expected), (".rebuild", expected)], assembly)
            self.assertEqual(
                artifact["build_platforms"],
                [row["scope"] for row in job["strategy"]["matrix"]["include"]],
            )

    def test_profile_job_prepares_every_governed_component(self) -> None:
        from tooling.release_supply_chain import qualify_workflow, load_json

        result = qualify_workflow(ROOT, load_json(MANIFEST))
        self.assertTrue(result["exact_artifact_handoff"])
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "needs.verify-release.outputs.is_dry_run == 'true'",
            workflow["jobs"]["certify-release-supply-chain"]["if"],
        )
        for slug in ("java", "kotlin"):
            commands = "\n".join(
                step.get("run", "")
                for step in workflow["jobs"]["compile-" + slug]["steps"]
            )
            self.assertIn("--prepare-sdk", commands)
        reference = next(
            rule["configuration"]["historical_delivery_reference"]
            for rule in json.loads(
                (ROOT / "governance/architecture-rules.json").read_text(
                    encoding="utf-8"
                )
            )["rules"]
            if "historical_delivery_reference" in rule["configuration"]
        )
        findings, _ = certification_checkout_findings(
            (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8"),
            ".github/workflows/cd.yml",
            pull_request_base=False,
            historical_reference=reference,
        )
        self.assertEqual([], findings)

    def test_fixture_explicitly_denies_live_and_publication_authority(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual("synthetic-contract-fixture", fixture["evidence_kind"])
        self.assertFalse(fixture["publication_authorized"])
        details = fixture["checks"][0]["details"]
        self.assertTrue(details["synthetic"])
        self.assertFalse(details["live_artifact"])
        self.assertFalse(details["publication_authority"])

    def test_active_change_control_resolves_and_historical_task_scope_is_exact(
        self,
    ) -> None:
        change_control = json.loads(CHANGE_CONTROL.read_text(encoding="utf-8"))
        active_task = ROOT / change_control["active_task"]
        self.assertTrue(active_task.is_file())
        self.assertEqual(ROOT / "docs/migration/records", active_task.parent)
        task = TASK.read_text(encoding="utf-8")
        for required in (
            "- core/src/lib_public.rs",
            "- spec/frontends/simply/1.0/README.md",
            "one publishable strling crate",
            "publication, release creation, upload, tag push, and branch push",
            "package versions, support tiers, performance contracts",
            "SPDX 2.3 JSON",
            "SLSA Provenance v1",
        ):
            self.assertIn(required, task)


if __name__ == "__main__":
    unittest.main()
