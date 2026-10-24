# Test Design — Effective process memory observations

## Purpose and authority

An unrestricted immediate job does not establish unrestricted ancestors. CPU
rate limits and working-set limits also have different measurement effects:
elapsed-time delay alone cannot establish that a low RSS observation is valid.
This read-only diagnostic records effective process working-set controls next
to the original resident and committed-memory counters. It is not admission,
a new performance metric, a replacement for peak RSS, or a live-policy change.

The Windows contracts are [GetProcessWorkingSetSizeEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-getprocessworkingsetsizeex),
[PROCESS_MEMORY_COUNTERS_EX](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex),
and [nested job limits](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).
The first returns process-level working-set bounds and enforcement flags;
job queries with a null handle return only the immediate job. Whether the
effective process query exposes a particular ancestor restriction must be
checked with an actual owned nested-job challenge, not assumed from its name.

## Scope and cases

-   Native x64 ABI sizes, explicit fixed-width fields and exact returned memory
    structure size; failed or incomplete queries fail closed.
-   Identity includes current PID and process birth; complete query brackets are
    retained. Record raw working-set minimum/maximum/flags, page faults, current
    and peak RSS, current and peak pagefile usage, and private commit.
-   Exact integer types, closed fields, monotonic query interval, consistent
    current/peak counters, strict denial flags and process identity are validated.
-   Unknown future working-set flag bits are preserved as raw data, not silently
    interpreted as unrestricted. No flags or counters grant eligibility.
-   Pair validation rejects changed process birth/PID, overlapping query brackets,
    changed working-set controls and regressed peaks. Preserve raw page-fault
    DWORD wrap without inventing a delta. In particular, hard maximum flags6
    becoming soft maximum flags10 must be observable and rejected as drift.
-   Native owned-child challenge uses fixed identical allocation/touch work under
    an unrestricted inner job and a newly owned constrained ancestor. Retain all
    outputs and read back both job controls. Never mutate inherited jobs, escape
    them, create a host broker, or change workstation configuration.
-   All allocations, child processes and jobs must retire. Diagnostic challenge
    timings are not certification samples, independent reference cohorts, or
    evidence that any product meets its ceilings.

## Completion criteria

Unit tests run on Native and WSL (mocked APIs where needed); a native integration
test exercises read-only current-process queries. The actual owned challenge
must establish which fields detect or fail to detect the ancestor restriction.
Snapshot observations cannot prove continuous controls or absence of trimming
between queries. Fresh reference/holdout cohorts, every conditioning obligation,
unchanged original samples/ceilings, governed policy review and independent
trusted verification remain required before any admission alternative.
