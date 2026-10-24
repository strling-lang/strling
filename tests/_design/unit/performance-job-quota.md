# Test Design — Windows job quota provenance

## Purpose

Prevent an unrestricted immediate job from being mistaken for an unrestricted
ancestor chain. Certification must reject unknown effective CPU quotas before
placement changes, conditioning waits, or product samples.

## Authority and scope

[QueryInformationJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject)
with a null job handle queries only the immediate job.
[Nested jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs)
inherit ancestor constraints. Absence of an immediate rate limit is not proof
that ancestors have none. No job escape, ancestor mutation, host change, quota
relaxation, baseline refresh, or alternative admission is authorized by this fix.

## Test categories

-   No job: retain the existing unlimited result without a job query.
-   Immediate enabled rate control: reject as limited, retaining the raw flags.
-   Immediate disabled rate control: report unknown and reject; cover nested
    capped-outer/unrestricted-inner jobs on newly owned synthetic processes.
-   Query failures and truncated/oversized result lengths: fail closed.
-   Early failure: quota rejection precedes placement, timer reads, and waits.
-   Pre-build failure: execute the actual isolated probe program with unknown,
    limited, and failed quota observations; all reject before placement or builds.
    Unlimited observations retain placement and exact output. Non-Windows probes
    do not query Windows quota. All seven public build callers retain the probe;
    the later live-environment quota check remains independent and mandatory.
-   Direct dependents: both Rust runner and memory worker share the same native
    query and rejection implementation. Build both with the complete default
    dependency graph, without executing a product performance coordinate.
-   Cross-platform: deterministic classification tests run on Windows and Linux;
    native API and owned-job integration are covered separately on Windows.

## Completion criteria

Preserve failed tests and the existing native counterexample. Require focused
regressions, native owned-job reproduction, direct dependent checks, unchanged
generated artifacts, and an exact-source engineering commit. Historical receipts
remain byte-preserved, not requalified. Unknown quotas remain an explicit blocker
until a separately governed and independently qualified architecture resolves them.
