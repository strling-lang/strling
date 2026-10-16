# Test Design — profile environment preflight

## Purpose

Ensure Pull Request certification validates the same exact runtime and offline
Maven inputs whether its quality runner is imported or launched directly as a
script. A test runner's package cache or repository-root import path must not
conceal a broken production bootstrap.

## Description and authority

`toolchain.json` defines profile membership and offline execution policy.
`tooling.exact_runtime_provision` owns the canonical preflight entrypoint;
`governance/exact-runtime-toolchains.json` and the registered JVM release graph
and verification metadata retain their existing identity/hash requirements.
The orchestration boundary delegates to that package entrypoint at its owning
repository root, rather than importing package-only dependencies as siblings.
This is certification tooling behavior, not language or product semantics.

## Scope

In scope are the subprocess command, owning checkout, inherited environment,
fresh direct-script import context, success/failure propagation, and unchanged
non-Pull-Request behavior. Existing runtime/provision tests retain responsibility
for rejecting missing or wrong runtimes, wrong Maven artifacts and unprepared
caches. No provisioning, dependency refresh, network access, benchmark,
calibration, authenticated performance sample, profile execution or publication
is permitted in these focused regression fixtures.

## Categories of tests

-   Positive: a successful canonical validator completes the preflight; its
    command is the same interpreter with `-B -m`, the canonical package module,
    `--check-pull-request --json`, and the actual repository as its working
    directory. Environment variables are inherited, never broadened or replaced.
-   Negative: a nonzero validator exit, even with success-looking stdout,
    preserves the underlying failure and fails closed with the existing
    environment-preparation guidance. A process-start failure is not a pass.
-   Bootstrap: a fresh interpreter loads the quality runner with only its
    script directory on the repository import path and no cached `tooling`
    package. The canonical validator boundary is stubbed, not its predicates;
    the runner must delegate correctly without injecting the repository root
    into its own import path. This reproduces a context normal unit imports miss.
-   Interaction: Local, Full and Release do not acquire a new Pull Request
    preflight, while existing generated-integrity ordering tests continue to
    require the freshness gate before environment preflight or expensive work.

## Completion criteria

-   The fresh-script regression fails against the broken bootstrap and passes
    after the correction, independently of locally installed governed runtimes.
-   Focused positive, error, wrong-exit and non-applicable-profile cases pass
    repeatedly on native Python and WSL.
-   Actual WSL atomic script-mode and canonical module preflights both pass
    the unchanged real runtime/Maven checks; these are not profile results.
-   Quality, exact-runtime, generated-artifact/profile-ordering and affected
    governance/static regressions pass before a new clean candidate is frozen.
-   No runtime identity, lock, license, security, performance, sample-count,
    profile-membership or trust requirement changes.
