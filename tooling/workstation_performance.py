"""Exact, prospectively fixed decisions for shared-workstation comparisons.

This module does no acquisition and grants no source or process provenance.
Its caller must independently reconstruct complete pinned raw observations.
"""

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "governance/workstation-performance-policy.json"
CONTEXT = "shared-workstation-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=1):
    require(type(value) is int and minimum <= value < 2**63, "exact bounded integer")
    return value


def validate_policy(value):
    require(value["policy_id"] == CONTEXT and value["status"] == "accepted", "policy")
    for key, expected in {
        "latency_warmups": 512,
        "policy_revision": 3,
        "cli_warmups": 8,
        "latency_samples": 64,
        "paired_repetitions": 9,
        "median_regression_basis_points": 1000,
        "pair_regression_basis_points": 2500,
        "minimum_passing_pairs": 7,
        "tail_percentile": 95,
        "tail_regression_basis_points": 2500,
        "tail_pair_regression_basis_points": 5000,
        "whole_process_regression_basis_points": 2500,
        "whole_process_pair_regression_basis_points": 5000,
        "calibration_minimum_nanoseconds": 1000000,
        "maximum_batch_iterations": 4096,
        "memory_absolute_ceiling_bytes": 67108864,
        "memory_relative_allowance_basis_points": 1000,
        "memory_fixed_allowance_bytes": 1048576,
    }.items():
        require(integer(value[key]) == expected, "versioned policy changed: " + key)
    require(
        type(value["reference_first"]) is list
        and len(value["reference_first"]) == 9
        and all(type(x) is bool for x in value["reference_first"])
        and value["reference_first"] == [i % 2 == 0 for i in range(9)],
        "fixed pair order",
    )
    require(
        value["reference_source"] == "1593801e187dfe913357e92e6c798b47b8944370",
        "fixed independently frozen reference source",
    )
    require(value["memory_metric"] == "process-lifetime-peak-commit-bytes", "metric")
    require(value["sample_retention"] == "all-fixed-slots-v1", "fixed raw slots")
    require(
        value["tail_estimator"] == "pooled-fixed-slots-nearest-rank-v1",
        "fixed pooled tail estimator",
    )
    return value


def load_policy(path=POLICY_PATH):
    return validate_policy(json.loads(Path(path).read_text(encoding="utf-8")))


def median_twice(values, count=64):
    require(type(values) is list and len(values) == count, "complete sample vector")
    ordered = sorted(integer(x) for x in values)
    middle = count // 2
    return ordered[middle - 1] + ordered[middle]


def _decision(
    ratios,
    policy,
    *,
    center_key="median_regression_basis_points",
    pair_key="pair_regression_basis_points",
):
    require(len(ratios) == policy["paired_repetitions"], "all prospective pairs")
    center = sorted(ratios)[len(ratios) // 2]
    limit = Fraction(10000 + policy[center_key], 10000)
    pair_limit = Fraction(10000 + policy[pair_key], 10000)
    passed = sum(r <= pair_limit for r in ratios)
    return {
        "passed": center <= limit and passed >= policy["minimum_passing_pairs"],
        "median_ratio": [center.numerator, center.denominator],
        "pair_ratios": [[r.numerator, r.denominator] for r in ratios],
        "passing_pairs": passed,
        "total_pairs": len(ratios),
    }


def latency_decision(pairs, policy=None):
    policy = load_policy() if policy is None else policy
    require(
        type(pairs) is list and len(pairs) == policy["paired_repetitions"], "nine pairs"
    )
    ratios = []
    reference_medians, candidate_medians = [], []
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"reference", "candidate"}, "pair")
        reference = median_twice(pair["reference"], policy["latency_samples"])
        candidate = median_twice(pair["candidate"], policy["latency_samples"])
        ratios.append(Fraction(candidate, reference))
        reference_medians.append(reference)
        candidate_medians.append(candidate)
    result = _decision(ratios, policy)
    # Preserve both absolute distributions; a ratio is not a wall-time guarantee.
    result["reference_medians_twice_ns"] = reference_medians
    result["candidate_medians_twice_ns"] = candidate_medians
    return result


