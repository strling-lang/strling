"""Bounded Windows prerequisite builds with private child ownership.

This is execution machinery, not measurement admission or an independent-owner
qualification. No inherited job, host setting, sample or performance budget is
modified. Each invocation retains its own raw logs and terminal receipt.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
import json
import locale
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

from tooling import performance_build_retirement as retirement
from tooling import performance_process_observation as observation
from tooling import performance_windows

ROOT = Path(__file__).resolve().parents[1]
# Reviewed MSVC 14.44.35207 Hostx64/x64 compiler helper, not a name-only rule.
# New image bytes require a reviewed source change and fresh lifecycle proof.
VCTIP_SHA256 = "b52c617b17083cdc8ecbaedb1aee6bd08ed323308230eebef05d02747e36b00b"


@dataclass(frozen=True)
class Build:
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    artifacts: dict[str, Path]
    timeout_seconds: int = 1800


def _require(value: object, message: str) -> None:
    if not value:
        raise ValueError(message)


def _save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validate(specs: list[Build]) -> None:
    _require(1 <= len(specs) <= 3, "one to three explicitly declared builds")
    outputs: set[Path] = set()
    commands = set()
    for spec in specs:
        _require(isinstance(spec, Build), "typed build specification")
        _require(
            isinstance(spec.command, tuple)
            and bool(spec.command)
            and all(isinstance(s, str) and s for s in spec.command),
            "explicit command",
        )
        _require(spec.command not in commands, "unique build commands")
        commands.add(spec.command)
        _require(spec.cwd.is_absolute() and spec.cwd.is_dir(), "absolute existing cwd")
        _require(
            type(spec.timeout_seconds) is int and 0 < spec.timeout_seconds <= 1800,
            "bounded command timeout",
        )
        _require(
            isinstance(spec.environment, dict)
            and all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in spec.environment.items()
            ),
            "explicit process environment",
        )
        _require(bool(spec.artifacts), "complete required artifact inventory")
        for role, path in spec.artifacts.items():
            _require(
                isinstance(role, str)
                and role
                and isinstance(path, Path)
                and path.is_absolute(),
                "named absolute artifact",
            )
            resolved = path.resolve()
            _require(resolved not in outputs, "independent build outputs")
            outputs.add(resolved)


def execute(
    specs: list[Build],
    directory: Path,
    *,
    launch: Callable | None = None,
    monotonic: Callable = time.monotonic,
    sleep: Callable = time.sleep,
) -> tuple[str, dict]:
    """Launch once, observe incrementally, cancel peers on failure, retain order.

    NativeBuild owns cleanup even when construction fails. A returned worker's
    cancel method must be idempotent and report quiescence; an exception never
    prevents cleanup of the remaining workers. The directory is exclusive.
    """
    _validate(specs)
    directory.mkdir(exist_ok=False)
    launch = NativeBuild if launch is None else launch
    started = monotonic()
    rows = [
        {"command": list(s.command), "status": "incomplete", "return_code": None}
        for s in specs
    ]
    result = {
        "status": "failed",
        "schedule": "concurrent-owned-windows-v1",
        "steps": rows,
        "cleanup": [],
        "receipt_directory": str(directory),
    }
    workers = []
    _save(
        directory / "plan.json",
        {
            "commands": [
                dict(
                    command=list(s.command),
                    cwd=str(s.cwd),
                    timeout_seconds=s.timeout_seconds,
                    artifacts={k: str(v) for k, v in s.artifacts.items()},
                    environment_sha256=hashlib.sha256(
                        json.dumps(s.environment, sort_keys=True).encode()
                    ).hexdigest(),
                )
                for s in specs
            ],
            "implementation_sha256": _digest(Path(__file__)),
            "retirement_sha256": _digest(Path(retirement.__file__)),
            "process_observation_sha256": _digest(Path(observation.__file__)),
            "approved_compiler_helper_sha256": VCTIP_SHA256,
        },
    )
    try:
        for index, spec in enumerate(specs):
            began = monotonic()
            try:
                worker = launch(spec, directory / str(index))
            except BaseException as error:
                rows[index].update(
                    status="failed", error=f"{type(error).__name__}: {error}"
                )
                raise
            workers.append((index, worker, began))
        pending = list(workers)
        while pending:
            for index, worker, began in list(pending):
                if monotonic() - began > specs[index].timeout_seconds + 60:
                    rows[index].update(status="failed", error="worker envelope timeout")
                    raise TimeoutError("worker envelope timeout")
                row = worker.poll()
                if row is None:
                    continue
                _require(
                    isinstance(row, dict)
                    and row.get("status") in ("passed", "failed", "unavailable"),
                    "explicit worker terminal status",
                )
                rows[index] = {**row, "command": list(specs[index].command)}
                pending.remove((index, worker, began))
                if row["status"] != "passed":
                    result["status"] = row["status"]
                    raise RuntimeError(f"build {index} failed; cancel owned peers")
            if pending:
                sleep(0.1)
        result["status"] = "passed"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        for index, worker, _ in workers:
            try:
                cleanup = worker.cancel()
                _require(
                    cleanup.get("quiescent") is True, "owned child quiescence required"
                )
                result["cleanup"].append({"index": index, **cleanup})
            except BaseException as error:
                result["status"] = "failed"
                result["cleanup"].append(
                    {
                        "index": index,
                        "quiescent": False,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        result["duration_ms"] = int((monotonic() - started) * 1000)
        _save(directory / "terminal.json", result)
    return result["status"], result


class _Job:
    """A new unnamed x64 Windows job; never mutate the caller's job."""

    def __init__(self):
        _require(
            os.name == "nt" and ctypes.sizeof(ctypes.c_void_p) == 8,
            "native x64 Windows required",
        )
        self.kernel = k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        k.CreateJobObjectW.restype = ctypes.c_void_p
        k.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.QueryInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        k.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        k.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = k.CreateJobObjectW(None, None)
        self.check(self.handle, "CreateJobObjectW")
        try:
            limits = ctypes.create_string_buffer(144)
            ctypes.c_uint32.from_buffer(limits, 16).value = 0x2000
            self.check(
                k.SetInformationJobObject(self.handle, 9, limits, 144),
                "SetInformationJobObject",
            )
        except BaseException:
            self.close()
            raise

    @staticmethod
    def check(value, action):
        if not value:
            raise OSError(ctypes.get_last_error(), action)

    def assign(self, process):
        self.check(
            self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)),
            "AssignProcessToJobObject",
        )
        member = ctypes.c_int32()
        self.check(
            self.kernel.IsProcessInJob(
                int(process._handle), self.handle, ctypes.byref(member)
            ),
            "IsProcessInJob",
        )
        _require(member.value, "exact new worker belongs to private job")

    def active(self):
        data = ctypes.create_string_buffer(48)
        self.check(
            self.kernel.QueryInformationJobObject(self.handle, 1, data, 48, None),
            "job accounting",
        )
        return ctypes.c_uint32.from_buffer(data, 40).value

    def snapshot(self):
        k = self.kernel
        start = time.perf_counter_ns()
        active = self.active()
        data = ctypes.create_string_buffer(8 + 128 * ctypes.sizeof(ctypes.c_size_t))
        self.check(
            k.QueryInformationJobObject(self.handle, 3, data, len(data), None),
            "complete job PID query",
        )
        assigned = ctypes.c_uint32.from_buffer(data, 0).value
        populated = ctypes.c_uint32.from_buffer(data, 4).value
        _require(
            assigned == populated and populated <= 128, "complete bounded job list"
        )
        pids = [
            ctypes.c_size_t.from_buffer(data, 8 + i * 8).value for i in range(populated)
        ]
        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.OpenProcess.restype = ctypes.c_void_p
        k.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        rows = []
        for pid in pids:
            handle = k.OpenProcess(0x101000, False, pid)
            if not handle:
                rows.append({"pid": pid, "open_error": ctypes.get_last_error()})
                continue
            try:
                member = ctypes.c_int32()
                self.check(
                    k.IsProcessInJob(handle, self.handle, ctypes.byref(member)),
                    "exact job membership",
                )
                row = observation._process_times(handle, pid)
                row["same_owned_job"] = bool(member.value)
                image = ctypes.create_unicode_buffer(32768)
                size = ctypes.c_uint32(len(image))
                if k.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                    row["image"] = image.value
                else:
                    row["image_error"] = ctypes.get_last_error()
                rows.append(row)
            finally:
                self.check(k.CloseHandle(handle), "close observation handle")
        return dict(
            query_start_ns=start,
            query_end_ns=time.perf_counter_ns(),
            active_accounting=active,
            assigned=assigned,
            populated=populated,
            pids=pids,
            processes=rows,
            queries_not_atomic=True,
        )

    def terminate(self):
        self.check(
            self.kernel.TerminateJobObject(self.handle, 124), "terminate own job"
        )

    def close(self):
        if self.handle is not None:
            self.check(self.kernel.CloseHandle(self.handle), "close own job")
            self.handle = None

    def cancel(self):
        if self.handle is None:
            return {"quiescent": True, "already_closed": True}
        snapshots = []
        try:
            self.terminate()
            deadline = time.monotonic() + 30
            while True:
                snapshot = self.snapshot()
                snapshots.append(snapshot)
                rows = retirement._validate_snapshot(snapshot)
                if not rows:
                    return {"quiescent": True, "snapshots": snapshots}
                _require(time.monotonic() < deadline, "failure cleanup drain deadline")
                time.sleep(0.1)
        finally:
            # Closing is unconditional containment; only a verified empty query
            # above supplies quiescence, never this last-resort close itself.
            self.close()


