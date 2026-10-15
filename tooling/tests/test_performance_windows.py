from __future__ import annotations

import copy
import hashlib
import json
import struct
import subprocess
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tooling import performance_windows
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

    def test_live_conditioner_is_exact_original_attested_source(self) -> None:
        source = ROOT / "tooling/performance_windows.py"
        self.assertEqual(
            "0996f40c7f96f747a8dabf4018c57238cbbec6d3a2daa0ed4df413bd0fda908c",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            subprocess.check_output(
                [
                    "git",
                    "show",
                    "9d36da894c826cf2331d43fb413c3bb0b34db08e:tooling/performance_windows.py",
                ],
                cwd=ROOT,
            ),
            source.read_bytes(),
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
            self.assertIn("selected Windows CPU set", unavailable["reason"])
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


if __name__ == "__main__":
    unittest.main()
