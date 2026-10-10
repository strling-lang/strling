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

## Native CPU-accounting batch precision

The native process CPU clock's observed 15,625,000ns increments are much larger
than the prior approximately 2ms batches. FILETIME's 100ns representation is not
an observed resolution guarantee. Independent integer-clock counterexamples
must retain the entire phase range: short intervals can report zero or one
whole accounting quantum for identical CPU work; a two-quantum interval has an
exact delta for every phase in that model.

The reviewed native in-process selector target is 31,250,000ns. This increases
measurement work, not an acceptance ceiling. Legacy manifests retain their
prior target. The CLI's process-launch control keeps its separate unchanged
target and batching. Every selected count stays bounded by 4,096; the 1ms
minimum accepted batch median, 512 warmups, 64 samples, nine repetitions,
50ms descheduling gate, 500bp MAD, and all prior effective ceilings remain
unchanged. Reuse of an authenticated baseline count must not reselect it.

Tests must reject arbitrary precision targets and policy changes, prove native
versus legacy and CLI selection, preserve all 54 prior caps, and require a
fresh clean-source calibration. Fixed diagnostic success is not certification.

## Supplementary native cycle audit

The optional diagnostic-only `--cpu-cycle-audit process-cycle-endpoints-v1`
records Windows QueryProcessCycleTime endpoints around every in-process batch
and around an immediately preceding empty counter-read control. Cycle values
are never time values and are never converted into nanoseconds. Ordinary
profile invocation, wall-time intervals, GetProcessTimes evidence, batching,
sample selection, descheduling, budgets, conditioning and isolation do not
change. Unsupported hosts, unknown audit identities, CLI child-process work
and peak-RSS work must reject this optional mode rather than claim coverage.

Pure tests must reconstruct both deltas exactly, reject decreasing or reordered
endpoints, retain zero CPU-time sentinel examples with positive independently
measured cycles, and reject zero or control-dominated cycle work. Missing,
truncated, mistyped or malformed audit data cannot pass an independent review.
Every accepted and rejected batch must retain its cycle endpoints, including
unfavorable values; no cycle value is a sample-filtering criterion.

Native compilation and repeated complete runner unit suites precede a new
clean-source nine-window proof. Earlier zero-time predictor failures stay
failed and immutable. A prospective cycle-work proof supplements, rather than
substitutes for, all existing performance acceptance and certification evidence.
