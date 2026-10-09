"""Independent regression contracts for normalized typical warmed CLI latency."""

import unittest
import copy
import json
import tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from tooling import performance_resource_certification as performance
from tooling.local_certification_attestation import (
    AttestationError,
    _reconstruct_normalized_cli_median,
)

from tooling.performance_resource_certification import (
    PerformanceResourceError,
    controlled_launch_estimate,
    normalized_launch_median,
)


class LaunchNormalizationTests(unittest.TestCase):
    def test_cpu_accounting_representation_is_not_interval_resolution(self):
        # Independent integer accounting clock, not measured timing or producer code.
        quantum = 15_625_000
        phases = [0, quantum - 1] + [quantum * index // 64 for index in range(64)]
        short_deltas = {
            ((phase + 2_000_000) // quantum - phase // quantum) * quantum
            for phase in phases
        }
        self.assertEqual(short_deltas, {0, quantum})
        for phase in phases:
            self.assertEqual(
                ((phase + 2 * quantum) // quantum - phase // quantum) * quantum,
                31_250_000,
            )

    def test_native_precision_target_preserves_legacy_and_cli_selection(self):
        policy = copy.deepcopy(
            performance.load_json(performance.MANIFEST_PATH)["measurement_policy"]
        )
        field = "native_cpu_accounting_batch_target_nanoseconds"
        operation = "latency:supported-host-overhead"
        self.assertEqual(
            performance._batch_selection_target(policy, {"os": "windows"}, operation),
            2_000_000,
        )
        policy[field] = 31_250_000
        self.assertEqual(
            performance._batch_selection_target(policy, {"os": "windows"}, operation),
            31_250_000,
        )
        self.assertEqual(
            performance._batch_selection_target(policy, {"os": "linux"}, operation),
            2_000_000,
        )
        self.assertEqual(
            performance._batch_selection_target(
                policy, {"os": "windows"}, "latency:cli-startup"
            ),
            2_000_000,
        )
        for value in (0, 2_000_000, 31_250_001):
            with self.subTest(value=value):
                policy[field] = value
                with self.assertRaises(performance.PerformanceResourceError):
                    performance._batch_selection_target(
                        policy, {"os": "windows"}, operation
                    )

    def test_native_precision_reuses_exact_count_without_reselecting(self):
        manifest = copy.deepcopy(performance.load_json(performance.MANIFEST_PATH))
        manifest["measurement_policy"][
            "native_cpu_accounting_batch_target_nanoseconds"
        ] = 31_250_000
        with patch.object(performance, "_runner_samples", return_value={}) as runner:
            for count, target in ((None, 31_250_000), (80, None)):
                performance._measure_key(
                    ("latency:supported-host-overhead", "fixture:protocol-common"),
                    manifest=manifest,
                    artifacts={},
                    environment={"os": "windows", "execution_resource": {}},
                    batch_iterations=count,
                )
                options = runner.call_args.kwargs
                self.assertEqual(options["minimum_sample_nanoseconds"], target)
                self.assertEqual(options["batch_iterations"], count)
                self.assertEqual(options["warmups"], 512)
                self.assertEqual(options["samples"], 64)
                self.assertEqual(options["maximum_batch_iterations"], 4096)

    def test_migration_requires_confirmation_and_clean_source_before_io(self):
        for confirm, dirty, code in (
            (False, False, "launch-normalization-confirmation"),
            (True, True, "dirty-launch-normalization"),
        ):
            with (
                patch.object(
                    performance, "_git_identity", return_value=("2" * 40, dirty)
                ),
                patch.object(performance, "load_json") as load,
            ):
                with self.assertRaises(performance.PerformanceResourceError) as caught:
                    performance._migrate_cli_normalization_command(
                        confirm_launch_normalization=confirm,
                        rationale="Reviewed normalization and unchanged governed caps",
                    )
                self.assertEqual(caught.exception.code, code)
                load.assert_not_called()

    def test_fresh_calibration_and_baseline_validation_reconstruct_new_statistic(self):
        # Use only independently authored synthetic observations, never retained timing.
        from tooling.tests.test_performance_resource_certification import (
            PerformanceResourceCertificationContractTests as Fixtures,
        )

        manifest = performance.load_json(performance.MANIFEST_PATH)
        fixture_manifest = performance.load_json(performance.FIXTURE_MANIFEST_PATH)
        manifest["measurement_policy"]["relative_budget_formula"] = (
            performance.DERIVED_RELATIVE_BUDGET_FORMULA
        )
        manifest["measurement_policy"][
            "native_cpu_accounting_batch_target_nanoseconds"
        ] = 31_250_000
        cli = next(
            row for row in manifest["operations"] if row["id"] == "latency:cli-startup"
        )
        cli["relative_estimator"] = performance.ROBUST_CLI_LAUNCH_RELATIVE_ESTIMATOR
        cli["launch_schedule"] = performance.ROBUST_CLI_LAUNCH_SCHEDULE
        environment = Fixtures._environment()
        conditioning = Fixtures._conditioning_snapshot(environment)

        def observation(key, **kwargs):
            if key[0].startswith("latency:"):
                result = {
                    "samples": [1_100_000] * 64,
                    "batch_iterations": 1,
                    "batch_duration_samples": [1_100_000] * 64,
                }
                if key[0] == "latency:cli-startup":
                    # Authored same-multiset normalization with differing pair strata.
                    result.update(
                        samples=[1_100_000, 1_100_000, 9_900_000, 9_900_000] * 16,
                        batch_duration_samples=[
                            1_100_000,
                            1_100_000,
                            9_900_000,
                            9_900_000,
                        ]
                        * 16,
                        control_samples=[1_000_000, 9_000_000, 1_000_000, 9_000_000]
                        * 16,
                        control_batch_duration_samples=[
                            1_000_000,
                            9_000_000,
                            1_000_000,
                            9_000_000,
                        ]
                        * 16,
                    )
                return result
            return {
                "samples": [17],
                "batch_iterations": 1,
                "batch_duration_samples": None,
            }

        with (
            patch.object(performance, "_measure_key", side_effect=observation),
            patch.object(
                performance,
                "_acquire_quiet_conditioning_snapshot",
                return_value=conditioning,
            ),
        ):
            active, baseline = performance.calibrate_baseline(
                manifest,
                fixture_manifest,
                artifacts={},
                artifact_fingerprints=Fixtures._artifact_fingerprints(),
                environment=environment,
                source_commit="2" * 40,
                rationale="Independently authored new-normalization contract regression",
            )
        cli_rows = [
            row
            for row in baseline["measurements"]
            if row["operation_id"] == "latency:cli-startup"
        ]
        self.assertEqual(len(cli_rows), 2)
        self.assertTrue(all(row["relative_samples"] == [11000] * 9 for row in cli_rows))
        # The signed-evidence fixture must follow the newly declared contract
        # after activation, without ever reinterpreting retained real timing.
        from tooling.tests.test_local_certification_attestation import (
            LocalCertificationAttestationTests,
        )

        with tempfile.TemporaryDirectory(
            dir=performance.ROOT / "target/codex-tools"
        ) as temporary:
            directory = Path(temporary)
            manifest_path, baseline_path = (
                directory / "manifest.json",
                directory / "baseline.json",
            )
            manifest_path.write_text(json.dumps(active), encoding="utf-8")
            fixture_baseline = copy.deepcopy(baseline)
            for snapshot in fixture_baseline["conditioning_repetitions"]:
                snapshot["quiescence_observation"] = {"failures": []}
            baseline_path.write_text(json.dumps(fixture_baseline), encoding="utf-8")
            fixture = LocalCertificationAttestationTests()
            fixture.source_sha, fixture.repository = "2" * 40, directory
            with (
                patch.object(performance, "MANIFEST_PATH", manifest_path),
                patch.object(performance, "BASELINE_PATH", baseline_path),
            ):
                synthetic, _ = fixture._performance_result("full")
            checks = [
                check
                for check in synthetic["checks"]
                if check["id"].startswith("measurement:latency:cli-startup/")
            ]
            self.assertEqual(len(checks), 2)
            for check in checks:
                details = check["details"]
                self.assertEqual(details["relative_signal"]["observed"], 11000)
                self.assertEqual(
                    details["relative_signal"]["kind"],
                    performance.ROBUST_CLI_LAUNCH_RELATIVE_ESTIMATOR,
                )
                self.assertEqual(
                    _reconstruct_normalized_cli_median(cli, details), 11000
                )
        # Changing the reported new statistic cannot survive complete reconstruction.
        cli_rows[0]["relative_samples"][0] += 1
        baseline["baseline_fingerprint"] = performance.document_fingerprint(
            baseline, "baseline_fingerprint"
        )
        with self.assertRaises(performance.PerformanceResourceError) as caught:
            performance.validate_baseline(baseline, manifest=active, synthetic=True)
        self.assertEqual(caught.exception.code, "launch-control-signal")

    def test_failed_calibration_retains_raw_prefix_and_forbids_same_source_retry(self):
        prior_manifest = performance.load_json(performance.MANIFEST_PATH)
        prior_baseline = performance.load_json(performance.BASELINE_PATH)
        prior_evidence = performance.load_json(performance.VALID_EVIDENCE_PATH)
        with tempfile.TemporaryDirectory(
            dir=performance.ROOT / "target/codex-tools"
        ) as temporary:
            root = Path(temporary)
            governed = root / "tests/certification/performance-resource/1.0"
            governed.mkdir(parents=True)
            for name, value in (
                ("manifest.json", prior_manifest),
                ("baseline.json", prior_baseline),
                ("valid-evidence.json", prior_evidence),
            ):
                (governed / name).write_text(json.dumps(value), encoding="utf-8")
            originals = {path.name: path.read_bytes() for path in governed.iterdir()}

            def failed_calibration(*args, **kwargs):
                kwargs["observation_recorder"](
                    {
                        "event": "coordinate-observation",
                        "observation": {
                            "samples": [17] * 64,
                            "control_samples": [13] * 64,
                        },
                    }
                )
                raise performance.PerformanceResourceError(
                    "unstable-baseline", "retained controlled failure"
                )

            with ExitStack() as stack:
                for name, returned in (
                    ("_git_identity", ("2" * 40, False)),
                    ("validate_manifest", None),
                    ("validate_baseline", None),
                    ("validate_evidence", None),
                    ("_enforce_governed_cpu_affinity", None),
                    ("_build_release_artifacts", ("passed", {"artifacts": {}})),
                    ("_artifact_source_changes", {}),
                    ("_artifact_identity_check", (True, {})),
                    ("live_environment", prior_baseline["environment"]),
                    ("_release_artifacts", {}),
                ):
                    stack.enter_context(
                        patch.object(performance, name, return_value=returned)
                    )
                real_load = performance.load_json
                stack.enter_context(
                    patch.object(
                        performance,
                        "load_json",
                        side_effect=lambda path: (
                            {}
                            if path.name == "fixture-manifest.json"
                            else real_load(path)
                        ),
                    )
                )
                calibration = stack.enter_context(
                    patch.object(
                        performance,
                        "calibrate_baseline",
                        side_effect=failed_calibration,
                    )
                )
                for expected_code in (
                    "unstable-baseline",
                    "launch-normalization-source-consumed",
                ):
                    with self.assertRaises(
                        performance.PerformanceResourceError
                    ) as caught:
                        performance._migrate_cli_normalization_command(
                            confirm_launch_normalization=True,
                            rationale="Reviewed normalization and unchanged governed caps",
                            root=root,
                        )
                    self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(calibration.call_count, 1)
            retained = root / "target/performance-calibration" / ("2" * 40)
            terminal = json.loads((retained / "terminal.json").read_text())
            self.assertEqual(terminal["code"], "unstable-baseline")
            self.assertIs(terminal["authoritative"], False)
            self.assertIs(terminal["certification_eligible"], False)
            events = [
                json.loads(line)
                for line in (retained / "observations.jsonl").read_text().splitlines()
            ]
            self.assertEqual(events[-1]["observation"]["control_samples"], [13] * 64)
            self.assertFalse((governed / "history").exists())
            self.assertEqual(
                originals, {path.name: path.read_bytes() for path in governed.iterdir()}
            )
            with self.assertRaises(performance.PerformanceResourceError):
                performance._write_calibration_diagnostic(
                    retained / "terminal.json", {}, root=root
                )
            with self.assertRaises(performance.PerformanceResourceError):
                performance._write_calibration_diagnostic(
                    root / "outside.json", {}, root=root
                )

    def test_verifier_reconstructs_independently_and_rejects_forged_allocation(self):
        definition = {"launch_schedule": performance.ROBUST_CLI_LAUNCH_SCHEDULE}
        details = {
            "samples": [1, 1, 9, 9] * 16,
            "control_samples": [1, 9, 1, 9] * 16,
            "cli_launch_schedule": performance.ROBUST_CLI_LAUNCH_SCHEDULE,
            "request_first": [False] * 32 + [True] * 32,
        }
        with patch.object(
            performance,
            "normalized_launch_median",
            side_effect=AssertionError("producer arithmetic imported"),
        ):
            self.assertEqual(
                _reconstruct_normalized_cli_median(definition, details), 10000
            )
        for field, replacement in (
            ("request_first", [True] * 64),
            ("request_first", [0] * 32 + [1] * 32),
            ("cli_launch_schedule", "old"),
            ("control_samples", [0] * 64),
            ("samples", [1] * 63),
        ):
            changed = {**details, field: replacement}
            with self.subTest(field=field):
                with self.assertRaises(AttestationError):
                    _reconstruct_normalized_cli_median(definition, changed)

    def test_migration_caps_all_prior_effective_ceilings_and_forbids_policy_drift(self):
        prior_manifest = performance.load_json(performance.MANIFEST_PATH)
        prior_baseline = performance.load_json(performance.BASELINE_PATH)
        candidate_manifest, candidate_baseline = (
            copy.deepcopy(prior_manifest),
            copy.deepcopy(prior_baseline),
        )
        cli = next(
            row
            for row in candidate_manifest["operations"]
            if row["id"] == "latency:cli-startup"
        )
        cli["relative_estimator"] = performance.ROBUST_CLI_LAUNCH_RELATIVE_ESTIMATOR
        cli["launch_schedule"] = performance.ROBUST_CLI_LAUNCH_SCHEDULE
        cli["description"] = performance.ROBUST_CLI_LAUNCH_DESCRIPTION
        candidate_manifest["measurement_policy"][
            "native_cpu_accounting_batch_target_nanoseconds"
        ] = 31_250_000
        # Synthetic fresh calibration medians remain at their prior locations.
        # This tests the cap algebra, not a calibration or a reassignment of old samples.
        comparisons = performance._preserve_warmup_migration_thresholds(
            prior_manifest,
            prior_baseline,
            candidate_manifest,
            candidate_baseline,
            launch_normalization_migration=True,
        )
        self.assertEqual(len(comparisons), 54)
        for prior, candidate in zip(
            prior_baseline["measurements"], candidate_baseline["measurements"]
        ):
            stat = prior.get("relative_statistics", prior["statistics"])
            effective = min(
                prior["budget"]["absolute_ceiling"],
                stat["median"]
                * (10000 + prior["budget"]["relative_regression_basis_points"])
                // 10000,
            )
            self.assertLessEqual(candidate["budget"]["absolute_ceiling"], effective)
            self.assertLessEqual(
                candidate["budget"]["relative_regression_basis_points"],
                prior["budget"]["relative_regression_basis_points"],
            )
        for field, value in (
            ("relative_budget_formula", "ungoverned formula"),
            ("sample_iterations", 63),
            ("warmup_iterations", 128),
            ("baseline_repetitions", 5),
            ("maximum_relative_mad_basis_points", 600),
            ("selected_logical_cpu", 20),
            ("native_cpu_accounting_batch_target_nanoseconds", 2_000_000),
            ("native_cpu_accounting_batch_target_nanoseconds", 31_250_001),
        ):
            changed = copy.deepcopy(candidate_manifest)
            changed["measurement_policy"][field] = value
            with self.subTest(field=field):
                with self.assertRaises(performance.PerformanceResourceError):
                    performance._preserve_warmup_migration_thresholds(
                        prior_manifest,
                        prior_baseline,
                        changed,
                        copy.deepcopy(candidate_baseline),
                        launch_normalization_migration=True,
                    )
        regressed = copy.deepcopy(candidate_baseline)
        regressed["measurements"][0]["statistics"]["median"] = (
            prior_baseline["measurements"][0]["budget"]["absolute_ceiling"] + 1
        )
        with self.assertRaises(performance.PerformanceResourceError) as caught:
            performance._preserve_warmup_migration_thresholds(
                prior_manifest,
                prior_baseline,
                copy.deepcopy(candidate_manifest),
                regressed,
                launch_normalization_migration=True,
            )
        self.assertEqual(caught.exception.code, "warmup-regression")

    def test_identical_distributions_and_every_repairing_normalize_exactly(self):
        requests = [1, 1, 9, 9] * 16
        controls = [1, 9, 1, 9] * 16
        self.assertEqual(controlled_launch_estimate(requests, controls), 16668)
        self.assertEqual(controlled_launch_estimate(controls, requests), 16668)
        for shift in range(64):
            self.assertEqual(
                normalized_launch_median(requests, controls[shift:] + controls[:shift]),
                10000,
            )

    def test_sparse_launch_cleanup_is_not_attributed_as_typical_product_work(self):
        for count in range(32):
            pulses = [9] * count + [1] * (64 - count)
            with self.subTest(count=count):
                self.assertEqual(normalized_launch_median(pulses, [1] * 64), 10000)
                self.assertEqual(normalized_launch_median([1] * 64, pulses), 10000)
                self.assertEqual(
                    normalized_launch_median([11 * x for x in pulses], [10] * 64), 11000
                )
                self.assertEqual(
                    normalized_launch_median([3] * 64, [2 * x for x in pulses]), 15000
                )
        self.assertEqual(normalized_launch_median([9] * 32 + [1] * 32, [1] * 64), 50000)

    def test_scaling_reciprocity_and_exact_half_nanosecond_medians(self):
        requests, controls = [13, 7, 91, 63] * 16, [3, 19, 71, 29] * 16
        estimate = normalized_launch_median(requests, controls)
        reverse = normalized_launch_median(controls, requests)
        self.assertGreaterEqual(estimate * reverse, 100000000)
        self.assertLess((estimate - 1) * (reverse - 1), 100000000)
        for scale in (2, 3, 11, 10**18 + 3):
            self.assertEqual(
                normalized_launch_median(
                    [x * scale for x in requests], [x * scale for x in controls]
                ),
                estimate,
            )
        self.assertEqual(normalized_launch_median([1] * 32 + [2] * 32, [1] * 64), 15000)

    def test_all_observations_are_monotone_and_real_slowdowns_are_retained(self):
        requests, controls = [200, 50, 220, 55] * 16, [100] * 64
        initial = normalized_launch_median(requests, controls)
        for index in range(64):
            changed = requests.copy()
            changed[index] *= 100
            self.assertGreaterEqual(
                normalized_launch_median(changed, controls), initial
            )
        for numerator, denominator in ((11, 10), (3, 2)):
            estimate = normalized_launch_median(
                [x * numerator for x in requests], [x * denominator for x in controls]
            )
            self.assertGreaterEqual(
                estimate, ((initial - 1) * numerator // denominator) + 1
            )
            self.assertLessEqual(
                estimate, (initial * numerator + denominator - 1) // denominator
            )
            self.assertGreater(estimate, initial)

    def test_incomplete_or_nonphysical_observations_are_rejected(self):
        for requests, controls, code in (
            ([], [], "launch-control-pairs"),
            ([1] * 63, [1] * 64, "launch-control-pairs"),
            ([1] * 63, [1] * 63, "launch-control-count"),
            ([0] * 64, [1] * 64, "launch-control-statistic"),
            ([True] * 64, [1] * 64, "launch-control-statistic"),
            ([1.5] * 64, [1] * 64, "launch-control-statistic"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(PerformanceResourceError) as caught:
                    normalized_launch_median(requests, controls)
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
