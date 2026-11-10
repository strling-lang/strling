"""Independent public-distribution obligations and evidence reduction.

Release policy and the supply-chain manifest retain identity and scope authority.
Neither registry data nor a publication receipt supplies trusted expectations.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import tarfile
import zipfile
from pathlib import Path

from tooling.public_retrieval import RetrievalError
from tooling.release_payload import archive_files
from tooling.release_supply_chain import canonical_json

CONTRACT = "strling-public-distribution-v1"
STATUSES = {
    "NOT_PUBLISHED",
    "READY",
    "VERIFYING",
    "VERIFIED",
    "FAILED",
    "INDETERMINATE",
}
CHECKS = (
    "coordinate",
    "metadata",
    "artifact",
    "source",
    "sbom",
    "provenance",
    "documentation",
    "scope",
)
CONSUMER_CHECKS = (
    "installation",
    "public-api",
    "product-version",
    "canonical-compiler",
    "native-wasm",
    "target-compatibility",
    "kernel-rejection",
    "isolation",
)


def validate_contract(root: Path) -> dict:
    from jsonschema import Draft202012Validator
    from tooling.release_supply_chain import load_json, validate_manifest

    contract = load_json(root / "governance/public-distribution.json")
    schema = load_json(root / "governance/schemas/public-distribution.schema.json")
    Draft202012Validator(schema).validate(contract)
    manifest = validate_manifest(
        load_json(root / contract["artifact_authority"]), root=root
    )
    required = {
        "github-tag" if row["registry"].startswith("github-tag:") else row["registry"]
        for row in manifest["artifacts"]
    }
    if set(contract["routes"]) != required:
        raise RetrievalError(
            "contract", "public adapters differ from the distribution registry"
        )
    supported = {
        row["id"]: row
        for row in manifest["artifacts"]
        if row["distribution_contract"]["tier"] == "Supported"
    }
    if set(contract["consumer_toolchains"]) != set(supported) or any(
        not set(tools).issubset(supported[identity]["toolchain_refs"])
        for identity, tools in contract["consumer_toolchains"].items()
    ):
        raise RetrievalError(
            "contract", "consumer runtime prerequisites differ from governed toolchains"
        )
    policy = load_json(root / contract["identity_authority"])
    if policy["post_publication_verification"]["independent_public_fetch"] is not True:
        raise RetrievalError(
            "contract", "public verification requires independent retrieval"
        )
    return {
        "contract": CONTRACT,
        "artifacts": len(manifest["artifacts"]),
        "obligations": obligations(manifest),
        "publication_authorized": False,
    }


def exact_rows(rows: list[dict], key: str, expected: set[str]) -> dict[str, dict]:
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or key not in row for row in rows
    ):
        raise RetrievalError("contract", "malformed obligation inventory")
    ids = [row[key] for row in rows]
    if (
        any(not isinstance(value, str) for value in ids)
        or len(ids) != len(set(ids))
        or set(ids) != expected
    ):
        raise RetrievalError(
            "contract", "missing, duplicate, or unexpected obligations"
        )
    return dict(zip(ids, rows))


def obligations(manifest: dict) -> list[dict]:
    """Derive every artifact and supported consumer row; never a fixed count."""
    artifacts = manifest["artifacts"]
    exact_rows(artifacts, "id", {row["id"] for row in artifacts})
    result = []
    for artifact in artifacts:
        distribution = artifact["distribution_contract"]
        platforms = distribution["platforms"]
        if len(platforms) != len(set(platforms)) or (
            distribution["tier"] == "Supported"
            and set(platforms) != set(artifact["build_platforms"])
        ):
            raise RetrievalError(
                "contract", "platform obligations disagree with assembly scope"
            )
        if distribution["tier"] not in {"Supported", "Preview"}:
            raise RetrievalError("contract", "unregistered public distribution tier")
        for check in CHECKS:
            result.append(
                {
                    "id": artifact["id"] + ":" + check,
                    "artifact_id": artifact["id"],
                    "check": check,
                    "platform": None,
                    "tier": distribution["tier"],
                }
            )
        if distribution["tier"] == "Supported":
            for platform in platforms:
                for check in CONSUMER_CHECKS:
                    result.append(
                        {
                            "id": artifact["id"] + ":" + platform + ":" + check,
                            "artifact_id": artifact["id"],
                            "check": check,
                            "platform": platform,
                            "tier": "Supported",
                        }
                    )
    return result


def reduce_observations(manifest: dict, rows: list[dict], *, authority: str) -> dict:
    """Synthetic success establishes READY only; partial publication is explicit."""
    if authority not in {"public", "synthetic", "staged"}:
        raise RetrievalError("contract", "unknown observation authority")
    required = {row["id"]: row for row in obligations(manifest)}
    observed = exact_rows(rows, "id", set(required))
    states = []
    for identity, row in observed.items():
        if any(row.get(key) != value for key, value in required[identity].items()):
            raise RetrievalError("contract", "observation changed the required scope")
        state = row.get("status")
        if state not in STATUSES or row.get("authority") != authority:
            raise RetrievalError("contract", "invalid observation status or authority")
        if state == "VERIFIED" and (
            authority != "public"
            or not row.get("retrieval_sha256")
            or not re.fullmatch(r"[0-9a-f]{64}", row["retrieval_sha256"])
        ):
            raise RetrievalError(
                "authority", "public success requires retained public retrieval"
            )
        if authority == "public" and state == "READY":
            raise RetrievalError(
                "authority", "engineering readiness cannot satisfy public execution"
            )
        states.append(state)
    if "FAILED" in states:
        status = "FAILED"
    elif "INDETERMINATE" in states or "VERIFYING" in states:
        status = "INDETERMINATE"
    elif "NOT_PUBLISHED" in states:
        status = "NOT_PUBLISHED"
    elif authority == "public" and set(states) == {"VERIFIED"}:
        status = "VERIFIED"
    elif authority != "public" and set(states) == {"READY"}:
        status = "READY"
    else:
        raise RetrievalError("authority", "inconsistent aggregate observations")
    return {
        "contract": CONTRACT,
        "authority": authority,
        "status": status,
        "required": len(required),
        "counts": {value: states.count(value) for value in sorted(STATUSES)},
        "partial_publication": authority == "public"
        and "NOT_PUBLISHED" in states
        and "VERIFIED" in states,
        "release_transition": "verified" if status == "VERIFIED" else None,
        "publication_authorized": False,
        "registry_mutation_authorized": False,
        "observations_sha256": hashlib.sha256(canonical_json(rows)).hexdigest(),
    }


def certified_file_graph(sbom: dict, subject: str) -> dict[str, str]:
    prefix = subject + "!/"
    result = {}
    for row in sbom["files"]:
        if not row["fileName"].startswith(prefix):
            continue
        name = row["fileName"][len(prefix) :]
        hashes = [
            item["checksumValue"]
            for item in row["checksums"]
            if item["algorithm"] == "SHA256"
        ]
        if (
            len(hashes) != 1
            or name in result
            or not re.fullmatch(r"[0-9a-f]{64}", hashes[0])
        ):
            raise RetrievalError("sbom", "ambiguous certified inner file graph")
        result[name] = hashes[0]
    if not result:
        raise RetrievalError("sbom", "certified archive has no inner file graph")
    return result


def authenticate_archive(
    payload: bytes,
    *,
    subject: str,
    expected_sha256: str,
    artifact: dict,
    sbom: dict,
    certified_payload: bytes | None = None,
) -> dict:
    """No extraction or execution; normalization never permits changed members."""
    observed = hashlib.sha256(payload).hexdigest()
    try:
        files = archive_files(io.BytesIO(payload))
    except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise RetrievalError("artifact-integrity", "unsafe public archive") from error
    if artifact.get("id") == "release:ruby" and "data.tar.gz" in files:
        nested = archive_files(io.BytesIO(files["data.tar.gz"]))
        files.update({"data.tar.gz!/" + name: value for name, value in nested.items()})
    expected = certified_file_graph(sbom, subject)
    actual = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if actual != expected:
        raise RetrievalError(
            "artifact-integrity",
            "public inner file graph differs from certified subject",
            expected=expected,
            observed=actual,
        )
    mode = artifact["reproducibility"]["mode"]
    if observed != expected_sha256:
        allowed = artifact["reproducibility"]["allowed_normalizations"]
        if mode != "normalized" or "archive-entry-timestamp" not in allowed:
            raise RetrievalError(
                "artifact-integrity",
                "public archive checksum differs from certified subject",
            )
        if (
            certified_payload is None
            or hashlib.sha256(certified_payload).hexdigest() != expected_sha256
        ):
            raise RetrievalError(
                "artifact-integrity",
                "registered normalization requires an authenticated certified exemplar",
            )
        from tooling.release_supply_chain import _normalized_file_sha256

        if subject.lower().endswith((".zip", ".jar", ".nupkg", ".whl")):
            with (
                zipfile.ZipFile(io.BytesIO(payload)) as public_archive,
                zipfile.ZipFile(io.BytesIO(certified_payload)) as certified_archive,
            ):
                if public_archive.comment != certified_archive.comment:
                    raise RetrievalError(
                        "artifact-integrity",
                        "archive comments are not a registered normalization",
                    )

        # Reuse the registered comparison, including modes and archive metadata;
        # equal inner bytes alone do not authorize broader normalization.
        with tempfile.TemporaryDirectory(prefix="strling-public-compare-") as temporary:
            first = Path(temporary) / "certified" / Path(subject).name
            second = Path(temporary) / "public" / Path(subject).name
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(certified_payload)
            second.write_bytes(payload)
            if _normalized_file_sha256(first, allowed) != _normalized_file_sha256(
                second, allowed
            ):
                raise RetrievalError(
                    "artifact-integrity",
                    "public archive exceeds registered normalization",
                )
    return {
        "sha256": observed,
        "certified_sha256": expected_sha256,
        "comparison": "byte-for-byte" if observed == expected_sha256 else "normalized",
        "files": len(actual),
    }


def authenticate_source_archive(
    payload: bytes,
    *,
    source_sha: str,
    expected_tree: str,
    observed_tree: str,
    sbom: dict,
    artifact: dict,
) -> dict[str, bytes]:
    if observed_tree != expected_tree or not re.fullmatch(
        r"[0-9a-f]{40}", expected_tree
    ):
        raise RetrievalError(
            "source-identity",
            "public Git tree differs from the signed source tree",
            expected=expected_tree,
            observed=observed_tree,
        )
    files = archive_files(io.BytesIO(payload))
    prefix = "strling-" + source_sha + "/"
    if any(not name.startswith(prefix) for name in files):
        raise RetrievalError("source-identity", "unexpected Git archive root")
    files = {name[len(prefix) :]: value for name, value in files.items()}
    expected = {}
    for row in sbom["files"]:
        hashes = [
            value["checksumValue"]
            for value in row["checksums"]
            if value["algorithm"] == "SHA256"
        ]
        if len(hashes) != 1 or row["fileName"] in expected:
            raise RetrievalError("sbom", "ambiguous source file graph")
        expected[row["fileName"]] = hashes[0]
    roots = artifact["artifact_policy"]["patterns"]
    selected = {
        name: value
        for name, value in files.items()
        if any(name == root or name.startswith(root + "/") for root in roots)
    }
    if (
        not expected
        or {name: hashlib.sha256(value).hexdigest() for name, value in selected.items()}
        != expected
    ):
        raise RetrievalError(
            "source-identity",
            "public source files differ from the complete certified file graph",
        )
    return selected


def authenticate_assembled_archive(
    payload: bytes, *, subject: str, sbom: dict
) -> dict[str, bytes]:
    """Pub's wrapper may vary; every source member must remain exact."""
    files = archive_files(io.BytesIO(payload))
    prefix = subject.rstrip("/") + "/"
    expected = {}
    for row in sbom["files"]:
        if not row["fileName"].startswith(prefix):
            raise RetrievalError(
                "sbom", "assembled package contains an unrelated signed subject"
            )
        values = [
            item["checksumValue"]
            for item in row["checksums"]
            if item["algorithm"] == "SHA256"
        ]
        name = row["fileName"][len(prefix) :]
        if len(values) != 1 or name in expected:
            raise RetrievalError("sbom", "ambiguous assembled file graph")
        expected[name] = values[0]
    if (
        not expected
        or {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
        != expected
    ):
        raise RetrievalError(
            "artifact-integrity",
            "registry assembly differs from certified source members",
        )
    return files


def strict_json(payload: bytes) -> dict:
    def invalid_constant(value):
        raise RetrievalError("metadata", "nonfinite public metadata number: " + value)

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise RetrievalError("metadata", "duplicate public metadata key")
            result[key] = value
        return result

    try:
        result = json.loads(
            payload, object_pairs_hook=pairs, parse_constant=invalid_constant
        )
    except (ValueError, UnicodeError) as error:
        raise RetrievalError("metadata", "malformed public metadata") from error
    if not isinstance(result, dict):
        raise RetrievalError("metadata", "public metadata must be an object")
    return result


def contract_result(root: Path, *, commit: str, profile: str) -> dict:
    from tooling.public_metadata import verify_readme_commands
    from tooling.release_supply_chain import load_json

    result = validate_contract(root)
    manifest = load_json(
        root / "tests/certification/release-supply-chain/1.0/manifest.json"
    )
    version = load_json(root / "governance/release-policy.json")["product"]["version"]
    documentation = {}
    for artifact in manifest["artifacts"]:
        readme = (
            "bindings/rust/README.md"
            if artifact["id"] == "release:rust"
            else artifact["package_root"] + "/README.md"
        )
        documentation[artifact["id"]] = verify_readme_commands(
            (root / readme).read_bytes(), artifact, version
        )
    evidence = {
        "status": "passed",
        "contract": result["contract"],
        "artifacts": result["artifacts"],
        "obligations": len(result["obligations"]),
        "documentation": documentation,
        "public_release_verified": False,
        "checked": True,
    }
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.public-distribution-contract",
        "commit": commit,
        "profile": profile,
        "status": "passed",
        "duration_ms": None,
        "details": evidence,
        "evidence_fingerprint": hashlib.sha256(canonical_json(evidence)).hexdigest(),
    }


