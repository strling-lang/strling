"""Unqualified acquisition of actual governed workloads inside native envelopes.

The caller supplies independently verified build/source/environment provenance and
an immutable prospective schedule. This module does not fit thresholds, grant
admission, create baselines, retry failed attempts or replace resource checks.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

from tooling import performance_process_envelope as envelope
from tooling import performance_resource_certification as controller


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _check_inputs(inputs):
    _require(type(inputs) is dict and inputs, "pinned inputs required")
    for path, digest in inputs.items():
        _require(
            isinstance(path, Path)
            and path.is_absolute()
            and path.is_file()
            and not path.is_symlink(),
            "regular absolute input",
        )
        _require(envelope._hash(path) == digest, f"input changed: {path}")


def _source(root, source_sha):
    _require(
        controller._git_identity(root) == (source_sha, False),
        "exact clean source required",
    )


def acquire_coordinate(
    key,
    *,
    root: Path,
    manifest: dict,
    artifacts: dict,
    environment: dict,
    process_environment: dict,
    inputs: dict,
    source_sha: str,
    batch_iterations: int,
    directory: Path,
) -> dict:
    """One single-use coordinate; source and input drift invalidate its result.

    Existing command builders and complete result validators are reused. A file
    size observation has no invented child process. The enclosing receipt retains
    the manifest/environment plus raw process output even if parsing fails.
    Clean-source checks bracket acquisition but are not a replacement for the
    caller's retained source owner/lease or independent binary provenance checks.
    """
    manifest, artifacts, environment, process_environment, inputs = copy.deepcopy(
        (manifest, artifacts, environment, process_environment, inputs)
    )
    _require(isinstance(root, Path) and root.is_absolute(), "absolute source root")
    _require(
        isinstance(directory, Path) and directory.is_absolute(),
        "absolute new directory",
    )
    _require(
        type(source_sha) is str
        and len(source_sha) == 40
        and all(c in "0123456789abcdef" for c in source_sha),
        "source SHA",
    )
    _require(
        type(key) is tuple and key in controller.performance_measurement_keys(manifest),
        "unknown measurement coordinate",
    )
    _require(
        environment.get("os") == "windows"
        and environment.get("execution_resource", {}).get("platform") == "windows",
        "native Windows acquisition required",
    )
    policy = manifest["measurement_policy"]
    _require(
        (
            policy["warmup_iterations"],
            policy["sample_iterations"],
            policy["baseline_repetitions"],
        )
        == (512, 64, 9),
        "governed sample counts",
    )
    _require(
        type(batch_iterations) is int
        and 1 <= batch_iterations <= policy["maximum_batch_iterations"],
        "fixed batch",
    )
    if not key[0].startswith("latency:") or key[0] == "latency:cli-startup":
        _require(batch_iterations == 1, "non-batched measurement")
    _require(
        set(artifacts) == {"runner", "kernel", "interop", "memory_worker"},
        "complete artifact roles",
    )
    _require(
        artifacts["memory_worker"]
        == artifacts["runner"].with_name("strling-performance-memory-worker.exe"),
        "runner-local memory worker",
    )
    manifest_path = root / controller.MANIFEST_PATH.relative_to(controller.ROOT)
    required = {
        manifest_path,
        *artifacts.values(),
        *(
            root / manifest[field]["path"]
            for field in ("fixture_manifest", "resource_inventory")
        ),
    }
    _require(required <= inputs.keys(), "missing pinned workload input")
    _check_inputs(inputs)
    _require(
        _strict_json(manifest_path.read_bytes()) == manifest,
        "manifest differs from pinned input",
    )
    for field in ("fixture_manifest", "resource_inventory"):
        _require(
            inputs[root / manifest[field]["path"]] == manifest[field]["sha256"],
            "manifest dependency changed",
        )
    _source(root, source_sha)
    # Validate the exact environment and primitive plan before consuming a slot.
    spec = envelope.Command(
        command=(str(artifacts["runner"]),),
        cwd=root,
        environment=process_environment,
        inputs=inputs,
        source_sha=source_sha,
        selected_cpu=policy["selected_logical_cpu"],
        timeout_seconds=1800,
    )
    envelope._validate(spec)
    directory.mkdir(exist_ok=False)
    plan = dict(
        contract="unqualified-enclosed-coordinate-v1",
        source_sha=source_sha,
        coordinate=list(key),
        batch_iterations=batch_iterations,
        manifest=manifest,
        environment=environment,
        artifacts={k: str(p) for k, p in artifacts.items()},
        inputs={str(p): h for p, h in inputs.items()},
        process_environment_sha256=hashlib.sha256(
            json.dumps(process_environment, sort_keys=True).encode()
        ).hexdigest(),
        adapter_sha256=envelope._hash(Path(__file__)),
        controller_sha256=envelope._hash(Path(controller.__file__)),
    )
    envelope._save(directory / "plan.json", plan)
    result = dict(
        contract=plan["contract"],
        status="failed",
        authoritative=False,
        certification_eligible=False,
        baseline_admission=False,
        plan_sha256=envelope._hash(directory / "plan.json"),
        process_envelope=None,
        coordinate=list(key),
    )
    events = []

    def run(command, **options):
        _require(
            options
            == dict(cwd=root, check=True, capture_output=True, text=True, timeout=1800),
            "unknown process options",
        )
        _require(
            command[0] == str(artifacts["runner"]), "unexpected measurement executable"
        )
        _require(result["process_envelope"] is None, "one process per coordinate")
        row = envelope.capture(
            envelope.Command(
                command=tuple(command),
                cwd=root,
                environment=process_environment,
                inputs=inputs,
                source_sha=source_sha,
                selected_cpu=policy["selected_logical_cpu"],
                timeout_seconds=1800,
            ),
            directory / "process",
        )
        result["process_envelope"] = dict(
            path="process/terminal.json",
            sha256=envelope._hash(directory / "process/terminal.json"),
        )
        _require(row.get("status") == "observed", "process envelope failed")
        stdout = (directory / "process/stdout.bin").read_bytes().decode("utf-8")
        stderr = (directory / "process/stderr.bin").read_bytes().decode("utf-8")
        _require(type(_strict_json(stdout)) is dict, "runner JSON object required")
        return subprocess.CompletedProcess(command, row["exit_code"], stdout, stderr)

    try:
        result["acquisition_begin_ns"] = time.perf_counter_ns()
        with controller._retain_measurement_processes(events.append):
            observation = controller._measure_key(
                key,
                manifest=manifest,
                artifacts=artifacts,
                environment=environment,
                batch_iterations=batch_iterations,
                process_executor=run,
                root=root,
            )
        result["acquisition_end_ns"] = time.perf_counter_ns()
        # This outer span includes transport validation and is NOT the native
        # whole-action interval. The latter lives in the pinned process receipt.
        _check_inputs(inputs)
        _source(root, source_sha)
        _require(
            envelope._hash(Path(__file__)) == plan["adapter_sha256"]
            and envelope._hash(Path(controller.__file__)) == plan["controller_sha256"],
            "acquisition implementation changed",
        )
        result.update(status="observed", observation=observation)
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        envelope._save(directory / "process-events.json", events)
        result["process_events_sha256"] = envelope._hash(
            directory / "process-events.json"
        )
        envelope._save(directory / "terminal.json", result)
    return result
