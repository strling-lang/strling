# Test Design — adversarial evidence writes

## Purpose

Verify deterministic, provenance-preserving persistence of registered empirical
evidence. This is an I/O and generator test charter, not language authority.

## Scope

The adversarial generator must retain all existing validation, exact runtime
execution, repeated observations, fingerprints and zero-finding requirements.
Unchanged serialized shards and envelopes need no write; changed contents must
still be persisted. I/O errors must propagate rather than be classified green.
No filesystem, security, host setting, sample count or certification waiver is
changed.

## Categories of Tests

-   Identical evidence: every output byte remains unchanged and no write occurs.
-   Source-only refresh: only the envelope is rewritten; all 41 shards retain
    their exact bytes.
-   Changed observation: the affected shard and envelope are written and the
    complete sharded round trip retains the new data.
-   Write failure: a changed shard raises the original I/O error; the preceding
    envelope and observations are not silently replaced or accepted.
-   Read failure: inaccessible existing output raises the original error;
    unreadability is never mistaken for missing or matching content.

## Completion Criteria

Run these regressions before implementation, then repeatedly after correction.
Run the complete existing adversarial unit suite and the registry's exact
generator and verifier. Independently review output differences, complete
denominators and retained failed receipts. Passing persistence tests is not
performance or authoritative certification acceptance.
