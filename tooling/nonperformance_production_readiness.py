#!/usr/bin/env python3
"""Fresh Release-shaped development readiness, without performance or product claims."""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from typing import Sequence

from tooling import production_certification as production


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    root = production.ROOT
    source = production.repository_identity(root)
    if source["status_porcelain"] or args.artifact_directory.exists():
        parser.error("clean source and a fresh evidence directory are required")
    output = args.artifact_directory.resolve()
    output.mkdir(parents=True)
    run_id = uuid.uuid4().hex
    worktree = root / ".cert/nonperformance-readiness" / run_id / "source"
    environment = production.build_certification_environment()
    environment["PYTHONPATH"] = str(worktree)
    contract = production.load_capacity_contract()
    capacity = production.storage_capacity_evidence(
        free_bytes=shutil.disk_usage(root).free, contract=contract
    )
    if capacity["status"] != "passed":
        parser.error("governed production capacity requirement is not met")
    artifact = output / "nonperformance-readiness-release.json"
    receipt = {
        "artifact_kind": "strling-nonperformance-production-readiness",
        "authoritative": False,
        "performance_deferred": True,
        "closure_authorized": False,
        "source_sha": source["sha"],
        "independent_no_reuse": True,
        "run_id": run_id,
        "worktree": str(worktree),
        "status": "failed",
        "capacity": capacity,
    }
    try:
        production.create_worktree(source_sha=source["sha"], path=worktree)
        receipt["materialized_governed_inputs"] = (
            production.materialize_governed_production_inputs(
                authority_root=root, worktree=worktree
            )
        )
        stages = (
            (
                worktree,
                [
                    "python3",
                    "-m",
                    "tooling.exact_runtime_toolchains",
                    "--check",
                    "--json",
                ],
            ),
            *(
                (worktree, command)
                for command in production.generated_setup_bootstrap_commands()
            ),
            (worktree, ["npm", "ci", "--no-audit", "--no-fund"]),
            (worktree / "tooling/lsp-server", ["npm", "ci", "--no-audit", "--no-fund"]),
            (worktree, ["./strling", "setup", "all"]),
            (
                worktree,
                [
                    "cargo",
                    "+1.75.0",
                    "build",
                    "--manifest-path",
                    "bindings/interop/Cargo.toml",
                    "--locked",
                ],
            ),
            (worktree, production.generated_artifact_preparation_command()),
        )
        for directory, command in stages:
            production.run_capacity_checked(
                command, cwd=directory, contract=contract, env=environment
            )
        if production.repository_identity(worktree)["status_porcelain"]:
            raise production.ProductionCertificationError(
                "generation changed clean independent source"
            )
        production.run_capacity_checked(
            [
                "python3",
                "-m",
                "tooling.certification_readiness",
                "--profile",
                "release",
                "--artifact",
                str(artifact),
            ],
            cwd=worktree,
            contract=contract,
            env=environment,
        )
        receipt["preserved_execution_evidence"] = (
            production.preserve_execution_evidence(
                worktree=worktree, output_dir=output, profile_artifact=artifact
            )
        )
        final = production.repository_identity(worktree)
        if (
            final["sha"] != source["sha"]
            or final["status_porcelain"]
            or production.repository_identity(root) != source
        ):
            raise production.ProductionCertificationError(
                "independent source identity changed"
            )
        receipt["status"] = "passed"
        # The worktree is retained for evidence review; no automatic destructive cleanup.
    except production.ProductionCertificationError as error:
        receipt["failure"] = str(error)
        if artifact.exists():
            receipt["preserved_execution_evidence"] = (
                production.preserve_execution_evidence(
                    worktree=worktree, output_dir=output, profile_artifact=artifact
                )
            )
    finally:
        (output / "nonperformance-production-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
