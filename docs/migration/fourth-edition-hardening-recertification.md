# Fourth Edition hardened-core recertification

## Candidate and authority

V4-H08 started from clean `dev` checkpoint
`61338f1581e8ecf436fc59acbfae28a603a90382`, identical to fetched
`origin/dev`. The machine profile authority is `toolchain.json`; release-state
and waiver authority is `governance/release-policy.json`; execution and result
semantics are governed by `governance/certification-profiles.md`.

The registered lifecycle requires the following sequence for this final
hardened-core boundary:

1. exact clean-source Local and Pull Request deterministic preflight;
2. one canonical Full 1.29.0 execution through the supported WSL aggregate
   controller, with its governed sampled operation delegated to the
   baseline-authenticated native Windows host;
3. after terminal green Full, a separate clean-worktree Release 1.29.0
   execution through the governed no-reuse production launcher for the same
   source SHA, with no result or performance-sample reuse;
4. creation of one trusted, signed local evidence bundle for both results;
5. cheap cloud verification of signature, source, contract, evidence, waiver,
   runtime, invocation, and aggregate integrity;
6. final adversarial, waiver, identity, generated-state, and clean-tree review.

Full and Release currently share the same 125-result operation envelope but
retain distinct profile identities and independently produced evidence. Each
includes exact target runtimes, interop/runtime matrices, deep-quality checks,
networked dependency risk, supply-chain dry runs, and the native governed
performance/resource producer. The active performance baseline authenticates
this native Windows machine, so a hosted Linux runner cannot substitute for
the sampled operation. Certification never authorizes publication.

## Steering amendment and architecture audit

The H08 steering amendment makes the qualified local environment authoritative
for expensive certification. The previous workflows provisioned exact engines
and recomputed Pull Request, Full, Release, runtime, and sampled evidence in
GitHub. Existing profile artifacts already bound source, profile definitions,
operation results, runtime declarations, sample consumption, and deterministic
evidence fingerprints. Existing release-supply-chain tooling already used
SHA-256 and in-toto/SLSA statements for package artifacts. Neither mechanism,
however, authorized a local certifier, signed a complete certification root, or
prevented a contributor from hashing fabricated evidence.

The bounded extension adds one trust policy and one attestation contract rather
than a parallel result system. Full and Release remain the sole expensive result
authorities. `./strling certification attest` validates those existing profile
artifacts, collects durable evidence, binds the exact source commit/tree,
profile/operation registries, kernel and interop trees, all target profiles,
exact runtimes, producer invocations, waivers, authenticated samples, and the
real-engine result, then signs the deterministic SHA-256 root with the governed
Ed25519 SSHSIG identity. The private key remains outside Git.

Normal cloud CI uses the verifier and trust policy from the trusted base
revision and treats the candidate checkout only as data. It rejects stale
source, wrong profile or invocation, missing/changed files, aggregate
contradiction, unapproved waiver, malformed signature, or untrusted certifier.
It performs no Full/Release execution, performance sampling, real-engine corpus,
or multi-language certification matrix. Delivery consumes the same verifier;
successful verification establishes `CLOUD_VERIFIED`, never `PUBLISHABLE`.

The evidence bundle is added in a post-certification closure commit. The trust
policy permits only the bundle, this record, the migration ledger, and active
task-state update in that closure. The verifier proves the certified commit is
an ancestor and rejects every other changed path, preventing a record commit
from silently changing the hardened source. P20 must bind packages back to the
recorded certified source through the existing supply-chain provenance path.

The registered Pull Request profile retains its exact-engine operation for the
canonical local preflight. Only its automatic cloud recomputation is replaced;
the profile contract and semantic hardgate are not weakened.

## Deterministic preflight correction

The first exact-SHA Pull Request preflight, hosted run `34213813721`, passed 77
of 78 operations and stopped before sampled certification. The sole failure was
not semantic: the enforced `dependency-license-evidence` generated-family
`--check` rebuilt evidence over the network inside the nominally offline Pull
Request profile, and a pub.dev request reset.

