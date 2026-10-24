"""Data-only decoder for unqualified x64 Windows working-set watch experiments.

Zero reported loss is not continuous coverage: the OS stops recording while a
query drains its buffer, and another consumer can drain the same process buffer.
No result from this module is performance admission or a replacement for RSS.
"""

from __future__ import annotations

import struct

RECORD = struct.Struct("<QQQQ")
MAX_BYTES = 2 * 1024 * 1024


def decode(raw: bytes) -> dict:
    """Preserve ordered records, duplicates and the native loss terminator."""
    if type(raw) is not bytes or not 32 <= len(raw) <= MAX_BYTES or len(raw) % 32:
        raise ValueError("bounded complete x64 watch records required")
    records = []
    for offset in range(0, len(raw), RECORD.size):
        pc, address, thread, flags = RECORD.unpack_from(raw, offset)
        if pc == 0:
            if any(raw[offset + RECORD.size :]):
                raise ValueError("nonzero data after watch terminator")
            return dict(
                records=records,
                lost_records=address,
                terminator_thread=thread,
                terminator_flags=flags,
                certification_eligible=False,
            )
        if address == 0:
            raise ValueError("null recorded page")
        records.append(dict(pc=pc, address=address, thread=thread, flags=flags))
    raise ValueError("missing watch terminator")


def require_promised_pages(buffers: list[bytes], pages: list[int]) -> dict:
    """Check only supplied synthetic page promises, never process completeness.

    The caller must independently establish query success, process identity,
    initialization, ownership and a quiescent boundary for every supplied buffer.
    Virtual addresses are page-rounded for matching; raw values remain in decode.
    """
    if type(buffers) is not list or not 1 <= len(buffers) <= 64:
        raise ValueError("bounded watch buffer sequence required")
    if (
        type(pages) is not list
        or not 1 <= len(pages) <= 32768
        or any(type(p) is not int or not 0 < p < 2**64 or p % 4096 for p in pages)
        or len(set(pages)) != len(pages)
    ):
        raise ValueError("unique aligned x64 promised pages required")
    observed = set()
    count = 0
    for raw in buffers:
        parsed = decode(raw)
        if parsed["lost_records"]:
            raise ValueError("working-set watch records lost")
        if parsed["terminator_flags"] or any(r["flags"] for r in parsed["records"]):
            raise ValueError("unsupported reserved watch flags")
        count += len(parsed["records"])
        observed.update(r["address"] & ~4095 for r in parsed["records"])
    missing = sorted(set(pages) - observed)
    if missing:
        raise ValueError(f"{len(missing)} promised pages absent")
    return dict(
        promised_pages=len(pages),
        distinct_observed_pages=len(observed),
        records=count,
        certification_eligible=False,
        process_lifetime_coverage=False,
    )
