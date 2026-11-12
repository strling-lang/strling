"""Verify a signed complete-product candidate and its publication handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.candidate_handoff import HANDOFF_PATH, derive, verify
from tooling.local_certification_attestation import verify_attestation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--trust-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--write-handoff", action="store_true")
    parser.add_argument("--provisional-rc", default="4.0.0-rc.1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify_attestation(
        repository_root=args.repository_root,
        trust_root=args.trust_root,
        bundle_dir=args.bundle,
        policy_name="release-candidate-certification-trust.json",
    )
    destination = args.handoff or args.repository_root / HANDOFF_PATH
    if args.write_handoff:
        if destination.exists():
            raise ValueError("publication handoff already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                derive(
                    args.repository_root,
                    args.trust_root,
                    args.bundle,
                    provisional_rc=args.provisional_rc,
                ),
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    handoff = verify(args.repository_root, args.trust_root, args.bundle, destination)
    print(
        json.dumps(
            dict(
                status="passed",
                operation_id="certification.release-candidate-integrity",
                certification=result,
                handoff=handoff,
                publication_authorized=False,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
