# Test Design — bounded snapshot read-ahead

## Purpose and authority

Reduce ordered snapshot head-of-line blocking without changing any reader,
snapshot boundary, census, fingerprint, metadata check, alias rejection, or
certification decision. The generated-artifact registry remains authoritative;
this is orchestration scheduling, not a new evidence or admission policy.

## Prospective implementation and tests

Keep the existing one-to-eight active reader limit. Queue at most twice the
selected worker count (maximum sixteen futures), including completed results
waiting for their ordered turn. This finite look-ahead lets an idle worker start
the next path while an earlier path is still reading. It is not a content,
metadata, directory, or cross-boundary cache. Readers still consume every full
file and the original fresh metadata operations.

-   A blocked first item must allow the ninth item to start with eight workers.
    This regression fails on the original eight-future scheduler.
-   Exactly eight readers may be active; at most sixteen futures may be retained.
    Smaller worker settings scale both bounds. Invalid settings still reject.
-   Return results and select errors in input order, regardless of completion
    order. Join all submitted work before returning an error; return no partial
    snapshot. Reader errors and iterator errors must retain their types/causes.
-   Preserve duplicates, missing paths, binary content, fresh modes, same-size
    same-mtime mutations, links, containment, Git node identity, symbolic-ref
    aliases and narrow UI-bookkeeping handling through the existing suites.

## Equivalent-workload measurement

Before any timing, pin the old and proposed implementation and the complete
source frame. Run one immutable six-round ABBAAB comparison on the real complete
integrity snapshot with its original tracked, governed and Git-authority census.
Use the same eight active readers for both schedulers. Preserve every timing,
snapshot, failure, and source/owner receipt. Require identical ordered snapshot
entries, not only matching aggregate counts. Do not visit ignored retained
verifier copies or run generators, profiles, product samples, or reference fits.

Report medians only after all six rounds complete. A slowdown stays in the
record and is not retried or filtered. This can establish a bounded snapshot
component improvement, not a total preparation or certification speedup. Reject
promotion of the scheduling change if the equivalent workload does not improve.

## Completion boundary

Run the integrated performance-artifact integrity check first, focused red/green
tests, native and WSL snapshot/preparation/registry/profile-gate dependents,
formatting, governance and exact-path source checks. Preserve all historical
attempts. Any accepted correction needs a clean engineering commit and complete
canonical preparation before a later source freeze. No performance threshold,
sample count, unknown-quota rejection, security control or trusted pin changes.
