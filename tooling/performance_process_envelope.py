"""Opt-in whole-process acquisition, NOT qualified performance admission.

Suspended creation closes the pre-assignment execution race. A private job owns
directly created descendants, including exited children in final accounting.
Wall time encloses launch/control setup, all work, output and exit. No short CPU
counter polling, CPU subtraction, filtering, normalization or threshold fitting.
Callers still own source freezing, semantic result validation, approved reference
acquisition, ancestor quota/power validation and independent evidence verification.
Broker/service-created processes are outside this source-reviewed launch model.
"""

from __future__ import annotations

from contextlib import ExitStack
import ctypes as c
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from types import SimpleNamespace
from typing import Callable

from tooling.performance_build_execution import _Job
from tooling import performance_process_observation as observation
from tooling import performance_windows as windows


@dataclass(frozen=True)
class Command:
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    inputs: dict[Path, str]
    source_sha: str
    selected_cpu: int
    timeout_seconds: int


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _check_inputs(spec):
    for path, digest in spec.inputs.items():
        _require(
            isinstance(path, Path)
            and path.is_absolute()
            and path.is_file()
            and not path.is_symlink(),
            "regular absolute input",
        )
        _require(
            type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest), "input SHA256"
        )
        _require(_hash(path) == digest, f"input changed: {path}")


def _validate(spec):
    _require(isinstance(spec, Command), "closed command plan")
    _require(type(spec.inputs) is dict and spec.inputs, "pinned inputs")
    _require(
        type(spec.command) is tuple
        and spec.command
        and all(type(s) is str and s and "\x00" not in s for s in spec.command),
        "literal command",
    )
    exe = Path(spec.command[0])
    _require(exe.is_absolute() and exe in spec.inputs, "pinned absolute executable")
    _require(
        isinstance(spec.cwd, Path) and spec.cwd.is_absolute() and spec.cwd.is_dir(),
        "absolute working directory",
    )
    _require(
        type(spec.selected_cpu) is int and 0 <= spec.selected_cpu < 64, "exact CPU"
    )
    _require(
        type(spec.timeout_seconds) is int and 1 <= spec.timeout_seconds <= 1800,
        "bounded deadline",
    )
    _require(
        type(spec.source_sha) is str and re.fullmatch("[0-9a-f]{40}", spec.source_sha),
        "source SHA",
    )
    _require(
        type(spec.environment) is dict
        and spec.environment
        and all(
            type(k) is str
            and k
            and "=" not in k
            and "\x00" not in k
            and type(v) is str
            and "\x00" not in v
            for k, v in spec.environment.items()
        ),
        "explicit environment",
    )
    _require(
        len({k.upper() for k in spec.environment}) == len(spec.environment),
        "environment key aliases",
    )
    _check_inputs(spec)


def _validate_accounting(row):
    for key in (
        "total_processes",
        "active_processes",
        "limit_terminated_processes",
        "user_100ns",
        "kernel_100ns",
    ):
        _require(
            type(row.get(key)) is int and row[key] >= 0, "invalid raw job accounting"
        )
    _require(
        row["total_processes"] >= 1
        and row["active_processes"] == 0
        and row["limit_terminated_processes"] == 0,
        "whole job did not exit normally",
    )


def _sealed_file(path):
    before = path.lstat()
    _require(
        stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
        "regular unlinked artifact",
    )
    _require(0 <= before.st_size <= 64 * 1024 * 1024, "bounded artifact")
    digest = _hash(path)
    after = path.lstat()
    fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    _require(
        all(getattr(before, k) == getattr(after, k) for k in fields),
        "artifact changed during sealing",
    )
    return dict(sha256=digest, bytes=before.st_size)


