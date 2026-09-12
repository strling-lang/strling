#!/usr/bin/env python3
"""Create and verify trusted attestations for authoritative local certification."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import importlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

try:
    from .certification import (
        operation_registry_fingerprint,
        profile_definition_fingerprint,
        profile_registry_fingerprint,
        validate_certification_artifact,
    )
except ImportError:  # pragma: no cover - direct script execution
    # Isolated Python omits both the script directory and PYTHONPATH. Bootstrap
    # only this verifier's package; candidate files remain data, never imports.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tooling.certification import (
        operation_registry_fingerprint,
        profile_definition_fingerprint,
        profile_registry_fingerprint,
        validate_certification_artifact,
    )


ATTESTATION_KIND = "strling-local-certification-attestation"
ATTESTATION_VERSION = "1.0.0"
TRUST_KIND = "strling-local-certification-trust"
TRUST_VERSION = "1.0.0"
CONTRACT_OPERATION = "certification.local-attestation-contract"
VERIFY_OPERATION = "certification.local-attestation-verification"
SUCCESS_STATUSES = {"passed", "waived"}
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROLE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
PERFORMANCE_DIRECTORY = "tests/certification/performance-resource/1.0"


def _helper_module(name: str) -> Any:
    """Import verifier-owned helpers, including when invoked as a script."""
    if not __package__:
        trusted_parent = str(Path(__file__).resolve().parents[1])
        if sys.path[0] != trusted_parent:
            sys.path.insert(0, trusted_parent)
    return importlib.import_module(f"tooling.{name}")


class AttestationError(ValueError):
    """Raised when certification evidence is incomplete or untrusted."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def object_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttestationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AttestationError(f"JSON document must be an object: {path}")
    return value


