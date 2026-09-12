from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

import yaml

from tooling import performance_resource_certification as performance
from tooling import adversarial_semantic_audit as audit
from tooling import production_certification as production
from tooling import product_certification as product
from tooling import profile_source_identity as profile_source
from tooling import structured_operation_execution as transport
from tooling import security

from tooling.certification import (
    build_certification_artifact,
    write_certification_artifact,
)
from tooling.local_certification_attestation import (
    AttestationError,
    _public_key_fingerprint,
    _sign,
    canonical_bytes,
    create_attestation,
    file_sha256,
    object_sha256,
    verify_attestation,
    _sample_counts,
    _real_engine_claim,
    _waivers,
)


ROOT = Path(__file__).resolve().parents[2]
CERTIFIER_ID = "test-local-certifier"
INVOCATION_ID = "a" * 32


class LocalCertificationAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_root = None
        if os.name == "nt":
            (ROOT / "target").mkdir(exist_ok=True)
            temporary_root = ROOT / "target"
        self.temporary = tempfile.TemporaryDirectory(
            dir=temporary_root, prefix="local-attestation-test-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        self.inputs = self.base / "inputs"
        self.bundle = self.base / "bundle"
        self.repository.mkdir()
        self.inputs.mkdir()
        self.production_worktree = (
            self.repository / ".cert/production-certification/test/source"
        )
        (self.repository / ".gitignore").write_text("/target/\n/artifacts/\n/.cert/\n")
        (self.repository / "governance/schemas").mkdir(parents=True)
        (self.repository / "spec/targets/profiles").mkdir(parents=True)
        (self.repository / "core").mkdir()
        (self.repository / "bindings/interop").mkdir(parents=True)
        for name in (
            "profile-certification-artifact.schema.json",
            "local-certification-attestation.schema.json",
            "local-certification-trust.schema.json",
            "structured-operation-execution.schema.json",
            "product-certification-artifact.schema.json",
            "product-certification-producer-manifest.schema.json",
            "profile-source-evidence.schema.json",
            "certification-evidence-dependency-graph.schema.json",
            "target-adapter-certification-matrix.schema.json",
            "security-result.schema.json",
        ):
            shutil.copyfile(
                ROOT / "governance/schemas" / name,
                self.repository / "governance/schemas" / name,
            )
        for relative in (
            "governance/certification-evidence-dependency-graph.json",
            "tooling/profile_source_identity.py",
            "tests/certification/performance-resource/1.0/manifest.json",
            "tests/certification/performance-resource/1.0/baseline.json",
            "tests/certification/performance-resource/1.0/fixtures/fixture-manifest.json",
            "tests/certification/performance-resource/1.0/fixtures/resource-limits.json",
            "tests/conformance/adversarial/1.0/evidence.json",
            "tests/conformance/adversarial/1.0/corpus.json",
            "governance/security-policy.json",
            "governance/schemas/security-policy.schema.json",
            "governance/schemas/waiver.schema.json",
            "governance/waivers/WVR-SEC-VSCE-LICENSE-001.yaml",
        ):
            destination = self.repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        shutil.copytree(
            ROOT / "tests/conformance/adversarial/1.0/observations",
            self.repository / "tests/conformance/adversarial/1.0/observations",
        )
        index_path = self.repository / "tests/conformance/adversarial/1.0/evidence.json"
        index = json.loads(index_path.read_text())
        for relative in index["source_files"]:
            destination = self.repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
            index["source_files"][relative] = file_sha256(destination)
        for profile_id in audit.PROFILES:
            path = audit.shared._profile_path(profile_id)
            destination = self.repository / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        inventory = json.loads((ROOT / performance.RESOURCE_INVENTORY_PATH).read_text())
        for family in inventory["families"]:
            for source in family["sources"] + family["test_sources"]:
                destination = self.repository / source["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source["path"], destination)
        index_path.write_text(json.dumps(index))
        self.private_key = self.base / "certifier"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(self.private_key),
            ],
            check=True,
        )
        public_key = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(self.private_key)],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        self.trust = {
            "$schema": "https://strling.dev/governance/local-certification-trust.schema.json",
            "schema_version": "1.0.0",
            "policy_kind": "strling-local-certification-trust",
            "signature_namespace": "strling-local-certification-v1",
            "bundle_path": "tests/certification/hardened-core/1.0/current",
            "required_profiles": ["full", "release"],
            "allowed_waivers": ["WVR-SEC-VSCE-LICENSE-001"],
            "closure_paths": ["docs/certification/**"],
            "authorized_certifiers": [
                {
                    "certifier_id": CERTIFIER_ID,
                    "public_key": public_key,
                    "ssh_key_fingerprint": _public_key_fingerprint(public_key),
                    "authorized_profiles": ["full", "release"],
                    "status": "active",
                }
            ],
        }
        (self.repository / "governance/local-certification-trust.json").write_text(
            json.dumps(self.trust, indent=2) + "\n", encoding="utf-8"
        )
        self.profiles = {
            name: {
                "definition_version": "1.0.0",
                "purpose": f"test {name}",
                "network_policy": "allowed",
                "operations": [
                    {"operation": "performance_resource_full_certification"},
                    {"operation": "adversarial_real_engine_equivalence"},
                    {"operation": "required_security_check"},
                ],
            }
            for name in ("local", "pull-request", "full", "release")
        }
        toolchain = {
            "schema_version": 1,
            "policy": {
                "profiles": self.profiles,
                "operation_registry": {
                    "performance_resource_full_certification": {
                        "kind": "repository",
                        "component": "repository",
                        "result_contract": "certification-result-v1",
                        "result_operation_id": "certification.performance-resource-full",
                        "result_transport": "atomic-artifact-v1",
                        "command": ["performance", "--profile", "full"],
                    },
                    "adversarial_real_engine_equivalence": {
                        "kind": "repository",
                        "component": "repository",
                        "result_contract": "certification-result-v1",
                        "result_operation_id": "certification.adversarial-real-engine-equivalence",
                    },
                    "required_security_check": {
                        "kind": "repository",
                        "component": "repository",
                    },
                },
            },
        }
        (self.repository / "toolchain.json").write_text(
            json.dumps(toolchain, indent=2) + "\n", encoding="utf-8"
        )
        manifest = json.loads((ROOT / product.MANIFEST_PATH).read_text())
        manifest["producers"] = [
            {
                "operation_id": name,
                "evidence_area": "performance-resource",
                "requirement": "required",
                "result_contract": definition.get("result_contract"),
                "structured_operation_id": definition.get("result_operation_id"),
                **(
                    {
                        "payload_version_override": {
                            "field": "schema_version",
                            "value": "1.0.0",
                        }
                    }
                    if name == "adversarial_real_engine_equivalence"
                    else {}
                ),
            }
            for name, definition in toolchain["policy"]["operation_registry"].items()
        ]
        manifest["evidence_areas"] = ["performance-resource"]
        for claim in manifest["claims"]:
            claim["source"] = {"all_profile_results": True}
        manifest_path = self.repository / product.MANIFEST_PATH
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))
        profile_source.write_definition_bundle(root=self.repository)
        target_profile = {
            "contract_version": "1.0.0",
            "profile_id": "profile:test/1",
            "profile_version": "1.0.0",
        }
        (self.repository / "spec/targets/profiles/test.json").write_text(
            json.dumps(target_profile) + "\n", encoding="utf-8"
        )
        (self.repository / "core/kernel.rs").write_text("kernel\n", encoding="utf-8")
        (self.repository / "bindings/interop/lib.rs").write_text(
            "interop\n", encoding="utf-8"
        )
        self._git("init")
        self._git("config", "user.email", "tests@strling.dev")
        self._git("config", "user.name", "STRling tests")
        self._git("add", ".")
        self._git("commit", "-m", "fixture")
        self.source_sha = self._git("rev-parse", "HEAD")
        for profile in ("full", "release"):
            artifact = build_certification_artifact(
                root=self.repository,
                profile_id=profile,
                profile_definition=self.profiles[profile],
                requested_component=None,
                results=self._results(profile),
                aggregate_status="passed",
                exit_code=0,
                resolved_repository_state={"commit": self.source_sha, "dirty": False},
            )
            write_certification_artifact(self.inputs / f"{profile}.json", artifact)
        self._write_production_evidence()
        create_attestation(
            repository_root=self.repository,
            trust_root=self.repository,
            output_dir=self.bundle,
            full_artifact=self.inputs / "full.json",
            release_artifact=self.inputs / "release.json",
            extra_evidence=[],
            private_key=self.private_key,
            certifier_id=CERTIFIER_ID,
            invocation_id=INVOCATION_ID,
        )

    def _git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip()

    def _results(self, profile: str) -> list[dict[str, object]]:
        governed = json.loads(
            (
                self.repository / "tests/conformance/adversarial/1.0/evidence.json"
            ).read_text()
        )
        execution_root = (
            self.repository if profile == "full" else self.production_worktree
        )
        raw = audit.load_evidence(
            self.repository / "tests/conformance/adversarial/1.0/evidence.json"
        )
        raw["source_sha"] = self.source_sha
        raw["result_sha256"] = audit.DIGEST(
            {key: value for key, value in raw.items() if key != "result_sha256"}
        )
        evidence_path = (
            execution_root / "artifacts/adversarial-semantic-runtime/evidence.json"
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        audit.write_evidence(raw, evidence_path)
        real_engine = {
            "schema_version": "1.0.0",
            "operation_id": "certification.adversarial-real-engine-equivalence",
            "status": "passed",
            "checks": [
                {
                    "check_id": "certification.adversarial-real-engine-equivalence.matrix",
                    "status": "passed",
                    "evidence": {
                        "counts": {
                            "semantic_cases": 41,
                            "subjects": 95,
                            "target_profile_compiles": 205,
                            "runtime_executions": 1531,
                            "governed_refusals": 48,
                            "cross_profile_comparisons": 1129,
                        },
                        "runtime_identities": governed["runtimes"],
                        "source_sha": self.source_sha,
                        "source_files": governed["source_files"],
                        "evidence_path": "artifacts/adversarial-semantic-runtime/evidence.json",
                        "findings": [],
                        "unaccounted_observations": 0,
                        "run_id": governed["run_id"],
                    },
                }
            ],
            "summary": {
                "passed": 1,
                "failed": 0,
                "waived": 0,
                "unavailable": 0,
                "incomplete": 0,
            },
        }
        performance_result, integrity = self._performance_result(profile)
        return [
            {
                "operation": "performance_resource_full_certification",
                "component": "repository",
                "status": "passed",
                "command": ["performance"],
                "exit_code": 0,
                "reason": None,
                "capability": None,
                "formatters": [],
                "environment": [],
                "structured_result": performance_result,
                "execution_integrity": integrity,
            },
            {
                "operation": "adversarial_real_engine_equivalence",
                "component": "repository",
                "status": "passed",
                "command": ["audit"],
                "exit_code": 0,
                "reason": None,
                "capability": None,
                "formatters": [],
                "environment": [],
                "structured_result": real_engine,
            },
            {
                "operation": "required_security_check",
                "component": "repository",
                "status": "passed",
                "command": ["security"],
                "exit_code": 0,
                "reason": None,
                "capability": None,
                "formatters": [],
                "environment": [],
            },
        ]

    def _performance_result(self, profile: str) -> tuple[dict, dict]:
        manifest = json.loads((ROOT / performance.MANIFEST_PATH).read_text())
        baseline = json.loads((ROOT / performance.BASELINE_PATH).read_text())
        environment_identity = performance.environment_identity_fingerprint(
            baseline["environment"]
        )
        conditioning_identity = performance.conditioning_identity_fingerprint(
            baseline["conditioning_repetitions"][0]
        )

        def step(command):
            return {
                "status": "passed",
                "command": command,
                "duration_ms": 1,
                "output_sha256": hashlib.sha256(b"fixture output").hexdigest(),
                "return_code": 0,
            }

        def isolation(phase, coordinate):
            return {
                "id": f"environment:external-workload-isolation/{phase}/{coordinate}",
                "status": "passed",
                "details": {
                    "phase": phase,
                    "observed_workloads": [],
                    "unrelated_heavyweight_workloads_absent": True,
                },
            }

        build_commands = [
            [
                "cargo",
                "+1.75.0",
                "build",
                "--release",
                "--manifest-path",
                path,
                "--locked",
                "--offline",
                *extra,
            ]
            for path, extra in (
                ("tests/certification/performance-resource/1.0/runner/Cargo.toml", []),
                ("core/internal/Cargo.toml", ["--bin", "strling-kernel"]),
                ("bindings/interop/Cargo.toml", ["--lib"]),
            )
        ]
        _, artifact_identity = performance._artifact_identity_check(
            baseline["artifact_fingerprints"],
            baseline["artifact_fingerprints"],
            baseline_source_commit=baseline["source_commit"],
            candidate_source_commit=self.source_sha,
            source_changes=None,
        )
        selected_cpu = manifest["measurement_policy"]["selected_logical_cpu"]
        checks = [
            {
                "id": "environment:single-fixed-logical-cpu",
                "status": "passed",
                "details": {
                    "selected_logical_cpu": selected_cpu,
                    "effective_cpu_affinity": [selected_cpu],
                    "effective_cpuset": performance._format_cpu_set([selected_cpu]),
                },
            },
            {
                "id": "build:release-performance-artifacts",
                "status": "passed",
                "details": {
                    "steps": [step(command) for command in build_commands],
                    "artifacts": baseline["artifact_fingerprints"],
                    "canonical_build_root": "P:/",
                },
            },
            {
                "id": "build:baseline-artifact-identity",
                "status": "passed",
                "details": {
                    "baseline_artifacts": baseline["artifact_fingerprints"],
                    "observed_artifacts": baseline["artifact_fingerprints"],
                    "exact_match": True,
                    "candidate_rebind": False,
                    "candidate_identity": artifact_identity,
                },
            },
            {
                "id": "environment:fingerprinted-native-x86_64",
                "status": "passed",
                "details": {
                    "baseline_fingerprint": baseline["environment_fingerprint"],
                    "observed_fingerprint": baseline["environment_fingerprint"],
                    "baseline_identity_fingerprint": environment_identity,
                    "observed_identity_fingerprint": environment_identity,
                    "governed_mismatches": [],
                    "exact_match": True,
                    "raw_mismatches": [],
                },
            },
            {
                "id": "environment:identical-conditioning",
                "status": "passed",
                "details": {
                    "baseline_conditioning_identity_fingerprint": conditioning_identity,
                    "conditioning_identity_fingerprint": conditioning_identity,
                    "identical_conditioning_identity": True,
                },
            },
        ]
        definitions = {row["id"]: row for row in manifest["operations"]}
        coordinates = []
        measurements = {
            (row["operation_id"], row["fixture_id"]): row
            for row in baseline["measurements"]
        }
        ordered = performance.performance_measurement_keys(manifest)
        performance.random.Random(manifest["measurement_policy"]["order_seed"]).shuffle(
            ordered
        )
        for key in ordered:
            row = measurements[key]
            definition = definitions[row["operation_id"]]
            samples = [
                row["statistics"]["median"]
            ] * performance._expected_repetition_sample_count(definition, manifest)
            coordinate = f"{row['operation_id']}/{row['fixture_id'] or 'fixture-free'}"
            coordinates.append(coordinate)
            checks.append(isolation("pre-measurement", coordinate))
            snapshot = baseline["conditioning_repetitions"][0]
            checks.append(
                {
                    "id": f"environment:measurement-conditioning/{coordinate}",
                    "status": "passed",
                    "details": {
                        "attempt": 1,
                        "maximum_attempts": performance.MEASUREMENT_CONDITIONING_MAX_ATTEMPTS,
                        "retry_delay_seconds": performance.MEASUREMENT_CONDITIONING_RETRY_DELAY_SECONDS,
                        "rejected_attempts": [],
                        "conditioning_identity_fingerprint": conditioning_identity,
                        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
                        "quiescence_observation": copy.deepcopy(
                            snapshot["quiescence_observation"]
                        ),
                    },
                }
            )
            comparison = performance.compare_hard_metric(
                baseline_median=row["statistics"]["median"],
                observed_median=row["statistics"]["median"],
                relative_regression_basis_points=row["budget"][
                    "relative_regression_basis_points"
                ],
                absolute_ceiling=row["budget"]["absolute_ceiling"],
            )
            checks.append(
                {
                    "id": f"measurement:{coordinate}",
                    "status": "passed",
                    "details": {
                        "samples": samples,
                        "statistics": performance.sample_statistics(samples),
                        "enforcement": definition["enforcement"],
                        "comparison": comparison,
                        "disposition": "release-blocking"
                        if definition["enforcement"] == "hard"
                        else "informational-trend",
                        "would_exceed_budget": comparison["status"] == "failed",
                        "unit": row["unit"],
                        "batch_iterations": row["batch_iterations"],
                        "batch_duration_samples": (
                            [sample * row["batch_iterations"] for sample in samples]
                            if definition["measurement_kind"] == "latency"
                            else None
                        ),
                    },
                }
            )
            checks.append(isolation("post-measurement", coordinate))
        checks.extend(
            {
                "id": operation_id,
                "status": "passed",
                "details": {
                    "steps": [
                        step(
                            [
                                *command,
                                "--target-dir",
                                str(
                                    self.repository
                                    / performance.RESOURCE_TARGET_DIRECTORY
                                ),
                            ]
                        )
                        for command in performance.RESOURCE_COMMANDS[operation_id]
                    ]
                },
            }
            for operation_id in performance.RESOURCE_OPERATION_IDS
        )
        checks.append(performance._controlled_regression_check(baseline))
        result = performance._certification_evidence(
            profile="full", commit=self.source_sha, checks=checks, manifest=manifest
        )
        total = transport.authenticated_sample_count(result)
        execution = {
            **transport.execution_context(
                producer_id="performance_resource_full_certification@repository",
                operation_id="certification.performance-resource-full",
                source_sha=self.source_sha,
                invocation_id=("3" if profile == "full" else "4") * 32,
                certification_profile=profile,
                producer_profile="full",
            ),
            "artifact_kind": "structured-operation-result",
            "result_contract": "certification-result-v1",
            "process_exit_code": 0,
            "terminal_status": "passed",
            "environment_identity": transport.extract_environment_identity(result),
            "performance_evidence_identity": result["evidence_fingerprint"],
            "sample_consumption": {
                "state": "consumed",
                "authenticated_sample_count": total,
                "completed_sample_count": total,
                "coordinates_started": len(coordinates),
                "coordinates_completed": len(coordinates),
                "completed_coordinate_ids": coordinates,
                "current_coordinate_id": None,
            },
            "structured_result": result,
            "integrity_error": None,
        }
        execution["artifact_fingerprint"] = transport.document_fingerprint(execution)
        execution_root = (
            self.repository if profile == "full" else self.production_worktree
        )
        directory = (
            execution_root
            / "target/certification-operation-results"
            / execution["invocation_id"]
        )
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "result.json").write_text(json.dumps(execution))
        streams = {
            "stdout": transport.atomic_write_stream(
                directory / "stdout.txt", json.dumps(result)
            ),
            "stderr": transport.atomic_write_stream(directory / "stderr.txt", ""),
        }
        integrity = {
            key: value
            for key, value in execution.items()
            if key not in ("structured_result", "integrity_error")
        }
        integrity.update(artifact_directory=str(directory), streams=streams)
        return result, integrity

    def _write_production_evidence(self) -> None:
        release_path = self.inputs / "release.json"
        release = json.loads(release_path.read_text())
        artifact = product.build_product_artifact(
            root=self.repository,
            profile_artifact=release,
            resolved_repository_state={"commit": self.source_sha, "dirty": False},
        )
        product_path = self.inputs / production.PRODUCT_ARTIFACT_NAME
        report_path = self.inputs / production.PRODUCT_REPORT_NAME
        product.write_json(product_path, artifact)
        product.write_report(report_path, product.render_product_report(artifact))
        preserved = production.preserve_execution_evidence(
            worktree=self.production_worktree,
            output_dir=self.inputs,
            profile_artifact=release_path,
        )
        production.write_artifact(
            output_dir=self.inputs,
            source={
                "sha": self.source_sha,
                "status_porcelain": "",
                "branch": "fixture",
            },
            environment={"preserved_execution_evidence": preserved},
            worktree=self.production_worktree,
            status="passed",
            profile_artifact=release_path,
            product_artifact=product_path,
            product_report=report_path,
            worktree_created=True,
            final_source_status="",
            final_root_status="",
            generated_artifacts_recreated=True,
            failure=None,
        )

    def _attestation(self) -> dict:
        return json.loads(
            (self.bundle / "attestation.json").read_text(encoding="utf-8")
        )

    def _write_resigned(self, attestation: dict) -> None:
        payload = attestation["signed_payload"]
        projection = copy.deepcopy(payload)
        projection.pop("evidence_root_sha256", None)
        payload["evidence_root_sha256"] = object_sha256(projection)
        signed = canonical_bytes(payload)
        signature = _sign(signed, self.private_key, "strling-local-certification-v1")
        attestation["signature"].update(
            {
                "signature_base64": base64.b64encode(signature).decode("ascii"),
                "signature_sha256": hashlib.sha256(signature).hexdigest(),
                "signed_payload_sha256": hashlib.sha256(signed).hexdigest(),
            }
        )
        (self.bundle / "attestation.json").write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _resign_payload_mutation(self, mutator) -> None:
        attestation = self._attestation()
        mutator(attestation["signed_payload"])
        self._write_resigned(attestation)

    def _resign_file(self, relative: str, value: dict) -> None:
        path = self.bundle / relative
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        attestation = self._attestation()
        entry = next(
            item
            for item in attestation["signed_payload"]["evidence_files"]
            if item["path"] == relative
        )
        entry.update(bytes=path.stat().st_size, sha256=file_sha256(path))
        self._write_resigned(attestation)

    def _resign_full_profile(self, mutate) -> None:
        relative = "evidence/profile-full/full.json"
        artifact = json.loads((self.bundle / relative).read_text())
        mutate(artifact["deterministic_evidence"])
        deterministic = artifact["deterministic_evidence"]
        for operation in deterministic["operations"]:
            integrity = operation.get("execution_integrity")
            if not isinstance(integrity, dict):
                continue
            structured = operation["structured_evidence"]
            structured["deterministic_evidence"]["checks"] = structured["checks"]
            structured["evidence_fingerprint"] = object_sha256(
                structured["deterministic_evidence"]
            )
            integrity["performance_evidence_identity"] = structured[
                "evidence_fingerprint"
            ]
            integrity["environment_identity"] = transport.extract_environment_identity(
                structured
            )
            complete = {
                key: value
                for key, value in integrity.items()
                if key not in ("artifact_directory", "streams")
            }
            complete.update(structured_result=structured, integrity_error=None)
            integrity["artifact_fingerprint"] = transport.document_fingerprint(complete)
        counts = Counter(item["status"] for item in deterministic["operations"])
        deterministic["aggregate"]["operation_count"] = len(deterministic["operations"])
        deterministic["aggregate"]["counts"] = {
            key: counts.get(key, 0) for key in deterministic["aggregate"]["counts"]
        }
        deterministic["aggregate"]["status"] = (
            "waived" if counts.get("waived") else "passed"
        )
        artifact["evidence_fingerprint"] = object_sha256(deterministic)
        self._resign_file(relative, artifact)
        attestation = self._attestation()
        payload = attestation["signed_payload"]
        payload["profile_results"][0].update(
            evidence_fingerprint=artifact["evidence_fingerprint"],
            status=deterministic["aggregate"]["status"],
            operation_count=deterministic["aggregate"]["operation_count"],
            counts=deterministic["aggregate"]["counts"],
        )
        release = json.loads(
            (self.bundle / "evidence/profile-release/release.json").read_text()
        )
        payload["authenticated_sample_counts"].update(
            _sample_counts((artifact, release))
        )
        payload["waiver_inventory"] = _waivers((artifact, release))
        self._write_resigned(attestation)

    def _verify(self) -> dict:
        return verify_attestation(
            repository_root=self.repository,
            trust_root=self.repository,
            bundle_dir=self.bundle,
        )

    def test_valid_attestation_passes(self) -> None:
        result = verify_attestation(
            repository_root=self.repository,
            trust_root=self.repository,
            bundle_dir=self.bundle,
        )
        self.assertEqual("CLOUD_VERIFIED", result["certification_state"])

    def test_missing_required_operation_with_consistent_aggregate_is_rejected(
        self,
    ) -> None:
        self._resign_full_profile(lambda value: value["operations"].pop())
        with self.assertRaisesRegex(AttestationError, "complete ordered profile"):
            self._verify()

    def test_component_scoped_profile_is_rejected(self) -> None:
        self._resign_full_profile(
            lambda value: value.update(component_scope={"mode": "all"})
        )
        with self.assertRaisesRegex(AttestationError, "complete ordered profile"):
            self._verify()

    def test_missing_atomic_evidence_is_rejected(self) -> None:
        self._resign_full_profile(
            lambda value: value["operations"][0].pop("execution_integrity")
        )
        with self.assertRaisesRegex(AttestationError, "invocation-bound"):
            self._verify()

    def test_one_sample_with_consistent_signed_fingerprints_is_rejected(self) -> None:
        def mutate(value):
            operation = value["operations"][0]
            measurement = next(
                item
                for item in operation["structured_evidence"]["checks"]
                if item["id"].startswith("measurement:latency:")
            )
            measurement["details"]["samples"] = measurement["details"]["samples"][:1]
            operation["execution_integrity"]["sample_consumption"][
                "authenticated_sample_count"
            ] -= 63
            operation["execution_integrity"]["sample_consumption"][
                "completed_sample_count"
            ] -= 63

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "sample denominator"):
            self._verify()

    def test_missing_measurement_coordinate_is_rejected(self) -> None:
        def mutate(value):
            checks = value["operations"][0]["structured_evidence"]["checks"]
            checks.pop(
                next(
                    index
                    for index, item in enumerate(checks)
                    if item["id"].startswith("measurement:")
                )
            )

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "coordinate denominator"):
            self._verify()

    def test_false_passing_statistics_are_rejected(self) -> None:
        def mutate(value):
            measurement = next(
                item
                for item in value["operations"][0]["structured_evidence"]["checks"]
                if item["id"].startswith("measurement:")
            )
            measurement["details"]["statistics"]["median"] += 1

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "statistics or acceptance"):
            self._verify()

    def test_stale_atomic_source_is_rejected(self) -> None:
        self._resign_full_profile(
            lambda value: value["operations"][0]["execution_integrity"].update(
                source_sha="f" * 40
            )
        )
        with self.assertRaisesRegex(AttestationError, "source/profile/invocation"):
            self._verify()

    def test_reused_full_release_invocation_is_rejected(self) -> None:
        self._resign_full_profile(
            lambda value: value["operations"][0]["execution_integrity"].update(
                invocation_id="4" * 32
            )
        )
        with self.assertRaisesRegex(AttestationError, "reuse a producer invocation"):
            self._verify()

    def test_missing_production_receipt_is_rejected_even_when_manifest_resigned(
        self,
    ) -> None:
        attestation = self._attestation()
        entries = attestation["signed_payload"]["evidence_files"]
        receipt = next(item for item in entries if item["role"] == "production-release")
        (self.bundle / receipt["path"]).unlink()
        entries.remove(receipt)
        self._write_resigned(attestation)
        with self.assertRaisesRegex(AttestationError, "production evidence role"):
            self._verify()

    def test_empty_execution_stderr_is_preserved(self) -> None:
        path = self.bundle / "evidence/execution-release/stderr.txt"
        self.assertEqual(b"", path.read_bytes())
        self.assertEqual("CLOUD_VERIFIED", self._verify()["certification_state"])

    def test_empty_required_json_is_rejected(self) -> None:
        attestation = self._attestation()
        entry = next(
            item
            for item in attestation["signed_payload"]["evidence_files"]
            if item["path"] == "evidence/execution-full/result.json"
        )
        (self.bundle / entry["path"]).write_bytes(b"")
        entry.update(bytes=0, sha256=hashlib.sha256(b"").hexdigest())
        self._write_resigned(attestation)
        with self.assertRaisesRegex(AttestationError, "schema validation|empty"):
            self._verify()

    def test_resigned_stream_tampering_is_rejected_against_producer_identity(
        self,
    ) -> None:
        attestation = self._attestation()
        entry = next(
            item
            for item in attestation["signed_payload"]["evidence_files"]
            if item["path"] == "evidence/execution-full/stderr.txt"
        )
        path = self.bundle / entry["path"]
        path.write_bytes(b"changed output")
        entry.update(bytes=path.stat().st_size, sha256=file_sha256(path))
        self._write_resigned(attestation)
        with self.assertRaisesRegex(AttestationError, "stream identity mismatch"):
            self._verify()

    def test_missing_raw_engine_shard_is_rejected_even_when_manifest_resigned(
        self,
    ) -> None:
        attestation = self._attestation()
        entries = attestation["signed_payload"]["evidence_files"]
        entry = next(
            item
            for item in entries
            if item["path"].startswith("evidence/real-engine-full/observations/")
        )
        (self.bundle / entry["path"]).unlink()
        entries.remove(entry)
        self._write_resigned(attestation)
        with self.assertRaisesRegex(AttestationError, "preserved real-engine objects"):
            self._verify()

    def test_resigned_raw_observation_contradiction_is_rejected(self) -> None:
        path = self.bundle / "evidence/real-engine-full/evidence.json"
        raw = audit.load_evidence(path)
        row = next(item for item in raw["rows"] if item["observations"])
        row["observations"][0]["subject_sha256"] = "0" * 64
        raw["run_id"] = audit.DIGEST(
            {"corpus": raw["corpus_sha256"], "rows": raw["rows"]}
        )
        raw["result_sha256"] = audit.DIGEST(
            {key: value for key, value in raw.items() if key != "result_sha256"}
        )
        audit.write_evidence(raw, path)
        attestation = self._attestation()
        for entry in attestation["signed_payload"]["evidence_files"]:
            if entry["role"] == "real-engine-full":
                source = self.bundle / entry["path"]
                entry.update(bytes=source.stat().st_size, sha256=file_sha256(source))
        self._write_resigned(attestation)
        self._resign_full_profile(
            lambda value: value["operations"][1]["structured_evidence"]["checks"][0][
                "evidence"
            ].update(run_id=raw["run_id"])
        )
        with self.assertRaisesRegex(AttestationError, "evidence subject differs"):
            self._verify()

    def test_raw_engine_run_must_match_profile_summary(self) -> None:
        self._resign_full_profile(
            lambda value: value["operations"][1]["structured_evidence"]["checks"][0][
                "evidence"
            ].update(run_id="0" * 64)
        )
        with self.assertRaisesRegex(
            AttestationError, "preserved real-engine evidence differs"
        ):
            self._verify()

    def test_isolated_script_verifies_without_candidate_imports(self) -> None:
        candidate_module = self.repository / "certification.py"
        candidate_module.write_text("raise RuntimeError('candidate code executed')\n")
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                str(ROOT / "tooling/local_certification_attestation.py"),
                "--repository-root",
                str(self.repository),
                "--trust-root",
                str(self.repository),
                "verify",
                "--bundle",
                str(self.bundle),
                "--json",
            ],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(self.repository)},
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual("passed", json.loads(completed.stdout)["status"])

    def test_warm_tree_release_receipt_is_rejected(self) -> None:
        relative = "evidence/production-release/production-candidate-certification.json"
        receipt = json.loads((self.bundle / relative).read_text())
        receipt["deterministic_evidence"]["no_reuse"]["honored"] = False
        receipt["evidence_fingerprint"] = production.fingerprint(
            receipt["deterministic_evidence"]
        )
        self._resign_file(relative, receipt)
        with self.assertRaisesRegex(AttestationError, "independent no-reuse"):
            self._verify()

    def test_production_subject_mismatch_is_rejected(self) -> None:
        relative = "evidence/production-release/production-candidate-certification.json"
        receipt = json.loads((self.bundle / relative).read_text())
        receipt["deterministic_evidence"]["artifact_identities"]["profile"][
            "sha256"
        ] = "0" * 64
        receipt["evidence_fingerprint"] = production.fingerprint(
            receipt["deterministic_evidence"]
        )
        self._resign_file(relative, receipt)
        with self.assertRaisesRegex(AttestationError, "subject identity mismatch"):
            self._verify()

    def test_uncommitted_source_change_is_rejected(self) -> None:
        (self.repository / "core/kernel.rs").write_text("dirty source")
        with self.assertRaisesRegex(AttestationError, "outside closure paths"):
            self._verify()

    def test_matching_but_ungoverned_runtime_claims_are_rejected(self) -> None:
        artifacts = [
            json.loads((self.inputs / f"{profile}.json").read_text())
            for profile in ("full", "release")
        ]
        for artifact in artifacts:
            evidence = artifact["deterministic_evidence"]["operations"][1][
                "structured_evidence"
            ]["checks"][0]["evidence"]
            evidence["runtime_identities"]["node"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(AttestationError, "governed source evidence"):
            _real_engine_claim(artifacts, self.repository, self.source_sha)

    def _add_scoped_waiver(self, *, wrong_version: bool = False) -> None:
        record = yaml.safe_load(
            (
                self.repository / "governance/waivers/WVR-SEC-VSCE-LICENSE-001.yaml"
            ).read_text()
        )
        findings = []
        for match in record["security"]["matches"]:
            for package in match["packages"]:
                for version in match["versions"]:
                    for license_value in match["licenses"]:
                        findings.append(
                            {
                                "code": record["security"]["finding_code"],
                                "message": "Synthetic scoped license metadata test finding",
                                "package": package,
                                "version": version,
                                "license": license_value,
                                "waiver_id": record["waiver_id"],
                            }
                        )
        if wrong_version:
            findings[0]["version"] = "0.0.0"
        structured = {
            "schema_version": "1.0.0",
            "operation_id": "security.dependency-risk",
            "status": "waived",
            "checks": [
                {
                    "check_id": "security.license.lsp-npm",
                    "category": "license",
                    "status": "waived",
                    "inputs": record["scope"]["paths"],
                    "findings": findings,
                }
            ],
        }
        structured = security.SecurityOperation(
            structured["operation_id"],
            "local",
            [
                security.SecurityCheck(
                    **{key: value for key, value in check.items() if key != "findings"},
                    findings=[
                        security.Finding(**finding) for finding in check["findings"]
                    ],
                )
                for check in structured["checks"]
            ],
        ).as_dict()

        def mutate(value):
            value["operations"][-1].update(
                status="waived",
                structured_evidence=structured,
                waiver_references=[record["waiver_id"]],
            )

        self._resign_full_profile(mutate)

    def test_scoped_current_waiver_passes(self) -> None:
        self._add_scoped_waiver()
        with patch("tooling.security.date", wraps=date) as today:
            today.today.return_value = date(2026, 9, 12)
            self.assertEqual("CLOUD_VERIFIED", self._verify()["certification_state"])

    def test_security_failed_check_cannot_be_hidden_by_passing_aggregate(self) -> None:
        structured = security.SecurityOperation(
            "security.repository-local",
            "local",
            [security.SecurityCheck("security.synthetic", "secret", "failed", [])],
        ).as_dict()
        structured["status"] = "passed"
        structured["summary"].update(passed=1, failed=0)
        self._resign_full_profile(
            lambda value: value["operations"][-1].update(structured_evidence=structured)
        )
        with self.assertRaisesRegex(AttestationError, "security producer aggregate"):
            self._verify()

    def test_baseline_validation_uses_authenticated_candidate_fixture_document(
        self,
    ) -> None:
        manifest = json.loads(performance.MANIFEST_PATH.read_text())
        baseline = json.loads(performance.BASELINE_PATH.read_text())
        fixtures = json.loads(performance.FIXTURE_MANIFEST_PATH.read_text())
        fixtures["fixtures"][0]["description"] += " Candidate data revision."
        fixtures["fixture_manifest_fingerprint"] = performance.document_fingerprint(
            fixtures, "fixture_manifest_fingerprint"
        )
        baseline["fixture_manifest_fingerprint"] = fixtures[
            "fixture_manifest_fingerprint"
        ]
        baseline["baseline_fingerprint"] = performance.document_fingerprint(
            baseline, "baseline_fingerprint"
        )
        performance.validate_fixture_manifest(fixtures)
        with self.assertRaisesRegex(
            performance.PerformanceResourceError, "fixture fingerprint changed"
        ):
            performance.validate_baseline(baseline, manifest=manifest)
        with patch.object(performance, "ROOT", self.base / "missing-verifier-data"):
            performance.validate_baseline(
                baseline, manifest=manifest, fixtures=fixtures
            )

    def test_candidate_waiver_scope_cannot_replace_pinned_authority(self) -> None:
        self._add_scoped_waiver()
        trusted = self.base / "trusted-verifier"
        shutil.copytree(self.repository / "governance", trusted / "governance")
        relative = "governance/waivers/WVR-SEC-VSCE-LICENSE-001.yaml"
        record = yaml.safe_load((trusted / relative).read_text())
        record["retirement"]["expires_on"] = "2026-10-10"
        (trusted / relative).write_text(yaml.safe_dump(record))
        with self.assertRaisesRegex(AttestationError, "waiver scope differs"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=trusted,
                bundle_dir=self.bundle,
            )

    def test_expired_signed_waiver_is_rejected(self) -> None:
        self._add_scoped_waiver()
        with patch("tooling.security.date", wraps=date) as today:
            today.today.return_value = date(2026, 10, 12)
            with self.assertRaisesRegex(AttestationError, "SEC-WAIVER-EXPIRED"):
                self._verify()

    def test_changed_waiver_dependency_version_is_rejected(self) -> None:
        self._add_scoped_waiver(wrong_version=True)
        with patch("tooling.security.date", wraps=date) as today:
            today.today.return_value = date(2026, 9, 12)
            with self.assertRaisesRegex(AttestationError, "SEC-WAIVER-SCOPE-STALE"):
                self._verify()

    def test_source_changed_after_certification_is_rejected(self) -> None:
        (self.repository / "core/kernel.rs").write_text("changed\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-m", "change source")
        with self.assertRaisesRegex(AttestationError, "outside closure paths"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_one_evidence_byte_changed_is_rejected(self) -> None:
        path = self.bundle / "evidence/profile-full/full.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(AttestationError, "size mismatch"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_missing_evidence_file_is_rejected(self) -> None:
        (self.bundle / "evidence/profile-release/release.json").unlink()
        with self.assertRaisesRegex(AttestationError, "presence mismatch"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_wrong_profile_fingerprint_is_rejected(self) -> None:
        self._resign_payload_mutation(
            lambda payload: payload["profile_results"][0].update(
                definition_fingerprint="0" * 64
            )
        )
        with self.assertRaisesRegex(AttestationError, "profile result aggregate"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_stale_attestation_replay_is_rejected(self) -> None:
        (self.repository / "outside.txt").write_text("new source\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-m", "advance")
        with self.assertRaisesRegex(AttestationError, "outside closure paths"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_untrusted_certifier_is_rejected(self) -> None:
        trust = copy.deepcopy(self.trust)
        trust["authorized_certifiers"][0]["certifier_id"] = "other-certifier"
        (self.repository / "governance/local-certification-trust.json").write_text(
            json.dumps(trust), encoding="utf-8"
        )
        with self.assertRaisesRegex(AttestationError, "not uniquely authorized"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_malformed_signature_is_rejected(self) -> None:
        attestation = self._attestation()
        attestation["signature"]["signature_base64"] = "not-base64"
        (self.bundle / "attestation.json").write_text(
            json.dumps(attestation), encoding="utf-8"
        )
        with self.assertRaises(AttestationError):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_passing_aggregate_with_failed_producer_is_rejected(self) -> None:
        path = self.bundle / "evidence/profile-full/full.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["deterministic_evidence"]["operations"][0]["structured_evidence"][
            "status"
        ] = "failed"
        artifact["evidence_fingerprint"] = object_sha256(
            artifact["deterministic_evidence"]
        )
        path.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        attestation = self._attestation()
        entry = next(
            item
            for item in attestation["signed_payload"]["evidence_files"]
            if item["path"] == "evidence/profile-full/full.json"
        )
        entry["bytes"] = path.stat().st_size
        entry["sha256"] = file_sha256(path)
        attestation["signed_payload"]["profile_results"][0]["evidence_fingerprint"] = (
            artifact["evidence_fingerprint"]
        )
        self._write_resigned(attestation)
        with self.assertRaisesRegex(AttestationError, "outer status contradicts"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_performance_sample_count_altered_is_rejected(self) -> None:
        self._resign_payload_mutation(
            lambda payload: payload["authenticated_sample_counts"].update(
                {next(iter(payload["authenticated_sample_counts"])): 1}
            )
        )
        with self.assertRaisesRegex(AttestationError, "sample count mismatch"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_real_engine_evidence_altered_is_rejected(self) -> None:
        self._resign_payload_mutation(
            lambda payload: payload["real_engine_evidence"].update(
                runtime_executions=1530
            )
        )
        with self.assertRaisesRegex(AttestationError, "real-engine evidence aggregate"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_waiver_added_after_certification_is_rejected(self) -> None:
        self._resign_payload_mutation(
            lambda payload: payload["waiver_inventory"].append("WVR-FAKE-001")
        )
        with self.assertRaisesRegex(AttestationError, "waiver inventory"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_wrong_invocation_id_is_rejected(self) -> None:
        self._resign_payload_mutation(
            lambda payload: payload["producer_invocation_ids"].append("f" * 32)
        )
        with self.assertRaisesRegex(AttestationError, "producer invocation"):
            verify_attestation(
                repository_root=self.repository,
                trust_root=self.repository,
                bundle_dir=self.bundle,
            )

    def test_evidence_root_is_deterministically_reproducible(self) -> None:
        payload = self._attestation()["signed_payload"]
        root = payload.pop("evidence_root_sha256")
        self.assertEqual(root, object_sha256(payload))

    def test_performance_required_resource_check_cannot_be_omitted(self) -> None:
        def mutate(value):
            checks = value["operations"][0]["structured_evidence"]["checks"]
            checks[:] = [
                check for check in checks if check["id"] != "resource:kernel-limits"
            ]

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "successful check denominator"):
            self._verify()

    def test_performance_latency_elapsed_must_normalize_to_samples(self) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"].startswith("measurement:latency:")
            )
            details["batch_duration_samples"][0] += details["batch_iterations"]

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "batch normalization"):
            self._verify()

    def test_performance_latency_batch_must_equal_governed_batch(self) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"].startswith("measurement:latency:")
            )
            details["batch_iterations"] += 1
            details["batch_duration_samples"] = [
                sample * details["batch_iterations"] for sample in details["samples"]
            ]

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "governed batch or unit"):
            self._verify()

    def test_performance_failed_resource_step_cannot_claim_passed(self) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"] == "resource:kernel-limits"
            )
            details["steps"][0]["return_code"] = 1

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "command or terminal"):
            self._verify()

    def test_performance_workload_observation_cannot_claim_isolation(self) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"].startswith("environment:external-workload-isolation/")
            )
            details["observed_workloads"] = [{"name": "cargo", "process_id": 123}]

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "workload isolation"):
            self._verify()

    def test_performance_cpu_check_must_match_governed_placement(self) -> None:
        def mutate(value):
            check = value["operations"][0]["structured_evidence"]["checks"][0]
            check["details"]["effective_cpu_affinity"].append(0)

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "CPU placement"):
            self._verify()

    def test_performance_candidate_rebind_cannot_claim_normal_certification(
        self,
    ) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"] == "build:baseline-artifact-identity"
            )
            details["candidate_rebind"] = True

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "baseline artifact identity"):
            self._verify()

    def test_performance_conditioning_snapshot_is_independently_bound(self) -> None:
        def mutate(value):
            details = next(
                check["details"]
                for check in value["operations"][0]["structured_evidence"]["checks"]
                if check["id"].startswith("environment:measurement-conditioning/")
            )
            details["snapshot_fingerprint"] = "0" * 64

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "quiescence or snapshot"):
            self._verify()

    def test_performance_controlled_regression_cannot_be_relabelled(self) -> None:
        def mutate(value):
            check = value["operations"][0]["structured_evidence"]["checks"][-1]
            check["details"]["comparison"]["status"] = "passed"

        self._resign_full_profile(mutate)
        with self.assertRaisesRegex(AttestationError, "controlled regression"):
            self._verify()


if __name__ == "__main__":
    unittest.main()
