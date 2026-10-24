"""Pure byte-bound acquisition/cohort reconstruction; no performance admission.

This reader imports neither the acquisition producer nor its controller. External
plans and terminal pins must be supplied independently. Build provenance, source
ownership, conditioning, empirical independence and trusted verification remain
separate obligations; self-consistent bytes cannot establish them.
"""

import json
from pathlib import PureWindowsPath

from tooling import performance_envelope_receipts as receipt
from tooling import performance_reference_bounds as bounds

need = receipt._need
integer = receipt._integer
sha = receipt._sha
parse = receipt._parse
shape = receipt._shape

FILES = {"plan.json", "terminal.json", "manifest.json", "process-events.json"} | {
    "process/" + name for name in receipt.FILES
}
PLAN = set(
    "contract source_sha coordinate batch_iterations manifest environment artifacts inputs process_environment_sha256 adapter_sha256 controller_sha256".split()
)
TERMINAL = set(
    "contract status authoritative certification_eligible baseline_admission plan_sha256 process_envelope coordinate acquisition_begin_ns acquisition_end_ns observation process_events_sha256".split()
)
RENAMED = {
    "batch_duration_samples": "batch_elapsed_samples",
    "process_cpu_batch_duration_samples": "process_cpu_batch_elapsed_samples",
    "rejected_batch_duration_samples": "rejected_batch_elapsed_samples",
    "rejected_process_cpu_batch_duration_samples": "rejected_process_cpu_batch_elapsed_samples",
    "control_batch_duration_samples": "control_batch_elapsed_samples",
    "control_process_cpu_batch_duration_samples": "control_process_cpu_batch_elapsed_samples",
}
COPIED = "samples batch_iterations process_cpu_samples process_cpu_utilization_basis_points maximum_descheduling_nanoseconds maximum_sample_attempts sample_attempts rejected_process_cpu_utilization_basis_points control_samples control_process_cpu_samples control_process_cpu_utilization_basis_points".split()
DENIALS = dict(
    authoritative=False,
    certification_eligible=False,
    baseline_admission=False,
    ancestor_quota_qualified=False,
    build_provenance_qualified=False,
    independence_qualified=False,
)


