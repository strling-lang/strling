"""Reconcile only this protected run's complete public verification receipts."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.public_distribution import strict_json
from tooling.public_retrieval import RetrievalError
from tooling.release_supply_chain import canonical_json, document_fingerprint
from tooling.verify_public_release import aggregate, protected_execution, save


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scope-result", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    control = protected_execution()
    try:
        return reconcile(args, control)
    except Exception as error:
        save(
            args.output,
            {
                "status": "INDETERMINATE" if isinstance(error, OSError) else "FAILED",
                "authority": "public",
                "execution": control,
                "category": getattr(error, "category", "incomplete-evidence"),
                "error_type": type(error).__name__,
                "detail": str(error),
                "expected": {
                    "scope_results": [str(path) for path in args.scope_result]
                },
                "observed": {
                    "available_scope_results": [
                        str(path) for path in args.scope_result if path.is_file()
                    ]
                },
                "release_transition": None,
                "public_release_verified": False,
                "publication_authorized": False,
                "registry_mutation_authorized": False,
            },
        )
        raise


def reconcile(args, control) -> int:
    request = strict_json(args.request.read_bytes())
    manifest = strict_json(args.manifest.read_bytes())
    if (
        hashlib.sha256(canonical_json(request)).hexdigest() != control["request_sha256"]
        or document_fingerprint(manifest) != request["manifest_fingerprint"]
    ):
        raise RetrievalError(
            "authority", "aggregate inputs differ from protected request"
        )
    reports = [strict_json(path.read_bytes()) for path in args.scope_result]
    for report in reports:
        authenticated = report["authentication"]
        if authenticated.get("status") != "passed" or any(
            authenticated.get(key) != request[key]
            for key in (
                "certified_source_sha",
                "closure_source_sha",
                "signed_evidence_root",
            )
        ):
            raise RetrievalError(
                "authority",
                "scope result lacks the approved signed-release authentication",
            )
    result = aggregate(manifest, reports, control)
    save(args.output, result)
    return int(result["status"] != "VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
