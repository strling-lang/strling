# Test Design — performance launch normalization

## Purpose

Verify that paired same-binary controls measure the governed typical warmed CLI
latency ratio, rather than deterministic host process-creation cleanup. Preserve
the interpretation of historical estimators and every authenticated observation.

## Description

Acquisition retains 512 warmups per side and 64 adjacent request/control pairs.
A half-complementary allocation balances every fixed launch-period residue from
2 through 64 to discrepancy at most two. Changing cleanup phase can still bias
an all-sample geometric mean, so the regression location is the exact ratio of
the two marginal medians, without intermediate half-nanosecond rounding.
Sorting is statistical aggregation, not rejection: both complete raw arrays,
their medians, p95, MAD, CPU evidence and consumption hashes remain retained.

## Scope

In scope: exact integer normalization; identity, permutation, unit scaling,
reciprocity up to conservative final rounding, real-slowdown sensitivity,
monotonicity, bounded contamination below the median breakdown boundary;
native allocation and controller/runner binding; legacy reconstruction; explicit
clean-source calibration migration with immutable history and prior ceiling caps.
Out of scope: compiler semantics, product APIs, target runtime behavior,
dependencies, host security/power settings, broader waivers or publication.

## Categories of Tests

-   Positive: identical input distributions normalize to 10000 basis points;
    common unit scaling is exact; 10% and 50% complete-array slowdowns are retained.
-   Negative: empty, unequal, non-64, non-positive or non-integer arrays; unknown
    schedule or mismatched runner metadata; unconfirmed/dirty migration; policy,
    denominator, environment or threshold expansion.
-   Edge: unequal middle observations; large integers; independently permuted
    arrays; 0 through 31 one-sided large cleanup pulses; transition at 32 pulses
    is explicitly not claimed immune.
-   Interaction: retain the old paired-ratio median and order-stratified estimator
    unchanged for old manifests, baselines and failed receipts. New authority must
    name both the new estimator and its acquisition schedule, and use fresh data.
-   Integration: native source-bound runner, all raw request/control accounting,
    actual conditioning/isolation, registered identity generator/check and both
    complete authoritative certification campaigns remain mandatory.

## Completion Criteria

-   Independent pure proofs, native allocation tests and controller/runner
    rejection tests pass before live qualification.
-   A prospectively fixed nine-repetition live proof retains every observation;
    identical-work controls respect the unchanged minimum 1000bp budget on every
    repetition; median/MAD limits and actual CLI ceilings are unchanged.
-   Migration archives prior authority and cannot increase any effective ceiling,
    counts, conditioning allowance, isolation allowance or waiver.
-   No diagnostic or readiness output is attributed as authoritative certification.
