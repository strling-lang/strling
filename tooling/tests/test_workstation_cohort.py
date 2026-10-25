"""Synthetic complete-cohort attacks; these are not native measurements."""

import base64
import copy
import hashlib
import unittest

from tooling import performance_envelope_receipts as process
from tooling import workstation_evidence as reader
from tooling import workstation_performance as score
from tooling.tests import test_workstation_evidence as fixtures


class WorkstationCohortTests(unittest.TestCase):
    def setUp(self):
        self.policy = score.load_policy()
        self.coordinate = ("latency:semantic-parse", "fixture:semantic-tiny")
        self.builds = {}
        for lane in ("reference", "candidate", "slowdown"):
            self.builds[lane] = dict(
                build_root="C:/" + lane,
                kernel_revision=self.policy["reference_source"]
                if lane == "reference"
                else "a" * 40,
                negative_control=lane == "slowdown",
                artifacts={
                    kind: dict(path=f"C:/{lane}/{kind}.exe", sha256="b" * 64, bytes=100)
                    for kind in ("runner", "memory_worker", "kernel", "interop")
                },
            )
        self.document = dict(
            contract="shared-workstation-cohort-v2",
            source_sha="a" * 40,
            policy_sha256="c" * 64,
            manifest_sha256="d" * 64,
            builds=copy.deepcopy(self.builds),
            observations=[],
        )
        self.pins = {}
        for purpose, other in (("ordinary", "candidate"), ("negative", "slowdown")):
            self.add(
                "reference",
                "calibration" if purpose == "ordinary" else "negative-calibration",
                None,
            )
            for repetition, reference_first in enumerate(
                self.policy["reference_first"]
            ):
                for lane in (
                    ("reference", other) if reference_first else (other, "reference")
                ):
                    self.add(lane, purpose, repetition)

    def add(self, lane, purpose, repetition):
        fixture = fixtures.WorkstationEvidenceTests()
        fixture.setUp()
        index = len(self.document["observations"])
        if lane == "slowdown":
            fixture.raw["measurement_role"] = "slowdown-control"
            fixture.raw["samples"] = [2000] * 64
            fixture.raw["batch_elapsed_samples"] = [32000] * 64
            fixture.raw["process_cpu_utilization_basis_points"] = [2500] * 64
        fixture.bundle.plan["command"] = reader.worker_command(
            self.builds[lane]["artifacts"],
            self.coordinate,
            16,
            self.policy,
            calibration="calibration" in purpose,
        )
        fixture.bundle.plan["inputs"] = {
            v["path"]: v["sha256"] for v in self.builds[lane]["artifacts"].values()
        }
        fixture.bundle.files["plan.json"] = fixtures.encoded(fixture.bundle.plan)
        fixture.bundle.row["plan_sha256"] = hashlib.sha256(
            fixture.bundle.files["plan.json"]
        ).hexdigest()
        for name in ("suspended.json", "root-exit.json"):
            row = reader.parse(fixture.bundle.files[name])
            row["pid"] += index
            fixture.bundle.files[name] = fixtures.encoded(row)
        wakeups = reader.parse(fixture.bundle.files["lifecycle-wakeups.json"])
        wakeups[0]["pid"] += index
        for row in wakeups:
            row["observed_ns"] += index * 2000000000
        fixture.bundle.files["lifecycle-wakeups.json"] = fixtures.encoded(wakeups)
        for key in (
            "action_begin_ns",
            "release_begin_ns",
            "root_exit_observed_ns",
            "action_end_ns",
            "finished_ns",
        ):
            fixture.bundle.row[key] += index * 2000000000
        for key in ("query_begin_ns", "query_end_ns"):
            fixture.bundle.row["accounting"][key] += index * 2000000000
        fixture.bundle.files["stdout.bin"] = fixtures.encoded(fixture.raw)
        fixture.bundle.seal()
        self.document["observations"].append(
            dict(
                slot=f"slot-{index}",
                coordinate=list(self.coordinate),
                lane=lane,
                purpose=purpose,
                repetition=repetition,
                expected_plan=fixture.bundle.plan,
                terminal_sha256=fixture.bundle.pin,
                files={
                    k: base64.b64encode(v).decode()
                    for k, v in fixture.bundle.files.items()
                },
            )
        )

    def verify(self):
        return reader.verify_cohort(
            self.document,
            coordinates=[self.coordinate],
            policy=self.policy,
            source_sha="a" * 40,
            policy_sha256="c" * 64,
            manifest_sha256="d" * 64,
            build_identities=self.builds,
            implementation_pins=self.pins,
            process_verifier=process.verify_process_receipt,
            latency_scorer=score.guarded_latency_decision,
            memory_scorer=score.memory_decision,
        )

    def test_complete_positive_and_negative_denominator_reconstructs(self):
        result = self.verify()
        self.assertEqual(result["observations"], 38)
        self.assertEqual(result["unique_processes"], 38)
        self.assertTrue(result["decisions"][0]["passed"])
        self.assertFalse(result["negative_control"]["passed"])

    def test_missing_extra_reordered_and_wrong_role_records_fail(self):
        self.verify()
        original = copy.deepcopy(self.document)
        for mutate in (
            lambda d: d["observations"].pop(),
            lambda d: d["observations"].append(copy.deepcopy(d["observations"][-1])),
            lambda d: d["observations"].reverse(),
            lambda d: d["observations"][1].__setitem__("lane", "slowdown"),
            lambda d: d["observations"][1].__setitem__("repetition", 1),
            lambda d: d["observations"][1]["expected_plan"]["command"].__setitem__(
                0, "C:/other.exe"
            ),
            lambda d: d["observations"][1].__setitem__(
                "slot", d["observations"][0]["slot"]
            ),
        ):
            self.document = copy.deepcopy(original)
            mutate(self.document)
            with self.assertRaises(ValueError):
                self.verify()

    def test_build_identity_and_kernel_source_roles_are_independent_inputs(self):
        self.document["builds"]["candidate"]["kernel_revision"] = "9" * 40
        with self.assertRaisesRegex(ValueError, "pinned builds"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