def _seal_artifacts(directory, result):
    observed = result["status"] == "observed"
    errors = []
    groups = {
        "logs": ("stdout.bin", "stderr.bin"),
        "artifacts": (
            "suspended.json",
            "root-exit.json",
            "lifecycle-wakeups.json",
            "launch-cleanup.json",
            "survivors.json",
        ),
    }
    for group, names in groups.items():
        result[group] = {}
        for name in names:
            path = directory / name
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
                continue
            try:
                result[group][name] = _sealed_file(path)
            except (OSError, ValueError) as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
    if observed and (
        set(result["logs"]) != {"stdout.bin", "stderr.bin"}
        or set(result["artifacts"])
        != {"suspended.json", "root-exit.json", "lifecycle-wakeups.json"}
    ):
        errors.append("complete successful artifact denominator required")
    if errors:
        result.update(status="failed", artifact_error="; ".join(errors))


def capture(spec: Command, directory: Path, *, factory: Callable | None = None) -> dict:
    """One immutable attempt. Failed acquisition never becomes an observation.

    This is a command envelope, not a replacement for existing sample JSON or a
    claim of isolation. Actual output and unfavorable elapsed times are retained.
    No automatic retry. Runtime cleanup is limited to newly owned handles/jobs.
    """
    _validate(spec)
    _require(directory.is_absolute(), "absolute new receipt directory")
    directory.mkdir(exist_ok=False)
    plan = dict(
        command=list(spec.command),
        cwd=str(spec.cwd),
        source_sha=spec.source_sha,
        inputs={str(p): h for p, h in spec.inputs.items()},
        environment_sha256=hashlib.sha256(
            json.dumps(spec.environment, sort_keys=True).encode()
        ).hexdigest(),
        selected_cpu=spec.selected_cpu,
        timeout_seconds=spec.timeout_seconds,
        implementation_sha256=_hash(Path(__file__)),
        job_implementation_sha256=_hash(
            Path(__file__).with_name("performance_build_execution.py")
        ),
        controls_implementation_sha256=_hash(Path(windows.__file__)),
        observation_implementation_sha256=_hash(Path(observation.__file__)),
    )
    _save(directory / "plan.json", plan)
    result = dict(
        contract="unqualified-process-tree-envelope-v2",
        status="failed",
        authoritative=False,
        certification_eligible=False,
        baseline_admission=False,
        plan_sha256=_hash(directory / "plan.json"),
        clock="perf_counter_ns",
        cpu_unit="raw-job-accounting-100ns",
        logs={},
    )
    child = None
    try:
        result["action_begin_ns"] = time.perf_counter_ns()
        child = (factory or _Native)(spec, directory)
        result["controls"] = child.configure()
        result["release_begin_ns"] = time.perf_counter_ns()
        child.resume()
        result["exit_code"] = child.wait(spec.timeout_seconds)
        result["root_exit_observed_ns"] = time.perf_counter_ns()
        # Read accounting even for a nonzero root exit; never hide bad results.
        result["accounting"] = child.finish()
        result["action_end_ns"] = time.perf_counter_ns()
        result["whole_action_ns"] = result["action_end_ns"] - result["action_begin_ns"]
        _validate_accounting(result["accounting"])
        _require(result["exit_code"] == 0, "nonzero command exit")
        _check_inputs(spec)
        result["status"] = "observed"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if child is not None:
            try:
                result["cleanup"] = child.close()
                _require(
                    result["cleanup"].get("quiescent") is True, "cleanup not quiescent"
                )
            except BaseException as error:
                result.update(
                    status="failed", cleanup_error=f"{type(error).__name__}: {error}"
                )
        _seal_artifacts(directory, result)
        result["finished_ns"] = time.perf_counter_ns()
        _save(directory / "terminal.json", result)
    return result


