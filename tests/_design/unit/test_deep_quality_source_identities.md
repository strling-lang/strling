# Test Design — Deep-quality generated source identities

## Purpose

Detect stale deep-quality source identities before expensive certification work,
without changing quality policy or accepting generated agreement as runtime proof.

## Scope

The generated-artifact registry, independently declared hygiene census, canonical
identity-only refresher, read-only verifier and synthetic contract fixture are in
scope. Product semantics, live or historical evidence, performance baselines,
sampling, thresholds, locks and signing/trust authority are out of scope.

## Categories of tests

-   Positive: both outputs are registered, every referenced source is mapped, and
    fresh canonical data passes deterministic check mode without mutation.
-   Negative: stale identities, missing or malformed outputs and removal from the
    registry fail before later build-backed checks; the independent census still
    detects removal of the family together with its registry census entries.
-   Governed refresh: preparation detects but never automatically regenerates
    this mixed authority/identity family. The explicit canonical refresh is
    deterministic and idempotent, preserving every nonidentity field and file.
-   Serialization ownership: repository formatting delegates only these two
    outputs to the registered serializer; check mode rejects semantically equal
    but noncanonical bytes without writing them.
-   Authority boundary: live or historical evidence cannot be rewritten as a
    synthetic fixture; quality definitions, budgets, partitions and denominators
    remain unchanged. Actual deep-quality execution is still required later.

## Completion criteria

Focused native and Linux tests pass, including the real registered check/refresh
commands in isolated fixture directories. Existing generated-artifact and
deep-quality regression suites remain green. The complete current inventory is
checked before a new clean candidate is frozen; no failed candidate is replayed.
