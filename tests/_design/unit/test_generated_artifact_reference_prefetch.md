# Evaluation — bounded Git-reference census prefetch

Status: rejected experiment; no prefetch implementation is deployed.

## Purpose and authority

Overlap fresh Git-reference directory traversal with the existing bounded node
readers. The registry and Git-authority guards retain every path, byte, metadata,
mode, identity, alias, containment, disappearance and error check. Change only
when the same lazy census is advanced, not its order or membership.

## Scope and bounds

One producer advances the existing `refs.rglob("*")` iterator into at most sixteen
pathnames. It acquires no node payloads or reusable authority evidence. The same
eight node readers and sixteen outstanding/completed futures remain. Traversal
previously overlapped readers on the calling thread; its dedicated thread adds
no second traversal or additional payload reader. No cross-boundary cache exists.
Use condition notifications, not polling. On success, census error or consumer
error, stop and join the producer, allowing its in-flight filesystem call to end.
HEAD validation must still complete before any census or parallel node work.

## Regression categories

-   A blocked first node can overlap advancement to the seventeenth census path;
    the old calling-thread traversal must fail this deterministic regression.
-   The queue never advances beyond sixteen unread paths, preserves duplicates
    and exact order, and propagates the original census exception after prior
    paths. Consumer failure joins the producer without further reader launches.
-   Preserve all existing node readers and raw exceptions, excluded-UI node
    validation, alias rejection, missing-node rules, eight-worker bounds, fresh
    bytes despite unchanged size/mtime, and complete ordered snapshot equality.
-   Run Native/WSL snapshot, preparation, registry and direct downstream consumer
    suites, with integrated artifact integrity first. No generators or profiles.

## Prospective equivalent-workload timing

One immutable six-pair AB/BA/BA/AB/AB/BA comparison runs the complete real integrity
snapshot on the same held source and WSL filesystem. A uses the pinned prior
reference snapshot function; B changes census scheduling only. Require identical
ordered snapshot entries on all twelve runs, unchanged readers and source frame,
retained unfavorable timings and all six pairs. Report full-snapshot time only,
not preparation or whole-certification gains. Do not repeat this experiment to
seek favorable results. Independently audit raw receipts and timing calculations.

## Retained outcome

The same-source six-pair comparison produced twelve identical ordered complete
snapshots, each with 2367 entries. Baseline median was 14.465856280 seconds;
candidate median was 14.4249523475 seconds, a 0.2827619168078725% reduction.
Only three pairs favored the candidate. All unfavorable rows are retained.
This is not convincing evidence that the added threading improves this workload.
Reject the candidate; do not promote it or rerun unchanged for favorable timing.

The candidate passed 111 Native tests plus seven POSIX skips and all 118 WSL
tests, including overlap, bounded queue, exact errors and producer retirement.
Its complete source/test/charter bytes and reverseable patch remain in the
immutable diagnostic archive. Restore the two experimental implementation/test
files byte-for-byte to their prior state. Preserve this evaluation, not the
experimental implementation. No generator, product sample or authoritative
profile ran, and no preparation or whole-certification speedup is claimed.
