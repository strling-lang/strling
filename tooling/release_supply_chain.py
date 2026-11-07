"""Validate governed STRling release supply-chain certification evidence."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

import yaml
from jsonschema import Draft7Validator, Draft202012Validator, FormatChecker
from jsonschema.exceptions import best_match


ROOT = Path(__file__).resolve().parents[1]
# Isolated script invocations import helpers only from this reviewed checkout.
# The separately supplied artifact/source root is never added to sys.path.
if not __package__:
    sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    sys.modules.setdefault("tooling.release_supply_chain", sys.modules[__name__])
SCHEMA_PATH = ROOT / "governance/schemas/release-supply-chain-certification.schema.json"
MANIFEST_PATH = ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
VALID_FIXTURE_PATH = (
    ROOT / "tests/certification/release-supply-chain/1.0/fixtures/valid-evidence.json"
)
SPDX_SCHEMA_PATH = (
    ROOT / "tests/certification/release-supply-chain/1.0/spdx-2.3.schema.json"
)
SECURITY_POLICY_PATH = ROOT / "governance/security-policy.json"
TOOLCHAIN_PATH = ROOT / "toolchain.json"

ARTIFACT_IDS = [
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
]
OIDC_ARTIFACT_IDS = {
    "release:dart",
    "release:python",
    "release:ruby",
    "release:rust",
    "release:typescript",
}
SOURCE_TAG_ARTIFACT_IDS = {
    "release:c",
    "release:go",
    "release:php",
    "release:r",
    "release:swift",
}
PROFILE_EXPECTATIONS = {
    "local": ("offline", False),
    "pull-request": ("offline", False),
    "full": ("allowed", True),
    "release": ("allowed", True),
}
STATUS_PRECEDENCE = ("failed", "incomplete", "unavailable", "passed")
TOOLCHAIN_PROBES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "R": (("R",), ("--version",)),
    "bundler": (("bundle", "bundler"), ("--version",)),
    "cargo": (("cargo",), ("--version",)),
    "cc": (("cc", "clang", "gcc", "cl"), ("--version",)),
    "cmake": (("cmake",), ("--version",)),
    "composer": (("composer",), ("--version",)),
    "conan": (("conan",), ("--version",)),
    "cxx": (("c++", "clang++", "g++", "cl"), ("--version",)),
    "dart": (("dart",), ("--version",)),
    "dotnet": (("dotnet",), ("--version",)),
    "go": (("go",), ("version",)),
    "gradle": (("gradle",), ("--version",)),
    "java": (("java",), ("-version",)),
    "lua": (("lua",), ("-v",)),
    "luarocks": (("luarocks",), ("--version",)),
    "make": (("make", "gmake"), ("--version",)),
    "maven": (("mvn",), ("--version",)),
    "node": (("node",), ("--version",)),
    "npm": (("npm",), ("--version",)),
    "perl": (("perl",), ("-v",)),
    "php": (("php",), ("--version",)),
    "python": (("python", "python3"), ("--version",)),
    "ruby": (("ruby",), ("--version",)),
    "rustc": (("rustc",), ("--version",)),
    "swift": (("swift",), ("--version",)),
}


class ReleaseSupplyChainError(RuntimeError):
    """A stable fail-closed release supply-chain validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_json(path: Path) -> dict[str, Any]:
    try:
        display_path = path.relative_to(ROOT)
    except ValueError:
        display_path = path
    try:

        def unique_pairs(items):
            document = {}
            for key, value in items:
                if key in document:
                    raise ValueError("duplicate JSON field: " + key)
                document[key] = value
            return document

        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("non-finite JSON value")
            ),
        )
    except (OSError, ValueError) as error:
        raise ReleaseSupplyChainError(
            "malformed-json", f"cannot load {display_path}: {error}"
        ) from error
    if not isinstance(loaded, dict):
        raise ReleaseSupplyChainError(
            "malformed-json", f"{display_path} must contain an object"
        )
    return cast(dict[str, Any], loaded)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def document_fingerprint(
    document: Mapping[str, object], field: str | None = None
) -> str:
    projected = copy.deepcopy(dict(document))
    if field is not None:
        projected.pop(field, None)
    return hashlib.sha256(canonical_json(projected)).hexdigest()


def _schema_validator() -> Draft202012Validator:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_schema(document: Mapping[str, object], *, label: str) -> None:
    error = best_match(_schema_validator().iter_errors(document))
    if error is not None:
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise ReleaseSupplyChainError(
            "schema", f"{label} schema violation at {location}: {error.message}"
        )


def _exact_ids(rows: Sequence[Mapping[str, object]], *, label: str) -> list[str]:
    ids = [row.get("id") for row in rows]
    if any(not isinstance(item, str) for item in ids):
        raise ReleaseSupplyChainError("denominator", f"{label} has a missing id")
    typed = cast(list[str], ids)
    if len(set(typed)) != len(typed):
        raise ReleaseSupplyChainError("denominator", f"{label} ids are duplicated")
    if typed != sorted(typed):
        raise ReleaseSupplyChainError("denominator", f"{label} ids must be sorted")
    return typed


def _artifact_rows(manifest: Mapping[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], manifest["artifacts"])


def artifact_scopes(artifact: Mapping[str, Any]) -> list[str]:
    """Registered build rows; these never promote the public support tier."""
    return list(artifact["build_platforms"])


def scoped_artifact(artifact: Mapping[str, Any], scope: str) -> dict[str, Any]:
    if scope not in artifact_scopes(artifact):
        raise ReleaseSupplyChainError(
            "artifact-scope", "unregistered artifact build scope"
        )
    selected = copy.deepcopy(dict(artifact))
    policy = selected["artifact_policy"]
    if "platform_patterns" in policy:
        policy["patterns"] = policy["platform_patterns"][scope]
        policy["maximum_subjects"] = len(policy["patterns"])
    selected["assembly_scope"] = scope
    return selected


def _toolchain_ids(manifest: Mapping[str, object]) -> list[str]:
    return sorted(
        {
            toolchain
            for artifact in _artifact_rows(manifest)
            for toolchain in cast(list[str], artifact["toolchain_refs"])
        }
    )


def _toolchain_evidence_ids(manifest: Mapping[str, object]) -> list[str]:
    return sorted(
        f"{artifact['id']}:{scope}:{toolchain}"
        for artifact in _artifact_rows(manifest)
        for scope in artifact_scopes(artifact)
        for toolchain in cast(list[str], artifact["toolchain_refs"])
    )


def validate_manifest(
    manifest: Mapping[str, object], *, root: Path = ROOT
) -> dict[str, Any]:
    validate_schema(manifest, label="release supply-chain manifest")
    artifacts = _artifact_rows(manifest)
    if _exact_ids(artifacts, label="release artifact") != ARTIFACT_IDS:
        raise ReleaseSupplyChainError(
            "artifact-denominator", "the exact 17-surface release denominator changed"
        )

    surfaces = [cast(str, artifact["surface"]) for artifact in artifacts]
    compile_jobs = [cast(str, artifact["compile_job"]) for artifact in artifacts]
    publish_jobs = [cast(str, artifact["publish_job"]) for artifact in artifacts]
    for values, label in (
        (surfaces, "surface"),
        (compile_jobs, "compile job"),
        (publish_jobs, "publish job"),
    ):
        if len(set(values)) != len(values):
            raise ReleaseSupplyChainError("artifact-denominator", f"duplicate {label}")

    security_policy = load_json(root / cast(str, manifest["security_policy"]))
    release_policy = load_json(root / "governance/release-policy.json")
    support_claims = {claim["id"]: claim for claim in release_policy["support_claims"]}
    load_json(root / cast(str, manifest["toolchain_authority"]))
    dependency_ids = {
        item["id"]
        for item in cast(list[dict[str, Any]], security_policy["dependency_roots"])
    }
    workflow_path = root / cast(dict[str, Any], manifest["workflow_policy"])["path"]
    try:
        workflow = workflow_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseSupplyChainError(
            "workflow", f"cannot read governed workflow: {error}"
        ) from error

    for artifact in artifacts:
        artifact_id = cast(str, artifact["id"])
        distribution = artifact["distribution_contract"]
        claim = support_claims.get(distribution["support_claim"])
        if (
            claim is None
            or distribution["support_claim"]
            != artifact_id.replace("release:", "binding:")
            or distribution["tier"] != claim["tier"]
            or distribution["scope"] != claim["scope"]
            or distribution["platforms"] != claim.get("platforms")
        ):
            raise ReleaseSupplyChainError(
                "distribution-support", f"{artifact_id} contradicts ratified support"
            )
        if (
            distribution["tier"] != "Supported"
            and distribution["publication_eligibility"]
            != "preview-only-explicit-authorization"
        ):
            raise ReleaseSupplyChainError(
                "distribution-support",
                f"{artifact_id} cannot inherit Supported guarantees",
            )
        expected_builds = distribution["platforms"] or ["linux-x86_64"]
        if artifact_scopes(artifact) != expected_builds:
            raise ReleaseSupplyChainError(
                "artifact-scope", "build rows differ from the registered bounded scope"
            )
        platform_patterns = artifact["artifact_policy"].get("platform_patterns")
        if platform_patterns is not None and (
            set(platform_patterns) != set(expected_builds)
            or any(
                not any(
                    fnmatch.fnmatchcase(pattern, declared)
                    for declared in artifact["artifact_policy"]["patterns"]
                )
                for patterns in platform_patterns.values()
                for pattern in patterns
            )
        ):
            raise ReleaseSupplyChainError(
                "artifact-scope",
                "platform subjects escape the registered artifact patterns",
            )
        package_root = root / cast(str, artifact["package_root"])
        working_directory = root / cast(str, artifact["working_directory"])
        if not package_root.is_dir() or not working_directory.is_dir():
            raise ReleaseSupplyChainError(
                "artifact-path", f"{artifact_id} package or working directory is absent"
            )
        referenced_roots = set(cast(list[str], artifact["dependency_roots"]))
        unknown_roots = sorted(referenced_roots - dependency_ids)
        if unknown_roots:
            raise ReleaseSupplyChainError(
                "dependency-root",
                f"{artifact_id} references unknown dependency roots: {unknown_roots}",
            )
        for job_field in ("compile_job", "publish_job"):
            job = cast(str, artifact[job_field])
            if (
                re.search(rf"^    {re.escape(job)}:\s*$", workflow, re.MULTILINE)
                is None
            ):
                raise ReleaseSupplyChainError(
                    "workflow-job",
                    f"{artifact_id} references absent workflow job {job}",
                )

        delivery_kind = artifact["delivery_kind"]
        artifact_policy = cast(dict[str, Any], artifact["artifact_policy"])
        reproducibility = cast(dict[str, Any], artifact["reproducibility"])
        credential = cast(dict[str, Any], artifact["credential_policy"])
        if artifact_id in SOURCE_TAG_ARTIFACT_IDS:
            expected = ("source-tag", "source-tree", False, "source-identity")
        else:
            expected = (
                "package-archive",
                artifact_policy["subject_kind"],
                True,
                reproducibility["mode"],
            )
        observed = (
            delivery_kind,
            artifact_policy["subject_kind"],
            artifact_policy["checksum_required"],
            reproducibility["mode"],
        )
        if observed != expected:
            raise ReleaseSupplyChainError(
                "artifact-policy", f"{artifact_id} delivery policy is inconsistent"
            )
        if reproducibility["mode"] == "normalized":
            if not reproducibility["allowed_normalizations"]:
                raise ReleaseSupplyChainError(
                    "reproducibility", f"{artifact_id} has an unbounded normalization"
                )
        elif reproducibility["allowed_normalizations"]:
            raise ReleaseSupplyChainError(
                "reproducibility", f"{artifact_id} normalizes an exact identity mode"
            )

        if artifact_id in OIDC_ARTIFACT_IDS:
            if (
                credential["mode"] != "oidc"
                or credential["secret_names"]
                or not credential["trusted_publishing"]
            ):
                raise ReleaseSupplyChainError(
                    "credential-policy", f"{artifact_id} must use secretless OIDC"
                )
        elif credential["mode"] == "long-lived-secret":
            if not credential["secret_names"] or credential["trusted_publishing"]:
                raise ReleaseSupplyChainError(
                    "credential-policy",
                    f"{artifact_id} long-lived credential scope is malformed",
                )
        elif credential["mode"] == "github-token":
            if credential["secret_names"] or credential["trusted_publishing"]:
                raise ReleaseSupplyChainError(
                    "credential-policy",
                    f"{artifact_id} GitHub token scope is malformed",
                )

    profiles = cast(dict[str, dict[str, Any]], manifest["profile_policy"])
    for profile, (network, builds) in PROFILE_EXPECTATIONS.items():
        rule = profiles[profile]
        if (rule["network"], rule["build_artifacts"], rule["publication"]) != (
            network,
            builds,
            False,
        ):
            raise ReleaseSupplyChainError(
                "profile-policy", f"{profile} release supply-chain policy changed"
            )

    workflow_policy = cast(dict[str, Any], manifest["workflow_policy"])
    if sorted(workflow_policy["attestation_permissions"]) != [
        "artifact-metadata: write",
        "attestations: write",
        "id-token: write",
    ]:
        raise ReleaseSupplyChainError(
            "workflow-policy", "the exact attestation permission set changed"
        )
    unknown_probes = sorted(set(_toolchain_ids(manifest)) - set(TOOLCHAIN_PROBES))
    if unknown_probes:
        raise ReleaseSupplyChainError(
            "toolchain-policy", f"toolchain probes are undefined: {unknown_probes}"
        )
    return cast(dict[str, Any], manifest)


def validate_contract_fixture(
    fixture: Mapping[str, object], manifest: Mapping[str, object]
) -> dict[str, Any]:
    validate_schema(fixture, label="release supply-chain contract fixture")
    if fixture["manifest_fingerprint"] != document_fingerprint(manifest):
        raise ReleaseSupplyChainError(
            "stale-manifest", "contract fixture manifest fingerprint changed"
        )
    if fixture["evidence_fingerprint"] != document_fingerprint(
        fixture, "evidence_fingerprint"
    ):
        raise ReleaseSupplyChainError(
            "fixture-fingerprint", "contract fixture fingerprint changed"
        )
    disclaimer = cast(str, fixture["disclaimer"])
    for required in (
        "synthetic",
        "not live artifact evidence",
        "cannot authorize publication",
    ):
        if required not in disclaimer.lower():
            raise ReleaseSupplyChainError(
                "fixture-authority",
                f"contract fixture disclaimer must contain {required!r}",
            )
    return cast(dict[str, Any], fixture)


def _aggregate_status(statuses: Sequence[str]) -> str:
    for status in STATUS_PRECEDENCE:
        if status in statuses:
            return status
    raise ReleaseSupplyChainError("status", "evidence has no artifact statuses")


