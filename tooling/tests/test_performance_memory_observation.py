"""Raw memory observations never confer admission or unrestricted ancestry."""

from copy import deepcopy
import ctypes as c
from contextlib import ExitStack
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tooling import performance_memory_observation as observed


def fixture():
    return dict(
        version=1,
        role="unqualified-process-memory-observation",
        pid=123,
        birth_100ns=456,
        query_begin_ns=100,
        query_end_ns=101,
        working_set_controls=dict(minimum=1024, maximum=2048, flags=6),
        memory={name: 1 for name, _ in observed._Memory._fields_ if name != "cb"},
        certification_eligible=False,
    )


class MemoryObservationTests(unittest.TestCase):
    def test_pair_requires_same_identity_order_controls_and_monotonic_peaks(self):
        before, after = fixture(), fixture()
        after["query_begin_ns"], after["query_end_ns"] = 102, 103
        observed.validate_pair(before, after)
        for field in ("pid", "birth_100ns"):
            changed = deepcopy(after)
            changed[field] += 1
            with self.assertRaises(ValueError):
                observed.validate_pair(before, changed)
        changed = deepcopy(after)
        changed["query_begin_ns"] = 100
        with self.assertRaises(ValueError):
            observed.validate_pair(before, changed)
        for name in before["working_set_controls"]:
            changed = deepcopy(after)
            changed["working_set_controls"][name] += 1
            with self.assertRaises(ValueError):
                observed.validate_pair(before, changed)
        for name in (
            "peak_working_set_bytes",
            "peak_pagefile_bytes",
            "quota_peak_paged_pool_bytes",
            "quota_peak_nonpaged_pool_bytes",
        ):
            changed = deepcopy(before)
            changed["memory"][name] += 1
            with self.assertRaises(ValueError):
                observed.validate_pair(changed, after)

    def test_assignment_flags_drift_rejected_and_raw_fault_wrap_preserved(self):
        before, after = fixture(), fixture()
        after["query_begin_ns"], after["query_end_ns"] = 102, 103
        after["working_set_controls"]["flags"] = 10
        with self.assertRaisesRegex(ValueError, "controls changed"):
            observed.validate_pair(before, after)
        after["working_set_controls"]["flags"] = 6
        before["memory"]["page_fault_count"] = 2**32 - 1
        expected = deepcopy((before, after))
        observed.validate_pair(before, after)
        self.assertEqual(expected, (before, after))

    def test_x64_structure(self):
        self.assertEqual(80, c.sizeof(observed._Memory))
        self.assertEqual(8, observed._Memory.peak_working_set_bytes.offset)
        self.assertEqual(72, observed._Memory.private_bytes.offset)

    def test_raw_flags_preserved_without_authority(self):
        for flags in (0, 5, 6, 9, 10, 2**31):
            raw = fixture()
            raw["working_set_controls"]["flags"] = flags
            before = deepcopy(raw)
            observed.validate_snapshot(raw)
            self.assertEqual(before, raw)

    def test_bad_closed_metadata_rejected(self):
        for key, value in (
            ("version", True),
            ("role", "qualified"),
            ("pid", False),
            ("pid", 0),
            ("birth_100ns", 0),
            ("query_begin_ns", -1),
            ("query_end_ns", 99),
            ("certification_eligible", 0),
            ("certification_eligible", True),
            ("extra", 1),
        ):
            with self.subTest(key=key, value=value):
                raw = fixture()
                raw[key] = value
                with self.assertRaises(ValueError):
                    observed.validate_snapshot(raw)
        raw = fixture()
        del raw["memory"]
        with self.assertRaises(ValueError):
            observed.validate_snapshot(raw)

    def test_bad_counters_controls_rejected(self):
        for group in ("memory", "working_set_controls"):
            for key in fixture()[group]:
                for value in (True, -1, 2**64, float("nan")):
                    with self.subTest(group=group, key=key, value=value):
                        raw = fixture()
                        raw[group][key] = value
                        with self.assertRaises(ValueError):
                            observed.validate_snapshot(raw)
            raw = fixture()
            raw[group]["extra"] = 0
            with self.assertRaises(ValueError):
                observed.validate_snapshot(raw)

    def test_inverted_limits_and_peaks_rejected(self):
        raw = fixture()
        raw["working_set_controls"]["maximum"] = 1
        with self.assertRaises(ValueError):
            observed.validate_snapshot(raw)
        for key in (
            "working_set_bytes",
            "pagefile_bytes",
            "quota_paged_pool_bytes",
            "quota_nonpaged_pool_bytes",
        ):
            raw = fixture()
            raw["memory"][key] = 2
            with self.assertRaises(ValueError):
                observed.validate_snapshot(raw)

    def native_fixture(self, failure=None, incomplete=False):
        def times(handle, birth, *unused):
            birth._obj.value = 456
            return failure != "times"

        def limits(handle, minimum, maximum, flags):
            minimum._obj.value, maximum._obj.value, flags._obj.value = 1024, 2048, 6
            return failure != "limits"

        def memory(handle, pointer, size):
            for name, _ in observed._Memory._fields_:
                if name != "cb":
                    setattr(pointer._obj, name, 1)
            if incomplete:
                pointer._obj.cb -= 1
            return failure != "memory"

        return SimpleNamespace(
            GetProcessId=Mock(return_value=os.getpid()),
            GetProcessTimes=Mock(side_effect=times),
            GetProcessWorkingSetSizeEx=Mock(side_effect=limits),
            K32GetProcessMemoryInfo=Mock(side_effect=memory),
        )

    def invoke(self, native):
        with ExitStack() as stack:
            for name, kwargs in (
                ("_require_windows", {"return_value": None}),
                ("_kernel32", {"return_value": native}),
                ("_current_process_handle", {"return_value": -1}),
                ("_raise_last_error", {"side_effect": RuntimeError("query failed")}),
            ):
                stack.enter_context(patch.object(observed.windows, name, **kwargs))
            return observed.current_process_snapshot()

    def test_complete_native_query(self):
        native = self.native_fixture()
        result = self.invoke(native)
        self.assertEqual(fixture()["memory"], result["memory"])
        self.assertEqual(
            fixture()["working_set_controls"], result["working_set_controls"]
        )
        self.assertEqual(os.getpid(), result["pid"])
        self.assertEqual(456, result["birth_100ns"])
        self.assertFalse(result["certification_eligible"])

    def test_failed_queries_never_become_unrestricted(self):
        for failure in ("times", "limits", "memory"):
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.invoke(self.native_fixture(failure=failure))
        with self.assertRaises(ValueError):
            self.invoke(self.native_fixture(incomplete=True))
        native = self.native_fixture()
        native.GetProcessId.return_value = os.getpid() + 1
        with self.assertRaises(ValueError):
            self.invoke(native)

    @unittest.skipUnless(os.name == "nt", "native Windows integration")
    def test_actual_readonly_current_process(self):
        result = observed.current_process_snapshot()
        self.assertEqual(os.getpid(), result["pid"])
        self.assertGreater(result["memory"]["working_set_bytes"], 0)
        self.assertGreater(result["memory"]["private_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