def main(argv=None) -> int:
    import argparse
    import subprocess
    from tooling.structured_operation_execution import (
        atomic_write_artifact,
        execution_context,
        zero_sample_consumption,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--profile", choices=("local",), default="local")
    parser.add_argument("--execution-directory", type=Path)
    parser.add_argument("--certification-invocation-id")
    parser.add_argument(
        "--certification-profile", choices=("local", "pull-request", "full", "release")
    )
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--producer-id")
    args = parser.parse_args(argv)
    values = (
        args.execution_directory,
        args.certification_invocation_id,
        args.certification_profile,
        args.expected_source_sha,
        args.producer_id,
    )
    if any(v is not None for v in values) and not all(v is not None for v in values):
        parser.error("invocation-bound execution arguments must be supplied together")
    root = Path(__file__).resolve().parents[1]

    def source():
        return subprocess.check_output(
            ["git", "--no-optional-locks", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            timeout=30,
        ).strip()

    def clean():
        return not subprocess.check_output(
            ["git", "--no-optional-locks", "status", "--porcelain"],
            cwd=root,
            timeout=120,
        ).strip()

    before = source()
    if args.execution_directory and (
        before != args.expected_source_sha
        or not clean()
        or args.producer_id != "public_distribution_contract@repository"
    ):
        raise ValueError("public contract source or producer does not match invocation")
    result = contract_result(root, commit=before, profile=args.profile)
    if source() != before or (args.execution_directory and not clean()):
        raise ValueError("source changed during public contract execution")
    if args.execution_directory:
        atomic_write_artifact(
            args.execution_directory / "result.json",
            {
                **execution_context(
                    producer_id=args.producer_id,
                    operation_id=result["operation_id"],
                    source_sha=before,
                    invocation_id=args.certification_invocation_id,
                    certification_profile=args.certification_profile,
                    producer_profile=args.profile,
                ),
                "artifact_kind": "structured-operation-result",
                "result_contract": result["schema_version"],
                "process_exit_code": 0,
                "terminal_status": result["status"],
                "environment_identity": None,
                "performance_evidence_identity": result["evidence_fingerprint"],
                "sample_consumption": zero_sample_consumption(),
                "structured_result": result,
                "integrity_error": None,
            },
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
