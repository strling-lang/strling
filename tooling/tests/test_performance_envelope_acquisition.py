"""Actual controller workload adapters, not reference qualification."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tooling import performance_resource_certification as controller
from tooling import performance_process_envelope as envelope
from tooling import performance_envelope_acquisition as acquisition


def result_for(command, environment):
    """Synthetic protocol response; production parsing is never mocked."""

    def option(name):
        return command[command.index(name) + 1]

    execution = environment["execution_resource"]
    result = dict(
        operation_id=option("--operation"),
        fixture_id=option("--fixture"),
        platform="windows",
        selected_logical_cpu=1,
        effective_cpu_affinity=[1],
        effective_cpuset=controller._execution_resource_cpuset(execution),
        placement_mechanism=execution["placement_mechanism"],
        processor_group=0,
        selected_cpu_set_id=257,
        cpu_set_allocation_state=execution["cpu_set_allocation_state"],
        cpu_quota="unlimited",
        timer_source="QueryPerformanceCounter:10000000",
        process_power_policy=execution["process_power_policy"],
        observed_processor_groups=[0],
        observed_logical_processors=[1],
    )
    if result["operation_id"].startswith("memory:"):
        return dict(
            result,
            peak_working_set_bytes=123456,
            memory_worker_contract="isolated-peak-rss-v1",
            memory_lifetime=dict(
                contract="retained-process-terminal-peak-v1",
                pid=456,
                birth_100ns=1000010,
                exit_100ns=1000110,
                worker_reported_peak_rss_bytes=123000,
                terminal_peak_rss_bytes=123456,
                residency_qualified=False,
                descendant_coverage_qualified=False,
                observer_effects_qualified=False,
            ),
        )
    batch = int(option("--batch-iterations"))
    paired = result["operation_id"] == "latency:cli-startup"
    result.update(
        unit="nanoseconds",
        sample_iterations=64,
        batch_iterations=batch,
        samples=[1000000] * 64,
        batch_elapsed_samples=[1000000 * batch] * 64,
        process_cpu_samples=[900000] * 64,
        process_cpu_batch_elapsed_samples=[900000 * batch] * 64,
        process_cpu_utilization_basis_points=[9000] * 64,
        maximum_descheduling_nanoseconds=50000000,
        maximum_sample_attempts=128,
        sample_attempts=64 if paired else 65,
        rejected_batch_elapsed_samples=[] if paired else [100000000],
        rejected_process_cpu_batch_elapsed_samples=[] if paired else [40000000],
        rejected_process_cpu_utilization_basis_points=[] if paired else [4000],
        control_samples=[1000000] * 64 if paired else [],
        control_batch_elapsed_samples=[1000000] * 64 if paired else [],
        control_process_cpu_samples=[900000] * 64 if paired else [],
        control_process_cpu_batch_elapsed_samples=[900000] * 64 if paired else [],
        control_process_cpu_utilization_basis_points=[9000] * 64 if paired else [],
    )
    if "--cli-launch-schedule" in command:
        result.update(
            cli_launch_schedule=option("--cli-launch-schedule"),
            request_first=[False] * 32 + [True] * 32,
        )
    return result


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = controller.load_json(controller.MANIFEST_PATH)
        self.manifest_path = self.root / controller.MANIFEST_PATH.relative_to(
            controller.ROOT
        )
        self.manifest_path.parent.mkdir(parents=True)
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.artifacts = {}
        for role in ("runner", "kernel", "interop", "memory_worker"):
            path = self.root / role
            path.write_bytes(role.encode())
            self.artifacts[role] = path
        # The worker is resolved by the runner from its own executable directory.
        worker = self.root / "strling-performance-memory-worker.exe"
        self.artifacts["memory_worker"].rename(worker)
        self.artifacts["memory_worker"] = worker
        for field in ("fixture_manifest", "resource_inventory"):
            path = self.root / self.manifest[field]["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                (controller.ROOT / self.manifest[field]["path"]).read_bytes()
            )
        self.inputs = {
            p: envelope._hash(p)
            for p in (
                self.manifest_path,
                *self.artifacts.values(),
                *(
                    self.root / self.manifest[f]["path"]
                    for f in ("fixture_manifest", "resource_inventory")
                ),
            )
        }
        self.environment = dict(
            os="windows",
            execution_resource=dict(
                platform="windows",
                processor_group=0,
                placement_mechanism="process-affinity-cpu-sets-supported-controls",
                selected_logical_processor=1,
                selected_cpu_set_id=257,
                cpu_set_allocation_state=dict(
                    allocated=False,
                    allocated_to_target_process=False,
                    realtime=False,
                    allocation_tag="0x0000000000000000",
                ),
                processor_topology=dict(core_index=1, efficiency_class=0),
                timer=dict(source="QueryPerformanceCounter", frequency_hz=10000000),
                process_power_policy=dict(
                    version=1,
                    control_mask=1,
                    state_mask=0,
                    execution_speed_policy="high-qos",
                    enforcement_result="success",
                ),
            ),
        )
        self.calls = []
        self.source = "a" * 40
        self.identity = patch.object(
            controller, "_git_identity", return_value=(self.source, False)
        ).start()
        self.addCleanup(patch.stopall)
        self.capture = patch.object(
            envelope, "capture", side_effect=self.fake_capture
        ).start()

    def fake_capture(self, spec, directory):
        envelope._validate(spec)
        directory.mkdir()
        self.calls.append(spec)
        result = result_for(list(spec.command), self.environment)
        (directory / "stdout.bin").write_bytes(json.dumps(result).encode())
        (directory / "stderr.bin").write_bytes(b"")
        row = dict(
            status="observed",
            exit_code=0,
            whole_action_ns=123,
            cleanup=dict(quiescent=True),
        )
        envelope._save(directory / "terminal.json", row)
        return row

    def acquire(
        self, key=("latency:semantic-parse", "fixture:semantic-tiny"), **overrides
    ):
        kwargs = dict(
            root=self.root,
            manifest=self.manifest,
            artifacts=self.artifacts,
            environment=self.environment,
            process_environment={"TEST": "1"},
            inputs=self.inputs,
            source_sha=self.source,
            batch_iterations=1,
            directory=self.root / "attempt",
        )
        kwargs.update(overrides)
        return acquisition.acquire_coordinate(key, **kwargs)

    def test_all_54_actual_builders_and_validators(self):
        keys = controller.performance_measurement_keys(self.manifest)
        self.assertEqual(len(keys), 54)
        for index, key in enumerate(keys):
            row = self.acquire(key, directory=self.root / str(index))
            self.assertEqual(row["status"], "observed")
            self.assertFalse(row["certification_eligible"])
            self.assertFalse(row["baseline_admission"])
            commands = []

            def normal_run(command, **options):
                commands.append(tuple(command))
                return subprocess.CompletedProcess(
                    command, 0, json.dumps(result_for(command, self.environment)), ""
                )

            with patch.object(controller.subprocess, "run", side_effect=normal_run):
                normal = controller._measure_key(
                    key,
                    manifest=self.manifest,
                    artifacts=self.artifacts,
                    environment=self.environment,
                    batch_iterations=1,
                    root=self.root,
                )
            self.assertEqual(row["observation"], normal)
            if commands:
                self.assertEqual(commands, [self.calls[-1].command])
            if key[0].startswith("latency:"):
                cmd = self.calls[-1].command
                self.assertEqual(cmd[cmd.index("--warmups") + 1], "512")
                self.assertEqual(len(row["observation"]["samples"]), 64)
                paired = key[0] == "latency:cli-startup"
                self.assertEqual(
                    len(row["observation"]["control_samples"]), 64 if paired else 0
                )
                self.assertEqual(
                    row["observation"]["sample_attempts"], 64 if paired else 65
                )
            elif key[0].startswith("memory:"):
                self.assertEqual(row["observation"]["samples"], [123456])
            else:
                self.assertIsNone(row["process_envelope"])
                self.assertEqual(row["observation"]["samples"], [len(b"kernelinterop")])
        self.assertEqual(len(self.calls), 53)
        self.assertEqual(sum("--kernel-bin" in c.command for c in self.calls), 2)
        self.assertEqual(
            sum(
                r["enforcement"] == "informational" for r in self.manifest["operations"]
            ),
            1,
        )

    def test_invalid_preflight_never_launches(self):
        variants = [
            dict(batch_iterations=True),
            dict(batch_iterations=0),
            dict(batch_iterations=4097),
            dict(source_sha="b" * 40),
            dict(environment={"os": "linux"}),
            dict(inputs={}),
        ]
        for values in variants:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.acquire(**values)
        self.identity.return_value = (self.source, True)
        with self.assertRaises(ValueError):
            self.acquire()
        self.capture.assert_not_called()
        self.assertFalse((self.root / "attempt").exists())

    def test_memory_scalar_requires_exact_positive_integer(self):
        key = ("memory:kernel-peak-rss", "fixture:protocol-common")
        for index, value in enumerate((True, False, 0, -1, 1.0, "1", None)):
            with self.subTest(value=value):
                events = []

                def returned(command, **options):
                    raw = result_for(command, self.environment)
                    raw["peak_working_set_bytes"] = value
                    raw["memory_lifetime"]["worker_reported_peak_rss_bytes"] = value
                    raw["memory_lifetime"]["terminal_peak_rss_bytes"] = value
                    return subprocess.CompletedProcess(command, 0, json.dumps(raw), "")

                with controller._retain_measurement_processes(events.append):
                    with self.assertRaises(controller.PerformanceResourceError):
                        controller._memory_sample(
                            key[1],
                            artifacts=self.artifacts,
                            selected_logical_cpu=1,
                            execution_resource=self.environment["execution_resource"],
                            process_executor=returned,
                            root=self.root,
                        )
                self.assertEqual(len(events), 2)
                self.assertEqual(
                    json.loads(events[-1]["stdout"])["peak_working_set_bytes"], value
                )

                def malformed(spec, directory):
                    terminal = self.fake_capture(spec, directory)
                    path = directory / "stdout.bin"
                    raw = json.loads(path.read_bytes())
                    raw["peak_working_set_bytes"] = value
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    return terminal

                self.capture.side_effect = malformed
                before = len(self.calls)
                directory = self.root / f"memory-{index}"
                receipt = self.acquire(key, directory=directory)
                self.assertEqual(receipt["status"], "failed")
                self.assertNotIn("observation", receipt)
                self.assertFalse(receipt["certification_eligible"])
                self.assertEqual(len(self.calls), before + 1)
                self.assertEqual(
                    json.loads((directory / "process/stdout.bin").read_bytes())[
                        "peak_working_set_bytes"
                    ],
                    value,
                )

    def test_memory_integer_preserved_without_coercion(self):
        for value in (1, 123456, 2**53 + 1):
            with self.subTest(value=value):

                def returned(command, **options):
                    raw = result_for(command, self.environment)
                    raw["peak_working_set_bytes"] = value
                    raw["memory_lifetime"]["worker_reported_peak_rss_bytes"] = value
                    raw["memory_lifetime"]["terminal_peak_rss_bytes"] = value
                    return subprocess.CompletedProcess(command, 0, json.dumps(raw), "")

                actual = controller._memory_sample(
                    "fixture:protocol-common",
                    artifacts=self.artifacts,
                    selected_logical_cpu=1,
                    execution_resource=self.environment["execution_resource"],
                    process_executor=returned,
                    root=self.root,
                )
                self.assertIs(type(actual), int)
                self.assertEqual(actual, value)

    def test_memory_lifetime_gaps_and_audit_contract_never_admit(self):
        mutations = [
            ("pid", True),
            ("pid", 0),
            ("birth_100ns", 0),
            ("exit_100ns", 100),
            ("exit_100ns", 0),
            ("terminal_peak_rss_bytes", 123455),
            ("terminal_peak_rss_bytes", True),
            ("worker_reported_peak_rss_bytes", 123457),
            ("worker_reported_peak_rss_bytes", False),
            ("contract", "self-report-only"),
            ("residency_qualified", True),
            ("descendant_coverage_qualified", 0),
            ("observer_effects_qualified", None),
            ("extra", 1),
            ("missing-lifetime", None),
            ("audit-contract", None),
        ]
        for index, (name, value) in enumerate(mutations):
            with self.subTest(name=name, value=value):

                def malformed(spec, directory):
                    terminal = self.fake_capture(spec, directory)
                    path = directory / "stdout.bin"
                    raw = json.loads(path.read_bytes())
                    if name == "missing-lifetime":
                        del raw["memory_lifetime"]
                    elif name == "audit-contract":
                        raw["memory_worker_contract"] = (
                            "unqualified-resident-memory-audit-v1"
                        )
                    else:
                        raw["memory_lifetime"][name] = value
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    return terminal

                self.capture.side_effect = malformed
                before = len(self.calls)
                directory = self.root / f"lifetime-{index}"
                receipt = self.acquire(
                    ("memory:kernel-peak-rss", "fixture:protocol-common"),
                    directory=directory,
                )
                self.assertEqual(receipt["status"], "failed")
                self.assertNotIn("observation", receipt)
                self.assertEqual(len(self.calls), before + 1)
                self.assertTrue((directory / "process/stdout.bin").is_file())

    def test_unknown_coordinate_and_changed_manifest(self):
        with self.assertRaises(ValueError):
            self.acquire(("unknown", None))
        manifest = copy.deepcopy(self.manifest)
        manifest["measurement_policy"]["warmup_iterations"] = 1
        with self.assertRaises(ValueError):
            self.acquire(manifest=manifest)
        self.capture.assert_not_called()

    def test_missing_memory_worker_and_changed_input(self):
        missing = dict(self.inputs)
        del missing[self.artifacts["memory_worker"]]
        with self.assertRaises(ValueError):
            self.acquire(inputs=missing)
        self.artifacts["kernel"].write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.acquire()
        self.capture.assert_not_called()

    def test_failed_envelope_retained_and_no_retry(self):
        def fail(spec, directory):
            row = self.fake_capture(spec, directory)
            return dict(row, status="failed")

        self.capture.side_effect = fail
        row = self.acquire()
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("observation", row)
        self.assertEqual(self.capture.call_count, 1)
        self.assertTrue((self.root / "attempt/process/stdout.bin").exists())
        with self.assertRaises(FileExistsError):
            self.acquire()

    def test_invalid_raw_json_and_controller_result_fail_closed(self):
        for index, raw in enumerate(
            (b"not-json", b'{"a":1,"a":2}', b'{"a":NaN}', b"{}")
        ):

            def malformed(spec, directory):
                row = self.fake_capture(spec, directory)
                (directory / "stdout.bin").write_bytes(raw)
                return row

            self.capture.side_effect = malformed
            row = self.acquire(directory=self.root / str(index))
            self.assertEqual(row["status"], "failed")
            self.assertNotIn("observation", row)

    def test_source_drift_and_input_drift_after_result(self):
        self.identity.side_effect = [(self.source, False), ("b" * 40, False)]
        row = self.acquire()
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("observation", row)
        self.identity.side_effect = None

        def changed(spec, directory):
            row = self.fake_capture(spec, directory)
            self.artifacts["interop"].write_bytes(b"change")
            return row

        self.capture.side_effect = changed
        row = self.acquire(directory=self.root / "second")
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("observation", row)

    def test_transport_is_explicit_and_preserves_recorder(self):
        events = []
        response = subprocess.CompletedProcess(["test"], 0, "raw", "err")
        with patch.object(
            controller.subprocess, "run", return_value=response
        ) as default:
            with controller._retain_measurement_processes(events.append):
                actual = controller._measurement_process_run(["test"])
            self.assertIs(actual, response)
            default.assert_called_once_with(["test"])
        self.assertEqual(
            [r["event"] for r in events],
            ["measurement-process-start", "measurement-process-result"],
        )


if __name__ == "__main__":
    unittest.main()