def _validate_schema(document: Mapping[str, object], schema_path: Path) -> None:
    schema = _load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
    except (SchemaError, ValidationError) as exc:
        raise AttestationError(
            f"schema validation failed for {schema_path}: {exc}"
        ) from exc


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise AttestationError(
            f"git {' '.join(arguments)} failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def _git_bytes(root: Path, source_sha: str, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{source_sha}:{relative}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise AttestationError(
            f"cannot read {relative} at {source_sha}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def _git_json(root: Path, source_sha: str, relative: str) -> dict[str, Any]:
    try:
        value = json.loads(_git_bytes(root, source_sha, relative))
    except json.JSONDecodeError as exc:
        raise AttestationError(
            f"invalid JSON at {source_sha}:{relative}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise AttestationError(f"expected object at {source_sha}:{relative}")
    return value


def _public_key_fingerprint(public_key: str) -> str:
    parts = public_key.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise AttestationError("authorized certifier key must be ssh-ed25519")
    try:
        wire_key = base64.b64decode(parts[1], validate=True)
    except ValueError as exc:
        raise AttestationError("authorized certifier public key is malformed") from exc
    encoded = base64.b64encode(hashlib.sha256(wire_key).digest()).decode("ascii")
    return f"SHA256:{encoded.rstrip('=')}"


def load_trust_policy(trust_root: Path) -> dict[str, Any]:
    path = trust_root / "governance/local-certification-trust.json"
    trust = _load_json(path)
    _validate_schema(
        trust,
        trust_root / "governance/schemas/local-certification-trust.schema.json",
    )
    if (
        trust.get("schema_version") != TRUST_VERSION
        or trust.get("policy_kind") != TRUST_KIND
    ):
        raise AttestationError("unsupported local certification trust policy")
    certifiers = trust["authorized_certifiers"]
    identities = [item["certifier_id"] for item in certifiers]
    fingerprints = [item["ssh_key_fingerprint"] for item in certifiers]
    if len(identities) != len(set(identities)):
        raise AttestationError("duplicate authorized certifier identity")
    if len(fingerprints) != len(set(fingerprints)):
        raise AttestationError("duplicate authorized certifier key fingerprint")
    for certifier in certifiers:
        actual = _public_key_fingerprint(certifier["public_key"])
        if actual != certifier["ssh_key_fingerprint"]:
            raise AttestationError(
                f"authorized certifier {certifier['certifier_id']} key fingerprint mismatch"
            )
    return trust


def validate_contract(repository_root: Path, trust_root: Path) -> dict[str, Any]:
    trust = load_trust_policy(trust_root)
    toolchain = _load_json(repository_root / "toolchain.json")
    profiles = toolchain.get("policy", {}).get("profiles")
    if not isinstance(profiles, dict):
        raise AttestationError("toolchain profile registry is missing")
    for profile in trust["required_profiles"]:
        if profile not in profiles:
            raise AttestationError(
                f"required certification profile is missing: {profile}"
            )
    bundle = PurePosixPath(trust["bundle_path"])
    if bundle.is_absolute() or ".." in bundle.parts:
        raise AttestationError("certification bundle path must be repository-relative")
    for pattern in trust["closure_paths"]:
        candidate = PurePosixPath(pattern)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AttestationError(f"unsafe closure path pattern: {pattern}")
    return trust


def _result(
    operation_id: str, status: str, checks: list[dict[str, object]]
) -> dict[str, object]:
    summary = {
        name: 0 for name in ("passed", "failed", "waived", "unavailable", "incomplete")
    }
    summary[status] = 1
    return {
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "status": status,
        "checks": checks,
        "summary": summary,
    }


def contract_result(repository_root: Path, trust_root: Path) -> dict[str, object]:
    try:
        trust = validate_contract(repository_root, trust_root)
    except AttestationError as exc:
        return _result(
            CONTRACT_OPERATION,
            "failed",
            [
                {
                    "check_id": f"{CONTRACT_OPERATION}.trust-policy",
                    "status": "failed",
                    "findings": [
                        {
                            "code": "CERT-LOCAL-ATTESTATION-0001",
                            "message": str(exc),
                        }
                    ],
                }
            ],
        )
    return _result(
        CONTRACT_OPERATION,
        "passed",
        [
            {
                "check_id": f"{CONTRACT_OPERATION}.trust-policy",
                "status": "passed",
                "evidence": {
                    "required_profiles": trust["required_profiles"],
                    "certifier_ids": [
                        item["certifier_id"] for item in trust["authorized_certifiers"]
                    ],
                    "bundle_path": trust["bundle_path"],
                },
            }
        ],
    )


def _nested_status_consistency(artifact: Mapping[str, Any]) -> None:
    operations = artifact["deterministic_evidence"]["operations"]
    for operation in operations:
        structured = operation.get("structured_evidence")
        if not isinstance(structured, dict):
            continue
        nested = structured.get("status")
        if nested is not None and nested != operation["status"]:
            raise AttestationError(
                f"{operation['result_id']} outer status contradicts producer status"
            )


def _validate_atomic_evidence(
    repository_root: Path,
    trust_root: Path,
    source_sha: str,
    profile: str,
    operation: Mapping[str, Any],
    definition: Mapping[str, Any],
) -> None:
    transport = _helper_module("structured_operation_execution")
    integrity = operation.get("execution_integrity")
    structured = operation.get("structured_evidence")
    if not isinstance(integrity, dict) or not isinstance(structured, dict):
        raise AttestationError("atomic producer is missing invocation-bound evidence")
    reconstructed = {
        key: value
        for key, value in integrity.items()
        if key not in ("artifact_directory", "streams")
    }
    reconstructed.update(structured_result=structured, integrity_error=None)
    _validate_schema(
        reconstructed,
        trust_root / "governance/schemas/structured-operation-execution.schema.json",
    )
    if reconstructed["artifact_fingerprint"] != transport.document_fingerprint(
        reconstructed
    ):
        raise AttestationError("atomic producer artifact fingerprint mismatch")
    command = definition["command"]
    producer_profile = command[command.index("--profile") + 1]
    expected = {
        "source_sha": source_sha,
        "certification_profile": profile,
        "producer_profile": producer_profile,
        "producer_id": operation["result_id"],
        "operation_id": definition["result_operation_id"],
        "result_contract": definition["result_contract"],
        "terminal_status": operation["status"],
        "process_exit_code": 0,
        "performance_evidence_identity": structured.get("evidence_fingerprint"),
        "environment_identity": transport.extract_environment_identity(structured),
    }
    if any(reconstructed.get(key) != value for key, value in expected.items()):
        raise AttestationError(
            "atomic producer source/profile/invocation binding mismatch"
        )
    if (
        structured.get("commit") != source_sha
        or structured.get("profile") != producer_profile
        or structured.get("schema_version") != definition["result_contract"]
    ):
        raise AttestationError("atomic structured evidence source or profile mismatch")
    if operation["operation_id"] == "performance_resource_full_certification":
        _validate_performance_measurements(
            repository_root, source_sha, structured, integrity
        )


def _validate_security_evidence(
    structured: Mapping[str, Any], trust_root: Path
) -> None:
    security = _helper_module("security")
    _validate_schema(
        structured, trust_root / "governance/schemas/security-result.schema.json"
    )
    checks = [
        security.SecurityCheck(
            **{
                key: value
                for key, value in check.items()
                if key not in ("findings", "finding_codes")
            },
            findings=[security.Finding(**finding) for finding in check["findings"]],
        )
        for check in structured["checks"]
    ]
    rebuilt = security.SecurityOperation(
        structured["operation_id"], structured["network_mode"], checks
    ).as_dict()
    if any(structured[key] != rebuilt[key] for key in ("status", "summary", "checks")):
        raise AttestationError("security producer aggregate contradicts check evidence")


def _validate_performance_measurements(
    repository_root: Path,
    source_sha: str,
    structured: Mapping[str, Any],
    integrity: Mapping[str, Any],
) -> None:
    performance = _helper_module("performance_resource_certification")
    manifest = _git_json(
        repository_root, source_sha, f"{PERFORMANCE_DIRECTORY}/manifest.json"
    )
    baseline = _git_json(
        repository_root, source_sha, f"{PERFORMANCE_DIRECTORY}/baseline.json"
    )
    fixtures = _git_json(
        repository_root, source_sha, manifest["fixture_manifest"]["path"]
    )
    inventory = _git_json(
        repository_root, source_sha, manifest["resource_inventory"]["path"]
    )
    try:
        performance.validate_manifest(
            manifest, root=repository_root, fixtures=fixtures, inventory=inventory
        )
        performance.validate_evidence(structured, manifest=manifest)
        performance.validate_fixture_manifest(fixtures)
        performance.validate_baseline(baseline, manifest=manifest, fixtures=fixtures)
    except ValueError as exc:
        raise AttestationError(f"invalid governed performance evidence: {exc}") from exc
    if structured.get("evidence_kind") != "live-certification":
        raise AttestationError("performance evidence is not live certification")
    checks = structured["checks"]
    ids = [item["id"] for item in checks]
    if len(ids) != len(set(ids)) or any(item["status"] != "passed" for item in checks):
        raise AttestationError("performance checks are duplicated or nonpassing")
    rows = {item["id"]: item for item in checks}
    environment = rows.get("environment:fingerprinted-native-x86_64", {}).get(
        "details", {}
    )
    conditioning = rows.get("environment:identical-conditioning", {}).get("details", {})
    expected_environment = performance.environment_identity_fingerprint(
        baseline["environment"]
    )
    expected_conditioning = performance.conditioning_identity_fingerprint(
        baseline["conditioning_repetitions"][0]
    )
    if (
        environment.get("baseline_fingerprint") != baseline["environment_fingerprint"]
        or environment.get("baseline_identity_fingerprint") != expected_environment
        or environment.get("observed_identity_fingerprint") != expected_environment
        or environment.get("governed_mismatches") != []
        or environment.get("exact_match") is not True
        or conditioning.get("baseline_conditioning_identity_fingerprint")
        != expected_conditioning
        or conditioning.get("conditioning_identity_fingerprint")
        != expected_conditioning
        or conditioning.get("identical_conditioning_identity") is not True
    ):
        raise AttestationError(
            "performance environment or conditioning differs from baseline"
        )
    keys = performance.performance_measurement_keys(manifest)
    expected_ids = {
        f"{operation}/{fixture or 'fixture-free'}" for operation, fixture in keys
    }
    measured = {
        key.removeprefix("measurement:")
        for key in ids
        if key.startswith("measurement:")
    }
    if measured != expected_ids:
        raise AttestationError(
            "performance measurement coordinate denominator mismatch"
        )
    ordered = list(keys)
    performance.random.Random(manifest["measurement_policy"]["order_seed"]).shuffle(
        ordered
    )
    expected_checks = [
        "environment:single-fixed-logical-cpu",
        "build:release-performance-artifacts",
        "build:baseline-artifact-identity",
        "environment:fingerprinted-native-x86_64",
        "environment:identical-conditioning",
    ]
    for operation_id, fixture_id in ordered:
        coordinate = f"{operation_id}/{fixture_id or 'fixture-free'}"
        expected_checks.extend(
            [
                f"environment:external-workload-isolation/pre-measurement/{coordinate}",
                f"environment:measurement-conditioning/{coordinate}",
                f"measurement:{coordinate}",
                f"environment:external-workload-isolation/post-measurement/{coordinate}",
            ]
        )
    expected_checks.extend(performance.RESOURCE_OPERATION_IDS)
    expected_checks.append("controlled:one-unit-relative-regression")
    if ids != expected_checks:
        raise AttestationError(
            "performance successful check denominator or order mismatch"
        )
    selected_cpu = manifest["measurement_policy"]["selected_logical_cpu"]
    if rows["environment:single-fixed-logical-cpu"]["details"] != {
        "selected_logical_cpu": selected_cpu,
        "effective_cpu_affinity": [selected_cpu],
        "effective_cpuset": performance._format_cpu_set([selected_cpu]),
    }:
        raise AttestationError("performance CPU placement differs from governed policy")

    def validate_steps(steps: Any, commands: Sequence[Sequence[str]]) -> None:
        if not isinstance(steps, list) or len(steps) != len(commands):
            raise AttestationError("performance command step denominator mismatch")
        for step, command in zip(steps, commands):
            observed = step.get("command") if isinstance(step, dict) else None
            if (
                not isinstance(observed, list)
                or not all(isinstance(value, str) for value in observed)
                or not observed
            ):
                raise AttestationError("performance command evidence is malformed")
            observed = [value.replace("\\", "/") for value in observed]
            executable = PurePosixPath(observed[0]).name
            if executable not in ("cargo", "cargo.exe"):
                raise AttestationError(
                    "performance command does not use governed Cargo"
                )
            observed[0] = "cargo"
            if len(observed) > 1 and observed[1] != "+1.75.0":
                observed.insert(1, "+1.75.0")
            expected = list(command)
            if expected[-1] == performance.RESOURCE_TARGET_DIRECTORY:
                if not observed[-1].endswith(
                    "/" + performance.RESOURCE_TARGET_DIRECTORY
                ):
                    raise AttestationError(
                        "performance resource target directory mismatch"
                    )
                observed[-1] = performance.RESOURCE_TARGET_DIRECTORY
            if (
                observed != expected
                or step.get("status") != "passed"
                or type(step.get("return_code")) is not int
                or step["return_code"] != 0
                or not isinstance(step.get("output_sha256"), str)
                or not SHA256.fullmatch(step["output_sha256"])
            ):
                raise AttestationError(
                    "performance command or terminal evidence mismatch"
                )

    build = rows["build:release-performance-artifacts"]["details"]
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
    validate_steps(build.get("steps"), build_commands)
    observed_artifacts = build.get("artifacts", {})
    try:
        performance.validate_definition(
            observed_artifacts,
            definition="artifactFingerprints",
            label="built artifacts",
        )
    except ValueError as exc:
        raise AttestationError(
            f"invalid performance build artifact identities: {exc}"
        ) from exc
    if any(
        observed_artifacts[name]["path"]
        != baseline["artifact_fingerprints"][name]["path"]
        for name in ("runner", "kernel", "interop")
    ) or build.get("canonical_build_root") != (
        f"{performance.WINDOWS_CANONICAL_BUILD_DRIVE}/"
        if baseline["environment"]["os"] == "windows"
        else None
    ):
        raise AttestationError(
            "performance build artifact path or canonical root mismatch"
        )
    exact_artifacts = performance._artifact_fingerprints_match(
        baseline["artifact_fingerprints"], observed_artifacts
    )
    source_changes = None
    if not exact_artifacts:
        try:
            source_changes = performance._artifact_source_changes(
                baseline_source_commit=baseline["source_commit"],
                candidate_source_commit=source_sha,
                root=repository_root,
            )
        except ValueError as exc:
            raise AttestationError(
                f"invalid performance artifact source binding: {exc}"
            ) from exc
    accepted, artifact_identity = performance._artifact_identity_check(
        baseline["artifact_fingerprints"],
        observed_artifacts,
        baseline_source_commit=baseline["source_commit"],
        candidate_source_commit=source_sha,
        source_changes=source_changes,
    )
    if not accepted or rows["build:baseline-artifact-identity"]["details"] != {
        "baseline_artifacts": baseline["artifact_fingerprints"],
        "observed_artifacts": observed_artifacts,
        "exact_match": exact_artifacts,
        "candidate_rebind": False,
        "candidate_identity": artifact_identity,
    }:
        raise AttestationError("performance baseline artifact identity mismatch")
    for operation_id in performance.RESOURCE_OPERATION_IDS:
        validate_steps(
            rows[operation_id]["details"].get("steps"),
            [
                [*command, "--target-dir", performance.RESOURCE_TARGET_DIRECTORY]
                for command in performance.RESOURCE_COMMANDS[operation_id]
            ],
        )
    if rows[
        "controlled:one-unit-relative-regression"
    ] != performance._controlled_regression_check(baseline):
        raise AttestationError("performance controlled regression evidence mismatch")
    operations = {item["id"]: item for item in manifest["operations"]}
    baselines = {
        (item["operation_id"], item["fixture_id"]): item
        for item in baseline["measurements"]
    }
    sample_total = 0
    for key in keys:
        coordinate = f"{key[0]}/{key[1] or 'fixture-free'}"
        details = rows[f"measurement:{coordinate}"]["details"]
        samples = details.get("samples")
        definition = operations[key[0]]
        expected_count = performance._expected_repetition_sample_count(
            definition, manifest
        )
        if (
            not isinstance(samples, list)
            or len(samples) != expected_count
            or any(type(value) is not int or value < 0 for value in samples)
        ):
            raise AttestationError(
                f"performance sample denominator mismatch: {coordinate}"
            )
        statistics = performance.sample_statistics(samples)
        source = baselines[key]
        batch = details.get("batch_iterations")
        elapsed = details.get("batch_duration_samples")
        if (
            type(batch) is not int
            or batch != source["batch_iterations"]
            or details.get("unit") != source["unit"]
        ):
            raise AttestationError(
                f"performance governed batch or unit mismatch: {coordinate}"
            )
        if definition["measurement_kind"] == "latency":
            if (
                not isinstance(elapsed, list)
                or len(elapsed) != expected_count
                or any(type(value) is not int or value < 0 for value in elapsed)
                or samples
                != [max(1, (value + batch // 2) // batch) for value in elapsed]
            ):
                raise AttestationError(
                    f"performance batch normalization mismatch: {coordinate}"
                )
        elif elapsed is not None or batch != 1:
            raise AttestationError(
                f"performance non-latency batch mismatch: {coordinate}"
            )
        for phase in ("pre-measurement", "post-measurement"):
            isolation = rows[
                f"environment:external-workload-isolation/{phase}/{coordinate}"
            ]["details"]
            if isolation != {
                "phase": phase,
                "observed_workloads": [],
                "unrelated_heavyweight_workloads_absent": True,
            }:
                raise AttestationError(
                    f"performance workload isolation mismatch: {coordinate}"
                )
        conditioned = rows[f"environment:measurement-conditioning/{coordinate}"][
            "details"
        ]
        attempt = conditioned.get("attempt")
        rejected = conditioned.get("rejected_attempts")
        if (
            type(attempt) is not int
            or not 1 <= attempt <= performance.MEASUREMENT_CONDITIONING_MAX_ATTEMPTS
            or conditioned.get("maximum_attempts")
            != performance.MEASUREMENT_CONDITIONING_MAX_ATTEMPTS
            or conditioned.get("retry_delay_seconds")
            != performance.MEASUREMENT_CONDITIONING_RETRY_DELAY_SECONDS
            or not isinstance(rejected, list)
            or len(rejected) != attempt - 1
            or conditioned.get("conditioning_identity_fingerprint")
            != expected_conditioning
        ):
            raise AttestationError(
                f"performance measurement conditioning mismatch: {coordinate}"
            )
        if baseline["environment"]["os"] == "windows":
            observation = conditioned.get("quiescence_observation", {})
            try:
                performance.validate_definition(
                    observation,
                    definition="quiescenceObservation",
                    label="measurement quiescence",
                )
            except ValueError as exc:
                raise AttestationError(
                    f"invalid performance quiescence evidence: {exc}"
                ) from exc
            snapshot = dict(baseline["conditioning_repetitions"][0])
            snapshot["quiescence_observation"] = observation
            if performance.performance_windows.evaluate_quiescence(
                observation
            ) or conditioned.get(
                "snapshot_fingerprint"
            ) != performance.document_fingerprint(snapshot, "snapshot_fingerprint"):
                raise AttestationError(
                    f"performance quiescence or snapshot mismatch: {coordinate}"
                )
        comparison = performance.compare_hard_metric(
            baseline_median=source["statistics"]["median"],
            observed_median=statistics["median"],
            relative_regression_basis_points=source["budget"][
                "relative_regression_basis_points"
            ],
            absolute_ceiling=source["budget"]["absolute_ceiling"],
        )
        if (
            details.get("statistics") != statistics
            or details.get("comparison") != comparison
            or details.get("enforcement") != definition["enforcement"]
            or details.get("disposition")
            != (
                "release-blocking"
                if definition["enforcement"] == "hard"
                else "informational-trend"
            )
            or details.get("would_exceed_budget")
            is not (comparison["status"] == "failed")
            or performance.certification_measurement_status(
                enforcement=definition["enforcement"],
                comparison_status=comparison["status"],
            )
            != "passed"
        ):
            raise AttestationError(
                f"performance statistics or acceptance mismatch: {coordinate}"
            )
        sample_total += expected_count
    consumption = integrity["sample_consumption"]
    if (
        consumption.get("state") != "consumed"
        or consumption.get("authenticated_sample_count") != sample_total
        or consumption.get("completed_sample_count") != sample_total
        or consumption.get("coordinates_started") != len(keys)
        or consumption.get("coordinates_completed") != len(keys)
        or set(consumption.get("completed_coordinate_ids", [])) != expected_ids
        or consumption.get("completed_coordinate_ids")
        != [
            f"{operation}/{fixture or 'fixture-free'}" for operation, fixture in ordered
        ]
        or consumption.get("current_coordinate_id") is not None
    ):
        raise AttestationError(
            "authenticated performance sample ledger denominator mismatch"
        )


def _profile_claim(
    repository_root: Path,
    artifact_path: Path,
    expected_profile: str,
    source_sha: str,
    source_toolchain: Mapping[str, Any],
    evidence_path: str,
    trust_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = _load_json(artifact_path)
    try:
        validate_certification_artifact(trust_root, artifact)
    except Exception as exc:
        raise AttestationError(
            f"invalid {expected_profile} profile artifact: {exc}"
        ) from exc
    _nested_status_consistency(artifact)
    deterministic = artifact["deterministic_evidence"]
    repository = deterministic["repository"]
    profile = deterministic["profile"]
    aggregate = deterministic["aggregate"]
    if repository != {"commit": source_sha, "dirty": False}:
        raise AttestationError(
            f"{expected_profile} profile is not bound to clean source {source_sha}"
        )
    if profile["id"] != expected_profile:
        raise AttestationError(f"expected {expected_profile} profile artifact")
    if aggregate["status"] not in SUCCESS_STATUSES or aggregate["exit_code"] != 0:
        raise AttestationError(
            f"{expected_profile} profile is not terminally successful"
        )
    definition = source_toolchain["policy"]["profiles"].get(expected_profile)
    if not isinstance(definition, dict):
        raise AttestationError(
            f"source profile definition is missing: {expected_profile}"
        )
    if profile["definition_version"] != definition.get("definition_version"):
        raise AttestationError(f"{expected_profile} profile version mismatch")
    if profile["definition_fingerprint"] != profile_definition_fingerprint(definition):
        raise AttestationError(f"{expected_profile} profile fingerprint mismatch")
    expected_ids = _helper_module("product_certification").expected_profile_result_ids(
        source_toolchain, expected_profile
    )
    if (
        deterministic["component_scope"] != {"mode": "profile-default"}
        or [item["result_id"] for item in deterministic["operations"]] != expected_ids
    ):
        raise AttestationError(
            f"{expected_profile} evidence does not contain the complete ordered profile"
        )
    for operation in deterministic["operations"]:
        definition = source_toolchain["policy"]["operation_registry"][
            operation["operation_id"]
        ]
        structured = operation.get("structured_evidence")
        if definition.get("result_contract") is not None and (
            not isinstance(structured, dict)
            or structured.get("operation_id") != definition.get("result_operation_id")
        ):
            raise AttestationError(
                f"{operation['result_id']} producer evidence is missing"
            )
        if isinstance(structured, dict) and str(
            structured.get("operation_id", "")
        ).startswith("security."):
            _validate_security_evidence(structured, trust_root)
        if definition.get("result_transport") == "atomic-artifact-v1":
            _validate_atomic_evidence(
                repository_root,
                trust_root,
                source_sha,
                expected_profile,
                operation,
                definition,
            )
    claim = {
        "profile": expected_profile,
        "definition_version": profile["definition_version"],
        "definition_fingerprint": profile["definition_fingerprint"],
        "evidence_fingerprint": artifact["evidence_fingerprint"],
        "status": aggregate["status"],
        "exit_code": aggregate["exit_code"],
        "operation_count": aggregate["operation_count"],
        "counts": aggregate["counts"],
        "evidence_path": evidence_path,
    }
    return claim, artifact


def _walk(value: object) -> Iterable[tuple[str, object]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key, nested
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _waivers(artifacts: Iterable[Mapping[str, Any]]) -> list[str]:
    values: set[str] = set()
    for artifact in artifacts:
        for key, value in _walk(artifact):
            if key == "waiver_id" and isinstance(value, str):
                values.add(value)
            elif key == "waiver_references" and isinstance(value, list):
                values.update(item for item in value if isinstance(item, str))
    return sorted(values)


def _validate_waiver_scope(
    repository_root: Path,
    trust_root: Path,
    source_sha: str,
    artifacts: Sequence[Mapping[str, Any]],
) -> None:
    if not _waivers(artifacts):
        return
    security = _helper_module("security")
    policy = _git_json(repository_root, source_sha, "governance/security-policy.json")
    _validate_schema(
        policy, trust_root / "governance/schemas/security-policy.schema.json"
    )
    trusted_policy = _load_json(trust_root / "governance/security-policy.json")
    if policy["security_waivers"] != trusted_policy["security_waivers"]:
        raise AttestationError("security waiver authority differs from trusted policy")
    for waiver_id in policy["security_waivers"]:
        relative = f"governance/waivers/{waiver_id}.yaml"
        record = security.yaml.safe_load(
            _git_bytes(repository_root, source_sha, relative)
        )
        _validate_schema(record, trust_root / "governance/schemas/waiver.schema.json")
        if record != security.yaml.safe_load(
            (trust_root / relative).read_text(encoding="utf-8")
        ):
            raise AttestationError(
                "security waiver scope differs from trusted authority"
            )
    engine = security.SecurityEngine(trust_root, trusted_policy, tracked_files=[])
    matched = set()
    for artifact in artifacts:
        for operation in artifact["deterministic_evidence"]["operations"]:
            structured = operation.get("structured_evidence")
            if (
                not isinstance(structured, dict)
                or structured.get("operation_id") != "security.dependency-risk"
            ):
                continue
            checks = []
            original_assignments = {}
            for check in structured["checks"]:
                if check["check_id"] == "security.waivers":
                    continue
                findings = []
                for index, finding in enumerate(check["findings"]):
                    value = dict(finding)
                    original_assignments[(check["check_id"], index)] = value.pop(
                        "waiver_id", None
                    )
                    findings.append(security.Finding(**value))
                checks.append(
                    security.SecurityCheck(
                        check["check_id"],
                        check["category"],
                        "failed" if check["status"] == "waived" else check["status"],
                        check["inputs"],
                        findings=findings,
                    )
                )
            rebuilt = engine._apply_security_waivers(
                security.SecurityOperation(structured["operation_id"], "local", checks)
            )
            if rebuilt.status not in SUCCESS_STATUSES:
                errors = [
                    finding.code
                    for check in rebuilt.checks
                    for finding in check.findings
                    if finding.code.startswith("SEC-WAIVER-")
                ]
                raise AttestationError(
                    "governed waiver is expired or out of scope: " + ", ".join(errors)
                )
            for check in rebuilt.checks:
                if check.check_id == "security.waivers":
                    continue
                for index, finding in enumerate(check.findings):
                    if (
                        finding.waiver_id
                        != original_assignments[(check.check_id, index)]
                    ):
                        raise AttestationError(
                            "waiver assignment differs from governed scope"
                        )
                    if finding.waiver_id:
                        matched.add(finding.waiver_id)
    if matched != set(_waivers(artifacts)):
        raise AttestationError(
            "waiver inventory has no corresponding scoped security finding"
        )


def _producer_invocations(artifacts: Iterable[Mapping[str, Any]]) -> list[str]:
    values: set[str] = set()
    for artifact in artifacts:
        operations = artifact["deterministic_evidence"]["operations"]
        for operation in operations:
            integrity = operation.get("execution_integrity")
            if isinstance(integrity, dict):
                identity = integrity.get("invocation_id")
                if isinstance(identity, str):
                    if identity in values:
                        raise AttestationError(
                            "Full and Release reuse a producer invocation"
                        )
                    values.add(identity)
    return sorted(values)


def _sample_counts(artifacts: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for artifact in artifacts:
        profile = artifact["deterministic_evidence"]["profile"]["id"]
        operations = artifact["deterministic_evidence"]["operations"]
        for operation in operations:
            integrity = operation.get("execution_integrity")
            if not isinstance(integrity, dict):
                continue
            consumption = integrity.get("sample_consumption")
            if not isinstance(consumption, dict):
                continue
            count = consumption.get("authenticated_sample_count")
            if isinstance(count, int):
                counts[f"{profile}:{operation['operation_id']}"] = count
    return dict(sorted(counts.items()))


def _require_authenticated_samples(counts: Mapping[str, int]) -> None:
    for profile in ("full", "release"):
        key = f"{profile}:performance_resource_full_certification"
        if counts.get(key, 0) <= 0:
            raise AttestationError(
                f"{profile} evidence has no authenticated governed performance samples"
            )


def _real_engine_claim(
    artifacts: Iterable[Mapping[str, Any]],
    repository_root: Path,
    source_sha: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    counts: dict[str, int] | None = None
    runtime_identities: dict[str, Any] | None = None
    run_ids: set[str] = set()
    for artifact in artifacts:
        operations = artifact["deterministic_evidence"]["operations"]
        operation = next(
            (
                item
                for item in operations
                if item["operation_id"] == "adversarial_real_engine_equivalence"
            ),
            None,
        )
        if operation is None:
            raise AttestationError(
                "profile is missing real-engine equivalence evidence"
            )
        structured = operation.get("structured_evidence")
        if not isinstance(structured, dict) or structured.get("status") != "passed":
            raise AttestationError("real-engine equivalence producer did not pass")
        checks = structured.get("checks")
        if not isinstance(checks, list) or len(checks) != 1:
            raise AttestationError("real-engine equivalence evidence is malformed")
        evidence = checks[0].get("evidence")
        if not isinstance(evidence, dict):
            raise AttestationError("real-engine equivalence evidence is missing")
        observed = evidence.get("counts")
        identities = evidence.get("runtime_identities")
        findings = evidence.get("findings")
        run_id = evidence.get("run_id")
        if not isinstance(observed, dict) or not isinstance(identities, dict):
            raise AttestationError(
                "real-engine counts or runtime identities are missing"
            )
        if findings != [] or evidence.get("unaccounted_observations") != 0:
            raise AttestationError(
                "real-engine evidence contains findings or unaccounted observations"
            )
        if not isinstance(run_id, str) or not SHA256.fullmatch(run_id):
            raise AttestationError("real-engine run identity is malformed")
        normalized = {key: int(value) for key, value in observed.items()}
        if counts is not None and normalized != counts:
            raise AttestationError("Full and Release real-engine counts disagree")
        if runtime_identities is not None and identities != runtime_identities:
            raise AttestationError("Full and Release runtime identities disagree")
        counts = normalized
        runtime_identities = identities
        run_ids.add(run_id)
    assert counts is not None and runtime_identities is not None
    audit = _helper_module("adversarial_semantic_audit")
    committed = audit.load_evidence(
        repository_root / "tests/conformance/adversarial/1.0/evidence.json"
    )
    corpus = _git_json(
        repository_root, source_sha, "tests/conformance/adversarial/1.0/corpus.json"
    )
    expected_counts = audit.empirical_counts(committed, corpus)
    if counts != expected_counts or runtime_identities != committed["runtimes"]:
        raise AttestationError(
            "real-engine counts or runtimes differ from governed source evidence"
        )
    required = {
        "semantic_cases",
        "subjects",
        "target_profile_compiles",
        "runtime_executions",
        "governed_refusals",
        "cross_profile_comparisons",
    }
    if not required.issubset(counts):
        raise AttestationError("real-engine evidence omits required counts")
    claim = {key: counts[key] for key in sorted(required)}
    claim["findings"] = 0
    claim["run_ids"] = sorted(run_ids)
    return claim, runtime_identities


def _production_evidence_inputs(release_artifact: Path) -> list[tuple[str, Path]]:
    production = _helper_module("production_certification")
    return [
        (
            "production-release",
            release_artifact.parent / production.PRODUCTION_ARTIFACT_NAME,
        ),
        ("product-release", release_artifact.parent / production.PRODUCT_ARTIFACT_NAME),
        (
            "product-release-report",
            release_artifact.parent / production.PRODUCT_REPORT_NAME,
        ),
    ]


def _execution_evidence_inputs(
    repository_root: Path, full_path: Path, release_path: Path
) -> list[tuple[str, Path]]:
    sources = []
    for profile, path in (("full", full_path), ("release", release_path)):
        artifact = _load_json(path)
        for operation in artifact["deterministic_evidence"]["operations"]:
            integrity = operation.get("execution_integrity")
            if isinstance(integrity, dict):
                invocation = integrity["invocation_id"]
                if not re.fullmatch(r"[0-9a-f]{32}", invocation):
                    raise AttestationError("producer invocation identity is malformed")
                source = (
                    Path(integrity["artifact_directory"])
                    if profile == "full"
                    else release_path.parent / "operation-results" / invocation
                )
                if (
                    profile == "full"
                    and source.resolve()
                    != (
                        repository_root
                        / "target/certification-operation-results"
                        / invocation
                    ).resolve()
                ):
                    raise AttestationError(
                        "Full producer evidence is outside its registered invocation directory"
                    )
                sources.append((f"execution-{profile}", source))
            if operation["operation_id"] == "adversarial_real_engine_equivalence":
                source = (
                    repository_root / "artifacts/adversarial-semantic-runtime"
                    if profile == "full"
                    else release_path.parent / "adversarial-semantic-runtime"
                )
                sources.append((f"real-engine-{profile}", source))
    return sources


def _verify_execution_objects(
    repository_root: Path,
    source_sha: str,
    bundle_dir: Path,
    entries: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
) -> None:
    transport = _helper_module("structured_operation_execution")
    audit = _helper_module("adversarial_semantic_audit")
    corpus = _git_json(
        repository_root, source_sha, "tests/conformance/adversarial/1.0/corpus.json"
    )
    roles = {item["role"] for item in entries}
    for artifact in artifacts:
        profile = artifact["deterministic_evidence"]["profile"]["id"]
        for role in (f"execution-{profile}", f"real-engine-{profile}"):
            if role not in roles:
                raise AttestationError(
                    f"required execution evidence objects are missing: {role}"
                )
        for operation in artifact["deterministic_evidence"]["operations"]:
            integrity = operation.get("execution_integrity")
            if isinstance(integrity, dict):
                directory = bundle_dir / "evidence" / f"execution-{profile}"
                expected_context = {
                    key: integrity[key]
                    for key in (
                        "schema_version",
                        "producer_id",
                        "operation_id",
                        "source_sha",
                        "invocation_id",
                        "certification_profile",
                        "producer_profile",
                    )
                }
                try:
                    raw = transport.validate_result_directory(
                        directory,
                        expected_context=expected_context,
                        result_contract=integrity["result_contract"],
                        actual_exit_code=0,
                    )
                except ValueError as exc:
                    raise AttestationError(
                        f"invalid preserved execution result: {exc}"
                    ) from exc
                reconstructed = {
                    key: value
                    for key, value in integrity.items()
                    if key not in ("artifact_directory", "streams")
                }
                reconstructed.update(
                    structured_result=operation["structured_evidence"],
                    integrity_error=None,
                )
                if raw != reconstructed:
                    raise AttestationError(
                        "preserved atomic result differs from profile evidence"
                    )
                for stream in ("stdout", "stderr"):
                    identity = integrity.get("streams", {}).get(stream)
                    path = directory / f"{stream}.txt"
                    if (
                        not isinstance(identity, dict)
                        or not path.is_file()
                        or identity
                        != {
                            "path": path.name,
                            "sha256": file_sha256(path),
                            "bytes": path.stat().st_size,
                        }
                    ):
                        raise AttestationError(
                            f"preserved execution stream identity mismatch: {stream}"
                        )
            if operation["operation_id"] == "adversarial_real_engine_equivalence":
                path = (
                    bundle_dir / "evidence" / f"real-engine-{profile}" / "evidence.json"
                )
                try:
                    raw = audit.load_evidence(path)
                except (OSError, ValueError, ValidationError) as exc:
                    raise AttestationError(
                        f"invalid preserved real-engine objects: {exc}"
                    ) from exc
                evidence = operation["structured_evidence"]["checks"][0]["evidence"]
                if (
                    raw["result_sha256"]
                    != audit.DIGEST(
                        {
                            key: value
                            for key, value in raw.items()
                            if key != "result_sha256"
                        }
                    )
                    or raw["source_sha"] != source_sha
                    or evidence.get("source_sha") != source_sha
                    or evidence.get("run_id") != raw["run_id"]
                    or raw["corpus_sha256"] != audit.DIGEST(corpus)
                    or raw["run_id"]
                    != audit.DIGEST(
                        {"corpus": audit.DIGEST(corpus), "rows": raw["rows"]}
                    )
                    or audit.empirical_counts(raw, corpus) != evidence["counts"]
                    or raw["runtimes"] != evidence["runtime_identities"]
                    or raw["source_files"] != evidence.get("source_files")
                    or raw["findings"] != []
                ):
                    raise AttestationError(
                        "preserved real-engine evidence differs from certified source/profile"
                    )
                governed = _git_json(
                    repository_root,
                    source_sha,
                    "tests/conformance/adversarial/1.0/evidence.json",
                )
                if set(raw["source_files"]) != set(governed["source_files"]):
                    raise AttestationError(
                        "real-engine source input denominator mismatch"
                    )
                for relative, expected in raw["source_files"].items():
                    if (
                        hashlib.sha256(
                            _git_bytes(repository_root, source_sha, relative)
                        ).hexdigest()
                        != expected
                    ):
                        raise AttestationError(
                            f"real-engine source input hash mismatch: {relative}"
                        )
                target_profiles = {
                    profile_id: _git_json(
                        repository_root,
                        source_sha,
                        audit.shared._profile_path(profile_id)
                        .relative_to(audit.ROOT)
                        .as_posix(),
                    )
                    for profile_id in audit.PROFILES
                }
                try:
                    audit.validate_evidence(
                        raw,
                        corpus,
                        expected_source_identity=raw["source_files"],
                        target_profiles=target_profiles,
                    )
                except (KeyError, ValueError, ValidationError) as exc:
                    raise AttestationError(
                        f"invalid preserved real-engine observations: {exc}"
                    ) from exc


def _verify_production_evidence(
    repository_root: Path,
    trust_root: Path,
    source_sha: str,
    bundle_dir: Path,
    entries: Sequence[Mapping[str, Any]],
    release: Mapping[str, Any],
) -> None:
    production = _helper_module("production_certification")
    paths = {}
    for role in (
        "production-release",
        "product-release",
        "product-release-report",
        "profile-release",
    ):
        matches = [entry for entry in entries if entry["role"] == role]
        if len(matches) != 1:
            raise AttestationError(
                f"required production evidence role is missing or duplicated: {role}"
            )
        paths[role] = bundle_dir / matches[0]["path"]
    receipt = _load_json(paths["production-release"])
    deterministic = receipt.get("deterministic_evidence", {})
    if (
        receipt.get("schema_version") != "1.0.0"
        or receipt.get("artifact_kind") != "strling-production-candidate-certification"
        or receipt.get("evidence_fingerprint") != production.fingerprint(deterministic)
        or deterministic.get("status") != "passed"
        or deterministic.get("profile") != "release"
        or deterministic.get("failure") is not None
        or deterministic.get("publication_authorized") is not False
        or deterministic.get("source", {}).get("sha") != source_sha
        or deterministic.get("source", {}).get("status_porcelain") != ""
    ):
        raise AttestationError(
            "production launcher receipt is not a passing same-source result"
        )
    no_reuse = deterministic.get("no_reuse", {})
    worktree = str(no_reuse.get("clean_detached_worktree", "")).replace("\\", "/")
    if (
        no_reuse.get("honored") is not True
        or no_reuse.get("generated_artifacts_recreated") is not True
        or no_reuse.get("initial_source_status") != "clean"
        or no_reuse.get("final_source_status") != ""
        or no_reuse.get("final_root_status") != ""
        or "/.cert/production-certification/" not in worktree
        or not worktree.endswith("/source")
    ):
        raise AttestationError(
            "production launcher does not prove clean independent no-reuse Release"
        )
    if deterministic.get("aggregate") != production.profile_summary(release):
        raise AttestationError(
            "production launcher aggregate differs from Release evidence"
        )
    invocation = next(
        item["execution_integrity"]["invocation_id"]
        for item in release["deterministic_evidence"]["operations"]
        if item["operation_id"] == "performance_resource_full_certification"
    )
    preserved = []
    for entry in entries:
        role = entry["role"]
        if role not in ("execution-release", "real-engine-release"):
            continue
        suffix = str(PurePosixPath(entry["path"]).relative_to(f"evidence/{role}"))
        prefix = (
            f"operation-results/{invocation}"
            if role == "execution-release"
            else "adversarial-semantic-runtime"
        )
        preserved.append(
            {
                "path": f"{prefix}/{suffix}",
                "sha256": entry["sha256"],
                "size_bytes": entry["bytes"],
            }
        )
    if deterministic.get("environment", {}).get(
        "preserved_execution_evidence"
    ) != sorted(preserved, key=lambda item: item["path"]):
        raise AttestationError(
            "production preserved object inventory differs from bundled Release evidence"
        )
    for subject, role in (
        ("profile", "profile-release"),
        ("product", "product-release"),
        ("product_report", "product-release-report"),
    ):
        if deterministic.get("artifact_identities", {}).get(
            subject
        ) != production.artifact_identity(paths[role]):
            raise AttestationError(
                f"production launcher subject identity mismatch: {subject}"
            )
    product = _load_json(paths["product-release"])
    product_verifier = _helper_module("product_certification")
    _validate_schema(product, trust_root / product_verifier.ARTIFACT_SCHEMA_PATH)
    source_manifest = _git_json(
        repository_root, source_sha, product_verifier.MANIFEST_PATH.as_posix()
    )
    _validate_schema(
        source_manifest, trust_root / product_verifier.MANIFEST_SCHEMA_PATH
    )
    _validate_schema(
        _git_json(
            repository_root,
            source_sha,
            "tests/certification/profile-source/1.0/definitions.json",
        ),
        trust_root / "governance/schemas/profile-source-evidence.schema.json",
    )
    product_evidence = product.get("deterministic_evidence", {})
    if (
        product_evidence.get("source_profile_evidence")
        != release["deterministic_evidence"]
    ):
        raise AttestationError(
            "production product evidence differs from independently verified Release"
        )
    try:
        product_verifier.validate_product_artifact(
            repository_root,
            product,
            manifest=source_manifest,
            toolchain=_git_json(repository_root, source_sha, "toolchain.json"),
            resolved_repository_state={"commit": source_sha, "dirty": False},
        )
    except ValueError as exc:
        raise AttestationError(f"invalid production product evidence: {exc}") from exc
    if deterministic.get("certification") != production.product_summary(product):
        raise AttestationError("production launcher product summary mismatch")
    expected_report = _helper_module("product_certification").render_product_report(
        product
    )
    if paths["product-release-report"].read_text(encoding="utf-8") != expected_report:
        raise AttestationError(
            "production product report differs from verified product evidence"
        )


def _target_profile_claims(
    repository_root: Path, source_sha: str
) -> list[dict[str, str]]:
    paths = _git(
        repository_root,
        "ls-tree",
        "-r",
        "--name-only",
        source_sha,
        "spec/targets/profiles",
    ).splitlines()
    claims: list[dict[str, str]] = []
    for relative in sorted(path for path in paths if path.endswith(".json")):
        profile = _git_json(repository_root, source_sha, relative)
        claims.append(
            {
                "profile_id": str(profile["profile_id"]),
                "profile_version": str(profile["profile_version"]),
                "fingerprint": object_sha256(profile),
            }
        )
    if not claims:
        raise AttestationError("source contains no governed target profiles")
    return claims


def _command_version(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _runner_identity() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "git": _command_version(["git", "--version"]),
        "ssh": _command_version(["ssh", "-V"]),
    }


def _copy_evidence(
    output_dir: Path,
    sources: Sequence[tuple[str, Path]],
) -> list[dict[str, object]]:
    evidence_root = output_dir / "evidence"
    evidence_root.mkdir(parents=True)
    destinations: set[str] = set()
    entries: list[dict[str, object]] = []
    for role, source in sources:
        if not ROLE.fullmatch(role):
            raise AttestationError(f"invalid evidence role: {role}")
        if not source.exists():
            raise AttestationError(f"evidence source does not exist: {source}")
        if source.is_symlink():
            raise AttestationError(f"evidence source is a symbolic link: {source}")
        files = (
            [source]
            if source.is_file()
            else sorted(path for path in source.rglob("*") if path.is_file())
        )
        if not files:
            raise AttestationError(f"evidence source is empty: {source}")
        for path in files:
            if path.is_symlink() or (
                source.is_dir() and not path.resolve().is_relative_to(source.resolve())
            ):
                raise AttestationError(
                    f"evidence source contains an escaping link: {path}"
                )
            suffix = Path(path.name) if source.is_file() else path.relative_to(source)
            relative = (
                PurePosixPath("evidence") / role / PurePosixPath(suffix.as_posix())
            ).as_posix()
            if relative in destinations:
                raise AttestationError(f"duplicate evidence destination: {relative}")
            destinations.add(relative)
            destination = output_dir / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            size = destination.stat().st_size
            if size == 0 and not (
                role in ("execution-full", "execution-release")
                and suffix.as_posix() in ("stdout.txt", "stderr.txt")
            ):
                raise AttestationError(f"evidence file is empty: {relative}")
            entries.append(
                {
                    "path": relative,
                    "role": role,
                    "bytes": size,
                    "sha256": file_sha256(destination),
                }
            )
    return sorted(entries, key=lambda item: str(item["path"]))


def _certifier(trust: Mapping[str, Any], certifier_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in trust["authorized_certifiers"]
        if item["certifier_id"] == certifier_id and item["status"] == "active"
    ]
    if len(matches) != 1:
        raise AttestationError(f"certifier is not uniquely authorized: {certifier_id}")
    if sorted(matches[0]["authorized_profiles"]) != sorted(trust["required_profiles"]):
        raise AttestationError("certifier profile authorization is incomplete")
    return matches[0]


def _private_key_matches(private_key: Path, certifier: Mapping[str, Any]) -> None:
    completed = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(private_key)],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise AttestationError(
            f"cannot read certifier private key: {completed.stderr.strip()}"
        )
    expected = " ".join(str(certifier["public_key"]).split()[:2])
    actual = " ".join(completed.stdout.strip().split()[:2])
    if actual != expected:
        raise AttestationError("private key does not match the trusted certifier")


def _sign(payload: bytes, private_key: Path, namespace: str) -> bytes:
    completed = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode or not completed.stdout:
        raise AttestationError(
            "certification signature failed: "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def _verify_signature(
    payload: bytes,
    signature: bytes,
    certifier: Mapping[str, Any],
    namespace: str,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        allowed = temporary / "allowed_signers"
        signature_path = temporary / "attestation.sig"
        allowed.write_text(
            f"{certifier['certifier_id']} {certifier['public_key']}\n",
            encoding="utf-8",
        )
        signature_path.write_bytes(signature)
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                str(certifier["certifier_id"]),
                "-n",
                namespace,
                "-s",
                str(signature_path),
            ],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode:
        reason = (
            (completed.stderr or completed.stdout)
            .decode("utf-8", errors="replace")
            .strip()
        )
        raise AttestationError(
            f"attestation signature is untrusted or malformed: {reason}"
        )


def _parse_evidence_argument(argument: str) -> tuple[str, Path]:
    if "=" not in argument:
        raise AttestationError("--evidence requires ROLE=PATH")
    role, value = argument.split("=", 1)
    return role, Path(value).resolve()


def create_attestation(
    *,
    repository_root: Path,
    trust_root: Path,
    output_dir: Path,
    full_artifact: Path,
    release_artifact: Path,
    extra_evidence: Sequence[tuple[str, Path]],
    private_key: Path,
    certifier_id: str,
    invocation_id: str,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    trust_root = trust_root.resolve()
    trust = validate_contract(repository_root, trust_root)
    if not re.fullmatch(r"[0-9a-f]{32}", invocation_id):
        raise AttestationError(
            "certification invocation ID must be 32 lowercase hex characters"
        )
    source_sha = _git(repository_root, "rev-parse", "HEAD")
    if not SHA1.fullmatch(source_sha):
        raise AttestationError("repository HEAD is not a full lowercase Git SHA")
    dirty = _git(repository_root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise AttestationError(
            "authoritative local certification requires a clean worktree"
        )
    source_tree = _git(repository_root, "rev-parse", f"{source_sha}^{{tree}}")
    toolchain_bytes = _git_bytes(repository_root, source_sha, "toolchain.json")
    toolchain = json.loads(toolchain_bytes)
    profiles = toolchain["policy"]["profiles"]
    operations = toolchain["policy"]["operation_registry"]
    certifier = _certifier(trust, certifier_id)
    if sorted(certifier["authorized_profiles"]) != sorted(trust["required_profiles"]):
        raise AttestationError("certifier profile authorization is incomplete")
    _private_key_matches(private_key.resolve(), certifier)

    if output_dir.exists():
        raise AttestationError(
            f"attestation output directory already exists: {output_dir}"
        )
    output_dir.mkdir(parents=True)
    try:
        supplied_roles = {role for role, _ in extra_evidence}
        production_inputs = [
            item
            for item in _production_evidence_inputs(release_artifact.resolve())
            if item[0] not in supplied_roles
        ]
        execution_inputs = [
            item
            for item in _execution_evidence_inputs(
                repository_root, full_artifact.resolve(), release_artifact.resolve()
            )
            if item[0] not in supplied_roles
        ]
        copied = _copy_evidence(
            output_dir,
            [
                ("profile-full", full_artifact.resolve()),
                ("profile-release", release_artifact.resolve()),
                *production_inputs,
                *execution_inputs,
                *extra_evidence,
            ],
        )
        full_path = next(
            item["path"] for item in copied if item["role"] == "profile-full"
        )
        release_path = next(
            item["path"] for item in copied if item["role"] == "profile-release"
        )
        full_claim, full = _profile_claim(
            repository_root,
            output_dir / str(full_path),
            "full",
            source_sha,
            toolchain,
            str(full_path),
            trust_root,
        )
        release_claim, release = _profile_claim(
            repository_root,
            output_dir / str(release_path),
            "release",
            source_sha,
            toolchain,
            str(release_path),
            trust_root,
        )
        _verify_production_evidence(
            repository_root, trust_root, source_sha, output_dir, copied, release
        )
        _producer_invocations((full, release))
        _verify_execution_objects(
            repository_root, source_sha, output_dir, copied, (full, release)
        )
        real_engine, runtimes = _real_engine_claim(
            (full, release), repository_root, source_sha
        )
        sample_counts = _sample_counts((full, release))
        _require_authenticated_samples(sample_counts)
        payload: dict[str, Any] = {
            "certification_state": "LOCALLY_CERTIFIED",
            "certified_source": {
                "commit": source_sha,
                "tree": source_tree,
                "clean": True,
            },
            "certification_contract": {
                "toolchain_sha256": hashlib.sha256(toolchain_bytes).hexdigest(),
                "profile_registry_fingerprint": profile_registry_fingerprint(profiles),
                "operation_registry_fingerprint": operation_registry_fingerprint(
                    operations
                ),
                "trust_policy_sha256": object_sha256(trust),
            },
            "certification_invocation_id": invocation_id,
            "certifier": {
                "certifier_id": certifier_id,
                "ssh_key_fingerprint": certifier["ssh_key_fingerprint"],
            },
            "runner_identity": _runner_identity(),
            "component_identities": {
                "kernel_tree": _git(repository_root, "rev-parse", f"{source_sha}:core"),
                "interop_tree": _git(
                    repository_root, "rev-parse", f"{source_sha}:bindings/interop"
                ),
            },
            "target_profiles": _target_profile_claims(repository_root, source_sha),
            "runtime_identities": runtimes,
            "profile_results": [full_claim, release_claim],
            "producer_invocation_ids": _producer_invocations((full, release)),
            "waiver_inventory": _waivers((full, release)),
            "authenticated_sample_counts": sample_counts,
            "real_engine_evidence": real_engine,
            "evidence_files": copied,
        }
        payload["evidence_root_sha256"] = object_sha256(payload)
        signed = canonical_bytes(payload)
        signature = _sign(signed, private_key.resolve(), trust["signature_namespace"])
        attestation = {
            "schema_version": ATTESTATION_VERSION,
            "artifact_kind": ATTESTATION_KIND,
            "signed_payload": payload,
            "signature": {
                "scheme": "SSHSIG_ED25519",
                "namespace": trust["signature_namespace"],
                "certifier_id": certifier_id,
                "signature_base64": base64.b64encode(signature).decode("ascii"),
                "signature_sha256": hashlib.sha256(signature).hexdigest(),
                "signed_payload_sha256": hashlib.sha256(signed).hexdigest(),
            },
        }
        _validate_schema(
            attestation,
            trust_root
            / "governance/schemas/local-certification-attestation.schema.json",
        )
        (output_dir / "attestation.json").write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_attestation(
            repository_root=repository_root,
            trust_root=trust_root,
            bundle_dir=output_dir,
        )
        return attestation
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def _closure_paths(
    repository_root: Path, source_sha: str, trust: Mapping[str, Any]
) -> list[str]:
    head = _git(repository_root, "rev-parse", "HEAD")
    dirty = _git(repository_root, "diff", "--name-only", "HEAD").splitlines()
    if any(
        not any(
            fnmatch.fnmatchcase(path, pattern) for pattern in trust["closure_paths"]
        )
        for path in dirty
    ):
        raise AttestationError(
            "working tree differs from certified source outside closure paths"
        )
    if head == source_sha:
        return []
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_sha, head],
        cwd=repository_root,
        check=False,
    )
    if completed.returncode:
        raise AttestationError(
            "certified source is not an ancestor of the verified source"
        )
    changed = _git(
        repository_root,
        "diff",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        f"{source_sha}..{head}",
    ).splitlines()
    allowed = trust["closure_paths"]
    rejected = [
        path
        for path in changed
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)
    ]
    if rejected:
        raise AttestationError(
            "source advanced beyond the certified commit outside closure paths: "
            + ", ".join(rejected)
        )
    return changed


def _verify_evidence_files(
    bundle_dir: Path, entries: Sequence[Mapping[str, Any]]
) -> None:
    declared = [str(item["path"]) for item in entries]
    if declared != sorted(declared) or len(declared) != len(set(declared)):
        raise AttestationError(
            "evidence file manifest is unordered or contains duplicates"
        )
    actual = sorted(
        path.relative_to(bundle_dir).as_posix()
        for path in (bundle_dir / "evidence").rglob("*")
        if path.is_file()
    )
    if actual != declared:
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        raise AttestationError(
            f"evidence presence mismatch; missing={missing}, extra={extra}"
        )
    for entry in entries:
        path = bundle_dir / str(entry["path"])
        relative = PurePosixPath(str(entry["path"]))
        if (
            relative.parts[:2] != ("evidence", entry["role"])
            or ".." in relative.parts
            or path.is_symlink()
            or not path.resolve().is_relative_to((bundle_dir / "evidence").resolve())
        ):
            raise AttestationError("evidence path escapes its declared role or bundle")
        if entry["bytes"] == 0 and not (
            entry["role"] in ("execution-full", "execution-release")
            and path.name in ("stdout.txt", "stderr.txt")
        ):
            raise AttestationError(
                "only declared execution streams may be empty evidence"
            )
        if path.stat().st_size != entry["bytes"]:
            raise AttestationError(f"evidence size mismatch: {entry['path']}")
        if file_sha256(path) != entry["sha256"]:
            raise AttestationError(f"evidence hash mismatch: {entry['path']}")


def verify_attestation(
    *, repository_root: Path, trust_root: Path, bundle_dir: Path
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    trust_root = trust_root.resolve()
    bundle_dir = bundle_dir.resolve()
    trust = validate_contract(repository_root, trust_root)
    attestation = _load_json(bundle_dir / "attestation.json")
    _validate_schema(
        attestation,
        trust_root / "governance/schemas/local-certification-attestation.schema.json",
    )
    payload = attestation["signed_payload"]
    signature_record = attestation["signature"]
    if signature_record["namespace"] != trust["signature_namespace"]:
        raise AttestationError("signature namespace does not match trust policy")
    if signature_record["certifier_id"] != payload["certifier"]["certifier_id"]:
        raise AttestationError("signature and payload certifier identities disagree")
    certifier = _certifier(trust, signature_record["certifier_id"])
    if payload["certifier"]["ssh_key_fingerprint"] != certifier["ssh_key_fingerprint"]:
        raise AttestationError("payload certifier fingerprint is not trusted")
    signed = canonical_bytes(payload)
    if hashlib.sha256(signed).hexdigest() != signature_record["signed_payload_sha256"]:
        raise AttestationError("signed payload digest mismatch")
    try:
        signature = base64.b64decode(
            signature_record["signature_base64"], validate=True
        )
    except ValueError as exc:
        raise AttestationError("attestation signature encoding is malformed") from exc
    if hashlib.sha256(signature).hexdigest() != signature_record["signature_sha256"]:
        raise AttestationError("signature digest mismatch")
    _verify_signature(signed, signature, certifier, trust["signature_namespace"])
    root_projection = dict(payload)
    root_digest = root_projection.pop("evidence_root_sha256")
    if root_digest != object_sha256(root_projection):
        raise AttestationError("root evidence digest mismatch")
    if payload["certification_state"] != "LOCALLY_CERTIFIED":
        raise AttestationError("terminal certification state is not LOCALLY_CERTIFIED")
    source_sha = payload["certified_source"]["commit"]
    if not SHA1.fullmatch(source_sha):
        raise AttestationError("certified source identity is malformed")
    if _git(repository_root, "rev-parse", f"{source_sha}^{{commit}}") != source_sha:
        raise AttestationError("certified source commit is unavailable")
    if (
        _git(repository_root, "rev-parse", f"{source_sha}^{{tree}}")
        != payload["certified_source"]["tree"]
    ):
        raise AttestationError("certified Git tree identity mismatch")
    if payload["certified_source"]["clean"] is not True:
        raise AttestationError("certified source does not assert a clean worktree")
    closure = _closure_paths(repository_root, source_sha, trust)
    _verify_evidence_files(bundle_dir, payload["evidence_files"])
    evidence_roles = {
        (str(item["role"]), str(item["path"])) for item in payload["evidence_files"]
    }

    toolchain_bytes = _git_bytes(repository_root, source_sha, "toolchain.json")
    toolchain = json.loads(toolchain_bytes)
    profiles = toolchain["policy"]["profiles"]
    operations = toolchain["policy"]["operation_registry"]
    contract = payload["certification_contract"]
    expected_contract = {
        "toolchain_sha256": hashlib.sha256(toolchain_bytes).hexdigest(),
        "profile_registry_fingerprint": profile_registry_fingerprint(profiles),
        "operation_registry_fingerprint": operation_registry_fingerprint(operations),
        "trust_policy_sha256": object_sha256(trust),
    }
    if contract != expected_contract:
        raise AttestationError("certification contract or profile fingerprint mismatch")
    if payload["component_identities"] != {
        "kernel_tree": _git(repository_root, "rev-parse", f"{source_sha}:core"),
        "interop_tree": _git(
            repository_root, "rev-parse", f"{source_sha}:bindings/interop"
        ),
    }:
        raise AttestationError("kernel or interop identity mismatch")
    if payload["target_profiles"] != _target_profile_claims(
        repository_root, source_sha
    ):
        raise AttestationError("target profile identity mismatch")

    results_by_profile = {item["profile"]: item for item in payload["profile_results"]}
    if sorted(results_by_profile) != sorted(trust["required_profiles"]):
        raise AttestationError("required Full/Release profile evidence is missing")
    artifacts: list[dict[str, Any]] = []
    reconstructed: list[dict[str, Any]] = []
    for profile in trust["required_profiles"]:
        claim = results_by_profile[profile]
        required_evidence = (f"profile-{profile}", claim["evidence_path"])
        if required_evidence not in evidence_roles:
            raise AttestationError(
                f"{profile} profile artifact is not declared with its required evidence role"
            )
        rebuilt, artifact = _profile_claim(
            repository_root,
            bundle_dir / claim["evidence_path"],
            profile,
            source_sha,
            toolchain,
            claim["evidence_path"],
            trust_root,
        )
        reconstructed.append(rebuilt)
        artifacts.append(artifact)
    if payload["profile_results"] != reconstructed:
        raise AttestationError("profile result aggregate contradicts producer evidence")
    _producer_invocations(artifacts)
    _verify_execution_objects(
        repository_root, source_sha, bundle_dir, payload["evidence_files"], artifacts
    )
    _verify_production_evidence(
        repository_root,
        trust_root,
        source_sha,
        bundle_dir,
        payload["evidence_files"],
        artifacts[1],
    )
    waivers = _waivers(artifacts)
    if waivers != payload["waiver_inventory"]:
        raise AttestationError("waiver inventory contradicts producer evidence")
    unapproved = sorted(set(waivers) - set(trust["allowed_waivers"]))
    if unapproved:
        raise AttestationError(
            "unapproved waiver in certification evidence: " + ", ".join(unapproved)
        )
    _validate_waiver_scope(repository_root, trust_root, source_sha, artifacts)
    if payload["producer_invocation_ids"] != _producer_invocations(artifacts):
        raise AttestationError("producer invocation identity mismatch")
    reconstructed_samples = _sample_counts(artifacts)
    _require_authenticated_samples(reconstructed_samples)
    if payload["authenticated_sample_counts"] != reconstructed_samples:
        raise AttestationError("authenticated performance sample count mismatch")
    real_engine, runtimes = _real_engine_claim(artifacts, repository_root, source_sha)
    if payload["real_engine_evidence"] != real_engine:
        raise AttestationError("real-engine evidence aggregate mismatch")
    if payload["runtime_identities"] != runtimes:
        raise AttestationError("governed runtime identity mismatch")
    return {
        "certification_state": "CLOUD_VERIFIED",
        "certified_source_sha": source_sha,
        "verified_head_sha": _git(repository_root, "rev-parse", "HEAD"),
        "closure_paths": closure,
        "evidence_root_sha256": root_digest,
        "attestation_sha256": file_sha256(bundle_dir / "attestation.json"),
        "signature_sha256": signature_record["signature_sha256"],
        "certifier_id": certifier["certifier_id"],
        "profile_results": reconstructed,
        "real_engine_evidence": real_engine,
        "authenticated_sample_counts": payload["authenticated_sample_counts"],
        "waiver_inventory": waivers,
    }


def verification_result(
    repository_root: Path, trust_root: Path, bundle_dir: Path
) -> dict[str, object]:
    try:
        evidence = verify_attestation(
            repository_root=repository_root,
            trust_root=trust_root,
            bundle_dir=bundle_dir,
        )
    except AttestationError as exc:
        return _result(
            VERIFY_OPERATION,
            "failed",
            [
                {
                    "check_id": f"{VERIFY_OPERATION}.integrity",
                    "status": "failed",
                    "findings": [
                        {
                            "code": "CERT-LOCAL-ATTESTATION-0002",
                            "message": str(exc),
                        }
                    ],
                }
            ],
        )
    return _result(
        VERIFY_OPERATION,
        "passed",
        [
            {
                "check_id": f"{VERIFY_OPERATION}.integrity",
                "status": "passed",
                "evidence": evidence,
            }
        ],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--trust-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    contract = subparsers.add_parser("contract")
    contract.add_argument("--json", action="store_true")
    attest = subparsers.add_parser("attest")
    attest.add_argument("--full-artifact", type=Path, required=True)
    attest.add_argument("--release-artifact", type=Path, required=True)
    attest.add_argument("--evidence", action="append", default=[])
    attest.add_argument("--private-key", type=Path, required=True)
    attest.add_argument("--certifier-id", required=True)
    attest.add_argument("--invocation-id", default=uuid.uuid4().hex)
    attest.add_argument("--output-dir", type=Path, required=True)
    attest.add_argument("--json", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle", type=Path)
    verify.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repository_root = arguments.repository_root.resolve()
    trust_root = (arguments.trust_root or repository_root).resolve()
    if arguments.command == "contract":
        result = contract_result(repository_root, trust_root)
    elif arguments.command == "attest":
        try:
            attestation = create_attestation(
                repository_root=repository_root,
                trust_root=trust_root,
                output_dir=arguments.output_dir.resolve(),
                full_artifact=arguments.full_artifact,
                release_artifact=arguments.release_artifact,
                extra_evidence=[
                    _parse_evidence_argument(item) for item in arguments.evidence
                ],
                private_key=arguments.private_key,
                certifier_id=arguments.certifier_id,
                invocation_id=arguments.invocation_id,
            )
        except AttestationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        summary = {
            "status": "passed",
            "output_dir": str(arguments.output_dir),
            "certified_source_sha": attestation["signed_payload"]["certified_source"][
                "commit"
            ],
            "evidence_root_sha256": attestation["signed_payload"][
                "evidence_root_sha256"
            ],
            "signature_sha256": attestation["signature"]["signature_sha256"],
        }
        print(
            json.dumps(summary, sort_keys=True)
            if arguments.json
            else json.dumps(summary, indent=2, sort_keys=True)
        )
        return 0
    else:
        trust = load_trust_policy(trust_root)
        bundle = arguments.bundle or repository_root / trust["bundle_path"]
        result = verification_result(repository_root, trust_root, bundle)
    print(
        json.dumps(result, sort_keys=True)
        if arguments.json
        else json.dumps(result, indent=2, sort_keys=True)
    )
    return 0 if result["status"] in SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