class _Startup(c.Structure):
    _fields_ = [
        ("cb", c.c_uint32),
        ("reserved", c.c_void_p),
        ("desktop", c.c_void_p),
        ("title", c.c_void_p),
        ("x", c.c_uint32),
        ("y", c.c_uint32),
        ("xsize", c.c_uint32),
        ("ysize", c.c_uint32),
        ("xcount", c.c_uint32),
        ("ycount", c.c_uint32),
        ("fill", c.c_uint32),
        ("flags", c.c_uint32),
        ("show", c.c_uint16),
        ("reserved_size", c.c_uint16),
        ("reserved_bytes", c.c_void_p),
        ("stdin", c.c_void_p),
        ("stdout", c.c_void_p),
        ("stderr", c.c_void_p),
    ]


class _StartupEx(c.Structure):
    _fields_ = [("startup", _Startup), ("attributes", c.c_void_p)]


class _Process(c.Structure):
    _fields_ = [
        ("process", c.c_void_p),
        ("thread", c.c_void_p),
        ("pid", c.c_uint32),
        ("tid", c.c_uint32),
    ]


class _Accounting(c.Structure):
    _fields_ = [
        ("user", c.c_int64),
        ("kernel", c.c_int64),
        ("period_user", c.c_int64),
        ("period_kernel", c.c_int64),
        ("page_faults", c.c_uint32),
        ("total", c.c_uint32),
        ("active", c.c_uint32),
        ("terminated", c.c_uint32),
    ]


class _BasicLimits(c.Structure):
    _fields_ = [
        ("process_time", c.c_int64),
        ("job_time", c.c_int64),
        ("flags", c.c_uint32),
        ("working_min", c.c_size_t),
        ("working_max", c.c_size_t),
        ("active_limit", c.c_uint32),
        ("affinity", c.c_size_t),
        ("priority", c.c_uint32),
        ("scheduling", c.c_uint32),
    ]


class _Limits(c.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", c.c_uint64 * 6),
        ("process_memory", c.c_size_t),
        ("job_memory", c.c_size_t),
        ("peak_process_memory", c.c_size_t),
        ("peak_job_memory", c.c_size_t),
    ]


