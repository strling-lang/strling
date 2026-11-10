"""Qualify public-verification adapters with authenticated staged packages."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tooling.public_authentication import authenticate_release
from tooling.public_fixtures import materialize_exports, protocol_fixture
from tooling.public_verification import verify_artifact
from tooling.release_supply_chain import load_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation-source", type=Path, required=True)
    parser.add_argument("--closure-source", type=Path, required=True)
    parser.add_argument("--trusted-verifier", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--closure-sha", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    contract = load_json(
        Path(__file__).resolve().parents[1] / "governance/public-distribution.json"
    )
    authenticated = authenticate_release(
        verifier=args.trusted_verifier.resolve(),
        implementation_source=args.implementation_source.resolve(),
        certification_source=args.closure_source.resolve(),
        bundle=args.bundle.resolve(),
        evidence=args.evidence.resolve(),
        expected_source=args.source_sha,
        expected_closure=args.closure_sha,
        expected_root=args.evidence_root,
        contract=contract,
        output=args.output / "authentication",
    )
    manifest = authenticated["manifest"]
    version = load_json(args.implementation_source / "governance/release-policy.json")[
        "product"
    ]["version"]
    materialization = materialize_exports(
        manifest=manifest,
        evidence=args.evidence,
        exports=args.exports,
        source_sha=args.source_sha,
        output=args.output / "certified",
    )
    attestation = load_json(args.bundle / "attestation.json")["signed_payload"]
    rows = []
    for artifact in manifest["artifacts"]:
        began = time.monotonic()
        transport, destination, documents = protocol_fixture(
            artifact=artifact,
            evidence=args.evidence,
            staged=args.output / "certified",
            source=args.implementation_source,
            source_sha=args.source_sha,
            source_tree=attestation["certified_source"]["tree"],
            version=version,
        )
        result = verify_artifact(
            transport=transport,
            artifact=artifact,
            manifest=manifest,
            destination=destination,
            documents=documents,
            version=version,
            source_sha=args.source_sha,
            source_tree=attestation["certified_source"]["tree"],
            source=args.implementation_source,
            evidence=args.evidence,
            materialized=args.output / "retrieved",
            certified_subject_root=args.output / "certified",
        )
        result["elapsed_seconds"] = time.monotonic() - began
        result["retrieval_observations"] = transport.observations
        result_path = args.output / (artifact["id"].replace(":", "-") + ".json")
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        passed = "finding" not in result
        rows.append(
            {
                "artifact_id": artifact["id"],
                "status": "passed" if passed else "failed",
                "elapsed_seconds": result["elapsed_seconds"],
            }
        )
        print(json.dumps({**rows[-1], "finding": result.get("finding")}), flush=True)
    failures = sum(row["status"] != "passed" for row in rows)
    report = {
        "authority": "synthetic",
        "status": "artifact-qualification-passed" if not failures else "failed",
        "required_artifacts": len(rows),
        "passed": len(rows) - failures,
        "failed": failures,
        "consumers_qualified_by_this_run": 0,
        "public_release_verified": False,
        "source": args.source_sha,
        "authentication": authenticated["receipt"],
        "materialization": materialization,
        "artifacts": rows,
        "elapsed_seconds": time.monotonic() - started,
    }
    (args.output / "qualification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
