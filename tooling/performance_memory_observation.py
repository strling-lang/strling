"""Read-only Windows memory attribution; never certification admission.

Raw process controls can expose restrictions hidden by an immediate-job query.
Snapshots neither prove continuous controls nor absence of working-set trimming.
No memory counter is subtracted, normalized, or substituted for governed RSS.
"""

from __future__ import annotations

import ctypes as c
import os
import time

from tooling import performance_windows as windows


class _Memory(c.Structure):
    _fields_ = [
        ("cb", c.c_uint32),
        ("page_fault_count", c.c_uint32),
        ("peak_working_set_bytes", c.c_size_t),
        ("working_set_bytes", c.c_size_t),
        ("quota_peak_paged_pool_bytes", c.c_size_t),
        ("quota_paged_pool_bytes", c.c_size_t),
        ("quota_peak_nonpaged_pool_bytes", c.c_size_t),
        ("quota_nonpaged_pool_bytes", c.c_size_t),
        ("pagefile_bytes", c.c_size_t),
        ("peak_pagefile_bytes", c.c_size_t),
        ("private_bytes", c.c_size_t),
    ]


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_snapshot(value):
    """Validate raw closed data, not environmental qualification."""
    _require(
        type(value) is dict
        and set(value)
        == {
            "version",
            "role",
            "pid",
            "birth_100ns",
            "query_begin_ns",
            "query_end_ns",
            "working_set_controls",
            "memory",
            "certification_eligible",
        },
        "closed memory snapshot",
    )
    _require(type(value["version"]) is int and value["version"] == 1, "version")
    _require(value["role"] == "unqualified-process-memory-observation", "role")
    _require(value["certification_eligible"] is False, "no admission authority")
    for name, minimum, maximum in (
        ("pid", 1, 2**32 - 1),
        ("birth_100ns", 1, 2**64 - 1),
        ("query_begin_ns", 0, 2**63 - 1),
        ("query_end_ns", 0, 2**63 - 1),
    ):
        _require(
            type(value[name]) is int and minimum <= value[name] <= maximum,
            f"exact {name}",
        )
    _require(value["query_end_ns"] >= value["query_begin_ns"], "query bracket")
    controls = value["working_set_controls"]
    _require(
        type(controls) is dict and set(controls) == {"minimum", "maximum", "flags"},
        "closed working-set controls",
    )
    for name, v in controls.items():
        _require(
            type(v) is int and 0 <= v <= (2**32 - 1 if name == "flags" else 2**64 - 1),
            "raw working-set control",
        )
    _require(controls["minimum"] <= controls["maximum"], "working-set range")
    memory = value["memory"]
    names = {name for name, _ in _Memory._fields_ if name != "cb"}
    _require(type(memory) is dict and set(memory) == names, "closed memory counters")
    for name, v in memory.items():
        maximum = 2**32 - 1 if name == "page_fault_count" else 2**64 - 1
        _require(type(v) is int and 0 <= v <= maximum, "exact raw memory counter")
    for current, peak in (
        ("working_set_bytes", "peak_working_set_bytes"),
        ("pagefile_bytes", "peak_pagefile_bytes"),
        ("quota_paged_pool_bytes", "quota_peak_paged_pool_bytes"),
        ("quota_nonpaged_pool_bytes", "quota_peak_nonpaged_pool_bytes"),
    ):
        _require(memory[current] <= memory[peak], "current exceeds peak")


def validate_pair(before, after):
    """Reject observed drift without treating two snapshots as continuous proof."""
    validate_snapshot(before)
    validate_snapshot(after)
    _require(
        (before["pid"], before["birth_100ns"]) == (after["pid"], after["birth_100ns"]),
        "memory observation process changed",
    )
    _require(after["query_begin_ns"] >= before["query_end_ns"], "overlapping queries")
    _require(
        before["working_set_controls"] == after["working_set_controls"],
        "working-set controls changed",
    )
    for name in (
        "peak_working_set_bytes",
        "peak_pagefile_bytes",
        "quota_peak_paged_pool_bytes",
        "quota_peak_nonpaged_pool_bytes",
    ):
        _require(after["memory"][name] >= before["memory"][name], "peak regressed")
    # PageFaultCount is a DWORD and can wrap; retain it without inferring a delta.


def current_process_snapshot():
    """Read only this process; query failures cannot become unlimited claims."""
    windows._require_windows()
    _require(c.sizeof(c.c_void_p) == 8 and c.sizeof(_Memory) == 80, "native x64 ABI")
    begin = time.perf_counter_ns()
    kernel = windows._kernel32()
    process = windows._current_process_handle()
    get_id = kernel.GetProcessId
    get_id.argtypes, get_id.restype = [c.c_void_p], c.c_uint32
    pid = int(get_id(process))
    _require(pid == os.getpid(), "current process identity")
    get_times = kernel.GetProcessTimes
    get_times.argtypes = [c.c_void_p] + [c.POINTER(c.c_uint64)] * 4
    get_times.restype = c.c_int
    times = [c.c_uint64() for _ in range(4)]
    if not get_times(process, *(c.byref(t) for t in times)):
        windows._raise_last_error("GetProcessTimes(memory observation)")
    get_limits = kernel.GetProcessWorkingSetSizeEx
    get_limits.argtypes = [
        c.c_void_p,
        c.POINTER(c.c_size_t),
        c.POINTER(c.c_size_t),
        c.POINTER(c.c_uint32),
    ]
    get_limits.restype = c.c_int
    minimum, maximum, flags = c.c_size_t(), c.c_size_t(), c.c_uint32()
    if not get_limits(process, c.byref(minimum), c.byref(maximum), c.byref(flags)):
        windows._raise_last_error("GetProcessWorkingSetSizeEx(memory observation)")
    memory = _Memory()
    memory.cb = c.sizeof(memory)
    get_memory = kernel.K32GetProcessMemoryInfo
    get_memory.argtypes = [c.c_void_p, c.POINTER(_Memory), c.c_uint32]
    get_memory.restype = c.c_int
    if not get_memory(process, c.byref(memory), c.sizeof(memory)):
        windows._raise_last_error("K32GetProcessMemoryInfo(memory observation)")
    _require(memory.cb == c.sizeof(memory), "complete memory structure")
    result = dict(
        version=1,
        role="unqualified-process-memory-observation",
        pid=pid,
        birth_100ns=times[0].value,
        query_begin_ns=begin,
        query_end_ns=time.perf_counter_ns(),
        working_set_controls=dict(
            minimum=minimum.value, maximum=maximum.value, flags=flags.value
        ),
        memory={
            name: int(getattr(memory, name))
            for name, _ in _Memory._fields_
            if name != "cb"
        },
        certification_eligible=False,
    )
    validate_snapshot(result)
    return result
