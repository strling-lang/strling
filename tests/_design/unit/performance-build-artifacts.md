# Test Design — performance build artifact boundaries

## Purpose and authority

The performance build helper must not report success without every required
artifact. The existing runner bundle and release artifact contract in
`tooling/performance_resource_certification.py` controls the expected outputs;
this is an implementation regression, not a new performance policy.

## Scope

Validate each successful Cargo command's outputs before launching the next
build, and recheck all outputs before creating the bundle. Preserve the same
three commands, order, flags, working directory, timeout, failure receipts and
canonical-drive cleanup. Do not run conditioning, samples or profiles.

## Cases

-   All four required files produce the existing bundle and fingerprints.
-   Missing runner or memory worker stops after the first command; missing kernel
    stops after the second; missing interop stops after the third.
-   Directories cannot satisfy file requirements; all missing paths are retained.
-   Existing files cannot override a failed or unavailable command.
-   A later command removing an earlier artifact fails the final recheck.
-   A missing build output cannot reach measurement placement.
-   Canonical-root cleanup runs after an early artifact failure.

## Completion criteria

The negative tests fail against the former implementation, pass after the
correction, and execute on Native Windows and WSL. Real temporary files exercise
bundle construction; mocked Cargo is explicit and does not certify a build.
Direct-dependent scheduling and performance-contract tests remain required.
Any timing fixture is diagnostic only, never a measured certification speedup.
