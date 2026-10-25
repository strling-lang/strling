"""Synthetic observation attacks, not empirical certification samples."""

import copy
import json
import unittest

from tooling import workstation_evidence as evidence
from tooling import workstation_performance as score
from tooling import performance_envelope_receipts as process
from tooling.tests import test_performance_envelope_receipts as fixtures

encoded = fixtures.encoded


class WorkstationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.bundle = fixtures.ReceiptTests()
        self.bundle.setUp()
        for key in (
            "action_begin_ns",
            "release_begin_ns",
            "root_exit_observed_ns",
            "action_end_ns",
            "finished_ns",
            "whole_action_ns",
        ):
            self.bundle.row[key] *= 10000000
        for key in ("query_begin_ns", "query_end_ns"):
            self.bundle.row["accounting"][key] *= 10000000
        wakeups = json.loads(self.bundle.files["lifecycle-wakeups.json"])
        for row in wakeups:
            row["observed_ns"] *= 10000000
        self.bundle.files["lifecycle-wakeups.json"] = encoded(wakeups)
        self.policy = score.load_policy()
        self.raw = dict(
            operation_id="latency:semantic-parse",
            fixture_id="fixture:semantic-tiny",
            certification_context="shared-workstation-v1",
            sample_retention="all-fixed-slots-v1",
            cpu_quota="observed-immediate-job:flags=0:rate=0:ancestors=unknown",
            selected_logical_cpu=1,
            effective_cpu_affinity=[1],
            platform="windows",
            processor_group=0,
            observed_processor_groups=[0],
            observed_logical_processors=[1],
            unit="nanoseconds",
            warmup_iterations=512,
            sample_iterations=64,
            batch_iterations=16,
            maximum_descheduling_nanoseconds=50000000,
            maximum_sample_attempts=64,
            sample_attempts=64,
            measurement_role="ordinary",
            checksum=42,
            samples=[1000] * 64,
            batch_elapsed_samples=[16000] * 64,
            process_cpu_samples=[500] * 64,
            process_cpu_batch_elapsed_samples=[8000] * 64,
            process_cpu_utilization_basis_points=[5000] * 64,
            rejected_batch_elapsed_samples=[],
            rejected_process_cpu_batch_elapsed_samples=[],
            rejected_process_cpu_utilization_basis_points=[],
            control_samples=[],
            control_batch_elapsed_samples=[],
        )

    def verify(self):
        self.bundle.files["stdout.bin"] = encoded(self.raw)
        self.bundle.seal()
        return evidence.verify_observation(
            self.bundle.files,
            self.bundle.pin,
            self.bundle.plan,
            coordinate=(self.raw["operation_id"], self.raw["fixture_id"]),
            batch=self.raw["batch_iterations"],
            policy=self.policy,
            process_verifier=process.verify_process_receipt,
        )

    def test_high_descheduling_slot_remains_in_complete_fixed_vector(self):
        # A 100ms gap must remain one of the 64 slots, never a replacement.
        self.raw["batch_elapsed_samples"][0] = 100000000
        self.raw["samples"][0] = 6250000
        self.raw["process_cpu_utilization_basis_points"][0] = 0
        checked = self.verify()
        self.assertEqual(checked["samples"][0], 6250000)
        self.assertEqual(len(checked["samples"]), 64)

    def test_refreshed_inner_hashes_do_not_hide_semantic_or_count_attacks(self):
        original = copy.deepcopy(self.raw)
        self.verify()
        attacks = [
            ("sample_attempts", 65),
            ("maximum_sample_attempts", 128),
            ("sample_retention", "best-slots"),
            ("cpu_quota", "unlimited"),
            (
                "cpu_quota",
                "observed-immediate-job:flags=4294967296:rate=0:ancestors=unknown",
            ),
            ("selected_logical_cpu", True),
            ("processor_group", False),
            ("effective_cpu_affinity", [True]),
            ("samples", [1001] * 64),
            ("process_cpu_utilization_basis_points", [9999] * 64),
            ("measurement_role", "slowdown-control"),
            ("warmup_iterations", 16),
            ("rejected_batch_elapsed_samples", [100000000]),
        ]
        for key, value in attacks:
            with self.subTest(key=key, value=value):
                self.raw = copy.deepcopy(original)
                self.raw[key] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def memory(self):
        self.raw.update(
            operation_id="memory:kernel-peak-rss",
            warmup_iterations=1,
            sample_iterations=1,
            batch_iterations=1,
            maximum_sample_attempts=1,
            sample_attempts=1,
            memory_worker_contract="shared-workstation-memory-v1",
            peak_working_set_bytes=5000000,
        )
        for name in (
            "samples",
            "batch_elapsed_samples",
            "process_cpu_samples",
            "process_cpu_batch_elapsed_samples",
            "process_cpu_utilization_basis_points",
        ):
            self.raw[name] = []
        self.raw["memory_lifetime"] = dict(
            contract="retained-process-terminal-peak-v1",
            pid=18,
            birth_100ns=1200,
            exit_100ns=1800,
            worker_reported_peak_rss_bytes=4000000,
            terminal_peak_rss_bytes=5000000,
            residency_qualified=False,
            descendant_coverage_qualified=False,
            observer_effects_qualified=False,
        )
        self.raw["workstation_memory"] = dict(
            contract="process-lifetime-peak-commit-v1",
            peak_commit_bytes=2000000,
            worker_reported_peak_commit_bytes=1900000,
            single_process_job=True,
            observer_scope="parent-outside-measured-worker",
        )
        reply = dict(
            worker_contract="shared-workstation-memory-v1",
            certification_context="shared-workstation-v1",
            sample_retention="all-fixed-slots-v1",
            effective_cpu_affinity=[1],
            peak_working_set_bytes=4000000,
            peak_commit_bytes=1900000,
            sample_attempts=1,
            checksum=42,
        )
        self.bundle.files["stderr.bin"] = (
            encoded(
                dict(
                    contract="retained-memory-worker-streams-v1",
                    pid=18,
                    birth_100ns=1200,
                    input_bytes=list(b'{"synthetic":true}'),
                    stdout_bytes=list(encoded(reply)),
                    stderr_bytes=[],
                    success=True,
                )
            )
            + b"\n"
        )

    def test_single_memory_compilation_reconstructs_exact_child_and_terminal_peak(self):
        self.memory()
        checked = self.verify()
        self.assertEqual(checked["peak_commit_bytes"], 2000000)
        self.assertEqual(checked["memory_identity"], (18, 1200))

    def test_memory_private_job_lifetime_and_child_stream_attacks(self):
        for section, key, value in [
            ("workstation_memory", "single_process_job", False),
            ("workstation_memory", "peak_commit_bytes", 0),
            ("memory_lifetime", "pid", 19),
            ("memory_lifetime", "exit_100ns", 3000),
            ("memory_lifetime", "residency_qualified", True),
        ]:
            with self.subTest(key=key):
                self.setUp()
                self.memory()
                self.verify()
                self.raw[section][key] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError):
                evidence.parse(value)


if __name__ == "__main__":
    unittest.main()
