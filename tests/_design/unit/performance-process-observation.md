# Test Design — Diagnostic process counter observation

## Purpose and authority

Acquire actual cumulative Windows CPU observations across an owned serial
process, including launch, warmups, rejected attempts and exit. This diagnostic
does not replace live conditioning, sample acceptance or performance ceilings.
It is not an independently qualified reference or a claim of physical cause.

## Scope

An exclusive JSON-lines journal records a pre-launch system snapshot, bracketed
system and process snapshots while the child runs, and a post-exit snapshot.
Every CPU is retained, including the selected CPU and its sibling. The observer's
own process times are retained without subtraction. Process times use raw
FILETIME units; timestamps use a monotonic clock. Do not subtract across these
clock domains or convert cycles to wall time. Cumulative endpoints cover elapsed
activity but cannot locate events within an interval or prove continuous control
state. Long gaps and query uncertainty must remain visible.

GetProcessTimes leaves exit time undefined for a running process. Retain the raw
field but interpret it only when the handle was observed signaled before the
query; do not require a running process's raw exit field to be zero. See the
[Microsoft API contract](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes).

The journal borrows a live process handle; it never launches, terminates, pins or
changes another process, host setting or service. Its caller owns bounded waits
and cleanup. Child trees and instantaneous placement/power tracking are outside
this component, as are admission decisions and authoritative reference signing.

## Tests and acceptance

-   Exclusive creation preserves existing attempts and rejects collision before
    reading native counters.
-   Pre-launch, running and post-exit snapshots retain every raw CPU and bracket.
-   Completion requires an actual exited child, stable PID/birth and final times.
-   Reject missing initial/running observations, reused identities, decreasing
    counters, malformed exact types, overlapping query brackets and CPU-count
    drift. Retain the offending raw snapshot before rejecting it.
-   Interrupt-count wrap remains raw and explicit; it is not a negative busy
    interval or permission to normalize unknown counter changes.
-   Context failure retains an incomplete terminal record and successful prefix.
-   Observer CPU, long scheduling gaps and unfavorable values are not filtered.
-   Mocked tests run on Native and WSL. A bounded native functional exercise must
    independently reconstruct the real API journal before product diagnostics.
-   A functioning journal is not overhead qualification, all-coordinate coverage
    or a source-distinct reference. Those obligations remain before promotion.

## Read-only handle acquisition regression

An optional context manager opens a handle for a caller-supplied PID and exact
creation FILETIME, not a PID alone. It requests only query-information, VM-read
and synchronization rights. Synchronization is required by the existing
zero-timeout signal-state check: a query/VM-read-only handle caused error 5 in
the preserved resident-census diagnostic. No process mutation rights,
inheritance, elevation, debug privilege, launch or termination are permitted.

-   The exact access mask includes SYNCHRONIZE and excludes write/control rights.
-   Reject invalid PID/birth before opening; reject PID reuse or a signaled
    process before yielding. A running process's undefined raw exit FILETIME
    is not evidence that it exited.
-   Close the owned handle once on success, caller failure, identity failure or
    counter-query failure. Do not close a failed-open null handle.
-   Mocked API tests run everywhere; a native self-process check exercises the
    actual open/wait/times/close path without executing product samples.
-   This access helper does not qualify a working-set census, historical peak
    attribution, continuous isolation or any certification result.