def validate_evidence(
    evidence: Mapping[str, object],
    manifest: Mapping[str, object],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    validate_schema(evidence, label="release supply-chain evidence")
    validate_manifest(manifest, root=root)
    if evidence["manifest_fingerprint"] != document_fingerprint(manifest):
        raise ReleaseSupplyChainError("stale-manifest", "evidence manifest changed")
    if evidence["evidence_fingerprint"] != document_fingerprint(
        evidence, "evidence_fingerprint"
    ):
        raise ReleaseSupplyChainError("evidence-fingerprint", "evidence changed")

    authority = evidence["evidence_authority"]
    profile = evidence["profile"]
    if (authority, profile) not in {
        ("synthetic-contract", "contract"),
        ("live-dry-run", "full"),
        ("live-dry-run", "release"),
    }:
        raise ReleaseSupplyChainError(
            "evidence-authority",
            "synthetic evidence cannot claim live profile authority",
        )
    workflow = cast(dict[str, Any], evidence["workflow"])
    expected_permissions = sorted(
        cast(dict[str, Any], manifest["workflow_policy"])["attestation_permissions"]
    )
    if workflow["attestation_permissions"] != expected_permissions:
        raise ReleaseSupplyChainError(
            "workflow-permissions", "evidence attestation permissions changed"
        )
    if authority == "live-dry-run":
        workflow_path = root / cast(
            str, cast(dict[str, Any], manifest["workflow_policy"])["path"]
        )
        if workflow["workflow_sha256"] != _sha256_file(workflow_path):
            raise ReleaseSupplyChainError(
                "workflow-fingerprint", "evidence workflow fingerprint changed"
            )

    artifacts = cast(list[dict[str, Any]], evidence["artifacts"])
    if _exact_ids(artifacts, label="release evidence") != ARTIFACT_IDS:
        raise ReleaseSupplyChainError(
            "artifact-denominator", "evidence does not cover all 17 release surfaces"
        )
    contracts = {item["id"]: item for item in _artifact_rows(manifest)}
    source = cast(dict[str, Any], evidence["source"])
    rebuild_source = cast(dict[str, Any], evidence["rebuild_source"])
    if rebuild_source != source:
        raise ReleaseSupplyChainError(
            "source-rebuild", "rebuild source identity differs from primary source"
        )
    if authority == "live-dry-run":
        if source != authenticate_source(root):
            raise ReleaseSupplyChainError(
                "source-rebuild",
                "live evidence is not bound to this clean exact source",
            )
        recorded_tools = _validate_retained_builds(
            root=root,
            manifest=manifest,
            source=source,
            captured=evidence["build_receipts"],
            version=load_json(root / "governance/release-policy.json")["product"][
                "version"
            ],
            verify_subjects=False,
        )
        if recorded_tools != evidence["toolchains"]:
            raise ReleaseSupplyChainError(
                "toolchain-rebuild",
                "retained build environments differ from provenance toolchains",
            )
    elif evidence["build_receipts"]:
        raise ReleaseSupplyChainError(
            "evidence-authority", "synthetic fixture cannot carry live build authority"
        )
    aggregate_statuses: list[str] = []
    artifact_statuses: list[str] = []
    toolchains = cast(list[dict[str, Any]], evidence["toolchains"])
    if _exact_ids(toolchains, label="toolchain evidence") != _toolchain_evidence_ids(
        manifest
    ):
        raise ReleaseSupplyChainError(
            "toolchain-denominator", "evidence toolchain denominator changed"
        )
    toolchain_policy_sha256 = document_fingerprint(
        load_json(root / cast(str, manifest["toolchain_authority"]))
    )
    for toolchain in toolchains:
        expected_id = f"{toolchain['artifact_id']}:{toolchain['scope']}:{toolchain['toolchain_id']}"
        if toolchain["scope"] not in artifact_scopes(
            contracts[toolchain["artifact_id"]]
        ):
            raise ReleaseSupplyChainError(
                "toolchain-denominator", "toolchain has an unregistered build scope"
            )
        if authority == "live-dry-run" and toolchain["status"] == "passed":
            _validate_toolchain_version(
                root,
                toolchain["toolchain_id"],
                toolchain["version"],
                scope=toolchain["scope"],
            )
        if toolchain["id"] != expected_id:
            raise ReleaseSupplyChainError(
                "toolchain-denominator",
                f"{toolchain['id']} toolchain coordinate is inconsistent",
            )
        aggregate_statuses.append(cast(str, toolchain["status"]))
        if toolchain["policy_sha256"] != toolchain_policy_sha256:
            raise ReleaseSupplyChainError(
                "toolchain-policy", f"{toolchain['id']} toolchain policy changed"
            )
        if toolchain["status"] == "passed":
            if (
                toolchain["version"] is None
                or toolchain["executable"] is None
                or toolchain["executable_sha256"] is None
                or toolchain["findings"]
            ):
                raise ReleaseSupplyChainError(
                    "false-pass", f"{toolchain['id']} toolchain passed incompletely"
                )
        elif not toolchain["findings"]:
            raise ReleaseSupplyChainError(
                "missing-finding",
                f"{toolchain['id']} toolchain nonpass lacks a finding",
            )
    for row in artifacts:
        artifact_id = cast(str, row["id"])
        contract = contracts[artifact_id]
        artifact_statuses.append(cast(str, row["status"]))
        aggregate_statuses.append(cast(str, row["status"]))
        subject = cast(dict[str, Any], row["subject"])
        checksum = cast(dict[str, Any], row["checksum"])
        provenance = cast(dict[str, Any], row["provenance"])
        reproducibility = cast(dict[str, Any], row["reproducibility"])
        credential = cast(dict[str, Any], row["credential"])
        contract_artifact = cast(dict[str, Any], contract["artifact_policy"])
        contract_reproducibility = cast(dict[str, Any], contract["reproducibility"])
        contract_credential = cast(dict[str, Any], contract["credential_policy"])

        if subject["kind"] != contract_artifact["subject_kind"]:
            raise ReleaseSupplyChainError(
                "subject-kind", f"{artifact_id} subject kind changed"
            )
        if checksum["digest"] != subject["sha256"]:
            raise ReleaseSupplyChainError(
                "checksum-subject", f"{artifact_id} checksum does not name its subject"
            )
        if (
            provenance["subject_name"] != subject["name"]
            or provenance["subject_sha256"] != subject["sha256"]
            or provenance["source_commit"] != source["commit"]
        ):
            raise ReleaseSupplyChainError(
                "provenance-subject", f"{artifact_id} provenance subject changed"
            )
        if (
            provenance["build_command_sha256"]
            != hashlib.sha256(canonical_json(contract["build_command"])).hexdigest()
        ):
            raise ReleaseSupplyChainError(
                "provenance-command", f"{artifact_id} build command changed"
            )
        if reproducibility["mode"] != contract_reproducibility["mode"]:
            raise ReleaseSupplyChainError(
                "reproducibility", f"{artifact_id} reproducibility mode changed"
            )
        if (
            reproducibility["normalized_fields"]
            != contract_reproducibility["allowed_normalizations"]
        ):
            raise ReleaseSupplyChainError(
                "reproducibility", f"{artifact_id} normalization scope changed"
            )
        if reproducibility["mode"] == "normalized":
            if (
                reproducibility["status"] == "passed"
                and reproducibility["normalized_sha256"] is None
            ):
                raise ReleaseSupplyChainError(
                    "reproducibility", f"{artifact_id} lacks normalized identity"
                )
        elif reproducibility["normalized_sha256"] is not None:
            raise ReleaseSupplyChainError(
                "reproducibility", f"{artifact_id} exact identity was normalized"
            )
        if reproducibility["status"] == "passed" and (
            reproducibility["mode"] != "normalized"
            and (
                reproducibility["first_sha256"] != subject["sha256"]
                or reproducibility["second_sha256"] != subject["sha256"]
            )
        ):
            raise ReleaseSupplyChainError(
                "reproducibility", f"{artifact_id} exact rebuild differs"
            )
        if (
            credential["mode"] != contract_credential["mode"]
            or credential["secret_names"] != contract_credential["secret_names"]
        ):
            raise ReleaseSupplyChainError(
                "credential-policy", f"{artifact_id} credential scope changed"
            )
        expected_issuer = (
            "https://token.actions.githubusercontent.com"
            if credential["mode"] == "oidc"
            else None
        )
        if credential["oidc_issuer"] != expected_issuer:
            raise ReleaseSupplyChainError(
                "credential-policy", f"{artifact_id} OIDC issuer changed"
            )
        if row["status"] == "passed":
            if (
                row["findings"]
                or cast(dict[str, Any], row["sbom"])["unresolved_components"]
                or reproducibility["status"] != "passed"
            ):
                raise ReleaseSupplyChainError(
                    "false-pass", f"{artifact_id} passed with unresolved evidence"
                )
        elif not row["findings"]:
            raise ReleaseSupplyChainError(
                "missing-finding", f"{artifact_id} nonpass lacks a finding"
            )

    summary = cast(dict[str, int], evidence["summary"])
    observed_summary = {
        status: artifact_statuses.count(status) for status in STATUS_PRECEDENCE
    }
    observed_summary["total"] = len(artifact_statuses)
    if summary != observed_summary:
        raise ReleaseSupplyChainError("summary", "artifact summary changed")
    if evidence["status"] != _aggregate_status(aggregate_statuses):
        raise ReleaseSupplyChainError("status", "aggregate status is inconsistent")
    return cast(dict[str, Any], evidence)


def synthetic_evidence(manifest: Mapping[str, object]) -> dict[str, Any]:
    """Build an in-memory no-authority fixture for controlled contract tests."""

    commit = "0" * 40
    toolchain_policy_sha256 = document_fingerprint(
        load_json(ROOT / cast(str, manifest["toolchain_authority"]))
    )
    toolchains = []
    for contract, scope in [
        (row, scope)
        for row in _artifact_rows(manifest)
        for scope in artifact_scopes(row)
    ]:
        artifact_id = cast(str, contract["id"])
        for toolchain_id in cast(list[str], contract["toolchain_refs"]):
            coordinate = f"{artifact_id}:{scope}:{toolchain_id}"
            toolchains.append(
                {
                    "id": coordinate,
                    "artifact_id": artifact_id,
                    "toolchain_id": toolchain_id,
                    "scope": scope,
                    "status": "passed",
                    "version": "fixture",
                    "executable": f"fixture/{coordinate}",
                    "executable_sha256": hashlib.sha256(
                        f"{coordinate}:executable".encode()
                    ).hexdigest(),
                    "runner_os": "Windows" if scope == "windows-x86_64" else "Linux",
                    "runner_arch": "x86_64",
                    "policy_sha256": toolchain_policy_sha256,
                    "findings": [],
                }
            )
    toolchains.sort(key=lambda row: cast(str, row["id"]))
    rows: list[dict[str, Any]] = []
    for contract in _artifact_rows(manifest):
        artifact_id = cast(str, contract["id"])
        digest = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
        sbom_digest = hashlib.sha256(f"{artifact_id}:sbom".encode()).hexdigest()
        predicate_digest = hashlib.sha256(
            f"{artifact_id}:provenance".encode()
        ).hexdigest()
        artifact_policy = cast(dict[str, Any], contract["artifact_policy"])
        reproducibility = cast(dict[str, Any], contract["reproducibility"])
        credential = cast(dict[str, Any], contract["credential_policy"])
        subject_name = f"fixture/{artifact_id.removeprefix('release:')}.artifact"
        rows.append(
            {
                "id": artifact_id,
                "status": "passed",
                "subject": {
                    "name": subject_name,
                    "kind": artifact_policy["subject_kind"],
                    "sha256": digest,
                    "bytes": None
                    if artifact_policy["subject_kind"] == "source-tree"
                    else 1,
                },
                "checksum": {"algorithm": "sha256", "digest": digest},
                "sbom": {
                    "spdx_version": "SPDX-2.3",
                    "document_namespace": (
                        "https://strling.dev/sbom/fixture/"
                        + artifact_id.removeprefix("release:")
                    ),
                    "sha256": sbom_digest,
                    "component_count": 1,
                    "relationship_count": 0,
                    "unresolved_components": 0,
                },
                "provenance": {
                    "statement_type": "https://in-toto.io/Statement/v1",
                    "predicate_type": "https://slsa.dev/provenance/v1",
                    "subject_name": subject_name,
                    "subject_sha256": digest,
                    "source_commit": commit,
                    "builder_id": "https://strling.dev/builders/release-supply-chain-fixture",
                    "build_command_sha256": hashlib.sha256(
                        canonical_json(contract["build_command"])
                    ).hexdigest(),
                    "predicate_sha256": predicate_digest,
                },
                "reproducibility": {
                    "mode": reproducibility["mode"],
                    "status": "passed",
                    "first_sha256": digest,
                    "second_sha256": digest,
                    "normalized_sha256": digest
                    if reproducibility["mode"] == "normalized"
                    else None,
                    "normalized_fields": reproducibility["allowed_normalizations"],
                },
                "credential": {
                    "mode": credential["mode"],
                    "secret_names": credential["secret_names"],
                    "oidc_issuer": "https://token.actions.githubusercontent.com"
                    if credential["mode"] == "oidc"
                    else None,
                    "environment": "release",
                    "untrusted_context_forbidden": True,
                },
                "findings": [],
            }
        )
    evidence: dict[str, Any] = {
        "schema_version": "2.0.0",
        "document_kind": "release-supply-chain-evidence",
        "operation_id": "certification.release-supply-chain",
        "profile": "contract",
        "status": "passed",
        "evidence_authority": "synthetic-contract",
        "publication_authorized": False,
        "manifest_fingerprint": document_fingerprint(manifest),
        "source": {
            "commit": commit,
            "dirty": False,
            "tree_sha256": hashlib.sha256(b"fixture-tree").hexdigest(),
        },
        "rebuild_source": {
            "commit": commit,
            "dirty": False,
            "tree_sha256": hashlib.sha256(b"fixture-tree").hexdigest(),
        },
        "workflow": {
            "workflow_sha256": hashlib.sha256(b"fixture-workflow").hexdigest(),
            "default_read_only": True,
            "protected_environment": "release",
            "untrusted_context_isolated": True,
            "exact_artifact_handoff": True,
            "attestation_permissions": [
                "artifact-metadata: write",
                "attestations: write",
                "id-token: write",
            ],
        },
        "toolchains": toolchains,
        "build_receipts": [],
        "artifacts": rows,
        "summary": {
            "passed": 17,
            "failed": 0,
            "unavailable": 0,
            "incomplete": 0,
            "total": 17,
        },
        "evidence_fingerprint": "0" * 64,
    }
    evidence["evidence_fingerprint"] = document_fingerprint(
        evidence, "evidence_fingerprint"
    )
    return evidence


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=4) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix="." + path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _relative_path(root: Path, path: Path) -> str:
    try:
        return (
            path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
        )
    except (OSError, ValueError) as error:
        raise ReleaseSupplyChainError(
            "artifact-path", f"artifact path escapes the authenticated root: {path}"
        ) from error


