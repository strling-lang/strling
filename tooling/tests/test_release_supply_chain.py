from __future__ import annotations

import copy
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import Draft202012Validator

from tooling.release_supply_chain import (
    ARTIFACT_IDS,
    MANIFEST_PATH,
    OIDC_ARTIFACT_IDS,
    SCHEMA_PATH,
    VALID_FIXTURE_PATH,
    ReleaseSupplyChainError,
    _dependency_resolution,
    _spdx_document,
    _surface_members,
    artifact_scopes,
    scoped_artifact,
    _surface_identity,
    authenticate_source,
    capture_build_receipt,
    document_fingerprint,
    load_build_receipts,
    load_json,
    produce_bundle,
    qualify_workflow,
    run_contract_check,
    run_profile_certification,
    synthetic_evidence,
    validate_contract_fixture,
    validate_evidence,
    validate_manifest,
    validate_schema,
    verify_bundle,
    canonical_json,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")


def write_archive(path: Path, *, variant: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lowered = path.name.lower()
    if "/bindings/cpp/" in path.as_posix() and lowered.endswith(".tgz"):
        recipe, binary = f"recipe{variant}", f"b/binary{variant}/p"
        pkglist = {
            "strling/1.0.0": {
                "revisions": {
                    "recipe-revision": {
                        "timestamp": variant,
                        "recipe_folder": recipe,
                        "packages": {
                            "package-id": {
                                "info": {"settings": {"arch": "x86_64"}},
                                "revisions": {
                                    "package-revision": {
                                        "timestamp": variant,
                                        "package_folder": binary,
                                    }
                                },
                            }
                        },
                    }
                }
            }
        }
        entries = {
            "pkglist.json": json.dumps(pkglist).encode(),
            recipe + "/export/conanfile.py": b"fixture recipe",
            binary + "/lib/libstrling.a": b"fixture static library",
            binary + "/conanmanifest.txt": f"{variant}\nfile: exact-digest\n".encode(),
        }
        with tarfile.open(path, "w:gz") as archive:
            for name, payload in entries.items():
                info = tarfile.TarInfo(name)
                info.size, info.mtime = len(payload), variant
                archive.addfile(info, io.BytesIO(payload))
    elif lowered.endswith((".jar", ".nupkg", ".whl", ".zip")):
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("payload.txt")
            info.date_time = (2020 + variant, 1, 1, 0, 0, 0)
            info.create_system = 3
            archive.writestr(info, b"governed payload")
    elif lowered.endswith((".tar.gz", ".tgz", ".crate", ".gem")):
        with tarfile.open(path, "w") as archive:
            payload = b"governed payload"
            info = tarfile.TarInfo("payload.txt")
            info.size = len(payload)
            info.mtime = variant
            archive.addfile(info, io.BytesIO(payload))
    else:
        path.write_text("governed payload\n", encoding="utf-8", newline="\n")


def materialize_artifacts(
    root: Path, manifest: dict[str, Any], *, variant: int
) -> None:
    for artifact in manifest["artifacts"]:
        artifact_variant = (
            0 if artifact["reproducibility"]["mode"] == "byte-for-byte" else variant
        )
        (root / artifact["package_root"]).mkdir(parents=True, exist_ok=True)
        (root / artifact["working_directory"]).mkdir(parents=True, exist_ok=True)
        patterns = artifact["artifact_policy"].get("platform_patterns")
        patterns = (
            sorted({p for rows in patterns.values() for p in rows})
            if patterns
            else artifact["artifact_policy"]["patterns"]
        )
        for pattern in patterns:
            relative = pattern.replace("VERSION", "1.0.0").replace("*", "fixture")
            path = root / relative
            if (
                artifact["artifact_policy"]["subject_kind"] == "source-tree"
                or relative == artifact["package_root"]
            ):
                path.mkdir(parents=True, exist_ok=True)
                (path / "fixture.txt").write_text(
                    "governed source tree\n", encoding="utf-8", newline="\n"
                )
            else:
                if artifact["id"] == "release:cpp" and path.name.endswith(".tgz"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    alias = "recipe" + str(artifact_variant)
                    package_list = {
                        "strling/1.0.0": {
                            "revisions": {
                                "a" * 32: {
                                    "recipe_folder": alias,
                                    "timestamp": artifact_variant,
                                    "packages": {},
                                }
                            }
                        }
                    }
                    with tarfile.open(path, "w") as archive:
                        for name, payload in {
                            "pkglist.json": json.dumps(package_list).encode(),
                            alias + "/conanmanifest.txt": str(artifact_variant).encode()
                            + b"\nconanfile.py: exact\n",
                            alias + "/conanfile.py": b"fixture recipe data",
                        }.items():
                            entry = tarfile.TarInfo(name)
                            entry.size = len(payload)
                            entry.mtime = artifact_variant
                            archive.addfile(entry, io.BytesIO(payload))
                else:
                    write_archive(
                        path,
                        variant=0
                        if path.name.endswith(".upload.zip")
                        else artifact_variant,
                    )


def write_workflow(root: Path, manifest: dict[str, Any]) -> None:
    import shutil

    path = root / manifest["workflow_policy"]["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        Path(MANIFEST_PATH).parents[4] / manifest["workflow_policy"]["path"], path
    )


def prepare_producer_root(
    root: Path, manifest: dict[str, Any], *, variant: int
) -> None:
    write_json(
        root / "governance/release-policy.json",
        {
            "product": {"version": "1.0.0"},
            "support_claims": [
                {
                    "id": a["distribution_contract"]["support_claim"],
                    "tier": a["distribution_contract"]["tier"],
                    "scope": a["distribution_contract"]["scope"],
                    "platforms": a["distribution_contract"]["platforms"],
                }
                for a in manifest["artifacts"]
            ],
        },
    )
    dependency_ids = sorted(
        {
            dependency
            for artifact in manifest["artifacts"]
            for dependency in artifact["dependency_roots"]
        }
    )
    write_json(
        root / manifest["security_policy"],
        {
            "dependency_roots": [
                {
                    "id": dependency,
                    "ecosystem": "fixture",
                    "manifests": [],
                    "locks": [],
                    "risk_mode": "no_dependencies",
                    "integrity_mode": "no_external_dependencies",
                }
                for dependency in dependency_ids
            ]
        },
    )
    write_json(root / manifest["toolchain_authority"], {})
    write_workflow(root, manifest)
    materialize_artifacts(root, manifest, variant=variant)


class ReleaseSupplyChainContractTests(unittest.TestCase):
    def test_conan_upload_fixture_is_a_stable_zip_across_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contents = []
            for clock in (1000, 2000):
                path = Path(temporary) / str(clock) / "bindings/cpp/package.upload.zip"
                with patch("gzip.time.time", return_value=clock):
                    write_archive(path, variant=0)
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(b"governed payload", archive.read("payload.txt"))
                contents.append(path.read_bytes())
            self.assertEqual(contents[0], contents[1])

    def setUp(self) -> None:
        self.manifest = load_json(MANIFEST_PATH)
        self.fixture = load_json(VALID_FIXTURE_PATH)

    def assert_rejected(
        self,
        callable_: Any,
        code: str,
    ) -> ReleaseSupplyChainError:
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            callable_()
        self.assertEqual(code, raised.exception.code)
        return raised.exception

    @staticmethod
    def resign_evidence(evidence: dict[str, Any]) -> None:
        evidence["evidence_fingerprint"] = document_fingerprint(
            evidence, "evidence_fingerprint"
        )

    @staticmethod
    def resign_fixture(fixture: dict[str, Any]) -> None:
        fixture["evidence_fingerprint"] = document_fingerprint(
            fixture, "evidence_fingerprint"
        )

    def test_schema_manifest_fixture_and_contract_check_pass(self) -> None:
        schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
        validate_schema(self.manifest, label="manifest")
        validate_manifest(self.manifest)
        validate_contract_fixture(self.fixture, self.manifest)
        result = run_contract_check()
        self.assertEqual("passed", result["status"])
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(17, result["artifact_count"])

    def test_manifest_is_structurally_deterministic(self) -> None:
        first = document_fingerprint(self.manifest)
        second = document_fingerprint(load_json(MANIFEST_PATH))
        self.assertEqual(first, second)
        self.assertEqual(self.fixture["manifest_fingerprint"], first)

    def test_exact_artifact_denominator_is_required(self) -> None:
        missing = copy.deepcopy(self.manifest)
        missing["artifacts"].pop()
        self.assert_rejected(lambda: validate_manifest(missing), "schema")

        duplicate = copy.deepcopy(self.manifest)
        duplicate["artifacts"][-1]["id"] = duplicate["artifacts"][-2]["id"]
        self.assert_rejected(lambda: validate_manifest(duplicate), "denominator")

        reordered = copy.deepcopy(self.manifest)
        reordered["artifacts"][0], reordered["artifacts"][1] = (
            reordered["artifacts"][1],
            reordered["artifacts"][0],
        )
        self.assert_rejected(lambda: validate_manifest(reordered), "denominator")

    def test_dependency_workflow_and_package_references_fail_closed(self) -> None:
        unknown_dependency = copy.deepcopy(self.manifest)
        unknown_dependency["artifacts"][0]["dependency_roots"] = ["unknown-root"]
        self.assert_rejected(
            lambda: validate_manifest(unknown_dependency), "dependency-root"
        )

        absent_job = copy.deepcopy(self.manifest)
        absent_job["artifacts"][0]["compile_job"] = "compile-absent"
        self.assert_rejected(lambda: validate_manifest(absent_job), "workflow-job")

        absent_path = copy.deepcopy(self.manifest)
        absent_path["artifacts"][0]["package_root"] = "bindings/absent"
        self.assert_rejected(lambda: validate_manifest(absent_path), "artifact-path")

    def test_source_tag_and_package_checksum_contracts_are_exact(self) -> None:
        source_tag = copy.deepcopy(self.manifest)
        source_tag["artifacts"][0]["artifact_policy"]["checksum_required"] = True
        self.assert_rejected(lambda: validate_manifest(source_tag), "artifact-policy")

        package = copy.deepcopy(self.manifest)
        package["artifacts"][1]["artifact_policy"]["checksum_required"] = False
        self.assert_rejected(lambda: validate_manifest(package), "artifact-policy")

    def test_reproducibility_normalization_is_bounded(self) -> None:
        missing = copy.deepcopy(self.manifest)
        missing["artifacts"][1]["reproducibility"]["allowed_normalizations"] = []
        self.assert_rejected(lambda: validate_manifest(missing), "reproducibility")

        excess = copy.deepcopy(self.manifest)
        excess["artifacts"][0]["reproducibility"]["allowed_normalizations"] = [
            "archive-entry-timestamp"
        ]
        self.assert_rejected(lambda: validate_manifest(excess), "reproducibility")

    def test_oidc_and_long_lived_credential_scopes_are_exact(self) -> None:
        oidc = copy.deepcopy(self.manifest)
        row = next(item for item in oidc["artifacts"] if item["id"] == "release:dart")
        row["credential_policy"]["secret_names"] = ["DART_TOKEN"]
        self.assert_rejected(lambda: validate_manifest(oidc), "credential-policy")

        long_lived = copy.deepcopy(self.manifest)
        row = next(
            item for item in long_lived["artifacts"] if item["id"] == "release:cpp"
        )
        row["credential_policy"]["secret_names"] = []
        self.assert_rejected(lambda: validate_manifest(long_lived), "credential-policy")

        observed_oidc = {
            item["id"]
            for item in self.manifest["artifacts"]
            if item["credential_policy"]["mode"] == "oidc"
        }
        self.assertEqual(OIDC_ARTIFACT_IDS, observed_oidc)

    def test_profile_and_attestation_permissions_cannot_be_weakened(self) -> None:
        network = copy.deepcopy(self.manifest)
        network["profile_policy"]["pull-request"]["network"] = "allowed"
        self.assert_rejected(lambda: validate_manifest(network), "profile-policy")

        permission = copy.deepcopy(self.manifest)
        permission["workflow_policy"]["attestation_permissions"].remove(
            "attestations: write"
        )
        self.assert_rejected(lambda: validate_manifest(permission), "workflow-policy")

        publication = copy.deepcopy(self.manifest)
        publication["profile_policy"]["release"]["publication"] = True
        self.assert_rejected(lambda: validate_manifest(publication), "schema")

    def test_contract_fixture_has_no_live_or_publication_authority(self) -> None:
        self.assertFalse(self.fixture["publication_authorized"])
        details = self.fixture["checks"][0]["details"]
        self.assertTrue(details["synthetic"])
        self.assertFalse(details["live_artifact"])
        self.assertFalse(details["publication_authority"])
        validate_contract_fixture(self.fixture, self.manifest)

    def test_contract_fixture_rejects_stale_or_tampered_identity(self) -> None:
        stale = copy.deepcopy(self.fixture)
        stale["manifest_fingerprint"] = "f" * 64
        self.resign_fixture(stale)
        self.assert_rejected(
            lambda: validate_contract_fixture(stale, self.manifest), "stale-manifest"
        )

        tampered = copy.deepcopy(self.fixture)
        tampered["disclaimer"] += " changed"
        self.assert_rejected(
            lambda: validate_contract_fixture(tampered, self.manifest),
            "fixture-fingerprint",
        )

        authority = copy.deepcopy(self.fixture)
        authority["disclaimer"] = "Synthetic only."
        self.resign_fixture(authority)
        self.assert_rejected(
            lambda: validate_contract_fixture(authority, self.manifest),
            "fixture-authority",
        )

    def test_complete_synthetic_evidence_passes_without_authority(self) -> None:
        evidence = synthetic_evidence(self.manifest)
        validated = validate_evidence(evidence, self.manifest)
        self.assertEqual(ARTIFACT_IDS, [row["id"] for row in validated["artifacts"]])
        self.assertEqual("synthetic-contract", validated["evidence_authority"])
        self.assertFalse(validated["publication_authorized"])

    def test_evidence_denominator_and_manifest_identity_fail_closed(self) -> None:
        evidence = synthetic_evidence(self.manifest)
        evidence["artifacts"].pop()
        evidence["summary"]["passed"] -= 1
        evidence["summary"]["total"] -= 1
        self.resign_evidence(evidence)
        self.assert_rejected(
            lambda: validate_evidence(evidence, self.manifest), "schema"
        )

        evidence = synthetic_evidence(self.manifest)
        evidence["manifest_fingerprint"] = "e" * 64
        self.resign_evidence(evidence)
        self.assert_rejected(
            lambda: validate_evidence(evidence, self.manifest), "stale-manifest"
        )

    def test_checksum_and_provenance_subjects_are_bound(self) -> None:
        checksum = synthetic_evidence(self.manifest)
        checksum["artifacts"][0]["checksum"]["digest"] = "f" * 64
        self.resign_evidence(checksum)
        self.assert_rejected(
            lambda: validate_evidence(checksum, self.manifest), "checksum-subject"
        )

        subject = synthetic_evidence(self.manifest)
        subject["artifacts"][0]["provenance"]["subject_name"] = "other"
        self.resign_evidence(subject)
        self.assert_rejected(
            lambda: validate_evidence(subject, self.manifest), "provenance-subject"
        )

        command = synthetic_evidence(self.manifest)
        command["artifacts"][0]["provenance"]["build_command_sha256"] = "f" * 64
        self.resign_evidence(command)
        self.assert_rejected(
            lambda: validate_evidence(command, self.manifest), "provenance-command"
        )

    def test_toolchain_denominator_policy_and_complete_pass_are_bound(self) -> None:
        denominator = synthetic_evidence(self.manifest)
        denominator["toolchains"].pop()
        self.resign_evidence(denominator)
        self.assert_rejected(
            lambda: validate_evidence(denominator, self.manifest),
            "toolchain-denominator",
        )

        policy = synthetic_evidence(self.manifest)
        policy["toolchains"][0]["policy_sha256"] = "f" * 64
        self.resign_evidence(policy)
        self.assert_rejected(
            lambda: validate_evidence(policy, self.manifest), "toolchain-policy"
        )

        incomplete = synthetic_evidence(self.manifest)
        incomplete["toolchains"][0]["version"] = None
        self.resign_evidence(incomplete)
        self.assert_rejected(
            lambda: validate_evidence(incomplete, self.manifest), "false-pass"
        )

    def test_reproducibility_scope_and_exact_rebuilds_are_bound(self) -> None:
        normalized = synthetic_evidence(self.manifest)
        cpp = next(
            item for item in normalized["artifacts"] if item["id"] == "release:cpp"
        )
        cpp["reproducibility"]["normalized_fields"] = ["signature"]
        self.resign_evidence(normalized)
        self.assert_rejected(
            lambda: validate_evidence(normalized, self.manifest), "reproducibility"
        )

        exact = synthetic_evidence(self.manifest)
        rust = next(item for item in exact["artifacts"] if item["id"] == "release:rust")
        rust["reproducibility"]["second_sha256"] = "f" * 64
        self.resign_evidence(exact)
        self.assert_rejected(
            lambda: validate_evidence(exact, self.manifest), "reproducibility"
        )

    def test_credential_mode_secret_names_and_oidc_issuer_are_bound(self) -> None:
        secret = synthetic_evidence(self.manifest)
        cpp = next(item for item in secret["artifacts"] if item["id"] == "release:cpp")
        cpp["credential"]["secret_names"] = ["CONAN_PASSWORD"]
        self.resign_evidence(secret)
        self.assert_rejected(
            lambda: validate_evidence(secret, self.manifest), "credential-policy"
        )

        issuer = synthetic_evidence(self.manifest)
        dart = next(
            item for item in issuer["artifacts"] if item["id"] == "release:dart"
        )
        dart["credential"]["oidc_issuer"] = "https://example.invalid"
        self.resign_evidence(issuer)
        self.assert_rejected(
            lambda: validate_evidence(issuer, self.manifest), "credential-policy"
        )

    def test_false_pass_and_missing_finding_are_rejected(self) -> None:
        unresolved = synthetic_evidence(self.manifest)
        unresolved["artifacts"][0]["sbom"]["unresolved_components"] = 1
        self.resign_evidence(unresolved)
        self.assert_rejected(
            lambda: validate_evidence(unresolved, self.manifest), "false-pass"
        )

        nonpass = synthetic_evidence(self.manifest)
        nonpass["artifacts"][0]["status"] = "unavailable"
        nonpass["summary"] = {
            "passed": 16,
            "failed": 0,
            "unavailable": 1,
            "incomplete": 0,
            "total": 17,
        }
        nonpass["status"] = "unavailable"
        self.resign_evidence(nonpass)
        self.assert_rejected(
            lambda: validate_evidence(nonpass, self.manifest), "missing-finding"
        )

    def test_summary_status_and_fingerprint_are_exact(self) -> None:
        summary = synthetic_evidence(self.manifest)
        summary["summary"]["passed"] = 16
        self.resign_evidence(summary)
        self.assert_rejected(
            lambda: validate_evidence(summary, self.manifest), "summary"
        )

        status = synthetic_evidence(self.manifest)
        status["status"] = "unavailable"
        self.resign_evidence(status)
        self.assert_rejected(lambda: validate_evidence(status, self.manifest), "status")

        fingerprint = synthetic_evidence(self.manifest)
        fingerprint["source"]["tree_sha256"] = "f" * 64
        self.assert_rejected(
            lambda: validate_evidence(fingerprint, self.manifest),
            "evidence-fingerprint",
        )

    def test_synthetic_evidence_cannot_claim_live_profile(self) -> None:
        evidence = synthetic_evidence(self.manifest)
        evidence["profile"] = "full"
        self.resign_evidence(evidence)
        self.assert_rejected(
            lambda: validate_evidence(evidence, self.manifest), "evidence-authority"
        )

    def test_full_profile_without_artifacts_certifies_only_the_contract(self) -> None:
        self.assert_rejected(
            lambda: run_profile_certification(profile="full", evidence_path=None),
            "evidence-required",
        )

    def test_release_profile_without_artifacts_certifies_only_the_contract(
        self,
    ) -> None:
        self.assert_rejected(
            lambda: run_profile_certification(profile="release", evidence_path=None),
            "evidence-required",
        )

    def test_fixture_inputs_are_not_modified(self) -> None:
        manifest_bytes = Path(MANIFEST_PATH).read_bytes()
        fixture_bytes = Path(VALID_FIXTURE_PATH).read_bytes()
        run_contract_check()
        self.assertEqual(manifest_bytes, Path(MANIFEST_PATH).read_bytes())
        self.assertEqual(fixture_bytes, Path(VALID_FIXTURE_PATH).read_bytes())


class ReleaseSupplyChainProducerTests(unittest.TestCase):
    def test_resigned_sbom_cannot_describe_another_coordinate(self) -> None:
        import hashlib

        evidence = self.produce()
        bundle = Path(self.temporary.name) / "evidence"
        path = bundle / "sbom/python.spdx.json"
        sbom = load_json(path)
        sbom["packages"][0]["name"] = "unapproved-package"
        write_json(path, sbom)
        row = next(
            row for row in evidence["artifacts"] if row["id"] == "release:python"
        )
        row["sbom"]["sha256"] = hashlib.sha256(canonical_json(sbom)).hexdigest()
        evidence["evidence_fingerprint"] = document_fingerprint(
            evidence, "evidence_fingerprint"
        )
        write_json(bundle / "release-supply-chain-evidence.json", evidence)
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            verify_bundle(
                root=self.first,
                evidence_path=bundle / "release-supply-chain-evidence.json",
                manifest=self.manifest,
            )
        self.assertEqual("sbom-metadata", raised.exception.code)

    def test_resigned_provenance_cannot_change_product_version(self) -> None:
        import hashlib

        evidence = self.produce()
        bundle = Path(self.temporary.name) / "evidence"
        path = bundle / "provenance/python.intoto.json"
        provenance = load_json(path)
        provenance["predicate"]["buildDefinition"]["externalParameters"][
            "productVersion"
        ] = "3.0.0"
        write_json(path, provenance)
        row = next(
            row for row in evidence["artifacts"] if row["id"] == "release:python"
        )
        row["provenance"]["predicate_sha256"] = hashlib.sha256(
            canonical_json(provenance)
        ).hexdigest()
        evidence["evidence_fingerprint"] = document_fingerprint(
            evidence, "evidence_fingerprint"
        )
        write_json(bundle / "release-supply-chain-evidence.json", evidence)
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            verify_bundle(
                root=self.first,
                evidence_path=bundle / "release-supply-chain-evidence.json",
                manifest=self.manifest,
            )
        self.assertEqual("provenance-metadata", raised.exception.code)

    def setUp(self) -> None:
        self.manifest = load_json(MANIFEST_PATH)
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.first = base / "first"
        self.second = base / "second"
        prepare_producer_root(self.first, self.manifest, variant=0)
        prepare_producer_root(self.second, self.manifest, variant=1)
        policy_sha256 = document_fingerprint({})
        self.toolchains = []
        for toolchain in synthetic_evidence(self.manifest)["toolchains"]:
            row = copy.deepcopy(toolchain)
            row["policy_sha256"] = policy_sha256
            self.toolchains.append(row)
        self.source = {
            "commit": "a" * 40,
            "dirty": False,
            "tree_sha256": "b" * 64,
        }
        self.workflow = qualify_workflow(self.first, self.manifest)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def produce(self, output_name: str = "evidence") -> dict[str, Any]:
        return produce_bundle(
            root=self.first,
            second_root=self.second,
            output_dir=Path(self.temporary.name) / output_name,
            version="1.0.0",
            profile="contract",
            manifest=self.manifest,
            source=self.source,
            workflow=self.workflow,
            toolchains=self.toolchains,
            evidence_authority="synthetic-contract",
        )

    def test_offline_producer_emits_complete_deterministic_bundle(self) -> None:
        first = self.produce("evidence-one")
        second = self.produce("evidence-two")
        self.assertEqual(
            "passed",
            first["status"],
            [
                (row["id"], row.get("findings"))
                for row in first["artifacts"]
                if row["status"] != "passed"
            ],
        )
        self.assertEqual(17, first["summary"]["passed"])
        self.assertFalse(first["publication_authorized"])
        self.assertEqual(first["evidence_fingerprint"], second["evidence_fingerprint"])

        first_root = Path(self.temporary.name) / "evidence-one"
        second_root = Path(self.temporary.name) / "evidence-two"
        first_files = sorted(
            path.relative_to(first_root) for path in first_root.rglob("*")
        )
        second_files = sorted(
            path.relative_to(second_root) for path in second_root.rglob("*")
        )
        self.assertEqual(first_files, second_files)
        for relative in first_files:
            if (first_root / relative).is_file():
                self.assertEqual(
                    (first_root / relative).read_bytes(),
                    (second_root / relative).read_bytes(),
                )
        verified = verify_bundle(
            root=self.first,
            evidence_path=first_root / "release-supply-chain-evidence.json",
            manifest=self.manifest,
        )
        self.assertEqual(
            first["evidence_fingerprint"], verified["evidence_fingerprint"]
        )

    def test_live_risk_components_populate_spdx_with_selected_runtime_license(
        self,
    ) -> None:
        perl = next(
            item for item in self.manifest["artifacts"] if item["id"] == "release:perl"
        )
        components = [
            {
                "name": package,
                "version": version,
                "reported_license": "Artistic-1.0-Perl OR GPL-1.0-or-later",
                "selected_license": "Artistic-1.0-Perl",
                "classification": "scoped_permitted",
                "disposition_id": disposition,
                "distribution_scope": "distributed-runtime",
            }
            for package, version, disposition in (
                ("FFI-CheckLib", "0.31", "LIC-CPAN-FFI-CHECKLIB-0.31"),
                ("FFI-Platypus", "2.11", "LIC-CPAN-FFI-PLATYPUS-2.11"),
                ("File-Which", "1.27", "LIC-CPAN-FILE-WHICH-1.27"),
            )
        ]
        risk = {
            "operation_id": "security.dependency-risk",
            "status": "waived",
            "summary": {
                "passed": 2,
                "waived": 1,
                "failed": 0,
                "incomplete": 0,
                "unavailable": 0,
            },
            "checks": [
                {
                    "check_id": "security.vulnerability.perl-cpan",
                    "status": "passed",
                },
                {
                    "check_id": "security.license.perl-cpan",
                    "status": "passed",
                    "scanner": {"components": components},
                },
            ],
        }
        dependencies, unresolved = _dependency_resolution(
            self.first, self.manifest, perl, risk
        )
        self.assertEqual(0, unresolved)
        sbom = _spdx_document(
            perl,
            [{"name": "bindings/perl/STRling-1.0.0.tar.gz", "sha256": "a" * 64}],
            "b" * 64,
            dependencies,
        )
        dependency_packages = sbom["packages"][1:]
        self.assertEqual(3, len(dependency_packages))
        self.assertTrue(
            all(
                item["licenseConcluded"] == "Artistic-1.0-Perl"
                for item in dependency_packages
            )
        )
        self.assertEqual(
            3,
            sum(
                item["relationshipType"] == "DEPENDS_ON"
                for item in sbom["relationships"]
            ),
        )

        risk["checks"][1]["status"] = "failed"
        _, unresolved = _dependency_resolution(self.first, self.manifest, perl, risk)
        self.assertEqual(1, unresolved)

    def test_normalization_is_bounded_to_declared_archive_fields(self) -> None:
        evidence = self.produce("normalized")
        normalized = [
            row
            for row in evidence["artifacts"]
            if row["reproducibility"]["mode"] == "normalized"
        ]
        self.assertTrue(
            any(
                row["reproducibility"]["first_sha256"]
                != row["reproducibility"]["second_sha256"]
                for row in normalized
            )
        )
        self.assertTrue(
            all(row["reproducibility"]["status"] == "passed" for row in normalized)
        )

    def test_live_security_nullable_selection_preserves_the_permitted_expression(
        self,
    ) -> None:
        from tooling.security import SecurityEngine

        artifact = next(
            row for row in self.manifest["artifacts"] if row["id"] == "release:perl"
        )
        engine = object.__new__(SecurityEngine)
        with patch.object(engine, "_scoped_license_disposition", return_value=None):
            component = engine._license_component_evidence(
                root_id="perl-cpan",
                dependency_root={"usage": "runtime"},
                ecosystem="cpan",
                package="fixture-dependency",
                version="1.2.3",
                expression="MIT OR Apache-2.0",
                classification="permitted",
                disposition_id=None,
            )
        self.assertIsNone(component["selected_license"])
        risk = {
            "operation_id": "security.dependency-risk",
            "status": "passed",
            "summary": {"passed": 2, "failed": 0, "incomplete": 0, "unavailable": 0},
            "checks": [
                {"check_id": "security.vulnerability.perl-cpan", "status": "passed"},
                {
                    "check_id": "security.license.perl-cpan",
                    "status": "passed",
                    "scanner": {"components": [component]},
                },
            ],
        }
        dependencies, unresolved = _dependency_resolution(
            self.first, self.manifest, artifact, risk
        )
        self.assertEqual(0, unresolved)
        sbom = _spdx_document(
            artifact,
            [{"name": "fixture.tar.gz", "sha256": "a" * 64}],
            "b" * 64,
            dependencies,
        )
        self.assertEqual("MIT OR Apache-2.0", sbom["packages"][1]["licenseDeclared"])
        self.assertEqual("MIT OR Apache-2.0", sbom["packages"][1]["licenseConcluded"])
        for invalid in ("", "NOASSERTION", "NONE", 42):
            with self.subTest(selected_license=invalid):
                component["selected_license"] = invalid
                _, unresolved = _dependency_resolution(
                    self.first, self.manifest, artifact, risk
                )
                self.assertGreater(unresolved, 0)

    def test_exact_rebuild_mutation_cannot_false_pass(self) -> None:
        target = self.second / "bindings/typescript/strling-lang-strling-1.0.0.tgz"
        write_archive(target, variant=9)
        evidence = self.produce("mismatch")
        row = next(
            item for item in evidence["artifacts"] if item["id"] == "release:typescript"
        )
        self.assertEqual("failed", row["status"])
        self.assertEqual("failed", row["reproducibility"]["status"])
        self.assertEqual("failed", evidence["status"])
        self.assertEqual("SUPPLY-REPRODUCIBILITY-MISMATCH", row["findings"][0]["code"])

    def test_live_evidence_requires_matching_authenticated_rebuild_source(self) -> None:
        arguments = {
            "root": self.first,
            "second_root": self.second,
            "output_dir": Path(self.temporary.name) / "live-source",
            "version": "1.0.0",
            "profile": "full",
            "manifest": self.manifest,
            "source": self.source,
            "workflow": self.workflow,
            "toolchains": self.toolchains,
            "evidence_authority": "live-dry-run",
        }
        with self.assertRaises(ReleaseSupplyChainError) as missing:
            produce_bundle(**arguments)
        self.assertEqual("source-rebuild", missing.exception.code)
        with self.assertRaises(ReleaseSupplyChainError) as drift:
            produce_bundle(
                **arguments,
                rebuild_source={**self.source, "commit": "c" * 40},
            )
        self.assertEqual("source-rebuild", drift.exception.code)

    def test_build_receipts_bind_each_artifact_toolchain_and_rebuild(self) -> None:
        from tooling.release_consumers import CONSUMER_FIXTURES
        import hashlib

        receipts = Path(self.temporary.name) / "receipts"
        toolchains = {row["id"]: row for row in self.toolchains}
        for root in (self.first, self.second):
            for relative in CONSUMER_FIXTURES.values():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"consumer fixture")

        def probe(root, *, artifact_id, toolchain_id, policy_sha256, scope):
            return copy.deepcopy(toolchains[f"{artifact_id}:{scope}:{toolchain_id}"])

        def consumer(artifact_id, *, root, native):
            artifact = next(
                a for a in self.manifest["artifacts"] if a["id"] == artifact_id
            )
            members = _surface_members(
                root, scoped_artifact(artifact, active_scope), "1.0.0"
            )
            result = dict(
                status="passed",
                source_outcome="succeeded",
                target_pattern="abc",
                kernel_mismatch_rejected=True,
            )
            if artifact_id == "release:rust":
                result.update(
                    linked_package_version="1.0.0",
                    target_profile_mismatch_rejected=True,
                )
            companion = {
                "release:fsharp": "release:csharp",
                "release:kotlin": "release:java",
            }.get(artifact_id)
            if companion:
                contract = next(
                    a for a in self.manifest["artifacts"] if a["id"] == companion
                )
                result["companion_subject_sha256"] = _surface_identity(
                    _surface_members(
                        root, scoped_artifact(contract, active_scope), "1.0.0"
                    )
                )[1]
            receipt = dict(
                schema_version="2.0.0",
                document_kind="release-consumer-receipt",
                artifact_id=artifact_id,
                product_version="1.0.0",
                scope=active_scope,
                source=self.source,
                engineering=False,
                publication_authorized=False,
                subject_sha256=_surface_identity(members)[1],
                manifest_fingerprint=document_fingerprint(self.manifest),
                fixture_sha256={
                    r: hashlib.sha256((root / r).read_bytes()).hexdigest()
                    for r in CONSUMER_FIXTURES.values()
                },
                result=result,
            )
            receipt["receipt_fingerprint"] = document_fingerprint(
                receipt, "receipt_fingerprint"
            )
            return receipt

        with (
            patch(
                "tooling.release_supply_chain.authenticate_source",
                return_value=self.source,
            ),
            patch("tooling.release_supply_chain._probe_toolchain", side_effect=probe),
            patch("tooling.release_supply_chain._validate_toolchain_version"),
            patch(
                "tooling.release_supply_chain.inspect_release_payload", return_value=[]
            ),
            patch("tooling.release_consumers.verify_consumer", side_effect=consumer),
        ):
            for artifact in self.manifest["artifacts"]:
                slug = artifact["id"].removeprefix("release:")
                for active_scope in artifact_scopes(artifact):
                    with patch(
                        "tooling.release_packaging.host_scope",
                        return_value=active_scope,
                    ):
                        for label, root in (
                            ("first", self.first),
                            ("second", self.second),
                        ):
                            capture_build_receipt(
                                root=root,
                                artifact_id=artifact["id"],
                                version="1.0.0",
                                output_path=receipts
                                / f"{slug}-{active_scope}-{label}.json",
                                manifest=self.manifest,
                            )
            observed, first_source, second_source, captured = load_build_receipts(
                receipt_dir=receipts,
                root=self.first,
                second_root=self.second,
                manifest=self.manifest,
                version="1.0.0",
            )
            self.assertEqual(self.toolchains, observed)
            self.assertEqual(self.source, first_source)
            self.assertEqual(self.source, second_source)
            self.assertEqual(42, len(captured))
            drift_path = receipts / "rust-linux-x86_64-second.json"
            drift = load_json(drift_path)
            drift["build_instance_id"] = load_json(
                receipts / "rust-linux-x86_64-first.json"
            )["build_instance_id"]
            drift["receipt_fingerprint"] = document_fingerprint(
                drift, "receipt_fingerprint"
            )
            write_json(drift_path, drift)
            with self.assertRaises(ReleaseSupplyChainError) as raised:
                load_build_receipts(
                    receipt_dir=receipts,
                    root=self.first,
                    second_root=self.second,
                    manifest=self.manifest,
                    version="1.0.0",
                )
            self.assertEqual("source-rebuild", raised.exception.code)

    def test_verifier_rejects_tampered_companion_document(self) -> None:
        self.produce("tampered")
        evidence_root = Path(self.temporary.name) / "tampered"
        sbom = evidence_root / "sbom/rust.spdx.json"
        document = json.loads(sbom.read_text(encoding="utf-8"))
        document["name"] = "tampered"
        write_json(sbom, document)
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            verify_bundle(
                root=self.first,
                evidence_path=evidence_root / "release-supply-chain-evidence.json",
                manifest=self.manifest,
            )
        self.assertEqual("sbom-document", raised.exception.code)

    def test_verifier_rejects_artifact_bytes_changed_after_collection(self) -> None:
        self.produce("artifact-tamper")
        evidence_root = Path(self.temporary.name) / "artifact-tamper"
        target = self.first / "target/package/strling-1.0.0.crate"
        write_archive(target, variant=8)
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            verify_bundle(
                root=self.first,
                evidence_path=evidence_root / "release-supply-chain-evidence.json",
                manifest=self.manifest,
            )
        self.assertEqual("checksum-document", raised.exception.code)

    def test_workflow_qualification_rejects_missing_exact_handoff(self) -> None:
        path = self.first / self.manifest["workflow_policy"]["path"]
        workflow = path.read_text(encoding="utf-8").replace(
            "actions/download-artifact@", "actions/checkout@"
        )
        path.write_text(workflow, encoding="utf-8", newline="\n")
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            qualify_workflow(self.first, self.manifest)
        self.assertEqual("workflow-handoff", raised.exception.code)

    def test_source_authentication_rejects_dirty_tree(self) -> None:
        repository = Path(self.temporary.name) / "source-authentication"
        repository.mkdir()
        commands = [
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "fixture@strling.dev"],
            ["git", "config", "user.name", "STRling fixture"],
        ]
        for command in commands:
            subprocess.run(command, cwd=repository, check=True, capture_output=True)
        (repository / "tracked.txt").write_text(
            "tracked\n", encoding="utf-8", newline="\n"
        )
        subprocess.run(
            ["git", "add", "tracked.txt"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "fixture"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
        authenticated = authenticate_source(repository)
        self.assertFalse(authenticated["dirty"])
        (repository / "untracked.txt").write_text(
            "dirty\n", encoding="utf-8", newline="\n"
        )
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            authenticate_source(repository)
        self.assertEqual("source-dirty", raised.exception.code)

    def test_source_delivery_ignores_only_git_ignored_build_outputs(self) -> None:
        repository = Path(self.temporary.name) / "source-tree-identity"
        source = repository / "bindings/go"
        source.mkdir(parents=True)
        (repository / ".gitignore").write_text(
            "bindings/go/build-output\n", encoding="utf-8", newline="\n"
        )
        (source / "tracked.go").write_text(
            "package strling\n", encoding="utf-8", newline="\n"
        )
        for command in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "fixture@strling.dev"],
            ["git", "config", "user.name", "STRling fixture"],
            ["git", "add", ".gitignore", "bindings/go/tracked.go"],
            ["git", "commit", "--quiet", "-m", "fixture"],
        ):
            subprocess.run(command, cwd=repository, check=True, capture_output=True)
        artifact = next(
            row for row in self.manifest["artifacts"] if row["id"] == "release:go"
        )
        before = _surface_members(repository, artifact, "1.0.0")
        (source / "build-output").write_text(
            "ignored output\n", encoding="utf-8", newline="\n"
        )
        self.assertEqual(before, _surface_members(repository, artifact, "1.0.0"))
        self.assertFalse(authenticate_source(repository)["dirty"])

    def test_output_directory_is_create_only(self) -> None:
        self.produce("create-only")
        with self.assertRaises(ReleaseSupplyChainError) as raised:
            self.produce("create-only")
        self.assertEqual("output-exists", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
