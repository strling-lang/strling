# Test Design — Quiescent working-set watch discrimination

## Authority and prospective scope

This is a synthetic Windows API experiment, never live performance admission.
The [watch API](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getwschangesex)
has one process buffer, a lost-record terminator, and an unrecorded interval
while it drains. Zero reported loss alone is not complete coverage. Raw RSS,
all existing ceilings, sample counts, original conditioning and unknown-ancestor
quota rejection remain unchanged. No debugger result is certification evidence.

Use the documented [debug-event suspension](https://learn.microsoft.com/en-us/windows/win32/debug/debugging-events)
of every thread in the affected process, rather than treating one suspended
thread or a cooperative signal as whole-process quiescence. Attach only to a
newly owned suspended child, initialize watch before its first resume, and drain
only while its debug event is outstanding. Retain process identity, raw event
bytes, query result/error/size, raw watch bytes, initial working-set census and
memory snapshots. Any attachment, query, ownership, loss or interpretation error
prevents a coverage conclusion. Do not enable privileges or debug other apps.

## Fixed workload and adverse case

Two fresh synthetic processes run once each: default owned controls and an
owned-child hard maximum of 1MiB (minimum204800, flags6), applied and read back
after all job assignments. Inherited controls remain untouched and unknown.
The new standalone Rust1.75 fixture requires the debugger before work. It
allocates two simultaneous 2MiB regions, writes512pages of A with1, trims,
writes512pages of B with3 and rereads A in reverse, then trims again. Exactly
1536page touches and checksum2560; five ordered debugger phase barriers0..4.
Both regions remain live until process exit. Query current/peak RSS and private
commit at barriers; low RSS is not admission. No product sample is consumed.

The observer uses a fixed2MiB output buffer and at most64phase buffers. The OS
internal watch capacity is separate and cannot be inferred from that size.
Preserve failed calls and nonzero loss; never replay the workload, enlarge a
buffer and rerun for a favorable result, drop unfavorable rows, or convert a
missing page into success. At most1024promised allocation pages are compared
against the ordered raw history, with duplicates retained. Page rounding is
only for matching; retain every raw address and reserved flag. Reject unknown
flags, missing terminators, nonzero trailing data, loss and missing promises.

## Tests and explicit non-claims

Data-only unit tests cover x64 layout, duplicate/order preservation, loss,
reserved flags, truncated or oversized input, terminator poisoning, missing
pages despite sufficient record count, exact integer/type/page boundaries and
no admission authority. Portable Rust tests prove coordinates and arithmetic.
Run integrity first, Native and WSL unit checks, direct envelope/memory reader
dependents, formatting and a source-bound data-only receipt audit.

Debugger attachment and pauses alter the process and its timing. No subtraction,
reference qualification, product lifetime proof, speedup or full-certification
claim follows. Even a successful promised-page comparison leaves descendants,
initial state races, address reuse, allocation/free lifetimes, kernel-mediated
changes, observer costs and actual product integration unqualified. A union of
addresses is not current or peak RSS and must not silently replace either.
Preserve every prior failure and all source-distinct campaign obligations.