def _tree_members(root: Path, directory: Path) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ReleaseSupplyChainError(
                "artifact-symlink", f"artifact tree contains a symlink: {path}"
            )
        if path.is_file():
            members.append(
                {
                    "name": _relative_path(root, path),
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    if not members:
        raise ReleaseSupplyChainError(
            "artifact-empty", f"artifact tree contains no files: {directory}"
        )
    return members


def _source_tree_members(root: Path, directory: Path) -> list[dict[str, object]]:
    """Describe a source delivery from authenticated Git inputs only."""

    if not (root / ".git").exists():
        return _tree_members(root, directory)
    relative_directory = _relative_path(root, directory)
    tracked = _git_output(root, ["ls-files", "-z", "--", relative_directory]).split(
        b"\0"
    )
    members: list[dict[str, object]] = []
    for raw_relative in tracked:
        if not raw_relative:
            continue
        try:
            relative = raw_relative.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReleaseSupplyChainError(
                "artifact-path", "tracked source path is not valid UTF-8"
            ) from error
        path = root / relative
        if _relative_path(root, path) != relative:
            raise ReleaseSupplyChainError(
                "artifact-path", f"tracked source path is not canonical: {relative}"
            )
        if path.is_symlink():
            raise ReleaseSupplyChainError(
                "artifact-symlink", f"source tree contains a symlink: {relative}"
            )
        if not path.is_file():
            raise ReleaseSupplyChainError(
                "artifact-missing", f"tracked source file is absent: {relative}"
            )
        members.append(
            {
                "name": relative,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    if not members:
        raise ReleaseSupplyChainError(
            "artifact-empty", f"source tree contains no tracked files: {directory}"
        )
    return members


def _surface_members(
    root: Path, artifact: Mapping[str, object], version: str
) -> list[dict[str, object]]:
    policy = cast(dict[str, Any], artifact["artifact_policy"])
    paths: dict[str, Path] = {}
    for raw_pattern in cast(list[str], policy["patterns"]):
        pattern = raw_pattern.replace("VERSION", version)
        for path in root.glob(pattern):
            relative = _relative_path(root, path)
            paths[relative] = path
    if not paths:
        raise ReleaseSupplyChainError(
            "artifact-missing", f"{artifact['id']} did not match an artifact"
        )
    if len(paths) > cast(int, policy["maximum_subjects"]):
        raise ReleaseSupplyChainError(
            "artifact-count", f"{artifact['id']} exceeded its maximum subject count"
        )

    members: list[dict[str, object]] = []
    for relative, path in sorted(paths.items()):
        if path.is_symlink():
            raise ReleaseSupplyChainError(
                "artifact-symlink", f"artifact subject is a symlink: {relative}"
            )
        if path.is_dir():
            nested = (
                _source_tree_members(root, path)
                if policy["subject_kind"] == "source-tree"
                else _tree_members(root, path)
            )
            members.append(
                {
                    "name": relative,
                    "sha256": hashlib.sha256(canonical_json(nested)).hexdigest(),
                    "bytes": sum(cast(int, row["bytes"]) for row in nested),
                    "files": nested,
                }
            )
        elif path.is_file():
            members.append(
                {
                    "name": relative,
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
        else:
            raise ReleaseSupplyChainError(
                "artifact-path", f"artifact subject has an unsupported type: {relative}"
            )
    return members


def _member_from_path(
    root: Path, relative: str, *, source_tree: bool = False
) -> dict[str, object]:
    path = root / relative
    authenticated = _relative_path(root, path)
    if authenticated != relative:
        raise ReleaseSupplyChainError(
            "artifact-path", f"artifact path is not canonical: {relative}"
        )
    if path.is_symlink():
        raise ReleaseSupplyChainError(
            "artifact-symlink", f"artifact subject is a symlink: {relative}"
        )
    if path.is_dir():
        nested = (
            _source_tree_members(root, path)
            if source_tree
            else _tree_members(root, path)
        )
        return {
            "name": relative,
            "sha256": hashlib.sha256(canonical_json(nested)).hexdigest(),
            "bytes": sum(cast(int, row["bytes"]) for row in nested),
            "files": nested,
        }
    if path.is_file():
        return {
            "name": relative,
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }
    raise ReleaseSupplyChainError(
        "artifact-missing", f"artifact subject is absent: {relative}"
    )


def _surface_identity(members: Sequence[Mapping[str, object]]) -> tuple[str, str, int]:
    projected = [
        {"name": row["name"], "sha256": row["sha256"], "bytes": row["bytes"]}
        for row in members
    ]
    if len(projected) == 1:
        name = cast(str, projected[0]["name"])
        digest = cast(str, projected[0]["sha256"])
    else:
        name = (
            "strling-release-set:"
            + hashlib.sha256(
                canonical_json([row["name"] for row in projected])
            ).hexdigest()[:16]
        )
        digest = hashlib.sha256(canonical_json(projected)).hexdigest()
    return name, digest, sum(cast(int, row["bytes"]) for row in projected)


def _git_output(root: Path, arguments: Sequence[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ReleaseSupplyChainError(
            "source-authentication", f"cannot authenticate Git source: {error}"
        ) from error
    return completed.stdout


def authenticate_source(root: Path) -> dict[str, object]:
    commit = _git_output(root, ["rev-parse", "HEAD"]).decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ReleaseSupplyChainError("source-authentication", "Git HEAD is not exact")
    dirty = _git_output(root, ["status", "--porcelain", "--untracked-files=all"])
    if dirty:
        raise ReleaseSupplyChainError(
            "source-dirty", "release evidence requires a clean source tree"
        )
    submodules = _git_output(root, ["submodule", "status", "--recursive"])
    if submodules:
        raise ReleaseSupplyChainError(
            "source-submodule", "release evidence forbids unauthenticated submodules"
        )
    tracked = _git_output(root, ["ls-files", "-s", "-z"])
    return {
        "commit": commit,
        "dirty": False,
        "tree_sha256": hashlib.sha256(tracked).hexdigest(),
    }


def _permission_set(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {
        f"{key}: {permission}"
        for key, permission in value.items()
        if isinstance(key, str) and isinstance(permission, str)
    }


def _workflow_artifact_name(artifact: Mapping[str, object]) -> str:
    slug = re.sub(
        r"[^a-z0-9]+", "-", cast(str, artifact["id"]).removeprefix("release:")
    ).strip("-")
    return f"certified-{slug}-${{{{ needs.verify-release.outputs.release_ref }}}}"


def _workflow_rebuild_name(artifact: Mapping[str, object]) -> str:
    slug = re.sub(
        r"[^a-z0-9]+", "-", cast(str, artifact["id"]).removeprefix("release:")
    ).strip("-")
    return f"rebuild-{slug}-${{{{ needs.verify-release.outputs.release_ref }}}}"


def _workflow_receipt_name(artifact: Mapping[str, object]) -> str:
    slug = re.sub(
        r"[^a-z0-9]+", "-", cast(str, artifact["id"]).removeprefix("release:")
    ).strip("-")
    return (
        f"release-build-receipt-{slug}-"
        "${{ needs.verify-release.outputs.release_ref }}"
    )


def qualify_workflow(root: Path, manifest: Mapping[str, object]) -> dict[str, object]:
    policy = cast(dict[str, Any], manifest["workflow_policy"])
    path = root / cast(str, policy["path"])
    try:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ReleaseSupplyChainError(
            "workflow", f"cannot parse the governed release workflow: {error}"
        ) from error
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        raise ReleaseSupplyChainError("workflow", "release workflow has no job map")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])
    if any(not isinstance(job, dict) for job in jobs.values()):
        raise ReleaseSupplyChainError(
            "workflow", "malformed workflow job configuration"
        )
    if "secrets." in yaml.safe_dump(workflow.get("env", {})):
        raise ReleaseSupplyChainError(
            "workflow-credentials", "global publication credentials are forbidden"
        )
    publish_jobs = {item["publish_job"] for item in _artifact_rows(manifest)}
    for job_name, job in jobs.items():
        if job_name in publish_jobs or job_name == "attest-release-subjects":
            continue
        permissions = job.get("permissions", {"contents": "read"})
        if (
            not isinstance(permissions, dict)
            or any(value not in {"read", "none"} for value in permissions.values())
            or job.get("environment") == "release"
            or "secrets." in yaml.safe_dump(job)
        ):
            raise ReleaseSupplyChainError(
                "workflow-credentials",
                "build or verification job can receive publication credentials",
            )
    triggers = workflow.get("on", workflow.get(True))
    if not isinstance(triggers, dict) or any(
        event in triggers for event in ("pull_request", "pull_request_target")
    ):
        raise ReleaseSupplyChainError(
            "workflow-trigger", "release workflow is callable from untrusted code"
        )
    dispatch = triggers.get("workflow_dispatch")
    if (
        not isinstance(dispatch, dict)
        or dispatch.get("inputs", {}).get("dry_run", {}).get("default") is not True
    ):
        raise ReleaseSupplyChainError(
            "workflow-authorization",
            "dry-run must be the explicit safe dispatch default",
        )
    if workflow.get("permissions") != {"contents": "read"}:
        raise ReleaseSupplyChainError(
            "workflow-permissions",
            "release workflow default permissions are not read-only",
        )

    certify = jobs.get("certify-release-supply-chain")
    required_permissions = set(cast(list[str], policy["attestation_permissions"]))
    if not isinstance(certify, dict):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "release workflow lacks the common certification job",
        )
    if certify.get("environment") is not None or _permission_set(
        certify.get("permissions")
    ) != {"contents: read"}:
        raise ReleaseSupplyChainError(
            "workflow-credentials",
            "artifact build verification must not receive protected publication authority",
        )
    attester = jobs.get("attest-release-subjects")
    if (
        not isinstance(attester, dict)
        or attester.get("environment") != "release-attestation"
    ):
        raise ReleaseSupplyChainError(
            "workflow-attestation", "an isolated attestation environment is required"
        )
    if _permission_set(attester.get("permissions")) != required_permissions | {
        "contents: read",
        "actions: read",
    }:
        raise ReleaseSupplyChainError(
            "workflow-permissions",
            "isolated attestation job lacks attestation permissions",
        )
    certify_needs = certify.get("needs", [])
    if isinstance(certify_needs, str):
        certify_needs = [certify_needs]
    required_needs = {
        "verify-release",
        *[cast(str, artifact["compile_job"]) for artifact in _artifact_rows(manifest)],
    }
    if not isinstance(certify_needs, list) or set(certify_needs) != required_needs:
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "certification job does not consume the exact compile denominator",
        )
    certify_steps = cast(list[dict[str, Any]], certify.get("steps", []))
    attester_steps = attester.get("steps", [])
    if not any(
        "actions/attest@" in str(step.get("uses", "")) for step in attester_steps
    ):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "attestation must use an immutable attestation action",
        )
    attester_commands = [step["run"] for step in attester_steps if "run" in step]
    if (
        len(attester_commands) != 2
        or attester_commands[0]
        != "python -m pip install jsonschema==4.10.3 PyYAML==6.0.1"
        or not attester_commands[1].startswith(
            "python -I .cert/publisher/tooling/release_supply_chain.py certified-checksums "
        )
    ):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "attestation may execute only pinned runtime setup and isolated signed-subject verification",
        )
    if set(attester.get("needs", [])) != {"verify-release", "release-certification"}:
        raise ReleaseSupplyChainError(
            "workflow-rebuild",
            "remote attestation cannot replace signed primary subjects with cloud rebuilds",
        )
    certify_commands = "\n".join(
        str(step.get("run", "")) for step in certify_steps if "run" in step
    )
    for required_command in (
        "release_supply_chain security",
        "release_supply_chain produce",
        "release_supply_chain verify",
    ):
        if required_command not in certify_commands:
            raise ReleaseSupplyChainError(
                "workflow-certification",
                f"certification job lacks {required_command}",
            )
    release_certification = jobs.get("release-certification")
    if not isinstance(release_certification, dict):
        raise ReleaseSupplyChainError(
            "workflow-certification", "release profile certification job is absent"
        )
    if release_certification.get("needs") not in (None, []):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "canonical release certification must precede release preflight",
        )
    release_commands = "\n".join(
        str(step.get("run", ""))
        for step in cast(list[dict[str, Any]], release_certification.get("steps", []))
        if "run" in step
    )
    if (
        "local_certification_attestation.py" not in release_commands
        or "--trust-root trusted" not in release_commands
    ):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "release job must use isolated trusted verification of signed local evidence",
        )
    verify_release = jobs.get("verify-release")
    if not isinstance(verify_release, dict) or verify_release.get("needs") != (
        "release-certification"
    ):
        raise ReleaseSupplyChainError(
            "workflow-certification",
            "release preflight does not depend on canonical release certification",
        )

    for artifact in _artifact_rows(manifest):
        compile_job = cast(str, artifact["compile_job"])
        publish_job = cast(str, artifact["publish_job"])
        compile_config = jobs.get(compile_job)
        publish_config = jobs.get(publish_job)
        if not isinstance(compile_config, dict) or not isinstance(publish_config, dict):
            raise ReleaseSupplyChainError(
                "workflow-job", f"release workflow lacks {compile_job} or {publish_job}"
            )
        environment = publish_config.get("environment")
        environment_name = (
            environment.get("name") if isinstance(environment, dict) else environment
        )
        if environment_name != policy["protected_environment"]:
            raise ReleaseSupplyChainError(
                "workflow-environment",
                f"{publish_job} is outside the release environment",
            )
        condition = str(publish_config.get("if", ""))
        if not all(
            term in condition
            for term in (
                "is_dry_run == 'false'",
                "RELEASE_PUBLICATION_ENABLED",
                "RELEASE_APPROVED_WORKFLOW_SHA",
                "RELEASE_AUTHORIZED_RUN_ID",
                "RELEASE_AUTHORIZED_RUN_ATTEMPT",
            )
        ):
            raise ReleaseSupplyChainError(
                "workflow-credentials",
                f"{publish_job} can receive publication authority during dry-run",
            )
        needs = publish_config.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        expected_publish_needs = {"verify-release", "release-certification"}
        companion_publish = {
            "release:fsharp": "publish-csharp",
            "release:kotlin": "publish-java",
        }.get(artifact["id"])
        if companion_publish:
            expected_publish_needs.add(companion_publish)
        if set(needs) != expected_publish_needs:
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "publication must consume previously certified assets independently of dry-run builds",
            )
        compile_steps = cast(list[dict[str, Any]], compile_config.get("steps", []))
        publish_steps = cast(list[dict[str, Any]], publish_config.get("steps", []))
        matrix = compile_config.get("strategy", {}).get("matrix", {}).get("include")
        expected_matrix = [
            {
                "scope": scope,
                "runner": "windows-2022"
                if scope == "windows-x86_64"
                else "ubuntu-24.04",
            }
            for scope in artifact_scopes(artifact)
        ]
        if (
            matrix != expected_matrix
            or compile_config.get("runs-on") != "${{ matrix.runner }}"
        ):
            raise ReleaseSupplyChainError(
                "workflow-scope",
                "build matrix differs from the exact registered platform denominator",
            )
        if (
            compile_config.get("if")
            != "needs.verify-release.outputs.is_dry_run == 'true'"
        ):
            raise ReleaseSupplyChainError(
                "workflow-rebuild",
                "publication execution must not create replacement artifacts",
            )
        slug = artifact["id"].removeprefix("release:")
        suffix = "${{ matrix.scope }}-${{ needs.verify-release.outputs.release_ref }}"
        uploads = [
            step["with"]
            for step in compile_steps
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        expected_uploads = {}
        for label, prefix in (("first", "release"), ("second", "rebuild")):
            expected_uploads[f"{prefix}-{slug}-{suffix}"] = (
                f".cert/uploads/{slug}-${{{{ matrix.scope }}}}-{label}",
                True,
            )
        expected_uploads[f"release-build-receipt-{slug}-{suffix}"] = (
            "\n".join(
                f"artifacts/build-receipts/{slug}-${{{{ matrix.scope }}}}-{label}.json"
                for label in ("first", "second")
            ),
            False,
        )
        if len(uploads) != 3 or {row.get("name") for row in uploads} != set(
            expected_uploads
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff", "artifact upload denominator changed"
            )
        for row in uploads:
            upload_path, hidden = expected_uploads[row["name"]]
            if (
                row.get("path") != upload_path
                or row.get("if-no-files-found") != "error"
                or (hidden and row.get("include-hidden-files") is not True)
            ):
                raise ReleaseSupplyChainError(
                    "workflow-handoff",
                    "upload is not the exact staged graph, including hidden package files",
                )
        build_commands = "\n".join(str(step.get("run", "")) for step in compile_steps)
        assembly = [
            (step.get("working-directory"), step.get("run"))
            for step in compile_steps
            if step.get("name")
            in {"Assemble first clean source", "Assemble second clean source"}
        ]
        if assembly != [
            (".", " ".join(artifact["build_command"])),
            (".rebuild", " ".join(artifact["build_command"])),
        ]:
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "workflow assembly differs from the receipt's governed build command",
            )
        if (
            "release_supply_chain prepare-upload" not in build_commands
            or "release_supply_chain capture" not in build_commands
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff", "build lacks authenticated graph staging"
            )
        companion = {
            "release:fsharp": "compile-csharp",
            "release:kotlin": "compile-java",
        }.get(artifact["id"])
        if companion and (
            companion not in compile_config.get("needs", [])
            or "release_supply_chain restore-upload" not in build_commands
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "companion was not restored from the primary certified build",
            )
        downloads = [
            step.get("with", {})
            for step in publish_steps
            if str(step.get("uses", "")).startswith("actions/download-artifact@")
        ]
        package = [
            row
            for row in downloads
            if row.get("name") == _workflow_artifact_name(artifact)
        ]
        if (
            len(package) != 1
            or package[0].get("path") != ".cert/downloads/" + slug
            or not any(
                str(row.get("name", "")).startswith("signed-release-")
                for row in downloads
            )
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "publication must download the separately retained certified package and signed root",
            )
        if any(
            row.get("repository") != "strling-lang/strling"
            or row.get("run-id")
            != "${{ inputs.certified_run_id || vars.RELEASE_CERTIFIED_RUN_ID }}"
            for row in downloads
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "certified asset transport is not bound to its authorized repository and run",
            )
        if "RELEASE_AUTHORIZED_DESTINATIONS" not in condition:
            raise ReleaseSupplyChainError(
                "workflow-authorization",
                "unselected destination can receive publication authority",
            )
        publish_commands = "\n".join(str(step.get("run", "")) for step in publish_steps)
        if "release_supply_chain.py handoff" not in publish_commands:
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "publication lacks immediate trusted artifact verification",
            )
        allowed_secrets = set(artifact["credential_policy"]["secret_names"])
        used_secrets = set(
            re.findall(r"secrets\.([A-Za-z0-9_]+)", yaml.safe_dump(publish_config))
        )
        if used_secrets - allowed_secrets:
            raise ReleaseSupplyChainError(
                "workflow-credentials",
                "publication references an unregistered persistent credential",
            )
        if not any(
            step.get("with", {}).get("ref")
            == "${{ vars.RELEASE_APPROVED_WORKFLOW_SHA }}"
            and step.get("with", {}).get("path") == ".cert/publisher"
            and step.get("with", {}).get("persist-credentials") is False
            for step in publish_steps
        ):
            raise ReleaseSupplyChainError(
                "workflow-candidate-execution",
                "publisher code is not isolated at the approved immutable source",
            )
        if re.search(
            r"\b(?:npm (?:ci|run build|pack)|cargo publish|dotnet pack|gem build|make dist|mvn (?:deploy|package)|gradlew)\b",
            publish_commands,
        ):
            raise ReleaseSupplyChainError(
                "workflow-rebuild", "publication must not rebuild certified payloads"
            )
        for step in publish_steps:
            if "run" in step and "working-directory" in step:
                raise ReleaseSupplyChainError(
                    "workflow-candidate-execution",
                    "publication may not execute candidate working-directory scripts",
                )

    workflow_text = path.read_text(encoding="utf-8")
    for action in re.findall(r"\buses:\s*([^\s#]+)", workflow_text):
        if "@" in action and re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) is None:
            raise ReleaseSupplyChainError(
                "workflow-action", f"workflow action is not immutable: {action}"
            )
    return {
        "workflow_sha256": _sha256_file(path),
        "default_read_only": True,
        "protected_environment": "release",
        "untrusted_context_isolated": True,
        "exact_artifact_handoff": True,
        "attestation_permissions": sorted(required_permissions),
    }


def probe_toolchains(
    root: Path, manifest: Mapping[str, object]
) -> list[dict[str, object]]:
    policy_sha256 = document_fingerprint(
        load_json(root / cast(str, manifest["toolchain_authority"]))
    )
    rows: list[dict[str, object]] = []
    for artifact in _artifact_rows(manifest):
        artifact_id = cast(str, artifact["id"])
        for scope in artifact_scopes(artifact):
            for toolchain_id in cast(list[str], artifact["toolchain_refs"]):
                rows.append(
                    _probe_toolchain(
                        root,
                        artifact_id=artifact_id,
                        toolchain_id=toolchain_id,
                        policy_sha256=policy_sha256,
                        scope=scope,
                    )
                )
    return sorted(rows, key=lambda row: cast(str, row["id"]))


def _validate_toolchain_version(
    root: Path, toolchain_id: str, banner: str, *, scope: str | None = None
) -> None:
    """Enforce the same version authority as profiles, plus release constraints.

    Transitional developer runtimes are never admitted to release receipts.
    Native families come from their registered Conan profiles; Gradle comes
    from the checksummed wrapper rather than a second version constant.
    """
    from tooling.quality import version_satisfies

    windows = scope == "windows-x86_64" if scope is not None else os.name == "nt"
    if toolchain_id in {"cc", "cxx"}:
        profile = (
            root
            / "bindings/cpp/profiles"
            / ("windows-x86_64" if windows else "linux-x86_64")
        )
        text = profile.read_text(encoding="utf-8")
        family = re.search(r"(?m)^compiler.version=(\d+)$", text)
        if family is None:
            raise ValueError("missing release compiler family")
        if windows:
            update = re.search(r"(?m)^compiler.update=(\d+)$", text)
            if (
                update is None
                or re.search(
                    r"Compiler Version 19\." + family[1][-1] + update[1] + r"\.", banner
                )
                is None
            ):
                raise ValueError("native compiler differs from the release profile")
        else:
            match = re.search(r"(\d+)(?:\.\d+){1,2}", banner)
            if match is None or match[1] != family[1]:
                raise ValueError("native compiler differs from the release profile")
        return
    if toolchain_id == "gradle":
        wrapper = (
            root / "bindings/kotlin/gradle/wrapper/gradle-wrapper.properties"
        ).read_text(encoding="utf-8")
        expected = re.search(r"gradle-(\d+(?:\.\d+){1,2})-bin\.zip", wrapper)
        actual = re.search(r"Gradle (\d+(?:\.\d+){1,2})", banner)
        if expected is None or actual is None or actual[1] != expected[1]:
            raise ValueError("Gradle differs from the repository wrapper")
        return
    alias = {"python": "python3", "maven": "mvn", "bundler": "bundle"}.get(
        toolchain_id, toolchain_id
    )
    tool = load_json(root / "toolchain.json")["tools"][alias]
    match = re.search(tool["version_pattern"], banner, re.IGNORECASE)
    if match is None:
        raise ValueError("tool banner does not match its governed version pattern")
    actual = match[1]
    resolution = tool["resolution"]
    constraint = resolution.get("version")
    if resolution["model"] == "repository_managed":
        content = (root / resolution["file"]).read_text(encoding="utf-8")
        governed = re.search(resolution["file_pattern"], content)
        if governed is None:
            raise ValueError("repository-managed tool version cannot be resolved")
        constraint = governed[1]
    if constraint is not None and not version_satisfies(actual, constraint):
        raise ValueError("tool version violates its declared constraint")
    release_constraint = tool.get("release_constraint")
    if resolution["model"] == "deferred" and release_constraint is None:
        raise ValueError("release tool has no governed version constraint")
    if release_constraint is not None and not version_satisfies(
        actual, release_constraint
    ):
        raise ValueError("tool version violates its release constraint")


