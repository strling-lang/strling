"""Unqualified Windows active-work diagnostics and pure raw reconstruction.

This module is deliberately NOT the live conditioner. Its output is diagnostic
only, never baseline admission, profile readiness, calibration or trust evidence.
The original v6 implementation and its exact attested source stay unchanged.
Any operational promotion requires separate governed fresh-reference qualification.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import re
import time
from typing import Any, Mapping

from tooling import performance_windows as live

WindowsQualificationError = live.WindowsQualificationError
OBSERVATION_MILLISECONDS = live.OBSERVATION_MILLISECONDS
_kernel32 = live._kernel32
_current_process_handle = live._current_process_handle
_raise_last_error = live._raise_last_error
process_affinity = live.process_affinity
processor_performance_counters = live.processor_performance_counters

# These are admission-control work, not product warmups or benchmark samples.
# The fixed extra debit tightens admission; it is NOT an inferred clock-error
# bound. GetSystemTimeAdjustment describes the time-of-day clock, not CPU time.
ACTIVE_WORK_KIND = "nested-user-accounted-isolation-v1"
ACTIVE_WORK_ITERATIONS = 10_000
ACTIVE_WORK_MINIMUM_BLOCKS = 64
ACTIVE_WORK_GUARD_100NS = 312_500
ACTIVE_WORK_DIGEST = "a6d7774ae6101ffa801a306b3c327b20a9c9f995983e05d604a1b20a69bf358b"


def _active_integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise WindowsQualificationError("invalid exact active-work counter")
    return value


def _active_filetime(value: object) -> int:
    if (
        not isinstance(value, str)
        or len(value) > 20
        or not value.isascii()
        or not value.isdecimal()
        or str(int(value)) != value
        or int(value) > 2**64 - 1
    ):
        raise WindowsQualificationError("invalid raw FILETIME decimal string")
    return int(value)


def whole_product_interval_diagnostic(
    proof: Mapping[str, Any], expected_workload: Mapping[str, Any]
) -> dict[str, object]:
    """Keep whole serial in-process workload time alongside sample medians.

    A sample median can miss time-sliced competition even when the complete
    process takes twice as long. This pure diagnostic never subtracts CPU time,
    converts cycles to time, applies an admission threshold, or changes sample
    acceptance. The enclosing span includes launch, all warmups, every accepted
    and rejected attempt, gaps, exit and caller overhead. Its difference from
    the batch sum is NOT an attribution of scheduler/interrupt time.

    The caller must independently bind expected_workload to reviewed source,
    artifact and command receipts. Validation of supplied fields alone cannot
    prove execution, qualify a reference, or grant certification authority.
    This shape covers the existing 512-warmup/64-sample serial latency runner;
    it does not claim coverage of nonlatency or subprocess workloads.
    """
    fields = {
        "role",
        "workload",
        "action_begin_ns",
        "action_end_ns",
        "exit_code",
        "child_before",
        "child_after",
        "accepted_batch_elapsed_samples",
        "rejected_batch_elapsed_samples",
    }
    workload_fields = {
        "source_sha",
        "runner_sha256",
        "operation_id",
        "fixture_id",
        "batch_iterations",
        "warmup_iterations",
        "sample_iterations",
        "maximum_sample_attempts",
        "selected_logical_cpu",
    }
    if (
        not isinstance(proof, Mapping)
        or set(proof) != fields
        or proof["role"] != "unqualified-whole-product-interval"
        or type(proof["exit_code"]) is not int
        or proof["exit_code"] != 0
    ):
        raise WindowsQualificationError("complete diagnostic product interval required")
    for workload in (expected_workload, proof["workload"]):
        if not isinstance(workload, Mapping) or set(workload) != workload_fields:
            raise WindowsQualificationError("closed expected workload required")
        for name, pattern in (
            ("source_sha", r"[0-9a-f]{40}"),
            ("runner_sha256", r"[0-9a-f]{64}"),
            ("operation_id", r"latency:[a-z0-9-]+"),
            ("fixture_id", r"fixture:[a-z0-9-]+"),
        ):
            if (
                not isinstance(workload[name], str)
                or re.fullmatch(pattern, workload[name]) is None
            ):
                raise WindowsQualificationError(
                    "invalid source-bound workload identity"
                )
        for name, required in (
            ("warmup_iterations", 512),
            ("sample_iterations", 64),
            ("maximum_sample_attempts", 128),
        ):
            if _active_integer(workload[name]) != required:
                raise WindowsQualificationError("whole-product workload count changed")
        if (
            _active_integer(workload["batch_iterations"], minimum=1) > 4096
            or _active_integer(workload["selected_logical_cpu"]) > 63
        ):
            raise WindowsQualificationError("whole-product batch or CPU changed")
    if proof["workload"] != expected_workload:
        raise WindowsQualificationError("whole-product expected workload mismatch")
    begin = _active_integer(proof["action_begin_ns"])
    end = _active_integer(proof["action_end_ns"])
    child_fields = {"pid", "birth", "kernel", "user", "query_begin_ns", "query_end_ns"}
    for child in (proof["child_before"], proof["child_after"]):
        if not isinstance(child, Mapping) or set(child) != child_fields:
            raise WindowsQualificationError("closed child clock identity required")
        _active_integer(child["pid"], minimum=1)
        if _active_filetime(child["birth"]) == 0:
            raise WindowsQualificationError("positive child birth required")
        for name in child_fields - {"pid", "birth"}:
            _active_integer(child[name])
    before, after = proof["child_before"], proof["child_after"]
    if (
        before["pid"] != after["pid"]
        or before["birth"] != after["birth"]
        or not begin
        <= before["query_begin_ns"]
        <= before["query_end_ns"]
        < after["query_begin_ns"]
        <= after["query_end_ns"]
        <= end
        or any(after[k] < before[k] for k in ("kernel", "user"))
    ):
        raise WindowsQualificationError("whole child interval is not nested/monotonic")
    accepted = proof["accepted_batch_elapsed_samples"]
    rejected = proof["rejected_batch_elapsed_samples"]
    if (
        type(accepted) is not list
        or len(accepted) != 64
        or type(rejected) is not list
        or len(accepted) + len(rejected) > 128
    ):
        raise WindowsQualificationError("all accepted/rejected attempts required")
    samples = [*_validated_durations(accepted), *_validated_durations(rejected)]
    total = sum(samples)
    if total > end - begin:
        raise WindowsQualificationError("serial batch durations exceed enclosing span")
    batch = expected_workload["batch_iterations"]
    normalized = sorted(max(1, (n + batch // 2) // batch) for n in accepted)
    return {
        "role": "unqualified-whole-product-interval",
        "status": "diagnostic-complete",
        "baseline_admission": False,
        "certification_eligible": False,
        "performance_qualification": False,
        "whole_action_elapsed_ns": end - begin,
        "all_attempt_batch_elapsed_ns": total,
        "outside_sample_batches_ns": end - begin - total,
        "accepted_sample_median_ns": (normalized[31] + normalized[32]) // 2,
        "attempts": len(samples),
        "rejected_attempts": len(rejected),
        "child_cpu_delta_100ns": sum(after[k] - before[k] for k in ("kernel", "user")),
        "cpu_time_subtracted": False,
    }


def _validated_durations(values: list[object]) -> list[int]:
    return [_active_integer(value, minimum=1) for value in values]


def _closed_reference(value: object, fields: set[str]) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise WindowsQualificationError("closed reference shape required")


def _reference_hash(value: object, length: int = 64) -> None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{%d}" % length, value) is None
    ):
        raise WindowsQualificationError("invalid reference digest")


def _unique_reference_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WindowsQualificationError("duplicate reference JSON key")
        result[key] = value
    return result


def _whole_interval_coverage(windows: object, begin: int, end: int) -> None:
    if type(windows) is not list or not 1 <= len(windows) <= 4096:
        raise WindowsQualificationError("bounded continuous coverage required")
    cursor, prior_begin = begin, -1
    for window in windows:
        _closed_reference(window, {"begin_ns", "end_ns"})
        start = _active_integer(window["begin_ns"])
        stop = _active_integer(window["end_ns"])
        if start < prior_begin or start > cursor or stop <= start:
            raise WindowsQualificationError("whole interval coverage gap/order changed")
        prior_begin = start
        cursor = max(cursor, stop)
    if cursor < end:
        raise WindowsQualificationError("whole interval exit is not covered")


def bound_whole_product_reference_diagnostic(
    reference_bytes: bytes,
    expected_sha256: str,
    expected: Mapping[str, Any],
    candidate_source_sha: str,
) -> dict[str, object]:
    """Reject circular or partial serial-latency references before acquisition.

    The caller supplies pins from an independent review boundary, never from
    this envelope. Hash agreement proves byte identity, NOT qualification,
    provenance, signatures, actual monitoring, reference quality or immunity
    to environmental confounding. In particular, source-distinct commits alone
    do not prove an independently acquired holdout. External acquisition and
    trust verification remain necessary. No live caller uses this preflight.

    Preserve all nine reference-only and nine holdout repetitions, including
    unfavorable intervals and rejected attempts. Union coverage must enclose
    launch through exit; before/after spot probes are insufficient. Coverage
    timestamps remain claims until the independently pinned raw acquisition
    is verified. No thresholds are learned, normalized or applied here; even
    structurally bound synthetic inputs cannot grant admission authority.
    """
    _reference_hash(expected_sha256)
    _reference_hash(candidate_source_sha, 40)
    if (
        type(reference_bytes) is not bytes
        or not 0 < len(reference_bytes) <= 2 * 1024 * 1024
        or hashlib.sha256(reference_bytes).hexdigest() != expected_sha256
    ):
        raise WindowsQualificationError("independently pinned reference bytes required")
    try:
        envelope = json.loads(
            reference_bytes.decode("utf-8"), object_pairs_hook=_unique_reference_object
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WindowsQualificationError("invalid reference JSON") from error
    fields = {"method_sha256", "environment_sha256", "recipe", "cohorts"}
    _closed_reference(expected, fields)
    _closed_reference(envelope, fields | {"role"})
    if envelope["role"] != "unqualified-whole-product-reference":
        raise WindowsQualificationError("reference cannot assert qualification")
    for field in ("method_sha256", "environment_sha256"):
        _reference_hash(expected[field])
        if envelope[field] != expected[field]:
            raise WindowsQualificationError("reference context pin mismatch")
    if envelope["recipe"] != expected["recipe"]:
        raise WindowsQualificationError("independent reference recipe mismatch")
    _closed_reference(
        expected["recipe"],
        {
            "operation_id",
            "fixture_id",
            "batch_iterations",
            "warmup_iterations",
            "sample_iterations",
            "maximum_sample_attempts",
            "selected_logical_cpu",
        },
    )
    _closed_reference(envelope["recipe"], set(expected["recipe"]))
    if any(
        type(envelope["recipe"][key]) is not type(value)
        for key, value in expected["recipe"].items()
    ):
        raise WindowsQualificationError("reference recipe types changed")
    for cohorts in (expected["cohorts"], envelope["cohorts"]):
        if type(cohorts) is not list or len(cohorts) != 2:
            raise WindowsQualificationError(
                "reference and independent holdout required"
            )
    source_ids = {candidate_source_sha}
    acquisitions: set[str] = set()
    receipts: set[str] = set()
    processes: set[tuple[int, str]] = set()
    results = []
    for index, role in enumerate(("reference-only", "source-distinct-holdout")):
        pins, cohort = expected["cohorts"][index], envelope["cohorts"][index]
        cohort_fields = {"role", "source_sha", "runner_sha256", "acquisition_sha256"}
        _closed_reference(pins, cohort_fields)
        _closed_reference(cohort, cohort_fields | {"observations"})
        if pins["role"] != role or any(cohort[k] != pins[k] for k in cohort_fields):
            raise WindowsQualificationError("independent cohort pin/order mismatch")
        _reference_hash(pins["source_sha"], 40)
        _reference_hash(pins["runner_sha256"])
        _reference_hash(pins["acquisition_sha256"])
        if (
            pins["source_sha"] in source_ids
            or pins["acquisition_sha256"] in acquisitions
        ):
            raise WindowsQualificationError(
                "candidate fit or reference acquisition reuse"
            )
        source_ids.add(pins["source_sha"])
        acquisitions.add(pins["acquisition_sha256"])
        observations = cohort["observations"]
        if type(observations) is not list or len(observations) != 9:
            raise WindowsQualificationError("all nine reference repetitions required")
        workload = {
            **expected["recipe"],
            "source_sha": pins["source_sha"],
            "runner_sha256": pins["runner_sha256"],
        }
        for repetition, observation in enumerate(observations):
            _closed_reference(
                observation, {"repetition", "receipt_sha256", "proof", "coverage"}
            )
            if _active_integer(observation["repetition"]) != repetition:
                raise WindowsQualificationError("reference repetition order changed")
            receipt = observation["receipt_sha256"]
            _reference_hash(receipt)
            if receipt in receipts:
                raise WindowsQualificationError("reference observation reused")
            receipts.add(receipt)
            proof = observation["proof"]
            result = whole_product_interval_diagnostic(proof, workload)
            child = proof["child_before"]
            identity = (child["pid"], child["birth"])
            if identity in processes:
                raise WindowsQualificationError("reference product process reused")
            processes.add(identity)
            _whole_interval_coverage(
                observation["coverage"],
                proof["action_begin_ns"],
                proof["action_end_ns"],
            )
            results.append(
                {
                    **result,
                    "cohort": role,
                    "repetition": repetition,
                    "receipt_sha256": receipt,
                }
            )
    return {
        "role": "unqualified-whole-product-reference",
        "status": "diagnostic-bound",
        "baseline_admission": False,
        "certification_eligible": False,
        "performance_qualification": False,
        "reference_sha256": expected_sha256,
        "observations": results,
        "attempts": sum(row["attempts"] for row in results),
    }


def active_quiescence_rates(
    proof: Mapping[str, Any], selected_logical_cpu: int, processor_count: int
) -> dict[str, int]:
    """Reconstruct conservative accounted interference, not physical clock error.

    Let B be selected accounted busy time and A nested, pinned actor USER time.
    B-A retains all non-actor accounted work AND all actor kernel time. Never
    credit kernel/DPC/ISR, estimate CPU time from cycles, subtract actor work
    from whole-host busy, or clamp inconsistent inclusion into a green result.
    The supported CPU-time API's units are amounts, not a precision guarantee.
    Raw readings and complete nesting must accompany every new observation;
    historical idle observations cannot be reinterpreted by this function.
    """
    _active_integer(processor_count, minimum=1)
    _active_integer(selected_logical_cpu)
    if processor_count > 64 or not 0 <= selected_logical_cpu < processor_count:
        raise WindowsQualificationError("active processor group/selection changed")
    expected = {
        "kind",
        "work_iterations",
        "minimum_blocks",
        "additional_guard_100ns",
        "block_count",
        "work_digest",
        "priority_class",
        "processor_before",
        "processor_after",
        "actor_before",
        "actor_after",
        "affinity_before",
        "affinity_after",
        "priority_class_after",
    }
    if not isinstance(proof, Mapping) or set(proof) != expected:
        raise WindowsQualificationError("active-work proof denominator changed")
    if (
        proof["kind"] != ACTIVE_WORK_KIND
        or type(proof["work_iterations"]) is not int
        or proof["work_iterations"] != ACTIVE_WORK_ITERATIONS
        or type(proof["minimum_blocks"]) is not int
        or proof["minimum_blocks"] != ACTIVE_WORK_MINIMUM_BLOCKS
        or type(proof["additional_guard_100ns"]) is not int
        or proof["additional_guard_100ns"] != ACTIVE_WORK_GUARD_100NS
        or proof["work_digest"] != ACTIVE_WORK_DIGEST
        or type(proof["priority_class"]) is not int
        or proof["priority_class"] != 0x20
        or type(proof["priority_class_after"]) is not int
        or proof["priority_class_after"] != 0x20
    ):
        raise WindowsQualificationError("active-work recipe or priority changed")
    affinity_fields = {
        "processor_group",
        "effective_logical_processors",
        "process_affinity_mask",
        "system_affinity_mask",
    }
    for key in ("affinity_before", "affinity_after"):
        affinity = proof[key]
        if (
            not isinstance(affinity, Mapping)
            or set(affinity) != affinity_fields
            or type(affinity["processor_group"]) is not int
            or affinity["processor_group"] != 0
            or type(affinity["effective_logical_processors"]) is not list
            or len(affinity["effective_logical_processors"]) != 1
            or type(affinity["effective_logical_processors"][0]) is not int
            or affinity["effective_logical_processors"] != [selected_logical_cpu]
            or any(
                not isinstance(affinity[field], str)
                or re.fullmatch(r"0x[0-9a-f]{16}", affinity[field]) is None
                for field in ("process_affinity_mask", "system_affinity_mask")
            )
            or int(affinity["process_affinity_mask"], 16) != 1 << selected_logical_cpu
            or not int(affinity["system_affinity_mask"], 16)
            & (1 << selected_logical_cpu)
        ):
            raise WindowsQualificationError("active actor affinity is not pinned")
    if proof["affinity_before"] != proof["affinity_after"]:
        raise WindowsQualificationError("active actor affinity changed")
    _active_integer(proof["block_count"], minimum=ACTIVE_WORK_MINIMUM_BLOCKS)
    counters = []
    for key in ("processor_before", "processor_after"):
        frame = proof[key]
        if not isinstance(frame, Mapping) or set(frame) != {
            "query_begin_ns",
            "query_end_ns",
            "rows",
        }:
            raise WindowsQualificationError("active processor frame changed")
        _active_integer(frame["query_begin_ns"])
        _active_integer(frame["query_end_ns"])
        if not isinstance(frame["rows"], list) or len(frame["rows"]) != processor_count:
            raise WindowsQualificationError("active CPU denominator changed")
        counters.append(frame)
    actors = []
    for key in ("actor_before", "actor_after"):
        frame = proof[key]
        if not isinstance(frame, Mapping) or set(frame) != {
            "query_begin_ns",
            "query_end_ns",
            "creation_filetime_100ns",
            "kernel_100ns",
            "user_100ns",
            "processor",
        }:
            raise WindowsQualificationError("active actor frame changed")
        _active_integer(frame["query_begin_ns"])
        _active_integer(frame["query_end_ns"])
        for field in ("creation_filetime_100ns", "kernel_100ns", "user_100ns"):
            _active_filetime(frame[field])
        if (
            _active_integer(frame["processor"]) != selected_logical_cpu
            or _active_filetime(frame["creation_filetime_100ns"]) == 0
        ):
            raise WindowsQualificationError("active actor CPU/birth changed")
        actors.append(frame)
    before, after = counters
    actor_before, actor_after = actors
    timestamps = (
        before["query_begin_ns"],
        before["query_end_ns"],
        actor_before["query_begin_ns"],
        actor_before["query_end_ns"],
        actor_after["query_begin_ns"],
        actor_after["query_end_ns"],
        after["query_begin_ns"],
        after["query_end_ns"],
    )
    if (
        list(timestamps) != sorted(timestamps)
        or actor_after["query_begin_ns"] - actor_before["query_end_ns"]
        < OBSERVATION_MILLISECONDS * 1_000_000
        or actor_before["creation_filetime_100ns"]
        != actor_after["creation_filetime_100ns"]
        or not 0 <= selected_logical_cpu < processor_count
    ):
        raise WindowsQualificationError("active actor interval is not nested/pinned")
    user_credit = _active_filetime(actor_after["user_100ns"]) - _active_filetime(
        actor_before["user_100ns"]
    )
    kernel_delta = _active_filetime(actor_after["kernel_100ns"]) - _active_filetime(
        actor_before["kernel_100ns"]
    )
    if min(user_credit, kernel_delta) < 0:
        raise WindowsQualificationError("active actor accounting regressed")
    deltas = []
    guard_ns = ACTIVE_WORK_GUARD_100NS * 100
    elapsed_lower_ns = after["query_begin_ns"] - before["query_end_ns"]
    elapsed_upper_ns = after["query_end_ns"] - before["query_begin_ns"]
    fields = {"idle", "kernel", "user", "dpc", "interrupt", "interrupt_count"}
    for start, end in zip(before["rows"], after["rows"]):
        if not isinstance(start, Mapping) or not isinstance(end, Mapping):
            raise WindowsQualificationError("active raw counter row changed")
        if set(start) != fields or set(end) != fields:
            raise WindowsQualificationError("active raw counter fields changed")
        for value in (*start.values(), *end.values()):
            _active_integer(value)
        if start["interrupt_count"] > 2**32 - 1 or end["interrupt_count"] > 2**32 - 1:
            raise WindowsQualificationError("active interrupt count overflow")
        delta = {key: end[key] - start[key] for key in fields}
        for value in delta.values():
            _active_integer(value)
        total = delta["kernel"] + delta["user"]
        busy = total - delta["idle"]
        interrupt = delta["dpc"] + delta["interrupt"]
        if (
            not 0 <= interrupt <= busy <= total
            or total <= 0
            or delta["kernel"] < delta["idle"]
            or total * 100 < elapsed_lower_ns - guard_ns
            or total * 100 > elapsed_upper_ns + guard_ns
        ):
            raise WindowsQualificationError(
                "active raw CPU inclusion/time agreement changed"
            )
        deltas.append(
            (
                total,
                busy,
                interrupt,
                delta["user"],
                delta["interrupt_count"],
                delta["kernel"] - delta["idle"],
            )
        )
    (
        selected_total,
        selected_busy,
        selected_interrupt,
        selected_user,
        count,
        selected_kernel,
    ) = deltas[selected_logical_cpu]
    if (
        user_credit > selected_user
        or kernel_delta > selected_kernel
        or user_credit + kernel_delta > selected_busy
        or selected_total < OBSERVATION_MILLISECONDS * 10_000
    ):
        raise WindowsQualificationError("active user inclusion/window changed")

    def upper_rate(numerator: int, denominator: int) -> int:
        return (numerator * 10_000 + denominator - 1) // denominator

    return {
        "selected_busy_basis_points": upper_rate(
            selected_busy - user_credit + ACTIVE_WORK_GUARD_100NS, selected_total
        ),
        "selected_interrupt_basis_points": upper_rate(
            selected_interrupt, selected_total
        ),
        "system_busy_basis_points": upper_rate(
            sum(row[1] for row in deltas), sum(row[0] for row in deltas)
        ),
        "selected_interrupt_count_delta": count,
    }


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def _active_actor_snapshot() -> dict[str, object]:
    kernel32 = _kernel32()
    kernel32.GetCurrentThread.argtypes = []
    kernel32.GetCurrentThread.restype = ctypes.c_void_p
    kernel32.GetCurrentProcessorNumber.argtypes = []
    kernel32.GetCurrentProcessorNumber.restype = ctypes.c_uint32
    function = kernel32.GetThreadTimes
    function.argtypes = [ctypes.c_void_p, *([ctypes.POINTER(_FILETIME)] * 4)]
    function.restype = ctypes.c_int
    created, exited, kernel, user = (_FILETIME() for _ in range(4))
    begin = time.perf_counter_ns()
    if not function(
        kernel32.GetCurrentThread(),
        ctypes.byref(created),
        ctypes.byref(exited),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        _raise_last_error("GetThreadTimes(current admission actor)")
    processor = int(kernel32.GetCurrentProcessorNumber())
    end = time.perf_counter_ns()

    def raw(value: _FILETIME) -> str:
        return str((int(value.high) << 32) | int(value.low))

    return {
        "query_begin_ns": begin,
        "query_end_ns": end,
        "creation_filetime_100ns": raw(created),
        "kernel_100ns": raw(kernel),
        "user_100ns": raw(user),
        "processor": processor,
    }


def _active_processor_snapshot(count: int) -> dict[str, object]:
    begin = time.perf_counter_ns()
    rows = processor_performance_counters(count)
    return {
        "query_begin_ns": begin,
        "query_end_ns": time.perf_counter_ns(),
        "rows": rows,
    }


def active_work_observation(
    selected_logical_cpu: int, processor_count: int
) -> tuple[dict[str, int], dict[str, object]]:
    """Acquire one bounded work-bearing window; never wait/retry for quiet."""
    proof: dict[str, object] = {
        "kind": ACTIVE_WORK_KIND,
        "work_iterations": ACTIVE_WORK_ITERATIONS,
        "minimum_blocks": ACTIVE_WORK_MINIMUM_BLOCKS,
        "additional_guard_100ns": ACTIVE_WORK_GUARD_100NS,
        "block_count": 0,
        "work_digest": ACTIVE_WORK_DIGEST,
    }
    try:
        kernel32 = _kernel32()
        kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        kernel32.GetPriorityClass.restype = ctypes.c_uint32
        proof["priority_class"] = int(
            kernel32.GetPriorityClass(_current_process_handle())
        )
        if proof["priority_class"] != 0x20:
            raise WindowsQualificationError("active admission requires normal priority")
        proof["affinity_before"] = process_affinity()
        proof["processor_before"] = _active_processor_snapshot(processor_count)
        proof["actor_before"] = _active_actor_snapshot()
        started = time.perf_counter_ns()
        count = 0
        while (
            time.perf_counter_ns() - started < OBSERVATION_MILLISECONDS * 1_000_000
            or count < ACTIVE_WORK_MINIMUM_BLOCKS
        ):
            value = hashlib.pbkdf2_hmac(
                "sha256",
                b"strling-active-work-v1",
                b"cpu1-accounted-isolation",
                ACTIVE_WORK_ITERATIONS,
                32,
            ).hex()
            proof["work_digest"] = value
            if value != ACTIVE_WORK_DIGEST:
                raise WindowsQualificationError("active admission work answer changed")
            count += 1
            proof["block_count"] = count
        proof["actor_after"] = _active_actor_snapshot()
        proof["processor_after"] = _active_processor_snapshot(processor_count)
        proof["affinity_after"] = process_affinity()
        proof["priority_class_after"] = int(
            kernel32.GetPriorityClass(_current_process_handle())
        )
        return active_quiescence_rates(
            proof, selected_logical_cpu, processor_count
        ), proof
    except WindowsQualificationError as error:
        # An unavailable or malformed window is never green, but its exact
        # complete/partial observations must remain in the retained raw stream.
        error.active_work_proof = proof
        raise


def validate_diagnostic_observation(
    observation: Mapping[str, Any], selected_logical_cpu: int, processor_count: int
) -> None:
    """Reconstruct diagnostic data only; reject any asserted admission authority."""
    required = {
        "role",
        "status",
        "baseline_admission",
        "certification_eligible",
        "performance_qualification",
        "profiles",
        "new_samples",
        "candidate_rates",
        "candidate_limit_exceedances",
        "active_work",
    }
    if not isinstance(observation, Mapping) or set(observation) != required:
        raise WindowsQualificationError("complete diagnostic shape changed")
    if (
        observation["role"] != "unqualified-active-work-diagnostic"
        or observation["status"] != "diagnostic-complete"
        or any(
            observation[key] is not False
            for key in (
                "baseline_admission",
                "certification_eligible",
                "performance_qualification",
            )
        )
        or any(
            type(observation[key]) is not int or observation[key] != 0
            for key in ("profiles", "new_samples")
        )
    ):
        raise WindowsQualificationError("diagnostics cannot assert admission authority")
    rates = active_quiescence_rates(
        observation["active_work"], selected_logical_cpu, processor_count
    )
    claimed = observation["candidate_rates"]
    if (
        not isinstance(claimed, Mapping)
        or set(claimed) != set(rates)
        or any(
            type(claimed[key]) is not int or claimed[key] != value
            for key, value in rates.items()
        )
        or observation["candidate_limit_exceedances"] != live.evaluate_quiescence(rates)
    ):
        raise WindowsQualificationError("raw diagnostic reconstruction changed")


def diagnostic_observation(
    selected_logical_cpu: int, processor_count: int
) -> dict[str, object]:
    """Retain complete/partial raw data without a governed passed status."""
    result: dict[str, object] = {
        "role": "unqualified-active-work-diagnostic",
        "baseline_admission": False,
        "certification_eligible": False,
        "performance_qualification": False,
        "profiles": 0,
        "new_samples": 0,
    }
    try:
        rates, proof = active_work_observation(selected_logical_cpu, processor_count)
        result.update(
            status="diagnostic-complete",
            candidate_rates=rates,
            candidate_limit_exceedances=live.evaluate_quiescence(rates),
            active_work=proof,
        )
    except WindowsQualificationError as error:
        result.update(
            status="diagnostic-unavailable",
            reason=str(error),
            active_work=getattr(error, "active_work_proof", None),
        )
    return result
