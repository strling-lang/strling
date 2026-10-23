"""Prospectively fixed whole-process comparison; not performance admission.

No live conditioner calls this component. External pins, complete acquisition,
independent provenance and empirical challenge qualification remain obligations
of the caller. A digest or source-distinct commit is not proof of those facts.
"""

from __future__ import annotations

import hashlib
import json
import re

METHOD = "prospective-whole-process-bounds-v1"
MARGIN_BP = 500
REPETITIONS = 9
MAX_BYTES = 4 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _closed(value, fields):
    _require(type(value) is dict and set(value) == set(fields.split()), "closed shape")


def _hash(value, length=64):
    _require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value), "digest"
    )


def _integer(value, minimum=0):
    _require(type(value) is int and minimum <= value < 2**63, "exact bounded integer")
    return value


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read(data, sha256):
    _hash(sha256)
    _require(type(data) is bytes and 0 < len(data) <= MAX_BYTES, "bounded bytes")
    _require(hashlib.sha256(data).hexdigest() == sha256, "independent byte pin")

    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"non-finite JSON: {value}")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, RecursionError) as error:
        raise ValueError("malformed reference JSON") from error


def _plan(plan, coordinates):
    _closed(
        plan,
        "method manifest_sha256 environment_sha256 recipe_sha256 coordinates warmup_iterations sample_iterations repetitions",
    )
    _require(plan["method"] == METHOD, "prospective method")
    for field in ("manifest_sha256", "environment_sha256", "recipe_sha256"):
        _hash(plan[field])
    for field, expected in (
        ("warmup_iterations", 512),
        ("sample_iterations", 64),
        ("repetitions", REPETITIONS),
    ):
        _require(_integer(plan[field]) == expected, "unchanged workload counts")
    _require(
        type(coordinates) is list and 0 < len(coordinates) <= 256,
        "coordinate denominator",
    )
    seen = set()
    for key in coordinates:
        _require(type(key) is list and len(key) == 2, "coordinate")
        _require(all(type(x) is str for x in key), "coordinate strings")
        _require(
            re.fullmatch(r"(?:latency|memory):[a-z0-9-]+", key[0])
            and re.fullmatch(r"fixture:[a-z0-9-]+", key[1]),
            "process-backed coordinate",
        )
        _require(tuple(key) not in seen, "unique complete coordinate denominator")
        seen.add(tuple(key))
    _require(
        plan["coordinates"] == coordinates,
        "independently supplied complete coordinates",
    )


def _pins(pins):
    _closed(pins, "source_sha runner_sha256 acquisition_sha256")
    for field in pins:
        _hash(pins[field], 40 if field == "source_sha" else 64)