class NativeBuild:
    def __init__(self, spec: Build, directory: Path):
        self.spec, self.directory = spec, directory
        directory.mkdir(exist_ok=False)
        self.process = None
        self.job = _Job()
        self.finished = None
        self.cleanup = None
        try:
            with (
                (directory / "worker.stdout.log").open("xb") as stdout,
                (directory / "worker.stderr.log").open("xb") as stderr,
            ):
                self.process = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "tooling.performance_build_execution",
                        "--worker",
                        str(directory),
                    ],
                    cwd=ROOT,
                    stdin=subprocess.PIPE,
                    stdout=stdout,
                    stderr=stderr,
                    env=spec.environment,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            # The worker cannot start a command until stdin is authorized. No
            # child can race job assignment, including on assignment failure.
            self.job.assign(self.process)
            self.identity = observation._process_times(
                int(self.process._handle), self.process.pid
            )
            request = dict(
                command=list(spec.command),
                cwd=str(spec.cwd),
                timeout_seconds=spec.timeout_seconds,
                owner=self.identity,
            )
            _save(directory / "owner.json", self.identity)
            _save(directory / "request.json", request)
            # Only one byte crosses the pipe; a large environment must never
            # block the supervisor before it can enforce its deadline. The
            # environment is inherited, hashed in the plan, never logged.
            self.process.stdin.write(b"1")
            self.process.stdin.close()
        except BaseException as error:
            cleanup_errors = []
            try:
                self.job.cancel()
            except BaseException as cleanup:
                cleanup_errors.append(f"{type(cleanup).__name__}: {cleanup}")
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        self.process.kill()  # Exact unreleased worker handle only.
                    self.process.wait(timeout=30)
                except BaseException as cleanup:
                    cleanup_errors.append(f"{type(cleanup).__name__}: {cleanup}")
            _save(
                directory / "launch-failure.json",
                dict(
                    error=f"{type(error).__name__}: {error}",
                    cleanup_errors=cleanup_errors,
                ),
            )
            raise

    def poll(self):
        if self.finished is not None:
            return self.finished
        if self.process.poll() is None:
            return None
        self.process.wait(timeout=30)
        row = {
            "status": "failed",
            "worker": self.identity,
            "worker_return_code": self.process.returncode,
        }
        try:
            raw = json.loads((self.directory / "result.json").read_bytes())
            _require(
                raw.get("command") == list(self.spec.command), "worker command binding"
            )
            _require(raw.get("owner") == self.identity, "worker birth identity binding")
            row.update(raw)
            if raw.get("status") == "unavailable" and self.process.returncode == 2:
                row["status"] = "unavailable"
            elif (
                self.process.returncode != 0
                or raw.get("return_code") != 0
                or raw.get("status") != "passed"
            ):
                row["status"] = "failed"
            else:
                missing = [
                    str(p)
                    for p in self.spec.artifacts.values()
                    if not p.is_file() or p.is_symlink() or p.stat().st_size == 0
                ]
                if missing:
                    row.update(
                        status="failed",
                        code="missing-release-artifacts",
                        missing_artifacts=missing,
                    )
                else:
                    first = self.job.snapshot()
                    # Approval bytes are fixed before execution, never derived
                    # from the observed image. The retirement policy rechecks
                    # exact path, hash, birth identity and owned membership.
                    approvals = {
                        r["image"]: VCTIP_SHA256
                        for r in first["processes"]
                        if isinstance(r.get("image"), str)
                        and Path(r["image"]).name.casefold() == "vctip.exe"
                    }
                    snapshots = [first]
                    row["retirement"] = retirement.retire_after_success(
                        build_passed=True,
                        required_artifacts=self.spec.artifacts,
                        approved_background_images=approvals,
                        snapshot=lambda: (
                            snapshots.pop() if snapshots else self.job.snapshot()
                        ),
                        terminate=self.job.terminate,
                        close=self.job.close,
                    )
        except retirement.RetirementError as error:
            row.update(status="failed", error=str(error), retirement=error.receipt)
        except BaseException as error:
            row.update(status="failed", error=f"{type(error).__name__}: {error}")
        _save(self.directory / "observed.json", row)
        self.finished = row
        return row

    def cancel(self):
        if self.cleanup is not None:
            return self.cleanup
        row = {"quiescent": False}
        try:
            row.update(self.job.cancel())
            self.process.wait(timeout=30)
            row["worker_exit"] = observation._process_times(
                int(self.process._handle), self.process.pid
            )
            _require(row["worker_exit"]["exited_before_query"], "worker exit required")
        except BaseException as error:
            row.update(quiescent=False, error=f"{type(error).__name__}: {error}")
            raise
        finally:
            _save(self.directory / "cleanup.json", row)
            self.cleanup = row
        return row


