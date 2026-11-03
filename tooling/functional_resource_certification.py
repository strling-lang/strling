"""Deterministic functional resource obligations, independent of benchmarks.

The profile producer and attestation adapter must supply source-bound transport;
these functions only execute and validate the complete functional denominator.
"""

from __future__ import annotations

CONTRACT = "strling-functional-resource-v1"
COMMANDS = {
    "resource:frontend-limits": [
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "core/internal/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "semantic_frontend",
            "--test",
            "semantic_frontend_properties",
            "--test",
            "regex_frontend",
        ]
    ],
    "resource:kernel-limits": [
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "core/internal/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "compiler_boundary_resources",
            "--test",
            "semantic_analysis",
            "--test",
            "structural_analysis",
            "--test",
            "safety_analysis",
            "--test",
            "capability_evaluation",
            "--test",
            "portability_planning",
        ]
    ],
    "resource:target-limits": [
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "core/internal/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "pcre2_lowering",
            "--test",
            "ecmascript_lowering",
            "--test",
            "python_re_lowering",
            "--test",
            "pcre2_serialization",
            "--test",
            "ecmascript_serialization",
            "--test",
            "python_re_serialization",
        ]
    ],
    "resource:editor-interop-limits": [
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "core/internal/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "editor_intelligence",
        ],
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "bindings/interop/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "protocol",
        ],
    ],
    "resource:no-match-limits": [
        [
            "cargo",
            "+1.75.0",
            "test",
            "--manifest-path",
            "core/internal/Cargo.toml",
            "--locked",
            "--offline",
            "--test",
            "no_match_explanation",
            "--test",
            "no_match_explanation_properties",
        ]
    ],
}


COMMANDS["resource:native-memory-lifetime"] = [
    [
        "rustup",
        "run",
        "1.75.0",
        "rustc",
        "--edition=2021",
        "--test",
        "tooling/tests/memory_worker_lifetime.rs",
        "-o",
        "target/functional-resource/native-memory-lifetime.exe",
    ],
    [
        "target/functional-resource/native-memory-lifetime.exe",
        "--test-threads=1",
        "--nocapture",
    ],
]


def execute_checks(run_command):
    """Run all registered functional obligations, retaining failed steps."""
    checks = []
    for operation, commands in COMMANDS.items():
        steps = [run_command(list(command)) for command in commands]
        checks.append({"id": operation, "steps": steps})
    return {"contract": CONTRACT, "checks": checks}


def validate_checks(evidence):
    """Reject unknown contracts, missing/duplicate obligations and failed steps."""
    if not isinstance(evidence, dict) or set(evidence) != {"contract", "checks"}:
        raise ValueError("functional resource evidence shape")
    if evidence["contract"] != CONTRACT:
        raise ValueError("functional resource contract")
    checks = evidence["checks"]
    if (
        not isinstance(checks, list)
        or not all(isinstance(x, dict) for x in checks)
        or [x.get("id") for x in checks] != list(COMMANDS)
    ):
        raise ValueError("functional resource denominator or order")
    for check in checks:
        if set(check) != {"id", "steps"}:
            raise ValueError("functional resource check shape")
        steps = check["steps"]
        if not isinstance(steps, list) or len(steps) != len(COMMANDS[check["id"]]):
            raise ValueError("functional resource step denominator")
        for expected, step in zip(COMMANDS[check["id"]], steps):
            if not isinstance(step, dict) or step.get("command") != expected:
                raise ValueError("functional resource command mismatch")
            if type(step.get("exit_code")) is not int or step["exit_code"] != 0:
                raise ValueError("functional resource command failed")
    return True


CERTIFICATION_CONTRACT = "strling-deterministic-certification-v1"


