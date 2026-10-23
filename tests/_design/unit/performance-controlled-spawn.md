# Test Design — Controlled performance-runner descendants

## Purpose

Explicit process HighQoS does not inherit reliably. Verify that every native
CLI request, paired launch control (including cycle audit), and memory-worker
child has an explicit, read-back HighQoS policy before its initial thread runs.
This is implementation-control evidence, not conditioning qualification.

## Description and authority

Use Rust 1.75 standard command construction for unchanged argv, environment,
streams and process handles. On Windows request suspended creation; find the
single initial thread in a bounded snapshot, validate its retained process owner,
set and read back process power throttling, and require resume's previous count
to be exactly one. Never modify a pre-existing process, ancestor job, security
setting, global power policy or CPU quota. Linux retains ordinary spawning.

References: [suspended creation](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags),
[process power control](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation),
[thread snapshots](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-thread32first),
and [resume counts](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread).

## Scope

The four real runner launch sites share one helper. Original commands, pipe
contents, exit failures, warmups, samples, paired ordering and ceilings remain.
All launch-control overhead stays inside the existing measured operation; no
subtraction or timing conversion is permitted. Process policy is not proof of
arbitrary descendant/thread policy changes, ancestors' quotas or admission.
Source review and later fresh reference/holdout qualification remain required.

## Categories of tests

-   Positive: a real child observes explicit HighQoS at entry, receives exact
    Unicode/quoted arguments and stdin bytes, and returns stdout/stderr and status.
    Run both piped-input request and null-input control shapes.
-   Negative: process creation failure, injected setup failure before resume,
    malformed thread count/owner, non-HighQoS readback, failed or unexpected resume
    count. No child entry marker is permitted on a pre-resume failure.
-   Boundaries: retained handles identify only the newly owned child; ambiguous
    initial threads fail closed. Cleanup is bounded, preserves original error and
    reports kill/wait failures. Native failures must not hang a suspended child.
-   Interactions: source guards cover all four actual call sites, prohibit direct
    ungoverned spawn/output there, and retain cycle-audit Child compatibility.
    A complete runner build and focused real CLI/memory smoke checks follow.
-   Portability: compile the dependency-free helper with pinned Rust 1.75 on
    Windows and Linux; Linux command/output behavior is unchanged. Native tests
    are covered on Windows rather than counted as passed on Linux.

## Completion criteria

Small native and offline regressions pass before broader runner/controller tests.
Every failed attempt remains retained. The registry matches no proposed runner,
helper, architecture-test or charter path; verify governed artifacts unchanged.
This correction does not promote the new conditioning method, recalibrate a
baseline, certify old binaries or claim a runtime speedup.
