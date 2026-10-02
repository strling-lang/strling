#!/usr/bin/env python3
"""Development-only profile readiness; never authoritative certification evidence."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Sequence

from tooling.certification import (
    build_certification_artifact,
    canonical_evidence_fingerprint,
    repository_state,
)


def _quality_controller() -> Any:
    """Load the existing script-oriented controller without import suppressions."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return import_module("quality")


quality = _quality_controller()

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_KIND = "strling-nonperformance-readiness"
SUCCESS = {"passed", "waived"}


def performance_stage(stage: quality.ProfileStage) -> bool:
    """Recognize the governed producer, failing closed on contradictory metadata."""
    definition = stage.definition or {}
    command = definition.get("command", [])
    producer = "tooling.performance_resource_certification" in command
    contract = str(definition.get("result_operation_id", "")).startswith(
        "certification.performance-resource-"
    )
    if producer != contract:
        raise quality.ConfigurationError(
            f"ambiguous performance operation: {stage.operation}"
        )
    return producer


def selection(runner: quality.QualityRunner, profile: str) -> dict[str, Any]:
    stages = quality.QualityRunner._profile_stages(runner, profile, None)
    return {
        "governed_result_ids": [f"{s.operation}@{s.component}" for s in stages],
        "selected_result_ids": [
            f"{s.operation}@{s.component}" for s in stages if not performance_stage(s)
        ],
        "deferred_operations": [
            {
                "result_id": f"{s.operation}@{s.component}",
                "definition": s.definition,
                "disposition": "intentionally-deferred-not-passed",
            }
            for s in stages
            if performance_stage(s)
        ],
    }


class ReadinessRunner(quality.QualityRunner):
    def _profile_stages(
        self, name: str, requested: str | None
    ) -> list[quality.ProfileStage]:
        if requested is not None:
            raise quality.ConfigurationError(
                "readiness requires the complete default scope"
            )
        return [
            stage
            for stage in super()._profile_stages(name, requested)
            if not performance_stage(stage)
        ]


def readiness_artifact(
    *,
    runner: quality.QualityRunner,
    profile: str,
    results: list[Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    selected = selection(runner, profile)
    statuses = [result.status for result in results]
    internal = build_certification_artifact(
        root=runner.toolchain.root,
        profile_id=profile,
        profile_definition=runner.toolchain.profile(profile),
        requested_component=None,
        results=[result.as_dict() for result in results],
        aggregate_status=quality._profile_status(results),
        exit_code=quality._profile_exit(results),
        resolved_repository_state=source,
    )["deterministic_evidence"]
    observed_ids = [f"{result.operation}@{result.component}" for result in results]
    complete = observed_ids == selected["selected_result_ids"]
    ready = complete and all(status in SUCCESS for status in statuses)
    evidence = {
        "repository": source,
        "governed_profile": internal["profile"],
        "selection": selected,
        "operations": internal["operations"],
        "aggregate": internal["aggregate"],
        "readiness_status": "passed" if ready else "failed",
        "unexecuted_result_ids": selected["selected_result_ids"][len(results) :],
    }
    return {
        "schema_version": "1.0.0",
        "artifact_kind": ARTIFACT_KIND,
        "authoritative": False,
        "performance_deferred": True,
        "closure_authorized": False,
        "deterministic_evidence": evidence,
        "evidence_fingerprint": canonical_evidence_fingerprint(evidence),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=("local", "pull-request", "full", "release"), required=True
    )
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)
    runner = ReadinessRunner(quality.Toolchain.load(ROOT / "toolchain.json"))
    if args.plan:
        print(json.dumps(selection(runner, args.profile), sort_keys=True))
        return 0
    if args.artifact is None or args.artifact.exists():
        parser.error("a fresh --artifact path is required; evidence reuse is forbidden")
    source = repository_state(ROOT)
    if source["dirty"]:
        parser.error("readiness requires a clean committed candidate")
    quality._preflight_profile_environment(args.profile)
    progress = quality.ProfileProgress(
        profile=f"nonperformance-readiness:{args.profile}",
        source=source,
        ledger_path=args.artifact.with_suffix(".progress.jsonl"),
        display_path=str(args.artifact),
        stream=sys.stderr,
        heartbeat_enabled=True,
    )
    results = runner.run_profile(args.profile, None, progress=progress)
    artifact = readiness_artifact(
        runner=runner, profile=args.profile, results=results, source=source
    )
    if repository_state(ROOT) != source:
        artifact["deterministic_evidence"]["readiness_status"] = "failed"
        artifact["deterministic_evidence"]["source_changed_during_execution"] = True
        artifact["evidence_fingerprint"] = canonical_evidence_fingerprint(
            artifact["deterministic_evidence"]
        )
    status = artifact["deterministic_evidence"]["readiness_status"]
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(
        json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    progress.profile_terminal(status)
    if status != "passed":
        quality._render_profile_failure_details(results)
    print(
        json.dumps(
            {
                "artifact": str(args.artifact),
                "status": status,
                "authoritative": False,
                "performance_deferred": True,
            }
        )
    )
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
