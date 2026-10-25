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


def load_policy(path=POLICY_PATH):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(value["policy_id"] == CONTEXT and value["status"] == "accepted", "policy")
    for key, expected in {
        "latency_warmups": 512,
        "cli_warmups": 8,
        "latency_samples": 64,
        "paired_repetitions": 9,
        "median_regression_basis_points": 1000,
        "pair_regression_basis_points": 2500,
        "minimum_passing_pairs": 7,
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
    require(value["memory_metric"] == "process-lifetime-peak-commit-bytes", "metric")
    return value


def median_twice(values, count=64):
    require(type(values) is list and len(values) == count, "complete sample vector")
    ordered = sorted(integer(x) for x in values)
    middle = count // 2
    return ordered[middle - 1] + ordered[middle]


def _decision(ratios, policy):
    require(len(ratios) == policy["paired_repetitions"], "all prospective pairs")
    center = sorted(ratios)[len(ratios) // 2]
    limit = Fraction(10000 + policy["median_regression_basis_points"], 10000)
    pair_limit = Fraction(10000 + policy["pair_regression_basis_points"], 10000)
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
