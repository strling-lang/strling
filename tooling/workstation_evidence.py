"""Independent data-only reconstruction of shared-workstation observations.

The caller binds the prospective plan and injects a trusted process verifier.
No producer, process-control or filesystem imports are used.
"""

import base64
import json
import re


def need(value, message):
    if not value:
        raise ValueError(message)


def integer(value, minimum=0, maximum=2**64 - 1):
    need(type(value) is int and minimum <= value <= maximum, "exact integer")
    return value


def parse(data):
    need(type(data) is bytes and len(data) <= 64 * 1024 * 1024, "bounded raw bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite JSON")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def vector(value, count, minimum=1):
    need(type(value) is list and len(value) == count, "complete sample vector")
    for item in value:
        integer(item, minimum)
    return value


def _memory(raw, files, root_before, root_after):
    need(
        raw["memory_worker_contract"] == "shared-workstation-memory-v1",
        "memory contract",
    )
    life = raw["memory_lifetime"]
    need(
        type(life) is dict
        and set(life)
        == set(
            "contract pid birth_100ns exit_100ns worker_reported_peak_rss_bytes terminal_peak_rss_bytes residency_qualified descendant_coverage_qualified observer_effects_qualified".split()
        ),
        "closed lifetime",
    )
    need(life["contract"] == "retained-process-terminal-peak-v1", "lifetime contract")
    for key in (
        "residency_qualified",
        "descendant_coverage_qualified",
        "observer_effects_qualified",
    ):
        need(life[key] is False, "no inherited laboratory assertion")
    child_pid = integer(life["pid"], 1, 2**32 - 1)
    birth = integer(life["birth_100ns"], 1)
    exited = integer(life["exit_100ns"], birth + 1)
    need(
        int(root_before["birth"]) <= birth < exited <= int(root_after["exit"]),
        "child within root lifetime",
    )
    peak = integer(raw["peak_working_set_bytes"], 1)
    need(integer(life["terminal_peak_rss_bytes"], 1) == peak, "terminal raw RSS")
    integer(life["worker_reported_peak_rss_bytes"], 1, peak)
    commit = raw["workstation_memory"]
    need(
        type(commit) is dict
        and set(commit)
        == set(
            "contract peak_commit_bytes worker_reported_peak_commit_bytes single_process_job observer_scope".split()
        ),
        "closed commit evidence",
    )
    need(commit["contract"] == "process-lifetime-peak-commit-v1", "commit contract")
    need(commit["single_process_job"] is True, "one-process job required")
    need(commit["observer_scope"] == "parent-outside-measured-worker", "observer scope")
    peak_commit = integer(commit["peak_commit_bytes"], 1)
    integer(commit["worker_reported_peak_commit_bytes"], 1, peak_commit)
    packets = []
    for line in files["stderr.bin"].splitlines():
        if line.startswith(b"{") and b'"retained-memory-worker-streams-v1"' in line:
            packets.append(parse(line))
    need(len(packets) == 1, "one exact memory child stream packet")
    packet = packets[0]
    need(
        type(packet) is dict
        and set(packet)
        == set(
            "contract pid birth_100ns input_bytes stdout_bytes stderr_bytes success".split()
        ),
        "closed child packet",
    )
    need(
        packet["success"] is True
        and integer(packet["pid"], 1, 2**32 - 1) == child_pid
        and integer(packet["birth_100ns"], 1) == birth,
        "successful exact child",
    )
    for key in ("input_bytes", "stdout_bytes", "stderr_bytes"):
        need(
            type(packet[key]) is list and len(packet[key]) <= 64 * 1024 * 1024,
            "raw child bytes",
        )
        if key != "stderr_bytes":
            need(len(packet[key]) > 0, "nonempty child transport")
        for item in packet[key]:
            integer(item, 0, 255)
    request = parse(bytes(packet["input_bytes"]))
    need(type(request) is dict and request, "actual compiler request")
    reply = parse(bytes(packet["stdout_bytes"]))
    need(reply["worker_contract"] == "shared-workstation-memory-v1", "child context")
    need(reply["certification_context"] == "shared-workstation-v1", "child context")
    need(reply["sample_retention"] == "all-fixed-slots-v1", "child fixed slots")
    need(
        reply["effective_cpu_affinity"] == raw["effective_cpu_affinity"],
        "child placement",
    )
    need(
        integer(reply["peak_working_set_bytes"], 1)
        == life["worker_reported_peak_rss_bytes"],
        "child RSS report",
    )
    need(
        integer(reply["peak_commit_bytes"], 1)
        == commit["worker_reported_peak_commit_bytes"],
        "child commit report",
    )
    need(
        integer(reply["sample_attempts"], 1) == raw["sample_attempts"],
        "child attempt count",
    )
    need(
        integer(reply["checksum"]) == integer(raw["checksum"]),
        "child semantic result binding",
    )
    return peak_commit, (child_pid, birth)


