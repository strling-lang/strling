"""Data-only validation of externally pinned, unqualified v2 process receipts.

No producer imports, execution, filesystem access, quota inference or admission.
The caller must obtain the terminal pin and complete expected plan independently.
"""

import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re


class ReceiptError(ValueError):
    """The complete receipt is not internally consistent with its external pins."""


LOGS = {"stdout.bin", "stderr.bin"}
ARTIFACTS = {"suspended.json", "root-exit.json", "lifecycle-wakeups.json"}
FILES = LOGS | ARTIFACTS | {"plan.json", "terminal.json"}
PLAN = {
    "command",
    "cwd",
    "source_sha",
    "inputs",
    "environment_sha256",
    "selected_cpu",
    "timeout_seconds",
    "implementation_sha256",
    "job_implementation_sha256",
    "controls_implementation_sha256",
    "observation_implementation_sha256",
}
TERMINAL = {
    "contract",
    "status",
    "authoritative",
    "certification_eligible",
    "baseline_admission",
    "plan_sha256",
    "clock",
    "cpu_unit",
    "logs",
    "artifacts",
    "action_begin_ns",
    "controls",
    "release_begin_ns",
    "exit_code",
    "root_exit_observed_ns",
    "accounting",
    "action_end_ns",
    "whole_action_ns",
    "cleanup",
    "finished_ns",
}


def _need(value, message):
    if not value:
        raise ReceiptError(message)


def _shape(value, keys, label):
    _need(type(value) is dict and set(value) == set(keys), label + " fields")


def _integer(value, minimum=0, maximum=(1 << 64) - 1):
    _need(type(value) is int and minimum <= value <= maximum, "exact bounded integer")
    return value


def _digest(value, length=64):
    _need(type(value) is str and re.fullmatch("[0-9a-f]{%d}" % length, value), "digest")
    return value


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ReceiptError("nonfinite JSON: " + value)


def _parse(data):
    _need(len(data) <= 32 * 1024 * 1024, "bounded JSON")
    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ReceiptError("invalid JSON: " + str(error)) from error


def _text(value):
    _need(type(value) is str and value and "\x00" not in value, "literal text")


def _absolute(value):
    _text(value)
    _need(
        PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute(),
        "absolute path",
    )


def _plan(row):
    _shape(row, PLAN, "plan")
    _need(type(row["command"]) is list and row["command"], "command")
    for value in row["command"]:
        _text(value)
    _absolute(row["cwd"])
    _digest(row["source_sha"], 40)
    _integer(row["selected_cpu"], 0, 63)
    _integer(row["timeout_seconds"], 1, 1800)
    for key in PLAN - {
        "command",
        "cwd",
        "source_sha",
        "inputs",
        "selected_cpu",
        "timeout_seconds",
    }:
        _digest(row[key])
    _need(type(row["inputs"]) is dict and row["inputs"], "input pins")
    for key, value in row["inputs"].items():
        _absolute(key)
        _digest(value)
    _need(row["command"][0] in row["inputs"], "pinned executable")


def _identity(row):
    _shape(
        row,
        {"pid", "birth", "exit", "kernel", "user", "exited_before_query"},
        "identity",
    )
    _integer(row["pid"], 1, (1 << 32) - 1)
    _need(type(row["exited_before_query"]) is bool, "identity query state")
    for key in ("birth", "exit"):
        value = row[key]
        _need(
            type(value) is str and re.fullmatch("0|[1-9][0-9]{0,19}", value),
            "raw FILETIME",
        )
        _integer(int(value), int(key == "birth"))
    for key in ("kernel", "user"):
        _integer(row[key])


