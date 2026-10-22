# Test Design — Diagnostic performance phase timeline

## Purpose and authority

Account for runner-body work that accepted sample medians do not cover. This is
diagnostic instrumentation, not a conditioning policy or performance baseline.
Existing performance-resource contracts retain every workload, cap, warmup,
sample, rejection, placement and isolation obligation.

## Scope

An explicit sidecar option records preparation, primary warmups, sample setup,
control warmups, measurement including rejected attempts, post-measurement
validation and serialization. It must not add fields to ordinary stdout or
change sample acceptance. Disabled instrumentation performs no timing or I/O.
The clock origin is after argument parsing, not process birth. Independent
parent receipts must still cover launch, argument parsing and process exit.

## Tests and acceptance

-   Reject unsupported operations, auto-batching and altered512/64 denominators.
-   Open the sidecar exclusively; never replace a prior attempt.
-   Require ordered, adjacent monotonic phase intervals without fabricated gaps.
-   Distinguish complete runner-body execution from partial/error output.
-   Preserve successful prefixes on failure; incomplete output grants no authority.
-   Exercise the module independently with the pinned Rust runtime before linking
    the product runner; test real CLI parsing and disabled/enabled output shapes.
-   Check original sample/warmup loops and acceptance arithmetic remain unchanged.
-   Reject a missing Windows CPU selection before fixture preparation, warmups or
    sampling, while retaining the existing post-work placement verification.
-   Verify all raw phase records independently against parent/process receipts
    before empirical use. A phase log is not independent reference qualification.

## Deferred empirical acceptance

Instrumentation overhead needs a prospectively fixed, counterbalanced comparison
on equivalent workloads before it can support any qualification claim. No
threshold may be fit to earlier favorable controls. Full54-coordinate empirical
qualification, source-distinct references/holdout and challenge sensitivity are
outside these structural/unit tests and remain mandatory before promotion.
