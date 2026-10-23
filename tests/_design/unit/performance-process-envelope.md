# Test Design — Native whole-process measurement envelope

## Purpose

Close the acquisition gap between a sampled runner body and its complete process
tree. The retained same-CPU challenge doubled whole-action time without failing
sample medians. A new, opt-in acquisition primitive must include launch, warmups,
all attempts, child processes, output and exit without polling CPU counters or
subtracting estimated interference. It does not grant performance admission.

## Description and authority

Create the exact pinned executable suspended. Assign it to a new private job
before resuming, enforce a fixed job affinity and root CPU set/HighQoS, and retain
raw wall boundaries plus final job accounting after every member has exited.
Only explicitly listed standard-stream handles may be inherited. The job has
no breakaway flags or CPU quota; no ancestor job or host setting is changed.

Windows job accounting includes exited descendants; it is coarse CPU time, not
elapsed time, retired work or a scheduler-delay estimate. A job affinity is an
enforced restriction, unlike sparse observation of process state. Root power and
CPU-set observations are not continuous proof of all descendant power states.
Source-reviewed direct process creation is required: broker/service-created
processes are outside this primitive's coverage and are not silently accepted.

References: [job accounting](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information),
[nested jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs),
[suspended creation and handle inheritance](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw).

## Scope

This primitive can enclose a latency, CLI, memory or size-observer command. It
does not interpret or change workloads, sample counts, caps or result JSON. It
preserves stdout/stderr byte-for-byte. It is not yet wired into certification.
Reference-only nine repetitions, independent source-distinct holdout nine,
all54 coordinates/all12 conditioning obligations, challenge discrimination,
overhead qualification and independent trust remain required before promotion.
No old baseline is relabeled as new whole-process reference evidence.

## Categories of tests

-   Positive: actual suspended native child, exact output, explicit environment,
    pinned inputs, fixed affinity and root HighQoS, zero active final job members.
-   Negative: bad plan/pins before launch; nonzero child exit; unknown surviving
    descendant; timeout; control/assignment failure before resume; changed input;
    replay/collision; cleanup failure and missing/invalid accounting.
-   Boundaries: strict integer CPU/deadline fields, no boolean aliases, no shell
    resolution, no environment-key aliases, complete immutable terminal on failure.
-   Interactions: a short-lived grandchild contributes to final accounting even
    after exiting; sleeping between observable work contributes to the complete
    wall interval; attempted affinity widening cannot escape the private job;
    unrelated inheritable handles and private job handles do not leak.
-   Offline: injected native adapter tests run without Windows and establish that
    every error fails closed and every live owned process receives cleanup.
-   Notification loss: completion messages are optional wakeups, never lifecycle
    authority. A bounded wait timeout rechecks actual job accounting; a naturally
    empty job completes, while live members retain the original absolute deadline.
    Unexpected port errors, changed limits and malformed accounting still fail.
    Deadline expiry never becomes success merely because a later query is empty.
    Compare the unchanged parent and corrected implementation on a fixed nine-pair
    native fixture with deliberately withheld wakeups, retaining every timing and
    failure. This is orchestration failure-path evidence, not product performance.

## Completion criteria

Native functional tests plus cross-platform state-machine tests pass. Raw CPU
counts remain uninterpreted, all output/failures remain retained, and every result
explicitly denies certification eligibility. The generated-artifact registry
matches none of this module, its tests or this charter; verify existing governed
performance artifacts without regenerating measurements.

## Versioned identity and lifecycle evidence sealing

Version1 terminals pin streams but omit the suspended/exit identity snapshots
and lifecycle wakeup journal used by downstream audits. Those historical bytes
must remain unchanged and cannot supply a newly qualified reference by pretending
to be a complete version2 receipt.

Version2 terminals hash the exact bytes and sizes of every known auxiliary file
after owned cleanup, including failure-only survivor/launch-cleanup records when
present. Observed success requires both identity snapshots and the lifecycle
journal, plus both streams. Missing, unreadable, linked, replaced or changed files
fail closed while retaining the failed terminal and all available evidence. This
sealing occurs outside the existing complete-work wall interval; no workload,
launch placement, sample, CPU accounting or measured boundary changes.

A separate data-only reader accepts only externally pinned version2 terminal
bytes and an independently supplied exact command/source/input/implementation
plan. It imports no producer or native process-control code and performs no
execution or file-system mutation. Validate closed fields, byte sizes/hashes,
identity continuity, monotonic clocks/counters, complete natural job retirement,
root placement and all retained lifecycle events. Notifications remain diagnostic;
they cannot override final job accounting. Preserve a running snapshot's undefined
raw exit field without interpreting it as a completed exit or requiring zero.
Unknown ancestor quotas and descendant-power qualification remain explicitly
unqualified; no reader result grants admission, signing or trust authority.

Tests must reject changed/missing/extra artifacts, same-size tampering, refreshed
inner hashes under the old external pin, plan changes, malformed exact types,
duplicate/nonfinite JSON, foreign/reused identities, terminated/surviving jobs,
inverted boundaries, out-of-interval events and all version1 receipts. Native
fresh owned fixture processes must prove end-to-end sealing and data-only replay,
including an exited descendant and timeout failure. Historical product samples
are not repeated, rewritten or used as fresh reference observations.