def fingerprint(value):
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def make_evidence(source_sha, profile, checks):
    try:
        validate_checks(checks)
        status = "passed"
    except ValueError:
        status = "failed"
    deterministic = {
        "certification_contract": CERTIFICATION_CONTRACT,
        "profile": profile,
        "status": status,
        "resources": checks,
    }
    return {
        "schema_version": "certification-result-v1",
        "operation_id": "certification.functional-resource",
        "certification_contract": CERTIFICATION_CONTRACT,
        "profile": profile,
        "commit": source_sha,
        "status": status,
        "duration_ms": None,
        "checks": [
            {
                "id": row["id"],
                "status": "passed"
                if all(
                    type(step.get("exit_code")) is int and step["exit_code"] == 0
                    for step in row["steps"]
                )
                else "failed",
                "details": {"steps": row["steps"]},
            }
            for row in checks["checks"]
        ],
        "deterministic_evidence": deterministic,
        "evidence_fingerprint": fingerprint(deterministic),
    }


def validate_evidence(value, *, source_sha, profile):
    if value.get("schema_version") != "certification-result-v1":
        raise ValueError("functional resource envelope contract")
    if (
        value.get("certification_contract") != CERTIFICATION_CONTRACT
        or value.get("operation_id") != "certification.functional-resource"
        or value.get("commit") != source_sha
        or value.get("profile") != profile
    ):
        raise ValueError("functional resource source/profile/scope binding")
    deterministic = value.get("deterministic_evidence", {})
    resources = deterministic.get("resources")
    validate_checks(resources)
    expected = make_evidence(source_sha, profile, resources)
    if value != expected:
        raise ValueError("functional resource envelope integrity")
    return True


def main(argv=None):
    import argparse
    import hashlib
    import json
    import subprocess
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", required=True, choices=("local", "pull-request", "full", "release")
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--execution-directory")
    parser.add_argument("--certification-invocation-id")
    parser.add_argument(
        "--certification-profile", choices=("local", "pull-request", "full", "release")
    )
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--producer-id")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    execution_values = (
        args.execution_directory,
        args.certification_invocation_id,
        args.certification_profile,
        args.expected_source_sha,
        args.producer_id,
    )
    if any(value is not None for value in execution_values) and not all(
        value is not None for value in execution_values
    ):
        parser.error("invocation-bound execution arguments must be supplied together")

    def source():
        return (
            subprocess.check_output(
                ["git", "--no-optional-locks", "rev-parse", "HEAD"],
                cwd=root,
                timeout=30,
            )
            .decode()
            .strip()
        )

    before = source()
    if args.execution_directory:
        if (
            before != args.expected_source_sha
            or subprocess.check_output(
                ["git", "--no-optional-locks", "status", "--porcelain"],
                cwd=root,
                timeout=120,
            ).strip()
        ):
            raise ValueError(
                "producer source SHA or clean-tree identity does not match invocation"
            )
        if args.producer_id != "functional_resource_certification@repository" or (
            args.certification_profile != args.profile
            and (args.certification_profile, args.profile) != ("release", "full")
        ):
            raise ValueError(
                "functional resource invocation profile or producer mismatch"
            )
    (root / "target/functional-resource").mkdir(parents=True, exist_ok=True)

    def run(command):
        try:
            result = subprocess.run(command, cwd=root, capture_output=True, timeout=900)
            stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            stdout, stderr, exit_code = b"", str(error).encode(), -1
        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        }

    result = make_evidence(before, args.profile, execute_checks(run))
    if source() != before:
        raise ValueError("source changed during functional resource execution")
    exit_code = 0 if result["status"] == "passed" else 1
    if args.execution_directory:
        from tooling.structured_operation_execution import (
            atomic_write_artifact,
            execution_context,
            extract_environment_identity,
            zero_sample_consumption,
        )

        atomic_write_artifact(
            Path(args.execution_directory) / "result.json",
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
                "result_contract": "certification-result-v1",
                "process_exit_code": exit_code,
                "terminal_status": result["status"],
                "environment_identity": extract_environment_identity(result),
                "performance_evidence_identity": result["evidence_fingerprint"],
                "sample_consumption": zero_sample_consumption(),
                "structured_result": result,
                "integrity_error": None,
            },
        )
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
