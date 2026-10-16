# Test Design — Development certification readiness

## Purpose

Prove every selected governed operation without issuing certification or closure
claims when performance operations are intentionally deferred.

## Scope

The authoritative profile registry, exact producer selection, non-authoritative
artifact boundary, ordered denominator, fail-fast execution, partial progress,
and independent no-reuse Release preparation are in scope. Live performance,
acceptance-policy changes, product semantics, and publication are out of scope.

The current composed profiles contain Local38, Pull Request80, Full126 and
Release126 operations. Their shared `generated_integrity@repository` prefix
must remain first, selected and present exactly once, never deferred. Only the
existing one/two/three performance producers may be deferred, leaving exactly
37/78/123/123 selected non-performance operations. These are regression locks
on current canonical membership, not permission to shrink a denominator or
classify a deferred producer as passed.

## Categories of tests

-   Positive: derive Local, Pull Request, Full, and Release membership directly
    from the real registry and retain every non-performance operation.
-   Negative: reject contradictory producer metadata, incomplete coverage,
    nonpassing operations, source changes, and evidence reuse.
-   Authority boundary: authoritative profile, product, and attestation validators
    must reject performance-deferred artifacts even when readiness is green.
-   Orchestration: fail at the first blocking operation, preserve progress and
    terminal evidence, and never invoke the deferred performance producer.
-   Independent Release: use fresh source, setup and generation, retain original
    atomic producer evidence, and record a development-only receipt.
-   Shared integrity: reject omitted or reordered integrity results, even if all
    supplied results pass. Partial progress must retain every unexecuted result
    ID, including the current Local remainder of 36 after its first operation.
-   Preparation boundary: require exactly one canonical
    `./strling generate --prepare --json` after setup and immediately before
    independent readiness. Reject a blanket generator or partial-check stand-in;
    actual preparation, profile and performance execution are stubbed in tests.

## Completion criteria

Every governed result ID is selected or explicitly deferred, never relabelled.
Focused tests pass on the exact Linux profile host; the runner-bundle fixture also
passes on Windows. All readiness artifacts remain invalid as authoritative
Full/Release evidence. Final certification still requires the normal denominator.
