"""Synthetic reference binding is not empirical conditioning qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest

from tooling import performance_windows_active as active
from tooling.tests.test_performance_whole_interval import fixture


def reference_fixture():
    workload, proof = fixture()
    recipe = {
        k: v for k, v in workload.items() if k not in {"source_sha", "runner_sha256"}
    }
    expected = {
        "method_sha256": "1" * 64,
        "environment_sha256": "2" * 64,
        "recipe": recipe,
        "cohorts": [],
    }
    envelope = {
        "role": "unqualified-whole-product-reference",
        "method_sha256": expected["method_sha256"],
        "environment_sha256": expected["environment_sha256"],
        "recipe": copy.deepcopy(recipe),
        "cohorts": [],
    }
    for index, role in enumerate(("reference-only", "source-distinct-holdout")):
        pins = {
            "role": role,
            "source_sha": str(index + 3) * 40,
            "runner_sha256": str(index + 5) * 64,
            "acquisition_sha256": str(index + 7) * 64,
        }
        expected["cohorts"].append(copy.deepcopy(pins))
        cohort = {**pins, "observations": []}
        for repetition in range(9):
            raw = copy.deepcopy(proof)
            raw["workload"].update(
                source_sha=pins["source_sha"], runner_sha256=pins["runner_sha256"]
            )
            for frame in ("child_before", "child_after"):
                raw[frame]["birth"] = str(134371742145275850 + index * 9 + repetition)
            cohort["observations"].append(
                {
                    "repetition": repetition,
                    "receipt_sha256": hashlib.sha256(
                        f"{index}/{repetition}".encode()
                    ).hexdigest(),
                    "proof": raw,
                    "coverage": [{"begin_ns": 0, "end_ns": raw["action_end_ns"]}],
                }
            )
        envelope["cohorts"].append(cohort)
    return expected, envelope


class ReferenceBindingTests(unittest.TestCase):
    def run_diagnostic(self, envelope=None, expected=None, candidate="a" * 40):
        defaults = reference_fixture()
        expected = defaults[0] if expected is None else expected
        envelope = defaults[1] if envelope is None else envelope
        data = json.dumps(envelope).encode()
        return active.bound_whole_product_reference_diagnostic(
            data, hashlib.sha256(data).hexdigest(), expected, candidate
        )

    def test_keeps_all_reference_and_holdout_repetitions(self):
        result = self.run_diagnostic()
        self.assertEqual(len(result["observations"]), 18)
        self.assertEqual(result["attempts"], 18 * 64)
        self.assertIs(result["performance_qualification"], False)
        self.assertIs(result["baseline_admission"], False)
        self.assertIs(result["certification_eligible"], False)
        self.assertEqual(result["status"], "diagnostic-bound")

    def test_reference_bytes_must_match_independent_digest(self):
        expected, envelope = reference_fixture()
        with self.assertRaises(active.WindowsQualificationError):
            active.bound_whole_product_reference_diagnostic(
                json.dumps(envelope).encode(), "0" * 64, expected, "a" * 40
            )

    def test_self_baseline_and_same_source_holdout_rejected(self):
        expected, envelope = reference_fixture()
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(candidate=expected["cohorts"][0]["source_sha"])
        expected["cohorts"][1]["source_sha"] = expected["cohorts"][0]["source_sha"]
        envelope["cohorts"][1]["source_sha"] = expected["cohorts"][0]["source_sha"]
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope, expected)

    def test_cannot_repin_from_envelope(self):
        for field in ("method_sha256", "environment_sha256"):
            _, envelope = reference_fixture()
            envelope[field] = "f" * 64
            with (
                self.subTest(field=field),
                self.assertRaises(active.WindowsQualificationError),
            ):
                self.run_diagnostic(envelope)
        for field in ("source_sha", "runner_sha256", "acquisition_sha256"):
            _, envelope = reference_fixture()
            envelope["cohorts"][0][field] = "f" * len(envelope["cohorts"][0][field])
            with (
                self.subTest(field=field),
                self.assertRaises(active.WindowsQualificationError),
            ):
                self.run_diagnostic(envelope)

    def test_missing_extra_reordered_or_duplicate_repetitions(self):
        for mutation in ("missing", "extra", "reorder", "duplicate"):
            _, envelope = reference_fixture()
            rows = envelope["cohorts"][0]["observations"]
            if mutation == "missing":
                rows.pop()
            elif mutation == "extra":
                rows.append(copy.deepcopy(rows[-1]))
            elif mutation == "reorder":
                rows.reverse()
            else:
                rows[1]["receipt_sha256"] = rows[0]["receipt_sha256"]
            with (
                self.subTest(mutation=mutation),
                self.assertRaises(active.WindowsQualificationError),
            ):
                self.run_diagnostic(envelope)

    def test_acquisition_reuse_rejected_even_with_changed_source(self):
        expected, envelope = reference_fixture()
        for item in (expected, envelope):
            item["cohorts"][1]["acquisition_sha256"] = item["cohorts"][0][
                "acquisition_sha256"
            ]
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope, expected)

    def test_repackaged_process_is_not_a_fresh_repetition(self):
        _, envelope = reference_fixture()
        rows = envelope["cohorts"][0]["observations"]
        rows[1]["proof"] = copy.deepcopy(rows[0]["proof"])
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope)

    def test_between_probe_gap_rejected(self):
        _, envelope = reference_fixture()
        row = envelope["cohorts"][0]["observations"][0]
        row["coverage"] = [
            {"begin_ns": 0, "end_ns": 10},
            {"begin_ns": 11, "end_ns": row["proof"]["action_end_ns"]},
        ]
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope)

    def test_launch_and_exit_must_be_covered(self):
        for field in ("begin_ns", "end_ns"):
            _, envelope = reference_fixture()
            row = envelope["cohorts"][0]["observations"][0]
            row["coverage"][0][field] += 1 if field == "begin_ns" else -1
            with self.assertRaises(active.WindowsQualificationError):
                self.run_diagnostic(envelope)

    def test_contiguous_and_overlapping_windows_cover(self):
        for start in (9, 10):
            _, envelope = reference_fixture()
            row = envelope["cohorts"][0]["observations"][0]
            row["coverage"] = [
                {"begin_ns": 0, "end_ns": 10},
                {"begin_ns": start, "end_ns": row["proof"]["action_end_ns"]},
            ]
            self.assertEqual(
                self.run_diagnostic(envelope)["status"], "diagnostic-bound"
            )

    def test_unfavorable_intervals_and_rejections_not_filtered(self):
        _, envelope = reference_fixture()
        row = envelope["cohorts"][0]["observations"][0]
        row["proof"]["action_end_ns"] *= 4
        row["coverage"][0]["end_ns"] *= 4
        row["proof"]["rejected_batch_elapsed_samples"] = [1_000_000]
        result = self.run_diagnostic(envelope)
        self.assertEqual(result["attempts"], 18 * 64 + 1)
        self.assertEqual(
            result["observations"][0]["whole_action_elapsed_ns"],
            row["proof"]["action_end_ns"],
        )

    def test_all_workload_proofs_validated(self):
        _, envelope = reference_fixture()
        envelope["cohorts"][-1]["observations"][-1]["proof"]["exit_code"] = 1
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope)

    def test_injected_authority_or_threshold_rejected(self):
        for field in ("qualified", "maximum_elapsed_ns", "baseline_admission"):
            _, envelope = reference_fixture()
            envelope[field] = True
            with self.assertRaises(active.WindowsQualificationError):
                self.run_diagnostic(envelope)

    def test_duplicate_json_key_rejected(self):
        expected, envelope = reference_fixture()
        data = json.dumps(envelope).encode()
        data = b'{"role":"forged",' + data[1:]
        with self.assertRaises(active.WindowsQualificationError):
            active.bound_whole_product_reference_diagnostic(
                data, hashlib.sha256(data).hexdigest(), expected, "a" * 40
            )

    def test_exact_integer_order_and_coverage(self):
        for field in ("repetition", "begin_ns", "end_ns"):
            _, envelope = reference_fixture()
            row = envelope["cohorts"][0]["observations"][0]
            target = row if field == "repetition" else row["coverage"][0]
            target[field] = True
            with self.assertRaises(active.WindowsQualificationError):
                self.run_diagnostic(envelope)

    def test_boolean_recipe_cannot_alias_integer_pin(self):
        _, envelope = reference_fixture()
        envelope["recipe"]["selected_logical_cpu"] = True
        with self.assertRaises(active.WindowsQualificationError):
            self.run_diagnostic(envelope)

    def test_inputs_unchanged(self):
        expected, envelope = reference_fixture()
        before = copy.deepcopy((expected, envelope))
        self.run_diagnostic(envelope, expected)
        self.assertEqual(before, (expected, envelope))


if __name__ == "__main__":
    unittest.main()