def _probe_toolchain(
    root: Path,
    *,
    artifact_id: str,
    toolchain_id: str,
    policy_sha256: str,
    scope: str | None = None,
) -> dict[str, object]:
    candidates, version_args = TOOLCHAIN_PROBES[toolchain_id]
    expected_cl_version = None
    host = {"Windows": "windows-x86_64", "Linux": "linux-x86_64"}.get(platform.system())
    scope = scope or host
    coordinate = f"{artifact_id}:{scope}:{toolchain_id}"
    runner = {
        "scope": scope,
        "runner_os": platform.system(),
        "runner_arch": platform.machine(),
    }
    if scope != host or platform.machine().lower() not in {"amd64", "x86_64"}:
        return {
            "id": coordinate,
            "artifact_id": artifact_id,
            "toolchain_id": toolchain_id,
            "status": "unavailable",
            "version": None,
            "executable": None,
            "executable_sha256": None,
            **runner,
            "policy_sha256": policy_sha256,
            "findings": [
                {
                    "code": "SUPPLY-TOOLCHAIN-UNAVAILABLE",
                    "message": "this host cannot certify the requested build scope",
                }
            ],
        }
    repository_candidates: list[Path] = []
    if artifact_id == "release:kotlin" and toolchain_id == "gradle":
        repository_candidates.append(
            root / "bindings/kotlin" / ("gradlew.bat" if os.name == "nt" else "gradlew")
        )
    executable = next(
        (str(path) for path in repository_candidates if path.is_file()),
        None,
    ) or next((shutil.which(name) for name in candidates if shutil.which(name)), None)
    if toolchain_id == "python":
        executable = sys.executable
    if toolchain_id in {"cc", "cxx"}:
        if os.name != "nt":
            executable = shutil.which("gcc-13" if toolchain_id == "cc" else "g++-13")
        else:
            vswhere = (
                Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
                / "Microsoft Visual Studio/Installer/vswhere.exe"
            )
            try:
                profile = (root / "bindings/cpp/profiles/windows-x86_64").read_text(
                    encoding="utf-8"
                )
                compiler = re.search(r"(?m)^compiler.version=(\d+)$", profile)
                update = re.search(r"(?m)^compiler.update=(\d+)$", profile)
                if compiler is None or update is None:
                    raise ValueError("an exact native compiler family is required")
                prefix = "14." + compiler[1][-1] + update[1]
                expected_cl_version = "19." + compiler[1][-1] + update[1]
                located = subprocess.run(
                    [
                        str(vswhere),
                        "-latest",
                        "-products",
                        "*",
                        "-property",
                        "installationPath",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=20,
                ).stdout.strip()
                tools = sorted(
                    (Path(located) / "VC/Tools/MSVC").glob(
                        prefix + ".*/bin/Hostx64/x64/cl.exe"
                    )
                )
                executable = str(tools[-1]) if tools else None
                version_args = ()
            except (OSError, ValueError, subprocess.SubprocessError):
                executable = None
    if executable is not None and toolchain_id in {"cargo", "rustc"}:
        rustup = shutil.which("rustup") or str(
            Path(executable).parent / ("rustup.exe" if os.name == "nt" else "rustup")
        )
        try:
            resolved = subprocess.run(
                [rustup, "which", "--toolchain", "1.75.0", toolchain_id],
                cwd=root,
                env=_canonical_subprocess_environment(),
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            executable = resolved.stdout.strip()
            if not Path(executable).is_file():
                executable = None
        except (OSError, subprocess.SubprocessError):
            executable = None
    if executable is None:
        return {
            "id": coordinate,
            "artifact_id": artifact_id,
            "toolchain_id": toolchain_id,
            "status": "unavailable",
            "version": None,
            "executable": None,
            "executable_sha256": None,
            **runner,
            "policy_sha256": policy_sha256,
            "findings": [
                {
                    "code": "SUPPLY-TOOLCHAIN-UNAVAILABLE",
                    "message": f"{coordinate} executable is unavailable",
                }
            ],
        }
    executable_path = Path(executable).resolve()
    executable_identity = (
        "repository:" + executable_path.relative_to(root.resolve()).as_posix()
        if executable_path.is_relative_to(root.resolve())
        and executable_path in [path.resolve() for path in repository_candidates]
        else executable_path.as_posix()
    )
    try:
        completed = subprocess.run(
            [executable, *version_args],
            cwd=root,
            env=_canonical_subprocess_environment(),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        version = " ".join(completed.stdout.split())
        cl_banner = (
            os.name == "nt"
            and toolchain_id in {"cc", "cxx"}
            and expected_cl_version is not None
            and re.search(
                r"Compiler Version " + re.escape(expected_cl_version) + r"\.", version
            )
        )
        if completed.returncode and not (completed.returncode == 2 and cl_banner):
            raise ValueError("governed tool version probe failed")
        if not version:
            raise ValueError("empty version output")
        _validate_toolchain_version(root, toolchain_id, version, scope=scope)
        return {
            "id": coordinate,
            "artifact_id": artifact_id,
            "toolchain_id": toolchain_id,
            "status": "passed",
            "version": version,
            "executable": executable_identity,
            "executable_sha256": _sha256_file(Path(executable)),
            **runner,
            "policy_sha256": policy_sha256,
            "findings": [],
        }
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
    ) as error:
        return {
            "id": coordinate,
            "artifact_id": artifact_id,
            "toolchain_id": toolchain_id,
            "status": "incomplete",
            "version": None,
            "executable": executable_identity,
            "executable_sha256": _sha256_file(Path(executable)),
            **runner,
            "policy_sha256": policy_sha256,
            "findings": [
                {
                    "code": "SUPPLY-TOOLCHAIN-VERSION",
                    "message": f"{coordinate} version probe failed: {error}",
                }
            ],
        }


def _canonical_subprocess_environment() -> dict[str, str] | None:
    """Remove case-duplicate PATH keys that native Windows tools reject."""

    if os.name != "nt":
        return None
    environment = {
        key: value for key, value in os.environ.items() if key.casefold() != "path"
    }
    path_values = [
        value for key, value in os.environ.items() if key.casefold() == "path"
    ]
    environment["Path"] = os.pathsep.join(dict.fromkeys(path_values))
    return environment


def capture_build_receipt(
    *,
    root: Path,
    artifact_id: str,
    version: str,
    output_path: Path,
    manifest: Mapping[str, object],
) -> dict[str, Any]:
    """Capture the exact output and environment of one completed dry-run build."""

    if output_path.exists():
        raise ReleaseSupplyChainError(
            "output-exists", "build receipt output must not already exist"
        )
    validate_manifest(manifest, root=root)
    if (
        version
        != load_json(root / "governance/release-policy.json")["product"]["version"]
    ):
        raise ReleaseSupplyChainError(
            "product-version", "build version differs from canonical product authority"
        )
    contracts = {cast(str, row["id"]): row for row in _artifact_rows(manifest)}
    if artifact_id not in contracts:
        raise ReleaseSupplyChainError(
            "artifact-denominator", f"unknown release artifact: {artifact_id}"
        )
    artifact = contracts[artifact_id]
    from tooling.release_packaging import host_scope

    scope = host_scope()
    artifact = scoped_artifact(artifact, scope)
    source = authenticate_source(root)
    members = _surface_members(root, artifact, version)
    inspect_release_payload(root, artifact, version, members)
    subject_name, subject_sha256, subject_bytes = _surface_identity(members)
    policy_sha256 = document_fingerprint(
        load_json(root / cast(str, manifest["toolchain_authority"]))
    )
    toolchains = [
        _probe_toolchain(
            root,
            artifact_id=artifact_id,
            toolchain_id=toolchain_id,
            policy_sha256=policy_sha256,
            scope=scope,
        )
        for toolchain_id in cast(list[str], artifact["toolchain_refs"])
    ]
    toolchains.sort(key=lambda row: cast(str, row["id"]))
    reproducibility = cast(dict[str, Any], artifact["reproducibility"])
    consumer = None
    if artifact["distribution_contract"]["tier"] == "Supported":
        from tooling.release_consumers import verify_consumer

        native = (
            root
            / "bindings/interop/target/release"
            / (
                "strling_interop.dll"
                if scope == "windows-x86_64"
                else "libstrling_interop.so"
            )
        )
        consumer = verify_consumer(artifact_id, root=root, native=native)
    normalized_sha256 = (
        _normalized_surface_sha256(
            root,
            members,
            cast(list[str], reproducibility["allowed_normalizations"]),
        )
        if reproducibility["mode"] == "normalized"
        else None
    )
    receipt: dict[str, Any] = {
        "schema_version": "2.0.0",
        "document_kind": "release-build-receipt",
        "operation_id": "certification.release-build-capture",
        "artifact_id": artifact_id,
        "product_version": version,
        "scope": scope,
        "build_instance_id": uuid.uuid4().hex,
        "build_root_sha256": hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
        "source": source,
        "build_command_sha256": hashlib.sha256(
            canonical_json(artifact["build_command"])
        ).hexdigest(),
        "subject": {
            "name": subject_name,
            "sha256": subject_sha256,
            "bytes": subject_bytes,
            "members": members,
            "normalized_sha256": normalized_sha256,
        },
        "toolchains": toolchains,
        "consumer": consumer,
        "publication_authorized": False,
        "receipt_fingerprint": "0" * 64,
    }
    receipt["receipt_fingerprint"] = document_fingerprint(
        receipt, "receipt_fingerprint"
    )
    _validate_build_receipt(
        receipt,
        root=root,
        artifact=artifact,
        version=version,
        manifest=manifest,
        require_passed_toolchains=True,
    )
    _write_json(output_path, receipt)
    return receipt


def _validate_build_receipt(
    receipt: Mapping[str, object],
    *,
    root: Path,
    artifact: Mapping[str, object],
    version: str,
    manifest: Mapping[str, object],
    require_passed_toolchains: bool,
    expected_source: Mapping[str, object] | None = None,
    verify_subjects: bool = True,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "document_kind",
        "operation_id",
        "artifact_id",
        "product_version",
        "scope",
        "build_instance_id",
        "build_root_sha256",
        "source",
        "build_command_sha256",
        "subject",
        "toolchains",
        "consumer",
        "publication_authorized",
        "receipt_fingerprint",
    }
    artifact_id = cast(str, artifact["id"])
    artifact = scoped_artifact(artifact, cast(str, receipt.get("scope")))
    if (
        re.fullmatch(r"[0-9a-f]{32}", str(receipt.get("build_instance_id", ""))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("build_root_sha256", "")))
        is None
    ):
        raise ReleaseSupplyChainError(
            "build-receipt", "independent build identity is absent"
        )
    if set(receipt) != required:
        raise ReleaseSupplyChainError(
            "build-receipt", f"{artifact_id} build receipt fields changed"
        )
    if (
        receipt["schema_version"] != "2.0.0"
        or receipt["document_kind"] != "release-build-receipt"
        or receipt["operation_id"] != "certification.release-build-capture"
        or receipt["artifact_id"] != artifact_id
        or receipt["product_version"] != version
        or receipt["publication_authorized"] is not False
    ):
        raise ReleaseSupplyChainError(
            "build-receipt", f"{artifact_id} build receipt authority changed"
        )
    if receipt["receipt_fingerprint"] != document_fingerprint(
        receipt, "receipt_fingerprint"
    ):
        raise ReleaseSupplyChainError(
            "build-receipt", f"{artifact_id} build receipt changed"
        )
    if receipt["source"] != (
        dict(expected_source)
        if expected_source is not None
        else authenticate_source(root)
    ):
        raise ReleaseSupplyChainError(
            "source-rebuild", f"{artifact_id} build receipt source changed"
        )
    if (
        receipt["build_command_sha256"]
        != hashlib.sha256(canonical_json(artifact["build_command"])).hexdigest()
    ):
        raise ReleaseSupplyChainError(
            "provenance-command", f"{artifact_id} build receipt command changed"
        )
    subject = receipt["subject"]
    if not isinstance(subject, dict):
        raise ReleaseSupplyChainError("build-receipt", "build subject is malformed")
    observed_members = (
        _surface_members(root, artifact, version)
        if verify_subjects
        else _receipt_members(subject, artifact, version)
    )
    observed_name, observed_sha256, observed_bytes = _surface_identity(observed_members)
    reproducibility = cast(dict[str, Any], artifact["reproducibility"])
    if not isinstance(subject, dict) or subject != {
        "name": observed_name,
        "sha256": observed_sha256,
        "bytes": observed_bytes,
        "members": observed_members,
        "normalized_sha256": (
            (
                _normalized_surface_sha256(
                    root,
                    observed_members,
                    cast(list[str], reproducibility["allowed_normalizations"]),
                )
                if verify_subjects
                else subject["normalized_sha256"]
            )
            if reproducibility["mode"] == "normalized"
            else None
        ),
    }:
        raise ReleaseSupplyChainError(
            "build-receipt", f"{artifact_id} build receipt subject changed"
        )
    toolchains = receipt["toolchains"]
    if not isinstance(toolchains, list) or _exact_ids(
        cast(list[Mapping[str, object]], toolchains), label="build receipt toolchain"
    ) != sorted(
        f"{artifact_id}:{receipt['scope']}:{toolchain}"
        for toolchain in cast(list[str], artifact["toolchain_refs"])
    ):
        raise ReleaseSupplyChainError(
            "toolchain-denominator", f"{artifact_id} build receipt toolchains changed"
        )
    for row in toolchains:
        if (
            row.get("scope") != receipt["scope"]
            or row.get("artifact_id") != artifact_id
        ):
            raise ReleaseSupplyChainError(
                "toolchain-denominator", "build receipt toolchain scope changed"
            )
        if row.get("status") == "passed":
            expected_os = "Windows" if receipt["scope"] == "windows-x86_64" else "Linux"
            if row.get("runner_os") != expected_os or str(
                row.get("runner_arch")
            ).lower() not in {"amd64", "x86_64"}:
                raise ReleaseSupplyChainError(
                    "toolchain-scope", "toolchain did not run on its claimed platform"
                )
            _validate_toolchain_version(
                root, row["toolchain_id"], row["version"], scope=receipt["scope"]
            )
    consumer = receipt["consumer"]
    if artifact["distribution_contract"]["tier"] == "Supported":
        from tooling.release_consumers import CONSUMER_FIXTURES

        expected_fixtures = {
            relative: _sha256_file(root / relative)
            for relative in CONSUMER_FIXTURES.values()
        }
        if not isinstance(consumer, dict) or (
            consumer.get("schema_version") != "2.0.0"
            or consumer.get("document_kind") != "release-consumer-receipt"
            or consumer.get("artifact_id") != artifact_id
            or consumer.get("product_version") != version
            or consumer.get("scope") != receipt["scope"]
            or consumer.get("source") != receipt["source"]
            or consumer.get("engineering") is not False
            or consumer.get("publication_authorized") is not False
            or consumer.get("subject_sha256") != observed_sha256
            or consumer.get("manifest_fingerprint") != document_fingerprint(manifest)
            or consumer.get("fixture_sha256") != expected_fixtures
            or consumer.get("receipt_fingerprint")
            != document_fingerprint(consumer, "receipt_fingerprint")
        ):
            raise ReleaseSupplyChainError(
                "consumer-receipt",
                "Supported build has no exact-source isolated consumer proof",
            )
        result = consumer.get("result", {})
        if not isinstance(result, dict):
            raise ReleaseSupplyChainError(
                "consumer-receipt", "consumer result is malformed"
            )
        compatibility = (
            result.get("linked_package_version") == version
            and result.get("target_profile_mismatch_rejected") is True
            if artifact_id == "release:rust"
            else result.get("kernel_mismatch_rejected") is True
        )
        if (
            result.get("status") != "passed"
            or result.get("source_outcome") != "succeeded"
            or result.get("target_pattern") != "abc"
            or not compatibility
        ):
            raise ReleaseSupplyChainError(
                "consumer-receipt",
                "Supported consumer did not prove canonical success and compatibility refusal",
            )
    elif consumer is not None:
        raise ReleaseSupplyChainError(
            "consumer-receipt", "Preview build cannot claim a Supported consumer proof"
        )
    if require_passed_toolchains and any(
        row.get("status") != "passed"
        for row in cast(list[Mapping[str, object]], toolchains)
    ):
        raise ReleaseSupplyChainError(
            "toolchain-unavailable", f"{artifact_id} build toolchain is not qualified"
        )
    return cast(dict[str, Any], receipt)


def _receipt_members(
    subject: Mapping[str, Any], artifact: Mapping[str, Any], version: str
) -> list[dict]:
    """Validate retained rebuild metadata without executing candidate inputs."""
    members = subject.get("members")
    if (
        not isinstance(members, list)
        or not members
        or len(members) > artifact["artifact_policy"]["maximum_subjects"]
    ):
        raise ReleaseSupplyChainError(
            "build-receipt", "invalid retained rebuild member set"
        )
    names = []
    for member in members:
        if not isinstance(member, dict) or set(member) not in (
            {"name", "sha256", "bytes"},
            {"name", "sha256", "bytes", "files"},
        ):
            raise ReleaseSupplyChainError(
                "build-receipt", "invalid retained rebuild member"
            )
        name = member["name"]
        if not isinstance(name, str) or not any(
            fnmatch.fnmatchcase(name, pattern.replace("VERSION", version))
            for pattern in artifact["artifact_policy"]["patterns"]
        ):
            raise ReleaseSupplyChainError(
                "build-receipt", "retained rebuild member escapes its registered scope"
            )
        if (
            type(member["bytes"]) is not int
            or member["bytes"] < 0
            or re.fullmatch(r"[0-9a-f]{64}", str(member["sha256"])) is None
        ):
            raise ReleaseSupplyChainError(
                "build-receipt", "invalid retained member digest or size"
            )
        nested = member.get("files", [member])
        if not isinstance(nested, list) or not nested:
            raise ReleaseSupplyChainError(
                "build-receipt", "empty retained source member"
            )
        file_names = []
        for row in nested:
            path = row.get("name") if isinstance(row, dict) else None
            if (
                not isinstance(path, str)
                or "\\" in path
                or ":" in path
                or "\0" in path
                or Path(path).is_absolute()
                or any(part in {"", ".", ".."} for part in path.split("/"))
                or ("files" in member and not path.startswith(name + "/"))
                or ("files" in member and set(row) != {"name", "sha256", "bytes"})
                or re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))) is None
                or type(row.get("bytes")) is not int
                or row["bytes"] < 0
            ):
                raise ReleaseSupplyChainError(
                    "build-receipt", "unsafe retained source file identity"
                )
            file_names.append(path)
        if file_names != sorted(set(file_names)):
            raise ReleaseSupplyChainError(
                "build-receipt", "duplicate or unordered retained source files"
            )
        if "files" in member and (
            hashlib.sha256(canonical_json(nested)).hexdigest() != member["sha256"]
            or sum(row["bytes"] for row in nested) != member["bytes"]
        ):
            raise ReleaseSupplyChainError(
                "build-receipt", "retained source member digest differs"
            )
        names.append(name)
    if names != sorted(set(names)):
        raise ReleaseSupplyChainError(
            "build-receipt", "duplicate or unordered retained members"
        )
    normalized = subject.get("normalized_sha256")
    if (
        artifact["reproducibility"]["mode"] == "normalized"
        and re.fullmatch(r"[0-9a-f]{64}", str(normalized)) is None
    ):
        raise ReleaseSupplyChainError(
            "build-receipt", "missing retained normalization identity"
        )
    return members


def load_build_receipts(
    *,
    receipt_dir: Path,
    root: Path,
    second_root: Path,
    manifest: Mapping[str, object],
    version: str,
) -> tuple[
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
    list[dict[str, object]],
]:
    """Require two authenticated builds for every one of the 21 build rows."""
    if root.resolve() == second_root.resolve():
        raise ReleaseSupplyChainError(
            "source-rebuild", "independent builds require separate source workspaces"
        )
    expected_files = {
        f"{artifact['id'].removeprefix('release:')}-{scope}-{label}.json"
        for artifact in _artifact_rows(manifest)
        for scope in artifact_scopes(artifact)
        for label in ("first", "second")
    }
    observed_files = set()
    for path in receipt_dir.rglob("*"):
        if path.is_symlink():
            raise ReleaseSupplyChainError("build-receipt", "symlink in receipt set")
        if path.is_file():
            observed_files.add(path.relative_to(receipt_dir).as_posix())
    if observed_files != expected_files:
        raise ReleaseSupplyChainError(
            "build-receipt", "missing or unregistered platform build receipts"
        )
    toolchains, captured = [], []
    sources = {}
    for artifact in _artifact_rows(manifest):
        artifact_id = cast(str, artifact["id"])
        slug = artifact_id.removeprefix("release:")
        for scope in artifact_scopes(artifact):
            pair = {}
            for label, subject_root in (("first", root), ("second", second_root)):
                receipt = _validate_build_receipt(
                    load_json(receipt_dir / f"{slug}-{scope}-{label}.json"),
                    root=subject_root,
                    artifact=artifact,
                    version=version,
                    manifest=manifest,
                    require_passed_toolchains=True,
                )
                if receipt["scope"] != scope:
                    raise ReleaseSupplyChainError(
                        "build-receipt", "platform receipt is assigned to the wrong row"
                    )
                pair[label] = receipt
                if label in sources and sources[label] != receipt["source"]:
                    raise ReleaseSupplyChainError(
                        "source-rebuild",
                        "platform builds do not share one exact source",
                    )
                sources[label] = receipt["source"]
                captured.append({"label": label, "receipt": receipt})
            if pair["first"]["toolchains"] != pair["second"]["toolchains"]:
                raise ReleaseSupplyChainError(
                    "toolchain-rebuild",
                    "platform rebuild toolchain fingerprint changed",
                )
            if any(
                pair["first"][field] == pair["second"][field]
                for field in ("build_instance_id", "build_root_sha256")
            ):
                raise ReleaseSupplyChainError(
                    "source-rebuild",
                    "rebuild reused the primary invocation or workspace",
                )
            policy = artifact["reproducibility"]
            first_subject, second_subject = (
                pair["first"]["subject"],
                pair["second"]["subject"],
            )
            key = "normalized_sha256" if policy["mode"] == "normalized" else "sha256"
            if first_subject[key] is None or first_subject[key] != second_subject[key]:
                raise ReleaseSupplyChainError(
                    "reproducibility", "independent platform artifacts differ"
                )
            toolchains.extend(pair["first"]["toolchains"])
    if sources.get("first") != sources.get("second") or not captured:
        raise ReleaseSupplyChainError(
            "source-rebuild", "independent source identities differ"
        )
    by_coordinate = {
        (row["receipt"]["artifact_id"], row["receipt"]["scope"], row["label"]): row[
            "receipt"
        ]
        for row in captured
    }
    for row in captured:
        receipt = row["receipt"]
        companion = {
            "release:fsharp": "release:csharp",
            "release:kotlin": "release:java",
        }.get(receipt["artifact_id"])
        if companion is not None:
            expected = by_coordinate[(companion, receipt["scope"], row["label"])][
                "subject"
            ]["sha256"]
            if (
                receipt["consumer"]["result"].get("companion_subject_sha256")
                != expected
            ):
                raise ReleaseSupplyChainError(
                    "consumer-companion",
                    "consumer used an unpublished or substituted companion",
                )
    return (
        sorted(toolchains, key=lambda row: row["id"]),
        sources["first"],
        sources["second"],
        sorted(
            captured,
            key=lambda row: (
                row["receipt"]["artifact_id"],
                row["receipt"]["scope"],
                row["label"],
            ),
        ),
    )


