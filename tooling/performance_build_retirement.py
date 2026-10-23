"""Fail-closed retirement policy for an already successful prerequisite build.

The native adapter must own a new, private job and supply fresh observations of
that exact job. This policy is not a process-ownership proof, an independent
owner launcher, performance admission, or certification authority. Failure
cleanup remains the adapter's responsibility; a failure receipt is never a pass.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import re
import time
from typing import Callable, Mapping


class RetirementError(RuntimeError):
    """A failed retirement together with every observation already captured."""

    def __init__(self, receipt: dict[str, object]):
        super().__init__(str(receipt["error"]))
        self.receipt = receipt


def _require(value: object, message: str) -> None:
    if not value:
        raise ValueError(message)


def _file(path: Path) -> dict[str, object]:
    _require(
        path.is_absolute()
        and path.resolve() == path
        and not path.is_symlink()
        and path.is_file(),
        "exact absolute regular file required",
    )
    size = path.stat().st_size
    _require(size > 0, "nonempty required file")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": size, "sha256": digest}


def _artifacts(paths: Mapping[str, Path]) -> dict[str, object]:
    _require(bool(paths), "nonempty required artifact inventory")
    _require(
        all(
            isinstance(name, str) and name and isinstance(path, Path)
            for name, path in paths.items()
        ),
        "explicit named artifact paths",
    )
    return {name: _file(path) for name, path in paths.items()}


def _approvals(images: Mapping[str, str]) -> dict[Path, str]:
    result = {}
    for name, pin in images.items():
        _require(isinstance(name, str) and isinstance(pin, str), "typed image pin")
        path = Path(name)
        _require(
            path.name.casefold() == "vctip.exe",
            "only explicitly pinned compiler helper",
        )
        _require(re.fullmatch(r"[0-9a-f]{64}", pin), "exact SHA256 approval")
        _require(_file(path)["sha256"] == pin, "approved compiler image bytes changed")
        _require(path not in result, "unique canonical compiler image")
        result[path] = pin
    return result


def _validate_snapshot(value: dict[str, object]) -> list[dict[str, object]]:
    _require(isinstance(value, dict), "structured native snapshot")
    counts = [
        value.get(name) for name in ("active_accounting", "assigned", "populated")
    ]
    _require(
        all(type(n) is int and n >= 0 for n in counts),
        "exact nonnegative native counts",
    )
    pids, rows = value.get("pids"), value.get("processes")
    _require(isinstance(pids, list) and isinstance(rows, list), "complete native lists")
    _require(all(type(pid) is int and pid > 0 for pid in pids), "positive integer PIDs")
    _require(len(set(pids)) == len(pids), "unique PID list")
    _require(
        counts[0] == counts[1] == counts[2] == len(pids) == len(rows),
        "inconsistent or truncated native observation",
    )
    _require(
        all(isinstance(row, dict) for row in rows), "structured process observations"
    )
    _require(
        [row.get("pid") for row in rows] == pids,
        "process observations match complete PID list",
    )
    return rows


def retire_after_success(
    *,
    build_passed: bool,
    required_artifacts: Mapping[str, Path],
    approved_background_images: Mapping[str, str],
    snapshot: Callable[[], dict[str, object]],
    terminate: Callable[[], object],
    close: Callable[[], object],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], object] = time.sleep,
    drain_seconds: float = 5.0,
    poll_seconds: float = 0.1,
) -> dict[str, object]:
    """Retire only pinned owned compiler helpers; verify empty job and stable files.

    The caller supplies the command's actual success and complete required output
    inventory. Native callbacks must fail on unsuccessful API returns. Queries
    are not atomic: any inconsistent observation fails, never implies emptiness.
    No polling retries a build, changes a result, or admits a performance sample.
    """
    observations: list[dict[str, object]] = []
    receipt: dict[str, object] = {
        "status": "failed",
        "authoritative": False,
        "action": "none",
        "snapshots": observations,
        "termination_called": False,
        "close_called": False,
    }
    started = monotonic()
    try:
        _require(build_passed is True, "actual successful build required")
        _require(
            type(drain_seconds) in (float, int)
            and type(poll_seconds) in (float, int)
            and 0 < poll_seconds <= drain_seconds <= 30,
            "finite bounded retirement polling",
        )
        approvals = _approvals(approved_background_images)
        receipt["artifacts_before"] = _artifacts(required_artifacts)

        def observe() -> list[dict[str, object]]:
            value = copy.deepcopy(snapshot())
            observations.append(value)
            return _validate_snapshot(value)

        rows = observe()
        if rows:
            for row in rows:
                _require(
                    row.get("same_owned_job") is True
                    and row.get("exited_before_query") is False
                    and isinstance(row.get("birth"), str)
                    and re.fullmatch(r"[1-9][0-9]*", row["birth"])
                    and not any(key in row for key in ("open_error", "image_error")),
                    "live birth-identified membership in exact owned job required",
                )
                image = row.get("image")
                _require(isinstance(image, str), "exact image path required")
                path = Path(image)
                _require(path in approvals, "unknown surviving process image")
                _require(
                    _file(path)["sha256"] == approvals[path],
                    "live compiler image pin changed",
                )
            receipt["action"] = "owned-compiler-background-cleanup"
            receipt["termination_called"] = True
            terminate()
            deadline = monotonic() + drain_seconds
            while True:
                sleep(poll_seconds)
                rows = observe()
                if not rows:
                    break
                _require(
                    monotonic() < deadline, "owned job did not drain before deadline"
                )
        else:
            receipt["action"] = "already-empty"
        receipt["artifacts_after"] = _artifacts(required_artifacts)
        _require(
            receipt["artifacts_after"] == receipt["artifacts_before"],
            "required artifact bytes changed during retirement",
        )
        receipt["close_called"] = True
        close()
        receipt["status"] = "passed"
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise RetirementError(receipt) from error
    finally:
        receipt["elapsed_seconds"] = monotonic() - started
    return receipt
