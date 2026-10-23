"""Unqualified raw Windows process observation; never admission authority.

Cumulative counter snapshots enclose activity, not the time of each event.
Query brackets and scheduling gaps are retained, not treated as continuous
placement/control-state proof. Callers own launch, bounded waits and cleanup.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

from tooling import performance_windows as live

_CPU_FIELDS = {"idle", "kernel", "user", "dpc", "interrupt", "interrupt_count"}
_PROCESS_FIELDS = {"pid", "birth", "exit", "kernel", "user", "exited_before_query"}


def _integer(value: Any, maximum: int = 2**63 - 1) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid exact nonnegative counter")


def _filetime(value: Any) -> int:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 20
        or not value.isascii()
        or not value.isdecimal()
        or str(int(value)) != value
        or int(value) > 2**64 - 1
    ):
        raise ValueError("invalid raw FILETIME")
    return int(value)


def _process(value: Any) -> None:
    if type(value) is not dict or set(value) != _PROCESS_FIELDS:
        raise ValueError("invalid process snapshot shape")
    _integer(value["pid"], 2**32 - 1)
    if value["pid"] == 0 or _filetime(value["birth"]) == 0:
        raise ValueError("invalid process identity")
    _filetime(value["exit"])
    if type(value["exited_before_query"]) is not bool:
        raise ValueError("invalid process signal state")
    for field in ("kernel", "user"):
        _integer(value[field])


def validate_snapshot(current: dict, count: int, previous: dict | None) -> None:
    """Validate raw structure/monotonicity without rates, filtering or gates."""
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError("one processor group required")
    fields = {"query_begin_ns", "query_end_ns", "processors", "observer", "child"}
    if type(current) is not dict or set(current) != fields:
        raise ValueError("invalid snapshot shape")
    for field in ("query_begin_ns", "query_end_ns"):
        _integer(current[field])
    if current["query_end_ns"] < current["query_begin_ns"]:
        raise ValueError("inverted query bracket")
    if type(current["processors"]) is not list or len(current["processors"]) != count:
        raise ValueError("processor count drift")
    for cpu in current["processors"]:
        if type(cpu) is not dict or set(cpu) != _CPU_FIELDS:
            raise ValueError("invalid processor snapshot shape")
        for field in _CPU_FIELDS:
            _integer(cpu[field], 2**32 - 1 if field == "interrupt_count" else 2**63 - 1)
    _process(current["observer"])
    if current["observer"]["exited_before_query"]:
        raise ValueError("observer exited")
    if current["child"] is not None:
        _process(current["child"])
        if current["child"]["pid"] == current["observer"]["pid"]:
            raise ValueError("observer cannot be its own child")
    if previous is None:
        return
    if current["query_begin_ns"] < previous["query_end_ns"]:
        raise ValueError("overlapping query brackets")
    for old, new in zip(previous["processors"], current["processors"]):
        # InterruptCount is a raw ULONG. Preserve wrap; do not infer wrap count.
        if any(new[k] < old[k] for k in _CPU_FIELDS - {"interrupt_count"}):
            raise ValueError("processor counter regression")
    for role in ("observer", "child"):
        old, new = previous[role], current[role]
        if old is None:
            continue
        if new is None or (old["pid"], old["birth"]) != (new["pid"], new["birth"]):
            raise ValueError("process identity drift")
        if any(new[k] < old[k] for k in ("kernel", "user")):
            raise ValueError("process counter regression")
        if old["exited_before_query"] and (
            not new["exited_before_query"] or new["exit"] != old["exit"]
        ):
            raise ValueError("process exit identity drift")


def _process_times(handle: Any, pid: int) -> dict:
    kernel32 = live._kernel32()
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    wait.restype = ctypes.c_ulong
    state = int(wait(handle, 0))
    if state not in (0, 258):
        live._raise_last_error("WaitForSingleObject(diagnostic observer)")
    identity = kernel32.GetProcessId
    identity.argtypes = [ctypes.c_void_p]
    identity.restype = ctypes.c_ulong
    if int(identity(handle)) != pid:
        raise ValueError("borrowed process handle identity mismatch")
    values = [ctypes.c_ulonglong() for _ in range(4)]
    function = kernel32.GetProcessTimes
    function.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    function.restype = ctypes.c_int
    if not function(handle, *(ctypes.byref(value) for value in values)):
        live._raise_last_error("GetProcessTimes(diagnostic observer)")
    return dict(
        pid=pid,
        birth=str(values[0].value),
        exit=str(values[1].value),
        exited_before_query=state == 0,
        kernel=values[2].value,
        user=values[3].value,
    )


@contextmanager
def open_snapshot_process(pid: int, expected_birth: str):
    """Own a read-only, non-inheritable handle bound to an expected live birth.

    SYNCHRONIZE is necessary for _process_times' zero-timeout wait. Query and
    VM-read rights alone are insufficient. This opens no mutation/control rights
    and establishes identity only, never ownership or continuous isolation.
    The caller must already have authority to observe this particular process.
    """
    _integer(pid, 2**32 - 1)
    if pid == 0 or _filetime(expected_birth) == 0:
        raise ValueError("invalid expected process identity")
    kernel32 = live._kernel32()
    opened = kernel32.OpenProcess
    opened.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    opened.restype = ctypes.c_void_p
    closed = kernel32.CloseHandle
    closed.argtypes = [ctypes.c_void_p]
    closed.restype = ctypes.c_int
    # SYNCHRONIZE | PROCESS_QUERY_INFORMATION | PROCESS_VM_READ.
    handle = opened(0x100410, False, pid)
    if not handle:
        live._raise_last_error("OpenProcess(diagnostic snapshot)")
    try:
        identity = _process_times(handle, pid)
        if identity["birth"] != expected_birth:
            raise ValueError("diagnostic process birth mismatch")
        if identity["exited_before_query"]:
            raise ValueError("diagnostic process already exited")
        yield handle, identity
    finally:
        if not closed(handle):
            live._raise_last_error("CloseHandle(diagnostic snapshot)")


def native_snapshot(count: int, child: Any | None) -> dict:
    """Read only; a borrowed Popen handle prevents PID-reuse ambiguity."""
    live._require_windows()
    begin = time.perf_counter_ns()
    processors = live.processor_performance_counters(count)
    observer = _process_times(live._current_process_handle(), os.getpid())
    process = None if child is None else _process_times(child._handle, child.pid)
    return dict(
        query_begin_ns=begin,
        query_end_ns=time.perf_counter_ns(),
        processors=processors,
        observer=observer,
        child=process,
    )


class ProcessCounterJournal:
    """Exclusive, append-only diagnostics; no child or machine mutation.

    Construct BEFORE launch, sample during bounded waits, finish AFTER wait.
    Flush every observation so a failed acquisition retains its raw prefix.
    Complete means journal complete, not passing product or qualifying evidence.
    """

    def __init__(
        self, path: Path, processor_count: int, *, reader: Callable = native_snapshot
    ):
        if type(processor_count) is not int or not 1 <= processor_count <= 64:
            raise ValueError("one processor group required")
        self.count = processor_count
        self.reader = reader
        self.previous = None
        self.complete = False
        self.failed = False
        self.file = path.open("x", encoding="utf-8", newline="\n")
        try:
            self._write(
                dict(
                    event="header",
                    contract="diagnostic-process-counters-v1",
                    authoritative=False,
                    processor_count=processor_count,
                    clock="perf_counter_ns",
                    cpu_time_unit="100ns-raw-FILETIME",
                )
            )
            self._capture("before-launch", None)
        except BaseException:
            self.close()
            raise

    def _write(self, value: dict) -> None:
        self.file.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        self.file.flush()

    def _capture(self, event: str, child: Any | None) -> None:
        if self.failed:
            raise ValueError("journal acquisition already failed")
        if self.complete or self.file.closed:
            raise ValueError("journal already closed")
        try:
            current = self.reader(self.count, child)
            self._write(dict(event=event, snapshot=current))
            validate_snapshot(current, self.count, self.previous)
            if child is None:
                if current["child"] is not None:
                    raise ValueError("unexpected pre-launch child")
            elif current["child"] is None or current["child"]["pid"] != child.pid:
                raise ValueError("borrowed child identity mismatch")
            self.previous = current
        except BaseException:
            self.failed = True
            raise

    def sample(self, child: Any) -> None:
        self._capture("running", child)

    def finish(self, child: Any) -> None:
        if self.previous is None or self.previous["child"] is None:
            raise ValueError("prior child observation required")
        code = child.poll()
        if type(code) is not int:
            raise ValueError("child must have exited")
        self._capture("after-exit", child)
        if (
            not self.previous["child"]["exited_before_query"]
            or self.previous["child"]["exit"] == "0"
        ):
            self.failed = True
            raise ValueError("missing native exit time")
        self._write(dict(event="complete", authoritative=False, exit_code=code))
        os.fsync(self.file.fileno())
        self.complete = True

    def close(self) -> None:
        if self.file.closed:
            return
        try:
            if not self.complete:
                self._write(dict(event="incomplete", authoritative=False))
            os.fsync(self.file.fileno())
        finally:
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.close()
