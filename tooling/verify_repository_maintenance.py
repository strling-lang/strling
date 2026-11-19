"""Check the explicitly approved dev integration against the signed release closure."""

import json
import os
import re
import subprocess
from pathlib import Path


MAINTENANCE_PATHS = frozenset(
    {
        ".github/public-verification/request.json",
        ".github/workflows/certification-integrity.yml",
        ".github/workflows/public-verification.yml",
        "CONTRIBUTING.md",
        "docs/release-policy.md",
        "governance/release-policy.json",
        "governance/schemas/release-policy.schema.json",
        "tooling/release_policy.py",
        "tooling/tests/test_release_policy.py",
        "tooling/tests/test_repository_maintenance.py",
        "tooling/verify_repository_maintenance.py",
    }
)


def check(
    repo: Path, baseline: str, approved: str, environment: dict[str, str]
) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (baseline, approved)):
        raise ValueError("Both maintenance and historical closure must be exact SHAs")
    if (
        environment.get("GITHUB_EVENT_NAME") != "push"
        or environment.get("GITHUB_REF") != "refs/heads/dev"
        or environment.get("GITHUB_SHA") != approved
        or environment.get("GITHUB_WORKFLOW_SHA") != approved
        or git("rev-parse", "HEAD") != approved
    ):
        raise ValueError(
            "Maintenance acceptance requires the approved dev push and workflow SHA"
        )
    if git("merge-base", baseline, approved) != baseline:
        raise ValueError(
            "Historical closure must be an ancestor of the maintenance source"
        )
    paths = set(
        git("diff", "--no-renames", "--name-only", baseline, approved).splitlines()
    )
    if not paths or paths - MAINTENANCE_PATHS:
        raise ValueError(
            f"Unexpected maintenance paths: {sorted(paths - MAINTENANCE_PATHS)}"
        )
    return {
        "kind": "repository-maintenance",
        "source_sha": approved,
        "historical_closure_sha": baseline,
        "changed_paths": sorted(paths),
        "publication_authorized": False,
    }


if __name__ == "__main__":
    print(
        json.dumps(
            check(
                Path.cwd(),
                os.environ["HISTORICAL_CLOSURE_SHA"],
                os.environ["APPROVED_MAINTENANCE_SHA"],
                dict(os.environ),
            ),
            sort_keys=True,
        )
    )
