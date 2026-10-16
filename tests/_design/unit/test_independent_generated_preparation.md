# Test Design — independent generated-artifact preparation

## Purpose

Require independent Release and sample-free readiness construction to use the
same governed candidate-preparation boundary before immutable profile execution.
Neither path may invoke blanket generation or substitute a partial artifact
check for the complete registered inventory.

## Description and authority

The generated-artifact registry owns generator, verification, automatic-repair
and direct-dependent relationships. The shared preparation CLI checks the whole
inventory, blocks protected authority-bearing refresh, repairs only canonically
permitted ordinary projections, checks its diff and idempotence, reruns every
family and validates direct dependents. The independent orchestration paths must
delegate to this boundary rather than define another generation policy.

`toolchain.json` continues to own immutable profile membership. The Release
profile command and its inherited early artifact-integrity check remain
check-only; preparation occurs during independent source construction, before
that profile starts. This is certification tooling, not language semantics.

## Scope

In scope are the shared preparation command, independently returned argument
lists, both independent setup call sites, exclusion of legacy unscoped
generation/partial checks, and ordering before profile execution. Existing
artifact-preparation/profile-gate suites own stale, missing, malformed,
unregistered and protected-output behavior. Existing production tests retain
capacity, runtime, provenance, evidence-preservation and no-reuse responsibility.

No tests in this focused suite may execute setup, generation, network queries,
worktree creation, performance readiness, sampling, calibration, signing or a
certification profile. AST checks inspect real orchestration source; command
checks call only the pure shared argument constructor.

## Categories of tests

-   Positive: the common constructor returns exactly `./strling generate
--prepare --json`, and each independent setup uses it once before its
    immutable profile/readiness execution.
-   Negative: unscoped `generate`, partial check substitutes, absent/duplicated
    shared preparation, or moving it after profile execution fail the structural
    contract. The regression must fail on the retained legacy setup paths.
-   Boundary: mutating one returned argument list cannot alter another caller's
    command. The authoritative Release command still selects only its complete
    profile; it cannot gain `generate` or `--prepare`.
-   Interaction: existing registry tests continue to reject automatic protected
    refresh, unrelated mutation, stale authoritative profiles and incomplete
    inventory; source-bound complete preparation is required again after a
    tracked correction, without promoting historical preparation as new proof.

## Completion criteria

-   Focused regressions are red before the correction and repeatedly green on
    native Python and WSL afterward, with no actual profile or sample execution.
-   Production, generated-artifact and immutable-profile direct dependents pass.
-   Governance/static checks pass and the exact correction is committed cleanly.
-   A new clean source gets its own complete inventory gate and prerequisites
    before any authoritative freeze. No authority-bearing output, lock graph,
    security/license scope, performance budget or denominator changes.
