# Test Design — retain the rejecting snapshot

## Authority and correction

The generated-artifact check must reject every mutation detected by its initial
and post-command full integrity snapshots. Currently its error description takes
a second post-command snapshot: a later restoration can erase the offending
paths from the explanation. Retain the exact rejecting state and compute the
reason from it. Do not rescan just to explain an already-final rejection.

All acceptance checks remain: every initial, post-command and final success-path
snapshot; every file byte, mode, containment, alias, census and Git-authority
check; each registered operation, output existence check and error policy. No
snapshot is reused across commands or successful boundaries. The redundant scan
was only for explaining a rejection, never for admitting a pass. Rejection still
returns immediately, preserving the original command result and failing status.

## Regression checks

-   With initial, rejecting and restored states supplied in sequence, report all
    added, removed and changed paths from the rejecting state. The old code must
    fail this regression. Require exactly the first two full snapshots.
-   On a nonmutating command, retain the independent final boundary. A late
    mutation detected only there must still reject with its exact paths.
-   Run the complete snapshot/preparation/registry suites and downstream output,
    profile-gate and certification consumers on Native and WSL. Integrated
    performance-artifact integrity comes first. No generator runs for this change.

## Prospective equivalent failure-path diagnostic

Use one immutable six-pair ABBAAB comparison on the same held real source and WSL
filesystem. For both implementations, read the complete real tracked/governed/Git
integrity snapshot on every call. A sample-free controlled executor performs no
external command and switches a single synthetic marker in the snapshot overlay
after its one invocation. The marker remains changed, giving identical failure
status, command output and offending path in both implementations. The complete
real snapshot bytes and order must agree on every read. This is a controlled
mutation-reporting diagnostic, not a real generator, profile or certification run.

Pin the source frame, both implementations, overlay and all ordered results.
Retain all six pairs, failures, and adverse timings. Count every real full scan:
the baseline performs three and the candidate two for the same failed operation.
No successful-path scan is removed. Report time to the completed failure result
only; do not extrapolate to successful preparation or total certification time.
No consumed product measurement is repeated, no threshold/sample count changes,
and no certification authority is produced. Promotion requires focused red/green
checks, equivalent output, independent data-only audit and a clean local commit.
