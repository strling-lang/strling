"""Adversarial reconstruction tests use synthetic records, never release proof."""

from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tooling.public_distribution import obligations
from tooling.release_candidate_evidence import (
    preview_expected,
    source_data,
    validate_preview_reports,
    validate_public_coverage,
    validate_public_producers,
    verify_candidate_evidence,
    PREVIEW_COMMANDS,
    reconstruct_packaging_inputs,
    validate_coordinate_preflight,
)
from tooling.evidence_bytes import encode
from tooling.release_supply_chain import document_fingerprint


ROOT = Path(__file__).resolve().parents[2]


class CandidateEvidenceTests(unittest.TestCase):
    def test_coordinate_preflight_is_complete_and_does_not_reserve_publication(self):
        observations = []
        from tooling.public_registries import coordinate_version

        for artifact in self.manifest["artifacts"]:
            row = dict(
                artifact_id=artifact["id"],
                registry=artifact["registry"],
                package_name=artifact["package_name"],
                ownership_confirmed=False,
            )
            if artifact["registry"] in {"conan", "cpan", "luarocks.org"}:
                row["status"] = "owner-specific-coordinate-unverified"
            else:
                row.update(
                    status="read-only-coordinate-observation",
                    coordinates=[
                        dict(
                            version=version,
                            coordinate=coordinate_version(
                                version, artifact["registry"]
                            ),
                        )
                        for version in ("4.0.0-rc.1", "4.0.0")
                    ],
                )
            observations.append(row)
        report = dict(
            status="read-only-preflight-completed",
            authoritative=False,
            publication_authorized=False,
            registry_mutation_authorized=False,
            rc_reserved=False,
            provisional_rc="4.0.0-rc.1",
            observations=observations,
        )
        validate_coordinate_preflight(self.manifest, report)
        for mutation in (
            "missing",
            "duplicate",
            "namespace",
            "owner",
            "reservation",
            "publication",
            "coordinate",
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(report)
                if mutation == "missing":
                    changed["observations"].pop()
                elif mutation == "duplicate":
                    changed["observations"].append(
                        copy.deepcopy(changed["observations"][0])
                    )
                elif mutation == "namespace":
                    changed["observations"][0]["package_name"] = "substituted"
                elif mutation == "owner":
                    changed["observations"][0]["ownership_confirmed"] = True
                elif mutation == "reservation":
                    changed["rc_reserved"] = True
                elif mutation == "publication":
                    changed["publication_authorized"] = True
                else:
                    changed["observations"][0]["coordinates"].pop()
                with self.assertRaises(ValueError):
                    validate_coordinate_preflight(self.manifest, changed)

    def test_nested_package_transport_requires_original_bytes_and_safe_paths(self):
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"original\r\nmetadata without final newline"
            source = "a" * 40
            payload = dict(
                certified_source=dict(commit=source),
                evidence_files=[
                    dict(
                        path="evidence/original.log",
                        bytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    )
                ],
            )
            (root / "attestation.json").write_text(
                json.dumps(dict(signed_payload=payload)), encoding="utf-8"
            )
            (root / "archive.json").write_bytes(encode(raw, "original.log", source))
            entries = [
                dict(
                    path=name,
                    role=role,
                    bytes=(root / name).stat().st_size,
                    sha256=hashlib.sha256((root / name).read_bytes()).hexdigest(),
                )
                for name, role in (
                    ("attestation.json", "staged-package-attestation"),
                    ("archive.json", "sealed-original-metadata"),
                )
            ]
            nested, _ = reconstruct_packaging_inputs(
                root, entries, source, root / "restored"
            )
            self.assertEqual(raw, (nested / "evidence/original.log").read_bytes())
            for index, mutation in enumerate(
                (
                    "missing-attestation",
                    "missing-archive",
                    "wrong-source",
                    "traversal",
                    "duplicate",
                    "altered-input",
                )
            ):
                with self.subTest(mutation=mutation):
                    changed = copy.deepcopy(entries)
                    changed_payload = copy.deepcopy(payload)
                    if mutation == "missing-attestation":
                        changed = changed[1:]
                    elif mutation == "missing-archive":
                        changed = changed[:1]
                    elif mutation == "wrong-source":
                        changed_payload["certified_source"]["commit"] = "b" * 40
                    elif mutation == "traversal":
                        changed_payload["evidence_files"][0]["path"] = (
                            "evidence/../../escape"
                        )
                    elif mutation == "duplicate":
                        changed_payload["evidence_files"].append(
                            copy.deepcopy(changed_payload["evidence_files"][0])
                        )
                    else:
                        changed[0]["sha256"] = "0" * 64
                    if mutation in {"wrong-source", "traversal", "duplicate"}:
                        (root / "attestation.json").write_text(
                            json.dumps(dict(signed_payload=changed_payload)),
                            encoding="utf-8",
                        )
                        changed[0].update(
                            bytes=(root / "attestation.json").stat().st_size,
                            sha256=hashlib.sha256(
                                (root / "attestation.json").read_bytes()
                            ).hexdigest(),
                        )
                    with self.assertRaises(ValueError):
                        reconstruct_packaging_inputs(
                            root, changed, source, root / ("rejected-" + str(index))
                        )
                    (root / "attestation.json").write_text(
                        json.dumps(dict(signed_payload=payload)), encoding="utf-8"
                    )

    def setUp(self):
        self.manifest = json.loads(
            (
                ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.examples = json.loads(
            (ROOT / "tests/documentation/1.0/manifest.json").read_text(encoding="utf-8")
        )
        self.source = dict(commit="a" * 40, dirty=False, tree_sha256="c" * 64)
        self.release = dict(
            source=self.source,
            artifacts=[
                dict(id=row["id"], subject=dict(sha256="b" * 64))
                for row in self.manifest["artifacts"]
            ],
            build_receipts=[
                dict(
                    receipt=dict(
                        scope="linux-x86_64",
                        consumer=dict(result=dict(native_sha256="d" * 64)),
                    )
                )
            ],
        )
        self.fixtures = {"synthetic-fixture": "e" * 64}
        self.documentation_sha256 = "f" * 64
        self.reports = []
        for row in self.manifest["artifacts"]:
            if row["distribution_contract"]["tier"] != "Preview":
                continue
            report = dict(
                status="passed",
                authority="bounded-preview-documentation",
                supported_claim=False,
                public_retrieval=False,
                engineering=False,
                source=self.source,
                artifact_id=row["id"],
                product_version="4.0.0",
                runner_scope="linux-x86_64",
                subject_sha256="b" * 64,
                fixture_sha256=self.fixtures,
                documentation_manifest_sha256=self.documentation_sha256,
                native_sha256="d" * 64,
                documentation_examples=preview_expected(self.examples, row["surface"]),
            )
            report["invocation_id"] = format(len(self.reports) + 1, "032x")
            report["command_evidence"] = [
                dict(
                    command=[command],
                    exit_code=0,
                    metadata_sha256="e" * 64,
                    metadata=f"command-{index}.json",
                )
                for index, command in enumerate(PREVIEW_COMMANDS[row["surface"]])
            ]
            report["evidence_fingerprint"] = document_fingerprint(report)
            self.reports.append(report)

    def validate(self, reports):
        validate_preview_reports(
            reports=reports,
            manifest=self.manifest,
            examples=self.examples,
            release=self.release,
            fixture_hashes=self.fixtures,
            documentation_sha256=self.documentation_sha256,
            product_version="4.0.0",
        )

    def test_complete_preview_records_preserve_bounded_claim(self):
        self.validate(self.reports)

    def test_preview_proof_rejects_omissions_substitution_and_false_authority(self):
        for mutation in (
            "missing",
            "duplicate",
            "wrong-route",
            "source",
            "dirty",
            "support",
            "engineering",
            "public",
            "version",
            "scope",
            "native",
            "subject",
            "fixtures",
            "documentation-manifest",
            "missing-example",
            "duplicate-example",
            "example-hash",
            "unexecuted",
            "missing-command",
            "failed-command",
            "missing-invocation",
            "fingerprint",
        ):
            with self.subTest(mutation=mutation):
                reports = copy.deepcopy(self.reports)
                report = reports[0]
                if mutation == "missing":
                    reports.pop()
                elif mutation == "duplicate":
                    reports.append(copy.deepcopy(report))
                elif mutation == "wrong-route":
                    report["artifact_id"] = "release:c"
                elif mutation == "source":
                    report["source"]["commit"] = "f" * 40
                elif mutation == "dirty":
                    report["source"]["dirty"] = True
                elif mutation in {"support", "engineering", "public"}:
                    report[
                        {
                            "support": "supported_claim",
                            "engineering": "engineering",
                            "public": "public_retrieval",
                        }[mutation]
                    ] = True
                elif mutation in {"version", "scope", "native", "subject"}:
                    report[
                        {
                            "version": "product_version",
                            "scope": "runner_scope",
                            "native": "native_sha256",
                            "subject": "subject_sha256",
                        }[mutation]
                    ] = "incorrect"
                elif mutation == "documentation-manifest":
                    report["documentation_manifest_sha256"] = "0" * 64
                elif mutation == "fixtures":
                    report["fixture_sha256"] = {}
                elif mutation == "missing-example":
                    report["documentation_examples"].pop()
                elif mutation == "duplicate-example":
                    report["documentation_examples"].append(
                        copy.deepcopy(report["documentation_examples"][0])
                    )
                elif mutation == "example-hash":
                    report["documentation_examples"][0]["sha256"] = "0" * 64
                elif mutation == "unexecuted":
                    report["documentation_examples"][0]["status"] = "not_run"
                elif mutation == "missing-command":
                    report["command_evidence"].pop()
                elif mutation == "failed-command":
                    report["command_evidence"][0]["exit_code"] = 1
                elif mutation == "missing-invocation":
                    del report["invocation_id"]
                if mutation == "fingerprint":
                    report["evidence_fingerprint"] = "0" * 64
                else:
                    report["evidence_fingerprint"] = document_fingerprint(
                        report, "evidence_fingerprint"
                    )
                with self.assertRaises(ValueError):
                    self.validate(reports)

    def public_fixture(self):
        required = obligations(self.manifest)
        scopes = {
            (row["artifact_id"], row["platform"])
            for row in required
            if row["platform"] is not None
        }
        return dict(
            source=self.source["commit"],
            status="passed-current-source-staged-qualification",
            public_release_verified=False,
            publication_authorized=False,
            artifact_routes=len(self.manifest["artifacts"]),
            supported_consumer_scopes=len(scopes),
            public_obligations=len(required),
            coverage=[
                dict(
                    row,
                    status="READY",
                    authority="synthetic" if row["platform"] is None else "staged",
                    evidence="synthetic-record.json",
                )
                for row in required
            ],
        )

    def test_public_denominator_and_authority_are_reconstructed(self):
        validate_public_coverage(
            self.manifest, self.public_fixture(), source_sha=self.source["commit"]
        )
        for mutation in (
            "missing",
            "duplicate",
            "scope",
            "source",
            "public",
            "publication",
            "status",
            "evidence",
        ):
            with self.subTest(mutation=mutation):
                proof = self.public_fixture()
                if mutation == "missing":
                    proof["coverage"].pop()
                elif mutation == "duplicate":
                    proof["coverage"].append(copy.deepcopy(proof["coverage"][0]))
                elif mutation == "scope":
                    proof["coverage"][0]["tier"] = "Preview"
                elif mutation == "source":
                    proof["source"] = "0" * 40
                elif mutation in {"public", "publication"}:
                    proof[
                        "public_release_verified"
                        if mutation == "public"
                        else "publication_authorized"
                    ] = True
                elif mutation == "status":
                    proof["coverage"][0]["status"] = "VERIFIED"
                else:
                    del proof["coverage"][0]["evidence"]
                with self.assertRaises(ValueError):
                    validate_public_coverage(
                        self.manifest, proof, source_sha=self.source["commit"]
                    )

    def test_omitted_required_roots_and_noncommit_source_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_candidate_evidence(ROOT, self.source["commit"], ROOT, [])
        with self.assertRaises(ValueError):
            with source_data(ROOT, "--invalid-source"):
                self.fail("non-commit source was accepted")

    def test_public_coverage_requires_actual_matching_producer_results(self):
        proof = self.public_fixture()
        records = {}
        for row in proof["coverage"]:
            identity, scope = row["artifact_id"], row["platform"]
            relative = identity + ":" + str(scope)
            row["evidence"] = relative
            if scope is None:
                records[relative] = dict(
                    artifact_id=identity,
                    authority="synthetic",
                    publication_authorized=False,
                    observations=[
                        dict(
                            entry,
                            authority="synthetic",
                            status="READY"
                            if entry["platform"] is None
                            else "VERIFYING",
                        )
                        for entry in obligations(self.manifest)
                        if entry["artifact_id"] == identity
                    ],
                )
            else:
                result = dict(
                    status="passed",
                    source_outcome="succeeded",
                    target_pattern="abc",
                    kernel_mismatch_rejected=True,
                    target_profile_mismatch_rejected=True,
                    linked_package_version="4.0.0",
                    documentation_manifest_sha256=self.documentation_sha256,
                    documentation_examples=preview_expected(
                        self.examples, identity.split(":")[1]
                    ),
                )
                receipt = dict(
                    artifact_id=identity,
                    scope=scope,
                    product_version="4.0.0",
                    authority="staged",
                    status="READY",
                    publication_authorized=False,
                    fixture_sha256=self.fixtures,
                    result=result,
                    toolchains=[dict(status="passed")],
                )
                receipt["receipt_fingerprint"] = document_fingerprint(receipt)
                row["receipt_fingerprint"] = receipt["receipt_fingerprint"]
                records[relative] = dict(
                    artifact_id=identity, status="passed", receipt=receipt
                )

        def verify(observed, coverage=proof):
            validate_public_producers(
                self.manifest,
                coverage,
                self.examples,
                self.fixtures,
                "4.0.0",
                self.documentation_sha256,
                observed.__getitem__,
            )

        verify(records)
        artifact = next(
            key for key, value in records.items() if "observations" in value
        )
        consumer = next(
            key
            for key, value in records.items()
            if "receipt" in value
            and value["receipt"]["result"]["documentation_examples"]
        )
        for mutation in (
            "missing-observation",
            "false-ready",
            "failed-result",
            "missing-example",
            "substituted-kernel",
            "wrong-source-fixtures",
            "documentation-manifest",
            "fingerprint",
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(records)
                if mutation == "missing-observation":
                    changed[artifact]["observations"].pop()
                elif mutation == "false-ready":
                    changed[artifact]["observations"][0]["status"] = "VERIFIED"
                elif mutation == "failed-result":
                    changed[consumer]["receipt"]["result"]["status"] = "failed"
                elif mutation == "missing-example":
                    changed[consumer]["receipt"]["result"][
                        "documentation_examples"
                    ] = []
                elif mutation == "substituted-kernel":
                    changed[consumer]["receipt"]["result"][
                        "kernel_mismatch_rejected"
                    ] = False
                elif mutation == "documentation-manifest":
                    changed[consumer]["receipt"]["result"][
                        "documentation_manifest_sha256"
                    ] = "0" * 64
                elif mutation == "wrong-source-fixtures":
                    changed[consumer]["receipt"]["fixture_sha256"] = {}
                else:
                    changed[consumer]["receipt"]["receipt_fingerprint"] = "0" * 64
                changed_proof = copy.deepcopy(proof)
                if mutation != "fingerprint":
                    receipt = changed[consumer]["receipt"]
                    receipt["receipt_fingerprint"] = document_fingerprint(
                        receipt, "receipt_fingerprint"
                    )
                    for entry in changed_proof["coverage"]:
                        if entry["evidence"] == consumer:
                            entry["receipt_fingerprint"] = receipt[
                                "receipt_fingerprint"
                            ]
                with self.assertRaises(ValueError):
                    verify(changed, changed_proof)

    def test_source_snapshot_reads_exact_git_data_without_importing_it(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        expected = subprocess.check_output(
            ["git", "show", head + ":README.md"], cwd=ROOT
        )
        with source_data(ROOT, head) as root:
            self.assertEqual(expected, (root / "README.md").read_bytes())

    def test_source_snapshot_handles_long_evidence_paths_in_a_deep_temp_root(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            deep = base / ("x" * max(1, 190 - len(str(base))))
            deep.mkdir()
            with patch("tempfile.tempdir", str(deep)):
                with source_data(ROOT, head) as root:
                    configured = subprocess.check_output(
                        ["git", "config", "--local", "core.longpaths"],
                        cwd=root,
                        text=True,
                    ).strip()
                    self.assertEqual("true", configured)
                    self.assertEqual(
                        subprocess.check_output(
                            ["git", "show", head + ":README.md"], cwd=ROOT
                        ),
                        (root / "README.md").read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main()
