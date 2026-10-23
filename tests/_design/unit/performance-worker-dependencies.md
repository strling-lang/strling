# Test Design — memory-worker build dependency isolation

## Authority and scope

The existing performance runner manifest and complete release artifact contract
remain authoritative. A memory-only functional diagnostic build may select only
the kernel and JSON dependencies actually used by the unchanged worker. This is
preparation selection, not permission to omit any profile, artifact, measurement
or gate. Its output is not a canonical performance predictor.

## Cases

-   Default Cargo builds retain both binaries and all full-runner dependencies.
-   Public API and interop dependencies are optional only for explicit
    `--no-default-features --bin strling-performance-memory-worker` builds.
-   The full runner requires its feature, so incomplete dependency selection cannot
    silently yield a partial runner.
-   Declared release-profile settings, toolchain, workload sources and required
    performance ceilings remain unchanged. This static check does not establish
    compiler-command, generated-code or runtime-performance equivalence.
-   Complete certification builds retain their original default-feature commands;
    the build-artifact tests guard those exact commands and all required outputs.

Removing interop's native-library outputs changes Cargo's dependency LTO planning:
the worker-only kernel compilation can use `linker-plugin-lto` where the full
dependency graph does not. Unchanged top-level profile settings therefore cannot
justify substituting a worker-only artifact for a full-build measurement.

## Integration and timing proof

Read-only locked/offline Cargo metadata must show the full dependency graph for
the default selection, and omit public/interop packages from the worker-only
resolved graph. Existing lock bytes must remain identical; catalog input review
is explicit and must not regenerate dependency or certification evidence.

Build fresh full-dependency and worker-only variants with the same compiler,
source, release configuration and worker target. Require exact worker executable
identity before calling them equivalent outputs. Retain raw commands, compiler
logs, elapsed times and owned process retirement. Report observed build timing
separately from full-profile and certification timing; no complete-campaign
speedup follows from this narrower comparison. A failed identity comparison is
retained as failed; functional agreement or favorable timing cannot retroactively
replace that requirement. Performance experiments must use the full default
dependency graph and record any intentional optimization change separately.
