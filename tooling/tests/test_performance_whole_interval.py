"""Whole-run conditioning diagnostics must not confuse sample medians with isolation."""

from __future__ import annotations

import copy
import unittest

from tooling import performance_windows_active as active


def fixture() -> tuple[dict, dict]:
    workload = {
        "source_sha": "6bd5a4e660452b9ec78f1d4cb30532d5dcab25dd",
        "runner_sha256": "b91c64cbe7d801668cab7b29fec50c728589c3ad79796c9a68829ad9711576e6",
        "operation_id": "latency:semantic-analysis",
        "fixture_id": "fixture:semantic-common",
        "batch_iterations": 76,
        "warmup_iterations": 512,
        "sample_iterations": 64,
        "maximum_sample_attempts": 128,
        "selected_logical_cpu": 1,
    }
    proof = {
        "role": "unqualified-whole-product-interval",
        "workload": copy.deepcopy(workload),
        "action_begin_ns": 0,
        "action_end_ns": 1_289_167_700,
        "exit_code": 0,
        "child_before": {
            "pid": 123,
            "birth": "134371742145275850",
            "kernel": 0,
            "user": 0,
            "query_begin_ns": 10,
            "query_end_ns": 20,
        },
        "child_after": {
            "pid": 123,
            "birth": "134371742145275850",
            "kernel": 625_000,
            "user": 10_781_250,
            "query_begin_ns": 1_289_167_670,
            "query_end_ns": 1_289_167_680,
        },
        "accepted_batch_elapsed_samples": [25_307 * 76] * 64,
        "rejected_batch_elapsed_samples": [],
    }
    return workload, proof


class WholeProductIntervalTests(unittest.TestCase):
    def result(self, proof=None, workload=None):
        default_workload, default_proof = fixture()
        return active.whole_product_interval_diagnostic(
            default_proof if proof is None else proof,
            default_workload if workload is None else workload,
        )

    def test_whole_span_preserved_without_subtracting_cpu(self):
        result = self.result()
        self.assertEqual(result["whole_action_elapsed_ns"], 1_289_167_700)
        self.assertEqual(result["accepted_sample_median_ns"], 25_307)
        self.assertEqual(result["all_attempt_batch_elapsed_ns"], 25_307 * 76 * 64)
        self.assertEqual(result["child_cpu_delta_100ns"], 11_406_250)

    def test_median_blindness_does_not_erase_full_interval(self):
        _, proof = fixture()
        proof["action_end_ns"] = 2_876_166_500
        proof["child_after"]["query_begin_ns"] = 2_876_166_470
        proof["child_after"]["query_end_ns"] = 2_876_166_480
        original, loaded = self.result(), self.result(proof)
        self.assertEqual(
            original["accepted_sample_median_ns"], loaded["accepted_sample_median_ns"]
        )
        self.assertGreater(
            loaded["whole_action_elapsed_ns"], 2 * original["whole_action_elapsed_ns"]
        )

    def test_rejected_attempt_is_included(self):
        _, proof = fixture()
        proof["rejected_batch_elapsed_samples"] = [60_000_000]
        result = self.result(proof)
        self.assertEqual(result["attempts"], 65)
        self.assertEqual(
            result["all_attempt_batch_elapsed_ns"], 25_307 * 76 * 64 + 60_000_000
        )

    def test_no_mutation(self):
        workload, proof = fixture()
        before = copy.deepcopy((workload, proof))
        self.result(proof, workload)
        self.assertEqual((workload, proof), before)

    def test_diagnostic_cannot_assert_authority(self):
        result = self.result()
        for key in (
            "baseline_admission",
            "certification_eligible",
            "performance_qualification",
        ):
            self.assertIs(result[key], False)
        self.assertNotIn("passed", result.values())

    def test_reject_partial_shape_and_injected_authority(self):
        for key in (
            "child_before",
            "accepted_batch_elapsed_samples",
            "action_begin_ns",
        ):
            _, proof = fixture()
            del proof[key]
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)
        _, proof = fixture()
        proof["baseline_admission"] = True
        with self.assertRaises(active.WindowsQualificationError):
            self.result(proof)

    def test_expected_workload_is_independent(self):
        for key, value in (
            ("source_sha", "a" * 40),
            ("runner_sha256", "b" * 64),
            ("operation_id", "latency:other"),
            ("batch_iterations", 75),
        ):
            _, proof = fixture()
            proof["workload"][key] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)

    def test_exact_workload_denominators(self):
        for key, value in (
            ("warmup_iterations", 1),
            ("sample_iterations", 63),
            ("maximum_sample_attempts", 129),
            ("batch_iterations", True),
            ("selected_logical_cpu", True),
        ):
            workload, proof = fixture()
            workload[key] = proof["workload"][key] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof, workload)

    def test_complete_sample_denominator(self):
        _, proof = fixture()
        proof["accepted_batch_elapsed_samples"].pop()
        with self.assertRaises(active.WindowsQualificationError):
            self.result(proof)

    def test_attempt_bound(self):
        _, proof = fixture()
        proof["rejected_batch_elapsed_samples"] = [1] * 65
        with self.assertRaises(active.WindowsQualificationError):
            self.result(proof)

    def test_monotonic_nonoverlapping_process_enclosure(self):
        for key, value in (("query_begin_ns", 10), ("query_end_ns", 2_000_000_000)):
            _, proof = fixture()
            proof["child_after"][key] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)

    def test_same_child_identity(self):
        for key, value in (("pid", 124), ("birth", "134371742145275851")):
            _, proof = fixture()
            proof["child_after"][key] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)

    def test_no_counter_regression(self):
        _, proof = fixture()
        proof["child_before"]["user"] = proof["child_after"]["user"] + 1
        with self.assertRaises(active.WindowsQualificationError):
            self.result(proof)

    def test_batch_sum_must_fit_whole_span(self):
        _, proof = fixture()
        proof["accepted_batch_elapsed_samples"] = [1_000_000_000] * 64
        with self.assertRaises(active.WindowsQualificationError):
            self.result(proof)

    def test_no_boolean_or_zero_durations(self):
        for value in (True, 0, -1, 1.0):
            _, proof = fixture()
            proof["accepted_batch_elapsed_samples"][0] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)

    def test_failed_process_not_complete(self):
        for value in (1, True):
            _, proof = fixture()
            proof["exit_code"] = value
            with self.assertRaises(active.WindowsQualificationError):
                self.result(proof)


if __name__ == "__main__":
    unittest.main()
