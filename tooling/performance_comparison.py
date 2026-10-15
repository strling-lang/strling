"""Offline prototype for variable-frequency comparison; not admission authority.

No host queries, sampling, baseline creation, or certification writes occur here.
Ceilings must come from a separately governed, version-compatible contract.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import ClassVar, Mapping, Sequence

from tooling.performance_resource_certification import normalized_launch_median


COMPARISON_VERSION = "variable-frequency-paired-wall-cpu-v2"
CYCLE_COMPARISON_VERSION = "paired-wall-process-cycles-v3"
NATIVE_CLI_CYCLE_CONTRACT = "native-cli-process-tree-cycles-v1"
CLI_CYCLE_SOURCE_PATHS = (
    "tests/certification/performance-resource/1.0/runner/src/main.rs",
    "tests/certification/performance-resource/1.0/runner/src/cli_cycles.rs",
    "tooling/performance_resource_certification.py",
    "tooling/performance_comparison.py",
    "tooling/performance_windows.py",
)


def validate_cycle_baseline_binding(
    baseline: Mapping[str, object],
    *,
    expected_sources: Mapping[str, str],
    expected_environment_fingerprint: str,
    expected_reference_commit: str,
) -> None:
    """Require fresh explicit domain/source/environment binding, never migrate data.

    The full baseline validator must independently validate measured denominators,
    fingerprints, budgets and provenance. This additional guard grants no authority.
    """
    binding = baseline.get("cli_cycle_binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "method",
        "comparison_version",
        "counter_api",
        "unit",
        "collector_source_fingerprints",
    }:
        raise ValueError(
            "fresh cycle-domain baseline required; legacy time baseline incompatible"
        )
    if (
        binding["method"] != NATIVE_CLI_CYCLE_CONTRACT
        or binding["comparison_version"] != CYCLE_COMPARISON_VERSION
        or binding["counter_api"] != "QueryProcessCycleTime"
        or binding["unit"] != "processor_cycles"
        or set(expected_sources) != set(CLI_CYCLE_SOURCE_PATHS)
        or any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
            for v in expected_sources.values()
        )
        or binding["collector_source_fingerprints"] != dict(expected_sources)
        or len(expected_environment_fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in expected_environment_fingerprint)
        or len(expected_reference_commit) != 40
        or any(c not in "0123456789abcdef" for c in expected_reference_commit)
        or baseline.get("environment_fingerprint") != expected_environment_fingerprint
        or baseline.get("source_commit") != expected_reference_commit
    ):
        raise ValueError("cycle baseline domain/source/environment identity mismatch")


def validate_cli_cycle_result(result: Mapping[str, object]) -> dict[str, object]:
    """Validate exact native wire evidence, without authenticating its producer."""
    if (
        result.get("runner_version") != "1.11.0"
        or result.get("cli_cycle_contract") != NATIVE_CLI_CYCLE_CONTRACT
        or result.get("operation_id") != "latency:cli-startup"
        or result.get("platform") != "windows"
        or type(result.get("batch_iterations")) is not int
        or result.get("batch_iterations") != 1
        or type(result.get("sample_iterations")) is not int
        or result.get("sample_iterations") != 64
    ):
        raise ValueError("incompatible native CLI cycle producer/denominator")
    checked: dict[str, object] = {"cli_cycle_contract": NATIVE_CLI_CYCLE_CONTRACT}
    for key in ("cli_request_cycle_evidence", "cli_control_cycle_evidence"):
        values = result.get(key)
        if not isinstance(values, list) or len(values) != 64:
            raise ValueError("complete paired native CLI cycle evidence required")
        for value in values:
            if not isinstance(value, Mapping) or set(value) != {
                "contract",
                "counter_api",
                "unit",
                "child_launches",
                "parent_started",
                "parent_ended",
                "parent_cycles",
                "child_cycles",
                "tree_cycles",
            }:
                raise ValueError("malformed native CLI cycle evidence")
            if (
                value["contract"] != NATIVE_CLI_CYCLE_CONTRACT
                or value["counter_api"] != "QueryProcessCycleTime"
                or value["unit"] != "processor_cycles"
                or type(value["child_launches"]) is not int
                or value["child_launches"] != 1
                or any(
                    type(value[k]) is not int or not 0 <= value[k] < 2**64
                    for k in (
                        "parent_started",
                        "parent_ended",
                        "parent_cycles",
                        "child_cycles",
                        "tree_cycles",
                    )
                )
                or value["parent_cycles"] <= 0
                or value["child_cycles"] <= 0
                or value["parent_ended"] - value["parent_started"]
                != value["parent_cycles"]
                or value["parent_cycles"] + value["child_cycles"]
                != value["tree_cycles"]
            ):
                raise ValueError("native CLI cycle identity/accounting mismatch")
        checked[key] = copy.deepcopy(values)
    return checked


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def split_frequency_identity(
    power: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, int]]:
    """Separate current frequency only; never discard limits or stable controls."""
    frequency = power.get("selected_processor_frequency")
    if not isinstance(frequency, Mapping):
        raise ValueError("missing frequency telemetry")
    for key in ("current_mhz", "maximum_mhz", "mhz_limit"):
        if not _positive(frequency.get(key)):
            raise ValueError(f"invalid frequency telemetry: {key}")
    processor = frequency.get("processor_number")
    if type(processor) is not int or processor < 0:
        raise ValueError("invalid processor identity")
    stable = copy.deepcopy(dict(power))
    stable_frequency = dict(frequency)
    current = stable_frequency.pop("current_mhz")
    stable["selected_processor_frequency"] = stable_frequency
    return stable, {"current_mhz": current}


@dataclass(frozen=True)
class ComparisonContract:
    expected_version: ClassVar[str] = COMPARISON_VERSION
    version: str
    baseline_signal: int
    relative_budget_basis_points: int
    signal_ceiling: int
    wall_median_ceiling: int
    wall_sample_ceiling: int

    def __post_init__(self) -> None:
        if self.version != self.expected_version:
            raise ValueError(
                "incompatible comparison contract; fresh baseline required"
            )
        if not all(
            _positive(value)
            for value in (
                self.baseline_signal,
                self.signal_ceiling,
                self.wall_median_ceiling,
                self.wall_sample_ceiling,
            )
        ):
            raise ValueError("explicit positive ceilings required")
        if (
            type(self.relative_budget_basis_points) is not int
            or self.relative_budget_basis_points < 0
            or self.wall_sample_ceiling < self.wall_median_ceiling
        ):
            raise ValueError("invalid comparison budgets")


@dataclass(frozen=True)
class CycleComparisonContract(ComparisonContract):
    expected_version: ClassVar[str] = CYCLE_COMPARISON_VERSION


@dataclass(frozen=True)
class CycleAttributionContract:
    baseline_sha256: str
    control_wall_minimum: int
    control_wall_maximum: int
    control_cycles_minimum: int
    control_cycles_maximum: int
    request_cycles_median_ceiling: int
    request_cycles_sample_ceiling: int

    def __post_init__(self) -> None:
        # Reuse structural validation only; units remain a distinct runtime type.
        AttributionContract(
            self.baseline_sha256,
            self.control_wall_minimum,
            self.control_wall_maximum,
            self.control_cycles_minimum,
            self.control_cycles_maximum,
            self.request_cycles_median_ceiling,
            self.request_cycles_sample_ceiling,
        )


@dataclass(frozen=True)
class AttributionContract:
    """Independent baseline-bound anchors, never inferred from candidate samples."""

    baseline_sha256: str
    control_wall_minimum: int
    control_wall_maximum: int
    control_cpu_minimum: int
    control_cpu_maximum: int
    request_cpu_median_ceiling: int
    request_cpu_sample_ceiling: int

    def __post_init__(self) -> None:
        if (
            len(self.baseline_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.baseline_sha256)
            or not all(
                _positive(value)
                for value in (
                    self.control_wall_minimum,
                    self.control_wall_maximum,
                    self.control_cpu_minimum,
                    self.control_cpu_maximum,
                    self.request_cpu_median_ceiling,
                    self.request_cpu_sample_ceiling,
                )
            )
            or self.control_wall_minimum > self.control_wall_maximum
            or self.control_cpu_minimum > self.control_cpu_maximum
            or self.request_cpu_median_ceiling > self.request_cpu_sample_ceiling
        ):
            raise ValueError("invalid baseline-bound attribution contract")


def compare_pairs(
    contract: ComparisonContract,
    request: Sequence[int],
    control: Sequence[int],
    *,
    attribution: AttributionContract,
    request_cpu: Sequence[int],
    control_cpu: Sequence[int],
    baseline_sha256: str,
    baseline_identity: Mapping[str, object],
    observed_identity: Mapping[str, object],
    observation_version: str,
) -> dict[str, object]:
    """Keep all 64 pairs; require relative, both order-strata, and wall gates.

    Callers supply acquisition order: alternating request-first/control-first.
    This pure evaluator cannot authenticate acquisition or establish valid ceilings.
    """
    if (
        type(contract) is not ComparisonContract
        or type(attribution) is not AttributionContract
    ):
        raise ValueError(
            "time-domain contract required; cycle baselines are incompatible"
        )
    if observation_version != contract.version:
        raise ValueError("incompatible observation version")
    if baseline_sha256 != attribution.baseline_sha256:
        raise ValueError("incompatible attribution baseline")
    if baseline_identity != observed_identity:
        raise ValueError("incompatible stable execution identity")
    signal = normalized_launch_median(request, control)
    for cpu, wall in ((request_cpu, request), (control_cpu, control)):
        if len(cpu) != 64 or any(not _positive(value) for value in cpu):
            raise ValueError("64 positive process-tree CPU observations required")
        if any(c > w for c, w in zip(cpu, wall)):
            raise ValueError("CPU exceeds wall time for single-core process tree")
    relative_ceiling = (
        contract.baseline_signal * (10_000 + contract.relative_budget_basis_points)
    ) // 10_000

    def median_twice(values: Sequence[int]) -> int:
        ordered = sorted(values)
        return ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]

    # Exact integer ratios, preserving both balanced acquisition-order strata.
    strata = [
        (
            median_twice(request[offset::2]) * 10_000
            + median_twice(control[offset::2])
            - 1
        )
        // median_twice(control[offset::2])
        for offset in (0, 1)
    ]
    checks = {
        "relative": signal <= relative_ceiling,
        "signal_absolute": signal <= contract.signal_ceiling,
        "order_strata": all(
            value <= min(relative_ceiling, contract.signal_ceiling) for value in strata
        ),
        "wall_median": median_twice(request) <= 2 * contract.wall_median_ceiling,
        "wall_samples": max(request) <= contract.wall_sample_ceiling,
        "control_wall_anchor": all(
            attribution.control_wall_minimum
            <= value
            <= attribution.control_wall_maximum
            for value in control
        ),
        "control_cpu_anchor": all(
            attribution.control_cpu_minimum <= value <= attribution.control_cpu_maximum
            for value in control_cpu
        ),
        "request_cpu_median": (
            median_twice(request_cpu) <= 2 * attribution.request_cpu_median_ceiling
        ),
        "request_cpu_samples": max(request_cpu)
        <= attribution.request_cpu_sample_ceiling,
    }
    return {
        "comparison_version": contract.version,
        "diagnostic_only": True,
        "passed": all(checks.values()),
        "checks": checks,
        "signal": signal,
        "order_signals": strata,
        "request_samples": list(request),
        "control_samples": list(control),
        "request_cpu_samples": list(request_cpu),
        "control_cpu_samples": list(control_cpu),
        "attribution_baseline_sha256": baseline_sha256,
    }


def compare_cycle_pairs(
    contract: CycleComparisonContract,
    request: Sequence[int],
    control: Sequence[int],
    *,
    attribution: CycleAttributionContract,
    request_cycles: Sequence[int],
    control_cycles: Sequence[int],
    baseline_sha256: str,
    baseline_identity: Mapping[str, object],
    observed_identity: Mapping[str, object],
    observation_version: str,
    counter_api: str,
    counter_unit: str,
) -> dict[str, object]:
    """Keep all 64 pairs; require relative, both order-strata, and wall gates.

    Callers supply acquisition order: alternating request-first/control-first.
    This pure evaluator cannot authenticate acquisition or establish valid ceilings.
    """
    if (
        type(contract) is not CycleComparisonContract
        or type(attribution) is not CycleAttributionContract
    ):
        raise ValueError(
            "cycle-domain contract required; time baselines are incompatible"
        )
    if observation_version != contract.version:
        raise ValueError("incompatible observation version")
    if baseline_sha256 != attribution.baseline_sha256:
        raise ValueError("incompatible attribution baseline")
    if baseline_identity != observed_identity:
        raise ValueError("incompatible stable execution identity")
    signal = normalized_launch_median(request, control)
    if counter_api != "QueryProcessCycleTime" or counter_unit != "processor_cycles":
        raise ValueError("incompatible cycle counter API or unit")
    for cycles in (request_cycles, control_cycles):
        if len(cycles) != 64 or any(not _positive(value) for value in cycles):
            raise ValueError("64 positive process-tree cycle observations required")
    relative_ceiling = (
        contract.baseline_signal * (10_000 + contract.relative_budget_basis_points)
    ) // 10_000

    def median_twice(values: Sequence[int]) -> int:
        ordered = sorted(values)
        return ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]

    # Exact integer ratios, preserving both balanced acquisition-order strata.
    strata = [
        (
            median_twice(request[offset::2]) * 10_000
            + median_twice(control[offset::2])
            - 1
        )
        // median_twice(control[offset::2])
        for offset in (0, 1)
    ]
    checks = {
        "relative": signal <= relative_ceiling,
        "signal_absolute": signal <= contract.signal_ceiling,
        "order_strata": all(
            value <= min(relative_ceiling, contract.signal_ceiling) for value in strata
        ),
        "wall_median": median_twice(request) <= 2 * contract.wall_median_ceiling,
        "wall_samples": max(request) <= contract.wall_sample_ceiling,
        "control_wall_anchor": all(
            attribution.control_wall_minimum
            <= value
            <= attribution.control_wall_maximum
            for value in control
        ),
        "control_cycles_anchor": all(
            attribution.control_cycles_minimum
            <= value
            <= attribution.control_cycles_maximum
            for value in control_cycles
        ),
        "request_cycles_median": (
            median_twice(request_cycles)
            <= 2 * attribution.request_cycles_median_ceiling
        ),
        "request_cycles_samples": max(request_cycles)
        <= attribution.request_cycles_sample_ceiling,
    }
    return {
        "comparison_version": contract.version,
        "diagnostic_only": True,
        "counter_api": counter_api,
        "counter_unit": counter_unit,
        "passed": all(checks.values()),
        "checks": checks,
        "signal": signal,
        "order_signals": strata,
        "request_samples": list(request),
        "control_samples": list(control),
        "request_cycles_samples": list(request_cycles),
        "control_cycles_samples": list(control_cycles),
        "attribution_baseline_sha256": baseline_sha256,
    }
