"""Pinned, explicitly approved ordinary-token native owner launch lifecycle.

This module never changes a job, token, security setting or performance policy.
The approved caller's existing job must permit detachment. The worker must call
require_independent_owner before work; source/one-use/conditioning guards belong
to the reviewed worker and are not replaced by this lifecycle check.
"""

from __future__ import annotations

import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Mapping


NATIVE_PYTHON = Path("C:/Python313/python.exe")
_KILL_ON_CLOSE = 0x2000
_BREAKAWAY_OK = 0x0800
_BREAKAWAY_CREATE = 0x01000000
_NO_WINDOW = 0x08000000


class NativeOwnerError(RuntimeError):
    """A launch context or evidence binding cannot be established safely."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", ctypes.c_uint32),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_uint32),
        ("scheduling_class", ctypes.c_uint32),
    ]


def lifecycle_context() -> dict[str, object]:
    """Read only this process's token and immediate job; never modify either."""
    if platform.system() != "Windows" or sys.maxsize <= 2**32:
        raise NativeOwnerError("Native 64-bit Windows required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.IsProcessInJob.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32),
    ]
    kernel.QueryInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    member = ctypes.c_int32()
    if not kernel.IsProcessInJob(
        kernel.GetCurrentProcess(), None, ctypes.byref(member)
    ):
        raise NativeOwnerError(f"IsProcessInJob failed: {ctypes.get_last_error()}")
    flags = None
    if member.value:
        limits = _BasicLimits()
        length = ctypes.c_uint32()
        if not kernel.QueryInformationJobObject(
            None, 2, ctypes.byref(limits), ctypes.sizeof(limits), ctypes.byref(length)
        ):
            raise NativeOwnerError(f"Job query failed: {ctypes.get_last_error()}")
        if ctypes.sizeof(limits) != 64 or length.value != 64:
            raise NativeOwnerError("Unexpected native job query layout")
        flags = int(limits.flags)
    return dict(
        platform="windows",
        administrator=bool(shell.IsUserAnAdmin()),
        in_job=bool(member.value),
        job_limit_flags=flags,
    )


def creation_flags(
    context: Mapping[str, object], *, approved_native_launch: bool
) -> int:
    """Fail closed unless explicit launch approval and existing OS permission agree."""
    if type(approved_native_launch) is not bool or not approved_native_launch:
        raise NativeOwnerError("Explicit approved native launch required")
    if set(context) != {"platform", "administrator", "in_job", "job_limit_flags"}:
        raise NativeOwnerError("Incomplete or ambiguous lifecycle context")
    if context["platform"] != "windows" or type(context["administrator"]) is not bool:
        raise NativeOwnerError("Invalid native token context")
    if context["administrator"] or type(context["in_job"]) is not bool:
        raise NativeOwnerError("Ordinary token and known job membership required")
    flags = context["job_limit_flags"]
    if not context["in_job"]:
        if flags is not None:
            raise NativeOwnerError("Inconsistent absent-job limits")
        return _NO_WINDOW
    if type(flags) is not int or flags < 0:
        raise NativeOwnerError("Unknown job limits")
    if not flags & _BREAKAWAY_OK or flags & ~(_BREAKAWAY_OK | _KILL_ON_CLOSE):
        raise NativeOwnerError("Job disallows detachment or imposes other constraints")
    return _NO_WINDOW | _BREAKAWAY_CREATE


def require_independent_owner(
    context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Worker-side check, before any acquisition; rejects nested inherited jobs too."""
    observed = lifecycle_context() if context is None else dict(context)
    creation_flags(observed, approved_native_launch=True)
    if observed["in_job"]:
        raise NativeOwnerError("Worker still belongs to an inherited job")
    return observed


def _exclusive_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def launch_retained_python_owner(
    *,
    script: Path,
    script_sha256: str,
    root: Path,
    evidence_prefix: Path,
    approved_native_launch: bool,
) -> dict[str, object]:
    """Launch one pinned hidden Python owner, with exclusive lifecycle receipts.

    No shell or arbitrary arguments are accepted. The returned launch receipt is
    not a producer terminal, performance result or certification acceptance.
    """
    context = lifecycle_context()
    flags = creation_flags(context, approved_native_launch=approved_native_launch)
    root = root.resolve(strict=True)
    tools = (root / "target/codex-tools").resolve(strict=True)
    script = script.resolve(strict=True)
    evidence_prefix = evidence_prefix.resolve()
    if not script.is_relative_to(tools) or script.suffix != ".py":
        raise NativeOwnerError(
            "Reviewed Python script must be confined to target/codex-tools"
        )
    if not evidence_prefix.is_relative_to(tools) or not evidence_prefix.name:
        raise NativeOwnerError(
            "Lifecycle evidence must be confined to target/codex-tools"
        )
    if Path(sys.executable).resolve() != NATIVE_PYTHON.resolve():
        raise NativeOwnerError("Exact native Python executable required")
    actual = hashlib.sha256(script.read_bytes()).hexdigest()
    if type(script_sha256) is not str or actual != script_sha256:
        raise NativeOwnerError("Reviewed script byte identity mismatch")
    outputs = {
        key: Path(str(evidence_prefix) + suffix)
        for key, suffix in {
            "launch": ".lifecycle-launch.json",
            "stdout": ".launcher.stdout.log",
            "stderr": ".launcher.stderr.log",
        }.items()
    }
    if any(path.exists() for path in outputs.values()):
        raise NativeOwnerError(
            "Consumed lifecycle evidence prefix; never retry or overwrite"
        )
    receipt = dict(
        status="launch-failed",
        source_root=str(root),
        script=str(script),
        script_sha256=actual,
        launcher_pid=os.getpid(),
        child_pid=None,
        launcher_context=context,
        creation_flags=flags,
        approved_native_launch=True,
        security_settings_changed=False,
        administrator_token_requested=False,
        worker_independent_check_required=True,
        producer_terminal=False,
        authoritative=False,
        certification_eligible=False,
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    # The exclusive stdout creation claims this prefix before any child starts.
    try:
        with (
            outputs["stdout"].open("xb") as stdout,
            outputs["stderr"].open("xb") as stderr,
        ):
            child = subprocess.Popen(
                [str(NATIVE_PYTHON), str(script)],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=flags,
            )
        receipt.update(status="launched-not-completed", child_pid=child.pid)
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        _exclusive_json(outputs["launch"], receipt)
        raise
    _exclusive_json(outputs["launch"], receipt)
    return receipt