The correction makes check mode validate the checked-in 54-entry projection
without network access. It verifies document identity, canonical ordering,
fingerprint, required fields, duplicate absence, complete Dart/Lua/CPAN/Python
lock identities, and archive hashes bound by the locks. Network-authenticated
official archive retrieval and license classification remain the unchanged
registered `--write` producer. The exact producer reproduced fingerprint
`sha256:248f426df0e64c38252695eed556b1ae765e1324d72fc012441b3809084559ed`
without changing the governed output.

The first Full attempt at correction checkpoint `9f85a00c` reached the governed
native performance producer but the Windows host did not satisfy the unchanged
quiet-host conditioning policy. Its atomic result records zero started
coordinates and zero authenticated samples. The remaining already-doomed
aggregate work was stopped; this was an environmental pre-sample attempt, not a
measured failing attempt and not certification evidence.

The next clean candidate Full run completed 122 operations before two newly
published dependency/security prerequisites failed and the native performance
producer rejected a Windows build-identity change before sampling. The result
recorded zero started coordinates and zero authenticated samples. The
dependency repair updates only the affected transitive locks, classifies the
exact JUnit BOM through the existing test-classpath policy, and regenerates the
Perl Makefile with the governed WSL Perl rather than consuming a
Windows-generated ignored build file. The remaining Windows identity mismatch
is governed by the existing immutable environment-rollover boundary; it cannot
be papered over or treated as a performance pass.

## Certification result

The historical deterministic candidate was
`7e58c04ad412fedef46f71b7d999dea56107f4e1`. Local 1.15.0 passes 37 of 37
operations with evidence fingerprint
`6ee2782e33fed8de376c832c1bb5db98d81fe67a6eee7d8732669cdf8df2531d`.
Pull Request 1.21.0 passes 79 of 79 operations with evidence fingerprint
`82bc93a9ec0b93abffbd8485a24ddec618b2b9ed61f026ff773489ea7a39d533`.
Both have zero failed, waived, unavailable, or incomplete operations, and
architecture remains 33 of 33.

The exact-engine result uses pinned Node 22.23.2, CPython 3.11.15, PCRE2 10.42,
and PCRE2 10.43. It records 41 programs, 95 subjects, 205 compile decisions, 48
governed refusals, 1,531 executions, 1,129 comparisons, and zero findings. Its
deterministic result fingerprint is
`5a73150aab9ec500363393a658cd410d33074dad172f762705d9d56f629ddbc8`.
All 148 historical audit findings remain resolved. The sole accepted waiver is
still `WVR-SEC-VSCE-LICENSE-001`.

The Program Owner subsequently authorized the existing immutable same-host
environment rollover. Windows `26200.9278` remains archived with its original
identity and evidence; Windows `26200.9445` was independently qualified and
measured once under the unchanged sampling, statistical, conditioning,
isolation, and acceptance rules. The active baseline is
`5a472de9302c8b5fd48a6a1c9c7970f747800f268185976c3de1f93db9e7e07b`, bound
to environment
`404f22e91201485db7563d518d19304077bb73b94f480dba3d4bc964dea6e4bd` and
historical calibration source `5f4a81643f33440be96760855fd0cedbe3add08f`.

The subsequent measured Full at candidate
`f3bb5ffb84564eb558ad58be9875575d147fa7b1` passed 123 operations, retained
only `WVR-SEC-VSCE-LICENSE-001`, and failed one of 125 operations after seven
coordinates and 385 authenticated samples. The sole regression was
`latency:pcre2-lower-serialize/fixture:semantic-common`: median `451844 ns`
against unchanged relative and absolute ceilings of `273845 ns` and
`298740 ns`. Full evidence fingerprint
`4df11302eae81923fa6d7f568d4d1d5c53af11cabd3c65fb18897f1b1e18f1f4`,
performance evidence fingerprint
`970afce604501ac18f008ea32f255e16a6667e97481e3cf1c055bc406686f808`,
invocation `744be042ede544aa83906e1529d3f9c7`, and source artifact SHA-256
`8ed2021c6757c64cb4a7fb968acdba55091fa86ceffde4cd6b10fe0af0f4b2c4` preserve
the consumed failure. Release correctly did not start.

