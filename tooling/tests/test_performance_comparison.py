from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import Mock, patch

from tooling.performance_comparison import (
    COMPARISON_VERSION,
    CYCLE_COMPARISON_VERSION,
    CLI_CYCLE_SOURCE_PATHS,
    NATIVE_CLI_CYCLE_CONTRACT,
    AttributionContract,
    ComparisonContract,
    CycleAttributionContract,
    CycleComparisonContract,
    compare_cycle_pairs,
    compare_pairs,
    split_frequency_identity,
    validate_cli_cycle_result,
    validate_cycle_baseline_binding,
)


class VariableFrequencyComparisonTests(unittest.TestCase):
    def native_result(self) -> dict[str, object]:
        row = {
            "contract": NATIVE_CLI_CYCLE_CONTRACT,
            "counter_api": "QueryProcessCycleTime",
            "unit": "processor_cycles",
            "child_launches": 1,
            "parent_started": 10,
            "parent_ended": 30,
            "parent_cycles": 20,
            "child_cycles": 50,
            "tree_cycles": 70,
        }
        return {
            "runner_version": "1.11.0",
            "cli_cycle_contract": NATIVE_CLI_CYCLE_CONTRACT,
            "operation_id": "latency:cli-startup",
            "platform": "windows",
            "batch_iterations": 1,
            "sample_iterations": 64,
            "cli_request_cycle_evidence": [copy.deepcopy(row) for _ in range(64)],
            "cli_control_cycle_evidence": [copy.deepcopy(row) for _ in range(64)],
        }

    def test_native_wire_count_identity_arithmetic_and_no_mutation(self) -> None:
        result = self.native_result()
        original = copy.deepcopy(result)
        checked = validate_cli_cycle_result(result)
        self.assertEqual(result, original)
        checked["cli_request_cycle_evidence"][0]["tree_cycles"] = 1
        self.assertEqual(result, original)
        for key, value in (
            ("runner_version", "1.10.0"),
            ("batch_iterations", True),
            ("sample_iterations", 63),
            ("platform", "linux"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_cli_cycle_result(result | {key: value})
        for field, value in (
            ("tree_cycles", 71),
            ("parent_ended", 9),
            ("child_cycles", 0),
            ("child_launches", True),
            ("unit", "nanoseconds"),
            ("tree_cycles", 2**64),
        ):
            changed = copy.deepcopy(result)
            changed["cli_request_cycle_evidence"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_cli_cycle_result(changed)

    def test_cycle_baseline_requires_new_domain_and_all_sources(self) -> None:
        sources = {p: "a" * 64 for p in CLI_CYCLE_SOURCE_PATHS}
        baseline = {
            "cli_cycle_binding": {
                "method": NATIVE_CLI_CYCLE_CONTRACT,
                "comparison_version": CYCLE_COMPARISON_VERSION,
                "counter_api": "QueryProcessCycleTime",
                "unit": "processor_cycles",
                "collector_source_fingerprints": sources,
            },
            "environment_fingerprint": "b" * 64,
            "source_commit": "c" * 40,
        }
        arguments = {
            "expected_sources": sources,
            "expected_environment_fingerprint": "b" * 64,
            "expected_reference_commit": "c" * 40,
        }
        validate_cycle_baseline_binding(baseline, **arguments)
        for changed in (
            {},
            baseline | {"source_commit": "d" * 40},
            baseline
            | {
                "cli_cycle_binding": baseline["cli_cycle_binding"]
                | {"unit": "nanoseconds"}
            },
        ):
            with self.assertRaises(ValueError):
                validate_cycle_baseline_binding(changed, **arguments)
        with self.assertRaises(ValueError):
            validate_cycle_baseline_binding(
                baseline, **(arguments | {"expected_sources": {}})
            )

    def test_controller_rejects_invalid_cycle_selection_without_launch(self) -> None:
        from tooling.performance_resource_certification import (
            PerformanceResourceError,
            _runner_samples,
        )

        with patch("tooling.performance_resource_certification.subprocess.run") as run:
            with self.assertRaises(PerformanceResourceError):
                _runner_samples(
                    "latency:cli-startup",
                    "fixture:semantic-tiny",
                    artifacts={},
                    warmups=512,
                    samples=63,
                    batch_iterations=1,
                    minimum_sample_nanoseconds=None,
                    maximum_batch_iterations=1,
                    selected_logical_cpu=1,
                    execution_resource={"platform": "windows"},
                    cli_cycle_contract=NATIVE_CLI_CYCLE_CONTRACT,
                )
            run.assert_not_called()

    def test_controller_preserves_native_cycle_pairs_and_rejects_unsolicited_domain(
        self,
    ) -> None:
        from tooling.performance_resource_certification import (
            MAXIMUM_DESCHEDULING_NANOSECONDS,
            MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER,
            PerformanceResourceError,
            _runner_samples,
        )

        result = self.native_result() | {
            "fixture_id": "fixture:semantic-tiny",
            "unit": "nanoseconds",
            "maximum_descheduling_nanoseconds": MAXIMUM_DESCHEDULING_NANOSECONDS,
            "maximum_sample_attempts": 64 * MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER,
            "sample_attempts": 64,
            "rejected_batch_elapsed_samples": [],
            "rejected_process_cpu_batch_elapsed_samples": [],
            "rejected_process_cpu_utilization_basis_points": [],
        }
        for prefix in ("", "control_"):
            result.update(
                {
                    prefix + "samples": [100_000_000] * 64,
                    prefix + "batch_elapsed_samples": [100_000_000] * 64,
                    prefix + "process_cpu_samples": [1] * 64,
                    prefix + "process_cpu_batch_elapsed_samples": [1] * 64,
                    prefix + "process_cpu_utilization_basis_points": [0] * 64,
                }
            )
        arguments = {
            "artifacts": {"runner": "synthetic-runner", "kernel": "synthetic-kernel"},
            "warmups": 512,
            "samples": 64,
            "batch_iterations": 1,
            "minimum_sample_nanoseconds": None,
            "maximum_batch_iterations": 1,
            "selected_logical_cpu": 1,
            "execution_resource": {"platform": "windows"},
        }
        with (
            patch(
                "tooling.performance_resource_certification.subprocess.run",
                return_value=Mock(stdout=json.dumps(result)),
            ) as run,
            patch(
                "tooling.performance_resource_certification._runner_resource_matches",
                return_value=True,
            ),
        ):
            observation = _runner_samples(
                "latency:cli-startup",
                "fixture:semantic-tiny",
                **arguments,
                cli_cycle_contract=NATIVE_CLI_CYCLE_CONTRACT,
            )
            self.assertEqual(
                observation["cli_request_cycle_evidence"],
                result["cli_request_cycle_evidence"],
            )
            self.assertIn("--cli-cycle-audit", run.call_args.args[0])
            with self.assertRaises(PerformanceResourceError):
                _runner_samples(
                    "latency:cli-startup", "fixture:semantic-tiny", **arguments
                )

    def cycle_arguments(self) -> dict[str, object]:
        return {
            "attribution": CycleAttributionContract(
                "a" * 64, 50, 150, 400, 600, 600, 800
            ),
            "request_cycles": [500] * 64,
            "control_cycles": [500] * 64,
            "baseline_sha256": "a" * 64,
            "baseline_identity": {"cpu": 1},
            "observed_identity": {"cpu": 1},
            "observation_version": CYCLE_COMPARISON_VERSION,
            "counter_api": "QueryProcessCycleTime",
            "counter_unit": "processor_cycles",
        }

    def test_cycle_domain_is_not_cpu_time_or_frequency_normalization(self) -> None:
        contract = CycleComparisonContract(
            CYCLE_COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250
        )
        result = compare_cycle_pairs(
            contract, [100] * 64, [100] * 64, **self.cycle_arguments()
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["request_cycles_samples"], [500] * 64)
        for field, value in (
            ("counter_unit", "nanoseconds"),
            ("counter_api", "GetProcessTimes"),
            ("request_cycles", [0] * 64),
            ("request_cycles", [500] * 63),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_cycle_pairs(
                    contract,
                    [100] * 64,
                    [100] * 64,
                    **(self.cycle_arguments() | {field: value}),
                )
        with self.assertRaises(ValueError):
            CycleComparisonContract(COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250)
        with self.assertRaises(ValueError):
            compare_cycle_pairs(
                ComparisonContract(COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250),
                [100] * 64,
                [100] * 64,
                **self.cycle_arguments(),
            )

    def test_cycles_reject_slow_control_concealment_order_and_baseline_mix(
        self,
    ) -> None:
        contract = CycleComparisonContract(
            CYCLE_COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250
        )
        result = compare_cycle_pairs(
            contract,
            [120] * 64,
            [140] * 64,
            **(self.cycle_arguments() | {"request_cycles": [700] * 64}),
        )
        self.assertTrue(result["checks"]["relative"])
        self.assertFalse(result["passed"])
        result = compare_cycle_pairs(
            contract, [140, 60] * 32, [100] * 64, **self.cycle_arguments()
        )
        self.assertFalse(result["checks"]["order_strata"])
        with self.assertRaises(ValueError):
            compare_cycle_pairs(
                contract,
                [100] * 64,
                [100] * 64,
                **(self.cycle_arguments() | {"baseline_sha256": "b" * 64}),
            )

    def compare(self, request: list[int], control: list[int]) -> dict[str, object]:
        return compare_pairs(
            ComparisonContract(COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250),
            request,
            control,
            attribution=AttributionContract("a" * 64, 50, 150, 40, 60, 60, 80),
            request_cpu=[50] * 64,
            control_cpu=[50] * 64,
            baseline_sha256="a" * 64,
            baseline_identity={"cpu": 1},
            observed_identity={"cpu": 1},
            observation_version=COMPARISON_VERSION,
        )

    def test_equal_and_bounded_common_mode(self) -> None:
        for value in (100, 140):
            self.assertTrue(self.compare([value] * 64, [value] * 64)["passed"])

    def test_common_mode_cannot_hide_absolute_slowdown(self) -> None:
        result = self.compare([200] * 64, [200] * 64)
        self.assertFalse(result["passed"])
        self.assertEqual(result["signal"], 10_000)

    def test_product_regression_and_asymmetric_contention_fail(self) -> None:
        self.assertFalse(self.compare([120] * 64, [100] * 64)["passed"])
        self.assertFalse(self.compare([100] * 63 + [300], [100] * 64)["passed"])

    def test_order_effect_cannot_cancel(self) -> None:
        result = self.compare([140, 60] * 32, [100] * 64)
        self.assertEqual(result["signal"], 10_000)
        self.assertFalse(result["passed"])

    def test_control_slowdown_does_not_override_wall_limit(self) -> None:
        self.assertFalse(self.compare([200] * 64, [400] * 64)["passed"])

    def test_retains_all_pairs_without_mutation(self) -> None:
        request, control = [100] * 64, [100] * 64
        before = copy.deepcopy((request, control))
        result = self.compare(request, control)
        self.assertEqual((request, control), before)
        self.assertEqual(result["request_samples"], request)
        self.assertEqual(result["control_samples"], control)
        with self.assertRaises(ValueError):
            self.compare(request[:-1], control[:-1])

    def test_version_and_identity_mismatch_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            ComparisonContract("historical", 10_000, 1000, 12_000, 150, 250)
        contract = ComparisonContract(
            COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250
        )
        for version, identity in (("historical", {}), (COMPARISON_VERSION, {"cpu": 2})):
            with self.assertRaises(ValueError):
                compare_pairs(
                    contract,
                    [100] * 64,
                    [100] * 64,
                    attribution=AttributionContract("a" * 64, 50, 150, 40, 60, 60, 80),
                    request_cpu=[50] * 64,
                    control_cpu=[50] * 64,
                    baseline_sha256="a" * 64,
                    baseline_identity={},
                    observed_identity=identity,
                    observation_version=version,
                )

    def test_slowed_control_cannot_conceal_request_cpu_regression(self) -> None:
        result = compare_pairs(
            ComparisonContract(COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250),
            [120] * 64,
            [140] * 64,
            attribution=AttributionContract("a" * 64, 50, 150, 40, 60, 60, 80),
            request_cpu=[70] * 64,
            control_cpu=[50] * 64,
            baseline_sha256="a" * 64,
            baseline_identity={},
            observed_identity={},
            observation_version=COMPARISON_VERSION,
        )
        self.assertTrue(result["checks"]["relative"])
        self.assertFalse(result["checks"]["request_cpu_median"])
        self.assertFalse(result["passed"])

    def test_control_drift_cpu_missing_and_baseline_mixing_fail_closed(self) -> None:
        arguments = {
            "attribution": AttributionContract("a" * 64, 50, 150, 40, 60, 60, 80),
            "request_cpu": [50] * 64,
            "control_cpu": [50] * 64,
            "baseline_sha256": "a" * 64,
            "baseline_identity": {},
            "observed_identity": {},
            "observation_version": COMPARISON_VERSION,
        }
        contract = ComparisonContract(
            COMPARISON_VERSION, 10_000, 1000, 12_000, 150, 250
        )
        for field, value in (
            ("request_cpu", []),
            ("control_cpu", [True] * 64),
            ("request_cpu", [101] * 64),
            ("baseline_sha256", "b" * 64),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_pairs(
                    contract, [100] * 64, [100] * 64, **(arguments | {field: value})
                )
        for control_wall, control_cpu in (
            ([151] * 64, [50] * 64),
            ([100] * 64, [61] * 64),
        ):
            result = compare_pairs(
                contract,
                [100] * 64,
                control_wall,
                **(arguments | {"control_cpu": control_cpu}),
            )
            self.assertFalse(result["passed"])

    def test_frequency_split_preserves_limits_and_rejects_missing_telemetry(
        self,
    ) -> None:
        power = {
            "selected_processor_frequency": {
                "processor_number": 1,
                "maximum_mhz": 2200,
                "mhz_limit": 2200,
                "current_mhz": 1466,
            },
            "processor_settings": {"boost": 0},
        }
        before = copy.deepcopy(power)
        stable, telemetry = split_frequency_identity(power)
        self.assertEqual(power, before)
        self.assertEqual(telemetry, {"current_mhz": 1466})
        self.assertEqual(stable["selected_processor_frequency"]["mhz_limit"], 2200)
        for value in (None, 0, "1466", True):
            changed = copy.deepcopy(power)
            changed["selected_processor_frequency"]["current_mhz"] = value
            with self.assertRaises(ValueError):
                split_frequency_identity(changed)
        with self.assertRaises(ValueError):
            split_frequency_identity({})
