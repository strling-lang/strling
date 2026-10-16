# Test Design — atomic quality fixture isolation

## Purpose

Exercise real atomic transport and rejection logic without depositing synthetic
Full/Release receipts in the owning repository's certification-results directory.
Fixture data must never be confused with live certification or historical evidence.

## Description and authority

The structured-operation schema and quality runner retain the same invocation,
source, stream, exit-code and sample-consumption requirements. Unit producers
remain synthetic and execute through an injected callback, but their toolchain
root, artifact directory and source identity must belong to a disposable fixture.
No production transport, verifier, acceptance rule or performance contract changes.

## Scope

The two atomic quality routing fixtures, their successful/failed/stale-success
cases and their temporary source/artifact boundaries are in scope. Real profile
execution, benchmark/calibration work, signed authority and deletion or rewriting
of prior leaked fixture receipts are out of scope.

## Categories of tests

-   Isolation: intercept directory creation at the real certification-results
    root before it writes. Running both existing atomic fixture methods must
    succeed without any attempt to allocate that real root.
-   Positive and negative transport: preserve the existing passed Full case,
    failed Release case and stale-success/process-failure integrity rejection.
    Verify retained stdout/stderr and synthetic context inside the temporary root.
-   Lifecycle: all three fixture allocations stay inside their respective owned
    temporary directories, which are removed by normal test cleanup. No real
    certification source or repository state is used as fixture identity.
-   Evidence: an external before/after receipt inventory must remain exactly
    unchanged during repeated focused/direct validation. Existing leaked files
    and the failed operator guard remain retained historical diagnostics.

## Completion criteria

-   The real-root interception regression fails before correction without
    creating another real receipt, and passes after temporary-root isolation.
-   Focused cases pass repeatedly Native and WSL without skipping transport
    checks or relaxing source, invocation, failure or sample-consumption rules.
-   Direct regressions, source/authority/receipt guards and static checks pass;
    the exact correction is committed before any new candidate is frozen.
-   No authenticated performance sample or authoritative profile is created.
