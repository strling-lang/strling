"""Synthetic arithmetic/discrimination proofs, never empirical qualification."""

import copy
import hashlib
import json
import unittest

from tooling import performance_reference_bounds as bounds
from tooling import performance_resource_certification as controller


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    coordinates = [["latency:cli-startup", "fixture:semantic-tiny"]]
    plan = dict(
        method="prospective-whole-process-bounds-v1",
        manifest_sha256="1" * 64,
        environment_sha256="2" * 64,
        recipe_sha256="3" * 64,
        coordinates=coordinates,
        warmup_iterations=512,
        sample_iterations=64,
        repetitions=9,
    )
    cohorts = []
    for index, role in enumerate(("reference-only", "source-distinct-holdout")):
        pins = dict(
            source_sha=str(4 + index) * 40,
            runner_sha256=str(6 + index) * 64,
            acquisition_sha256=str(8 + index) * 64,
        )
        rows = []
        for coordinate in coordinates:
            for repetition in range(9):
                rows.append(
                    dict(
                        coordinate=coordinate,
                        repetition=repetition,
                        begin_ns=1_000_000,
                        end_ns=2_000_000,
                        pid=100,
                        birth_100ns=1000 + index * 9 + repetition,
                        receipt_sha256=digest(
                            f"{index}/{coordinate}/{repetition}".encode()
                        ),
                        cli_samples=dict(
                            request_ns=[1100] * 64, control_ns=[1000] * 64
                        ),
                    )
                )
        cohorts.append(dict(role=role, plan=plan, pins=pins, observations=rows))
    return coordinates, plan, cohorts