def _worker(directory: Path) -> int:
    # EOF without a complete authorization is a failure before any build starts.
    _require(sys.stdin.buffer.read(1) == b"1", "parent job assignment authorization")
    request = json.loads((directory / "request.json").read_bytes())
    owner = request["owner"]
    current = observation._process_times(
        performance_windows._current_process_handle(), os.getpid()
    )
    _require(
        (current["pid"], current["birth"]) == (owner["pid"], owner["birth"]),
        "exact authorized worker",
    )
    row = {
        "owner": owner,
        "command": request["command"],
        "status": "failed",
        "return_code": None,
    }
    started = time.monotonic()
    try:
        row["power_policy"] = performance_windows.enforce_current_process_power_policy()
        with (
            (directory / "command.stdout.log").open("xb") as stdout,
            (directory / "command.stderr.log").open("xb") as stderr,
        ):
            row["launch_ns"] = time.perf_counter_ns()
            child = subprocess.Popen(
                request["command"],
                cwd=request["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            row["child"] = observation._process_times(int(child._handle), child.pid)
            _save(directory / "child.json", row["child"])
            row["return_code"] = child.wait(timeout=request["timeout_seconds"])
            row["return_ns"] = time.perf_counter_ns()
            row["child_exit"] = observation._process_times(
                int(child._handle), child.pid
            )
        row["status"] = "passed" if row["return_code"] == 0 else "failed"
    except FileNotFoundError as error:
        row.update(status="unavailable", error=f"{type(error).__name__}: {error}")
    except BaseException as error:
        row["error"] = f"{type(error).__name__}: {error}"
    row["duration_ms"] = int((time.monotonic() - started) * 1000)
    logs = [directory / f"command.{s}.log" for s in ("stdout", "stderr")]
    row["logs"] = {
        p.name: {"sha256": _digest(p), "bytes": p.stat().st_size}
        for p in logs
        if p.exists()
    }
    output = "".join(
        p.read_text(encoding=locale.getpreferredencoding(False), errors="replace")
        for p in logs
        if p.exists()
    )
    row["output_sha256"] = hashlib.sha256(output.encode()).hexdigest()
    if row["status"] != "passed":
        row["output_tail"] = output[-4000:]
    _save(directory / "result.json", row)
    return {"passed": 0, "failed": 1, "unavailable": 2}[row["status"]]


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit("internal owned build worker only")
    raise SystemExit(_worker(Path(sys.argv[2])))