def _validate_retained_builds(
    *,
    root: Path,
    manifest: Mapping[str, object],
    source: Mapping[str, object],
    captured: Sequence[Mapping[str, Any]],
    version: str,
    verify_subjects: bool,
) -> list[dict]:
    contracts = {row["id"]: row for row in _artifact_rows(manifest)}
    expected = sorted(
        (row["id"], scope, label)
        for row in _artifact_rows(manifest)
        for scope in artifact_scopes(row)
        for label in ("first", "second")
    )
    coordinates, receipts = [], {}
    for entry in captured:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"label", "receipt"}
            or not isinstance(entry["receipt"], dict)
        ):
            raise ReleaseSupplyChainError(
                "build-receipt", "retained build record is malformed"
            )
        receipt = entry["receipt"]
        coordinate = (receipt.get("artifact_id"), receipt.get("scope"), entry["label"])
        if coordinate not in expected or coordinate in receipts:
            raise ReleaseSupplyChainError(
                "build-receipt", "unregistered or duplicate retained build row"
            )
        _validate_build_receipt(
            receipt,
            root=root,
            artifact=contracts[coordinate[0]],
            version=version,
            manifest=manifest,
            require_passed_toolchains=True,
            expected_source=source,
            verify_subjects=verify_subjects and entry["label"] == "first",
        )
        coordinates.append(coordinate)
        receipts[coordinate] = receipt
    if coordinates != expected:
        raise ReleaseSupplyChainError(
            "build-receipt",
            "every platform requires two ordered build and consumer records",
        )
    toolchains = []
    for artifact in _artifact_rows(manifest):
        artifact_id = artifact["id"]
        for scope in artifact_scopes(artifact):
            first, second = (
                receipts[(artifact_id, scope, label)] for label in ("first", "second")
            )
            if first["toolchains"] != second["toolchains"]:
                raise ReleaseSupplyChainError(
                    "toolchain-rebuild",
                    "retained independent toolchain identities differ",
                )
            if any(
                first[field] == second[field]
                for field in ("build_instance_id", "build_root_sha256")
            ):
                raise ReleaseSupplyChainError(
                    "source-rebuild",
                    "retained rebuild reused its primary workspace or invocation",
                )

            def shape(receipt):
                return [
                    (row["name"], "files" in row)
                    for row in receipt["subject"]["members"]
                ]

            key = (
                "normalized_sha256"
                if artifact["reproducibility"]["mode"] == "normalized"
                else "sha256"
            )
            if (
                shape(first) != shape(second)
                or first["subject"][key] is None
                or first["subject"][key] != second["subject"][key]
            ):
                raise ReleaseSupplyChainError(
                    "reproducibility", "retained independent build subjects differ"
                )
            toolchains.extend(first["toolchains"])
            companion = {
                "release:fsharp": "release:csharp",
                "release:kotlin": "release:java",
            }.get(artifact_id)
            if companion is not None:
                for label, receipt in (("first", first), ("second", second)):
                    expected_companion = receipts[(companion, scope, label)]["subject"][
                        "sha256"
                    ]
                    if (
                        receipt["consumer"]["result"].get("companion_subject_sha256")
                        != expected_companion
                    ):
                        raise ReleaseSupplyChainError(
                            "consumer-companion",
                            "retained consumer used a different companion",
                        )
    return sorted(toolchains, key=lambda row: row["id"])


def _upload_members(members: Sequence[Mapping[str, Any]]) -> tuple[Path, list[dict]]:
    concrete = [
        dict(row) for member in members for row in member.get("files", [member])
    ]
    names = [row.get("name") for row in concrete]
    if (
        not names
        or any(
            not isinstance(name, str)
            or "\\" in name
            or ":" in name
            or "\0" in name
            or Path(name).is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))
            for name in names
        )
        or len(names) != len(set(names))
    ):
        raise ReleaseSupplyChainError(
            "artifact-path", "upload contains unsafe or duplicate member paths"
        )
    if len(members) == 1 and "files" in members[0]:
        base = Path(members[0]["name"])
    else:
        base = Path(os.path.commonpath([str(Path(name).parent) for name in names]))
    return base, concrete


def prepare_artifact_upload(
    *, root: Path, receipt_path: Path, output: Path, manifest: Mapping[str, object]
) -> dict:
    """Serialize only the authenticated file graph into workflow transport."""
    if output.exists():
        raise ReleaseSupplyChainError(
            "output-exists", "upload staging directory already exists"
        )
    receipt = load_json(receipt_path)
    artifact = next(
        (
            row
            for row in _artifact_rows(manifest)
            if row["id"] == receipt.get("artifact_id")
        ),
        None,
    )
    if artifact is None:
        raise ReleaseSupplyChainError("build-receipt", "unknown upload artifact")
    version = load_json(root / "governance/release-policy.json")["product"]["version"]
    _validate_build_receipt(
        receipt,
        root=root,
        artifact=artifact,
        version=version,
        manifest=manifest,
        require_passed_toolchains=True,
    )
    base, concrete = _upload_members(receipt["subject"]["members"])
    planned = []
    for row in concrete:
        source = root / row["name"]
        target = output / Path(row["name"]).relative_to(base)
        if (
            source.is_symlink()
            or not source.resolve().is_relative_to(root.resolve())
            or not target.resolve().is_relative_to(output.resolve())
            or _sha256_file(source) != row["sha256"]
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff",
                "upload staging bytes differ from their captured subject",
            )
        planned.append((source, target))
    for source, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return {
        "status": "passed",
        "artifact_id": artifact["id"],
        "scope": receipt["scope"],
        "staged_files": len(planned),
        "publication_authorized": False,
    }


def prepare_certified_upload(
    *,
    root: Path,
    evidence_path: Path,
    output: Path,
    artifact_id: str,
    manifest: Mapping[str, object],
) -> dict:
    """Export verified primary bytes for a future immutable owner-approved handoff.

    This creates local transport only. It neither uploads an Actions artifact nor
    grants publication authority; the publisher revalidates the signed root.
    """
    if output.exists():
        raise ReleaseSupplyChainError(
            "output-exists", "certified transport directory already exists"
        )
    evidence = verify_bundle(root=root, evidence_path=evidence_path, manifest=manifest)
    if (
        evidence["evidence_authority"] != "live-dry-run"
        or evidence["profile"] != "release"
        or evidence["status"] != "passed"
    ):
        raise ReleaseSupplyChainError(
            "publication-evidence",
            "only passing exact-source Release subjects can be exported",
        )
    contract = next(
        (row for row in _artifact_rows(manifest) if row["id"] == artifact_id), None
    )
    if contract is None:
        raise ReleaseSupplyChainError(
            "artifact-denominator", "unknown certified transport"
        )
    version = load_json(root / "governance/release-policy.json")["product"]["version"]
    members = _surface_members(root, contract, version)
    base, concrete = _upload_members(members)
    for row in concrete:
        source = root / row["name"]
        target = output / Path(row["name"]).relative_to(base)
        if (
            source.is_symlink()
            or not source.resolve().is_relative_to(root.resolve())
            or not target.resolve().is_relative_to(output.resolve())
            or _sha256_file(source) != row["sha256"]
        ):
            raise ReleaseSupplyChainError(
                "publication-substitution", "certified bytes changed during export"
            )
    for row in concrete:
        target = output / Path(row["name"]).relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / row["name"], target)
    return {
        "status": "passed",
        "artifact_id": artifact_id,
        "artifact_name": "certified-"
        + artifact_id.removeprefix("release:")
        + "-"
        + evidence["source"]["commit"],
        "subject_sha256": _surface_identity(members)[1],
        "staged_files": len(concrete),
        "publication_authorized": False,
    }


def restore_artifact_upload(
    *, artifact_root: Path, target_root: Path, receipt: Mapping[str, Any]
) -> int:
    base, concrete = _upload_members(receipt["subject"]["members"])
    expected = {Path(row["name"]).relative_to(base).as_posix() for row in concrete}
    observed = set()
    for path in artifact_root.rglob("*"):
        if path.is_symlink():
            raise ReleaseSupplyChainError(
                "workflow-handoff", "symlink in downloaded artifact"
            )
        if path.is_file():
            observed.add(path.relative_to(artifact_root).as_posix())
    if observed != expected:
        raise ReleaseSupplyChainError(
            "workflow-handoff", "download has missing or unregistered files"
        )
    planned = []
    for row in concrete:
        source = artifact_root / Path(row["name"]).relative_to(base)
        destination = target_root / row["name"]
        if (
            source.is_symlink()
            or destination.is_symlink()
            or not source.resolve().is_relative_to(artifact_root.resolve())
            or not destination.resolve().is_relative_to(target_root.resolve())
            or _sha256_file(source) != row["sha256"]
        ):
            raise ReleaseSupplyChainError(
                "workflow-handoff", "downloaded subject changed or escaped its root"
            )
        if destination.exists():
            if not destination.is_file() or _sha256_file(destination) != row["sha256"]:
                raise ReleaseSupplyChainError(
                    "workflow-handoff",
                    "platforms supplied conflicting bytes for one subject path",
                )
        else:
            planned.append((source, destination))
    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return len(concrete)