def _cohort(data, sha256, *, role, plan, pins, coordinates):
    _plan(plan, coordinates)
    _pins(pins)
    cohort = _read(data, sha256)
    _closed(cohort, "role plan pins observations")
    _require(cohort["role"] == role, "cohort role")
    # Validate observed types before equality: bool/int aliases cannot pass.
    _plan(cohort["plan"], coordinates)
    _pins(cohort["pins"])
    _require(cohort["plan"] == plan and cohort["pins"] == pins, "external cohort pins")
    rows = cohort["observations"]
    _require(
        type(rows) is list and len(rows) == len(coordinates) * REPETITIONS,
        "all nine observations per coordinate",
    )
    receipts, processes = set(), set()
    for index, row in enumerate(rows):
        _closed(
            row,
            "coordinate repetition begin_ns end_ns pid birth_100ns receipt_sha256 cli_samples",
        )
        _require(
            row["coordinate"] == coordinates[index // REPETITIONS]
            and _integer(row["repetition"]) == index % REPETITIONS,
            "exact coordinate/repetition order",
        )
        begin, end = _integer(row["begin_ns"]), _integer(row["end_ns"])
        _require(end > begin, "positive complete interval")
        process = (_integer(row["pid"], 1), _integer(row["birth_100ns"], 1))
        _hash(row["receipt_sha256"])
        if row["coordinate"][0] == "latency:cli-startup":
            _closed(row["cli_samples"], "request_ns control_ns")
            for values in row["cli_samples"].values():
                _require(
                    type(values) is list and len(values) == 64, "all 64 raw CLI pairs"
                )
                for value in values:
                    _integer(value, 1)
            _require(
                sum(sum(v) for v in row["cli_samples"].values()) <= end - begin,
                "serial CLI samples exceed enclosing interval",
            )
        else:
            _require(row["cli_samples"] is None, "CLI channels only on CLI coordinates")
        _require(
            row["receipt_sha256"] not in receipts and process not in processes,
            "no reused receipt or process",
        )
        receipts.add(row["receipt_sha256"])
        processes.add(process)
    return cohort, receipts, processes


def _statistics(values):
    median = sorted(values)[4]
    mad = sorted(abs(v - median) for v in values)[4]
    stable = mad * 10_000 <= median * MARGIN_BP and all(
        median * (10_000 - MARGIN_BP) <= v * 10_000 <= median * (10_000 + MARGIN_BP)
        for v in values
    )
    return dict(median=median, mad=mad, values=values, reference_stable=stable)


def _cli_medians_twice(row):
    if row["cli_samples"] is None:
        return {}
    return {
        key: sum(sorted(values)[31:33]) for key, values in row["cli_samples"].items()
    }


def freeze_reference(data, sha256, *, plan, pins, coordinates):
    """Retain all nine observations and freeze arithmetic before any holdout.

    Unstable input produces an explicitly unstable frozen record, not new samples
    or a more generous bound. Callers must not acquire holdouts from such a record.
    """
    cohort, _, _ = _cohort(
        data,
        sha256,
        role="reference-only",
        plan=plan,
        pins=pins,
        coordinates=coordinates,
    )
    bounds = []
    for index, key in enumerate(coordinates):
        rows = cohort["observations"][index * REPETITIONS : (index + 1) * REPETITIONS]
        values = [r["end_ns"] - r["begin_ns"] for r in rows]
        summary = _statistics(values)
        cli = {
            key: _statistics([_cli_medians_twice(row)[key] for row in rows])
            for key in _cli_medians_twice(rows[0])
        }
        bounds.append(
            dict(
                coordinate=key,
                median_ns=summary["median"],
                mad_ns=summary["mad"],
                elapsed_ns=values,
                cli_medians_twice_ns=cli,
                reference_stable=summary["reference_stable"]
                and all(s["reference_stable"] for s in cli.values()),
            )
        )
    frozen = _encode(
        dict(
            method=METHOD,
            role="unqualified-frozen-whole-process-bounds",
            reference_json=data.decode("utf-8"),
            reference_sha256=sha256,
            margin_basis_points=MARGIN_BP,
            bounds=bounds,
            reference_stable=all(b["reference_stable"] for b in bounds),
            certification_eligible=False,
            baseline_admission=False,
            quota_qualified=False,
        )
    )
    _require(len(frozen) <= MAX_BYTES, "bounded frozen reference")
    return frozen


def check_holdout(
    frozen,
    frozen_sha256,
    data,
    sha256,
    *,
    reference_sha256,
    plan,
    reference_pins,
    holdout_pins,
    coordinates,
):
    """Compare a complete independent holdout without fitting any value to it.

    This checks supplied shapes and arithmetic, not signed execution or actual
    independence. No result grants performance, quota or baseline qualification.
    """
    record = _read(frozen, frozen_sha256)
    _require(
        type(record) is dict and type(record.get("reference_json")) is str,
        "frozen reference",
    )
    original = record["reference_json"].encode("utf-8")
    recomputed = freeze_reference(
        original,
        reference_sha256,
        plan=plan,
        pins=reference_pins,
        coordinates=coordinates,
    )
    _require(frozen == recomputed, "frozen reference arithmetic or pins changed")
    _require(record["reference_stable"], "unstable reference cannot qualify a holdout")
    _, receipts, processes = _cohort(
        original,
        reference_sha256,
        role="reference-only",
        plan=plan,
        pins=reference_pins,
        coordinates=coordinates,
    )
    holdout, new_receipts, new_processes = _cohort(
        data,
        sha256,
        role="source-distinct-holdout",
        plan=plan,
        pins=holdout_pins,
        coordinates=coordinates,
    )
    _require(
        reference_pins["source_sha"] != holdout_pins["source_sha"]
        and reference_pins["acquisition_sha256"] != holdout_pins["acquisition_sha256"],
        "source-distinct independent acquisition required",
    )
    _require(
        not receipts & new_receipts and not processes & new_processes,
        "cross-cohort observation reuse",
    )
    comparisons = []
    for index, row in enumerate(holdout["observations"]):
        elapsed = row["end_ns"] - row["begin_ns"]
        median = record["bounds"][index // REPETITIONS]["median_ns"]
        cli = {}
        for key, value in _cli_medians_twice(row).items():
            reference = record["bounds"][index // REPETITIONS]["cli_medians_twice_ns"][
                key
            ]["median"]
            cli[key] = dict(
                median_twice_ns=value,
                reference_median_twice_ns=reference,
                within_bound=value * 10_000 <= reference * (10_000 + MARGIN_BP),
            )
        comparisons.append(
            dict(
                coordinate=row["coordinate"],
                repetition=row["repetition"],
                receipt_sha256=row["receipt_sha256"],
                elapsed_ns=elapsed,
                reference_median_ns=median,
                whole_interval_within_bound=elapsed * 10_000
                <= median * (10_000 + MARGIN_BP),
                cli_comparisons=cli,
                within_bound=elapsed * 10_000 <= median * (10_000 + MARGIN_BP)
                and all(s["within_bound"] for s in cli.values()),
            )
        )
    return dict(
        method=METHOD,
        role="unqualified-whole-process-holdout-comparison",
        frozen_sha256=frozen_sha256,
        holdout_sha256=sha256,
        within_bounds=all(row["within_bound"] for row in comparisons),
        comparisons=comparisons,
        certification_eligible=False,
        baseline_admission=False,
        quota_qualified=False,
    )