Diagnosis traced the regression to repeated validation, canonical
serialization, and hashing of the same already-validated semantic-fact-expanded
profile during target lowering. The correction extends the existing immutable
`TargetProfileSet` reference path to PCRE2, ECMAScript, and Python lowering.
Exact profile resolution remains mandatory on every invocation, stale or
mismatched references fail closed, and direct versus reference-based plans are
tested for structural equality. The initial correction claimed that profile
loading, validation, and immutable-reference creation were certified untimed
preconditions. The resumed calibration-source audit below rejects that claim
and restores the original workload before accepting any new measurement.

The `f3bb5ffb` sampled attempt is permanently consumed and will not be retried.
Any subsequent Full must bind a substantive corrected source SHA, pass the same
unchanged performance policy, and precede same-SHA Release. Until that sequence,
attestation, and cloud verification finish, P20-T02 remains paused and no
hardened source baseline is declared.

No package is published, no release tag or GitHub Release is created, `main`
is unchanged, and P20-T02 does not begin in this task.

## Resumed correction and verification design

Execution resumed at `47f68db6fd21b4fa7928a85e2b6fc3a5ff2a5227` on `dev`,
preserving the eleven reported local changes. The saved Local result has 34
passes, two formatter failures, and one incomplete performance-resource
source-identity result. The source changes are formatting-only; structural
comparison of the six JSON changes finds only source hashes and their dependent
fingerprints. Baseline measurements, limits, sampling rules, statistics, and
the accepted waiver are unchanged. The original `dedf9e09` rollover fingerprint
and later identity-only projections are distinct recorded identities of the
same measurements, not new calibrations. Commit `232c48d6` records this
mechanical correction. All 84 focused architecture and evidence-contract tests
pass. The complete identity-generation and policy-formatting sequence is
byte-stable on a second pass; deep-quality check and performance-resource Local
pass. The resulting active projection is
`d1569ecb34bd4e454cd3e83e7b5db222c29cf995088b25b5004f58cbf819c467`.

Both sampled failures remain consumed: `5f38bf1a` authenticated 192 samples,
and `f3bb5ffb` authenticated 385. Recovered original output identifies the
earlier LSP failure as six quantifier-matrix subprocess timeouts at the existing
five-second debug-compiler limit, with 566 tests passing. The unchanged registered
suite subsequently passed all 572 tests in 174.99 seconds; the later `f3bb5ffb`
Full also passed `test@lsp`. This disposition is independent of the PCRE2
lowering correction.

A new bounded adversarial probe exposes an incomplete-bundle acceptance gap in
the existing attestation verifier. A trusted signed fixture can omit required
profile operations, authenticate only one performance sample, reuse performance
invocation identities between profiles, and omit production-launcher evidence while still
receiving `CLOUD_VERIFIED`. Existing passing tests do not establish rejection
of these cases. The next implementation checkpoint must close these gaps using
the existing operation, performance, structured-evidence, and no-reuse launcher
contracts before freezing or sampling another candidate. Trust-root identity,
the narrow closure allowlist, waiver scope, and acceptance thresholds remain
unchanged. Event-specific trusted-verifier selection is also under review;
historical general descriptions do not establish equivalent isolation for every
workflow event.

The corrected validator passes all 69 integrated attestation/production tests.
It reconstructs complete profile and performance denominators, statistical and
conditioning checks, original atomic streams and exact-engine observations,
product results, independent Release receipt, and security aggregates. Waiver
validity and scope come from the trusted authority. Authenticated candidate
fixture/profile data is passed to trusted validation code explicitly; isolated
Python imports reject candidate tooling as an import source. Empty captured
stdout/stderr is accepted only for execution-stream roles. No trust key, waiver
record, acceptance threshold, or closure allowlist changed.