def stage_downloaded_artifacts(
    *,
    download_root: Path,
    receipt_dir: Path,
    first_root: Path,
    second_root: Path,
    release_ref: str,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Restore every exact scope into independent primary/rebuild source trees."""
    if (
        re.fullmatch(r"[0-9a-f]{40}", release_ref) is None
        or first_root.resolve() == second_root.resolve()
    ):
        raise ReleaseSupplyChainError(
            "source-rebuild", "staging requires an exact source and separate workspaces"
        )
    staged = 0
    for artifact in _artifact_rows(manifest):
        slug = artifact["id"].removeprefix("release:")
        for scope in artifact_scopes(artifact):
            for label, target, prefix in (
                ("first", first_root, "release"),
                ("second", second_root, "rebuild"),
            ):
                receipt = load_json(receipt_dir / f"{slug}-{scope}-{label}.json")
                if (
                    receipt.get("artifact_id") != artifact["id"]
                    or receipt.get("scope") != scope
                    or receipt.get("source", {}).get("commit") != release_ref
                ):
                    raise ReleaseSupplyChainError(
                        "build-receipt",
                        "download receipt has the wrong source or scope",
                    )
                staged += restore_artifact_upload(
                    artifact_root=download_root
                    / f"{prefix}-{slug}-{scope}-{release_ref}",
                    target_root=target,
                    receipt=receipt,
                )
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.release-artifact-stage",
        "profile": "release",
        "status": "passed",
        "publication_authorized": False,
        "staged_files": staged,
    }


def _normalized_conan_sha256(path: Path) -> str:
    """Normalize only Conan cache aliases and its recorded creation timestamps.

    Package/recipe revisions, settings, native bytes, modes, source content,
    dependencies, and manifest file digests remain exact comparison inputs.
    """
    from tooling.release_payload import archive_files

    try:
        bounded_files = archive_files(path)
    except (OSError, ValueError, tarfile.TarError) as error:
        raise ReleaseSupplyChainError(
            "reproducibility", "unsafe or unbounded Conan cache"
        ) from error
    with tarfile.open(path, "r:*") as archive:
        names = [entry.name for entry in archive.getmembers()]
        if len(names) != len(set(names)) or any(
            Path(name).is_absolute() or ".." in Path(name).parts for name in names
        ):
            raise ReleaseSupplyChainError(
                "reproducibility", "unsafe Conan cache members"
            )
        pkglist_file = archive.extractfile("pkglist.json")
        if pkglist_file is None:
            raise ReleaseSupplyChainError(
                "reproducibility", "Conan cache has no package list"
            )
        pkglist = json.loads(pkglist_file.read())
        aliases: dict[str, str] = {}
        for ref, recipe in pkglist.items():
            for revision, record in recipe["revisions"].items():
                base = ref + "/" + revision
                aliases[record["recipe_folder"]] = "recipe/" + base
                record["recipe_folder"] = "recipe/" + base
                record.pop("timestamp", None)
                for package_id, package in record.get("packages", {}).items():
                    for package_revision, binary in package["revisions"].items():
                        package_base = (
                            "package/"
                            + base
                            + "/"
                            + package_id
                            + "/"
                            + package_revision
                        )
                        for key in ("package_folder", "metadata_folder"):
                            if key in binary:
                                normalized = package_base + (
                                    "/metadata"
                                    if key == "metadata_folder"
                                    else "/payload"
                                )
                                aliases[binary[key]] = normalized
                                binary[key] = normalized
                        binary.pop("timestamp", None)
        rows = []
        for entry in archive.getmembers():
            if entry.isdir():
                continue
            if not entry.isfile():
                raise ReleaseSupplyChainError(
                    "reproducibility", "Conan cache contains a non-regular payload"
                )
            data_file = archive.extractfile(entry)
            assert data_file is not None
            data = bounded_files[entry.name]
            if entry.name == "pkglist.json":
                name, data = entry.name, canonical_json(pkglist)
            else:
                alias = next(
                    (
                        prefix
                        for prefix in sorted(aliases, key=len, reverse=True)
                        if entry.name.startswith(prefix + "/")
                    ),
                    None,
                )
                if alias is None:
                    raise ReleaseSupplyChainError(
                        "reproducibility", "unregistered Conan cache layout member"
                    )
                name = aliases[alias] + entry.name[len(alias) :]
                if entry.name.endswith("/conanmanifest.txt"):
                    first, separator, rest = data.partition(b"\n")
                    if (
                        not separator
                        or re.fullmatch(rb"[0-9]+(?:\.[0-9]+)?", first) is None
                    ):
                        raise ReleaseSupplyChainError(
                            "reproducibility",
                            "unknown Conan manifest timestamp encoding",
                        )
                    data = b"0\n" + rest
            rows.append(
                {
                    "name": name,
                    "mode": entry.mode,
                    "uid": entry.uid,
                    "gid": entry.gid,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        return hashlib.sha256(
            canonical_json(sorted(rows, key=lambda item: item["name"]))
        ).hexdigest()


def _normalized_file_sha256(path: Path, fields: Sequence[str]) -> str:
    lowered = path.name.lower()
    if "registry-generated-metadata" in fields and lowered.endswith(".tgz"):
        return _normalized_conan_sha256(path)
    if "archive-entry-timestamp" in fields and (
        lowered.endswith((".tar.gz", ".tgz", ".crate", ".gem"))
    ):
        try:
            with tarfile.open(path, "r:*") as archive:
                rows: list[dict[str, object]] = []
                for member in sorted(archive.getmembers(), key=lambda item: item.name):
                    row: dict[str, object] = {
                        "name": member.name,
                        "type": member.type.hex(),
                        "mode": member.mode,
                        "size": member.size,
                        "linkname": member.linkname,
                        "uid": member.uid,
                        "gid": member.gid,
                        "uname": member.uname,
                        "gname": member.gname,
                        "pax_headers": {
                            key: value
                            for key, value in member.pax_headers.items()
                            if key not in {"mtime", "atime", "ctime"}
                        },
                    }
                    if member.isfile():
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            raise ReleaseSupplyChainError(
                                "reproducibility",
                                f"cannot read archive entry {member.name}",
                            )
                        row["sha256"] = hashlib.sha256(extracted.read()).hexdigest()
                    rows.append(row)
            return hashlib.sha256(canonical_json(rows)).hexdigest()
        except (OSError, tarfile.TarError) as error:
            raise ReleaseSupplyChainError(
                "reproducibility", f"cannot normalize tar artifact {path}: {error}"
            ) from error

    if any(item in fields for item in ("archive-entry-timestamp", "signature")) and (
        lowered.endswith((".zip", ".jar", ".nupkg", ".whl"))
    ):
        try:
            with zipfile.ZipFile(path) as archive:
                rows = []
                if len(archive.namelist()) != len(set(archive.namelist())):
                    raise ReleaseSupplyChainError(
                        "reproducibility", "duplicate ZIP member"
                    )
                for name in sorted(archive.namelist()):
                    upper = name.upper()
                    if "signature" in fields and (
                        upper.startswith("META-INF/")
                        and upper.endswith((".SF", ".RSA", ".DSA", ".EC"))
                    ):
                        continue
                    rows.append(
                        {
                            "name": name,
                            "sha256": hashlib.sha256(archive.read(name)).hexdigest(),
                            "external_attr": archive.getinfo(name).external_attr,
                            "internal_attr": archive.getinfo(name).internal_attr,
                            "create_system": archive.getinfo(name).create_system,
                            "compress_type": archive.getinfo(name).compress_type,
                            "comment": archive.getinfo(name).comment.hex(),
                            "extra": archive.getinfo(name).extra.hex(),
                        }
                    )
            return hashlib.sha256(canonical_json(rows)).hexdigest()
        except (OSError, zipfile.BadZipFile) as error:
            raise ReleaseSupplyChainError(
                "reproducibility", f"cannot normalize ZIP artifact {path}: {error}"
            ) from error
    return _sha256_file(path)


def _normalized_surface_sha256(
    root: Path, members: Sequence[Mapping[str, object]], fields: Sequence[str]
) -> str:
    normalized: list[dict[str, str]] = []
    for member in members:
        path = root / cast(str, member["name"])
        if path.is_dir():
            nested = []
            for row in _tree_members(root, path):
                nested_path = root / cast(str, row["name"])
                nested.append(
                    {
                        "name": row["name"],
                        "sha256": _normalized_file_sha256(nested_path, fields),
                    }
                )
            digest = hashlib.sha256(canonical_json(nested)).hexdigest()
        else:
            digest = _normalized_file_sha256(path, fields)
        normalized.append({"name": cast(str, member["name"]), "sha256": digest})
    return hashlib.sha256(canonical_json(normalized)).hexdigest()


def _dependency_resolution(
    root: Path,
    manifest: Mapping[str, object],
    artifact: Mapping[str, object],
    risk_evidence: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], int]:
    security = load_json(root / cast(str, manifest["security_policy"]))
    policies = {
        row["id"]: row
        for row in cast(list[dict[str, Any]], security["dependency_roots"])
    }
    components: list[dict[str, object]] = []
    unresolved = 0
    risk_checks: dict[str, Mapping[str, object]] = {}
    if risk_evidence is not None:
        summary = risk_evidence.get("summary")
        raw_checks = risk_evidence.get("checks")
        if (
            risk_evidence.get("operation_id") != "security.dependency-risk"
            or risk_evidence.get("status") not in ("passed", "waived")
            or not isinstance(summary, dict)
            or any(
                summary.get(status, 0) != 0
                for status in ("failed", "incomplete", "unavailable")
            )
            or not isinstance(raw_checks, list)
        ):
            raise ReleaseSupplyChainError(
                "dependency-risk", "live dependency-risk evidence is not release-usable"
            )
        for check in raw_checks:
            if not isinstance(check, dict) or not isinstance(
                check.get("check_id"), str
            ):
                raise ReleaseSupplyChainError(
                    "dependency-risk", "live dependency-risk evidence is malformed"
                )
            risk_checks[cast(str, check["check_id"])] = check
    for dependency_id in cast(list[str], artifact["dependency_roots"]):
        policy = policies[dependency_id]
        manifest_hashes = []
        for relative in [*policy.get("manifests", []), *policy.get("locks", [])]:
            path = root / relative
            if path.is_file():
                manifest_hashes.append({"path": relative, "sha256": _sha256_file(path)})
            else:
                unresolved += 1
        resolved_without_external = policy.get(
            "risk_mode"
        ) == "no_dependencies" and policy.get("integrity_mode") in (
            "no_external_dependencies",
            "inventory_only",
        )
        resolved_components: list[dict[str, object]] = []
        reachable = None
        if dependency_id == "interop-cargo" and policy.get("ecosystem") == "cargo":
            from tooling.release_notices import locked_packages

            reachable = {(row["name"], row["version"]) for row in locked_packages(root)}
        evidence_hash: str | None = None
        if risk_evidence is not None:
            vulnerability = risk_checks.get(f"security.vulnerability.{dependency_id}")
            license_check = risk_checks.get(f"security.license.{dependency_id}")
            if (
                vulnerability is None
                or license_check is None
                or vulnerability.get("status") != "passed"
                or license_check.get("status") != "passed"
            ):
                unresolved += 1
            else:
                scanner = license_check.get("scanner")
                raw_components = (
                    scanner.get("components") if isinstance(scanner, dict) else None
                )
                if raw_components is None and resolved_without_external:
                    raw_components = []
                if not isinstance(raw_components, list):
                    unresolved += 1
                else:
                    for component in raw_components:
                        if (
                            reachable is not None
                            and isinstance(component, dict)
                            and (component.get("name"), component.get("version"))
                            not in reachable
                        ):
                            continue
                        if (
                            not isinstance(component, dict)
                            or not all(
                                isinstance(component.get(field), str)
                                and bool(component[field].strip())
                                for field in (
                                    "name",
                                    "version",
                                    "reported_license",
                                    "classification",
                                    "distribution_scope",
                                )
                            )
                            or component.get("classification")
                            not in ("permitted", "scoped_permitted")
                            or component.get("reported_license")
                            in {"NOASSERTION", "NONE"}
                            or (
                                component.get("selected_license") is not None
                                and (
                                    not isinstance(component["selected_license"], str)
                                    or not component["selected_license"].strip()
                                    or component["selected_license"]
                                    in {"NOASSERTION", "NONE"}
                                )
                            )
                            or re.search(r"[<>=*]", component.get("version", ""))
                        ):
                            unresolved += 1
                            continue
                        resolved_components.append(dict(component))
                    evidence_hash = hashlib.sha256(
                        canonical_json(
                            {"vulnerability": vulnerability, "license": license_check}
                        )
                    ).hexdigest()
        elif not resolved_without_external:
            unresolved += 1
        if (
            reachable is not None
            and {(row["name"], row["version"]) for row in resolved_components}
            != reachable
        ):
            unresolved += 1
        components.append(
            {
                "id": dependency_id,
                "policy": {
                    "ecosystem": policy.get("ecosystem"),
                    "risk_mode": policy.get("risk_mode"),
                    "integrity_mode": policy.get("integrity_mode"),
                },
                "inputs": manifest_hashes,
                "resolved_without_external": resolved_without_external,
                "resolved_components": resolved_components,
                "risk_evidence_sha256": evidence_hash,
            }
        )
    return components, unresolved


def inspect_release_payload(
    root: Path, artifact: Mapping[str, object], version: str, members: list
) -> list:
    try:
        from tooling.release_payload import inspect_payload

        return inspect_payload(root, dict(artifact), version, members)
    except (
        ValueError,
        OSError,
        KeyError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        raise ReleaseSupplyChainError("artifact-payload", str(error)) from error


def _validate_spdx(document: Mapping[str, object]) -> None:
    """Validate against the attributed, semantically unchanged official schema."""
    schema = load_json(SPDX_SCHEMA_PATH)
    identity = load_json(SPDX_SCHEMA_PATH.with_name("spdx-schema-source.json"))
    if identity["vendored_sha256"] != _sha256_file(SPDX_SCHEMA_PATH) or identity[
        "semantic_sha256"
    ] != document_fingerprint(schema):
        raise ReleaseSupplyChainError(
            "sbom-schema",
            "vendored SPDX schema differs from its reviewed upstream identity",
        )
    Draft7Validator.check_schema(schema)
    error = best_match(Draft7Validator(schema).iter_errors(document))
    if error is not None:
        raise ReleaseSupplyChainError(
            "sbom-schema", "invalid SPDX 2.3 document: " + error.message
        )


def _spdx_document(
    artifact: Mapping[str, object],
    members: Sequence[Mapping[str, object]],
    subject_digest: str,
    dependencies: Sequence[Mapping[str, object]],
    version: str = "unspecified",
    content_files: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    artifact_id = cast(str, artifact["id"])
    surface = cast(str, artifact["surface"])
    namespace = f"https://strling.dev/sbom/{surface}/{subject_digest}"
    files: list[dict[str, object]] = []
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package",
        }
    ]
    flattened: list[Mapping[str, object]] = []
    for member in members:
        nested = member.get("files")
        if isinstance(nested, list):
            flattened.extend(cast(list[Mapping[str, object]], nested))
        else:
            flattened.append(member)
    if content_files is not None:
        flattened = list(content_files)
    if content_files is not None and any(
        re.fullmatch(r"[0-9a-f]{40}", str(member.get("sha1", ""))) is None
        for member in flattened
    ):
        raise ReleaseSupplyChainError(
            "sbom-files",
            "analyzed SPDX files require actual SHA-1 compatibility digests",
        )
    analyzed = bool(flattened) and all("sha1" in member for member in flattened)
    for index, member in enumerate(flattened, start=1):
        spdx_id = f"SPDXRef-File-{index}"
        files.append(
            {
                "SPDXID": spdx_id,
                "fileName": member["name"],
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": member["sha256"]},
                    *(
                        [{"algorithm": "SHA1", "checksumValue": member["sha1"]}]
                        if analyzed
                        else []
                    ),
                ],
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": spdx_id,
            }
        )
    annotations = [
        {
            "annotationType": "OTHER",
            "annotator": "Tool: strling-release-supply-chain",
            "annotationDate": "1970-01-01T00:00:00Z",
            "comment": json.dumps(dependency, sort_keys=True, separators=(",", ":")),
        }
        for dependency in dependencies
    ]
    packages: list[dict[str, object]] = [
        {
            "name": cast(str, artifact["package_name"]),
            "versionInfo": version,
            "SPDXID": "SPDXRef-Package",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": analyzed,
            **(
                {
                    "packageVerificationCode": {
                        "packageVerificationCodeValue": hashlib.sha1(
                            "".join(
                                sorted(str(member["sha1"]) for member in flattened)
                            ).encode("ascii"),
                            usedforsecurity=False,
                        ).hexdigest()
                    }
                }
                if analyzed
                else {}
            ),
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "Apache-2.0",
            "copyrightText": "NOASSERTION",
            "checksums": [{"algorithm": "SHA256", "checksumValue": subject_digest}],
            "externalRefs": [
                {
                    "referenceCategory": "OTHER",
                    "referenceType": "strling-release-surface",
                    "referenceLocator": artifact_id,
                }
            ],
        }
    ]
    dependency_index = 0
    for dependency in dependencies:
        root_id = cast(str, dependency["id"])
        for component in cast(
            list[Mapping[str, object]], dependency.get("resolved_components", [])
        ):
            dependency_index += 1
            name = cast(str, component["name"])
            version = cast(str, component["version"])
            reported_license = cast(str, component["reported_license"])
            selected_license = component.get("selected_license")
            identity = hashlib.sha256(
                canonical_json(
                    {
                        "root": root_id,
                        "name": name,
                        "version": version,
                    }
                )
            ).hexdigest()[:12]
            spdx_id = f"SPDXRef-Dependency-{dependency_index}-{identity}"
            coordinate = json.dumps(
                {
                    "dependency_root": root_id,
                    "ecosystem": dependency["policy"]["ecosystem"],
                    "name": name,
                    "version": version,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            packages.append(
                {
                    "name": name,
                    "versionInfo": version,
                    "SPDXID": spdx_id,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "licenseDeclared": reported_license,
                    "licenseConcluded": (
                        selected_license
                        if isinstance(selected_license, str)
                        else reported_license
                    ),
                    "copyrightText": "NOASSERTION",
                    "externalRefs": [
                        {
                            "referenceCategory": "OTHER",
                            "referenceType": "strling-dependency-coordinate",
                            "referenceLocator": coordinate,
                        }
                    ],
                    "annotations": [
                        {
                            "annotationType": "OTHER",
                            "annotator": "Tool: strling-release-supply-chain",
                            "annotationDate": "1970-01-01T00:00:00Z",
                            "comment": json.dumps(
                                {
                                    "dependency_root": root_id,
                                    "classification": component["classification"],
                                    "disposition_id": component.get("disposition_id"),
                                    "distribution_scope": component[
                                        "distribution_scope"
                                    ],
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            )
            if str(component["distribution_scope"]).startswith("non-distributed"):
                relationships.append(
                    {
                        "spdxElementId": spdx_id,
                        "relationshipType": "BUILD_DEPENDENCY_OF",
                        "relatedSpdxElement": "SPDXRef-Package",
                    }
                )
            else:
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-Package",
                        "relationshipType": "DEPENDS_ON",
                        "relatedSpdxElement": spdx_id,
                    }
                )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"STRling {surface} release artifact",
        "documentNamespace": namespace,
        "creationInfo": {
            "created": "1970-01-01T00:00:00Z",
            "creators": ["Tool: strling-release-supply-chain"],
            "licenseListVersion": "3.23",
        },
        "documentDescribes": ["SPDXRef-Package"],
        "packages": packages,
        "files": files,
        "relationships": relationships,
        "annotations": annotations,
    }


def _provenance_statement(
    artifact: Mapping[str, object],
    members: Sequence[Mapping[str, object]],
    source: Mapping[str, object],
    manifest_fingerprint: str,
    toolchains: Sequence[Mapping[str, object]],
    dependencies: Sequence[Mapping[str, object]],
    version: str = "unspecified",
) -> dict[str, object]:
    artifact_id = cast(str, artifact["id"])
    required_toolchains = set(cast(list[str], artifact["toolchain_refs"]))
    toolchain_inputs = [
        {
            "id": row["id"],
            "executable_sha256": row["executable_sha256"],
            "version": row["version"],
        }
        for row in toolchains
        if row["artifact_id"] == artifact_id
        and row["toolchain_id"] in required_toolchains
    ]
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": member["name"], "digest": {"sha256": member["sha256"]}}
            for member in members
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://strling.dev/build-types/release-supply-chain/v1",
                "externalParameters": {
                    "artifactId": artifact_id,
                    "buildCommand": artifact["build_command"],
                    "productVersion": version,
                    "registry": artifact["registry"],
                    "support": artifact["distribution_contract"],
                },
                "internalParameters": {
                    "manifestSha256": manifest_fingerprint,
                    "toolchains": toolchain_inputs,
                },
                "resolvedDependencies": [
                    {
                        "uri": f"git+https://github.com/strling-lang/strling@{source['commit']}",
                        "digest": {"gitCommit": source["commit"]},
                    },
                    *[
                        {
                            "uri": f"strling:dependency-root:{row['id']}",
                            "digest": {
                                "sha256": hashlib.sha256(
                                    canonical_json(row)
                                ).hexdigest()
                            },
                        }
                        for row in dependencies
                    ],
                ],
            },
            "runDetails": {
                "builder": {
                    "id": "https://strling.dev/builders/release-supply-chain/v1"
                },
                "metadata": {
                    "invocationId": f"{source['commit']}:{artifact_id}",
                    "startedOn": "1970-01-01T00:00:00Z",
                    "finishedOn": "1970-01-01T00:00:00Z",
                },
            },
        },
    }


def _missing_artifact_row(
    artifact: Mapping[str, object], source: Mapping[str, object], message: str
) -> dict[str, object]:
    artifact_id = cast(str, artifact["id"])
    policy = cast(dict[str, Any], artifact["artifact_policy"])
    reproducibility = cast(dict[str, Any], artifact["reproducibility"])
    credential = cast(dict[str, Any], artifact["credential_policy"])
    digest = hashlib.sha256(
        canonical_json({"id": artifact_id, "missing": True})
    ).hexdigest()
    subject_name = f"missing:{artifact_id}"
    return {
        "id": artifact_id,
        "status": "unavailable",
        "subject": {
            "name": subject_name,
            "kind": policy["subject_kind"],
            "sha256": digest,
            "bytes": None,
        },
        "checksum": {"algorithm": "sha256", "digest": digest},
        "sbom": {
            "spdx_version": "SPDX-2.3",
            "document_namespace": f"https://strling.dev/sbom/missing/{artifact_id.removeprefix('release:')}",
            "sha256": hashlib.sha256(
                f"{artifact_id}:missing-sbom".encode()
            ).hexdigest(),
            "component_count": 1,
            "relationship_count": 0,
            "unresolved_components": 1,
        },
        "provenance": {
            "statement_type": "https://in-toto.io/Statement/v1",
            "predicate_type": "https://slsa.dev/provenance/v1",
            "subject_name": subject_name,
            "subject_sha256": digest,
            "source_commit": source["commit"],
            "builder_id": "https://strling.dev/builders/release-supply-chain/v1",
            "build_command_sha256": hashlib.sha256(
                canonical_json(artifact["build_command"])
            ).hexdigest(),
            "predicate_sha256": hashlib.sha256(
                f"{artifact_id}:missing-provenance".encode()
            ).hexdigest(),
        },
        "reproducibility": {
            "mode": reproducibility["mode"],
            "status": "unavailable",
            "first_sha256": digest,
            "second_sha256": digest,
            "normalized_sha256": None,
            "normalized_fields": reproducibility["allowed_normalizations"],
        },
        "credential": {
            "mode": credential["mode"],
            "secret_names": credential["secret_names"],
            "oidc_issuer": "https://token.actions.githubusercontent.com"
            if credential["mode"] == "oidc"
            else None,
            "environment": "release",
            "untrusted_context_forbidden": True,
        },
        "findings": [{"code": "SUPPLY-ARTIFACT-UNAVAILABLE", "message": message}],
    }


def produce_bundle(
    *,
    root: Path,
    second_root: Path,
    output_dir: Path,
    version: str,
    profile: str,
    manifest: Mapping[str, object],
    source: Mapping[str, object],
    workflow: Mapping[str, object],
    toolchains: Sequence[Mapping[str, object]],
    evidence_authority: str,
    risk_evidence: Mapping[str, object] | None = None,
    rebuild_source: Mapping[str, object] | None = None,
    build_receipts: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Produce deterministic evidence over two already-prepared artifact trees."""

    if output_dir.exists():
        raise ReleaseSupplyChainError(
            "output-exists", "evidence output directory must not already exist"
        )
    if evidence_authority == "live-dry-run" and rebuild_source is None:
        raise ReleaseSupplyChainError(
            "source-rebuild", "live evidence requires an authenticated rebuild source"
        )
    authenticated_rebuild = dict(rebuild_source or source)
    if authenticated_rebuild != dict(source):
        raise ReleaseSupplyChainError(
            "source-rebuild", "rebuild source identity differs from primary source"
        )
    if evidence_authority == "live-dry-run" and build_receipts is None:
        raise ReleaseSupplyChainError(
            "build-receipt",
            "live evidence requires every independent platform build receipt",
        )
    validate_manifest(manifest, root=root)
    if (
        version
        != load_json(root / "governance/release-policy.json")["product"]["version"]
    ):
        raise ReleaseSupplyChainError(
            "product-version",
            "artifact version differs from canonical product authority",
        )
    expected_toolchains = _toolchain_evidence_ids(manifest)
    if _exact_ids(toolchains, label="producer toolchain") != expected_toolchains:
        raise ReleaseSupplyChainError(
            "toolchain-denominator", "producer toolchain denominator changed"
        )
    manifest_fingerprint = document_fingerprint(manifest)
    toolchain_by_id = {
        (
            cast(str, row["artifact_id"]),
            cast(str, row["scope"]),
            cast(str, row["toolchain_id"]),
        ): row
        for row in toolchains
    }
    rows: list[dict[str, object]] = []
    companion_documents: list[tuple[Path, Mapping[str, object] | str]] = []

    for artifact in _artifact_rows(manifest):
        artifact_id = cast(str, artifact["id"])
        surface = cast(str, artifact["surface"])
        try:
            first_members = _surface_members(root, artifact, version)
            second_members = _surface_members(second_root, artifact, version)
            content_files = None
            if evidence_authority == "live-dry-run":
                content_files = inspect_release_payload(
                    root, artifact, version, first_members
                )
                inspect_release_payload(second_root, artifact, version, second_members)
        except ReleaseSupplyChainError as error:
            rows.append(_missing_artifact_row(artifact, source, str(error)))
            continue

        subject_name, subject_digest, subject_bytes = _surface_identity(first_members)
        _, second_digest, _ = _surface_identity(second_members)
        reproducibility_policy = cast(dict[str, Any], artifact["reproducibility"])
        mode = cast(str, reproducibility_policy["mode"])
        normalized_fields = cast(
            list[str], reproducibility_policy["allowed_normalizations"]
        )
        normalized_sha256: str | None = None
        reproducibility_status = "passed"
        findings: list[dict[str, str]] = []
        if mode == "normalized":
            first_normalized = _normalized_surface_sha256(
                root, first_members, normalized_fields
            )
            second_normalized = _normalized_surface_sha256(
                second_root, second_members, normalized_fields
            )
            normalized_sha256 = first_normalized
            if first_normalized != second_normalized:
                reproducibility_status = "failed"
                findings.append(
                    {
                        "code": "SUPPLY-REPRODUCIBILITY-MISMATCH",
                        "message": f"{artifact_id} normalized rebuild differs",
                    }
                )
        elif subject_digest != second_digest:
            reproducibility_status = "failed"
            findings.append(
                {
                    "code": "SUPPLY-REPRODUCIBILITY-MISMATCH",
                    "message": f"{artifact_id} exact rebuild differs",
                }
            )

        dependencies, unresolved = _dependency_resolution(
            root, manifest, artifact, risk_evidence
        )
        if unresolved:
            findings.append(
                {
                    "code": "SUPPLY-SBOM-UNRESOLVED",
                    "message": f"{artifact_id} has {unresolved} unresolved dependency inputs",
                }
            )
        required_toolchains = cast(list[str], artifact["toolchain_refs"])
        unavailable_toolchains = [
            f"{scope}:{item}"
            for scope in artifact_scopes(artifact)
            for item in required_toolchains
            if toolchain_by_id[(artifact_id, scope, item)]["status"] != "passed"
        ]
        if unavailable_toolchains:
            findings.append(
                {
                    "code": "SUPPLY-TOOLCHAIN-UNAVAILABLE",
                    "message": f"{artifact_id} lacks toolchains: {', '.join(unavailable_toolchains)}",
                }
            )

        spdx = _spdx_document(
            artifact,
            first_members,
            subject_digest,
            dependencies,
            version,
            content_files,
        )
        provenance = _provenance_statement(
            artifact,
            first_members,
            source,
            manifest_fingerprint,
            toolchains,
            dependencies,
            version,
        )
        _validate_spdx(spdx)
        spdx_sha256 = hashlib.sha256(canonical_json(spdx)).hexdigest()
        provenance_sha256 = hashlib.sha256(canonical_json(provenance)).hexdigest()
        checksum_lines = [f"# surface-sha256 {subject_digest}"]
        checksum_lines.extend(
            f"{member['sha256']}  {member['name']}" for member in first_members
        )
        checksum_text = "\n".join(checksum_lines) + "\n"
        companion_documents.extend(
            [
                (Path("checksums") / f"{surface}.sha256", checksum_text),
                (Path("sbom") / f"{surface}.spdx.json", spdx),
                (Path("provenance") / f"{surface}.intoto.json", provenance),
            ]
        )
        artifact_status = "passed"
        if reproducibility_status == "failed":
            artifact_status = "failed"
        elif unresolved or unavailable_toolchains:
            artifact_status = "incomplete"
        policy = cast(dict[str, Any], artifact["artifact_policy"])
        credential = cast(dict[str, Any], artifact["credential_policy"])
        rows.append(
            {
                "id": artifact_id,
                "status": artifact_status,
                "subject": {
                    "name": subject_name,
                    "kind": policy["subject_kind"],
                    "sha256": subject_digest,
                    "bytes": subject_bytes,
                },
                "checksum": {"algorithm": "sha256", "digest": subject_digest},
                "sbom": {
                    "spdx_version": "SPDX-2.3",
                    "document_namespace": spdx["documentNamespace"],
                    "sha256": spdx_sha256,
                    "component_count": len(cast(list[object], spdx["packages"])),
                    "relationship_count": len(
                        cast(list[object], spdx["relationships"])
                    ),
                    "unresolved_components": unresolved,
                },
                "provenance": {
                    "statement_type": "https://in-toto.io/Statement/v1",
                    "predicate_type": "https://slsa.dev/provenance/v1",
                    "subject_name": subject_name,
                    "subject_sha256": subject_digest,
                    "source_commit": source["commit"],
                    "builder_id": "https://strling.dev/builders/release-supply-chain/v1",
                    "build_command_sha256": hashlib.sha256(
                        canonical_json(artifact["build_command"])
                    ).hexdigest(),
                    "predicate_sha256": provenance_sha256,
                },
                "reproducibility": {
                    "mode": mode,
                    "status": reproducibility_status,
                    "first_sha256": subject_digest,
                    "second_sha256": second_digest,
                    "normalized_sha256": normalized_sha256,
                    "normalized_fields": normalized_fields,
                },
                "credential": {
                    "mode": credential["mode"],
                    "secret_names": credential["secret_names"],
                    "oidc_issuer": "https://token.actions.githubusercontent.com"
                    if credential["mode"] == "oidc"
                    else None,
                    "environment": "release",
                    "untrusted_context_forbidden": True,
                },
                "findings": findings,
            }
        )

    artifact_statuses = [cast(str, row["status"]) for row in rows]
    overall_status = _aggregate_status(
        [*artifact_statuses, *[cast(str, row["status"]) for row in toolchains]]
    )
    evidence: dict[str, Any] = {
        "schema_version": "2.0.0",
        "document_kind": "release-supply-chain-evidence",
        "operation_id": "certification.release-supply-chain",
        "profile": profile,
        "status": overall_status,
        "evidence_authority": evidence_authority,
        "publication_authorized": False,
        "manifest_fingerprint": manifest_fingerprint,
        "source": dict(source),
        "rebuild_source": authenticated_rebuild,
        "workflow": dict(workflow),
        "toolchains": [dict(row) for row in toolchains],
        "build_receipts": [dict(row) for row in (build_receipts or [])],
        "artifacts": rows,
        "summary": {
            status: artifact_statuses.count(status) for status in STATUS_PRECEDENCE
        },
        "evidence_fingerprint": "0" * 64,
    }
    evidence["summary"]["total"] = len(rows)
    evidence["evidence_fingerprint"] = document_fingerprint(
        evidence, "evidence_fingerprint"
    )
    validate_evidence(evidence, manifest, root=root)

    output_dir.mkdir(parents=True)
    for relative, document in companion_documents:
        path = output_dir / relative
        if isinstance(document, str):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(document, encoding="utf-8", newline="\n")
        else:
            _write_json(path, document)
    _write_json(output_dir / "release-supply-chain-evidence.json", evidence)
    return evidence


def verify_bundle(
    *,
    root: Path,
    evidence_path: Path,
    manifest: Mapping[str, object],
    verify_subjects: bool = True,
) -> dict[str, Any]:
    evidence = validate_evidence(load_json(evidence_path), manifest, root=root)
    if verify_subjects and evidence["evidence_authority"] == "live-dry-run":
        _validate_retained_builds(
            root=root,
            manifest=manifest,
            source=evidence["source"],
            captured=evidence["build_receipts"],
            version=load_json(root / "governance/release-policy.json")["product"][
                "version"
            ],
            verify_subjects=True,
        )
    bundle_root = evidence_path.parent
    contracts = {row["id"]: row for row in _artifact_rows(manifest)}
    for row in cast(list[dict[str, Any]], evidence["artifacts"]):
        if row["status"] != "passed":
            continue
        surface = cast(str, contracts[row["id"]]["surface"])
        checksum_path = bundle_root / "checksums" / f"{surface}.sha256"
        sbom_path = bundle_root / "sbom" / f"{surface}.spdx.json"
        provenance_path = bundle_root / "provenance" / f"{surface}.intoto.json"
        try:
            checksum = checksum_path.read_text(encoding="utf-8")
            sbom = load_json(sbom_path)
            provenance = load_json(provenance_path)
        except OSError as error:
            raise ReleaseSupplyChainError(
                "bundle-document", f"cannot read {surface} companion evidence: {error}"
            ) from error
        expected_header = f"# surface-sha256 {row['subject']['sha256']}\n"
        if not checksum.startswith(expected_header):
            raise ReleaseSupplyChainError(
                "checksum-document", f"{surface} checksum header changed"
            )
        members: list[dict[str, object]] = []
        checksum_subjects: list[dict[str, object]] = []
        for line in checksum.splitlines()[1:]:
            matched = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if matched is None:
                raise ReleaseSupplyChainError(
                    "checksum-document", f"{surface} checksum entry is malformed"
                )
            expected_digest, relative = matched.groups()
            if verify_subjects:
                policy = cast(dict[str, Any], contracts[row["id"]]["artifact_policy"])
                member = _member_from_path(
                    root,
                    relative,
                    source_tree=policy["subject_kind"] == "source-tree",
                )
                if member["sha256"] != expected_digest:
                    raise ReleaseSupplyChainError(
                        "checksum-document",
                        f"{surface} artifact bytes changed: {relative}",
                    )
                members.append(member)
            checksum_subjects.append(
                {"name": relative, "digest": {"sha256": expected_digest}}
            )
        if not checksum_subjects:
            raise ReleaseSupplyChainError(
                "checksum-document", f"{surface} checksum document is empty"
            )
        if verify_subjects:
            observed_name, observed_digest, observed_bytes = _surface_identity(members)
            if (
                observed_name != row["subject"]["name"]
                or observed_digest != row["subject"]["sha256"]
                or observed_bytes != row["subject"]["bytes"]
            ):
                raise ReleaseSupplyChainError(
                    "checksum-document", f"{surface} aggregate subject changed"
                )
        if hashlib.sha256(canonical_json(sbom)).hexdigest() != row["sbom"]["sha256"]:
            raise ReleaseSupplyChainError(
                "sbom-document", f"{surface} SPDX document changed"
            )
        _validate_spdx(sbom)
        packages = sbom.get("packages")
        if not isinstance(packages, list) or not packages:
            raise ReleaseSupplyChainError(
                "sbom-document", f"{surface} SPDX package is absent"
            )
        product_version = load_json(root / "governance/release-policy.json")["product"][
            "version"
        ]
        if (
            sbom.get("spdxVersion") != "SPDX-2.3"
            or sbom.get("dataLicense") != "CC0-1.0"
            or packages[0].get("name") != contracts[row["id"]]["package_name"]
            or packages[0].get("versionInfo") != product_version
            or packages[0].get("licenseDeclared") != "Apache-2.0"
            or not sbom.get("files")
        ):
            raise ReleaseSupplyChainError(
                "sbom-metadata",
                f"{surface} SPDX identity, version, license, or file graph is inconsistent",
            )
        if verify_subjects and evidence["evidence_authority"] == "live-dry-run":
            content = inspect_release_payload(
                root, contracts[row["id"]], product_version, members
            )
            expected_files = [
                (item["name"], item["sha256"], item["sha1"]) for item in content
            ]
            observed_files = [
                (item.get("fileName"), item.get("checksums")) for item in sbom["files"]
            ]
            if observed_files != [
                (
                    name,
                    [
                        {"algorithm": "SHA256", "checksumValue": digest},
                        {"algorithm": "SHA1", "checksumValue": sha1},
                    ],
                )
                for name, digest, sha1 in expected_files
            ]:
                raise ReleaseSupplyChainError(
                    "sbom-files", "SPDX content graph differs from actual package files"
                )
        if verify_subjects and evidence["evidence_authority"] == "live-dry-run":
            expected_verification = hashlib.sha1(
                "".join(sorted(item["sha1"] for item in content)).encode("ascii"),
                usedforsecurity=False,
            ).hexdigest()
            if packages[0].get("filesAnalyzed") is not True or packages[0].get(
                "packageVerificationCode"
            ) != {"packageVerificationCodeValue": expected_verification}:
                raise ReleaseSupplyChainError(
                    "sbom-files",
                    "SPDX package verification code differs from actual content",
                )
        package_checksums = packages[0].get("checksums")
        if package_checksums != [
            {"algorithm": "SHA256", "checksumValue": row["subject"]["sha256"]}
        ]:
            raise ReleaseSupplyChainError(
                "sbom-document", f"{surface} SPDX subject changed"
            )
        if (
            hashlib.sha256(canonical_json(provenance)).hexdigest()
            != row["provenance"]["predicate_sha256"]
        ):
            raise ReleaseSupplyChainError(
                "provenance-document", f"{surface} provenance statement changed"
            )
        if (
            provenance.get("_type") != "https://in-toto.io/Statement/v1"
            or provenance.get("predicateType") != "https://slsa.dev/provenance/v1"
        ):
            raise ReleaseSupplyChainError(
                "provenance-document", f"{surface} provenance type changed"
            )
        if provenance.get("subject") != checksum_subjects:
            raise ReleaseSupplyChainError(
                "provenance-document", f"{surface} provenance subjects changed"
            )
        contract = contracts[row["id"]]
        definition = provenance.get("predicate", {}).get("buildDefinition", {})
        expected_parameters = {
            "artifactId": row["id"],
            "buildCommand": contract["build_command"],
            "productVersion": product_version,
            "registry": contract["registry"],
            "support": contract["distribution_contract"],
        }
        dependencies = definition.get("resolvedDependencies", [])
        if (
            definition.get("externalParameters") != expected_parameters
            or definition.get("internalParameters", {}).get("manifestSha256")
            != evidence["manifest_fingerprint"]
            or not dependencies
            or dependencies[0]
            != {
                "uri": "git+https://github.com/strling-lang/strling@"
                + evidence["source"]["commit"],
                "digest": {"gitCommit": evidence["source"]["commit"]},
            }
        ):
            raise ReleaseSupplyChainError(
                "provenance-metadata",
                f"{surface} SLSA source or release metadata is inconsistent",
            )
    return evidence


def run_profile_certification(
    *, profile: str, evidence_path: Path | None, root: Path = ROOT
) -> dict[str, Any]:
    if evidence_path is None:
        if profile in {"full", "release"}:
            raise ReleaseSupplyChainError(
                "evidence-required",
                "Full/Release packaging certification requires exact-source live artifact and consumer evidence",
            )
        contract = run_contract_check()
        status = cast(str, contract["status"])
        fingerprint = cast(str, contract["manifest_fingerprint"])
        evidence_authority = "contract"
    else:
        manifest = load_json(root / MANIFEST_PATH.relative_to(ROOT))
        evidence = verify_bundle(
            root=root,
            evidence_path=evidence_path,
            manifest=manifest,
            verify_subjects=False,
        )
        if evidence["profile"] != profile:
            raise ReleaseSupplyChainError(
                "profile", f"{profile} evidence profile changed"
            )
        status = cast(str, evidence["status"])
        fingerprint = cast(str, evidence["evidence_fingerprint"])
        evidence_authority = "live-dry-run"
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.release-supply-chain-profile",
        "profile": profile,
        "status": status,
        "publication_authorized": False,
        "evidence_authority": evidence_authority,
        "evidence_fingerprint": fingerprint,
    }


