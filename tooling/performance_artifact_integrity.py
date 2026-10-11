"""Offline integrity of governed performance artifacts, never performance evidence.

This intentionally invokes only the pure repository-contract validator. It does
not invoke a profile producer, runner, conditioning, calibration or sampling.
Authority-bearing baseline and historical evidence remain separately governed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from tooling.performance_resource_certification import (
    PerformanceResourceError,
    validate_repository_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def check_integrity(root: Path = ROOT) -> dict[str, object]:
    try:
        details = validate_repository_contract(root=root)
    except (PerformanceResourceError, OSError, ValueError) as exc:
        return {
            "operation": "performance-artifact-integrity",
            "status": "failed",
            "authoritative": False,
            "authenticated_performance_samples": 0,
            "reason": str(exc),
        }
    return {
        "operation": "performance-artifact-integrity",
        "status": "passed",
        "authoritative": False,
        "authenticated_performance_samples": 0,
        "contract": details,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--json", action="store_true")
    parser.parse_args(argv)
    result = check_integrity()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