def verify_observation(
    files,
    terminal_sha256,
    expected_plan,
    *,
    coordinate,
    batch,
    policy,
    process_verifier,
    negative_control=False,
):
    """Caller supplies independently bound plan, policy and pure process verifier."""
    checked = process_verifier(files, terminal_sha256, expected_plan)
    operation, fixture = coordinate
    memory = operation.startswith("memory:")
    cli = operation == "latency:cli-startup"
    raw = parse(files["stdout.bin"])
    need(type(raw) is dict, "raw runner object")
    need(
        raw["operation_id"] == operation and raw["fixture_id"] == fixture, "coordinate"
    )
    need(raw["certification_context"] == "shared-workstation-v1", "explicit context")
    quota = raw["cpu_quota"]
    need(type(quota) is str, "quota observation text")
    if quota != "observed-no-job-at-query":
        matched = re.fullmatch(
            r"observed-immediate-job:flags=(0|[1-9][0-9]{0,9}):rate=(0|[1-9][0-9]{0,9}):ancestors=unknown",
            quota,
        )
        need(matched is not None, "explicit raw quota observation")
        integer(int(matched.group(1)), 0, 2**32 - 1)
        integer(int(matched.group(2)), 0, 2**32 - 1)
    cpu = integer(expected_plan["selected_cpu"], 0, 63)
    need(
        integer(raw["selected_logical_cpu"], 0, 63) == cpu
        and raw["effective_cpu_affinity"] == [cpu]
        and type(raw["effective_cpu_affinity"][0]) is int,
        "selected placement",
    )
    need(
        raw["platform"] == "windows" and integer(raw["processor_group"]) == 0,
        "native platform",
    )
    need(
        raw["observed_processor_groups"] == [0]
        and raw["observed_logical_processors"] == [cpu],
        "observed placement",
    )
    need(
        all(
            type(x) is int
            for x in raw["observed_processor_groups"]
            + raw["observed_logical_processors"]
        ),
        "exact processor observations",
    )
    need(raw["unit"] == "nanoseconds", "raw protocol unit")
    warmups = (
        1 if memory else policy["cli_warmups"] if cli else policy["latency_warmups"]
    )
    count = 1 if memory else policy["latency_samples"]
    need(integer(raw["warmup_iterations"], 1) == warmups, "warmups")
    need(integer(raw["sample_iterations"], 1) == count, "sample count")
    need(integer(raw["batch_iterations"], 1, 4096) == batch, "prospective batch")
    need(
        integer(raw["maximum_descheduling_nanoseconds"]) == 50_000_000,
        "sample authenticity rule",
    )
    retain_all = policy.get("sample_retention") == "all-fixed-slots-v1"
    maximum = count if retain_all else 2 * count
    need(integer(raw["maximum_sample_attempts"], 1) == maximum, "attempt bound")
    attempts = integer(raw["sample_attempts"], count, maximum)
    if retain_all:
        need(
            raw.get("sample_retention") == "all-fixed-slots-v1",
            "fixed raw sample retention",
        )
        need(attempts == count, "no replacement attempts")
    before, after = parse(files["suspended.json"]), parse(files["root-exit.json"])
    result = dict(
        identity=(checked["pid"], int(checked["birth"])),
        begin_ns=parse(files["terminal.json"])["action_begin_ns"],
        end_ns=parse(files["terminal.json"])["action_end_ns"],
        whole_action_ns=checked["whole_action_ns"],
        raw=raw,
        terminal_sha256=terminal_sha256,
    )
    if memory:
        need(batch == 1 and not negative_control, "memory role")
        result["peak_commit_bytes"], result["memory_identity"] = _memory(
            raw, files, before, after
        )
        for name in ("samples", "batch_elapsed_samples", "control_samples"):
            need(raw[name] == [], "memory is singleton native counter")
        return result
    need(
        raw["measurement_role"]
        == ("slowdown-control" if negative_control else "ordinary"),
        "build role",
    )
    samples = vector(raw["samples"], count)
    batches = vector(raw["batch_elapsed_samples"], count)
    need(
        samples == [max(1, min(2**64 - 1, x + batch // 2) // batch) for x in batches],
        "batch arithmetic",
    )
    cpu_batches = vector(raw["process_cpu_batch_elapsed_samples"], count)
    cpu_samples = vector(raw["process_cpu_samples"], count)
    need(
        cpu_samples
        == [max(1, min(2**64 - 1, x + batch // 2) // batch) for x in cpu_batches],
        "CPU normalization",
    )
    utilization = vector(raw["process_cpu_utilization_basis_points"], count, 0)
    need(
        utilization
        == [min(10000, c * 10000 // w) for c, w in zip(cpu_batches, batches)],
        "raw CPU accounting arithmetic",
    )
    if not cli and not retain_all:
        need(
            all(max(0, w - c) <= 50_000_000 for w, c in zip(batches, cpu_batches)),
            "legacy accepted-attempt rule",
        )
    rejected = vector(
        raw["rejected_batch_elapsed_samples"], 0 if cli else attempts - count
    )
    rejected_cpu = vector(
        raw["rejected_process_cpu_batch_elapsed_samples"], len(rejected)
    )
    rejected_utilization = vector(
        raw["rejected_process_cpu_utilization_basis_points"], len(rejected), 0
    )
    need(
        rejected_utilization
        == [min(10000, c * 10000 // w) for c, w in zip(rejected_cpu, rejected)],
        "rejected CPU arithmetic",
    )
    if retain_all:
        need(not rejected, "no discarded workstation slots")
    elif not cli:
        need(
            all(max(0, w - c) > 50_000_000 for w, c in zip(rejected, rejected_cpu)),
            "legacy rejection rule",
        )
    if cli:
        need(batch == 1 and attempts == count, "complete CLI pairs")
        vector(raw["control_samples"], count)
        vector(raw["control_batch_elapsed_samples"], count)
        need(
            raw["control_samples"] == raw["control_batch_elapsed_samples"],
            "CLI control duration",
        )
        vector(raw["control_process_cpu_samples"], count)
        vector(raw["control_process_cpu_batch_elapsed_samples"], count)
        vector(raw["control_process_cpu_utilization_basis_points"], count, 0)
        need(
            raw["control_process_cpu_samples"]
            == raw["control_process_cpu_batch_elapsed_samples"],
            "CLI control CPU normalization",
        )
        need(
            raw["control_process_cpu_utilization_basis_points"]
            == [
                min(10000, c * 10000 // w)
                for c, w in zip(
                    raw["control_process_cpu_batch_elapsed_samples"],
                    raw["control_batch_elapsed_samples"],
                )
            ],
            "CLI control CPU arithmetic",
        )
        need(
            raw["cli_launch_schedule"] == "half-complementary-adjacent-pairs-64-v1",
            "CLI launch schedule",
        )
        need(
            type(raw["request_first"]) is list
            and len(raw["request_first"]) == count
            and all(type(x) is bool for x in raw["request_first"]),
            "exact CLI order",
        )
        need(
            raw["request_first"] == [i >= 32 for i in range(count)],
            "prospective CLI order",
        )
    else:
        need(
            raw["control_samples"] == [] and raw["control_batch_elapsed_samples"] == [],
            "no invented control samples",
        )
    duration_sum = sum(batches) + sum(rejected)
    if cli:
        duration_sum += sum(raw["control_batch_elapsed_samples"])
    need(
        duration_sum <= checked["whole_action_ns"],
        "serial sample durations exceed whole process interval",
    )
    result["samples"] = samples
    result["control_samples"] = raw["control_samples"]
    return result


def worker_command(artifacts, coordinate, batch, policy, *, calibration=False):
    """The one versioned command recipe, reconstructed before process validation."""
    operation, fixture = coordinate
    memory = operation.startswith("memory:")
    cli = operation == "latency:cli-startup"
    command = [
        artifacts["runner"]["path"],
        "--operation",
        operation,
        "--fixture",
        fixture,
        "--warmups",
        str(
            1 if memory else policy["cli_warmups"] if cli else policy["latency_warmups"]
        ),
        "--samples",
        str(1 if memory else policy["latency_samples"]),
        "--expected-logical-cpu",
        "1",
        "--certification-context",
        "shared-workstation-v1",
    ]
    if not memory:
        command += [
            "--maximum-batch-iterations",
            str(1 if cli else policy["maximum_batch_iterations"]),
        ]
        command += (
            [
                "--minimum-sample-nanoseconds",
                str(policy["calibration_minimum_nanoseconds"]),
            ]
            if calibration
            else ["--batch-iterations", str(batch)]
        )
    if cli:
        need(not calibration, "no CLI calibration")
        command += [
            "--kernel-bin",
            artifacts["kernel"]["path"],
            "--cli-launch-schedule",
            "half-complementary-adjacent-pairs-64-v1",
        ]
    return command


def verify_cohort(
    document,
    *,
    coordinates,
    policy,
    source_sha,
    policy_sha256,
    manifest_sha256,
    build_identities,
    implementation_pins,
    process_verifier,
    latency_scorer,
    memory_scorer,
):
    """Reconstruct the complete denominator, order, source roles and all decisions.

    Build identities and implementation hashes must be supplied independently
    by the caller, never copied from this candidate evidence document.
    """
    need(document["contract"] == "shared-workstation-cohort-v2", "cohort contract")
    need(
        document["source_sha"] == source_sha
        and document["policy_sha256"] == policy_sha256
        and document["manifest_sha256"] == manifest_sha256,
        "source and policy binding",
    )
    need(document["builds"] == build_identities, "independently pinned builds")
    need(
        set(build_identities) == {"reference", "candidate", "slowdown"},
        "independent ordinary/control builds",
    )
    for lane, build in build_identities.items():
        need(
            set(build["artifacts"]) == {"runner", "memory_worker", "kernel", "interop"},
            "complete native artifacts",
        )
        need(build["negative_control"] is (lane == "slowdown"), "build role")
        need(
            build["kernel_revision"]
            == (policy["reference_source"] if lane == "reference" else source_sha),
            "kernel source role",
        )
    need(
        len({x["build_root"] for x in build_identities.values()}) == 3,
        "three independent build roots",
    )
    records = document["observations"]
    need(type(records) is list, "observation denominator")
    cursor = 0
    identities, slots = set(), set()
    previous_end = 0
    decisions = []

    def take(coordinate, lane, purpose, repetition, batch, calibration=False):
        nonlocal cursor, previous_end
        need(cursor < len(records), "missing prospective observation")
        row = records[cursor]
        cursor += 1
        need(
            row["coordinate"] == list(coordinate)
            and row["lane"] == lane
            and row["purpose"] == purpose
            and row["repetition"] == repetition,
            "prospective coordinate/order/role",
        )
        need(type(row["slot"]) is str and row["slot"] not in slots, "unique slot")
        slots.add(row["slot"])
        plan = row["expected_plan"]
        command = worker_command(
            build_identities[lane]["artifacts"],
            coordinate,
            batch,
            policy,
            calibration=calibration,
        )
        need(
            plan["command"] == command
            and plan["source_sha"] == source_sha
            and integer(plan["selected_cpu"], 0, 63) == 1,
            "independent command recipe",
        )
        for key, value in implementation_pins.items():
            need(plan[key] == value, "measurement implementation binding")
        for artifact in build_identities[lane]["artifacts"].values():
            need(
                plan["inputs"].get(artifact["path"]) == artifact["sha256"],
                "actual binary binding",
            )
        need(type(row["files"]) is dict, "raw files")
        files = {
            name: base64.b64decode(value, validate=True)
            for name, value in row["files"].items()
        }
        actual_batch = (
            parse(files["stdout.bin"])["batch_iterations"] if calibration else batch
        )
        checked = verify_observation(
            files,
            row["terminal_sha256"],
            plan,
            coordinate=coordinate,
            batch=actual_batch,
            policy=policy,
            process_verifier=process_verifier,
            negative_control=lane == "slowdown",
        )
        need(checked["identity"] not in identities, "process reused")
        identities.add(checked["identity"])
        if "memory_identity" in checked:
            need(checked["memory_identity"] not in identities, "memory process reused")
            identities.add(checked["memory_identity"])
        need(
            checked["begin_ns"] >= previous_end, "overlapping or reordered acquisitions"
        )
        previous_end = checked["end_ns"]
        return checked, actual_batch

    for coordinate in coordinates:
        operation, _ = coordinate
        if operation == "size:kernel-artifacts":
            sizes = {
                lane: sum(
                    integer(build_identities[lane]["artifacts"][kind]["bytes"])
                    for kind in ("kernel", "interop")
                )
                for lane in ("reference", "candidate")
            }
            passed = sizes["candidate"] * 10000 <= sizes["reference"] * 11000
            decisions.append(
                dict(
                    coordinate=list(coordinate),
                    passed=passed,
                    metric="kernel-plus-interop-bytes",
                    sizes=sizes,
                )
            )
            continue
        batch = 1
        if not operation.startswith("memory:") and operation != "latency:cli-startup":
            _, batch = take(
                coordinate, "reference", "calibration", None, None, calibration=True
            )
        pairs = []
        for repetition, reference_first in enumerate(policy["reference_first"]):
            pair = {}
            for lane in (
                ("reference", "candidate")
                if reference_first
                else ("candidate", "reference")
            ):
                pair[lane], _ = take(coordinate, lane, "ordinary", repetition, batch)
            pairs.append(pair)
        if operation.startswith("memory:"):
            decision = memory_scorer(
                [
                    {
                        lane: pair[lane]["peak_commit_bytes"]
                        for lane in ("reference", "candidate")
                    }
                    for pair in pairs
                ],
                policy,
            )
        else:
            decision = latency_scorer(
                pairs, policy, cli=operation == "latency:cli-startup"
            )
        decisions.append(dict(coordinate=list(coordinate), **decision))
    control_coordinate = ("latency:semantic-parse", "fixture:semantic-tiny")
    _, batch = take(
        control_coordinate,
        "reference",
        "negative-calibration",
        None,
        None,
        calibration=True,
    )
    pairs = []
    for repetition, reference_first in enumerate(policy["reference_first"]):
        pair = {}
        for lane in (
            ("reference", "slowdown") if reference_first else ("slowdown", "reference")
        ):
            checked, _ = take(control_coordinate, lane, "negative", repetition, batch)
            pair["reference" if lane == "reference" else "candidate"] = checked
        pairs.append(pair)
    control = latency_scorer(pairs, policy)
    need(control["passed"] is False, "real slowdown discrimination required")
    need(cursor == len(records), "unexpected/unconsumed observations")
    return dict(
        decisions=decisions,
        negative_control=control,
        observations=cursor,
        unique_processes=len(identities),
    )
