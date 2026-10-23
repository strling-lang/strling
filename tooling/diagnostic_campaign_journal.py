"""One-use checkpoints for prospectively fixed, sample-free diagnostics.

This module does not launch work, qualify a host or grant evidence authority.
Callers retain source leases, timing, bounded waits, child supervision and raw
result verification. Yield only BETWEEN sealed units, never inside a unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class JournalError(ValueError):
    """Incomplete, consumed, contradictory or unbound diagnostic state."""


def _require(condition, message):
    if not condition:
        raise JournalError(message)


def canonical_bytes(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _hex(value, length=64):
    _require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value),
        "invalid exact digest",
    )


def _integer(value, *, minimum=0, maximum=2**63 - 1):
    _require(
        type(value) is int and minimum <= value <= maximum, "invalid exact integer"
    )


def _pins(value):
    expected = {
        "source_sha",
        "source_tree",
        "recipe_sha256",
        "implementation_sha256",
        "environment_sha256",
    }
    _require(type(value) is dict and set(value) == expected, "invalid pin denominator")
    for key, pin in value.items():
        _hex(pin, 40 if key in ("source_sha", "source_tree") else 64)


def _owner(value):
    _require(type(value) is dict and set(value) == {"pid", "birth"}, "invalid owner")
    _integer(value["pid"], minimum=1, maximum=2**32 - 1)
    birth = value["birth"]
    _require(
        type(birth) is str
        and re.fullmatch(r"[1-9][0-9]{0,19}", birth)
        and int(birth) < 2**64,
        "invalid owner birth",
    )


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value):
    _require(type(value) is str and value.endswith("Z"), "UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise JournalError("invalid UTC timestamp") from error
    _require(parsed.tzinfo == timezone.utc, "invalid UTC timestamp")


def _plan(value):
    _require(
        type(value) is dict
        and set(value)
        == {
            "version",
            "kind",
            "authoritative",
            "certification_eligible",
            "pins",
            "units",
        },
        "invalid plan fields",
    )
    _require(
        type(value["version"]) is int
        and value["version"] == 1
        and value["kind"] == "session-bound-sample-free-diagnostic"
        and value["authoritative"] is False
        and value["certification_eligible"] is False,
        "diagnostic-only plan required",
    )
    _pins(value["pins"])
    units = value["units"]
    _require(
        type(units) is list and 1 <= len(units) <= 9999, "invalid unit denominator"
    )
    ids = []
    for unit in units:
        _require(
            type(unit) is dict and set(unit) == {"id", "maximum_elapsed_ns"},
            "invalid unit",
        )
        _require(
            type(unit["id"]) is str
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", unit["id"]),
            "invalid unit identity",
        )
        _integer(unit["maximum_elapsed_ns"], minimum=1)
        ids.append(unit["id"])
    _require(len(set(ids)) == len(ids), "duplicate unit identity")


def _safe(path):
    """Reject filesystem aliases before reading or creating receipts."""
    _require(
        path.is_absolute() and path.resolve() == path,
        "unaliased absolute path required",
    )
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        _require(
            not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400,
            "reparse/symlink receipt path",
        )
    if path.exists():
        info = path.stat()
        _require(
            stat.S_ISDIR(info.st_mode)
            or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
            "regular single-link receipt required",
        )


def _write(path, value):
    # Serialize first. A crash during exclusive writing leaves a consumed,
    # invalid receipt, not a hole that a later caller may fill or overwrite.
    raw = canonical_bytes(value)
    _safe(path)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise JournalError(
            f"cannot claim exclusive receipt {path.name}: {error}"
        ) from error
    return _digest(raw)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate JSON field")
        value[key] = item
    return value


def _read(path):
    _safe(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_pairs)
        _require(raw == canonical_bytes(value), "noncanonical receipt")
    except (OSError, ValueError, TypeError) as error:
        raise JournalError(f"unreadable receipt {path.name}: {error}") from error
    return value, _digest(raw)


def create(path: Path, plan: dict) -> str:
    """Create a fresh fixed plan. Return its hash for an external checkpoint."""
    _plan(plan)
    _safe(path)
    try:
        path.mkdir(exist_ok=False)
    except OSError as error:
        raise JournalError(
            f"campaign namespace already consumed/unavailable: {error}"
        ) from error
    return _write(path / "plan.json", plan)


def _failures(terminal, plan, index):
    failures = []
    if terminal["observed_pins"] != plan["pins"]:
        failures.append("pin-drift")
    if terminal["elapsed_ns"] > plan["units"][index]["maximum_elapsed_ns"]:
        failures.append("elapsed-bound")
    if not terminal["children_quiescent"]:
        failures.append("children-not-quiescent")
    return failures


def _scan(path, expected_plan_sha256):
    _hex(expected_plan_sha256)
    plan, plan_hash = _read(path / "plan.json")
    _plan(plan)
    _require(plan_hash == expected_plan_sha256, "plan pin mismatch")
    allowed = {"plan.json"} | {
        f"{i:04d}.{kind}.json"
        for i in range(len(plan["units"]))
        for kind in ("claim", "terminal")
    }
    names = {p.name for p in path.iterdir()}
    _require(names <= allowed, "unexpected receipt/denominator")
    previous = plan_hash
    completed = 0
    disposition = "complete"
    stopped = False
    for index, unit in enumerate(plan["units"]):
        claim_path = path / f"{index:04d}.claim.json"
        terminal_path = path / f"{index:04d}.terminal.json"
        has_claim, has_terminal = claim_path.name in names, terminal_path.name in names
        if stopped:
            _require(
                not has_claim and not has_terminal,
                "receipt after unsealed/failed prefix",
            )
            continue
        if not has_claim:
            _require(not has_terminal, "terminal without claim")
            disposition, stopped = "ready", True
            continue
        claimed, claim_hash = _read(claim_path)
        _require(
            type(claimed) is dict
            and set(claimed)
            == {
                "index",
                "unit_id",
                "plan_sha256",
                "previous_sha256",
                "owner",
                "started_utc",
            },
            "invalid claim fields",
        )
        _integer(claimed["index"])
        _owner(claimed["owner"])
        _timestamp(claimed["started_utc"])
        _require(
            claimed["index"] == index
            and claimed["unit_id"] == unit["id"]
            and claimed["plan_sha256"] == plan_hash
            and claimed["previous_sha256"] == previous,
            "claim chain/order mismatch",
        )
        if not has_terminal:
            disposition, stopped = "incomplete", True
            continue
        terminal, terminal_hash = _read(terminal_path)
        _require(
            type(terminal) is dict
            and set(terminal)
            == {
                "claim_sha256",
                "reported_status",
                "status",
                "result_sha256",
                "elapsed_ns",
                "observed_pins",
                "children_quiescent",
                "failures",
                "finished_utc",
            },
            "invalid terminal fields",
        )
        _require(terminal["claim_sha256"] == claim_hash, "terminal claim mismatch")
        _hex(terminal["result_sha256"])
        _integer(terminal["elapsed_ns"])
        _pins(terminal["observed_pins"])
        _timestamp(terminal["finished_utc"])
        _require(
            type(terminal["children_quiescent"]) is bool, "exact quiescence required"
        )
        _require(
            terminal["reported_status"] in ("passed", "failed", "incomplete"),
            "invalid reported disposition",
        )
        failures = _failures(terminal, plan, index)
        status = "failed" if failures else terminal["reported_status"]
        _require(
            terminal["failures"] == failures and terminal["status"] == status,
            "contradictory terminal disposition",
        )
        previous = terminal_hash
        if status != "passed":
            disposition, stopped = status, True
            continue
        completed += 1
    return plan, {
        "status": disposition,
        "completed": completed,
        "required": len(plan["units"]),
        "next_unit": completed if disposition == "ready" else None,
        "checkpoint_sha256": previous,
        "authoritative": False,
        "certification_eligible": False,
    }


def inspect(path: Path, *, expected_plan_sha256: str) -> dict:
    """Read only; a live or interrupted claim is never inferred retryable."""
    return _scan(path, expected_plan_sha256)[1]


@dataclass(frozen=True)
class Claim:
    path: Path
    index: int
    plan_sha256: str
    claim_sha256: str


def claim(
    path: Path,
    index: int,
    *,
    expected_plan_sha256: str,
    expected_previous_sha256: str,
    observed_pins: dict,
    owner: dict,
) -> Claim:
    """Claim exactly the requested unit, never a later unit on contention."""
    _integer(index)
    _hex(expected_previous_sha256)
    _pins(observed_pins)
    _owner(owner)
    plan, state = _scan(path, expected_plan_sha256)
    _require(observed_pins == plan["pins"], "pins changed before acquisition")
    _require(
        state["status"] == "ready" and state["next_unit"] == index,
        "unit consumed, incomplete, failed, or out of order",
    )
    _require(
        state["checkpoint_sha256"] == expected_previous_sha256,
        "external previous checkpoint mismatch",
    )
    digest = _write(
        path / f"{index:04d}.claim.json",
        {
            "index": index,
            "unit_id": plan["units"][index]["id"],
            "plan_sha256": expected_plan_sha256,
            "previous_sha256": expected_previous_sha256,
            "owner": owner,
            "started_utc": _utc(),
        },
    )
    return Claim(path, index, expected_plan_sha256, digest)


def finish(
    claimed: Claim,
    *,
    status: str,
    result_sha256: str,
    elapsed_ns: int,
    observed_pins: dict,
    owner: dict,
    children_quiescent: bool,
) -> str:
    """Seal once after caller-verified raw evidence and bounded child cleanup."""
    _require(type(claimed) is Claim, "exact claim required")
    _integer(claimed.index)
    _hex(claimed.claim_sha256)
    _require(status in ("passed", "failed", "incomplete"), "invalid result status")
    _hex(result_sha256)
    _integer(elapsed_ns)
    _pins(observed_pins)
    _owner(owner)
    _require(type(children_quiescent) is bool, "exact quiescence required")
    plan, state = _scan(claimed.path, claimed.plan_sha256)
    _require(
        state["status"] == "incomplete" and state["completed"] == claimed.index,
        "claim already sealed or earlier unit incomplete",
    )
    receipt, digest = _read(claimed.path / f"{claimed.index:04d}.claim.json")
    _require(
        digest == claimed.claim_sha256 and receipt["owner"] == owner,
        "claim or owner changed",
    )
    terminal = {
        "claim_sha256": digest,
        "reported_status": status,
        "status": status,
        "result_sha256": result_sha256,
        "elapsed_ns": elapsed_ns,
        "observed_pins": observed_pins,
        "children_quiescent": children_quiescent,
        "failures": [],
        "finished_utc": _utc(),
    }
    terminal["failures"] = _failures(terminal, plan, claimed.index)
    if terminal["failures"]:
        terminal["status"] = "failed"
    return _write(claimed.path / f"{claimed.index:04d}.terminal.json", terminal)