def verify_process_receipt(files, expected_terminal_sha256, expected_plan):
    """Validate a complete immutable byte bundle; return diagnostic facts only."""
    _shape(files, FILES, "bundle")
    for data in files.values():
        _need(type(data) is bytes and len(data) <= 64 * 1024 * 1024, "bounded bytes")
    _need(
        _sha(files["terminal.json"]) == _digest(expected_terminal_sha256),
        "external terminal pin",
    )
    _plan(expected_plan)
    plan = _parse(files["plan.json"])
    _plan(plan)
    _need(plan == expected_plan, "independent plan mismatch")
    row = _parse(files["terminal.json"])
    _shape(row, TERMINAL, "terminal")
    _need(row["contract"] == "unqualified-process-tree-envelope-v2", "receipt version")
    _need(row["status"] == "observed", "successful acquisition required")
    for key in ("authoritative", "certification_eligible", "baseline_admission"):
        _need(row[key] is False, "no authority")
    _need(
        row["clock"] == "perf_counter_ns"
        and row["cpu_unit"] == "raw-job-accounting-100ns",
        "raw clock units",
    )
    _need(_sha(files["plan.json"]) == _digest(row["plan_sha256"]), "plan pin")
    for group, names in (("logs", LOGS), ("artifacts", ARTIFACTS)):
        _shape(row[group], names, group)
        for name, pin in row[group].items():
            _shape(pin, {"sha256", "bytes"}, "artifact pin")
            _need(_integer(pin["bytes"]) == len(files[name]), "artifact size")
            _need(_digest(pin["sha256"]) == _sha(files[name]), "artifact hash")
    controls = row["controls"]
    _shape(
        controls,
        {
            "affinity_mask",
            "cpu_set_id",
            "root_high_qos",
            "job_limit_flags",
            "root_resumed",
            "ancestor_quota_qualified",
            "descendant_power_qualified",
        },
        "controls",
    )
    _need(
        _integer(controls["affinity_mask"]) == 1 << plan["selected_cpu"],
        "root placement",
    )
    _integer(controls["cpu_set_id"], 1, (1 << 32) - 1)
    _need(_integer(controls["job_limit_flags"]) == 0x2010, "job limits")
    _need(
        controls["root_high_qos"] is True and controls["root_resumed"] is False,
        "pre-release root controls",
    )
    for key in ("ancestor_quota_qualified", "descendant_power_qualified"):
        _need(controls[key] is False, "no unproved controls")
    _shape(row["cleanup"], {"quiescent", "terminated"}, "cleanup")
    _need(
        row["cleanup"]["quiescent"] is True and row["cleanup"]["terminated"] is False,
        "natural retirement",
    )
    _need(_integer(row["exit_code"]) == 0, "root exit")
    accounting = row["accounting"]
    _shape(
        accounting,
        {
            "query_begin_ns",
            "query_end_ns",
            "user_100ns",
            "kernel_100ns",
            "total_processes",
            "active_processes",
            "limit_terminated_processes",
        },
        "accounting",
    )
    for value in accounting.values():
        _integer(value)
    _need(
        accounting["total_processes"] >= 1
        and accounting["active_processes"]
        == accounting["limit_terminated_processes"]
        == 0,
        "whole job normal exit",
    )
    times = [
        row["action_begin_ns"],
        row["release_begin_ns"],
        row["root_exit_observed_ns"],
        accounting["query_begin_ns"],
        accounting["query_end_ns"],
        row["action_end_ns"],
        row["finished_ns"],
    ]
    for value in times:
        _integer(value)
    _need(times == sorted(times), "clock order")
    _need(
        _integer(row["whole_action_ns"])
        == row["action_end_ns"] - row["action_begin_ns"],
        "whole interval",
    )
    before, after = (_parse(files[n]) for n in ("suspended.json", "root-exit.json"))
    _identity(before)
    _identity(after)
    _need(
        before["exited_before_query"] is False and after["exited_before_query"] is True,
        "process lifetime",
    )
    _need(
        (before["pid"], before["birth"]) == (after["pid"], after["birth"]),
        "process identity continuity",
    )
    _need(int(after["exit"]) >= int(after["birth"]), "exit FILETIME order")
    _need(
        all(after[k] >= before[k] for k in ("kernel", "user")), "process CPU continuity"
    )
    # Running-process exit FILETIME is undefined. Root CPU starts before job
    # assignment and need not be less than aggregate post-assignment job CPU.
    events = _parse(files["lifecycle-wakeups.json"])
    _need(type(events) is list and len(events) <= 100000, "bounded lifecycle")
    previous = row["root_exit_observed_ns"]
    for event in events:
        _need(type(event) is dict, "lifecycle object")
        kind = event.get("kind")
        _need(kind in ("wait-timeout", "completion-wakeup"), "lifecycle kind")
        keys = {"kind", "wait_milliseconds", "observed_ns"}
        if kind == "completion-wakeup":
            keys |= {"message", "pid"}
        _shape(event, keys, "lifecycle")
        _integer(event["wait_milliseconds"], 1, 100)
        timestamp = _integer(event["observed_ns"])
        _need(previous <= timestamp <= accounting["query_begin_ns"], "lifecycle clock")
        previous = timestamp
        if kind == "completion-wakeup":
            _integer(event["message"], 0, (1 << 32) - 1)
            if event["pid"] is not None:
                _integer(event["pid"], 0, (1 << 64) - 1)
    return dict(
        status="internally-consistent-unqualified-receipt",
        terminal_sha256=expected_terminal_sha256,
        plan_sha256=row["plan_sha256"],
        source_sha=plan["source_sha"],
        pid=after["pid"],
        birth=after["birth"],
        whole_action_ns=row["whole_action_ns"],
        authoritative=False,
        certification_eligible=False,
        baseline_admission=False,
        ancestor_quota_qualified=False,
        independence_qualified=False,
    )