def encode(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("invalid supplied JSON") from error


def equal(actual, expected, message):
    # JSON spelling distinguishes booleans/floats from exact integers at every
    # depth, unlike Python container equality. Parsed inputs reject duplicate keys.
    need(encode(actual) == encode(expected), message)


def _array(raw, name, count, minimum=0):
    values = raw.get(name)
    need(type(values) is list and len(values) == count, "complete raw " + name)
    for value in values:
        integer(value, minimum)
    return values


def _command(plan, process):
    policy = plan["manifest"]["measurement_policy"]
    key = plan["coordinate"]
    operations = [o for o in plan["manifest"]["operations"] if o["id"] == key[0]]
    need(
        len(operations) == 1 and key[1] in operations[0]["fixture_ids"],
        "manifest coordinate",
    )
    operation = operations[0]
    memory = operation["measurement_kind"] == "peak-rss"
    need(
        memory or operation["measurement_kind"] == "latency",
        "process coordinate required",
    )
    for key_name, value in (
        ("warmup_iterations", 512),
        ("sample_iterations", 64),
        ("baseline_repetitions", 9),
    ):
        need(integer(policy[key_name]) == value, "original workload counts")
    batch = integer(
        plan["batch_iterations"], 1, integer(policy["maximum_batch_iterations"], 1)
    )
    cli = key[0] == "latency:cli-startup"
    need(not (memory or cli) or batch == 1, "unbatched workload")
    equal(process["selected_cpu"], policy["selected_logical_cpu"], "selected CPU")
    need(process["timeout_seconds"] == 1800, "acquisition deadline")
    command = [
        plan["artifacts"]["runner"],
        "--operation",
        key[0],
        "--fixture",
        key[1],
        "--warmups",
        "1" if memory else "512",
        "--samples",
        "1" if memory else "64",
    ]
    if not memory:
        command += [
            "--maximum-batch-iterations",
            str(policy["maximum_batch_iterations"]),
        ]
    command += ["--expected-logical-cpu", str(policy["selected_logical_cpu"])]
    if not memory:
        command += ["--batch-iterations", str(batch)]
    if cli:
        command += ["--kernel-bin", plan["artifacts"]["kernel"]]
        if (
            operation.get("relative_estimator")
            == "exact-ratio-of-all-sample-marginal-medians"
        ):
            command += [
                "--cli-launch-schedule",
                "half-complementary-adjacent-pairs-64-v1",
            ]
    equal(process["command"], command, "exact governed command")
    return memory, cli


def _projection(raw, plan, process):
    need(type(raw) is dict, "raw runner object")
    memory, cli = _command(plan, process)
    key = plan["coordinate"]
    equal([raw.get("operation_id"), raw.get("fixture_id")], key, "raw coordinate")
    execution = plan["environment"]["execution_resource"]
    cpu = process["selected_cpu"]
    topology = execution["processor_topology"]
    cpuset = f"group-{execution['processor_group']}:logical-{execution['selected_logical_processor']}:cpu-set-{execution['selected_cpu_set_id']}:core-{topology['core_index']}:efficiency-{topology['efficiency_class']}"
    metadata = dict(
        platform="windows",
        selected_logical_cpu=cpu,
        effective_cpu_affinity=[cpu],
        effective_cpuset=cpuset,
        placement_mechanism=execution["placement_mechanism"],
        processor_group=execution["processor_group"],
        selected_cpu_set_id=execution["selected_cpu_set_id"],
        cpu_set_allocation_state=execution["cpu_set_allocation_state"],
        cpu_quota="unlimited",
        timer_source=f"{execution['timer']['source']}:{execution['timer']['frequency_hz']}",
        process_power_policy=execution["process_power_policy"],
        observed_processor_groups=[execution["processor_group"]],
        observed_logical_processors=[cpu],
    )
    equal({k: raw.get(k) for k in metadata}, metadata, "raw placement claims")
    if memory:
        peak = integer(raw.get("peak_working_set_bytes"), 1)
        equal(
            raw.get("memory_worker_contract"),
            "isolated-peak-rss-v1",
            "memory worker contract",
        )
        lifetime = raw.get("memory_lifetime")
        shape(
            lifetime,
            set(
                "contract pid birth_100ns exit_100ns worker_reported_peak_rss_bytes terminal_peak_rss_bytes residency_qualified descendant_coverage_qualified observer_effects_qualified".split()
            ),
            "terminal memory lifetime",
        )
        equal(
            lifetime["contract"],
            "retained-process-terminal-peak-v1",
            "memory lifetime contract",
        )
        integer(lifetime["pid"], 1, 2**32 - 1)
        birth = integer(lifetime["birth_100ns"], 1)
        exit_time = integer(lifetime["exit_100ns"], birth + 1)
        need(exit_time > birth, "memory worker exited after birth")
        integer(lifetime["worker_reported_peak_rss_bytes"], 1, peak)
        equal(
            integer(lifetime["terminal_peak_rss_bytes"], 1), peak, "terminal peak RSS"
        )
        for name in (
            "residency_qualified",
            "descendant_coverage_qualified",
            "observer_effects_qualified",
        ):
            need(
                lifetime[name] is False,
                "memory observation cannot assert qualification",
            )
        return dict(samples=[peak], batch_iterations=1, batch_duration_samples=None)
    need(raw.get("unit") == "nanoseconds", "raw time unit")
    need(integer(raw.get("sample_iterations")) == 64, "all raw samples")
    batch = integer(raw.get("batch_iterations"), 1)
    equal(batch, plan["batch_iterations"], "raw fixed batch")
    need(
        integer(raw.get("maximum_descheduling_nanoseconds")) == 50_000_000
        and integer(raw.get("maximum_sample_attempts")) == 128,
        "unchanged authenticity limits",
    )
    rejected = raw.get("rejected_batch_elapsed_samples")
    need(type(rejected) is list and len(rejected) <= 64, "retained rejected attempts")
    need(integer(raw.get("sample_attempts")) == 64 + len(rejected), "all raw attempts")
    need(not cli or not rejected, "CLI rejection policy")
    for prefix, count in (
        ("", 64),
        ("control_", 64 if cli else 0),
        ("rejected_", len(rejected)),
    ):
        wall = _array(raw, prefix + "batch_elapsed_samples", count, 1)
        cpu_values = _array(raw, prefix + "process_cpu_batch_elapsed_samples", count)
        utilization = _array(
            raw, prefix + "process_cpu_utilization_basis_points", count
        )
        equal(
            utilization,
            [min(10000, c * 10000 // w) for w, c in zip(wall, cpu_values, strict=True)],
            "raw CPU arithmetic",
        )
        if prefix != "rejected_":
            for field, values in (
                ("samples", wall),
                ("process_cpu_samples", cpu_values),
            ):
                normalized = _array(raw, prefix + field, count, 1)
                equal(
                    normalized,
                    [max(1, (v + batch // 2) // batch) for v in values],
                    "raw batch normalization",
                )
        if not cli and prefix != "control_":
            need(
                all(
                    (w - c > 50_000_000) == (prefix == "rejected_")
                    for w, c in zip(wall, cpu_values, strict=True)
                ),
                "raw accepted/rejected partition",
            )
    projected = {
        **{k: raw[k] for k in COPIED},
        **{k: raw[v] for k, v in RENAMED.items()},
    }
    if "--cli-launch-schedule" in process["command"]:
        equal(
            raw.get("cli_launch_schedule"),
            "half-complementary-adjacent-pairs-64-v1",
            "CLI schedule",
        )
        equal(raw.get("request_first"), [i >= 32 for i in range(64)], "CLI allocation")
        projected.update(
            cli_launch_schedule=raw["cli_launch_schedule"],
            request_first=raw["request_first"],
        )
    else:
        need(
            "cli_launch_schedule" not in raw and "request_first" not in raw,
            "unsolicited CLI schedule",
        )
    need(
        not any(
            k.startswith("cli_cycle_") or k.endswith("cycle_evidence") for k in raw
        ),
        "unsolicited cycle evidence",
    )
    return projected


def _memory_worker_streams(stderr, raw):
    packets = []
    for line in stderr.splitlines():
        if line.startswith("{"):
            packet = parse(line.encode())
            if (
                type(packet) is dict
                and packet.get("contract") == "retained-memory-worker-streams-v1"
            ):
                packets.append(packet)
    need(len(packets) == 1, "one retained memory worker stream packet")
    packet = packets[0]
    shape(
        packet,
        set(
            "contract pid birth_100ns input_bytes stdout_bytes stderr_bytes success".split()
        ),
        "memory worker streams",
    )
    lifetime = raw["memory_lifetime"]
    equal(
        [packet["pid"], packet["birth_100ns"]],
        [lifetime["pid"], lifetime["birth_100ns"]],
        "memory worker stream identity",
    )
    need(packet["success"] is True, "memory worker stream success")
    streams = {}
    for name in ("input_bytes", "stdout_bytes", "stderr_bytes"):
        need(type(packet[name]) is list, "raw worker byte array")
        for byte in packet[name]:
            integer(byte, 0, 255)
        streams[name] = bytes(packet[name])
    need(type(parse(streams["input_bytes"])) is dict, "complete worker input JSON")
    worker = parse(streams["stdout_bytes"])
    need(type(worker) is dict, "complete worker output JSON")
    equal(
        worker.get("worker_contract"), "isolated-peak-rss-v1", "nested worker contract"
    )
    equal(
        worker.get("peak_working_set_bytes"),
        lifetime["worker_reported_peak_rss_bytes"],
        "nested worker peak RSS",
    )
    for name in (
        "effective_cpu_affinity",
        "observed_processor_groups",
        "observed_logical_processors",
    ):
        equal(worker.get(name), raw[name], "nested worker placement")


def verify_acquisition_receipt(files, expected):
    """Reconstruct one process-backed observation, retaining raw output and claims."""
    shape(files, FILES, "acquisition bundle")
    shape(
        expected,
        {"terminal_sha256", "acquisition_plan", "process_plan"},
        "external expectations",
    )
    for data in files.values():
        need(type(data) is bytes and len(data) <= 64 * 1024 * 1024, "bounded bytes")
    need(
        sha(files["terminal.json"]) == receipt._digest(expected["terminal_sha256"]),
        "external acquisition pin",
    )
    plan = parse(files["plan.json"])
    shape(plan, PLAN, "acquisition plan")
    equal(plan, expected["acquisition_plan"], "independent acquisition plan")
    for field in ("adapter_sha256", "controller_sha256"):
        receipt._digest(plan[field])
    need(
        plan["contract"] == "unqualified-enclosed-coordinate-v1", "acquisition version"
    )
    row = parse(files["terminal.json"])
    shape(row, TERMINAL, "acquisition terminal")
    need(
        row["contract"] == plan["contract"] and row["status"] == "observed",
        "observed acquisition",
    )
    for field in ("authoritative", "certification_eligible", "baseline_admission"):
        need(row[field] is False, "no promoted acquisition")
    need(sha(files["plan.json"]) == row["plan_sha256"], "acquisition plan pin")
    equal(row["coordinate"], plan["coordinate"], "acquisition coordinate")
    shape(row["process_envelope"], {"path", "sha256"}, "nested receipt pin")
    need(
        row["process_envelope"]["path"] == "process/terminal.json",
        "literal nested path",
    )
    process_files = {name: files["process/" + name] for name in receipt.FILES}
    verified = receipt.verify_process_receipt(
        process_files, row["process_envelope"]["sha256"], expected["process_plan"]
    )
    process = expected["process_plan"]
    equal(process["source_sha"], plan["source_sha"], "nested source")
    equal(process["inputs"], plan["inputs"], "nested input pins")
    equal(
        process["environment_sha256"],
        plan["process_environment_sha256"],
        "nested environment",
    )
    shape(
        plan["artifacts"],
        {"runner", "kernel", "interop", "memory_worker"},
        "artifact roles",
    )
    need(
        len(set(PureWindowsPath(p) for p in plan["artifacts"].values())) == 4,
        "distinct artifact roles",
    )
    inputs = {str(PureWindowsPath(p)).casefold(): h for p, h in plan["inputs"].items()}
    need(len(inputs) == len(plan["inputs"]), "unambiguous Windows inputs")
    for path in plan["artifacts"].values():
        need(str(PureWindowsPath(path)).casefold() in inputs, "pinned role")
    need(
        PureWindowsPath(plan["artifacts"]["memory_worker"])
        == PureWindowsPath(plan["artifacts"]["runner"]).with_name(
            "strling-performance-memory-worker.exe"
        ),
        "runner-local memory worker",
    )
    manifest = parse(files["manifest.json"])
    equal(manifest, plan["manifest"], "original manifest")
    manifest_path = (
        PureWindowsPath(process["cwd"])
        / "tests/certification/performance-resource/1.0/manifest.json"
    )
    need(
        inputs.get(str(manifest_path).casefold()) == sha(files["manifest.json"]),
        "original manifest byte pin",
    )
    for field in ("fixture_manifest", "resource_inventory"):
        dependency = manifest[field]
        need(
            inputs.get(
                str(PureWindowsPath(process["cwd"]) / dependency["path"]).casefold()
            )
            == dependency["sha256"],
            "pinned workload dependency",
        )
    need(
        plan["environment"]["os"]
        == plan["environment"]["execution_resource"]["platform"]
        == "windows",
        "native acquisition platform",
    )
    inner = parse(process_files["terminal.json"])
    equal(
        inner["controls"]["cpu_set_id"],
        plan["environment"]["execution_resource"]["selected_cpu_set_id"],
        "nested CPU set",
    )
    begin, end = (
        integer(row["acquisition_begin_ns"]),
        integer(row["acquisition_end_ns"]),
    )
    need(
        begin
        <= inner["action_begin_ns"]
        < inner["action_end_ns"]
        <= inner["finished_ns"]
        <= end,
        "acquisition encloses native work",
    )
    events = parse(files["process-events.json"])
    need(
        sha(files["process-events.json"]) == row["process_events_sha256"],
        "process events pin",
    )
    try:
        stdout, stderr = (
            process_files[n].decode("utf-8") for n in ("stdout.bin", "stderr.bin")
        )
    except UnicodeError as error:
        raise ValueError("observed UTF8 transport") from error
    equal(
        events,
        [
            dict(event="measurement-process-start", command=process["command"]),
            dict(
                event="measurement-process-result",
                command=process["command"],
                returncode=0,
                stdout=stdout,
                stderr=stderr,
            ),
        ],
        "exact process events",
    )
    raw = parse(process_files["stdout.bin"])
    equal(
        row["observation"],
        _projection(raw, plan, process),
        "raw observation projection",
    )
    if plan["coordinate"][0].startswith("memory:"):
        _memory_worker_streams(stderr, raw)
        root_birth = parse(process_files["suspended.json"])
        root_exit = parse(process_files["root-exit.json"])
        lifetime = raw["memory_lifetime"]
        need(
            lifetime["pid"] != root_birth["pid"]
            and int(root_birth["birth"])
            <= lifetime["birth_100ns"]
            < lifetime["exit_100ns"]
            <= int(root_exit["exit"]),
            "memory worker lifetime belongs within the retained root lifetime",
        )
    if plan["coordinate"][0].startswith("latency:"):
        elapsed = sum(
            sum(raw[k])
            for k in (
                "batch_elapsed_samples",
                "control_batch_elapsed_samples",
                "rejected_batch_elapsed_samples",
            )
        )
        need(elapsed <= inner["whole_action_ns"], "all attempts fit enclosing work")
    cli_samples = (
        dict(request_ns=raw["samples"], control_ns=raw["control_samples"])
        if plan["coordinate"][0] == "latency:cli-startup"
        else None
    )
    return dict(
        **DENIALS,
        row=dict(
            coordinate=plan["coordinate"],
            begin_ns=inner["action_begin_ns"],
            end_ns=inner["action_end_ns"],
            pid=verified["pid"],
            birth_100ns=int(verified["birth"]),
            receipt_sha256=expected["terminal_sha256"],
            cli_samples=cli_samples,
        ),
        acquisition_begin_ns=begin,
        acquisition_end_ns=end,
        raw_runner=raw,
        observation=row["observation"],
    )


def recipe_for(expected):
    """Prospective recipe from external plans, independent of measured values."""
    plan, process = expected["acquisition_plan"], expected["process_plan"]
    roles = {v: "artifact:" + k for k, v in plan["artifacts"].items()}
    root = PureWindowsPath(process["cwd"])
    inputs = {}
    for path, digest in plan["inputs"].items():
        if path not in roles:
            try:
                key = "source:" + str(PureWindowsPath(path).relative_to(root))
            except ValueError:
                key = "absolute:" + str(PureWindowsPath(path))
            inputs[key] = digest
    return dict(
        coordinate=plan["coordinate"],
        batch_iterations=plan["batch_iterations"],
        command=[roles.get(v, v) for v in process["command"]],
        selected_cpu=process["selected_cpu"],
        timeout_seconds=process["timeout_seconds"],
        process_environment_sha256=plan["process_environment_sha256"],
        inputs=inputs,
        implementations={
            **{k: v for k, v in process.items() if k.endswith("implementation_sha256")},
            "adapter_sha256": plan["adapter_sha256"],
            "controller_sha256": plan["controller_sha256"],
        },
    )


def assemble_cohort(bundles, expectations, *, role, plan, pins, coordinates):
    """Return canonical complete cohort bytes, with every qualification denied."""
    bounds._plan(plan, coordinates)
    bounds._pins(pins)
    need(role in ("reference-only", "source-distinct-holdout"), "cohort role")
    count = len(coordinates) * 9
    need(
        type(bundles) is list
        and type(expectations) is list
        and len(bundles) == len(expectations) == count,
        "complete nine-run cohort",
    )
    terminal_pins = [e["terminal_sha256"] for e in expectations]
    need(
        sha(encode(terminal_pins)) == pins["acquisition_sha256"],
        "ordered acquisition identity",
    )
    recipes = [recipe_for(expectations[i * 9]) for i in range(len(coordinates))]
    need(sha(encode(recipes)) == plan["recipe_sha256"], "prospective recipe pin")
    rows, intervals = [], []
    memory_workers = set()
    artifact_pins = None
    for index, (files, expected) in enumerate(zip(bundles, expectations, strict=True)):
        verified = verify_acquisition_receipt(files, expected)
        if verified["raw_runner"].get("memory_lifetime") is not None:
            lifetime = verified["raw_runner"]["memory_lifetime"]
            identity = (lifetime["pid"], lifetime["birth_100ns"])
            need(identity not in memory_workers, "memory worker evidence reuse")
            memory_workers.add(identity)
        outer = expected["acquisition_plan"]
        manifest_coordinates = [
            [o["id"], f]
            for o in outer["manifest"]["operations"]
            if o["measurement_kind"] in ("latency", "peak-rss")
            for f in o["fixture_ids"]
        ]
        equal(
            coordinates, manifest_coordinates, "complete manifest process denominator"
        )
        equal(outer["coordinate"], coordinates[index // 9], "cohort coordinate order")
        equal(outer["source_sha"], pins["source_sha"], "cohort source")
        current_pins = {k: outer["inputs"][v] for k, v in outer["artifacts"].items()}
        need(current_pins["runner"] == pins["runner_sha256"], "cohort runner")
        if artifact_pins is None:
            artifact_pins = current_pins
        equal(current_pins, artifact_pins, "stable cohort artifact pins")
        need(sha(files["manifest.json"]) == plan["manifest_sha256"], "cohort manifest")
        need(
            sha(encode(outer["environment"])) == plan["environment_sha256"],
            "cohort environment",
        )
        equal(recipe_for(expected), recipes[index // 9], "stable prospective recipe")
        rows.append(dict(verified["row"], repetition=index % 9))
        intervals.append(
            (verified["acquisition_begin_ns"], verified["acquisition_end_ns"])
        )
    intervals.sort()
    need(
        all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])),
        "nonoverlapping acquisition",
    )
    data = encode(dict(role=role, plan=plan, pins=pins, observations=rows))
    digest = sha(data)
    bounds._cohort(
        data, digest, role=role, plan=plan, pins=pins, coordinates=coordinates
    )
    return dict(**DENIALS, cohort=data, cohort_sha256=digest)