def verify_publication_authorization(
    *,
    authorization: Mapping[str, Any],
    expected_sha256: str,
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any],
    context: Mapping[str, str],
    certified_source_sha: str,
    certified_evidence_root: str,
) -> dict[str, Any]:
    """Bind future owner approval to exact verified bytes and a protected run.

    The expected digest and reviewed workflow SHA must come from the protected
    environment, never dispatch inputs or candidate executable output. This
    verifier grants no registry credentials and performs no external writes.
    """
    validate_schema(authorization, label="publication authorization")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or "")
        or hashlib.sha256(canonical_json(authorization)).hexdigest() != expected_sha256
    ):
        raise ReleaseSupplyChainError(
            "publication-authorization", "missing or unapproved owner authorization"
        )
    event = context.get("event_name")
    allowed_ref = (
        "refs/heads/main"
        if event == "workflow_dispatch"
        else "refs/tags/v" + authorization["version"]
    )
    if (
        event not in {"workflow_dispatch", "push"}
        or context.get("repository") != "strling-lang/strling"
        or context.get("ref") != allowed_ref
        or context.get("environment") != "release"
        or not re.fullmatch(r"[0-9a-f]{40}", context.get("reviewed_workflow_sha", ""))
        or context.get("workflow_sha") != context.get("reviewed_workflow_sha")
        or context.get("dry_run") != "false"
    ):
        raise ReleaseSupplyChainError(
            "publication-context",
            "publication requires the reviewed workflow and protected owner-authorized run",
        )
    for field in ("repository", "workflow_sha", "run_id", "run_attempt", "environment"):
        if authorization[field] != context.get(field):
            raise ReleaseSupplyChainError(
                "publication-context", f"authorization {field} does not match this run"
            )
    for field in ("artifact_run_id", "certification_ref"):
        if authorization[field] != context.get(field):
            raise ReleaseSupplyChainError(
                "publication-context",
                "certified artifact transport differs from owner approval",
            )
    if (
        evidence.get("profile") != "release"
        or evidence.get("evidence_authority") != "live-dry-run"
        or evidence.get("status") != "passed"
        or authorization["source_sha"] != evidence["source"]["commit"]
        or authorization["source_sha"] != certified_source_sha
        or authorization["certification_evidence_root"] != certified_evidence_root
        or authorization["evidence_fingerprint"] != evidence["evidence_fingerprint"]
        or authorization["manifest_fingerprint"] != document_fingerprint(manifest)
    ):
        raise ReleaseSupplyChainError(
            "publication-evidence",
            "authorization lacks exact same-source certified Release evidence",
        )
    version = authorization["version"]
    if not re.fullmatch(r"4\.0\.0(?:-rc\.[1-9][0-9]*)?", version):
        raise ReleaseSupplyChainError(
            "publication-version",
            "authorization version is outside the ratified release line",
        )
    if (authorization["channel"] == "stable") != (version == "4.0.0"):
        raise ReleaseSupplyChainError(
            "publication-version", "release channel and coordinate disagree"
        )
    contracts = {item["id"]: item for item in manifest["artifacts"]}
    subjects = {item["id"]: item for item in evidence["artifacts"]}
    approved = authorization["destinations"]
    ids = [item["artifact_id"] for item in approved]
    if len(ids) != len(set(ids)):
        raise ReleaseSupplyChainError(
            "publication-destination", "duplicate authorized destination"
        )
    for item in approved:
        contract = contracts.get(item["artifact_id"])
        row = subjects.get(item["artifact_id"])
        if contract is None or row is None:
            raise ReleaseSupplyChainError(
                "publication-destination", "unknown destination"
            )
        distribution = contract["distribution_contract"]
        if (
            item["artifact_id"] in {"release:java", "release:kotlin"}
            and re.fullmatch(r"[A-F0-9]{40}", item.get("signing_key_fingerprint", ""))
            is None
        ):
            raise ReleaseSupplyChainError(
                "publication-signing",
                "an exact owner-approved PGP signing fingerprint is required",
            )
        if item["artifact_id"] == "release:lua" and (
            type(item.get("registry_user_id")) is not int
            or item["registry_user_id"] <= 0
        ):
            raise ReleaseSupplyChainError(
                "publication-destination",
                "LuaRocks requires the exact owner-approved numeric uploader identity",
            )
        if item["artifact_id"] == "release:cpp":
            endpoint = urllib.parse.urlparse(item.get("registry_endpoint", ""))
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise ReleaseSupplyChainError(
                    "publication-destination",
                    "Conan requires an owner-approved HTTPS registry endpoint without embedded credentials",
                )
        if distribution["ownership_status"] == "verified" and distribution[
            "registry_owner"
        ].startswith("existing "):
            raise ReleaseSupplyChainError(
                "publication-destination",
                "pending registry owner placeholders cannot be verified owners",
            )
        if item["artifact_id"] == "release:dart" and event != "push":
            raise ReleaseSupplyChainError(
                "publication-context",
                "pub.dev trusted publishing requires a protected version-tag push",
            )
        if (
            item["registry"] != contract["registry"]
            or item["package_name"] != contract["package_name"]
            or item["registry_owner"] != distribution["registry_owner"]
            or item["tier"] != distribution["tier"]
            or distribution["ownership_status"] != "verified"
            or distribution["tier"] == "Legacy"
            or (
                distribution["tier"] == "Preview"
                and item.get("preview_acknowledged") is not True
            )
            or row["status"] != "passed"
            or row["subject"]["sha256"] != item["subject_sha256"]
        ):
            raise ReleaseSupplyChainError(
                "publication-destination",
                "wrong registry, owner, support classification, or artifact identity",
            )
    return {
        "status": "passed",
        "publication_authorized": True,
        "authorization_sha256": expected_sha256,
        "destinations": ids,
    }


