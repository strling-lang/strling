from __future__ import annotations

import ast
import copy
import hashlib
import subprocess
import json
import tempfile
import unittest
from pathlib import Path

from tooling.product_documentation import fences, validate_manifest
from tooling.release_candidate import ROOT, render, scope, trust_projection
from tooling.documentation_programs import expected_proof, verify_proof


class ProductScopeTests(unittest.TestCase):
    def test_candidate_context_preserves_authority_and_limits_closure(self):
        policy = trust_projection(ROOT)
        original = json.loads(
            (ROOT / "governance/local-certification-trust.json").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "authorized_certifiers",
            "allowed_waivers",
            "required_profiles",
            "signature_namespace",
        ):
            self.assertEqual(original[key], policy[key])
        self.assertEqual(
            "tests/certification/release-candidate/1.0/current", policy["bundle_path"]
        )
        self.assertNotIn("README.md", policy["closure_paths"])
        self.assertTrue(
            all(
                not path.startswith(("bindings/", "tooling/", "core/", "spec/"))
                for path in policy["closure_paths"]
            )
        )

    def test_every_registered_route_and_target_is_projected(self):
        data = scope(ROOT)
        text = render(ROOT)
        for artifact in data["artifacts"]:
            self.assertIn(artifact["package_name"], text)
            self.assertIn(artifact["distribution_contract"]["tier"], text)
        for identity in data["claims"]:
            if identity.startswith("target:"):
                self.assertIn(identity, text)

    def test_distribution_cannot_omit_duplicate_or_reclassify_binding(self):
        manifest_path = "tests/certification/release-supply-chain/1.0/manifest.json"
        policy_path = "governance/release-policy.json"
        manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
        for mutation in ("omit", "duplicate", "tier", "platform"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                for relative in (manifest_path, policy_path):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((ROOT / relative).read_bytes())
                altered = copy.deepcopy(manifest)
                if mutation == "omit":
                    altered["artifacts"].pop()
                elif mutation == "duplicate":
                    altered["artifacts"].append(copy.deepcopy(altered["artifacts"][0]))
                else:
                    row = altered["artifacts"][0]["distribution_contract"]
                    row["tier" if mutation == "tier" else "platforms"] = (
                        "Preview" if mutation == "tier" else ["arm64"]
                    )
                (root / manifest_path).write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    scope(root)


class DocumentationInventoryTests(unittest.TestCase):
    def test_original_consumer_fixture_contract_is_preserved(self):
        from tooling.release_consumers import CONSUMER_FIXTURES

        source = subprocess.check_output(
            [
                "git",
                "show",
                "642cc21f8f5d5ccabde1bb893076e02c624247a7:tooling/release_consumers.py",
            ],
            cwd=ROOT,
            text=True,
        )
        historical = next(
            ast.literal_eval(node.value)
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "CONSUMER_FIXTURES"
                for target in node.targets
            )
        )
        self.assertEqual(historical, CONSUMER_FIXTURES)

    def test_documentation_manifest_identity_is_mandatory(self):
        manifest = json.loads(
            (ROOT / "tests/documentation/1.0/manifest.json").read_bytes()
        )
        result = {"documentation_examples": expected_proof(manifest, "python")}
        for value in (None, "0" * 64):
            with self.subTest(identity=value):
                result["documentation_manifest_sha256"] = value
                with self.assertRaises(ValueError):
                    verify_proof(ROOT, "python", result)

    def test_consumer_proof_rejects_missing_duplicate_substituted_or_unexecuted_results(
        self,
    ):
        manifest = json.loads(
            (ROOT / "tests/documentation/1.0/manifest.json").read_text(encoding="utf-8")
        )
        identity = hashlib.sha256(
            (ROOT / "tests/documentation/1.0/manifest.json").read_bytes()
        ).hexdigest()
        original = expected_proof(manifest, "python")
        self.assertTrue(original)
        verify_proof(
            ROOT,
            "python",
            {
                "documentation_examples": original,
                "documentation_manifest_sha256": identity,
            },
        )
        for mutation in (
            "missing",
            "duplicate",
            "substitute",
            "unexecuted",
            "wrong-route",
        ):
            with self.subTest(mutation=mutation):
                observed = copy.deepcopy(original)
                if mutation == "missing":
                    observed.pop()
                elif mutation == "duplicate":
                    observed.append(copy.deepcopy(observed[0]))
                elif mutation == "substitute":
                    observed[0]["sha256"] = "0" * 64
                elif mutation == "unexecuted":
                    observed[0]["status"] = "not_run"
                else:
                    observed[0]["id"] = "bindings/go/README.md#1"
                with self.assertRaises(ValueError):
                    verify_proof(
                        ROOT,
                        "python",
                        {
                            "documentation_examples": observed,
                            "documentation_manifest_sha256": identity,
                        },
                    )

    def fixture(self, root):
        path = root / "README.md"
        path.write_text("```strling\nsemantic strling 1.0;\n```\n", encoding="utf-8")
        block = fences(path.read_text(encoding="utf-8"))[0]
        return dict(
            schema_version="1.0.0",
            documents=["README.md"],
            examples=[
                dict(
                    id="README.md#1",
                    kind="canonical",
                    sha256=block["sha256"],
                    language="strling",
                    reason="Complete governed language example",
                    evidence="documentation.product-canonical-examples",
                )
            ],
        )

    def test_inventory_rejects_missing_duplicate_changed_unexecuted_examples(self):
        for mutation in (
            "missing",
            "duplicate",
            "changed",
            "unexecuted",
            "historical",
            "missing-document",
        ):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                manifest = self.fixture(root)
                if mutation == "missing":
                    manifest["examples"] = []
                elif mutation == "duplicate":
                    manifest["examples"] *= 2
                elif mutation == "changed":
                    manifest["examples"][0]["sha256"] = "0" * 64
                elif mutation in ("unexecuted", "historical"):
                    manifest["examples"][0]["kind"] = (
                        "historical" if mutation == "historical" else "diagram"
                    )
                else:
                    manifest["documents"] = []
                self.assertTrue(validate_manifest(root, manifest, ["README.md"]))

    def test_reviewed_inventory_passes_and_unclosed_fence_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                [], validate_manifest(root, self.fixture(root), ["README.md"])
            )
        with self.assertRaises(ValueError):
            fences("```python\nprint('not closed')\n")


if __name__ == "__main__":
    unittest.main()
