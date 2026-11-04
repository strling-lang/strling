# Deterministic certification contract

Contract identity: `strling-deterministic-certification-v1`.

Authority: repository owner decision of 2026-11-02, superseding the
performance-inclusive acceptance scope for the new H08 candidate. This is a
deliberate reduction in certification scope, not an equivalence claim.

## Mandatory scope

Certification MUST enforce functional and semantic correctness, compiler and
parser behavior, normalization, lowering, portability, real-engine conformance,
binding compatibility, structural safety, memory safety, bounded-operation
correctness, security, dependency vulnerabilities and license compliance,
public contracts, architecture, governance, static analysis, formatting,
deterministic builds, generated-artifact integrity, source integrity, and
required cross-platform tests.

Evidence MUST remain complete, source-bound, independently reconstructible,
and fail-closed. Independent Release execution, restricted signing, immutable
trusted verification, required source-distinct verifier qualification and
promotion campaigns, and guarded closure remain mandatory. The existing
`WVR-SEC-VSCE-LICENSE-001` waiver retains only its original scope.

## Excluded quantitative acceptance

Latency, startup timing, throughput, benchmark regression thresholds, CPU
utilization and scheduling, memory-performance measurements, statistical
normalization, host-idle admission, calibration, baseline comparisons, and
performance sample acquisition MUST NOT participate in authoritative
acceptance or its transitive prerequisites. Missing performance measurements
MUST NOT make authoritative evidence incomplete. Profiling privileges MUST
NOT be an admission requirement.

Preserve standalone performance tools, baselines, and observations for explicit
non-gating engineering use. Defer the Windows process-launch latency and
normalization variability investigations. Actual memory-safety defects and
functional resource-limit violations remain blocking; an operation that mixes
those checks with benchmarking must be split rather than removed wholesale.

The resource evidence contract `strling-functional-resource-v2` preserves the
original frontend, kernel, target, editor/interop, and no-match resource-limit
commands unchanged. Windows benchmark-recorder lifetime and memory-accounting
qualification (`tooling/tests/memory_worker_lifetime.rs`) is a separate
performance diagnostic, excluded from authoritative membership. It does not
test product memory safety. Its platform-disabled zero-test result cannot
establish resource coverage. The earlier resource-v1 envelope is rejected;
its historical results remain unchanged and require fresh candidate execution.

Removed operations are excluded from the new denominator, not passed, waived,
or unavailable. Mandatory denominators MUST be derived from the effective
registered definitions, never historical operation counts.

## Transition and evidence isolation

The amended contract requires a new clean committed source identity and fresh
authoritative Local, Pull Request, Full, and independent same-source Release
evidence. Evidence producers, schemas, readers, attestations, trust rules, and
closure MUST bind the explicit contract identity. Unknown, mixed, stale,
tampered, or incomplete contract evidence MUST be rejected.

Historical performance-inclusive results retain their original interpretation
and status. In particular, the failed Full CLI-startup result, its original
ledgers, and all 64,248 consumed authenticated samples remain immutable and
cannot be reused or relabeled as acceptance of this contract.

The first frozen implementation revision and its signed evidence establish
the effective source revision. This policy document alone does not establish
implementation readiness, an accepted profile, or closure. All integrated
positive and adversarial contract tests and canonical generated-artifact
preparation must pass before that candidate is frozen.

## Certification claim

H08 under this contract certifies deterministic functional, security,
architectural, and evidence integrity—not quantitative performance compliance.
It makes no claim of compliance with the former performance thresholds.
