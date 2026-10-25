"""Fresh native acquisition for the explicitly scoped workstation policy.

This entry point is qualification engineering. Profile adoption requires the
independent reader, functional resource checks and trusted attestation routing.
The caller retains exclusive source ownership for the complete invocation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from tooling import performance_envelope_receipts as process_reader
from tooling import performance_process_envelope as envelope
from tooling import performance_resource_certification as governed
from tooling import workstation_builds as builds
from tooling import workstation_evidence as reader
from tooling import workstation_performance as score

MANIFEST = Path("tests/certification/performance-resource/1.0/manifest.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def source_identity(root):
    def git(*args):
        return (
            subprocess.check_output(["git", "--no-optional-locks", *args], cwd=root)
            .decode()
            .strip()
        )

    if git("status", "--porcelain"):
        raise ValueError("fresh clean candidate source required")
    return git("rev-parse", "HEAD")


def acquire(root, output, *, cargo, rustc, coordinates=None):
    """No retry, slot filling, candidate calibration or compiled artifact reuse."""
    if os.name != "nt":
        raise ValueError("native Windows acquisition required")
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "target"):
        raise ValueError("qualification output must be inside target")
    source = source_identity(root)
    output.mkdir(exist_ok=False)
    policy = score.load_policy(root / "governance/workstation-performance-policy.json")
    manifest = governed.load_json(root / MANIFEST)
    complete_coordinates = governed.performance_measurement_keys(manifest)
    coordinates = complete_coordinates if coordinates is None else coordinates
    if any(tuple(key) not in complete_coordinates for key in coordinates):
        raise ValueError("unknown workload coordinate")
    environment = dict(os.environ)
    implementation_pins = dict(
        implementation_sha256=digest(Path(envelope.__file__)),
        job_implementation_sha256=digest(
            root / "tooling/performance_build_execution.py"
        ),
        controls_implementation_sha256=digest(root / "tooling/performance_windows.py"),
        observation_implementation_sha256=digest(
            root / "tooling/performance_process_observation.py"
        ),
        cwd=str(root),
        timeout_seconds=300,
        environment_sha256=hashlib.sha256(
            json.dumps(environment, sort_keys=True).encode()
        ).hexdigest(),
    )
    document = dict(
        contract="shared-workstation-cohort-v2",
        source_sha=source,
        policy_sha256=digest(root / "governance/workstation-performance-policy.json"),
        manifest_sha256=digest(root / MANIFEST),
        builds={},
        observations=[],
    )
    prospective = dict(
        source_sha=source,
        policy=policy,
        coordinates=[list(x) for x in coordinates],
        full_coordinate_qualification=coordinates == complete_coordinates,
        implementation_pins=implementation_pins,
        candidate_calibration=False,
        no_retries=True,
        negative_control_coordinate=["latency:semantic-parse", "fixture:semantic-tiny"],
    )
    save(output / "prospective-plan.json", prospective)
    started = time.monotonic()
    terminal = dict(
        status="failed", full_coordinate_qualification=False, source_sha=source
    )
    seen, previous_end = set(), 0

    def observe(coordinate, lane, purpose, repetition, batch=None, calibration=False):
        nonlocal previous_end
        slot = f"slot-{len(document['observations']):04d}"
        artifacts = document["builds"][lane]["artifacts"]
        command = reader.worker_command(
            artifacts, coordinate, batch, policy, calibration=calibration
        )
        inputs = {Path(item["path"]): item["sha256"] for item in artifacts.values()}
        inputs.update(
            {
                output / lane / "recipe.json": document["builds"][lane][
                    "recipe_sha256"
                ],
                root / "governance/workstation-performance-policy.json": document[
                    "policy_sha256"
                ],
                root / MANIFEST: document["manifest_sha256"],
            }
        )
        expected = dict(
            command=command,
            source_sha=source,
            selected_cpu=1,
            inputs={str(path): pin for path, pin in inputs.items()},
            **implementation_pins,
        )
        save(output / (slot + "-expected-plan.json"), expected)
        # Persist a consumed prospective slot BEFORE invoking the native producer.
        save(
            output / (slot + "-intent.json"),
            dict(
                coordinate=list(coordinate),
                lane=lane,
                purpose=purpose,
                repetition=repetition,
                batch=batch,
                calibration=calibration,
            ),
        )
        acquired = envelope.capture(
            envelope.Command(tuple(command), root, environment, inputs, source, 1, 300),
            output / slot,
        )
        if acquired["status"] != "observed":
            raise ValueError(
                slot + " failed; prospective slot consumed and raw failure retained"
            )
        files = {
            name: (output / slot / name).read_bytes() for name in process_reader.FILES
        }
        pin = digest(output / slot / "terminal.json")
        actual_batch = (
            reader.parse(files["stdout.bin"])["batch_iterations"]
            if calibration
            else batch
        )
        checked = reader.verify_observation(
            files,
            pin,
            expected,
            coordinate=coordinate,
            batch=actual_batch,
            policy=policy,
            process_verifier=process_reader.verify_process_receipt,
            negative_control=lane == "slowdown",
        )
        if checked["identity"] in seen or checked["begin_ns"] < previous_end:
            raise ValueError("process reuse or overlapping acquisition")
        seen.add(checked["identity"])
        previous_end = checked["end_ns"]
        document["observations"].append(
            dict(
                slot=slot,
                coordinate=list(coordinate),
                lane=lane,
                purpose=purpose,
                repetition=repetition,
                terminal_sha256=pin,
                expected_plan=expected,
                files={
                    name: base64.b64encode(data).decode("ascii")
                    for name, data in files.items()
                },
            )
        )
        print(
            json.dumps(
                dict(
                    slot=slot,
                    coordinate=coordinate,
                    lane=lane,
                    purpose=purpose,
                    pid=checked["identity"][0],
                    whole_action_ns=checked["whole_action_ns"],
                )
            ),
            flush=True,
        )
        return checked, actual_batch

    try:
        # Functional and native memory qualification remain required even on a
        # shared host. They do not depend on the empirical timing outcome.
        native_test = output / "native-memory-lifetime.exe"
        qualification_environment = dict(environment, RUSTC=str(rustc))
        builds._run(
            [
                str(rustc),
                "--edition=2021",
                "--test",
                str(root / "tooling/tests/memory_worker_lifetime.rs"),
                "-o",
                str(native_test),
            ],
            root=root,
            directory=output,
            name="native-memory-test-build",
            environment=qualification_environment,
        )
        builds._run(
            [str(native_test), "--test-threads=1", "--nocapture"],
            root=root,
            directory=output,
            name="native-memory-tests",
            environment=qualification_environment,
        )
        terminal["native_memory_qualification"] = dict(
            status="passed",
            binary_sha256=digest(native_test),
            source_sha256=digest(root / "tooling/tests/memory_worker_lifetime.rs"),
            stdout_sha256=digest(output / "native-memory-tests.stdout"),
            stderr_sha256=digest(output / "native-memory-tests.stderr"),
        )
        override_names = {
            "STRLING_PERFORMANCE_CARGO": str(cargo),
            "STRLING_PERFORMANCE_RUSTC": str(rustc),
        }
        old_environment = {key: os.environ.get(key) for key in override_names}
        try:
            os.environ.update(override_names)
            resource_checks = governed._resource_checks(root)
        finally:
            for key, value in old_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        save(output / "functional-resource-checks.json", resource_checks)
        terminal["functional_resource_qualification"] = all(
            row["status"] == "passed" for row in resource_checks
        )
        for lane in ("reference", "candidate", "slowdown"):
            print(json.dumps(dict(stage="build-started", lane=lane)), flush=True)
            document["builds"][lane] = builds.build_lane(
                root,
                output / lane,
                kernel_revision=policy["reference_source"]
                if lane == "reference"
                else source,
                harness_root=root,
                cargo=cargo,
                rustc=rustc,
                slowdown=lane == "slowdown",
            )
            print(json.dumps(dict(stage="build-passed", lane=lane)), flush=True)
        for index, coordinate in enumerate(coordinates):
            if coordinate[0] == "size:kernel-artifacts":
                continue
            batch = 1
            if (
                not coordinate[0].startswith("memory:")
                and coordinate[0] != "latency:cli-startup"
            ):
                _, batch = observe(
                    coordinate, "reference", "calibration", None, calibration=True
                )
            save(
                output / f"coordinate-{index:02d}-frozen.json",
                dict(
                    coordinate=list(coordinate),
                    batch=batch,
                    reference_first=policy["reference_first"],
                    pairs=policy["paired_repetitions"],
                ),
            )
            for repetition, reference_first in enumerate(policy["reference_first"]):
                for lane in (
                    ("reference", "candidate")
                    if reference_first
                    else ("candidate", "reference")
                ):
                    observe(coordinate, lane, "ordinary", repetition, batch)
        coordinate = ("latency:semantic-parse", "fixture:semantic-tiny")
        _, batch = observe(
            coordinate, "reference", "negative-calibration", None, calibration=True
        )
        save(
            output / "negative-frozen.json",
            dict(
                coordinate=list(coordinate),
                batch=batch,
                reference_first=policy["reference_first"],
                pairs=policy["paired_repetitions"],
            ),
        )
        for repetition, reference_first in enumerate(policy["reference_first"]):
            for lane in (
                ("reference", "slowdown")
                if reference_first
                else ("slowdown", "reference")
            ):
                observe(coordinate, lane, "negative", repetition, batch)
        # Seal exact bytes before invoking the independent data-only cohort reader.
        save(output / "cohort.json", document)
        reconstructed = reader.verify_cohort(
            json.loads((output / "cohort.json").read_bytes()),
            coordinates=coordinates,
            policy=policy,
            source_sha=source,
            policy_sha256=document["policy_sha256"],
            manifest_sha256=document["manifest_sha256"],
            build_identities={
                lane: json.loads((output / lane / "built.json").read_bytes())
                for lane in ("reference", "candidate", "slowdown")
            },
            implementation_pins=implementation_pins,
            process_verifier=process_reader.verify_process_receipt,
            latency_scorer=score.guarded_latency_decision,
            memory_scorer=score.memory_decision,
        )
        save(output / "independent-reconstruction.json", reconstructed)
        operations = {op["id"]: op for op in manifest["operations"]}
        failures = [
            row["coordinate"]
            for row in reconstructed["decisions"]
            if not row["passed"]
            and operations[row["coordinate"][0]]["enforcement"] == "hard"
        ]
        terminal.update(
            status="failed"
            if failures or not terminal["functional_resource_qualification"]
            else "passed",
            hard_failures=failures,
            full_coordinate_qualification=coordinates == complete_coordinates,
            observations=reconstructed["observations"],
            cohort_sha256=digest(output / "cohort.json"),
            independent_reconstruction_sha256=digest(
                output / "independent-reconstruction.json"
            ),
        )
    except BaseException as error:
        terminal["error"] = repr(error)
        if not (output / "cohort.json").exists():
            save(output / "partial-cohort.json", document)
    finally:
        terminal["elapsed_seconds"] = time.monotonic() - started
        try:
            terminal["source_unchanged"] = source_identity(root) == source
        except (ValueError, subprocess.SubprocessError) as error:
            terminal["source_unchanged"] = False
            terminal["source_error"] = repr(error)
        if not terminal["source_unchanged"]:
            terminal["status"] = "failed"
        save(output / "terminal.json", terminal)
    return terminal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    args = parser.parse_args(argv)
    result = acquire(
        Path(__file__).resolve().parent.parent,
        args.output,
        cargo=args.cargo,
        rustc=args.rustc,
    )
    print(json.dumps(result), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