def tail_decision(pairs, policy=None):
    """Compare the complete fixed-slot tails without excluding noisy blocks.

    A block of 64 values has only four values at or above its p95 rank. Moving
    one stall across a block boundary can change that block's p95 substantially.
    Pool all nine complete blocks; keep their individual decisions as diagnostics.
    This is a fixed empirical rule, not a population confidence bound.
    """
    policy = load_policy() if policy is None else policy
    require(
        type(pairs) is list and len(pairs) == policy["paired_repetitions"], "nine pairs"
    )
    pooled = {lane: [] for lane in ("reference", "candidate")}
    block_ratios = []
    block_rank = (policy["tail_percentile"] * policy["latency_samples"] + 99) // 100 - 1
    for pair in pairs:
        require(type(pair) is dict and set(pair) == set(pooled), "pair")
        tails = {}
        for lane in pooled:
            median_twice(pair[lane], policy["latency_samples"])
            pooled[lane].extend(pair[lane])
            tails[lane] = sorted(pair[lane])[block_rank]
        block_ratios.append(Fraction(tails["candidate"], tails["reference"]))
    count = policy["latency_samples"] * policy["paired_repetitions"]
    rank = (policy["tail_percentile"] * count + 99) // 100 - 1
    tails = {lane: sorted(values)[rank] for lane, values in pooled.items()}
    ratio = Fraction(tails["candidate"], tails["reference"])
    return {
        "passed": ratio
        <= Fraction(10000 + policy["tail_regression_basis_points"], 10000),
        "method": policy["tail_estimator"],
        "samples_per_lane": count,
        "rank_one_based": rank + 1,
        "reference_p95_ns": tails["reference"],
        "candidate_p95_ns": tails["candidate"],
        "pooled_ratio": [ratio.numerator, ratio.denominator],
        "block_diagnostics": dict(
            diagnostic_only=True,
            **_decision(
                block_ratios,
                policy,
                center_key="tail_regression_basis_points",
                pair_key="tail_pair_regression_basis_points",
            ),
        ),
    }


def guarded_latency_decision(pairs, policy=None, *, cli=False):
    """All fixed-slot distributions and whole root lifetimes are mandatory.

    The CLI request and control marginals are each guarded. Paired ratios are
    retained as context only; a common slowdown cannot cancel out of the guards.
    """
    policy = load_policy() if policy is None else policy
    require(
        type(pairs) is list and len(pairs) == policy["paired_repetitions"], "nine pairs"
    )
    channels = ["samples", "control_samples"] if cli else ["samples"]
    result = {"passed": True, "channels": {}}
    whole = []
    cli_ratios = []
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"reference", "candidate"}, "pair")
        whole.append(
            Fraction(
                integer(pair["candidate"]["whole_action_ns"]),
                integer(pair["reference"]["whole_action_ns"]),
            )
        )
        if cli:
            row = {}
            for lane in ("reference", "candidate"):
                request = pair[lane]["samples"]
                control = pair[lane]["control_samples"]
                median_twice(request, policy["latency_samples"])
                median_twice(control, policy["latency_samples"])
                row[lane] = [[integer(r), integer(c)] for r, c in zip(request, control)]
            cli_ratios.append(row)
    for channel in channels:
        values = [
            {lane: pair[lane][channel] for lane in ("reference", "candidate")}
            for pair in pairs
        ]
        median = latency_decision(values, policy)
        tail = tail_decision(values, policy)
        result["channels"][channel] = {"median": median, "tail": tail}
        result["passed"] &= median["passed"] and tail["passed"]
    result["whole_process"] = _decision(
        whole,
        policy,
        center_key="whole_process_regression_basis_points",
        pair_key="whole_process_pair_regression_basis_points",
    )
    result["passed"] &= result["whole_process"]["passed"]
    if cli:
        result["request_control_ratios"] = cli_ratios
    return result


def memory_decision(pairs, policy=None):
    policy = load_policy() if policy is None else policy
    require(
        type(pairs) is list and len(pairs) == policy["paired_repetitions"], "nine pairs"
    )
    absolute_ok = True
    relative_ok = True
    values = []
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"reference", "candidate"}, "pair")
        reference, candidate = integer(pair["reference"]), integer(pair["candidate"])
        values.append([reference, candidate])
        absolute_ok &= (
            max(reference, candidate) <= policy["memory_absolute_ceiling_bytes"]
        )
        relative_ok &= (
            candidate * 10000
            <= reference * (10000 + policy["memory_relative_allowance_basis_points"])
            + policy["memory_fixed_allowance_bytes"] * 10000
        )
    return {
        "passed": bool(absolute_ok and relative_ok),
        "absolute_passed": bool(absolute_ok),
        "relative_passed": bool(relative_ok),
        "metric": policy["memory_metric"],
        "all_pair_peaks_bytes": values,
    }