class _Native:
    def __init__(self, spec, directory):
        import msvcrt

        _require(os.name == "nt" and c.sizeof(c.c_void_p) == 8, "native x64 Windows")
        _require(
            c.sizeof(_StartupEx) == 112
            and c.sizeof(_Accounting) == 48
            and c.sizeof(_Limits) == 144
            and _BasicLimits.affinity.offset == 48,
            "native ABI",
        )
        self.spec, self.directory = spec, directory
        self.stack = ExitStack()
        self.process = _Process()
        self.job = _Job()
        self.k = self.job.kernel
        self.completed = False
        self.port = None
        self.created_at = time.monotonic()
        self.events = []
        try:
            self.configure_api()
            self.port = self.k.CreateIoCompletionPort(c.c_void_p(-1), None, 0, 1)
            self.job.check(self.port, "private completion port")
            association = (c.c_void_p * 2)(1, self.port)
            self.job.check(
                self.k.SetInformationJobObject(
                    self.job.handle, 7, association, c.sizeof(association)
                ),
                "private job completion association",
            )
            streams = [
                self.stack.enter_context(open(os.devnull, "rb")),
                self.stack.enter_context((directory / "stdout.bin").open("xb")),
                self.stack.enter_context((directory / "stderr.bin").open("xb")),
            ]
            handles = (c.c_void_p * 3)(
                *(msvcrt.get_osfhandle(s.fileno()) for s in streams)
            )
            size = c.c_size_t()
            self.k.InitializeProcThreadAttributeList(None, 1, 0, c.byref(size))
            _require(size.value > 0, "attribute-list size")
            attributes = c.create_string_buffer(size.value)
            self.job.check(
                self.k.InitializeProcThreadAttributeList(
                    attributes, 1, 0, c.byref(size)
                ),
                "attribute-list initialization",
            )
            try:
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                self.job.check(
                    self.k.UpdateProcThreadAttribute(
                        attributes, 0, 0x20002, handles, c.sizeof(handles), None, None
                    ),
                    "explicit standard handle list",
                )
                startup = _StartupEx()
                startup.startup.cb = c.sizeof(startup)
                startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
                (
                    startup.startup.stdin,
                    startup.startup.stdout,
                    startup.startup.stderr,
                ) = handles
                startup.attributes = c.addressof(attributes)
                command = c.create_unicode_buffer(subprocess.list2cmdline(spec.command))
                environment = c.create_unicode_buffer(
                    "\x00".join(
                        f"{k}={v}"
                        for k, v in sorted(
                            spec.environment.items(), key=lambda p: p[0].upper()
                        )
                    )
                    + "\x00"
                )
                # Preserve hidden-console behavior. Its conhost is part of the
                # owned tree and must also exit; never detach or use breakaway.
                self.job.check(
                    self.k.CreateProcessW(
                        spec.command[0],
                        command,
                        None,
                        None,
                        True,
                        0x8000000 | 0x80000 | 0x400 | 0x4,
                        environment,
                        str(spec.cwd),
                        c.byref(startup),
                        c.byref(self.process),
                    ),
                    "CreateProcessW suspended",
                )
            finally:
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
                self.k.DeleteProcThreadAttributeList(attributes)
            self.identity = observation._process_times(
                self.process.process, self.process.pid
            )
            _save(directory / "suspended.json", self.identity)
            # Root code has never run; assignment failure cannot race a child spawn.
            self.job.assign(SimpleNamespace(_handle=self.process.process))
        except BaseException:
            cleanup = self.close()
            _save(directory / "launch-cleanup.json", cleanup)
            raise

    def configure_api(self):
        k = self.k
        signatures = {
            "InitializeProcThreadAttributeList": (
                [c.c_void_p, c.c_uint32, c.c_uint32, c.POINTER(c.c_size_t)],
                c.c_int,
            ),
            "UpdateProcThreadAttribute": (
                [
                    c.c_void_p,
                    c.c_uint32,
                    c.c_size_t,
                    c.c_void_p,
                    c.c_size_t,
                    c.c_void_p,
                    c.c_void_p,
                ],
                c.c_int,
            ),
            "DeleteProcThreadAttributeList": ([c.c_void_p], None),
            "CreateProcessW": (
                [
                    c.c_wchar_p,
                    c.c_wchar_p,
                    c.c_void_p,
                    c.c_void_p,
                    c.c_int,
                    c.c_uint32,
                    c.c_void_p,
                    c.c_wchar_p,
                    c.c_void_p,
                    c.c_void_p,
                ],
                c.c_int,
            ),
            "ResumeThread": ([c.c_void_p], c.c_uint32),
            "WaitForSingleObject": ([c.c_void_p, c.c_uint32], c.c_uint32),
            "GetExitCodeProcess": ([c.c_void_p, c.POINTER(c.c_uint32)], c.c_int),
            "TerminateProcess": ([c.c_void_p, c.c_uint32], c.c_int),
            "SetProcessDefaultCpuSets": (
                [c.c_void_p, c.POINTER(c.c_uint32), c.c_uint32],
                c.c_int,
            ),
            "GetProcessDefaultCpuSets": (
                [c.c_void_p, c.POINTER(c.c_uint32), c.c_uint32, c.POINTER(c.c_uint32)],
                c.c_int,
            ),
            "GetProcessAffinityMask": (
                [c.c_void_p, c.POINTER(c.c_size_t), c.POINTER(c.c_size_t)],
                c.c_int,
            ),
            "SetProcessInformation": (
                [c.c_void_p, c.c_int, c.c_void_p, c.c_uint32],
                c.c_int,
            ),
            "GetProcessInformation": (
                [c.c_void_p, c.c_int, c.c_void_p, c.c_uint32],
                c.c_int,
            ),
            "CreateIoCompletionPort": (
                [c.c_void_p, c.c_void_p, c.c_size_t, c.c_uint32],
                c.c_void_p,
            ),
            "GetQueuedCompletionStatus": (
                [
                    c.c_void_p,
                    c.POINTER(c.c_uint32),
                    c.POINTER(c.c_size_t),
                    c.POINTER(c.c_void_p),
                    c.c_uint32,
                ],
                c.c_int,
            ),
        }
        for name, (args, result) in signatures.items():
            function = getattr(k, name)
            function.argtypes, function.restype = args, result

    def configure(self):
        counts = windows.processor_group_counts()
        _require(
            len(counts) == 1 and self.spec.selected_cpu < counts[0],
            "one processor group and available CPU",
        )
        cpu = windows.selected_cpu_set(
            self.spec.selected_cpu, windows.enumerate_cpu_sets()
        )
        self.mask = 1 << self.spec.selected_cpu
        limits = _Limits()
        limits.basic.flags = 0x2010  # kill-on-close + affinity, NO breakaway
        limits.basic.affinity = self.mask
        self.job.check(
            self.k.SetInformationJobObject(
                self.job.handle, 9, c.byref(limits), c.sizeof(limits)
            ),
            "private job affinity",
        )
        ids = (c.c_uint32 * 1)(cpu["cpu_set_id"])
        self.job.check(
            self.k.SetProcessDefaultCpuSets(self.process.process, ids, 1),
            "root CPU set",
        )
        power = windows._PROCESS_POWER_THROTTLING_STATE(1, 1, 0)
        self.job.check(
            self.k.SetProcessInformation(
                self.process.process, 4, c.byref(power), c.sizeof(power)
            ),
            "root HighQoS",
        )
        observed = windows._PROCESS_POWER_THROTTLING_STATE(1, 0, 0)
        self.job.check(
            self.k.GetProcessInformation(
                self.process.process, 4, c.byref(observed), c.sizeof(observed)
            ),
            "read root HighQoS",
        )
        _require(
            (observed.Version, observed.ControlMask, observed.StateMask) == (1, 1, 0),
            "HighQoS changed",
        )
        mask, system = c.c_size_t(), c.c_size_t()
        self.job.check(
            self.k.GetProcessAffinityMask(
                self.process.process, c.byref(mask), c.byref(system)
            ),
            "root affinity readback",
        )
        _require(mask.value == self.mask, "effective root affinity changed")
        returned, observed_ids = c.c_uint32(), (c.c_uint32 * 64)()
        self.job.check(
            self.k.GetProcessDefaultCpuSets(
                self.process.process, observed_ids, 64, c.byref(returned)
            ),
            "root CPU set readback",
        )
        _require(
            returned.value == 1 and observed_ids[0] == ids[0], "root CPU set changed"
        )
        self.check_job_limits()
        return dict(
            affinity_mask=self.mask,
            cpu_set_id=ids[0],
            root_high_qos=True,
            job_limit_flags=0x2010,
            root_resumed=False,
            ancestor_quota_qualified=False,
            descendant_power_qualified=False,
        )

    def check_job_limits(self):
        limits = _Limits()
        self.job.check(
            self.k.QueryInformationJobObject(
                self.job.handle, 9, c.byref(limits), c.sizeof(limits), None
            ),
            "job limits readback",
        )
        _require(
            limits.basic.flags == 0x2010 and limits.basic.affinity == self.mask,
            "job placement or breakaway changed",
        )

    def resume(self):
        _require(
            time.monotonic() < self.created_at + self.spec.timeout_seconds,
            "pre-execution deadline",
        )
        _require(
            self.k.ResumeThread(self.process.thread) == 1, "exact single suspension"
        )

    def wait(self, timeout):
        self.deadline = self.created_at + timeout
        remaining = max(0, int((self.deadline - time.monotonic()) * 1000))
        status = self.k.WaitForSingleObject(self.process.process, remaining)
        if status == 258:
            raise TimeoutError("whole-process deadline")
        _require(status == 0, "root wait failed")
        code = c.c_uint32()
        self.job.check(
            self.k.GetExitCodeProcess(self.process.process, c.byref(code)),
            "root exit status",
        )
        return code.value

    def await_job_exit(self):
        # Process exit precedes console-host retirement. Await the whole job's
        # natural exit, not root-only exit or a name-based survivor exemption.
        # Windows does not guarantee these completion notifications. Recheck the
        # authoritative job count after bounded waits, without CPU-counter polling.
        # An expired deadline or an API error never becomes successful retirement.
        while True:
            remaining = int((self.deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                _save(self.directory / "survivors.json", self.job.snapshot())
                raise TimeoutError("whole-job exit deadline")
            if self.job.active() == 0:
                return
            milliseconds = min(remaining, 100)
            message, key, pid = c.c_uint32(), c.c_size_t(), c.c_void_p()
            ok = self.k.GetQueuedCompletionStatus(
                self.port, c.byref(message), c.byref(key), c.byref(pid), milliseconds
            )
            if not ok:
                error = c.get_last_error()
                if error != 258:  # WAIT_TIMEOUT, not a broken completion port
                    raise OSError(error, "whole-job completion unavailable")
                self.events.append(
                    dict(
                        kind="wait-timeout",
                        wait_milliseconds=milliseconds,
                        observed_ns=time.perf_counter_ns(),
                    )
                )
            else:
                _require(key.value == 1, "private completion key")
                self.events.append(
                    dict(
                        kind="completion-wakeup",
                        message=message.value,
                        pid=pid.value,
                        wait_milliseconds=milliseconds,
                        observed_ns=time.perf_counter_ns(),
                    )
                )
            _require(len(self.events) <= 100_000, "bounded lifecycle event count")

    def finish(self):
        self.check_job_limits()
        try:
            self.await_job_exit()
        finally:
            _save(self.directory / "lifecycle-wakeups.json", self.events)
        self.check_job_limits()
        row = _Accounting()
        begin = time.perf_counter_ns()
        self.job.check(
            self.k.QueryInformationJobObject(
                self.job.handle, 1, c.byref(row), c.sizeof(row), None
            ),
            "final whole-job accounting",
        )
        if row.active:
            _save(self.directory / "survivors.json", self.job.snapshot())
        result = dict(
            query_begin_ns=begin,
            query_end_ns=time.perf_counter_ns(),
            user_100ns=row.user,
            kernel_100ns=row.kernel,
            total_processes=row.total,
            active_processes=row.active,
            limit_terminated_processes=row.terminated,
        )
        exited = observation._process_times(self.process.process, self.process.pid)
        _require(
            exited["birth"] == self.identity["birth"] and exited["exited_before_query"],
            "retained root identity and exit",
        )
        _save(self.directory / "root-exit.json", exited)
        _require(
            time.monotonic() < self.deadline, "whole-job final verification deadline"
        )
        self.completed = row.active == 0
        return result

    def close(self):
        cleanup = {"quiescent": False}
        try:
            if self.completed:
                _require(self.job.active() == 0, "job no longer empty")
                self.job.close()
                cleanup = {"quiescent": True, "terminated": False}
            else:
                # Also handles a suspended root for which assignment failed.
                if (
                    self.process.process
                    and self.k.WaitForSingleObject(self.process.process, 0) == 258
                ):
                    self.job.check(
                        self.k.TerminateProcess(self.process.process, 124),
                        "terminate exact owned root",
                    )
                cleanup = self.job.cancel()
                if self.process.process:
                    _require(
                        self.k.WaitForSingleObject(self.process.process, 30000) == 0,
                        "owned root cleanup timeout",
                    )
        finally:
            for handle in (self.process.thread, self.process.process):
                if handle:
                    self.job.check(
                        self.k.CloseHandle(handle), "close owned process handle"
                    )
            if self.port:
                self.job.check(
                    self.k.CloseHandle(self.port), "close private completion port"
                )
            self.stack.close()
        return cleanup