class ReferenceBoundsTests(unittest.TestCase):
    def setUp(self):
        self.coordinates, self.plan, self.cohorts = fixture()
        self.reference_pins = copy.deepcopy(self.cohorts[0]["pins"])
        self.holdout_pins = copy.deepcopy(self.cohorts[1]["pins"])

    def freeze(self):
        data = encoded(self.cohorts[0])
        return bounds.freeze_reference(
            data,
            digest(data),
            plan=self.plan,
            pins=self.reference_pins,
            coordinates=self.coordinates,
        )

    def check(self, frozen=None):
        frozen = self.freeze() if frozen is None else frozen
        reference = encoded(self.cohorts[0])
        holdout = encoded(self.cohorts[1])
        return bounds.check_holdout(
            frozen,
            digest(frozen),
            holdout,
            digest(holdout),
            reference_sha256=digest(reference),
            plan=self.plan,
            reference_pins=self.reference_pins,
            holdout_pins=self.holdout_pins,
            coordinates=self.coordinates,
        )

    def test_deterministic_frozen_reference_and_complete_holdout(self):
        frozen = self.freeze()
        self.assertEqual(frozen, self.freeze())
        result = self.check(frozen)
        self.assertTrue(result["within_bounds"])
        self.assertEqual(len(result["comparisons"]), 9)
        self.assertEqual(result["comparisons"][0]["elapsed_ns"], 1_000_000)
        for key in ("certification_eligible", "baseline_admission", "quota_qualified"):
            self.assertIs(result[key], False)
        self.assertEqual(frozen, self.freeze())

    def test_exact_bound_without_rounding_allowance(self):
        for amount, expected in ((1_050_000, True), (1_050_001, False)):
            with self.subTest(amount=amount):
                self.cohorts[1]["observations"][-1]["end_ns"] = 1_000_000 + amount
                self.assertEqual(self.check()["within_bounds"], expected)

    def test_common_mode_slowdown_cannot_disappear_in_ratio(self):
        frozen = self.freeze()
        for percent in (110, 150):
            request, control = 22_000_000 * percent, 20_000_000 * percent
            self.assertEqual(request * 10_000 // control, 11_000)
            for row in self.cohorts[1]["observations"]:
                row["end_ns"] = row["begin_ns"] + 1_000_000 * percent // 100
            result = self.check(frozen)
            self.assertFalse(result["within_bounds"])
            self.assertEqual(
                sum(not r["within_bound"] for r in result["comparisons"]), 9
            )

    def test_single_unfavorable_holdout_is_retained_not_refitted(self):
        frozen = self.freeze()
        self.cohorts[1]["observations"][4]["end_ns"] = 9_000_000
        result = self.check(frozen)
        self.assertFalse(result["within_bounds"])
        self.assertEqual(result["comparisons"][4]["elapsed_ns"], 8_000_000)
        self.assertEqual(frozen, self.freeze())

    def test_sample_only_common_mode_is_not_diluted_by_warmups(self):
        frozen = self.freeze()
        for row in self.cohorts[1]["observations"]:
            row["end_ns"] += 20_000  # Only 2% whole-interval increase.
            row["cli_samples"] = dict(request_ns=[1210] * 64, control_ns=[1100] * 64)
        result = self.check(frozen)
        self.assertFalse(result["within_bounds"])
        self.assertTrue(
            all(r["whole_interval_within_bound"] for r in result["comparisons"])
        )
        self.assertTrue(
            all(
                not r["cli_comparisons"]["request_ns"]["within_bound"]
                for r in result["comparisons"]
            )
        )

    def test_cli_half_nanosecond_boundary_is_exact(self):
        for row in self.cohorts[0]["observations"]:
            row["cli_samples"]["request_ns"] = [10] * 32 + [11] * 32
        frozen = self.freeze()
        for value, expected in ((11, True), (12, False)):
            for row in self.cohorts[1]["observations"]:
                row["cli_samples"]["request_ns"] = [value] * 64
            self.assertEqual(self.check(frozen)["within_bounds"], expected)

    def test_cli_raw_denominator_is_closed(self):
        for value in (
            None,
            {},
            {"request_ns": [1] * 63, "control_ns": [1] * 64},
            {"request_ns": [True] * 64, "control_ns": [1] * 64},
        ):
            self.setUp()
            self.cohorts[1]["observations"][0]["cli_samples"] = value
            with self.subTest(value=str(value)[:40]), self.assertRaises(ValueError):
                self.check()

    def test_unfavorable_reference_cannot_inflate_bound(self):
        self.cohorts[0]["observations"][0]["end_ns"] = 9_000_000
        result = json.loads(self.freeze())
        self.assertFalse(result["reference_stable"])
        self.assertEqual(result["bounds"][0]["median_ns"], 1_000_000)
        self.assertEqual(result["bounds"][0]["elapsed_ns"][0], 8_000_000)
        with self.assertRaises(ValueError):
            self.check()

    def test_mad_and_all_reference_values_are_checked(self):
        for index, row in enumerate(self.cohorts[0]["observations"]):
            row["end_ns"] = row["begin_ns"] + (
                800_000 if index < 4 else 1_000_000 if index == 4 else 1_020_000
            )
        # MAD is 2%, but a faster outlier still invalidates stationarity.
        self.assertFalse(json.loads(self.freeze())["reference_stable"])
        for index, row in enumerate(self.cohorts[0]["observations"]):
            row["end_ns"] = row["begin_ns"] + 1_000_000 + (index - 4) * 60_000
        self.assertFalse(json.loads(self.freeze())["reference_stable"])

    def test_denominator_and_exact_types(self):
        mutations = (
            lambda c: c["observations"].pop(),
            lambda c: c["observations"].append(copy.deepcopy(c["observations"][-1])),
            lambda c: c["observations"].reverse(),
            lambda c: c["observations"][0].update(repetition=False),
            lambda c: c["observations"][0].update(begin_ns=True),
            lambda c: c["observations"][0].update(end_ns=1_000_000),
            lambda c: c["observations"][0].update(end_ns=2**63),
            lambda c: c["observations"][0].update(certification_eligible=True),
            lambda c: c["observations"][1].update(
                receipt_sha256=c["observations"][0]["receipt_sha256"]
            ),
            lambda c: c["observations"][1].update(
                birth_100ns=c["observations"][0]["birth_100ns"]
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.setUp()
                mutate(self.cohorts[0])
                with self.assertRaises(ValueError):
                    self.freeze()

    def test_plan_and_pins_cannot_be_self_supplied(self):
        for kind in ("source", "recipe", "coordinates", "size"):
            self.setUp()
            if kind == "source":
                self.cohorts[0]["pins"]["source_sha"] = "b" * 40
            elif kind == "recipe":
                self.plan["sample_iterations"] = 32
            elif kind == "coordinates":
                self.coordinates = self.coordinates + [
                    ["memory:kernel-peak-rss", "fixture:semantic-tiny"]
                ]
            else:
                self.coordinates[0][0] = "size:kernel-artifacts"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.freeze()

    def test_cross_cohort_reuse(self):
        for kind in ("source", "acquisition", "receipt", "process"):
            self.setUp()
            reference, holdout = self.cohorts
            if kind in ("source", "acquisition"):
                field = "source_sha" if kind == "source" else "acquisition_sha256"
                self.holdout_pins[field] = reference["pins"][field]
                holdout["pins"][field] = reference["pins"][field]
            else:
                field = "receipt_sha256" if kind == "receipt" else "birth_100ns"
                holdout["observations"][0][field] = reference["observations"][0][field]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.check()

    def test_changed_frozen_bound_rejected_even_with_new_outer_hash(self):
        frozen = json.loads(self.freeze())
        frozen["bounds"][0]["median_ns"] *= 2
        with self.assertRaises(ValueError):
            self.check(encoded(frozen))

    def test_bad_hash_duplicate_json_nonfinite_and_injected_authority(self):
        good = encoded(self.cohorts[0])
        for raw, pin in (
            (good, "0" * 64),
            (b'{"a":1,"a":2}', None),
            (b'{"a":NaN}', None),
            (b"[]", None),
        ):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                bounds.freeze_reference(
                    raw,
                    pin or digest(raw),
                    plan=self.plan,
                    pins=self.reference_pins,
                    coordinates=self.coordinates,
                )

    def test_large_integer_boundary(self):
        value = 10**16 + 1
        for row in self.cohorts[0]["observations"]:
            row["end_ns"] = row["begin_ns"] + value
        frozen = self.freeze()
        for row in self.cohorts[1]["observations"]:
            row["end_ns"] = row["begin_ns"] + value * 10500 // 10000 + 1
        self.assertFalse(self.check(frozen)["within_bounds"])

    def test_all_actual_process_coordinates_and_all_954_observations(self):
        manifest = controller.load_json(controller.MANIFEST_PATH)
        coordinates = [
            list(k)
            for k in controller.performance_measurement_keys(manifest)
            if k[0].startswith(("latency:", "memory:"))
        ]
        self.assertEqual(len(coordinates), 53)
        self.coordinates = coordinates
        self.plan["coordinates"] = coordinates
        for cohort_index, cohort in enumerate(self.cohorts):
            template = cohort["observations"][0]
            cohort["observations"] = []
            for index, coordinate in enumerate(coordinates):
                for repetition in range(9):
                    row = copy.deepcopy(template)
                    row.update(
                        coordinate=coordinate,
                        repetition=repetition,
                        birth_100ns=1000 + cohort_index * 1000 + index * 9 + repetition,
                        receipt_sha256=digest(
                            f"{cohort_index}/{index}/{repetition}".encode()
                        ),
                    )
                    if coordinate[0] != "latency:cli-startup":
                        row["cli_samples"] = None
                    cohort["observations"].append(row)
        frozen = self.freeze()
        self.assertEqual(len(json.loads(frozen)["bounds"]), 53)
        result = self.check(frozen)
        self.assertEqual(len(result["comparisons"]), 477)
        self.assertTrue(result["within_bounds"])
        self.assertEqual(
            sum(bool(r["cli_comparisons"]) for r in result["comparisons"]), 18
        )
        self.cohorts[1]["observations"][-1]["end_ns"] *= 2
        self.assertFalse(self.check(frozen)["within_bounds"])

    def test_cli_samples_cannot_exceed_complete_serial_interval(self):
        self.cohorts[0]["observations"][0]["cli_samples"]["request_ns"] = [10**10] * 64
        with self.assertRaises(ValueError):
            self.freeze()


if __name__ == "__main__":
    unittest.main()
