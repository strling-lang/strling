"""Synthetic complete-byte acquisition binding, never empirical qualification."""

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tooling import performance_acquisition_receipts as adapter
from tooling import performance_reference_bounds as bounds
from tooling.tests import test_performance_envelope_receipts as envelope_fixture
from tooling.tests.test_performance_envelope_receipts import encoded, digest
from tooling.tests.test_performance_envelope_acquisition import result_for
from tooling.tests import test_performance_envelope_acquisition as producer_fixture


def fixture(coordinate=None, ordinal=0, source="a", delay=0):
    inner = envelope_fixture.ReceiptTests()
    inner.setUp()
    root = Path(__file__).resolve().parents[2]
    manifest_bytes = (
        root / "tests/certification/performance-resource/1.0/manifest.json"
    ).read_bytes()
    manifest = json.loads(manifest_bytes)
    coordinate = coordinate or ["latency:cli-startup", "fixture:semantic-tiny"]
    memory = coordinate[0].startswith("memory:")
    artifacts = dict(
        runner="C:/fixture/runner.exe",
        kernel="C:/fixture/kernel.exe",
        interop="C:/fixture/interop.exe",
        memory_worker="C:/fixture/strling-performance-memory-worker.exe",
    )
    command = [
        artifacts["runner"],
        "--operation",
        coordinate[0],
        "--fixture",
        coordinate[1],
        "--warmups",
        "1" if memory else "512",
        "--samples",
        "1" if memory else "64",
    ]
    if not memory:
        command += ["--maximum-batch-iterations", "4096"]
    command += ["--expected-logical-cpu", "1"]
    if not memory:
        command += ["--batch-iterations", "1"]
    if coordinate[0] == "latency:cli-startup":
        command += ["--kernel-bin", artifacts["kernel"]]
    environment = dict(
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
    inputs = {p: "b" * 64 for p in artifacts.values()}
    inputs["C:/fixture/tests/certification/performance-resource/1.0/manifest.json"] = (
        digest(manifest_bytes)
    )
    for field in ("fixture_manifest", "resource_inventory"):
        inputs["C:/fixture/" + manifest[field]["path"]] = manifest[field]["sha256"]
    inner.plan.update(
        command=command,
        cwd="C:/fixture",
        source_sha=source * 40,
        inputs=inputs,
        timeout_seconds=1800,
    )
    inner.files["plan.json"] = encoded(inner.plan)
    inner.row["plan_sha256"] = digest(inner.files["plan.json"])
    offset = ordinal * 10_000_000_000
    for field, value in dict(
        action_begin_ns=10,
        release_begin_ns=20,
        root_exit_observed_ns=1_999_999_960,
        action_end_ns=2_000_000_010,
        finished_ns=2_000_000_080,
    ).items():
        inner.row[field] = (
            offset
            + value
            + (delay if field not in ("action_begin_ns", "release_begin_ns") else 0)
        )
    inner.row["whole_action_ns"] = 2_000_000_000 + delay
    inner.row["accounting"].update(
        query_begin_ns=offset + 2_000_000_000 + delay,
        query_end_ns=offset + 2_000_000_005 + delay,
    )
    inner.row["controls"]["cpu_set_id"] = 257
    inner.files["lifecycle-wakeups.json"] = b"[]"
    for name in ("suspended.json", "root-exit.json"):
        identity = json.loads(inner.files[name])
        identity.update(
            pid=1000 + ordinal,
            birth=str(1000000 + ordinal),
            exit=str(2000000 + ordinal),
        )
        inner.files[name] = encoded(identity)
    raw = result_for(command, environment)
    inner.files["stdout.bin"] = encoded(raw)
    inner.seal()
    outer_plan = dict(
        contract="unqualified-enclosed-coordinate-v1",
        source_sha=source * 40,
        coordinate=coordinate,
        batch_iterations=1,
        manifest=manifest,
        environment=environment,
        artifacts=artifacts,
        inputs=inputs,
        process_environment_sha256=inner.plan["environment_sha256"],
        adapter_sha256="1" * 64,
        controller_sha256="2" * 64,
    )
    events = [
        dict(event="measurement-process-start", command=command),
        dict(
            event="measurement-process-result",
            command=command,
            returncode=0,
            stdout=inner.files["stdout.bin"].decode(),
            stderr=inner.files["stderr.bin"].decode(),
        ),
    ]
    observation = project_fixture(raw, memory)
    files = {"process/" + k: v for k, v in inner.files.items()}
    files.update(
        {
            "manifest.json": manifest_bytes,
            "plan.json": encoded(outer_plan),
            "process-events.json": encoded(events),
        }
    )
    terminal = dict(
        contract=outer_plan["contract"],
        status="observed",
        authoritative=False,
        certification_eligible=False,
        baseline_admission=False,
        plan_sha256=digest(files["plan.json"]),
        process_envelope=dict(path="process/terminal.json", sha256=inner.pin),
        coordinate=coordinate,
        acquisition_begin_ns=offset + 1,
        acquisition_end_ns=offset + 2_000_000_090 + delay,
        observation=observation,
        process_events_sha256=digest(files["process-events.json"]),
    )
    files["terminal.json"] = encoded(terminal)
    expected = dict(
        terminal_sha256=digest(files["terminal.json"]),
        acquisition_plan=outer_plan,
        process_plan=inner.plan,
    )
    return files, expected


def project_fixture(raw, memory):
    if memory:
        return dict(
            samples=[raw["peak_working_set_bytes"]],
            batch_iterations=1,
            batch_duration_samples=None,
        )
    mapping = {
        "batch_duration_samples": "batch_elapsed_samples",
        "process_cpu_batch_duration_samples": "process_cpu_batch_elapsed_samples",
        "rejected_batch_duration_samples": "rejected_batch_elapsed_samples",
        "rejected_process_cpu_batch_duration_samples": "rejected_process_cpu_batch_elapsed_samples",
        "control_batch_duration_samples": "control_batch_elapsed_samples",
        "control_process_cpu_batch_duration_samples": "control_process_cpu_batch_elapsed_samples",
    }
    fields = "samples batch_iterations process_cpu_samples process_cpu_utilization_basis_points maximum_descheduling_nanoseconds maximum_sample_attempts sample_attempts rejected_process_cpu_utilization_basis_points control_samples control_process_cpu_samples control_process_cpu_utilization_basis_points".split()
    return {**{k: raw[k] for k in fields}, **{k: raw[v] for k, v in mapping.items()}}


class AcquisitionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.files, self.expected = fixture()

    def verify(self):
        return adapter.verify_acquisition_receipt(self.files, self.expected)

    def reseal_outer(self, row):
        self.files["terminal.json"] = encoded(row)
        self.expected["terminal_sha256"] = digest(self.files["terminal.json"])

    def test_raw_cli_bytes_and_all_denials(self):
        value = self.verify()
        self.assertEqual(
            value["row"]["cli_samples"],
            dict(request_ns=[1000000] * 64, control_ns=[1000000] * 64),
        )
        for key in (
            "certification_eligible",
            "baseline_admission",
            "ancestor_quota_qualified",
            "build_provenance_qualified",
            "independence_qualified",
        ):
            self.assertIs(value[key], False)

    def test_every_byte_stream_is_bound(self):
        for name in self.files:
            with self.subTest(name=name):
                self.setUp()
                self.files[name] += b" "
                with self.assertRaises(ValueError):
                    self.verify()

    def test_forged_observation_cannot_replace_raw_samples(self):
        row = json.loads(self.files["terminal.json"])
        row["observation"]["samples"][0] += 1
        self.reseal_outer(row)
        with self.assertRaisesRegex(ValueError, "projection"):
            self.verify()

    def test_raw_event_disagreement_rejected_even_with_refreshed_outer_hash(self):
        events = json.loads(self.files["process-events.json"])
        events[1]["stdout"] += " "
        self.files["process-events.json"] = encoded(events)
        row = json.loads(self.files["terminal.json"])
        row["process_events_sha256"] = digest(self.files["process-events.json"])
        self.reseal_outer(row)
        with self.assertRaisesRegex(ValueError, "events"):
            self.verify()

    def test_missing_extra_and_nested_receipt_tamper(self):
        for name in self.files:
            with self.subTest(name=name):
                self.setUp()
                del self.files[name]
                with self.assertRaises(ValueError):
                    self.verify()
        self.setUp()
        self.files["foreign"] = b""
        with self.assertRaises(ValueError):
            self.verify()

    def test_external_plan_and_source_boundaries(self):
        for key, value in (
            ("source_sha", "f" * 40),
            ("batch_iterations", 2),
            ("process_environment_sha256", "f" * 64),
        ):
            with self.subTest(key=key):
                self.setUp()
                self.expected["acquisition_plan"][key] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def test_valid_unfavorable_time_is_retained(self):
        files, expected = fixture(delay=500000000)
        value = adapter.verify_acquisition_receipt(files, expected)
        self.assertEqual(value["row"]["end_ns"] - value["row"]["begin_ns"], 2500000000)

    def test_all_actual_process_coordinate_commands(self):
        manifest = self.expected["acquisition_plan"]["manifest"]
        coordinates = [
            [op["id"], f]
            for op in manifest["operations"]
            if op["measurement_kind"] in ("latency", "peak-rss")
            for f in op["fixture_ids"]
        ]
        self.assertEqual(len(coordinates), 53)
        for i, key in enumerate(coordinates):
            with self.subTest(key=key):
                files, expected = fixture(key, i)
                value = adapter.verify_acquisition_receipt(files, expected)
                self.assertEqual(value["row"]["coordinate"], key)
                self.assertEqual(value["raw_runner"]["operation_id"], key[0])

    def replace_raw(self, raw):
        self.files["process/stdout.bin"] = encoded(raw)
        inner = json.loads(self.files["process/terminal.json"])
        inner["logs"]["stdout.bin"] = dict(
            sha256=digest(self.files["process/stdout.bin"]),
            bytes=len(self.files["process/stdout.bin"]),
        )
        self.files["process/terminal.json"] = encoded(inner)
        events = json.loads(self.files["process-events.json"])
        events[1]["stdout"] = self.files["process/stdout.bin"].decode()
        self.files["process-events.json"] = encoded(events)
        row = json.loads(self.files["terminal.json"])
        row["process_envelope"]["sha256"] = digest(self.files["process/terminal.json"])
        row["process_events_sha256"] = digest(self.files["process-events.json"])
        row["observation"] = project_fixture(raw, False)
        self.reseal_outer(row)

    def test_raw_arithmetic_and_type_forgery(self):
        attacks = [
            ("samples", True),
            ("samples", 999999),
            ("process_cpu_batch_elapsed_samples", 800000),
            ("control_samples", 999999),
            ("control_process_cpu_utilization_basis_points", 9999),
            ("maximum_descheduling_nanoseconds", 50000001),
            ("sample_attempts", 65),
            ("selected_logical_cpu", True),
        ]
        for field, value in attacks:
            with self.subTest(field=field):
                self.setUp()
                raw = json.loads(self.files["process/stdout.bin"])
                if type(raw[field]) is list:
                    raw[field][0] = value
                else:
                    raw[field] = value
                self.replace_raw(raw)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_rejected_attempts_and_control_channels_remain_lossless(self):
        files, expected = fixture(["latency:semantic-parse", "fixture:semantic-tiny"])
        value = adapter.verify_acquisition_receipt(files, expected)
        self.assertEqual(value["raw_runner"]["sample_attempts"], 65)
        self.assertEqual(
            value["observation"]["rejected_batch_duration_samples"], [100000000]
        )
        self.assertEqual(value["observation"]["control_samples"], [])

    def test_no_producer_or_execution_imports(self):
        import ast

        tree = ast.parse(Path(adapter.__file__).read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.extend((node.module + "." + a.name) for a in node.names)
        self.assertEqual(
            set(names),
            {
                "json",
                "pathlib.PureWindowsPath",
                "tooling.performance_envelope_receipts",
                "tooling.performance_reference_bounds",
            },
        )

    def test_actual_producer_transport_and_projection_compatibility(self):
        # Only the process executor/source identity is synthetic. The current
        # acquisition producer, command builder and raw validators really run.
        for key in (
            ("latency:cli-startup", "fixture:semantic-tiny"),
            ("memory:kernel-peak-rss", "fixture:protocol-common"),
        ):
            with self.subTest(key=key):
                suite = producer_fixture.AcquisitionTests()
                suite.setUp()
                captured = {}

                def native_fixture(spec, directory):
                    files, external = fixture(list(key))
                    process = external["process_plan"]
                    process.update(
                        command=list(spec.command),
                        cwd=str(spec.cwd),
                        source_sha=spec.source_sha,
                        inputs={str(p): h for p, h in spec.inputs.items()},
                        environment_sha256=digest(
                            json.dumps(spec.environment, sort_keys=True).encode()
                        ),
                        selected_cpu=spec.selected_cpu,
                        timeout_seconds=spec.timeout_seconds,
                    )
                    files["process/plan.json"] = encoded(process)
                    files["process/stdout.bin"] = encoded(
                        result_for(list(spec.command), suite.environment)
                    )
                    terminal = json.loads(files["process/terminal.json"])
                    terminal["plan_sha256"] = digest(files["process/plan.json"])
                    terminal["logs"]["stdout.bin"] = dict(
                        sha256=digest(files["process/stdout.bin"]),
                        bytes=len(files["process/stdout.bin"]),
                    )
                    files["process/terminal.json"] = encoded(terminal)
                    directory.mkdir()
                    for name in envelope_fixture.reader.FILES:
                        (directory / name).write_bytes(files["process/" + name])
                    captured["process_plan"] = copy.deepcopy(process)
                    return terminal

                try:
                    suite.capture.side_effect = native_fixture
                    with patch.object(
                        producer_fixture.acquisition.time,
                        "perf_counter_ns",
                        side_effect=(1, 2_000_000_100),
                    ):
                        terminal = suite.acquire(key)
                    self.assertEqual(terminal["status"], "observed", terminal)
                    directory = suite.root / "attempt"
                    files = {
                        name: (directory / name).read_bytes()
                        for name in adapter.FILES
                        if name != "manifest.json"
                    }
                    files["manifest.json"] = suite.manifest_path.read_bytes()
                    expected = dict(
                        terminal_sha256=digest(files["terminal.json"]),
                        acquisition_plan=json.loads(files["plan.json"]),
                        process_plan=captured["process_plan"],
                    )
                    verified = adapter.verify_acquisition_receipt(files, expected)
                    self.assertEqual(verified["observation"], terminal["observation"])
                    self.assertFalse(verified["certification_eligible"])
                finally:
                    suite.doCleanups()


class CohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, expected = fixture()
        manifest = expected["acquisition_plan"]["manifest"]
        cls.coordinates = [
            [op["id"], f]
            for op in manifest["operations"]
            if op["measurement_kind"] in ("latency", "peak-rss")
            for f in op["fixture_ids"]
        ]
        cls.bundles, cls.expectations = [], []
        for i, key in enumerate(cls.coordinates):
            for repetition in range(9):
                files, expected = fixture(key, i * 9 + repetition)
                cls.bundles.append(files)
                cls.expectations.append(expected)
        cls.plan = dict(
            method=bounds.METHOD,
            manifest_sha256=digest(cls.bundles[0]["manifest.json"]),
            environment_sha256=digest(
                adapter.encode(cls.expectations[0]["acquisition_plan"]["environment"])
            ),
            recipe_sha256=digest(
                adapter.encode(
                    [
                        adapter.recipe_for(cls.expectations[i * 9])
                        for i in range(len(cls.coordinates))
                    ]
                )
            ),
            coordinates=cls.coordinates,
            warmup_iterations=512,
            sample_iterations=64,
            repetitions=9,
        )
        cls.pins = dict(
            source_sha="a" * 40,
            runner_sha256="b" * 64,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in cls.expectations])
            ),
        )

    def assemble(
        self,
        bundles=None,
        expectations=None,
        plan=None,
        pins=None,
        role="reference-only",
    ):
        return adapter.assemble_cohort(
            self.bundles if bundles is None else bundles,
            self.expectations if expectations is None else expectations,
            role=role,
            plan=self.plan if plan is None else plan,
            pins=self.pins if pins is None else pins,
            coordinates=self.coordinates,
        )

    def test_all_954_raw_observations_flow_through_existing_bounds(self):
        result = self.assemble()
        frozen = bounds.freeze_reference(
            result["cohort"],
            result["cohort_sha256"],
            plan=self.plan,
            pins=self.pins,
            coordinates=self.coordinates,
        )
        holdout, expected = [], []
        for i, key in enumerate(self.coordinates):
            for repetition in range(9):
                files, exp = fixture(key, 477 + i * 9 + repetition, source="d")
                holdout.append(files)
                expected.append(exp)
        pins = dict(
            self.pins,
            source_sha="d" * 40,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in expected])
            ),
        )
        other = self.assemble(
            holdout, expected, pins=pins, role="source-distinct-holdout"
        )
        comparison = bounds.check_holdout(
            frozen,
            digest(frozen),
            other["cohort"],
            other["cohort_sha256"],
            reference_sha256=result["cohort_sha256"],
            plan=self.plan,
            reference_pins=self.pins,
            holdout_pins=pins,
            coordinates=self.coordinates,
        )
        self.assertEqual(len(json.loads(other["cohort"])["observations"]), 477)
        self.assertTrue(all(row["within_bound"] for row in comparison["comparisons"]))
        self.assertFalse(other["certification_eligible"])
        self.assertFalse(other["independence_qualified"])
        # Synthetic counterexample: both CLI channels slow equally while the
        # enclosing interval and their paired ratio remain unchanged.
        index = (
            next(
                i
                for i, key in enumerate(self.coordinates)
                if key[0] == "latency:cli-startup"
            )
            * 9
        )
        mutation = AcquisitionReceiptTests()
        mutation.files, mutation.expected = holdout[index], expected[index]
        raw = json.loads(mutation.files["process/stdout.bin"])
        for prefix in ("", "control_"):
            for field in ("samples", "batch_elapsed_samples"):
                raw[prefix + field] = [1100000] * 64
            for field in ("process_cpu_samples", "process_cpu_batch_elapsed_samples"):
                raw[prefix + field] = [990000] * 64
        mutation.replace_raw(raw)
        adverse_pins = dict(
            pins,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in expected])
            ),
        )
        adverse = self.assemble(
            holdout, expected, pins=adverse_pins, role="source-distinct-holdout"
        )
        checked = bounds.check_holdout(
            frozen,
            digest(frozen),
            adverse["cohort"],
            adverse["cohort_sha256"],
            reference_sha256=result["cohort_sha256"],
            plan=self.plan,
            reference_pins=self.pins,
            holdout_pins=adverse_pins,
            coordinates=self.coordinates,
        )
        self.assertFalse(checked["within_bounds"])
        self.assertTrue(checked["comparisons"][index]["whole_interval_within_bound"])
        self.assertFalse(checked["comparisons"][index]["within_bound"])
        self.assertEqual(
            json.loads(adverse["cohort"])["observations"][index]["cli_samples"][
                "request_ns"
            ],
            [1100000] * 64,
        )

    def test_incomplete_or_reused_receipts_never_fill_denominator(self):
        with self.assertRaisesRegex(ValueError, "complete nine"):
            self.assemble(self.bundles[:-1], self.expectations[:-1])
        files, expected = list(self.bundles), list(self.expectations)
        files[1], expected[1] = files[0], expected[0]
        pins = dict(
            self.pins,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in expected])
            ),
        )
        with self.assertRaises(ValueError):
            self.assemble(files, expected, pins=pins)

    def test_manifest_environment_recipe_source_and_binary_pins(self):
        for field in ("manifest_sha256", "environment_sha256", "recipe_sha256"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.assemble(plan=dict(self.plan, **{field: "f" * 64}))
        for field in ("source_sha", "runner_sha256", "acquisition_sha256"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.assemble(
                        pins=dict(
                            self.pins,
                            **{field: "f" * (40 if field == "source_sha" else 64)},
                        )
                    )

    def test_nested_process_reuse_with_new_outer_receipt_is_rejected(self):
        files, expected = list(self.bundles), copy.deepcopy(self.expectations)
        files[1] = dict(files[0])
        row = json.loads(files[1]["terminal.json"])
        row["acquisition_end_ns"] += 1
        files[1]["terminal.json"] = encoded(row)
        expected[1] = copy.deepcopy(expected[0])
        expected[1]["terminal_sha256"] = digest(files[1]["terminal.json"])
        pins = dict(
            self.pins,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in expected])
            ),
        )
        with self.assertRaises(ValueError):
            self.assemble(files, expected, pins=pins)

    def test_partial_coordinate_plan_cannot_shrink_manifest(self):
        coordinates = self.coordinates[:1]
        plan = dict(
            self.plan,
            coordinates=coordinates,
            recipe_sha256=digest(
                adapter.encode([adapter.recipe_for(self.expectations[0])])
            ),
        )
        pins = dict(
            self.pins,
            acquisition_sha256=digest(
                adapter.encode([e["terminal_sha256"] for e in self.expectations[:9]])
            ),
        )
        with self.assertRaisesRegex(ValueError, "complete manifest"):
            adapter.assemble_cohort(
                self.bundles[:9],
                self.expectations[:9],
                role="reference-only",
                plan=plan,
                pins=pins,
                coordinates=coordinates,
            )


if __name__ == "__main__":
    unittest.main()