def certified_subject_checksums(
    *,
    root: Path,
    trust_root: Path,
    certification_root: Path,
    certification_bundle: Path,
    evidence_path: Path,
    output: Path,
) -> dict:
    """Export metadata-only attestation subjects after isolated signed verification."""
    if output.exists():
        raise ReleaseSupplyChainError(
            "output-exists", "attestation subject list already exists"
        )
    checked = subprocess.run(
        [
            sys.executable,
            "-I",
            str(trust_root / "tooling/local_certification_attestation.py"),
            "--repository-root",
            str(certification_root),
            "--trust-root",
            str(trust_root),
            "--trust-policy",
            "release-certification-trust.json",
            "verify",
            "--bundle",
            str(certification_bundle),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if checked.returncode:
        raise ReleaseSupplyChainError(
            "publication-certification",
            "independent signed Release verification failed",
        )
    result = json.loads(checked.stdout)
    if result.get("status") != "passed":
        raise ReleaseSupplyChainError(
            "publication-certification", "independent verifier did not pass"
        )
    signed = load_json(certification_bundle / "attestation.json")["signed_payload"]
    if not any(
        row["role"] == "release-supply-chain"
        and row["sha256"] == _sha256_file(evidence_path)
        for row in signed["evidence_files"]
    ):
        raise ReleaseSupplyChainError(
            "publication-certification",
            "artifact evidence is outside the signed Release root",
        )
    manifest = load_json(root / MANIFEST_PATH.relative_to(ROOT))
    evidence = verify_bundle(
        root=root, evidence_path=evidence_path, manifest=manifest, verify_subjects=False
    )
    if (
        evidence["profile"] != "release"
        or evidence["evidence_authority"] != "live-dry-run"
        or evidence["status"] != "passed"
        or evidence["source"]["commit"]
        != result["checks"][0]["evidence"]["certified_source_sha"]
    ):
        raise ReleaseSupplyChainError(
            "publication-certification",
            "attestation subjects differ from the signed certified source",
        )
    text = "".join(
        row["subject"]["sha256"] + "  " + row["id"].replace(":", "-") + "\n"
        for row in evidence["artifacts"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")
    return {
        "status": "passed",
        "subjects": len(evidence["artifacts"]),
        "publication_authorized": False,
    }


def verify_publication_handoff(
    *,
    root: Path,
    trust_root: Path,
    certification_bundle: Path,
    evidence_path: Path,
    authorization_path: Path,
    artifact_id: str,
    download_root: Path | None = None,
    certification_root: Path | None = None,
) -> dict[str, Any]:
    """Reverify signed certification and exact restored subject before upload."""
    manifest = load_json(root / MANIFEST_PATH.relative_to(ROOT))
    evidence = verify_bundle(
        root=root, evidence_path=evidence_path, manifest=manifest, verify_subjects=False
    )
    authorization = load_json(authorization_path)
    product = load_json(root / "governance/release-policy.json")["product"]
    if authorization.get("version") != product["version"]:
        raise ReleaseSupplyChainError(
            "publication-version",
            "authorization differs from product-version authority",
        )
    checked = subprocess.run(
        [
            sys.executable,
            "-I",
            str(trust_root / "tooling/local_certification_attestation.py"),
            "--repository-root",
            str(certification_root or root),
            "--trust-root",
            str(trust_root),
            "--trust-policy",
            "release-certification-trust.json",
            "verify",
            "--bundle",
            str(certification_bundle),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if checked.returncode:
        raise ReleaseSupplyChainError(
            "publication-certification", "trusted signed Release verification failed"
        )
    result = json.loads(checked.stdout)
    if result.get("status") != "passed":
        raise ReleaseSupplyChainError(
            "publication-certification", "trusted verifier did not pass"
        )
    certified = result["checks"][0]["evidence"]
    attestation = load_json(certification_bundle / "attestation.json")["signed_payload"]
    if not any(
        item["sha256"] == _sha256_file(evidence_path)
        and item["role"] == "release-supply-chain"
        for item in attestation["evidence_files"]
    ):
        raise ReleaseSupplyChainError(
            "publication-certification",
            "artifact evidence is absent from the signed Release root",
        )
    context = {
        field: os.environ.get(env, "")
        for field, env in {
            "event_name": "GITHUB_EVENT_NAME",
            "repository": "GITHUB_REPOSITORY",
            "ref": "GITHUB_REF",
            "workflow_sha": "GITHUB_WORKFLOW_SHA",
            "reviewed_workflow_sha": "RELEASE_APPROVED_WORKFLOW_SHA",
            "run_id": "GITHUB_RUN_ID",
            "run_attempt": "GITHUB_RUN_ATTEMPT",
            "environment": "RELEASE_ENVIRONMENT",
            "dry_run": "RELEASE_DRY_RUN",
            "artifact_run_id": "RELEASE_CERTIFIED_RUN_ID",
            "certification_ref": "RELEASE_CERTIFICATION_REF",
        }.items()
    }
    if (
        certification_root is None
        or _git_output(certification_root, ["rev-parse", "HEAD"]).decode().strip()
        != context["certification_ref"]
    ):
        raise ReleaseSupplyChainError(
            "publication-context",
            "signed evidence closure is not the exact owner-approved commit",
        )
    approval = verify_publication_authorization(
        authorization=authorization,
        expected_sha256=os.environ.get("RELEASE_AUTHORIZATION_SHA256", ""),
        evidence=evidence,
        manifest=manifest,
        context=context,
        certified_source_sha=certified["certified_source_sha"],
        certified_evidence_root=certified["evidence_root_sha256"],
    )
    if (
        _git_output(ROOT, ["rev-parse", "HEAD"]).decode().strip()
        != context["reviewed_workflow_sha"]
    ):
        raise ReleaseSupplyChainError(
            "publication-context",
            "publisher code is not the approved immutable checkout",
        )
    if artifact_id not in approval["destinations"]:
        raise ReleaseSupplyChainError(
            "publication-destination", "this artifact is not authorized"
        )
    artifact = next(item for item in manifest["artifacts"] if item["id"] == artifact_id)
    row = next(item for item in evidence["artifacts"] if item["id"] == artifact_id)
    if (
        download_root is not None
        and artifact["artifact_policy"]["subject_kind"] != "source-tree"
    ):
        restore_certified_subject(
            root=root,
            download_root=download_root,
            checksum_path=evidence_path.parent
            / "checksums"
            / (artifact["surface"] + ".sha256"),
            artifact=artifact,
            version=authorization["version"],
        )
    members = _surface_members(root, artifact, authorization["version"])
    name, digest, size = _surface_identity(members)
    if (name, digest, size) != (
        row["subject"]["name"],
        row["subject"]["sha256"],
        row["subject"]["bytes"],
    ):
        raise ReleaseSupplyChainError(
            "publication-substitution",
            "restored artifact differs from the exact certified subject",
        )
    return {
        **approval,
        "artifact_id": artifact_id,
        "subject_sha256": digest,
        "source_sha": authorization["source_sha"],
    }


def restore_certified_subject(
    *,
    root: Path,
    download_root: Path,
    checksum_path: Path,
    artifact: Mapping[str, Any],
    version: str,
) -> None:
    """Restore an approved upload's files at their original governed paths."""
    entries = []
    patterns = [
        pattern.replace("VERSION", version)
        for pattern in artifact["artifact_policy"]["patterns"]
    ]
    for line in checksum_path.read_text(encoding="utf-8").splitlines()[1:]:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ReleaseSupplyChainError(
                "publication-restore", "malformed certified checksum entry"
            )
        digest, name = match.groups()
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ".git" in path.parts
            or "\\" in name
            or not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        ):
            raise ReleaseSupplyChainError(
                "publication-restore",
                "subject is outside its governed archive patterns",
            )
        entries.append((path, digest))
    directory_subject = (
        artifact["artifact_policy"]["subject_kind"] == "registry-assembled"
    )
    if directory_subject:
        if (
            len(patterns) != 1
            or len(entries) != 1
            or entries[0][0].as_posix() != patterns[0]
        ):
            raise ReleaseSupplyChainError(
                "publication-restore", "unsupported assembled directory layout"
            )
        sbom = load_json(
            checksum_path.parent.parent / "sbom" / (artifact["surface"] + ".spdx.json")
        )
        entries = []
        for row in sbom["files"]:
            name = row["fileName"]
            path = Path(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or ".git" in path.parts
                or "\\" in name
                or not name.startswith(patterns[0] + "/")
                or len(row["checksums"]) != 2
                or row["checksums"][0]["algorithm"] != "SHA256"
                or row["checksums"][1]["algorithm"] != "SHA1"
                or re.fullmatch(
                    r"[0-9a-f]{64}", str(row["checksums"][0].get("checksumValue", ""))
                )
                is None
                or re.fullmatch(
                    r"[0-9a-f]{40}", str(row["checksums"][1].get("checksumValue", ""))
                )
                is None
            ):
                raise ReleaseSupplyChainError(
                    "publication-restore", "assembled SBOM has an unsafe file identity"
                )
            entries.append((path, row["checksums"][0]["checksumValue"]))
    if not entries or len(entries) != len({path for path, _ in entries}):
        raise ReleaseSupplyChainError(
            "publication-restore", "missing or duplicate certified subject"
        )
    upload_root = (
        Path(patterns[0])
        if directory_subject
        else Path(os.path.commonpath([str(path.parent) for path, _ in entries]))
    )
    planned = []
    for path, digest in entries:
        source, target = download_root / path.relative_to(upload_root), root / path
        if (
            source.is_symlink()
            or target.is_symlink()
            or not source.resolve().is_relative_to(download_root.resolve())
            or not target.resolve().is_relative_to(root.resolve())
            or not source.is_file()
            or _sha256_file(source) != digest
        ):
            raise ReleaseSupplyChainError(
                "publication-substitution",
                "downloaded subject does not match its certified checksum",
            )
        planned.append((source, target))
    for source, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def run_governed_security_evidence(*, root: Path, risk_output: Path) -> dict[str, Any]:
    from tooling import security

    try:
        policy = security.load_policy(
            root / SECURITY_POLICY_PATH.relative_to(ROOT),
            root / "governance/schemas/security-policy.schema.json",
        )
        engine = security.SecurityEngine(root, policy)
        operations = {
            "integrity": engine.run_integrity(),
            "content": engine.run_content(),
            "risk": engine.run_risk(),
        }
    except security.SecurityConfigurationError as error:
        raise ReleaseSupplyChainError("security-evidence", str(error)) from error
    documents = {name: operation.as_dict() for name, operation in operations.items()}
    _write_json(risk_output, documents["risk"])
    statuses = {name: operation.status for name, operation in operations.items()}
    blocking = {
        name: status
        for name, status in statuses.items()
        if status in security.BLOCKING_STATUSES
    }
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.release-supply-chain-security-evidence",
        "profile": "release",
        "status": "failed" if blocking else "passed",
        "publication_authorized": False,
        "security_statuses": statuses,
        "risk_evidence": risk_output.as_posix(),
        "risk_evidence_sha256": hashlib.sha256(risk_output.read_bytes()).hexdigest(),
    }


def run_live_producer(
    *,
    root: Path = ROOT,
    profile: str,
    version: str,
    second_root: Path,
    output_dir: Path,
    risk_evidence_path: Path,
    build_receipt_dir: Path | None = None,
) -> dict[str, Any]:
    manifest_path = root / MANIFEST_PATH.relative_to(ROOT)
    manifest = validate_manifest(load_json(manifest_path), root=root)
    if build_receipt_dir is None:
        raise ReleaseSupplyChainError(
            "build-receipt",
            "live multi-platform certification requires authenticated build receipts",
        )
    toolchains, source, rebuild_source, captured = load_build_receipts(
        receipt_dir=build_receipt_dir,
        root=root,
        second_root=second_root,
        manifest=manifest,
        version=version,
    )
    return produce_bundle(
        root=root,
        second_root=second_root,
        output_dir=output_dir,
        version=version,
        profile=profile,
        manifest=manifest,
        source=source,
        workflow=qualify_workflow(root, manifest),
        toolchains=toolchains,
        evidence_authority="live-dry-run",
        risk_evidence=load_json(risk_evidence_path),
        rebuild_source=rebuild_source,
        build_receipts=captured,
    )


def run_contract_check() -> dict[str, Any]:
    manifest = validate_manifest(load_json(MANIFEST_PATH))
    fixture = validate_contract_fixture(load_json(VALID_FIXTURE_PATH), manifest)
    validate_evidence(synthetic_evidence(manifest), manifest)
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.release-supply-chain-contract",
        "profile": "contract",
        "status": "passed",
        "publication_authorized": False,
        "manifest_fingerprint": document_fingerprint(manifest),
        "fixture_fingerprint": fixture["evidence_fingerprint"],
        "artifact_count": len(ARTIFACT_IDS),
        "standards": manifest["standards"],
    }


def write_contract_fixture() -> None:
    """Renew only the explicitly synthetic fixture's input identity."""
    fixture = load_json(VALID_FIXTURE_PATH)
    fixture["manifest_fingerprint"] = document_fingerprint(load_json(MANIFEST_PATH))
    fixture["evidence_fingerprint"] = document_fingerprint(
        fixture, "evidence_fingerprint"
    )
    validate_contract_fixture(fixture, load_json(MANIFEST_PATH))
    _write_json(VALID_FIXTURE_PATH, fixture)


def release_trust_document() -> dict[str, Any]:
    trust = load_json(ROOT / "governance/local-certification-trust.json")
    trust["bundle_path"] = "tests/certification/release-packaging/1.0/current"
    trust["closure_paths"] = [
        "tests/certification/release-packaging/1.0/current/**",
        "docs/migration/release-packaging-rebuild.md",
        "docs/migration/records/release-packaging-rebuild.yaml",
        "docs/migration/ledger.md",
        "governance/change-control.json",
    ]
    return trust


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Produce and validate STRling release supply-chain evidence."
    )
    parser.add_argument(
        "command",
        choices=[
            "capture",
            "prepare-upload",
            "prepare-certified-upload",
            "certified-checksums",
            "restore-upload",
            "handoff",
            "write-contract-fixture",
            "write-release-trust",
            "check-release-trust",
            "check",
            "produce",
            "profile",
            "security",
            "stage",
            "verify",
        ],
    )
    parser.add_argument(
        "--profile", choices=["local", "pull-request", "full", "release"]
    )
    parser.add_argument("--version")
    parser.add_argument("--second-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--risk-evidence", type=Path)
    parser.add_argument("--artifact-id")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--build-receipt-dir", type=Path)
    parser.add_argument("--download-root", type=Path)
    parser.add_argument("--first-root", type=Path)
    parser.add_argument("--release-ref")
    parser.add_argument("--trust-root", type=Path)
    parser.add_argument("--certification-bundle", type=Path)
    parser.add_argument("--certification-root", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command in {"write-release-trust", "check-release-trust"}:
            document = release_trust_document()
            path = ROOT / "governance/release-certification-trust.json"
            if args.command == "write-release-trust":
                _write_json(path, document)
            elif not path.is_file() or load_json(path) != document:
                raise ReleaseSupplyChainError(
                    "release-trust", "release trust projection is stale"
                )
            result = {"status": "passed", "publication_authorized": False}
        elif args.command == "handoff":
            if not all(
                (
                    args.trust_root,
                    args.certification_bundle,
                    args.evidence,
                    args.authorization,
                    args.artifact_id,
                )
            ):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "handoff requires trust root, signed certification, evidence, authorization, and artifact ID",
                )
            result = verify_publication_handoff(
                root=(args.source_root or ROOT).resolve(),
                trust_root=args.trust_root.resolve(),
                certification_bundle=args.certification_bundle.resolve(),
                evidence_path=args.evidence.resolve(),
                authorization_path=args.authorization.resolve(),
                artifact_id=args.artifact_id,
                certification_root=args.certification_root.resolve()
                if args.certification_root
                else None,
                download_root=args.download_root.resolve()
                if args.download_root
                else None,
            )
            if args.output_dir:
                if args.output_dir.exists():
                    raise ReleaseSupplyChainError(
                        "output-exists", "handoff intent receipt already exists"
                    )
                _write_json(
                    args.output_dir,
                    {**result, "status": "handoff-verified-upload-not-observed"},
                )
        elif args.command == "write-contract-fixture":
            write_contract_fixture()
            result = run_contract_check()
        elif args.command == "certified-checksums":
            if not all(
                (
                    args.evidence,
                    args.output_dir,
                    args.certification_root,
                    args.certification_bundle,
                    args.trust_root,
                )
            ):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "signed subject export requires source, trust, closure, bundle, evidence, and output",
                )
            result = certified_subject_checksums(
                root=(args.source_root or ROOT).resolve(),
                trust_root=args.trust_root.resolve(),
                certification_root=args.certification_root.resolve(),
                certification_bundle=args.certification_bundle.resolve(),
                evidence_path=args.evidence.resolve(),
                output=args.output_dir.resolve(),
            )
        elif args.command == "prepare-certified-upload":
            if not all((args.evidence, args.output_dir, args.artifact_id)):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "certified export requires evidence, artifact ID, and output directory",
                )
            source_root = (args.source_root or ROOT).resolve()
            manifest = load_json(source_root / MANIFEST_PATH.relative_to(ROOT))
            result = prepare_certified_upload(
                root=source_root,
                evidence_path=args.evidence.resolve(),
                output=args.output_dir.resolve(),
                artifact_id=args.artifact_id,
                manifest=manifest,
            )
        elif args.command in {"prepare-upload", "restore-upload"}:
            if args.receipt is None:
                raise ReleaseSupplyChainError(
                    "arguments", "upload transport requires a captured receipt"
                )
            source_root = (args.source_root or ROOT).resolve()
            manifest = validate_manifest(
                load_json(source_root / MANIFEST_PATH.relative_to(ROOT)),
                root=source_root,
            )
            if args.command == "prepare-upload":
                if args.output_dir is None:
                    raise ReleaseSupplyChainError(
                        "arguments", "upload preparation requires an output directory"
                    )
                result = prepare_artifact_upload(
                    root=source_root,
                    receipt_path=args.receipt.resolve(),
                    output=args.output_dir.resolve(),
                    manifest=manifest,
                )
            else:
                if args.download_root is None:
                    raise ReleaseSupplyChainError(
                        "arguments", "upload restoration requires a download directory"
                    )
                receipt = load_json(args.receipt.resolve())
                artifact = next(
                    (
                        row
                        for row in _artifact_rows(manifest)
                        if row["id"] == receipt.get("artifact_id")
                    ),
                    None,
                )
                if artifact is None:
                    raise ReleaseSupplyChainError(
                        "build-receipt", "unknown restored artifact"
                    )
                _validate_build_receipt(
                    receipt,
                    root=source_root,
                    artifact=artifact,
                    version=load_json(source_root / "governance/release-policy.json")[
                        "product"
                    ]["version"],
                    manifest=manifest,
                    require_passed_toolchains=True,
                    expected_source=authenticate_source(source_root),
                    verify_subjects=False,
                )
                count = restore_artifact_upload(
                    artifact_root=args.download_root.resolve(),
                    target_root=source_root,
                    receipt=receipt,
                )
                result = {
                    "status": "passed",
                    "staged_files": count,
                    "publication_authorized": False,
                }
        elif args.command == "capture":
            if not all((args.artifact_id, args.version, args.output_dir)):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "capture requires --artifact-id, --version, and --output-dir",
                )
            source_root = (args.source_root or ROOT).resolve()
            receipt = capture_build_receipt(
                root=source_root,
                artifact_id=args.artifact_id,
                version=args.version,
                output_path=args.output_dir.resolve(),
                manifest=load_json(source_root / MANIFEST_PATH.relative_to(ROOT)),
            )
            result = {
                "schema_version": "certification-result-v1",
                "operation_id": "certification.release-build-capture",
                "profile": "full",
                "status": (
                    "passed"
                    if all(row["status"] == "passed" for row in receipt["toolchains"])
                    else "incomplete"
                ),
                "publication_authorized": False,
                "receipt_fingerprint": receipt["receipt_fingerprint"],
            }
        elif args.command == "check":
            result = run_contract_check()
        elif args.command == "profile":
            if args.profile is None:
                raise ReleaseSupplyChainError("arguments", "profile requires --profile")
            environment_evidence = os.environ.get(
                "STRLING_RELEASE_SUPPLY_CHAIN_EVIDENCE"
            )
            evidence_path = args.evidence or (
                Path(environment_evidence) if environment_evidence else None
            )
            result = run_profile_certification(
                profile=args.profile,
                evidence_path=(evidence_path.resolve() if evidence_path else None),
                root=(args.source_root or ROOT).resolve(),
            )
        elif args.command == "security":
            if args.risk_evidence is None:
                raise ReleaseSupplyChainError(
                    "arguments", "security requires --risk-evidence"
                )
            result = run_governed_security_evidence(
                root=(args.source_root or ROOT).resolve(),
                risk_output=args.risk_evidence.resolve(),
            )
        elif args.command == "stage":
            if not all(
                (
                    args.download_root,
                    args.build_receipt_dir,
                    args.first_root,
                    args.second_root,
                    args.release_ref,
                )
            ):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "stage requires --download-root, --build-receipt-dir, --first-root, --second-root, and --release-ref",
                )
            source_root = (args.source_root or ROOT).resolve()
            result = stage_downloaded_artifacts(
                download_root=args.download_root.resolve(),
                receipt_dir=args.build_receipt_dir.resolve(),
                first_root=args.first_root.resolve(),
                second_root=args.second_root.resolve(),
                release_ref=args.release_ref,
                manifest=load_json(source_root / MANIFEST_PATH.relative_to(ROOT)),
            )
        elif args.command == "produce":
            if not all(
                (
                    args.profile,
                    args.version,
                    args.second_root,
                    args.output_dir,
                    args.risk_evidence,
                )
            ):
                raise ReleaseSupplyChainError(
                    "arguments",
                    "produce requires --profile, --version, --second-root, --output-dir, and --risk-evidence",
                )
            evidence = run_live_producer(
                root=(args.source_root or ROOT).resolve(),
                profile=args.profile,
                version=args.version,
                second_root=args.second_root.resolve(),
                output_dir=args.output_dir.resolve(),
                risk_evidence_path=args.risk_evidence.resolve(),
                build_receipt_dir=(
                    args.build_receipt_dir.resolve()
                    if args.build_receipt_dir is not None
                    else None
                ),
            )
            result = {
                "schema_version": "certification-result-v1",
                "operation_id": "certification.release-supply-chain",
                "profile": args.profile,
                "status": evidence["status"],
                "publication_authorized": False,
                "evidence_fingerprint": evidence["evidence_fingerprint"],
                "summary": evidence["summary"],
            }
        else:
            if args.evidence is None:
                raise ReleaseSupplyChainError("arguments", "verify requires --evidence")
            evidence = verify_bundle(
                root=(args.source_root or ROOT).resolve(),
                evidence_path=args.evidence.resolve(),
                manifest=load_json(MANIFEST_PATH),
            )
            result = {
                "schema_version": "certification-result-v1",
                "operation_id": "certification.release-supply-chain",
                "profile": evidence["profile"],
                "status": evidence["status"],
                "publication_authorized": False,
                "evidence_fingerprint": evidence["evidence_fingerprint"],
                "summary": evidence["summary"],
            }
    except ReleaseSupplyChainError as error:
        operation_id = (
            "certification.release-supply-chain-profile"
            if args.command == "profile"
            else "certification.release-supply-chain"
        )
        result = {
            "schema_version": "certification-result-v1",
            "operation_id": operation_id,
            "profile": getattr(args, "profile", None) or "contract",
            "status": "failed",
            "publication_authorized": False,
            "error": {"code": error.code, "message": str(error)},
        }
        if args.json:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        else:
            print(f"release supply-chain contract failed: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"release supply-chain {args.command}: {result['status']}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
