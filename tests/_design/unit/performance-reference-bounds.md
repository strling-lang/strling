# Test Design — Prospective whole-process reference bounds

## Purpose

Prevent a common launch delay from disappearing in a request/control ratio.
Retained actual CLI diagnostics show that favorable ratios can coexist with
much longer complete workloads. Absolute launch-to-exit observations therefore
need a separately frozen reference, not a denominator fitted to candidate work.

## Description and authority

This is an experimental, data-only qualification component, not live admission.
Before new acquisition, fix a 500-basis-point upper margin around the nine-run
reference median. This is a new prospective control tolerance, not a reinterpretation
of an existing performance ceiling, CPU-idle threshold or precision guarantee.
Every reference observation must fit the symmetric median +/-5% band (an unusually
fast reference is also a stationarity warning), and relative reference MAD must
not exceed 500 basis points. A failed reference is retained and cannot be enlarged
using its maximum, discarded observations, holdout data or candidate measurements.

Freeze the complete reference and derived bounds by externally retained SHA-256.
Only then compare nine fresh, source-distinct holdout observations per coordinate.
All comparisons use integer cross multiplication: rounding cannot admit a value
above the exact margin. Holdout failures never refit the reference. Unknown parent
job limits remain unknown; this calculation cannot claim unlimited CPU quota.

## Scope

The independently supplied plan enumerates every process-backed coordinate in
the actual manifest (currently 53: 50 latency and three memory). The artifact-size
coordinate and five functional resource groups remain separately required; no
process time is fabricated for file size. Whole intervals include launch, warmups,
all accepted/rejected attempts, descendants and exit. Their raw acquisition and
complete process retirement must be independently verified by the caller.

Byte hashes and distinct commits prove neither provenance nor independence by
themselves. This module checks exact expected pins, closed shapes, complete ordered
denominators, unique receipts/process births and arithmetic only. Its outputs
always deny certification eligibility, quota qualification and baseline admission.
It neither edits authority nor launches work, changes caps, subtracts overhead,
normalizes wall time, retries or filters any observation.

For each CLI coordinate, also retain all 64 raw request and control samples and
freeze separate nine-run bounds for each marginal median. An interval-only check
can dilute sample-only delay across 512 warmups. Use twice the exact median (sum
of the two middle observations) to avoid rounding a half-nanosecond into admission.
The existing paired estimator and hard ceiling remain independently mandatory.

## Categories of tests

-   Positive: exact nine-run reference and nine-run holdout, all planned coordinates,
    deterministic freeze, complete raw durations and unchanged frozen bytes.
-   Negative: wrong hashes/pins, source or acquisition reuse, missing/extra/reordered
    coordinates/repetitions, reused receipts/process identities, malformed types,
    non-finite/duplicate JSON, injected authority, invalid clock intervals and gaps
    in the claimed denominator. Reject a size coordinate and an incomplete plan
    against the independently supplied complete coordinate list.
-   Boundaries: integer values on either side of the exact 5% boundary, large
    integers, reference MAD, one unfavorable reference and one unfavorable holdout.
-   Discrimination: equal request/control slowdowns leave their ratio unchanged,
    but complete-interval bounds reject 10% and 50% common-mode slowdowns. Delays in
    launch, warmup, gaps or exit are not omitted merely because sample medians agree.
    Sample-only common-mode delay must fail the marginal checks even when its
    dilution across warmups would pass the whole-interval bound.
-   Integrity: tampered frozen bounds must fail even if the caller supplies the new
    byte hash; independently pinned original reference statistics are reconstructed.

## Completion criteria

Focused and direct-dependent Native/WSL tests pass before empirical qualification.
Fresh reference nine and independently acquired source-distinct holdout nine,
all 12 conditioning obligations, all 54 workload coordinates, original performance
ceilings/sample counts, challenge discrimination, complete raw provenance and
independent trust remain necessary before any live-policy promotion. In particular,
this component alone does not solve ancestor-quota provenance or establish that a
5% whole-process bound detects every regression in the governed workload.
