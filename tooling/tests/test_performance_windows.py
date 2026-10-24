from __future__ import annotations

import ast
import copy
import hashlib
import json
import struct
import subprocess
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from tooling import performance_windows
from tooling import performance_windows_active
from tooling import performance_resource_certification as controller
from tooling.performance_resource_certification import _windows_host_attestation
from tooling.performance_windows import (
    CONDITIONING_VERSION,
    MAXIMUM_SELECTED_BUSY_BASIS_POINTS,
    MAXIMUM_SELECTED_INTERRUPT_BASIS_POINTS,
    MAXIMUM_SYSTEM_BUSY_BASIS_POINTS,
    OBSERVATION_MILLISECONDS,
    POLICY_ID,
    WindowsQualificationError,
    evaluate_quiescence,
    guest_indicators,
    parse_cpu_set_records,
    quiescence_rates,
    selected_cpu_set,
    selected_cpu_set_allocation_state,
    validate_process_power_policy,
    validate_performance_power_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def _counter(
    *, idle: int, kernel: int, user: int, dpc: int = 0, interrupt: int = 0
) -> dict[str, int]:
    return {
        "idle": idle,
        "kernel": kernel,
        "user": user,
        "dpc": dpc,
        "interrupt": interrupt,
        "interrupt_count": 0,
    }


class NativeWindowsPerformanceEnvironmentTests(unittest.TestCase):
    def quota_api(self, *, in_job=True, flags=0, returned_bytes=8, failure=None):
        def membership(process, job, output):
            if failure == "membership":
                return 0
            output._obj.value = int(in_job)
            return 1

        def query(job, information_class, values, size, returned):
            self.assertIsNone(job)
            self.assertEqual(information_class, 15)
            self.assertEqual(size, 8)
            if failure == "query":
                return 0
            values[0] = flags
            returned._obj.value = returned_bytes
            return 1

        return Mock(
            IsProcessInJob=Mock(side_effect=membership),
            QueryInformationJobObject=Mock(side_effect=query),
        )

    def test_job_quota_observation_distinguishes_unknown_ancestors(self):
        for in_job, flags, expected in (
            (False, 0, "unlimited"),
            (True, 0, "unknown"),
            (True, 1, "limited"),
            (True, 5, "limited"),
            (True, 0x10, "unknown"),
        ):
            with self.subTest(in_job=in_job, flags=flags):
                api = self.quota_api(in_job=in_job, flags=flags)
                with (
                    patch.object(performance_windows, "_kernel32", return_value=api),
                    patch.object(
                        performance_windows, "_current_process_handle", return_value=42
                    ),
                ):
                    result = performance_windows.cpu_quota_state()
                self.assertEqual(result["effective_cpu_quota"], expected)
                self.assertEqual(result["control_flags"], flags)
                self.assertEqual(api.QueryInformationJobObject.call_count, int(in_job))

    def test_job_quota_query_errors_and_wrong_lengths_fail_closed(self):
        for failure, length in (
            ("membership", 8),
            ("query", 8),
            (None, 0),
            (None, 7),
            (None, 9),
        ):
            with self.subTest(failure=failure, length=length):
                api = self.quota_api(failure=failure, returned_bytes=length)
                with (
                    patch.object(performance_windows, "_kernel32", return_value=api),
                    patch.object(
                        performance_windows, "_current_process_handle", return_value=42
                    ),
                    patch.object(
                        performance_windows,
                        "_raise_last_error",
                        side_effect=WindowsQualificationError("API failure"),
                    ),
                    self.assertRaises(WindowsQualificationError),
                ):
                    performance_windows.cpu_quota_state()

    def test_job_quota_rejection_precedes_placement_and_timer(self):
        for state, reason in (
            ("unknown", "ancestor CPU quota is unknown"),
            ("limited", "imposes a CPU quota"),
        ):
            with (
                self.subTest(state=state),
                patch.object(
                    performance_windows,
                    "cpu_quota_state",
                    return_value={"effective_cpu_quota": state},
                ),
                patch.object(
                    performance_windows, "enforce_current_process_placement"
                ) as placement,
                patch.object(performance_windows, "timer_information") as timer,
            ):
                with self.assertRaisesRegex(WindowsQualificationError, reason):
                    performance_windows.execution_resource(1)
                placement.assert_not_called()
                timer.assert_not_called()

    def test_conditioning_policy_requires_sustained_recovery_window(self) -> None:
        self.assertEqual(CONDITIONING_VERSION, "1.5.0")
        self.assertEqual(POLICY_ID, "native-windows-supported-controls-quiescence-v6")
        self.assertEqual(OBSERVATION_MILLISECONDS, 10_000)

    def test_cpu_set_records_authenticate_group_core_and_class(self) -> None:
        record = struct.pack(
            "<IIIHBBBBBBIQ",
            32,
            0,
            276,
            0,
            20,
            20,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        parsed = parse_cpu_set_records(record)
        self.assertEqual(parsed[0]["cpu_set_id"], 276)
        self.assertEqual(parsed[0]["processor_group"], 0)
        self.assertEqual(parsed[0]["logical_processor_index"], 20)
        self.assertEqual(parsed[0]["core_index"], 20)
        self.assertEqual(parsed[0]["efficiency_class"], 0)
        selected = selected_cpu_set(20, parsed)
        self.assertEqual(selected["thread_siblings"], [20])
        self.assertEqual(
            selected["physical_core_identity"], "group-0/core-20/efficiency-0"
        )

    def test_cpu_set_parser_and_selection_fail_closed(self) -> None:
        with self.assertRaises(WindowsQualificationError):
            parse_cpu_set_records(b"\x20\x00")
        record = struct.pack(
            "<IIIHBBBBBBIQ",
            32,
            0,
            256,
            0,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
        )
        with self.assertRaises(WindowsQualificationError):
            selected_cpu_set(20, parse_cpu_set_records(record))

    def test_cpu_set_allocation_state_accepts_supported_native_controls(self) -> None:
        def record(flags: int) -> bytes:
            return struct.pack(
                "<IIIHBBBBBBIQ",
                32,
                0,
                276,
                0,
                20,
                20,
                0,
                0,
                0,
                flags,
                0,
                0xA11C,
            )

        ordinary = selected_cpu_set_allocation_state(
            20, parse_cpu_set_records(record(0x00))
        )
        self.assertEqual(
            ordinary,
            {
                "allocated": False,
                "allocated_to_target_process": False,
                "realtime": False,
                "allocation_tag": "0x000000000000a11c",
            },
        )
        reservation = selected_cpu_set_allocation_state(
            20, parse_cpu_set_records(record(0x06))
        )
        self.assertEqual(
            reservation,
            {
                "allocated": True,
                "allocated_to_target_process": True,
                "realtime": False,
                "allocation_tag": "0x000000000000a11c",
            },
        )
        selected_cpu_set_allocation_state(20, parse_cpu_set_records(record(0x07)))
        for flags in (0x02, 0x04):
            with (
                self.subTest(flags=flags),
                self.assertRaises(WindowsQualificationError),
            ):
                selected_cpu_set_allocation_state(
                    20, parse_cpu_set_records(record(flags))
                )

    def test_guest_firmware_indicators_fail_closed(self) -> None:
        self.assertEqual(
            guest_indicators(
                {"manufacturer": "VMware, Inc.", "product": "Virtual Machine"}
            ),
            ["manufacturer:vmware", "product:virtual machine"],
        )
        self.assertEqual(
            guest_indicators({"manufacturer": "Notebook", "product": "X370SNx1"}),
            [],
        )

    def test_quiescence_limits_pass_at_boundary_and_reject_one_over(self) -> None:
        at_boundary = {
            "selected_busy_basis_points": MAXIMUM_SELECTED_BUSY_BASIS_POINTS,
            "selected_interrupt_basis_points": (
                MAXIMUM_SELECTED_INTERRUPT_BASIS_POINTS
            ),
            "system_busy_basis_points": MAXIMUM_SYSTEM_BUSY_BASIS_POINTS,
        }
        self.assertEqual(evaluate_quiescence(at_boundary), [])
        for field in at_boundary:
            noisy = dict(at_boundary)
            noisy[field] += 1
            self.assertEqual(len(evaluate_quiescence(noisy)), 1, field)

    def test_quiescence_rates_use_selected_and_whole_host_denominators(self) -> None:
        before = [
            _counter(idle=0, kernel=0, user=0),
            _counter(idle=0, kernel=0, user=0),
        ]
        after = [
            _counter(idle=9_000, kernel=9_500, user=500),
            _counter(idle=9_600, kernel=9_700, user=300, dpc=25, interrupt=25),
        ]
        rates = quiescence_rates(before, after, 1)
        self.assertEqual(rates["selected_busy_basis_points"], 400)
        self.assertEqual(rates["selected_interrupt_basis_points"], 50)
        self.assertEqual(rates["system_busy_basis_points"], 700)
        self.assertEqual(evaluate_quiescence(rates), [])

    def test_fixed_frequency_power_policy_fails_closed(self) -> None:
        power = {
            "processor_settings": {
                "minimum_processor_state_percent": 100,
                "maximum_processor_state_percent": 100,
                "processor_performance_boost_mode": 0,
            },
            "selected_processor_frequency": {
                "processor_number": 20,
                "maximum_mhz": 2200,
                "current_mhz": 2200,
                "mhz_limit": 2200,
            },
        }
        validate_performance_power_policy(power)
        for field, value in (
            ("minimum_processor_state_percent", 99),
            ("maximum_processor_state_percent", 99),
            ("processor_performance_boost_mode", 1),
        ):
            changed = json.loads(json.dumps(power))
            changed["processor_settings"][field] = value
            with self.assertRaises(WindowsQualificationError):
                validate_performance_power_policy(changed)
        changed = json.loads(json.dumps(power))
        changed["selected_processor_frequency"]["current_mhz"] = 2199
        with self.assertRaises(WindowsQualificationError):
            validate_performance_power_policy(changed)

    def test_attested_frequency_guard_rejects_values_without_mutation(
        self,
    ) -> None:
        power = {
            "processor_settings": {
                "minimum_processor_state_percent": 100,
                "maximum_processor_state_percent": 100,
                "processor_performance_boost_mode": 0,
            },
            "selected_processor_frequency": {
                "processor_number": 1,
                "maximum_mhz": 2200,
                "current_mhz": 1466,
                "mhz_limit": 2200,
            },
        }
        original = copy.deepcopy(power)
        with self.assertRaises(WindowsQualificationError) as caught:
            validate_performance_power_policy(power)
        self.assertIn("authenticated non-boosted frequency", str(caught.exception))
        self.assertEqual(power, original)
        for field in ("current_mhz", "mhz_limit"):
            for value in (None, "2200", 2199, 2201):
                with self.subTest(field=field, value=value):
                    changed = copy.deepcopy(power)
                    changed["selected_processor_frequency"]["current_mhz"] = 2200
                    changed["selected_processor_frequency"][field] = value
                    with self.assertRaisesRegex(
                        WindowsQualificationError, "authenticated non-boosted frequency"
                    ):
                        validate_performance_power_policy(changed)

    def test_controller_prepares_controls_before_unmodified_probe_guard(
        self,
    ) -> None:
        power = {
            "processor_settings": {
                "minimum_processor_state_percent": 100,
                "maximum_processor_state_percent": 100,
                "processor_performance_boost_mode": 0,
            },
            "selected_processor_frequency": {
                "processor_number": 1,
                "maximum_mhz": 2200,
                "current_mhz": 1466,
                "mhz_limit": 2200,
            },
        }

        def reject_power(*args: object, **kwargs: str) -> None:
            self.assertEqual(resource_mock.call_count, 1)
            validate_performance_power_policy(power, **kwargs)

        with ExitStack() as stack:
            for name, value in (
                ("enumerate_cpu_sets", []),
                ("selected_cpu_set", {}),
                ("processor_group_counts", [2]),
                ("firmware_identity", {}),
                ("guest_indicators", []),
            ):
                stack.enter_context(
                    patch.object(performance_windows, name, return_value=value)
                )
            power_mock = stack.enter_context(
                patch.object(
                    performance_windows, "power_information", side_effect=reject_power
                )
            )
            resource_mock = stack.enter_context(
                patch.object(performance_windows, "execution_resource")
            )
            with self.assertRaisesRegex(
                WindowsQualificationError,
                "authenticated non-boosted frequency",
            ):
                controller._prepared_windows_platform_probe(1)
            power_mock.assert_called_once_with(2, 1)
            resource_mock.assert_called_once_with(1)
            power_mock.reset_mock()
            resource_mock.side_effect = WindowsQualificationError(
                "controls unavailable"
            )
            with self.assertRaisesRegex(
                WindowsQualificationError, "controls unavailable"
            ):
                controller._prepared_windows_platform_probe(1)
            power_mock.assert_not_called()

    def test_live_conditioner_only_adds_reviewed_fail_closed_quota_check(self) -> None:
        source = ROOT / "tooling/performance_windows.py"
        self.assertEqual(
            "ae27259d989e0ea55e0a79c84c0ad7fee3a9e74f502432925b4f174b23ce7112",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        original = subprocess.check_output(
            [
                "git",
                "show",
                "9d36da894c826cf2331d43fb413c3bb0b34db08e:tooling/performance_windows.py",
            ],
            cwd=ROOT,
        )
        self.assertEqual(
            "0996f40c7f96f747a8dabf4018c57238cbbec6d3a2daa0ed4df413bd0fda908c",
            hashlib.sha256(original).hexdigest(),
        )

        def unchanged_policy(data):
            tree = ast.parse(data)
            tree.body = [
                node
                for node in tree.body
                if not isinstance(node, ast.FunctionDef)
                or node.name not in {"cpu_quota_state", "execution_resource"}
            ]
            return ast.dump(tree, include_attributes=False)

        self.assertEqual(
            unchanged_policy(original), unchanged_policy(source.read_bytes())
        )

    def test_conditioner_child_preparation_preserves_exit_and_authority(self) -> None:
        arguments = {
            "selected_logical_cpu": 1,
            "expected_host_attestation": "a" * 64,
            "expected_conditioner_sha256": hashlib.sha256(
                (ROOT / "tooling/performance_windows.py").read_bytes()
            ).hexdigest(),
        }
        authority = {
            name: (controller.BASELINE_PATH.parent / name).read_bytes()
            for name in ("baseline.json", "manifest.json", "valid-evidence.json")
        }
        for exit_code in (0, 2):
            calls = []
            with (
                self.subTest(exit_code=exit_code),
                patch.object(controller.platform, "system", return_value="Windows"),
                patch.object(
                    performance_windows,
                    "execution_resource",
                    side_effect=lambda cpu: calls.append(("resource", cpu)),
                ),
                patch.object(
                    performance_windows,
                    "main",
                    side_effect=lambda argv: (
                        calls.append(("condition", argv)) or exit_code
                    ),
                ),
            ):
                self.assertEqual(
                    exit_code, controller._windows_conditioner_entrypoint(**arguments)
                )
            self.assertEqual("resource", calls[0][0])
            self.assertEqual(
                (
                    "condition",
                    [
                        "condition",
                        "--selected-logical-cpu",
                        "1",
                        "--expected-host-attestation",
                        "a" * 64,
                        "--json",
                    ],
                ),
                calls[1],
            )
        for name, payload in authority.items():
            self.assertEqual(
                payload, (controller.BASELINE_PATH.parent / name).read_bytes()
            )

    def test_conditioner_child_identity_controls_and_drift_fail_closed(self) -> None:
        expected = hashlib.sha256(
            (ROOT / "tooling/performance_windows.py").read_bytes()
        ).hexdigest()
        good = dict(
            selected_logical_cpu=1,
            expected_host_attestation="a" * 64,
            expected_conditioner_sha256=expected,
        )
        for field, bad in (
            ("selected_logical_cpu", 2),
            ("expected_host_attestation", "malformed"),
            ("expected_conditioner_sha256", "0" * 64),
        ):
            with (
                self.subTest(field=field),
                patch.object(controller.platform, "system", return_value="Windows"),
                patch.object(performance_windows, "execution_resource") as controls,
                patch.object(performance_windows, "main") as main,
                self.assertRaisesRegex(
                    controller.PerformanceResourceError, "canonical attested"
                ),
            ):
                controller._windows_conditioner_entrypoint(**{**good, field: bad})
            controls.assert_not_called()
            main.assert_not_called()
        with (
            patch.object(controller.platform, "system", return_value="Windows"),
            patch.object(
                performance_windows,
                "execution_resource",
                side_effect=WindowsQualificationError("controls unavailable"),
            ),
            patch.object(performance_windows, "main") as main,
            self.assertRaisesRegex(
                controller.PerformanceResourceError, "controls unavailable"
            ),
        ):
            controller._windows_conditioner_entrypoint(**good)
        main.assert_not_called()

        with (
            patch.object(controller.platform, "system", return_value="Windows"),
            patch.object(
                controller,
                "file_fingerprint",
                side_effect=[expected, expected, "0" * 64],
            ),
            patch.object(performance_windows, "execution_resource"),
            patch.object(performance_windows, "main", return_value=0),
            self.assertRaisesRegex(
                controller.PerformanceResourceError, "changed during observation"
            ),
        ):
            controller._windows_conditioner_entrypoint(**good)

        with (
            patch.object(controller.platform, "system", return_value="Windows"),
            patch.object(
                controller, "file_fingerprint", side_effect=[expected, "0" * 64]
            ),
            patch.object(performance_windows, "execution_resource"),
            patch.object(performance_windows, "main") as main,
            self.assertRaisesRegex(
                controller.PerformanceResourceError, "changed during preparation"
            ),
        ):
            controller._windows_conditioner_entrypoint(**good)
        main.assert_not_called()

    def test_conditioner_child_cli_keeps_original_status(self) -> None:
        with patch.object(
            controller, "_windows_conditioner_entrypoint", return_value=2
        ) as entrypoint:
            self.assertEqual(
                2,
                controller.main(
                    [
                        "condition-windows",
                        "--selected-logical-cpu",
                        "1",
                        "--expected-host-attestation",
                        "a" * 64,
                        "--expected-conditioner-sha256",
                        "b" * 64,
                        "--json",
                    ]
                ),
            )
        entrypoint.assert_called_once_with(
            selected_logical_cpu=1,
            expected_host_attestation="a" * 64,
            expected_conditioner_sha256="b" * 64,
        )

    def test_process_power_policy_requires_explicit_high_qos(self) -> None:
        policy = {
            "api": "SetProcessInformation(ProcessPowerThrottling)",
            "version": 1,
            "control_mask": 1,
            "state_mask": 0,
            "execution_speed_policy": "high-qos",
            "enforcement_result": "success",
        }
        validate_process_power_policy(policy)
        for field, value in (
            ("control_mask", 0),
            ("state_mask", 1),
            ("execution_speed_policy", "eco-qos"),
            ("enforcement_result", "failed"),
        ):
            changed = dict(policy)
            changed[field] = value
            with self.assertRaises(WindowsQualificationError):
                validate_process_power_policy(changed)

    def test_supported_controls_attestation_is_schema_valid(self) -> None:
        baseline = json.loads(
            (
                ROOT / "tests/certification/performance-resource/1.0/baseline.json"
            ).read_text(encoding="utf-8")
        )
        environment = baseline["environment"]
        historical = environment["host_attestation"]
        host_processor = historical["host_processor"]
        historical_evidence = historical["reservation_evidence"]
        execution = copy.deepcopy(environment["execution_resource"])
        allocation_state = {
            "allocated": False,
            "allocated_to_target_process": False,
            "realtime": False,
            "allocation_tag": "0x0000000000000000",
        }
        execution["placement_mechanism"] = (
            "process-affinity-cpu-sets-supported-controls"
        )
        execution["cpu_set_allocation_state"] = allocation_state
        probe = {
            "os": {
                "product_name": "Windows 11 Pro",
                "display_version": "25H2",
                "current_build": "26200",
                "ubr": 9168,
                "native_version": "10.0.26200.9168",
            },
            "processor_registry": {
                "identifier": host_processor["processor_identifier"],
                "vendor_id": host_processor["vendor_id"],
                "microcode_update_revision": host_processor["microcode"],
                "model_name": host_processor["model_name"],
            },
            "execution_resource": execution,
            "selected_cpu_set": historical_evidence["selected_cpu_topology"],
            "host_cpu_sets": historical_evidence["host_topology"],
            "processor_group_counts": historical_evidence["processor_group_counts"],
            "logical_processor_count": host_processor["logical_cpu_count"],
            "physical_core_count": host_processor["physical_core_count"],
            "power": historical_evidence["power"],
            "firmware": historical_evidence["firmware"],
            "guest_indicators": [],
        }
        attestation = _windows_host_attestation(
            probe, selected_logical_cpu=20, root=ROOT
        )
        self.assertEqual(
            attestation["reservation"]["mechanism"],
            "native-windows-supported-controls",
        )
        self.assertFalse(attestation["reservation"]["exclusive"])
        self.assertFalse(attestation["reservation"]["unrelated_workloads_excluded"])
        self.assertEqual(
            attestation["reservation_evidence"]["cpu_set_allocation_state"],
            allocation_state,
        )

    @unittest.skipUnless(sys.platform == "win32", "native Windows-only integration")
    def test_live_native_probe_and_attestation_are_self_consistent(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tooling.performance_windows",
                "probe",
                "--selected-logical-cpu",
                "20",
                "--json",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            unavailable = json.loads(completed.stderr)
            self.assertEqual(unavailable["status"], "unavailable")
            self.assertTrue(
                "selected Windows CPU set" in unavailable["reason"]
                or "ancestor CPU quota is unknown" in unavailable["reason"],
                unavailable,
            )
            return
        probe = json.loads(completed.stdout)
        execution = probe["execution_resource"]
        self.assertEqual(execution["effective_cpu_affinity"], [20])
        self.assertEqual(execution["processor_group"], 0)
        self.assertEqual(
            execution["process_power_policy"],
            {
                "api": "SetProcessInformation(ProcessPowerThrottling)",
                "version": 1,
                "control_mask": 1,
                "state_mask": 0,
                "execution_speed_policy": "high-qos",
                "enforcement_result": "success",
            },
        )
        self.assertEqual(execution["cpu_quota"]["effective_cpu_quota"], "unlimited")
        self.assertIs(execution["cpu_quota"]["in_job"], False)
        self.assertEqual(probe["power"]["source"], "ac")
        self.assertEqual(
            probe["power"]["processor_settings"],
            {
                "minimum_processor_state_percent": 100,
                "maximum_processor_state_percent": 100,
                "processor_performance_boost_mode": 0,
            },
        )
        self.assertEqual(
            probe["power"]["selected_processor_frequency"]["current_mhz"],
            probe["power"]["selected_processor_frequency"]["maximum_mhz"],
        )
        self.assertEqual(probe["guest_indicators"], [])
        attestation = _windows_host_attestation(
            probe, selected_logical_cpu=20, root=ROOT
        )
        self.assertEqual(attestation["environment_kind"], "native-windows-bare-metal")
        self.assertFalse(attestation["reservation"]["exclusive"])
        self.assertFalse(attestation["reservation"]["unrelated_workloads_excluded"])
        self.assertTrue(attestation["reservation"]["quiescence_required"])


class ActiveWorkAccountingTests(unittest.TestCase):
    def window(self) -> dict[str, object]:
        empty = _counter(idle=0, kernel=0, user=0)
        idle = _counter(idle=100_000_000, kernel=100_000_000, user=0)
        after = [copy.deepcopy(idle) for _ in range(32)]
        after[1] = _counter(idle=0, kernel=3_125_000, user=96_875_000, dpc=500_000)
        return {
            "kind": performance_windows_active.ACTIVE_WORK_KIND,
            "work_iterations": 10_000,
            "minimum_blocks": 64,
            "additional_guard_100ns": 312_500,
            "block_count": 64,
            "work_digest": performance_windows_active.ACTIVE_WORK_DIGEST,
            "priority_class": 32,
            "priority_class_after": 32,
            "affinity_before": {
                "processor_group": 0,
                "effective_logical_processors": [1],
                "process_affinity_mask": "0x0000000000000002",
                "system_affinity_mask": "0x00000000ffffffff",
            },
            "affinity_after": {
                "processor_group": 0,
                "effective_logical_processors": [1],
                "process_affinity_mask": "0x0000000000000002",
                "system_affinity_mask": "0x00000000ffffffff",
            },
            "processor_before": {
                "query_begin_ns": 0,
                "query_end_ns": 10,
                "rows": [copy.deepcopy(empty) for _ in range(32)],
            },
            "actor_before": {
                "query_begin_ns": 20,
                "query_end_ns": 30,
                "creation_filetime_100ns": "134371087783213433",
                "kernel_100ns": "0",
                "user_100ns": "0",
                "processor": 1,
            },
            "actor_after": {
                "query_begin_ns": 10_000_000_030,
                "query_end_ns": 10_000_000_040,
                "creation_filetime_100ns": "134371087783213433",
                "kernel_100ns": "1000000",
                "user_100ns": "96875000",
                "processor": 1,
            },
            "processor_after": {
                "query_begin_ns": 10_000_000_050,
                "query_end_ns": 10_000_000_060,
                "rows": after,
            },
        }

    def rates(self, proof=None):
        return performance_windows_active.active_quiescence_rates(
            self.window() if proof is None else proof, 1, 32
        )

    def test_same_ceilings_and_no_kernel_or_system_credit(self):
        proof = self.window()
        rates = self.rates(proof)
        self.assertEqual(rates["selected_busy_basis_points"], 344)
        self.assertEqual(rates["selected_interrupt_basis_points"], 50)
        self.assertEqual(rates["system_busy_basis_points"], 313)
        proof["actor_after"]["kernel_100ns"] = "3000000"
        self.assertEqual(rates, self.rates(proof))
        self.assertEqual(evaluate_quiescence(rates), [])

    def test_exact_selected_boundary_and_one_accounted_unit_over(self):
        proof = self.window()
        proof["actor_after"]["user_100ns"] = "95312500"
        self.assertEqual(self.rates(proof)["selected_busy_basis_points"], 500)
        proof["actor_after"]["user_100ns"] = "95312499"
        self.assertEqual(self.rates(proof)["selected_busy_basis_points"], 501)

    def test_interrupt_boundary_never_rounds_into_pass(self):
        proof = self.window()
        proof["processor_after"]["rows"][1]["dpc"] = 1_000_001
        self.assertEqual(self.rates(proof)["selected_interrupt_basis_points"], 101)
        self.assertIn(
            "selected_interrupt_basis_points>100",
            evaluate_quiescence(self.rates(proof)),
        )

    def test_whole_host_limit_includes_the_complete_actor(self):
        proof = self.window()
        for cpu in range(2, 7):
            proof["processor_after"]["rows"][cpu] = _counter(
                idle=0, kernel=100_000_000, user=0
            )
        self.assertIn(
            "system_busy_basis_points>1500", evaluate_quiescence(self.rates(proof))
        )

    def test_high_foreground_interference_is_retained_and_rejected(self):
        proof = self.window()
        proof["actor_after"]["user_100ns"] = "90000000"
        self.assertEqual(self.rates(proof)["selected_busy_basis_points"], 1032)
        self.assertIn(
            "selected_busy_basis_points>500", evaluate_quiescence(self.rates(proof))
        )

    def test_actor_user_or_kernel_overclaim_is_not_clamped(self):
        for field, value in (("user_100ns", "96875001"), ("kernel_100ns", "3125001")):
            proof = self.window()
            proof["actor_after"][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_actor_cpu_birth_and_regressed_accounting_fail_closed(self):
        for field, value in (
            ("processor", 20),
            ("creation_filetime_100ns", "134371087783213434"),
            ("kernel_100ns", "0"),
        ):
            proof = self.window()
            if field == "kernel_100ns":
                proof["actor_before"]["kernel_100ns"] = "1"
            proof["actor_after"][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_affinity_and_priority_cannot_change_during_work(self):
        for field, value in (
            ("processor_group", 1),
            ("effective_logical_processors", [0, 1]),
            ("effective_logical_processors", [True]),
            ("process_affinity_mask", "0x0000000000000003"),
            ("system_affinity_mask", "0x0000000000000000"),
        ):
            proof = self.window()
            proof["affinity_after"][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)
        proof = self.window()
        proof["priority_class_after"] = 64
        with self.assertRaises(WindowsQualificationError):
            self.rates(proof)

    def test_every_nesting_boundary_and_short_window_fail_closed(self):
        for frame, field, value in (
            ("processor_before", "query_begin_ns", 11),
            ("processor_before", "query_end_ns", 21),
            ("actor_before", "query_begin_ns", 31),
            ("actor_after", "query_begin_ns", 10_000_000_029),
            ("actor_after", "query_end_ns", 10_000_000_051),
            ("processor_after", "query_end_ns", 10_000_000_049),
        ):
            proof = self.window()
            proof[frame][field] = value
            with (
                self.subTest(frame=frame, field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_raw_cpu_denominator_fields_types_and_regressions(self):
        variants = []
        proof = self.window()
        proof["processor_after"]["rows"].pop()
        variants.append(proof)
        for field, value in (("user", True), ("kernel", 100_000_000.0), ("idle", -1)):
            proof = self.window()
            proof["processor_after"]["rows"][0][field] = value
            variants.append(proof)
        proof = self.window()
        proof["processor_before"]["rows"][0]["user"] = 1
        variants.append(proof)
        proof = self.window()
        del proof["processor_after"]["rows"][0]["interrupt_count"]
        variants.append(proof)
        for proof in variants:
            with (
                self.subTest(proof=proof),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_recipe_coverage_unknown_keys_and_priority_fail_closed(self):
        for field, value in (
            ("kind", "idle-v6"),
            ("block_count", 63),
            ("minimum_blocks", True),
            ("work_iterations", 9999),
            ("additional_guard_100ns", 0),
            ("priority_class", 64),
            ("work_digest", "0" * 64),
            ("unregistered", 0),
        ):
            proof = self.window()
            proof[field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_FILETIME_strings_are_exact_and_no_clock_grid_is_inferred(self):
        proof = self.window()
        proof["actor_after"]["user_100ns"] = "96000001"
        self.assertEqual(self.rates(proof)["selected_busy_basis_points"], 432)
        for value in (
            96_875_000,
            96_875_000.0,
            "096875000",
            "９６８７５０００",
            str(2**64),
            "1" * 5000,
        ):
            proof = self.window()
            proof["actor_after"]["user_100ns"] = value
            with (
                self.subTest(value=value),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_native_counter_widths_and_processor_group_fail_closed(self):
        for selected, count in ((1, True), (64, 64), (1, 65), (2**63 - 1, 32)):
            with (
                self.subTest(selected=selected, count=count),
                self.assertRaises(WindowsQualificationError),
            ):
                performance_windows_active.active_quiescence_rates(
                    self.window(), selected, count
                )
        for field, value in (("user", 2**63), ("interrupt_count", 2**32)):
            proof = self.window()
            proof["processor_after"]["rows"][0][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)
        proof = self.window()
        proof["processor_after"]["rows"][0] = _counter(
            idle=100_000_000, kernel=99_000_000, user=2_000_000
        )
        with self.assertRaises(WindowsQualificationError):
            self.rates(proof)

    def test_inflated_or_short_CPU_denominators_cannot_hide_interference(self):
        for kernel in (90_000_000, 110_000_000):
            proof = self.window()
            proof["processor_after"]["rows"][0] = _counter(
                idle=kernel, kernel=kernel, user=0
            )
            with (
                self.subTest(kernel=kernel),
                self.assertRaises(WindowsQualificationError),
            ):
                self.rates(proof)

    def test_accounted_interference_fraction_exhaustive_boundary_model(self):
        # Inclusion theorem over accounted units; not a physical error-bound
        # or an empirical claim about the precision of Windows CPU counters.
        for nonactor in range(21):
            for actor_kernel in range(21):
                actor_user = 100 - nonactor - actor_kernel
                self.assertGreaterEqual(100 - actor_user, nonactor)
                self.assertEqual(100 - actor_user, nonactor + actor_kernel)

    def test_fixed_work_known_answer(self):
        self.assertEqual(
            hashlib.pbkdf2_hmac(
                "sha256",
                b"strling-active-work-v1",
                b"cpu1-accounted-isolation",
                10_000,
                32,
            ).hex(),
            performance_windows_active.ACTIVE_WORK_DIGEST,
        )

    def test_strict_schema_accepts_raw_proof_and_rejects_unregistered_fields(self):
        proof = self.window()
        controller.validate_definition(
            proof, definition="activeWorkProof", label="synthetic active proof"
        )
        for mutate in ("unknown", "numeric-birth", "missing-counter"):
            changed = copy.deepcopy(proof)
            if mutate == "unknown":
                changed["foreign"] = True
            elif mutate == "numeric-birth":
                changed["actor_before"]["creation_filetime_100ns"] = 134371087783213433
            else:
                del changed["processor_after"]["rows"][0]["idle"]
            with (
                self.subTest(mutate=mutate),
                self.assertRaises(controller.PerformanceResourceError),
            ):
                controller.validate_definition(
                    changed,
                    definition="activeWorkProof",
                    label="invalid synthetic active proof",
                )

    def observation(self):
        proof = self.window()
        return {
            "role": "unqualified-active-work-diagnostic",
            "status": "diagnostic-complete",
            "baseline_admission": False,
            "certification_eligible": False,
            "performance_qualification": False,
            "profiles": 0,
            "new_samples": 0,
            "candidate_rates": self.rates(proof),
            "candidate_limit_exceedances": [],
            "active_work": proof,
        }

    def test_diagnostic_reconstructs_instead_of_trusting_claimed_green(self):
        observation = self.observation()
        performance_windows_active.validate_diagnostic_observation(observation, 1, 32)
        for field, value in (
            ("selected_busy_basis_points", 0),
            ("selected_interrupt_basis_points", 0),
            ("selected_interrupt_count_delta", False),
        ):
            changed = copy.deepcopy(observation)
            changed["candidate_rates"][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                performance_windows_active.validate_diagnostic_observation(
                    changed, 1, 32
                )
        changed = copy.deepcopy(observation)
        changed["active_work"]["actor_after"]["user_100ns"] = "90000000"
        with self.assertRaises(WindowsQualificationError):
            performance_windows_active.validate_diagnostic_observation(changed, 1, 32)

    def test_diagnostic_cannot_assert_authority_or_hide_exceeded_limits(self):
        for field, value in (
            ("status", "passed"),
            ("baseline_admission", True),
            ("certification_eligible", True),
            ("performance_qualification", True),
            ("profiles", False),
            ("new_samples", 1),
            ("candidate_limit_exceedances", ["ignored"]),
        ):
            changed = self.observation()
            changed[field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(WindowsQualificationError),
            ):
                performance_windows_active.validate_diagnostic_observation(
                    changed, 1, 32
                )

    def test_old_idle_snapshot_schema_cannot_carry_an_active_proof(self):
        baseline = json.loads(
            (
                ROOT / "tests/certification/performance-resource/1.0/baseline.json"
            ).read_bytes()
        )
        snapshot = copy.deepcopy(baseline["conditioning_repetitions"][0])
        controller.validate_definition(
            snapshot,
            definition="conditioningSnapshot",
            label="retained historical snapshot",
        )
        snapshot["quiescence_observation"]["active_work"] = self.window()
        with self.assertRaises(controller.PerformanceResourceError):
            controller.validate_definition(
                snapshot, definition="conditioningSnapshot", label="invalid relabel"
            )
        snapshot["policy_id"] = "native-windows-active-user-accounting-v7"
        with self.assertRaises(controller.PerformanceResourceError):
            controller.validate_definition(
                snapshot,
                definition="conditioningSnapshot",
                label="unqualified v7 snapshot",
            )
        del snapshot["quiescence_observation"]["active_work"]
        with self.assertRaises(controller.PerformanceResourceError):
            controller.validate_definition(
                snapshot,
                definition="conditioningSnapshot",
                label="v7 missing raw proof",
            )

    def test_acquisition_preserves_all_blocks_and_calls_only_own_apis(self):
        proof = self.window()
        kernel32 = Mock()
        kernel32.GetPriorityClass.return_value = 32
        with (
            patch.object(
                performance_windows_active, "_kernel32", return_value=kernel32
            ),
            patch.object(
                performance_windows_active, "_current_process_handle", return_value=1
            ),
            patch.object(
                performance_windows_active,
                "process_affinity",
                return_value=proof["affinity_before"],
            ),
            patch.object(
                performance_windows_active,
                "_active_processor_snapshot",
                side_effect=[
                    proof["processor_before"],
                    proof["processor_after"],
                ],
            ),
            patch.object(
                performance_windows_active,
                "_active_actor_snapshot",
                side_effect=[
                    proof["actor_before"],
                    proof["actor_after"],
                ],
            ),
            patch.object(
                performance_windows_active.time,
                "perf_counter_ns",
                side_effect=[
                    0,
                    *([20_000_000_000] * 65),
                ],
            ),
            patch.object(
                performance_windows_active.hashlib,
                "pbkdf2_hmac",
                return_value=bytes.fromhex(
                    performance_windows_active.ACTIVE_WORK_DIGEST
                ),
            ) as work,
        ):
            rates, observed = performance_windows_active.active_work_observation(1, 32)
        self.assertEqual(observed["block_count"], 64)
        self.assertEqual(work.call_count, 64)
        self.assertEqual(self.rates(proof), rates)

    def test_unavailable_or_non_normal_priority_is_not_work_admission(self):
        for value in (0, 64):
            kernel32 = Mock()
            kernel32.GetPriorityClass.return_value = value
            with (
                patch.object(
                    performance_windows_active, "_kernel32", return_value=kernel32
                ),
                patch.object(
                    performance_windows_active,
                    "_current_process_handle",
                    return_value=1,
                ),
                patch.object(
                    performance_windows_active, "_active_processor_snapshot"
                ) as capture,
                self.assertRaises(WindowsQualificationError),
            ):
                performance_windows_active.active_work_observation(1, 32)
            capture.assert_not_called()

    def test_failed_acquisition_preserves_exact_partial_raw_observations(self):
        proof = self.window()
        kernel32 = Mock()
        kernel32.GetPriorityClass.return_value = 32
        with (
            patch.object(
                performance_windows_active, "_kernel32", return_value=kernel32
            ),
            patch.object(
                performance_windows_active, "_current_process_handle", return_value=1
            ),
            patch.object(
                performance_windows_active,
                "process_affinity",
                return_value=proof["affinity_before"],
            ),
            patch.object(
                performance_windows_active,
                "_active_processor_snapshot",
                return_value=proof["processor_before"],
            ),
            patch.object(
                performance_windows_active,
                "_active_actor_snapshot",
                return_value=proof["actor_before"],
            ),
            patch.object(
                performance_windows_active.time, "perf_counter_ns", return_value=0
            ),
            patch.object(
                performance_windows_active.hashlib,
                "pbkdf2_hmac",
                return_value=b"invalid answer",
            ),
            self.assertRaises(WindowsQualificationError) as caught,
        ):
            performance_windows_active.active_work_observation(1, 32)
        raw = caught.exception.active_work_proof
        self.assertEqual(raw["processor_before"], proof["processor_before"])
        self.assertEqual(raw["actor_before"], proof["actor_before"])
        self.assertEqual(raw["work_digest"], b"invalid answer".hex())
        self.assertEqual(raw["block_count"], 0)
        self.assertNotIn("actor_after", raw)

    def test_own_thread_query_error_is_reported_without_an_undefined_fallback(self):
        kernel32 = Mock()
        kernel32.GetThreadTimes.return_value = 0
        with (
            patch.object(
                performance_windows_active, "_kernel32", return_value=kernel32
            ),
            patch.object(
                performance_windows_active,
                "_raise_last_error",
                side_effect=WindowsQualificationError(
                    "intentional current-thread query failure"
                ),
            ) as failed,
            self.assertRaises(WindowsQualificationError),
        ):
            performance_windows_active._active_actor_snapshot()
        failed.assert_called_once_with("GetThreadTimes(current admission actor)")

    def test_unavailable_diagnostic_retains_partial_data_never_green(self):
        error = WindowsQualificationError("intentional synthetic acquisition error")
        error.active_work_proof = {"block_count": 0, "complete": False}
        with patch.object(
            performance_windows_active, "active_work_observation", side_effect=error
        ):
            document = performance_windows_active.diagnostic_observation(1, 32)
        self.assertEqual(document["status"], "diagnostic-unavailable")
        self.assertEqual(document["active_work"], error.active_work_proof)
        self.assertIs(document["baseline_admission"], False)
        self.assertIs(document["certification_eligible"], False)


if __name__ == "__main__":
    unittest.main()
