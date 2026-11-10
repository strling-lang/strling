"""Protected, read-only public retrieval and clean-consumer execution.

This entry point has no publication operation. Protected configuration selects
the verifier revision and approved request digest; dispatch inputs cannot do so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.public_authentication import authenticate_release, git
from tooling.public_distribution import (
    exact_rows,
    obligations,
    reduce_observations,
    strict_json,
)
from tooling.public_fixtures import materialize_exports
from tooling.public_retrieval import PublicTransport, RetrievalError
from tooling.public_verification import verify_artifact, write_retrieved
from tooling.public_verification_request import validate_request
from tooling.release_consumers import verify_retrieved_consumer
from tooling.release_packaging import host_scope
from tooling.release_payload import archive_files
from tooling.release_supply_chain import canonical_json, document_fingerprint, load_json

ROOT = Path(__file__).resolve().parents[1]


def protected_execution(root: Path = ROOT) -> dict:
    """No caller-selected trust and no execution from unreviewed source."""
    expected = os.environ.get("STRLING_PUBLIC_VERIFIER_SHA", "")
    request_digest = os.environ.get("STRLING_PUBLIC_REQUEST_SHA256", "")
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REPOSITORY") != "strling-lang/strling"
        or not re.fullmatch(r"[0-9a-f]{40}", expected)
        or not re.fullmatch(r"[0-9a-f]{64}", request_digest)
        or git(root, "rev-parse", "HEAD") != expected
        or git(root, "status", "--porcelain", "--untracked-files=all")
    ):
        raise RetrievalError(
            "authority",
            "public verification requires the protected immutable hosted execution",
        )
    run_id, attempt = (
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    )
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise RetrievalError(
            "authority", "missing protected workflow execution identity"
        )
    return {
        "verifier_sha": expected,
        "request_sha256": request_digest,
        "run_id": run_id,
        "run_attempt": attempt,
    }


def save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def native_companion(root: Path, files: dict[str, str], scope: str) -> Path:
    marker = "win_amd64" if scope == "windows-x86_64" else "linux_x86_64"
    wheels = [name for name in files if name.endswith(".whl") and marker in name]
    if (
        len(wheels) != 1
        or hashlib.sha256((root / wheels[0]).read_bytes()).hexdigest()
        != files[wheels[0]]
    ):
        raise RetrievalError(
            "native-wasm", "exact authenticated host native companion is unavailable"
        )
    suffix = (
        "strling_interop.dll" if scope == "windows-x86_64" else "libstrling_interop.so"
    )
    candidates = {
        name: data
        for name, data in archive_files(root / wheels[0]).items()
        if name.endswith(suffix)
    }
    if len(candidates) != 1:
        raise RetrievalError("native-wasm", "native companion is absent or ambiguous")
    name, data = next(iter(candidates.items()))
    name = "authenticated-native/" + scope + "/" + Path(name).name
    files[name] = write_retrieved(root, name, data)
    return root / name


def execute(args, control: dict) -> dict:
    started = time.monotonic()
    request = strict_json(args.request.read_bytes())
    # Authenticate the digest before using request identities even as git data.
    if hashlib.sha256(canonical_json(request)).hexdigest() != control["request_sha256"]:
        raise RetrievalError("authority", "request differs from protected approval")
    contract = load_json(ROOT / "governance/public-distribution.json")
    authenticated = authenticate_release(
        verifier=args.trusted_verifier.resolve(),
        implementation_source=args.implementation_source.resolve(),
        certification_source=args.closure_source.resolve(),
        bundle=args.bundle.resolve(),
        evidence=args.evidence.resolve(),
        expected_source=request["certified_source_sha"],
        expected_closure=request["closure_source_sha"],
        expected_root=request["signed_evidence_root"],
        contract=contract,
        output=args.output / "authentication",
    )
    manifest = authenticated["manifest"]
    validate_request(
        request,
        expected_sha256=control["request_sha256"],
        manifest=manifest,
        authentication=authenticated["receipt"],
        authority="public",
    )
    if (
        request["version"]
        != load_json(args.implementation_source / "governance/release-policy.json")[
            "product"
        ]["version"]
    ):
        raise RetrievalError(
            "source-identity",
            "request version differs from certified product authority",
        )
    # Certified bytes supply comparison expectations only. Consumer payloads are
    # written exclusively by the public retrieval/authentication path below.
    materialize_exports(
        manifest=manifest,
        evidence=args.evidence,
        exports=args.exports,
        source_sha=request["certified_source_sha"],
        output=args.output / "expectations",
    )
    attestation = load_json(args.bundle / "attestation.json")["signed_payload"]
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    destinations = exact_rows(request["destinations"], "artifact_id", set(artifacts))
    documents = exact_rows(request["documents"], "artifact_id", set(artifacts))
    results, observations, files = {}, [], {}
    for identity, artifact in artifacts.items():
        route = (
            "github-tag"
            if artifact["registry"].startswith("github-tag:")
            else artifact["registry"]
        )
        origins = set(contract["routes"][route]["origins"])
        for kind in ("sbom", "provenance", "documentation"):
            url = urlsplit(documents[identity][kind]["url"])
            origins.add(url.scheme + "://" + url.netloc)
        if route == "conan":
            url = urlsplit(destinations[identity]["registry_endpoint"])
            origins.add(url.scheme + "://" + url.netloc)
        transport = PublicTransport(
            args.output / ("responses-" + identity.split(":")[1]), origins
        )
        result = verify_artifact(
            transport=transport,
            artifact=artifact,
            manifest=manifest,
            destination=destinations[identity],
            documents=documents[identity],
            version=request["version"],
            source_sha=request["certified_source_sha"],
            source_tree=attestation["certified_source"]["tree"],
            source=args.implementation_source,
            evidence=args.evidence,
            materialized=args.output / "retrieved",
            certified_subject_root=args.output / "expectations",
        )
        result["retrieval_observations"] = transport.observations
        results[identity] = result
        observations.extend(result["observations"])
        for name, digest in result["retrieval_files"].items():
            if name in files and files[name] != digest:
                raise RetrievalError(
                    "artifact-integrity", "conflicting authenticated retrievals"
                )
            files[name] = digest
        save(args.output / (identity.replace(":", "-") + ".json"), result)
    scope = host_scope()
    consumers = []
    for identity, artifact in artifacts.items():
        if (
            artifact["distribution_contract"]["tier"] != "Supported"
            or scope not in artifact["distribution_contract"]["platforms"]
        ):
            continue
        selected = [
            row
            for row in observations
            if row["artifact_id"] == identity and row["platform"] == scope
        ]
        if "finding" in results[identity]:
            continue
        try:
            native = (
                native_companion(args.output / "retrieved", files, scope)
                if identity
                in {
                    "release:java",
                    "release:kotlin",
                    "release:go",
                    "release:dart",
                    "release:swift",
                }
                else None
            )
            receipt = verify_retrieved_consumer(
                identity,
                retrieval_root=args.output / "retrieved",
                fixture_root=ROOT,
                work=args.consumer_work / identity.split(":")[1],
                manifest=manifest,
                version=request["version"],
                sdk_environment=dict(os.environ),
                retrieval_files=files,
                authority="public",
                native=native,
            )
            consumers.append(receipt)
            for row in selected:
                row.update(
                    status="VERIFIED",
                    consumer_receipt_sha256=hashlib.sha256(
                        canonical_json(receipt)
                    ).hexdigest(),
                )
        except Exception as error:
            code = getattr(error, "code", "")
            categories = {
                "consumer-runtime": "runtime-compatibility",
                "consumer-dependency": "dependency-resolution",
                "consumer-native": "native-wasm",
                "consumer-result": "functional-behavior",
                "consumer-isolation": "security",
                "consumer-substitution": "artifact-integrity",
                "consumer-scope": "runtime-compatibility",
            }
            finding = {
                "category": getattr(
                    error, "category", categories.get(code, "installation")
                ),
                "detail": str(error),
                "artifact_id": identity,
                "scope": scope,
                "expected": {
                    "source": request["certified_source_sha"],
                    "version": request["version"],
                    "canonical_source_outcome": "succeeded",
                    "canonical_target_pattern": "abc",
                    "kernel_mismatch_rejected": True,
                },
                "observed": {"error_type": type(error).__name__, "detail": str(error)},
                "environment": {"scope": scope, "execution": control},
                "supporting_evidence": "consumer-diagnostics/" + identity.split(":")[1],
            }
            consumers.append(
                {
                    "artifact_id": identity,
                    "scope": scope,
                    "status": "FAILED",
                    "finding": finding,
                }
            )
            for row in selected:
                row.update(status="FAILED", finding=finding)
        finally:
            consumer_root = args.consumer_work / identity.split(":")[1]
            for log in consumer_root.rglob("consumer-command-*.*"):
                target = (
                    args.output
                    / "consumer-diagnostics"
                    / identity.split(":")[1]
                    / log.relative_to(consumer_root)
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(log, target)
    report = {
        "contract": request["contract"],
        "authority": "public",
        "execution": control,
        "source": request["certified_source_sha"],
        "scope": scope,
        "manifest_fingerprint": request["manifest_fingerprint"],
        "authentication": authenticated["receipt"],
        "observations": observations,
        "consumers": consumers,
        "elapsed_seconds": time.monotonic() - started,
        "publication_authorized": False,
        "registry_mutation_authorized": False,
        "release_transition": None,
    }
    save(args.output / "scope-result.json", report)
    return report


def aggregate(manifest: dict, reports: list[dict], control: dict) -> dict:
    scopes = {
        row["platform"] for row in obligations(manifest) if row["platform"] is not None
    }
    scoped = exact_rows(reports, "scope", scopes)
    required = obligations(manifest)
    for report in reports:
        if report["authority"] != "public" or report["execution"] != control:
            raise RetrievalError(
                "authority", "scope receipt is from another protected execution"
            )
        if (
            report["source"] != reports[0]["source"]
            or report["manifest_fingerprint"] != reports[0]["manifest_fingerprint"]
        ):
            raise RetrievalError(
                "source-identity", "scope receipts disagree on release identity"
            )
        if report["manifest_fingerprint"] != document_fingerprint(manifest):
            raise RetrievalError(
                "contract", "aggregate denominator differs from authenticated manifest"
            )
        reduce_observations(manifest, report["observations"], authority="public")
        consumers = {}
        for receipt in report["consumers"]:
            identity = receipt.get("artifact_id")
            if identity in consumers:
                raise RetrievalError("contract", "duplicate consumer receipt")
            consumers[identity] = receipt
        for observation in report["observations"]:
            if (
                observation["platform"] != report["scope"]
                or observation["status"] != "VERIFIED"
            ):
                continue
            receipt = consumers.get(observation["artifact_id"], {})
            unsigned = {
                key: value
                for key, value in receipt.items()
                if key != "receipt_fingerprint"
            }
            if (
                receipt.get("authority") != "public"
                or receipt.get("scope") != report["scope"]
                or receipt.get("status") != "VERIFIED"
                or receipt.get("receipt_fingerprint")
                != hashlib.sha256(canonical_json(unsigned)).hexdigest()
                or observation.get("consumer_receipt_sha256")
                != hashlib.sha256(canonical_json(receipt)).hexdigest()
            ):
                raise RetrievalError(
                    "authority",
                    "consumer observation lacks its exact authenticated execution receipt",
                )
    indexed = {
        scope: {row["id"]: row for row in report["observations"]}
        for scope, report in scoped.items()
    }
    combined = []
    priority = {
        "FAILED": 0,
        "INDETERMINATE": 1,
        "VERIFYING": 2,
        "NOT_PUBLISHED": 3,
        "VERIFIED": 4,
    }
    for obligation in required:
        if obligation["platform"] is not None:
            chosen = indexed[obligation["platform"]][obligation["id"]]
        else:
            candidates = [rows[obligation["id"]] for rows in indexed.values()]
            chosen = min(candidates, key=lambda row: priority[row["status"]])
        combined.append(chosen)
    result = reduce_observations(manifest, combined, authority="public")
    result.update(
        execution=control,
        source=reports[0]["source"],
        observations=combined,
        findings=[row["finding"] for row in combined if "finding" in row],
        corrective_action="separate-owner-authorization-required",
    )
    from jsonschema import Draft202012Validator

    Draft202012Validator(
        load_json(ROOT / "governance/schemas/public-verification-result.schema.json")
    ).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--implementation-source", type=Path, required=True)
    parser.add_argument("--closure-source", type=Path, required=True)
    parser.add_argument("--trusted-verifier", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--consumer-work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    control = protected_execution()
    args.output = args.output.resolve()
    args.consumer_work = args.consumer_work.resolve()
    if args.output.is_relative_to(ROOT) or args.consumer_work.is_relative_to(ROOT):
        raise RetrievalError(
            "security", "outputs must be outside the immutable verifier checkout"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        report = execute(args, control)
        return int(
            any(
                row["status"] in {"FAILED", "INDETERMINATE", "NOT_PUBLISHED"}
                for row in report["observations"]
            )
        )
    except Exception as error:
        save(
            args.output / "terminal-failure.json",
            {
                "status": "FAILED",
                "execution": control,
                "error_type": type(error).__name__,
                "category": getattr(error, "category", "contract"),
                "detail": str(error),
                "release_transition": None,
                "publication_authorized": False,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