Calibration-source comparison also supersedes the earlier claim that profile
validation was an established untimed precondition. `fafd1879` moved initial
capability/planning validation and hashing out of the timed section, and
`335fffe6` substituted prepared-reference lowering for the calibrated raw-profile
entrypoints. Commit `4836dd94` restores the runner byte-for-byte to calibration
source `5f4a81643f33440be96760855fd0cedbe3add08f` and adds a workload-boundary guard.
The useful product APIs remain available, but their prepared-input measurements
cannot replace the calibrated workload or establish normal compiler speedups.

The bounded product correction targets redundant canonical-JSON map rebuilding:
preserve already-sorted map allocations while recursing through children, and
retain the original sorting fallback for insertion-order representations. This
retains the existing dependency API floor and exact digest bytes.
Commit `fe17793b` records this correction. Three independent digest and governed
target-profile tests pass on Rust 1.75.0, and the same three pass in an isolated
insertion-order feature harness on Rust 1.85.1. The latter does not establish
Rust 1.75 compatibility for that downstream feature's newer transitive lock.
All 50 focused lowering/planning tests pass. Registered shared-engine and
standard-library generators/verifiers reproduce byte-identical evidence. The
adversarial producer completes two identical executions with zero findings;
all 41 raw observation shards are unchanged. Its source-bound envelope is
refreshed. No performance result is inferred from these checks; the unchanged
benchmark still requires authorized sampling.

No new sampled attempt, Release, attestation, cloud acceptance, or publication
is claimed by this reconstruction. `main` remains
`664d08de53565929c8f62379b006cd29f93b239f`. H08 is in progress and P20-T02
remains paused.

That `main` revision contains neither the verifier, trust registry, nor the
integrity workflow. Therefore it cannot supply a PR-base integrity run yet.
The authorized `dev` push can use a separately pinned reviewed verifier commit;
success there will not establish `main` bootstrap or authorize integration.

## Exact-source Local failure and test correction

The clean candidate `9b305f3ddad5b74857d960d8d102c1d025b23085` completed Local
profile definition 1.15.0 on 2026-09-12 at 21:22:18 UTC with 36 passed operations
and one failed operation out of 37, with no waivers or incomplete operations.
The retained evidence fingerprint is
`14b8af8d02de929740e8d3eda759f93c4eed171ae36dda96a9a352561e8c576c`.
The sole failure is `lint@core`: Clippy 0.1.75 rejects `format_collect` in the
new canonical-digest test. Core formatting, typechecking, and tests passed.
The complete artifact, log, and terminal execution receipt remain under
`target/codex-tools/h08-candidate-9b305f3ddad5b74857d960d8d102c1d025b23085/`;
this result cannot qualify the candidate for Pull Request or Full.

The correction writes each digest byte into one preallocated string in the
test. It changes no production hashing behavior, expected digest, benchmark,
or threshold. Core formatting, Clippy, and all three canonical-digest tests
pass on Rust 1.75.0. All three affected registered observation generators and
verifiers pass. Shared-engine evidence, standard-library evidence, and all 41
adversarial raw observation shards remain byte-identical. The adversarial
envelope changes only its execution timestamp, source commit, changed test-file
hash, and dependent checksum; two repeated executions again report zero
findings. The retained comparison is
`target/codex-tools/certification-forensics/h08-observations-lint-correction/comparison.json`.
A new clean committed candidate must restart deterministic qualification.
No Full sample or Release was started at the failed Local candidate.

The owner's publication-account amendment applies after H08 closes, beginning
with P20-T02. It preserves the prerequisite sequence and does not authorize
public publication, production tags, or integration into `main`.

**BLOCKED — NO-GO FOR P20-T02.**
