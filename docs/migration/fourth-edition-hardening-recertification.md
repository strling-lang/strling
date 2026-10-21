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

## Exact-source Pull Request failure and workflow-test correction

Candidate `a76fafb3446c2708224c891ac71b048c61ed10c1` passed all 37 Local
operations under definition 1.15.0, with evidence fingerprint
`398da34b279fc9bbacc13c8f31d266bc4bbd89fc55dc25e04dac9b95ab29445e`.
Its Pull Request profile definition 1.21.0 completed on 2026-09-13 at
01:21:21 UTC with 78 passed operations and one failure out of 79; no operation
was waived, unavailable, or incomplete. Its evidence fingerprint is
`59985e7503903fdda7eb688b09bc5a6aac6f571980914bec6d756acda065fc41`.
The source and tree remained clean and unchanged throughout both runs.

The only failed operation is `test@repository`: 1,173 unit tests ran with one
failure and one skip. The captured failure output was truncated by the profile
reporter. A focused reproduction identifies the obsolete assertion in
`test_profile_job_prepares_every_governed_component` that still requires
`./strling certification verify` in CD. The reviewed workflow instead runs the
isolated verifier from pinned source `f47bd092`, with the candidate supplied
only as data. All other Pull Request operations passed, including LSP, core,
interop, binding tests, source identities, architecture fitness, and the strict
real-engine audit.

The correction replaces the obsolete command-text assertion with the existing
structured checkout validator. It requires the governed immutable verifier
checkout, exact candidate event identity, credential isolation, trusted Python
invocation, and Bash failure propagation. The existing CI prerequisite and CD
no-recomputation assertions remain. All 53 focused release-supply-chain
architecture and governance tests pass, including the established negative
trust-boundary cases. No registered generated family depends on the changed
test or this record.

The complete profile artifacts and execution receipts remain under
`target/codex-tools/h08-candidate-a76fafb3446c2708224c891ac71b048c61ed10c1/`.
The focused failing reproduction and corrected test result are retained in
`target/codex-tools/h08-workflow-assertion-before.log` and
`target/codex-tools/h08-workflow-assertion-focused.log`. This correction changes
no workflow, product code, trust authority, benchmark, or measured baseline.
No Full sample or Release was started at this candidate. The next clean commit
must obtain its own complete deterministic qualification before Full.

## Release preparation defect and deterministic requalification

Candidate `58abe48baa916d2b5735d135f654b3ff945d133f` passed all 37 Local
operations under definition 1.15.0, with evidence fingerprint
`d71cf62c47777f766387d0e11d799d798f26a049997adf7a17e0e1e921a26afd`.
An independent audit confirmed the exact clean source, ordered operation
denominator, aggregate, execution receipt, and fingerprint.

Static preflight then found a deterministic Release preparation defect.
`materialize_governed_production_inputs` still required the historical
`artifacts/production-certification` prefix introduced in `1362339f`.
Commit `f67681b5` had moved that same historical receipt into tracked inputs at
`tests/architecture/legacy-removal/1.0/source-production-candidate-certification.json`.
Commit `d1e24c92` updated its formatted-byte hash. The current tracked file
matches the governed SHA-256
`d4b90eeca9c3d2d5c82a311ea99b7bd3ed1edf9a0310bcb62f3cb5b780544ab3`,
but the old prefix check rejects it before Release execution. A bounded
reproduction confirms that rejection without creating a Git worktree or
launching any profile.

The running Pull Request profile at `58abe48b` was deliberately stopped at
2026-09-13 03:15:04 UTC. Its wrapper retained exit 143 and unchanged clean
source; the separate cancellation record identifies the signaled process
tree and reason. This is an interrupted, unqualified profile, with no terminal
aggregate or passing claim. Its log, execution receipt, cancellation record,
and observations remain under
`target/codex-tools/h08-candidate-58abe48baa916d2b5735d135f654b3ff945d133f/`.
No Full or Release was started at that candidate.

The correction verifies Git-tracked historical input directly in the clean
Release checkout without copying from the external authority tree. Literal
Git path matching, contained regular-file checks, and the governed hash reject
untracked, missing, altered, linked, or escaped input. Git errors fail closed.
The existing ignored historical-input route retains its bounded prefix and
hash checks, with an explicit destination containment check before copying.
The inventory, historical bytes, trust registry, pinned verifier, benchmarks,
baselines, and sampling rules are unchanged.

All 26 focused production-launcher tests pass, including the actual tracked
inventory path, rejection of missing or altered tracked evidence despite a
valid external copy, untracked-file rejection, Git failure, and destination
escape. The retained suite log is
`target/codex-tools/h08-tracked-input-focused.log`; the failing reproduction is
`target/codex-tools/h08-tracked-production-input-reproduction/reproduction.json`.
The generated-artifact registry maps no family to this launcher, its test, or
this record. Independent review confirms the correction fits existing H08
scope and requires no new trust authority.

The owner now runs the governed Full command after the agent completes all
remediation, runtime preparation, and fresh terminal-green Local and Pull
Request qualification at one clean committed source. The agent must not start
Full. On the owner's completion message, inspect the authoritative Full
artifact, atomic evidence, sample ledger, and failed operations before deciding
whether the same-source independent Release may begin. A sampled failure
requires proven remediation and a new substantive qualified candidate; an
unchanged retry is permitted only with preserved proof of zero authenticated
samples.

## Windows 26200.9457 performance-baseline rollover

Candidate `be8115996e0211bf5455e047990bf045cf35d3fe` completed Full
with 123 passed operations, the existing
`WVR-SEC-VSCE-LICENSE-001` waiver, one unavailable operation, and no
failures. The unavailable operation was
`performance_resource_full_certification@repository`; native admission
rejected Windows build `26200.9457` against the active `26200.9445`
environment before benchmarking. Structured invocation
`d070493b417242ab8b28becefba4b56f` records
`authenticated_sample_count=0`, `completed_sample_count=0`,
`coordinates_started=0`, `coordinates_completed=0`, no current coordinate,
sample state `zero`, and no integrity error in both progress and terminal
result artifacts. The profile artifact, progress ledger, and console log agree.
The preserved zero-sample proof makes rollover work policy-safe; it does not
reinterpret the unavailable Full as passing.

The repository-defined `reset-environment` operation archived baseline
`dffac2d05330d2e2cd19edc3d9427bc95b12bb93e5b3cc7b16450e20841a98d0`,
manifest `ee4238d380838683618be88a9f1630dcb1013e16e67deb70503dff8d90d3336c`,
and their evidence byte-for-byte under the existing history convention.
Native Windows qualification then proved that the only old/new environment
coordinates were `os_version`, `host_attestation.host_os`,
`host_attestation.attestation_fingerprint`, and
`host_attestation_fingerprint`. The edition and release remain Windows 10 Pro
25H2; the build changes from `26200.9445` to `26200.9457`, and the attestation
fingerprint changes from
`72c1708cb95a4ef85ac55584163f9715476f7c60d524a5fedfc730ed52e902cd` to
`4e1abce33238cb78de84841aefe32e706636f570fab8158bb2b224d37b07c19f`.
Bare-metal status, i9-14900HX identity, 32-logical/24-physical topology,
logical CPU 20, CPU set 276, group 0, affinity, CPU-set enforcement, unlimited
quota, high-QoS power policy, fixed 2200 MHz policy, QPC 10 MHz timer, memory,
stepping, microcode, topology fingerprint, Python/Rust/Cargo identities and
hashes, target triple, release profile, and conditioning policy are unchanged.

The rollover exposed two general implementation gaps. Candidate artifacts may
differ from the historical calibration only when Git proves the exact
artifact-source closure changed; unexplained binary replacement remains
rejected. The current candidate also exceeded the historical artifact-size
relative ceiling before remediation. Error-only validation construction is
outlined to contain binary growth. Capability evaluation and portability
planning now share one private validated profile snapshot, and direct lowering
reuses its exact reference only when the supplied profile equals that snapshot;
mutated or stale profiles retain canonical hashing and fail-closed mismatch
handling. This removes redundant canonical profile serialization from the
calibrated success path without changing the benchmark workload or product
semantics.

Governed calibration at clean source
`36d13f24bcf0c182cb926b2f669c7650747fdd64` completed all 54 coordinates
across five repetitions and passed all 54 comparisons against the prior active
contract. The first invocation stopped before sampling when native quiescence
could not be established; the single zero-sample retry passed. Active baseline
`a0f0ab5f3da117efaa6fd907e5696bb865ecba8376ddbd82f714d8adbf32a7cd`,
environment `07046a769a2618588399efd80156976d88f6fcb38886160c542d6757c836e14f`,
and manifest `962897b9c1e5f2a908ab58adcc49473176ca46a86b1edae95f2cda37957070e0`
are generated by canonical repository logic. A clean post-adoption native
qualification reproduces the active environment and artifact identities.

No workload, repetition count, relative acceptance policy, conditioning rule,
isolation rule, or pre-adoption ceiling was weakened. Forty-three calibrated
medians decreased and eleven increased. The largest increase is governed
kernel-plus-interop size: `8,933,888` to `9,794,560` bytes (`+9.63%`), which
passed the old `9,827,276` relative ceiling and `10,720,666` absolute ceiling.
The canonical calibration algorithm then derived the new 10% relative and 20%
absolute size ceilings (`10,774,016` and `11,753,472`) from the accepted new
median. Across all coordinates, 12 derived absolute ceilings increased and 42
decreased; 13 variance-derived relative budgets increased, four decreased, and
the remainder stayed fixed. These are measured derivations after passing the
old contract, not threshold relaxation used to admit the candidate. Complete
old measurements and ceilings remain in the immutable history directory; the
new active document contains the corresponding new values and raw repetitions.

The rollover creates a new certification candidate. Historical Local 37/37 and
Pull Request 79/79 evidence at `be811599` remains useful diagnosis but cannot
qualify the new source. Authoritative certification must restart at Local,
continue through Pull Request, and stop after Full for owner inspection. No
Local, Pull Request, Full, Release, attestation, cloud acceptance, publication,
or tag action was performed during this rollover task.

Because the focused core correction is a registered input to adversarial
semantic evidence, the governed generator was rerun with exact Node 22.23.2,
CPython 3.11.15, PCRE2 10.42, and PCRE2 10.43 runtimes. The regenerated
two-repeat evidence remains at zero findings and passes its offline verifier;
this targeted source-bound refresh is not a profile certification result.

## Post-rollover deep-quality identity remediation

The authoritative campaign at clean candidate
`03ab81b526c54872f7f8cee48dfd268238048293` stopped in Local with 36 passed,
one incomplete, and zero failed operations. The sole incomplete operation was
`deep_quality_local_certification@repository`. Its producer first reported
stale governed identity for `core/src/capability_evaluation.rs`; because that
exception preceded JSON output, the outer runner secondarily classified the
empty structured result as malformed. Every other Local operation passed.
Pull Request and Full were never invoked, so this campaign consumed zero
authenticated Full samples. Its profile artifact, progress ledger, and console
log remain preserved under
`target/codex-tools/h08-authoritative-03ab81b526c54872f7f8cee48dfd268238048293-20260916T123457Z/`.

Complete manifest closure inspection found exactly five stale source paths:
capability evaluation, portability planning, and PCRE2, ECMAScript, and Python
re lowering. Their governed hashes match `be811599` byte-for-byte. Commits
`a3831fda` and `36d13f24` intentionally changed those files to reuse exact
validated target-profile proof during the Windows rollover performance
remediation; the adjacent changed validation and planning helper files are not
deep-quality identity entries. All seven core paths were already H08-authorized,
their focused lowering/capability/planning suites passed, and the 54-coordinate
calibration passed the prior performance contract. The other 50 governed paths
remain current, leaving no unexplained drift.

The canonical `--refresh-source-identities` producer renewed the five source
hashes plus the dependent manifest and synthetic-evidence fingerprints. The
new manifest fingerprint is
`e4a5fb1d6223656f6adafab53a8caee1fa96f792f4966673c964f46f7d1f28e9`.
Mutation tokens, operators, test sources, workloads, denominators, thresholds,
and profile membership are unchanged. The repository formatter preserved the
same semantic fingerprint. The structured producer now converts deterministic
manifest-validation exceptions into an explicit failed manifest check with the
original code and reason, so the operation remains fail closed without the
secondary malformed-result classification.

Isolated deep-quality execution passes Local 1/1, Pull Request 22/22, and Full
36/36. Full includes one manifest check, fourteen property suites, five fuzz
targets, two sanitizer cases, and all fourteen mutants, with zero failed or
unavailable checks. These are isolated producer proofs, not profile results and
not performance sampling. Because tracked certification authority and tooling
changed, the next authoritative campaign must start again at Local, continue
through Pull Request, and stop after Full for inspection.

## Deterministic Perl build and measured-operation overhead correction

The authoritative campaign at clean candidate
`df7ff7370fdec1ae5d8f629d4cbba4d037162a57` passed Local 37/37 and Pull Request
79/79 and then traversed all 125 Full operations, recording 121 passed, two
failed, one waived, and one unavailable. Its structured performance evidence
proves sample state `zero` with zero started coordinates and zero
authenticated samples, so the attempt consumed no governed sample. The
artifact, progress ledger, and console log remain preserved under
`target/codex-tools/h08-pr-full-df7ff7370fdec1ae5d8f629d4cbba4d037162a57-20260918T034625Z/`.

`build@perl` failed with exit 2. Its declared command is bare `make`, but the
`Makefile` that `make` consumes is an untracked artifact generated from
`Makefile.PL`, and only `./setup.sh` produced it. No certification profile runs
`setup`. ExtUtils::MakeMaker also gives the generated Makefile a rule that
depends on `Makefile.PL` plus the interpreter's `Config.pm` and `config.h`: on
a clean checkout `make` has no target at all, and when the Makefile is older
than the interpreter MakeMaker rebuilds it and then deliberately fails, telling
the caller to rerun `make`. The governed WSL Perl 5.38.2 `Config.pm` and
`config.h` carry mtime `2026-09-14T12:50:06`, later than the Makefile left in
the tree, so the operation could only pass when an operator had already
regenerated the Makefile with the identical interpreter. The same class of
defect was corrected by hand at candidate `c3081cc2`, where a Windows-generated
Makefile was consumed under WSL, and it recurred because nothing in the
repository owned the generated Makefile.

Both failure shapes reproduce exactly under the governed controller. A clean
checkout exits 2 with `No targets specified and no makefile found`; a Makefile
older than `Config.pm` reproduces the recorded Full output including the
rebuild notice, the instruction to rerun `make`, the trailing `false`, and
`make: *** [Makefile:796: Makefile] Error 1` on stderr.

The correction gives the Perl binding ownership of its own generated Makefile.
`bindings/perl/build.sh` regenerates the Makefile from the tracked
`Makefile.PL` and then runs `make`, and the registered build command becomes
`bash build.sh`, with `build.sh` declared among the binding configuration
files. There is no retry, no second `make`, no ignored exit code and no sleep;
dependency resolution, declared tools, capabilities, lint, test, clean and
every certification threshold are unchanged. Four governed invocations now pass
with exit 0: a clean checkout, a Makefile backdated behind `Config.pm`, an
immediate repeat, and a Windows Strawberry Perl `gmake`-style Makefile consumed
by the WSL controller. `lint@perl` passes and `test@perl` passes 15/15.

`deep_quality_full_certification@repository` failed for a separate repository
reason. The operation carries a governed whole-operation budget of 3,600
seconds and hands each command the remaining budget with a one-second floor.
`sanitizer:c-adapter-address-undefined` alone consumed 3,289.7 seconds, 2,205.6
of them in its `cmake` configure step, so its build step was cut off at the
remaining 1,084 seconds and the C++ sanitizer case plus all fourteen mutants
then received the one-second floor and reported failed without running. The
immediately preceding isolated Full that passed 36/36 shows the same shape on a
quiet host: the two sanitizer cases consumed 2,283.9 of 3,600 seconds, 576.6
and 575.0 in configure and 591.3 and 540.4 in build, leaving the whole
operation only 417 seconds of headroom.

The cause is in `bindings/c/CMakeLists.txt`. It declared the canonical interop
dependency set with a single recursive file glob whose expressions included
exact manifest and lock paths. A recursive glob walks the entire parent tree of
every expression, so those three expressions traversed `bindings/interop` twice
and `core/internal` once: 61,399 entries, almost all of them Cargo build
output, across the 9p mount that exposes the repository to the WSL controller.
Because the glob is declared with configure-dependency tracking, CMake repeats
the identical traversal before every build, which is why the configure and the
build step of each sanitizer case each cost roughly nine minutes. A
pre-correction probe of the exact certification configure command was still
inside that traversal after 429 seconds, in uninterruptible 9p client sleep on
`newfstatat`, with 1,950 of 2,049 CPU ticks in system time.

The correction limits recursive globbing to the wildcard source patterns for
`bindings/interop/src`, `core/src` and `spec/interop/1.0`, and declares the
exact manifest and lock inputs directly, including the interop workspace
`fuzz` member that the recursive form resolved. The dependency set, the cargo
command, the produced static library, the isolated temporary sanitizer build
tree and the sanitizer flags are unchanged; only the repeated directory
traversal is removed. No budget, timeout, threshold, workload, denominator or
profile membership changed. The exact certification sanitizer sequence for the
C surface now completes with configure 8 seconds, build 66 seconds and `ctest`
1 second, passing 2/2 address and undefined-behaviour tests. The generated
build-time glob verification now contains only the three source-directory
expressions, and `build@c`, `build@cpp`, `test@c` and `test@cpp` pass through
the ordinary persistent build trees, which reconfigure from the corrected file.

`performance_resource_full_certification@repository` needed no repository
change. It reported `environment:identical-conditioning` as unavailable with
code `conditioning` and the reason that the native Windows host was not quiet
under the governed conditioning policy, after single-fixed-logical-CPU
selection, release artifact build, baseline artifact identity and the
fingerprinted native environment check all passed. The producer exited 2, its
terminal status is `unavailable` rather than failed or passed, and sample
consumption is state `zero`. That is the designed fail-closed environmental
result, so no threshold, baseline, conditioning rule, performance policy or
host state was changed.

Because tracked repository files changed again, the retained Local 37/37 and
Pull Request 79/79 no longer qualify the candidate. The owner must run one new
Local, then Pull Request, then a single Full at the new clean SHA under the
unchanged `26200.9457` authority and stop for inspection. No Local, Pull
Request, Full, Release, attestation, cloud acceptance, publication or tag
action was performed during this correction task.

**BLOCKED — NO-GO FOR P20-T02.**

## Partially sampled Full and native conditioning acquisition

Clean candidate `9e5647d4d241c0887ed5c0e4dec46b901fa0530e` passed Local
37/37 and Pull Request 79/79. Its Full profile traversed all 125 operations:
123 passed, `WVR-SEC-VSCE-LICENSE-001` waived, one unavailable, and zero failed
or incomplete. The unavailable operation was the native performance producer.
Its invocation `f66dd788482c4270b7b1313027fcf80c` has an intact atomic result,
streams, environment identity and progress ledger. It completed 27 coordinates
and 1,539 authenticated samples, then rejected all three pre-measurement
conditioning attempts for `latency:cli-startup/fixture:semantic-tiny`. No 28th
coordinate or sample started. The terminal sample state is `consumed`, with
`coordinates_started=coordinates_completed=27`,
`authenticated_sample_count=completed_sample_count=1539`, null current
coordinate, and terminal status `unavailable`. The preserved profile and atomic
evidence are under
`target/codex-tools/h08-recertification-9e5647d4d241c0887ed5c0e4dec46b901fa0530e-20260918T205104Z/`
and `target/certification-operation-results/f66dd788482c4270b7b1313027fcf80c/`.
Governance permits an unchanged-source Full retry only after preserved proof of
zero authenticated samples, so this candidate cannot be sampled again.

The failed producer discarded the raw rejected conditioner reports and retained
only their count and generic reason. Direct, sample-free execution of the exact
hashed native conditioner reproduced the environmental cause. CPU 20 recorded
selected-busy values of 2,812, 4,766, 6,641, and 6,719 basis points across
four observations spaced fifteen seconds apart, all above the unchanged 500
basis-point limit. Further fifteen-second observations remained rejected
through 07:30:45 local time and first passed at 07:31:02. This was a
multi-minute burst on the selected measurement CPU even with no STRling
certification profile running. Some observations also exceeded the existing
selected interrupt or whole-host limits, but the selected-CPU limit alone was
sufficient to reject them. The native delegation already authenticated CPU 20,
CPU set 276, affinity, release artifacts, and the active Windows baseline. No
unrelated process or host setting was changed.

The repository's three-attempt, fifteen-second acquisition window cannot span
that observed burst. The bounded acquisition is extended to 24 attempts at the
same fifteen-second interval, allowing up to about six minutes for a genuinely
quiet two-second window before each coordinate. Every rejected attempt remains
outside the sample ledger; a passing native observation is still required
immediately before each coordinate, and all 16 warmups, 64 samples, batch
normalization, comparisons, ceilings, affinity and environment identities are
unchanged. The exact native report's rejected observation and fingerprint are
now retained in the attempt evidence. Report or identity defects stop acquisition
without a quiet-host retry. This is an explicit acquisition-policy correction,
not a reinterpretation of the consumed attempt or a baseline update. The
corrected source requires a new clean SHA and a fresh Local, Pull Request, Full,
independent same-SHA Release, attestation, and cloud verification sequence.

Focused proof passes 51 performance-resource contract tests, including the
bounded busy sequence and immediate failure on conditioner identity drift; 46
governance tests, Ruff lint and formatting, and patch integrity also pass. Three
sample-free invocations of the exact producer conditioning check at the failing
coordinate all passed: the first acquired a quiet window on attempt 21 after
20 preserved rejections in 347.473 seconds, and the next two passed on their
first attempt. Their raw checks are retained in
`target/codex-tools/h08-conditioning-acquisition-proof.json`. No authenticated
performance sample was consumed in this proof.

## Structural-safety sampled regression and validation reuse

Clean candidate `7909b0e5a1ecc7938f1cf10bdf0bbd5c82762bb5` passed Local
37/37 and Pull Request 79/79. Full traversed all 125 operations, recording 123
passed, `WVR-SEC-VSCE-LICENSE-001` waived, and one failed performance
operation. Invocation `8c82c5a66540474e9d8d39873955af99` consumed 769
authenticated samples across 13 completed coordinates before
`latency:structural-safety/fixture:semantic-large` recorded a `32269700 ns`
median against unchanged relative and absolute ceilings of `30317155 ns` and
`33073260 ns`. The relative comparison failed while the absolute comparison
passed. This source identity is permanently consumed and was not retried.

The combined structural-safety path called safety analysis with immutable
foundational and structural stores for the same program. Safety analysis then
derived that program's exact semantic identity twice and its reachable-node set
three times while validating the foundational store, structural store, and
result evidence. The correction derives each value once per safety invocation
and reuses it across the unchanged correspondence checks. Standalone validators
continue to derive their own context. Semantic validation, exact identity
comparisons, node coverage and kind checks, relationship validation, evidence
validation, finding limits, traversal, workload, warmups, samples, batching,
conditioning, baseline, and acceptance ceilings are unchanged.

Five consecutive direct executions of the exact native Windows runner
coordinate on governed logical CPU 20 produce 64-sample medians from
`23589700 ns` to `24138250 ns`, leaving `6178905 ns` to `6727455 ns` below the
unchanged relative ceiling. Five pre-correction direct executions measured
`28141900 ns` to `28856300 ns`. All 36 focused Rust 1.75 safety and structural
tests pass, including mismatched prerequisite stores, malformed evidence,
resource limits, deterministic properties, competition evidence, and
repetition safety. The two deep-quality mutant source identities for the
changed implementation and their dependent fingerprints are refreshed without
changing mutant definitions, tests, workloads, thresholds, or profile
membership.

The same targeted proof exposed an independent governance traversal defect.
The forbidden-dependency rule recursively walked the complete workspace before
filtering for its exact declared tooling sources. Under WSL it remained in
`p9_client_rpc` for more than nineteen minutes with unchanged I/O counters while
crossing ignored build trees. The rule now expands only its declared source
patterns, so tracked and untracked matching files remain covered while ignored
`target` and cache trees outside those patterns are not traversed. A focused
regression forbids repository-wide `rglob` use; the native command passes all
four governance checks and 33 architecture rules.

The substantive correction requires a new clean SHA, sample-free performance
preflight, Local, Pull Request, Full, independent same-SHA no-reuse Release,
attestation, and cloud verification. No authenticated performance sample has
been taken for the corrected source.

## Full success and independent Release launch-latency disposition

Clean candidate `42f57b28eed2f70034ddfc8f3f36f3fd4abeaf20` passed Local
37/37 and Pull Request 79/79. Full traversed all 125 operations and closed with
124 passed, the expected `WVR-SEC-VSCE-LICENSE-001` waiver, and zero failed,
incomplete, or unavailable operations. Native performance invocation
`844389fdca49417aa92b89ba316dba0e` consumed 3,204 authenticated samples
across all 54 coordinates and passed. This is the first terminally green Full
result in the H08 remediation sequence.

The independent same-SHA no-reuse Release traversed the same 125-operation
denominator with 123 passed, the expected waiver, and one failed operation.
Performance invocation `f03691b8d3b543f4aad86ce463663a7e` consumed 321
authenticated samples across six completed coordinates before
`latency:cli-startup/fixture:simply-tiny` recorded a `30539050 ns` median.
The unchanged relative ceiling was `28265718 ns`; the unchanged absolute
ceiling of `31144588 ns` passed. Host isolation and conditioning checks passed,
the other five sampled coordinates passed, and the exact kernel and runner
artifact hashes equal the Full artifacts. This source identity is consumed and
was not retried.

Sample-free diagnosis against the preserved byte-identical artifacts then
reproduced elevated executable-launch latency across three independent
conditioned windows. Minimal `cmd.exe /c exit 0` medians were `54221300`,
`53881300`, and `55734150 ns`; kernel `--help` medians were `42648600`,
`43504700`, and `44548600 ns`; and exact non-authoritative CLI-coordinate
medians were `47496950`, `46679900`, and `46292900 ns`. Every conditioner was
valid, the exact runner remained on governed logical CPU 20, pre/post workload
isolation passed, and no authenticated sample was produced by the diagnostic.

The live environment fingerprint remains exactly
`07046a769a2618588399efd80156976d88f6fcb38886160c542d6757c836e14f`,
the active Windows `26200.9457` baseline identity. Repository rollover policy
permits environment-version calibration only after an authenticated OS identity
change and explicitly excludes unexplained performance changes. A same-identity
rollover would fail `rollover-no-change`, so baseline
`a0f0ab5f3da117efaa6fd907e5696bb865ecba8376ddbd82f714d8adbf32a7cd`
is retained without changing any workload, threshold, ceiling, sample count,
conditioning rule, or host setting.

This factual H08 record is a legitimate source change after the consumed
Release attempt. It does not reinterpret that failure or authorize sampling
while launch readiness remains outside the existing envelope. The new candidate
must pass targeted record, governance, generated-artifact, format, and
sample-free performance checks before Local, Pull Request, Full, and independent
same-SHA Release certification. Release may start only after an immediate
sample-free launch-readiness check is inside the unchanged relative ceiling.

## Windows process-launch signal correction

The quiet-host readiness gate did not establish a stable margin beneath the
`28265718 ns` relative ceiling. Five byte-identical `simply-tiny` runs measured
`29146950`, `28005400`, `27990100`, `28084300`, and `27252200 ns`; repeating
from the canonical repository paths measured `27696950`, `29216100`,
`30147800`, `28365300`, and `26604450 ns`. Passes and failures alternated under
valid conditioning, so the prior raw fresh-process signal is not a sufficiently
stable release-blocking measure on the unchanged Windows identity.

A same-executable launch control isolated the source of variance. In five
conditioned windows, `simply-tiny` request/control medians were
`27593550/24862750`, `26585700/23985650`, `51682200/48741050`,
`27411950/23447150`, and `25813000/23274850 ns`. The third window nearly
doubled both request and control latency, while their request/control ratio
remained consistent with the other windows. Five `semantic-tiny` windows showed
the same stable relationship. This demonstrates shared Windows process creation
and image-load variance rather than a STRling request-work regression.

`latency:cli-startup` therefore retains raw request nanoseconds as authenticated
diagnostic evidence and compares a request median to a separately warmed
`--help` median from the same kernel executable. Both arrays use the same
sample count, timer, affinity, pipes, and accepted conditioning window, and both
consume the authenticated sample opportunity. The ratio remains bounded by a
derived relative limit and a separately derived absolute ratio ceiling. The
prior raw ceiling remains visible as diagnostic history. Existing hard
in-process latency and kernel artifact-size coordinates continue to block
compiler-work and executable-growth regressions. No busy threshold, sample
count, warmup count, repetition count, product workload, or unrelated host
state is weakened or changed.

A separate conditioner defect discarded the exact native unavailable report
when Windows processor counters changed epoch during the two-second observation.
The controller now reacquires only that exact counter-discontinuity report under
the existing bounded conditioning policy. Malformed reports and identity,
power, busy, or interrupt failures remain fail closed. Twenty sample-free raw
observations reproduced three such discontinuities, with selected unrelated
logical-processor idle and kernel counters regressing together or reporting a
zero interval.

The one-time migration is clean-source, archives the old manifest, baseline,
and valid evidence by fingerprint, rebuilds source-bound artifacts, requires
the unchanged environment and conditioning identity, and recalibrates only the
two CLI coordinates. Every non-CLI baseline row is preserved byte for byte.
Focused Python contract tests, the Rust 1.75 runner tests, performance contract
validation, governance, repository formatting, static analysis, and the exact
public-contract check pass. The migration and its governed sample-free ratio
proof must complete before a new candidate enters Local, Pull Request, Full,
and independent no-reuse Release certification.
Before the migration wrote any authority, native qualification detected a real
OS identity change from Windows build `26200.9457` to `26200.9550`. The host,
CPU topology, microcode, toolchain, conditioner hash, affinity, CPU set, power
policy, timer, and reservation evidence are unchanged; only `os_version`, the
host OS/kernel attestation strings, and their dependent attestation fingerprints
differ. The unchanged-environment migration therefore failed closed with
`launch-control-environment` and wrote no tracked files. The governed combined
migration must recalibrate all 54 performance coordinates on build
`26200.9550`, permit only the reviewed CLI comparison-model change, and require
all 52 non-CLI coordinates to pass the prior active contract. This is the
repository-authorized environment rollover path, not a same-identity ceiling
change.

The first full rollover calibration rejected
`latency:pcre2-lower-serialize/fixture:simply-large` at `534 bp` relative MAD,
just above the unchanged `500 bp` stability limit. Seven exact sample-free,
conditioned repetitions then measured `9341900` to `9771750 ns`; their median
was `9552200 ns` with `196 bp` relative MAD, and every repetition passed the
prior ceiling. That isolated the calibration value as transient noise and
justified one same-source calibration retry without a threshold or source
change.

The retry then exposed a defect in the initial CLI control arrangement:
`simply-tiny` request/control ratios had `606 bp` MAD because the complete
request and control blocks were measured sequentially, allowing normal host
drift between them. The runner now warms both commands, measures every request
immediately beside its same-binary control, and alternates request-first and
control-first order. Sample and warmup counts, the request and control
workloads, affinity, timer, conditioning, and the unchanged `500 bp` stability
limit remain intact. Seven consecutive sample-free conditioned windows per CLI fixture pass with the interleaved runner. `simply-tiny` ratios are `[11361, 11485, 11233, 11434, 11636, 12284, 11334]` basis points, with median `11434` and `88 bp` relative MAD. `semantic-tiny` ratios are `[11452, 10922, 11918, 12054, 11668, 11812, 11843]`, with median `11812` and `122 bp` relative MAD. Both are well inside the unchanged `500 bp` limit; all fourteen raw request medians also pass their historical reference ceilings. The governed rollover may now be attempted again.

The next rollover calibration completed measurement but rejected replacement
because `latency:normalization/fixture:simply-large` measured `5078500 ns`
against the prior `4903690 ns` relative ceiling; the prior `5349480 ns`
absolute ceiling passed. Seven exact sample-free conditioned repetitions then
measured `[5000550, 4884200, 5082650, 4768050, 4859500, 4978450, 4753600] ns`.
Their median is `4884200 ns`, their relative MAD is `238 bp`, and the median
passes the prior relative ceiling.

The outlier exposed that baseline calibration authenticated one quiet window at
the start of each randomized 54-coordinate repetition, then reused that
observation for every later coordinate. Full and Release already condition
immediately before every coordinate. The corrected calibration does the same
and retains five coordinate-local conditioning snapshots in every measurement
row, while keeping the five repetition-envelope snapshots. Busy and interrupt
thresholds, attempts, delay, sampling, randomization, and acceptance limits are
unchanged. Historical baselines remain valid under their declared repetition
conditioning policy; the new `26200.9550` authority must use per-coordinate
conditioning.

## Windows 26200.9550 governed baseline qualification

The governed combined environment and CLI comparison migration completed from
clean source `46db35ffa44cd35df6731fc6d94a6cfa08a892b4`. It calibrated all 54
coordinates with five repetitions and retained five coordinate-local
conditioning snapshots in every row, for 270 coordinate snapshots in total.
All 52 non-CLI coordinates passed their prior relative and absolute contracts;
there were zero failed comparisons. The prior authority is archived intact at
`tests/certification/performance-resource/1.0/history/a0f0ab5f3da117efaa6fd907e5696bb865ecba8376ddbd82f714d8adbf32a7cd`.

The active baseline fingerprint is
`7e159f1ac589c1b4179a8a64aef38b87f76784c72820e97ac42dc849c515502d`,
the manifest fingerprint is
`50ca85310dcc881356ff0ddee70df0147ea70b0af7363c7710353d3df317c608`,
and the authenticated Windows `26200.9550` environment fingerprint is
`505a15ce4c35f0c3a53640c5589ca8121fea6dc91859a9d2ed7e4c15fc15ab8b`.
The OS and dependent attestation fingerprints are the only host-identity
changes from the prior environment.

For `semantic-tiny`, the five request medians produce a `24679800 ns` median,
the same-binary control median is `21669300 ns`, and the ratio median is
`11394` basis points against a derived absolute ratio ceiling of `13673`. For
`simply-tiny`, the corresponding medians are `24510200 ns`, `21038300 ns`, and
`11652` basis points against `13983`. Their ratio MADs are `90` and `174`
basis points. Both historical raw reference ceilings pass and remain diagnostic
evidence. The deterministic performance contract accepts the new authority.
The 67 affected Python contract tests also pass against the active and archived
authorities. No authenticated Full or Release sample was consumed by
qualification.

Because the baseline, manifest, evidence pointer, archived authority, and H08
records are tracked changes, they require a new clean candidate. That candidate
must pass final targeted checks and sample-free launch readiness before Local,
Pull Request, and Full. Release remains independently gated by an immediate
same-SHA sample-free readiness check and the no-reuse launcher.

## Post-rollover Local hygiene correction

Clean candidate `b1371f951955f38af5aea99d5066ce39a15d5791` passed 36 of
37 Local operations. Only `hygiene@repository` failed: the active baseline was
`1589193` bytes after adding 270 full coordinate-conditioning snapshots, above
the repository's `1048576`-byte tracked-file limit. Contracts, generated
artifacts, governance, formatting, static analysis, core and interop tests, and
the other Local operations passed. Local performed no authenticated performance
sampling, and Pull Request and Full did not start.

The governed atomic writer now serializes only `baseline.json` files as compact
UTF-8 JSON. The active baseline becomes `621909` bytes while preserving the
complete parsed document, all 54 measurements, all 270 conditioning snapshots,
and baseline fingerprint
`7e159f1ac589c1b4179a8a64aef38b87f76784c72820e97ac42dc849c515502d`.
Manifests, evidence records, and other governed JSON retain their existing
indented form. A focused writer test protects both dispositions. Because this
is a tracked tooling correction, the next clean candidate must restart Local.

## Paired-measurement attestation correction

Clean candidate `fa60bec1f1599b710649d5016497cce11adb57c2` passed Local
37/37. Pull Request passed 78/79 operations and failed only `test@repository`:
49 attestation tests stopped during fixture setup because the attestation
verifier still reconstructed every performance coordinate with the direct
median comparison. The active `latency:cli-startup` coordinates now use the
governed paired same-binary request/control model. Full and Release did not
start, and no authenticated performance sample was consumed.

The verifier now authenticates the CLI control-sample denominator, batch
normalization, statistics, request/control ratio, paired comparison, and both
request and control contributions to the sample ledger. It rejects control
fields on direct-comparison coordinates. The attestation fixture now emits the
same production evidence shape, and focused regressions reject truncated or
misnormalized control samples. The exact failed repository operation then
passed 1,220 tests with one governed skip and zero failures in 2,214.869
seconds. Because this correction changes tracked verifier source, the next
clean candidate must restart Local and Pull Request before Full.

## Direct-coordinate sample-accounting correction

Clean candidate `148dc1a88033cc08d72d23c111aef8508c80838e` passed Local
37/37 and Pull Request 79/79. Full traversed all 125 operations and recorded
123 passed, the expected `WVR-SEC-VSCE-LICENSE-001` waiver, and one incomplete
operation. `performance_resource_full_certification@repository` completed four
coordinates and 256 authenticated samples before starting
`memory:kernel-peak-rss/fixture:semantic-large`; structured invocation
`628f450bdf0641ffbc098801803d0333` correctly preserved the fifth coordinate as
indeterminate. The producer then raised `KeyError: control_samples` because its
new ledger accounting indexed paired launch controls for every measurement,
including direct-comparison memory observations. Release did not start, and
the sampled candidate is not retried.

The producer now selects the comparison model before reading controls. Direct
coordinates authenticate request samples alone; paired CLI launch coordinates
authenticate both request and same-binary control samples. Focused regressions
cover both evidence shapes plus zero, consumed, and indeterminate atomic sample
boundaries. Thresholds, ratios, sample counts, conditioning, ceilings, workload
isolation, and authenticated-sample rules are unchanged. The tracked correction
requires a new clean candidate to restart Local and Pull Request before Full.

Clean candidate `42f11c44f2ed126fe70fa511e41e1596d64d962e` stopped at
Local 36/37. Only `format_check@repository` failed: a final focused test edit
was not normalized after the preceding formatting proof. Ruff reformatted that
single file; no semantic or certification policy changed. Pull Request, Full,
Release, and authenticated performance sampling did not start. The formatting
correction requires another clean candidate to restart Local.

## Trusted-verifier compatibility correction

Clean candidate `4d5ef0750847152e7e574f8442f1edcecb415c99` passed Local
37/37 and Pull Request 79/79. Full and the independent no-reuse Release each
completed all 125 operations with 124 passed, only
`WVR-SEC-VSCE-LICENSE-001` waived, and zero failed, unavailable, or incomplete
operations. Their evidence fingerprints are
`8d43b97bc1a41b7c2c3f9a42c3df7a3040cc4707ab07cf13b4eb9eb0ed4da2ba`
and
`984231c74a65751f9956f12985fc9c7721f5417ac2b8fe809fbf43671cdcbe24`.
Both authenticated 3,332 performance samples under distinct producer
invocations. Local attestation creation and verification passed with evidence
root `403b6d03d1aa323f5e9dca83216649bb3a8fada33a18ac1b3e76895f838ebd11`.

The pinned cloud verifier at `f47bd09254c9a08e5578b549e45f41ad7278e1c9`
then failed closed before accepting the bundle because its trusted performance
schema and reconstruction code predate coordinate-local conditioning and the
paired request/control comparison model. Substituting candidate code for the
trusted verifier is forbidden. The signed evidence and failed cloud result are
retained as diagnostic history; the bundle is not promoted to current closure
authority.

The minimal correction promotes the already certified and immutable
`4d5ef0750847152e7e574f8442f1edcecb415c99` revision as the shared integrity
and delivery verifier pin and PR-base ancestry floor. That revision contains
the reviewed paired-evidence verifier, the matching trusted schemas, and the
complete green Full/Release evidence described above. Candidate code remains
data-only, isolated Python remains required, and the certifier, trust policy,
closure allowlist, waiver scope, thresholds, sample counts, and performance
contracts are unchanged. Because the workflow pin is tracked source, a new
clean candidate must restart Local, Pull Request, Full, independent Release,
attestation, and cloud verification.

## Closure-policy compatibility correction

Clean candidate `d041a697e850f08d1d3c0a6e52d15a412dd02325` passed the
complete ordered campaign without a tracked source change: Local 37/37, Pull
Request 79/79, Full 124 passed plus only
`WVR-SEC-VSCE-LICENSE-001`, and independent no-reuse Release 124 passed plus
that same waiver. Full and Release each had zero failed, unavailable, or
incomplete operations. Their evidence fingerprints are
`97eb8a309d349a17f41130999ed7869077644dea0f5cadde89720fccfef552b8` and
`33cb09e8f0cebe0b656f052afcb240174b9bf33e7fad60bce2f67c51a374eb92`.
The two performance producers authenticated 3,332 samples apiece under
distinct invocation identities `380cec82b1e942b9883bbf61909e5046` and
`ea3e3b230eaa446e873569cf5ace4bd2`, proving Release did not reuse Full
evidence.

The diagnostic closure bundle bound the exact certified source, both complete
profile artifacts, independent execution receipts, the real-engine
observations, and the expected waiver. Its evidence root is
`8b36fcfefbd7911e97589cd03905af898f2755aa985d934c28ed3853ac6c86c4`,
signature SHA-256 is
`976bd7d6b642641c988c27496f3870b7ec0edf69433faa26eef8a37b0ba66c3b`,
and attestation SHA-256 is
`4061f9c71b5d89b19502b2cc3418bbaea398479cc3afde25bf3575c8fef736c5`.
Local verification and the immutable `4d5ef075` trusted verifier both pass;
the resulting state is `CLOUD_VERIFIED`, never `PUBLISHABLE`.

Targeted closure validation then found two repository-policy defects. The
repository formatter selected the byte-authenticated bundle for Prettier
rewriting, which would invalidate the evidence root and signature. Repository
hygiene also rejected the complete product projection and both profile
artifacts because their required evidence exceeds one MiB. The bundle was not
rewritten, truncated, or promoted; it remains ignored diagnostic history.

The narrow correction classifies only the exact current hardened-core bundle
as serializer-owned signed evidence and grants maximum-file-size exceptions
only to the three required complete artifacts. Focused tests enforce both
boundaries. No language behavior, signature rule, evidence denominator,
threshold, sample count, conditioning, workload isolation, or publication
authority changes. Because formatting and hygiene policy are tracked source
outside the closure allowlist, a new clean candidate must repeat the full
campaign. P20-T02 remains paused and unstarted.

## Paired launch-estimator correction

Clean candidate `831d28c4144e61f4ab67bbd01875cbf965a6e826` passed Local
37/37 and Pull Request 79/79. The mandatory sample-free gate immediately before
Full then stopped the campaign: four of five conditioned windows passed, but
the third `latency:cli-startup/fixture:semantic-tiny` observation produced
13,165 basis points against the unchanged 12,533 relative ceiling. Its 13,673
absolute ceiling still passed. Full, Release, and authenticated performance
sampling did not start at this source identity.

The failure was treated as a certification-design defect. The native runner
already emitted interleaved request/control pairs, but production reduced each
stream independently and divided the request median by the control median.
That aggregation discards the pair relationship named by the governed
`paired-same-binary-launch-control` model. A bounded ten-window diagnostic
confirmed that the retained per-pair ratios were stable inside the unchanged
envelope; rerunning the unchanged profile was not used as diagnosis.

The corrected estimator computes one request/control ratio for every
interleaved pair and compares the median of those ratios. Production evidence
records the complete ratio stream and statistics, and the trusted attestation
verifier independently reconstructs them. The governed migration archived
baseline `7e159f1ac589c1b4179a8a64aef38b87f76784c72820e97ac42dc849c515502d`
and deterministically derived active baseline
`fcadf7f648c826b392e551ca51788eaa25dd77a2a087a01a3abb62ff4f98c39e`
from its retained raw pairs. All raw request/control measurements, 54
coordinates, 270 conditioning snapshots, sample counts, 1,000-basis-point
relative budgets, and absolute ceilings 13,673 and 13,983 are unchanged. A new
clean candidate must prove repeated paired readiness and restart at Local.

## Profile fail-fast correction

Clean candidate `50e6b962aa364dfbf49e152d3a16ff2f5bc4e6e6` passed every
sample-free predictor, including five consecutive conditioned paired-launch
windows, and then passed Local 37/37. Pull Request passed its first 72
operations, including the 44-minute repository test operation, before
`test@lsp` reported failure at stage 73/79 after 237 seconds. The campaign was
stopped before Full, Release, or authenticated performance sampling.

The exact governed `./strling test lsp` operation passed independently with
572/572 tests in 219 seconds under the same frozen source and exact runtime
environment. The profile runner nevertheless started stage 74 after recording
the blocking failure, while retaining the failed child output in memory until
the whole profile returned. Enforcing the campaign's stop-on-failure rule
therefore made the failed operation's diagnostic output unavailable. That is a
deterministic certification-orchestration defect, not an acceptable reason to
rerun the unchanged expensive profile.

The runner now stops immediately after the first failed, unavailable, or
incomplete operation. It still finalizes the progress ledger, writes the JSON
artifact for the exact completed prefix, and renders only the blocking
operation's bounded child output. A focused regression proves that a later
operation cannot execute after a blocking result, and the complete quality
runner test module remains green. This tracked correction requires another
clean candidate to restart at Local; if the LSP operation fails again, its
exact output will be preserved for atomic diagnosis.

## Release end-to-end stationarity correction

Clean candidate `1bb1241d46daa09abf955681d181c77179456446` passed every
sample-free predictor, five consecutive paired-launch windows, Local 37/37,
Pull Request 79/79, and Full with 124 passed plus only
`WVR-SEC-VSCE-LICENSE-001` waived. Full performance invocation
`2ff60dd7b9384b3fbae822e720e1fece` completed all 54 coordinates and
authenticated 3,332 samples. The immediate pre-Release Full preflight and five
paired-launch windows also passed.

The independent no-reuse Release stopped fail-fast at operation 22/125.
Performance invocation `6bb6a1d778cd4b53868fd0440090bbb7` authenticated 513
samples across eight completed coordinates before
`latency:end-to-end/fixture:simply-common` measured a `791350 ns` median.
That exceeded the unchanged `724422 ns` relative and `790280 ns` absolute
ceilings. Conditioning, workload isolation, environment identity, and exact
runner, kernel, and interop artifact hashes all passed. This source identity is
consumed and is not retried.

The failed sequence shifted from an `830150 ns` first-half median to
`737650 ns` in its second half. Five exact non-authoritative repetitions with
the existing 16 warmups all passed but retained the same early/late movement.
Five further conditioned repetitions with 128 fixed warmups passed at medians
`616016`, `661766`, `620183`, `622000`, and `625233 ns`; every window passed
isolation, and their first- and second-half medians no longer showed the
Release failure's directional settling. None of these diagnostics entered an
authenticated sample ledger.

The governed policy therefore strengthens latency warmups from 16 to 128 while
retaining all 64 authenticated samples, batching, workloads, ratios,
conditioning, affinity, thresholds, and absolute ceilings. The existing batch
duration contract makes this a bounded settling interval rather than a retry
or discarded-sample rule. A one-time clean-source migration must recalibrate
all 54 coordinates under five coordinate-local conditioned repetitions, prove
every new median against the prior hard ceilings, archive baseline
`fcadf7f648c826b392e551ca51788eaa25dd77a2a087a01a3abb62ff4f98c39e`,
and retain or tighten every prior budget and ceiling. The resulting tracked
authority requires a new candidate to restart at Local.

The first governed calibration completed measurement and then failed closed
before writing because the migration substituted its one-time command for the
baseline's canonical update command. The focused regression now performs full
manifest and baseline validation and preserves the canonical command. The
second calibration also wrote nothing: its first coordinate derived a relative
budget above the prior 1,000-basis-point threshold, and exact budget
preservation conflicted with the baseline validator's derivation invariant.
The migration now retains the newly derived budget only when it is equal to or
stricter than the prior threshold, caps every absolute ceiling at its prior
value, and rejects any weakening before writing.

Five independent non-authoritative five-repetition groups then exercised the
exact failing `latency:semantic-parse/fixture:semantic-tiny` boundary with 128
warmups. All five groups derived the unchanged 1,000-basis-point budget; their
median-of-medians values were `9609`, `9558`, `9612`, `9709`, and `9714 ns`,
and all passed the prior relative and absolute ceilings. The 25 observations
used authenticated conditioning but entered no certification sample ledger.

The next complete calibration used aggregate budget-drift reporting and
rejected seven coordinates whose freshly derived budgets exceeded their prior
hard thresholds. This proved that repeating until five random repetition
medians happen to recreate every old variance estimate would be an invalid
methodology. The governed baseline now records the derived relative budget and
absolute ceiling, the corresponding prior hard values, their capped active
values, and the prior baseline fingerprint. Validation independently
reconstructs the derived values and requires each active threshold to equal
`min(derived, prior)`. Any missing or altered provenance fails closed.

This explicit policy is incompatible with immutable trusted verifier
`4d5ef075`, which predates both 128 warmups and capped-budget provenance. The
first clean candidate under the new authority must therefore complete Local,
Pull Request, Full, and independent Release to qualify its verifier revision.
A subsequent pin-only candidate must then repeat the complete campaign before
cloud verification and final H08 closure, following the same trust-promotion
sequence already used for the paired-measurement verifier.

The first clean-source calibration under capped-budget provenance then stopped
before writes because one semantic-analysis pathological coordinate produced
`561 bp` relative MAD from five repetition medians, above the unchanged
`500 bp` stability limit, while still passing both prior hard ceilings. Five
independent five-repetition diagnostics reproduced the estimator intermittency:
four groups passed at `448`, `93`, `43`, and `449 bp`, while one failed at
`777 bp`; all 25 observations passed the prior ceilings. Every sliding
nine-observation window from that evidence passed (`353 bp` maximum), and five
fresh nine-repetition groups passed at `217`, `342`, `37`, `55`, and `323 bp`.
The stationary authority therefore strengthens the calibration denominator
from five to nine repetitions for all 54 coordinates. The `500 bp` limit,
128 warmups, 64 samples, conditioning, workloads, and hard ceilings remain
unchanged.

The governed nine-repetition calibration at source
`88651d7ce8504a63157e98bded9394b25ff8d7e1` then passed all 54 coordinates and
all prior relative and absolute ceilings. It retained 486 per-coordinate
conditioning snapshots, capped 22 derived thresholds at their prior hard
values, archived baseline
`fcadf7f648c826b392e551ca51788eaa25dd77a2a087a01a3abb62ff4f98c39e`, and
produced manifest
`8efce9dfa700039ee2b387cd4e0763e44f87a2052f914c3905b211008f3fd117`.
Persisted snapshots omit only the repeated conditioning-identity hash, which
is derivable from their retained controls; live conditioner reports still
authenticate that hash before acquisition. Snapshot and baseline fingerprints
cover the compact representation. The resulting governed baseline is
1,035,872 bytes with fingerprint
`43f4b9cec4f4f7e135f31af0eb94a04faabfa74af3850198d5d735be2ebc01c6`, below
the unchanged 1 MiB hygiene ceiling without removing measurements,
observations, or semantic evidence.

Clean candidate `7d12882385a50472dc8625168538bd73de0149f5` passed all
targeted predictors, five paired-launch readiness windows, Local `37/37`, and
Pull Request `79/79`. Full stopped fail-fast at operation 22 after 20 passes and
the expected waiver. Performance invocation
`c8fb794769e244969a59193b7f5e4b78` preserved 1,219 authenticated samples across
21 completed coordinates before
`latency:editor-interaction/fixture:semantic-large` measured a `193386200 ns`
median against the unchanged `186888460 ns` relative and `203878320 ns`
absolute ceilings. The relative comparison failed while the absolute
comparison passed. Conditioning, workload isolation, environment identity,
and exact artifact hashes passed, so the consumed source is not retried.

Five exact non-authoritative reproductions of that coordinate then passed at
medians `169116150`, `172620550`, `169506950`, `175872850`, and `174950100 ns`.
Every repetition used production conditioning, isolation, 128 warmups, the
frozen batch size, and 64 samples; none entered an authenticated ledger. Their
half-window medians showed no directional settling.

The diagnostic exposed a readiness-design defect: the production Full
preflight returned immediately after conditioning the first shuffled
coordinate and never invoked a workload. It therefore could not predict a
non-CLI latency failure. The preflight now derives the slowest direct
hard-latency coordinate from governed baseline duration and requires five
consecutive production-equivalent conditioned, isolated passes outside the
authenticated ledger. The current sentinel is the failed
editor/semantic-large coordinate. Thresholds, ceilings, warmups, sample count,
batching, workloads, conditioning, and paired CLI logic are unchanged.

Clean candidate `dcc6e2bb183fd8ba186d418cf83b0c12a42b0ddb` passed the
corrected five-observation Full sentinel, five paired-launch readiness windows,
Local `37/37`, and Pull Request `79/79`. Full then stopped fail-fast at
operation 3 after two passes. `security_dependency_risk@repository` reported
new blocking advisories for LSP `fast-uri` 3.1.6 and JVM/Kotlin
`jackson-databind` 2.18.9, plus nonblocking findings for LSP `undici` 7.29.0
and the same Jackson coordinate. The exact atomic operation reproduced all
three failed checks with completed advisory retrieval. Full performance and
authenticated sampling never started; the source identity is consumed and is
not retried.

The bounded remediation advances only affected compatible dependency lines:
LSP transitive `fast-uri` to 3.1.8 and `undici` to 7.30.0, and the shared JVM
Jackson graph to 2.18.10. The owning package managers regenerated the npm and
Gradle lock evidence and Gradle artifact hashes, and the registered JVM graph
producer emitted fingerprint
`sha256:92ad25d118aba87429b5cfbe05a41d6817ff229de2a41b8d7c30d2558d9c5195`.
The exact dependency-risk operation then passed `54` checks with only the
expected `WVR-SEC-VSCE-LICENSE-001` waiver and no failed, unavailable, or
incomplete result. This tracked repair requires a fresh clean candidate to
restart at Local.

Clean dependency-remediation candidate
`978c04981d602e55f6f6036d9db437260fc8bfa8` passed the complete cheap,
sample-free prerequisite set until the required five-observation Full
sentinel. Its first four editor/semantic-large observations passed, but the
fifth measured a `193891950 ns` median against the unchanged `186888460 ns`
relative and `203878320 ns` absolute ceilings. The absolute comparison passed,
but readiness correctly stopped before Local. Full, Release, and authenticated
performance sampling did not start.

Per-sample process CPU instrumentation then proved that the workload had not
regressed. Five conditioned 64-sample diagnostic windows passed at medians
`172822800`, `172225250`, `170227700`, `168923100`, and `170666450 ns`, while
the fifth retained a contiguous `209555600`, `212817700`, `556575500`, and
`306281000 ns` wall-time burst with only `156250000`, `109375000`,
`109375000`, and `109375000 ns` of process CPU. The `556575500 ns` observation
was scheduled for only 19.65 percent of its wall interval. Production
conditioning and pre/post workload isolation cannot detect interference that
begins inside the measurement window.

The runner now authenticates every non-CLI sample against its measured process
CPU interval. A wall-minus-process-CPU gap above `50000000 ns` is preserved as
rejected interference, and collection continues until the unchanged 64-sample
denominator is complete. A hard 128-attempt bound fails closed if the host
cannot provide that denominator. Paired CLI request/control collection remains
unfiltered and otherwise unchanged. Thresholds, ratios, warmups, accepted
sample counts, batching, workloads, conditioning, ceilings, and ledger rules
are unchanged. Production validation reconstructs the CPU arithmetic and
retains accepted and rejected evidence.

Five consecutive production-conditioned atomic proofs passed at medians
`177855850`, `170270150`, `168704050`, `171274550`, and `168573300 ns`.
They retained exactly 64 accepted samples from 67, 71, 64, 70, and 69 attempts,
all below the 128-attempt bound and with zero authenticated ledger samples.
The correction is tracked source, so the next clean candidate must restart at
Local after the complete cheap predictor set passes.

Clean authenticity-remediation candidate
`c3ef5eaaf509cb0aa3c66cb9d35c19dc554065e1` passed the complete cheap
predictor set, five Full sentinel windows, five paired-launch windows, Local
`37/37`, and Pull Request `79/79`. Full stopped fail-fast at operation 22 after
20 passes and the expected waiver. Performance invocation
`8bddb93157ec4d77b89631b84779b896` completed all 52 coordinates and preserved
3,267 authenticated samples before
`latency:semantic-analysis/fixture:simply-large` reported a `33001200 ns`
median against `18190975 ns` relative and `19844700 ns` absolute ceilings.
Its sample state is permanently consumed and the candidate is not retried.

The failed window spent most of its first 58 observations near `33 ms` before
returning to the baseline's approximately `16.5 ms` range. Five direct
production-conditioned reproductions passed at medians `16423650`, `16420550`,
`16669900`, `16426500`, and `16729000 ns`. The exact complete producer then
reproduced the defect without an authenticated ledger on a different short
coordinate: `latency:structural-safety/fixture:semantic-pathological` shifted
from a `1265775 ns` first-half median to `1058425 ns` in its second half and
failed at `1187400 ns`. That sequence distinguishes directional execution-rate
settling from a product regression or an ordinary external-host explanation.

The fixed count of 128 warmups provides radically different settling duration
across the frozen batch sizes. The governed migration therefore strengthens
fixed warmups from 128 to 512 while retaining all 64 samples, nine baseline
repetitions, batch sizes, workloads, conditioning, ratios, hard thresholds,
absolute ceilings, and sample-authenticity rules. Five 512-warmup atomic proofs
for each failed coordinate passed. Semantic-analysis medians were `14159200`,
`14205900`, `13751300`, `13814450`, and `14241350 ns`; structural-safety
medians were `960600`, `891325`, `893800`, `885475`, and `888725 ns`. The
one-time clean-source migration must recalibrate all 54 coordinates, pass every
prior hard ceiling, archive the prior authority, and retain or tighten every
budget before a new candidate can restart at Local.

The first complete 512-warmup migration attempt wrote no authority because
calibration inherited the active capped-budget formula before the migration
had attached its required prior-baseline fingerprint. Validation failed closed
with `budget-provenance`. The migration now constructs an uncapped derived
calibration manifest first, then applies the existing prior-ceiling cap and
provenance transformation to the complete result. A focused regression starts
from the current capped authority and proves the 128-to-512 step preserves the
sample and nine-repetition denominators.

The corrected clean-source migration at
`42be2a6af7b2c81f2ecf10f545c08d973f6bf74e` passed all 54 coordinates and all
prior relative and absolute ceilings. It retained 512 warmups, 64 samples,
nine repetitions, and 486 coordinate-local conditioning snapshots, archived
baseline `43f4b9cec4f4f7e135f31af0eb94a04faabfa74af3850198d5d735be2ebc01c6`,
and produced manifest
`4a2fa3940b587a17ab36332576c922f2a58f467dbbde2b9036085d5922b10907`.
Every active budget is equal to or stricter than its prior hard authority. The
compact baseline is 1,033,842 bytes with fingerprint
`c94bda9ed4ae2dcdfce00ce3d89cf63ef78d38b042eb7c2978ec6b1b6ece1c53`,
below the unchanged 1 MiB hygiene limit without removing measurements or
semantic evidence.

Clean warmup-migration candidate
`bbae6b613ca7562c1eaf44c8d52378519b51aba2` passed the complete non-sampling
predictor set and the production Full sample-free gate. The paired CLI
diagnostic then passed its first four conditioned windows but stopped before
Local when window five measured `fixture:simply-tiny` at `12531` basis points
against the unchanged `12337` ceiling. The same window exposed an order split:
request-first pairs had a `15302` median while control-first pairs had a `7819`
median. The aggregate median therefore depended on the two inner tail values
rather than a balanced estimate of the deliberately alternating launch orders.
No authenticated samples were consumed.

The paired estimator now computes each launch-order stratum median separately
and combines them with an integer geometric mean, which cancels reciprocal
first/second-launch drift while preserving one-to-one request/control pairs.
All raw samples, sample counts, warmups, conditioning, ratios, relative budgets,
and prior effective ratio ceilings remain governed. Retained baseline samples
permit a sample-free authority migration: every candidate effective ceiling is
capped at its immediately prior effective ceiling, so the correction cannot
relax either CLI coordinate. The five observed windows produce balanced values
of `11459/11400`, `11535/11702`, `11393/11343`, `12098/11432`, and
`11132/10939` basis points for semantic-tiny/simply-tiny respectively; all ten
pass their unchanged prior effective ceilings.

The clean-source retained-evidence migration at
`75ce95993ccec228d3a24cbedb3c4a45512c45e0` archived baseline
`c94bda9ed4ae2dcdfce00ce3d89cf63ef78d38b042eb7c2978ec6b1b6ece1c53`
without consuming samples. It preserved every raw repetition and produced
manifest `c8ff8e5a19515ec16157ecc3393df42c8b0e8450cd71199c7e016715cc5ab42e`
and baseline `00087567449973c0ca1b7bf649b2a82ce5b4dc3157c2dc37c6285e0aa97ad98a`.
The governed relative budgets remain `1000` basis points. Effective ceilings
remain exactly `12658` and `12337`; the migration cannot admit evidence that
the prior authority would have rejected.

Clean order-balanced candidate
`8055584440e8e3dacab0efce277b59fe0f252a48` passed every cheap predictor,
five paired-launch readiness windows, Local `37/37`, Pull Request `79/79`, and
the immediate pre-Full gates. Full stopped fail-fast at operation 22 after 20
passes and the expected waiver. Performance invocation
`c20e958cc97e459b998cbd9a9bbb7160` authenticated 1,027 samples across 18
completed coordinates before `latency:semantic-analysis/fixture:simply-common`
measured `96808 ns` against the unchanged `89146 ns` relative and `98165 ns`
absolute ceilings. The relative comparison failed while the absolute
comparison passed. Release did not start, and the consumed source is not
retried.

The exact complete producer reproduced the coordinate at `96983 ns` with zero
authenticated ledger samples, while five isolated conditioned observations
passed between `81004` and `84100 ns`. Prefix bisection then proved that the
first five shuffled operations followed by the target passed at `78396 ns`,
the first six followed by the target failed at `90167 ns`, and the sixth
operation (`latency:cli-startup/fixture:simply-tiny`) alone followed by the
target passed at `82084 ns`. The defect is therefore cumulative producer state,
not a product regression or a single leaking operation. The governed baseline
independently contains fast `78673`–`83902 ns` and sustained-work
`92021`–`92954 ns` repetition medians for this coordinate, but its median
authority is `81042 ns`.

The existing two-second Windows quiescence observation could accept a quiet
host before the selected CPU had recovered from sustained launch work. Adding
eight seconds after the failing prefix, for ten seconds total before the target,
restored a passing median of `80061 ns`; a twelve-second total check passed at
`81750 ns`. The Windows supported-controls conditioning policy therefore moves
from v5/`1.4.0` to v6/`1.5.0` and strengthens its observation from 2,000 to
10,000 milliseconds. Busy and interrupt thresholds, performance ceilings,
ratios, warmups, sample counts, batching, workloads, isolation, and
authenticated-sample rules remain unchanged. Because the conditioner identity
is baseline authority, the correction requires a clean-source governed
recalibration before Local restarts.

At clean correction source
`804f16e0d8e100847b12ca9566e73c52ab6b7f4d`, the governed sample-free reset
archived baseline
`00087567449973c0ca1b7bf649b2a82ce5b4dc3157c2dc37c6285e0aa97ad98a`
byte-for-byte and produced planned manifest
`90890dfac6fafad899b0029831dcc5063c589079d4f9bdee06f3e335bb963544`.
No measurement or authenticated sample was consumed. The next step is one
clean-source 54-coordinate recalibration under the strengthened v6 conditioning
identity and every immediately prior hard ceiling.

The first native v6 qualification then correctly refused CPU 20: its ten-second
window observed `4297` selected-busy basis points against the unchanged `500`
basis-point limit. Independent all-core windows continued to show CPU 20
occupied while the machine as a whole was admissibly quiet. This is not treated
as host noise. A fixed-core certification design that cannot select an
admissible core would make the readiness predictor unusable.

Topology inspection initially identified logical CPUs 16–31 as the same
efficiency-0, single-thread processor class. CPU 24 passed five v6 conditioning
windows and the exact six-operation cumulative trigger at `78800`, `78984`,
`77553`, `83590`, and `79938 ns`, all below the unchanged `89146 ns` relative
ceiling. The subsequent governed 54-coordinate calibration nevertheless failed
closed and wrote no authority. `latency:end-to-end/fixture:simply-tiny` measured
`63216 ns` against `57618 ns` relative and `62856 ns` absolute ceilings, while
`memory:kernel-peak-rss/fixture:protocol-common` measured `7417856 bytes`
against `7353139` relative and `7947879` absolute ceilings.

Atomic reproductions proved the latency defect was processor-class-wide rather
than ordinary host noise: CPU 24 measured `69782 ns`, and every other screened
efficiency-0 CPU (17, 18, 19, 22, 25, 30, and 31) also failed the unchanged
relative ceiling. Quiet performance-core CPU 1 passed the same end-to-end
coordinate at `32952 ns` and the original six-operation semantic trigger at
`43586 ns`. It preserves the processor, group, last-level cache, NUMA node,
power controls, timer, toolchains, and Windows build while making the exact
reviewed efficiency-0/single-thread to efficiency-1/sibling-pair transition.

Five production-conditioned CPU 1 peak-RSS observations formed a stable lower
plateau at `7372800 bytes` (four observations) with one `7446528-byte`
observation. All passed the absolute ceiling but missed the prior relative
ceiling by at least 19,661 bytes. The release runner, kernel, and interop DLLs
were byte-identical to the archived authority, proving this was not product
growth. Removing serialized buffers and generic timing-evidence allocations did
not lower the plateau, falsifying allocation retention as the cause. Direct
instrumentation instead proved that the coordinate included pages from the
9 MiB multi-operation certification runner and its Windows topology/evidence
machinery before it measured the kernel workload.

The corrected Windows path keeps that runner as the control owner but moves the
unchanged canonical request, one warmup compile, and one measured compile into
a 3.15 MiB kernel-only worker. The worker reapplies the parent's attested
affinity, CPU-set ID, HighQoS policy, and unlimited Job quota, authenticates the
same descheduling rule, observes actual execution on CPU 1, and reads its native
peak-working-set counter only after both compiles. A deterministic bundle
manifest binds both runner executables as the single source-bound runner
artifact. Eight governed direct observations measured `7032832`–`7073792
bytes`, all below the unchanged `7353139` relative and `7947879` absolute
ceilings. Five subsequent production-conditioned observations passed at
`7036928`, `7049216`, `7032832`, `7036928`, and `7036928 bytes`.

The same clean runner bundle then passed five conditioned
`latency:end-to-end/fixture:simply-tiny` windows at `32076`, `32404`, `32089`,
`32847`, and `31643 ns` against the unchanged `57618 ns` relative ceiling. It
also passed five exact six-operation cumulative-trigger windows followed by
`latency:semantic-analysis/fixture:simply-common` at `41504`, `41523`, `41594`,
`41529`, and `41533 ns` against the unchanged `89146 ns` relative ceiling.
All three predictors are therefore repeatedly green with meaningful margin and
zero authenticated samples; one all-or-nothing 54-coordinate calibration may
now begin.

The revised governed migration therefore permits exactly CPU 20 to CPU 1 and
v5/2,000-millisecond to v6/10,000-millisecond identity changes. It enumerates
the 34 derived placement, processor-class, reservation, attestation, and
conditioner coordinates; requires every other environment coordinate and all
conditioner thresholds to remain identical; requires the archived authority
and a clean planned reset; rebuilds source-bound release artifacts; recalibrates
all 54 coordinates; and requires each non-CLI metric and paired CLI ratio to
pass every prior relative and absolute ceiling before writing active authority.
Calibration failure writes nothing. No threshold, ceiling, ratio, warmup,
sample count, workload, isolation, or authenticated-sample rule is weakened.

The clean-source migration at
`9d36da894c826cf2331d43fb413c3bb0b34db08e` passed on September 30, 2026.
All 54 coordinates completed nine governed repetitions with 486 retained
coordinate-conditioning observations. All 52 non-CLI comparisons and both
paired CLI-ratio comparisons passed every prior ceiling. The accepted baseline
fingerprint is
`28838ccce1b6c7dc9bbf094354a108c5e419927476a3d3879b6b0aecd56008be`,
and the manifest fingerprint is
`bcce3beb87a97e0e04a0e7a7d0f5700cd3146092317d13fccf4da87e03748e7d`.
Compact baseline serialization retains all authority in 1,024,915 bytes,
below the unchanged 1 MiB tracked-file limit. Five preceding CPU 1 paired-CLI
diagnostic windows also passed with zero authenticated samples. The former
tool-owned invocation lost its process and terminal result on a session
transition without accepting authority; only the retained owner invocation's
successful result is accepted. Console, progress, observations, and exit
evidence are preserved under `target/codex-tools/h08-cpu1-calibration-9d36da89`.
Targeted validation and a new clean candidate freeze must precede all readiness
predictors and the Local → Pull Request → Full → independent Release sequence.

## Performance-deferred development readiness

On September 30, clean candidate `d4c8c705ba1eca2d46dacf811ce2af755a8b01b9`
passed Local 37/37. Pull Request stopped after 71 passes when operation 72,
`test@repository`, failed because its runner-bundle fixture created Windows
`.exe` names on Linux. Seven operations were not reached; Full and Release did
not start. The correction follows the host's executable suffix in the test
fixture only and leaves production performance logic unchanged.

The owner requested a performance-deferred readiness workflow on October 2.
`python3 -m tooling.certification_readiness --profile <profile> --plan` derives
the exact operation selection from `toolchain.json`. Local defers its one
performance-resource operation; Pull Request defers two; Full and Release defer
all three. Thus readiness denominators are 36, 77, 122, and 122, respectively.
The existing license waiver remains governed, not a performance deferral.

Execution requires a clean committed candidate and a fresh `--artifact` path.
Every other governed operation executes under its original profile identity,
with the same fail-fast producer logic and durable progress. Independent Release
readiness uses `python3 -m tooling.nonperformance_production_readiness
--artifact-directory <fresh-directory>` to create fresh source, rebuild, regenerate,
and preserve original producer evidence without Full reuse. Its receipt and
profile-shaped evidence are explicitly non-authoritative.

Artifacts use `strling-nonperformance-readiness`, `authoritative: false`,
`performance_deferred: true`, and `closure_authorized: false`. They enumerate
every intentionally deferred governed definition and are rejected by the normal
profile schema, product certification, and attestation path. Deferred operations
are never recorded as passed. No normal profile membership, performance
baseline, threshold, sample count, conditioning, isolation, or authentication
rule changes. H08 remains open. The final performance-inclusive campaign may
start only after the owner explicitly confirms an idle host.

Initial atomic proof passes all eight readiness tests and the runner-bundle
fixture on both Linux and Windows. Real authorized-key signing and isolated
signature verification pass under a separate development namespace; that same
signature is rejected under the authoritative namespace. The closure projection
has a deterministic, schema-valid, history-preserving dry self-test and rejects
missing, partial, or invalid authoritative performance sample counts. None of
these diagnostics is an authoritative profile or closure result.

The ignored native owner initially lost its exit receipt because Windows
PowerShell treats ordinary native stderr as a terminating error under
`ErrorActionPreference=Stop`. An exact two-case reproducer identifies that cause.
Direct process stream capture retains both stdout and stderr under the same
strict preference, with an unconditional exit receipt. Only unfinished dependent
validation was resumed after confirming the former owner and child were absent.
The existing immutable verifier pin rejects current-format synthetic evidence;
reviewed verifier-promotion authority remains a separate pending decision.

The retained dependent suite passed 244 tests (one declared skip). Static
analysis then correctly rejected six new unmanaged import suppressions. A local
compatibility loader removed those suppressions without changing the existing
profile controller or the managed suppression baseline. All eight readiness
tests, standalone operation selection, and the unchanged 53-suppression static
gate passed the focused correction; no performance measurement was repeated.

### October 2 dependency-risk readiness correction

Clean development candidate `97bb1ee21fcf920e08a2b7daf2ab327ad5b80b02`
passed Local non-performance readiness 36/36 and Pull Request non-performance
readiness 77/77. Full readiness stopped at operation 3 after two passes:
`security_dependency_risk@repository` reported blocking high-severity
brace-expansion advisories in the TypeScript/LSP locks and Jackson advisories in
the shared JVM/Kotlin graph. The exact security command reproduced all four
failed checks with completed retrieval; 119 Full operations were not reached.
Independent Release and downstream campaign signing did not start. No
performance observations or authenticated samples were consumed.

The narrow repair refreshes only brace-expansion patch releases within existing
declared ranges and the shared Jackson maintenance pin, preserving all security
and performance policies. Gradle owns its lock and verification-metadata
serialization; the registered JVM producer owns the release-graph projection.
Repeated advisory proof and direct-dependent validation must pass before any
readiness retry.

A read-only comparison of the actual selected stage definitions proves that
Full contains all 36 Local and 77 Pull Request non-performance operations with
identical definitions. The repaired SHA will nevertheless execute Local and
Pull Request afresh before Full, so each readiness profile has its own exact-SHA
result. The retained earlier-SHA artifacts remain historical and are not
relabeled. Independent Release still executes afresh without Full evidence
reuse. Authoritative final certification will execute its normal governed
profile progression with performance restored, only after explicit idle-host
confirmation. H08 remains open.

### October 2 exact JUnit test-scope decision and atomic proof

The owner approved only the exact JUnit BOM and JUnit test dependencies under
the existing test-classpath license policy. Native Gradle lock regeneration
records the JUnit BOM 5.10.1 on `testImplementationDependenciesMetadata` as
well as its two test classpaths. The exact scoped disposition now names that
test metadata configuration; package, version, license, dependency root,
required usage, and every production/runtime restriction remain unchanged.
A negative regression adds `runtimeClasspath` to that exact JUnit lock row and
requires a scope violation. No generalized waiver or distributed dependency
permission was added.

The focused three-test scope proof and all 70 affected security/JVM unit tests
pass. Two independent live `security.py risk --json` invocations produce
identical evidence: 54 passed checks, only the existing
`WVR-SEC-VSCE-LICENSE-001` waiver, and zero failed, unavailable, or incomplete
checks. Dependency integrity, static analysis with its unchanged 53 managed
suppressions, governance and architecture, hygiene, formatting, and whitespace
also pass. All 15 previously unfinished unaffected direct dependents passed
separately. The retained Windows wrapper did not write its exit JSON, so no
wrapper exit code is inferred; its final shell pass marker and each atomic
operation output are preserved. No readiness profile or performance operation
ran during this correction.

The owner chose the post-authoritative verifier-promotion sequence. The old
immutable pin remains unchanged and is not claimed compatible with the current
signed evidence format. After explicit idle-host confirmation, a complete
performance-inclusive campaign must qualify the new verifier revision; a
pin-only workflow commit must then create a new source identity and a second
complete Local, Pull Request, Full, and independent no-reuse Release campaign
must precede trusted cloud verification and formal closure. The first
campaign's Full/Release evidence cannot be reused. H08 remains open, and the
present development-only readiness evidence is never authoritative.

## AC authenticated semantic latency failure — 2026-10-18

Actual qualification source `ac931f72300d98c8511932966c0eed185badfa33`
passes Local 38, PR 80 and sample-free Full readiness 123 (122 PASS plus only
`WVR-SEC-VSCE-LICENSE-001`). Actual Full 1.30.0 then stops at 23 of 126 with
21 PASS, one sole waiver, one FAIL and103 not reached. First coordinate
`latency:semantic-analysis/fixture:semantic-common` authenticates 64 accepted
samples from64 attempts, zero rejected batches, median 35,159 ns against unchanged
27,838 ns relative/31,481 ns absolute ceilings. The other eight checks pass.
Full profile `c0b88a1576b2a240cb4b5b361e93d83a57564eccfa16e023105f2bf2a6bb1427`,
terminal `a787c6fe9a5742b12be5b209d52ceef92794cf6345714369f2dd4fc7d1a6fc6b`
and invocation `4f9c57effc314abfa79d9d2d70d5b664` are consumed and preserved.
There is no unchanged AC retry, Release, signing, trust promotion or closure.

Bounded diagnostics, explicitly not performance authority, attribute most
product cost to the streaming identity writer. Exact input normalization leaves
nine nodes/3,225 serialized bytes from twelve authored items. The second complete
seven-round comparison retains all unfavorable observations and642 protected
file hashes unchanged: existing digest 34,686 ns wall/32,424 ns CPU versus a bounded
fast path 16,036 ns wall/15,258 ns CPU. Terminal
`2fe493dd9680dfc7227749b4e4be29d81de41643bec9aaa3be1fef2e76ec459a`
is diagnostic evidence only. The first diagnostic and all pre-execution operator
guard failures are retained, not relabeled as certification.

The minimal product correction adds inline `Write::write_all` handling while
retaining 512-byte storage, exact serialized bytes/SHA-256, validation and errors.
All nine digest regressions pass twice each on Native Windows and WSL; pinned
native formatting passes. All-core/static dependents and isolated-output native
product compilation remain in progress. Performance/deep-quality identities,
shared-engine and stdlib evidence check unchanged; stale adversarial evidence
and ordinary LSP payload require their specific registered refresh/preparation
and direct dependents, followed by the complete 36-family gate and idempotence.
No new candidate is frozen and no new authenticated samples or authoritative
profile results are created by this engineering.

The waiver remains limited to the same ten development-only dependencies
through 2026-11-13. No threshold, baseline, sample-count, conditioning/isolation,
lockgraph, security scope or trust-pin change accompanies the product remedy.
Both actual 38/80/126/126 campaigns, fresh independent Releases, signing,
reviewed isolated qualification, exact pin-only promotion, pinned verification,
guarded closure projection and clean formally CLOSED final state remain
mandatory. H08 remains OPEN and autonomous completion ACTIVE.

Subsequent actual native compilation passes using the pinned Rust 1.75 and
canonical source remapping, with separate ignored output. Terminal
`5bc53f605975c93d05764e2fb93a82d439ca9fcb746229e11e0894506bb0ecdd`
binds executable `dddcd767e61fe544203c2b15a39407ff9b3d51f5aa7cbabb1e39c2622db649c0`
and all 642 held hashes unchanged. Independent audit also confirms the five
consumed AC binary/bundle identities are unchanged and the temporary build
drive is released. No authenticated samples, profile, freeze or promotion.
All-core/static dependents remain active; the actual corrected-product atomic
timing check is prepared and guard-tested, but has not executed.

The complete core/static plan subsequently passes: 91 Rust harness summaries
contain 498 passed, zero failed/ignored/measured tests; Clippy, formatting,
core contracts and governance also pass. Core terminal
`c9314c4877d7af606f9502a68aea5f0e2496a899f9df40b6d20d211f74ace4b0`
preserves all 642 held hashes. Actual corrected-product atomic diagnosis then
retains every round and all 650 held hashes; raw
`176aae466c420995890500d7b9efd095746bde7363c04405211a3e35b841eff4`
reports 27,907 ns API median, versus the unchanged 27,838 ns relative ceiling.
The improvement is marginal, not a performance PASS or a basis for freezing.
Further bounded-copy controls precede any additional product correction.
All prior data are retained; no new authenticated samples or profiles.

## Borrowed private indexes — 2026-10-18 engineering checkpoint

Balanced writer controls did not justify changing the 512-byte buffer. Private
capture/consumption indexes now borrow immutable identities, removing 36 temporary
node-key clones from the common fixture while public facts remain owned. A new
drop-the-input regression proves that ownership. Final formatted source passes
59 focused tests twice on each host, then the complete core suite has 499 passed
tests across 91 harnesses, with zero failed/ignored/measured. Clippy, formatting
and core contracts pass. Core terminal
`d159b486f52c82b239bd33d64fca47c5a76675eab47f64aac1f13283f11d66a1`
and separate native build terminal
`89961289f014e41d3707af7aff159075989beb4b7195d4bda282fe3bdc3e6a9d`
each preserve 642 protected hashes.

After every retained owner completed, one unauthenticated API diagnostic retained
all seven wall rounds: 23,062, 22,874, 22,977, 22,774, 23,747, 25,393 and 25,947 ns.
Median wall/CPU is 23,062/22,888 ns against unchanged 27,838/31,481 ns ceilings.
Raw `a24dd32be72fc1b3a22d577fbf0f63861b7e34fe6104e59a0c9c9927d27e760e`
and terminal `ecb924603ee28a9cab72a87db0dbb5cdd0872b65fd57c45f4d72149abf379d38`
preserve all 722 held hashes. This is a dirty-source predictor, not certification.

The initial whole-inventory wrapper hit its arbitrary 900-second watchdog and
returned no inventory result. Its failed request and empty streams are preserved;
independent audit proves all 642 protected hashes unchanged. It was not replayed.
Six canonical atomic checks instead isolate stale LSP input fingerprints,
performance test-source identity and adversarial source identity; deep-quality,
shared-engine and stdlib evidence pass unchanged. Specific governed repairs,
complete 36-family integrity, direct dependents, prerequisites and a clean new
candidate remain pending. No baseline values, ceilings, samples, conditioning,
security scope, lockgraph or trust pins changed. At this checkpoint H08 is OPEN;
both complete campaigns, signing, immutable qualification/promotion and closure
remain outstanding. All new engineering creates zero authenticated samples and
zero authoritative profile results.

The specific governed performance identity correction subsequently passes all
six stages, including repeated generation, registered verification, the one-test
identity regression twice and two artifact-integrity unit tests. Exactly one test
hash and six dependent fingerprint fields change; all measured values, ceilings,
budgets and 718 other protected hashes remain unchanged. Terminal
`499be4fb2c54907ab9df96cbf4a52f619898de87c7990be7cdf7fd64c2a07e29`
proves byte-idempotence, not recalibration or certification. Adversarial refresh,
ordinary LSP preparation and complete 36-family integrity remain pending.

The governed adversarial refresh subsequently completes five stages: fresh
repeated real-engine observations, check, a second idempotent real generation,
recheck and 39 direct unit regressions. Each governed run retains 41 cases,
205 target-profile compiles and 1,531 runtime executions, with zero findings.
Semantic observations, runtime identities, denominators and all raw shards are
unchanged; only four intended source identities and provenance metadata change.
Terminal `03afc6e9598c80ddbcbe080a212577cdff30fe1e4b699857668143f60844cca2`
preserves 785 other protected hashes. This creates no authenticated performance
samples or authoritative profile. LSP preparation and complete integrity remain
before the new candidate; both authoritative campaigns and closure are pending.

## Integrated generated-state preparation — 2026-10-18 03:33 UTC

The retained ordinary preparation completes with exit 0. Its complete initial
inventory has 35 fresh families and only the diagnosed stale LSP family; the
canonical repair, byte-idempotence, 37 registered direct tests and first isolated
build check pass. All 36 final families pass, with no blocked family. A second
actual independent build check reproduces the same 22-file payload without
mutation. Only the two LSP core binaries and their input/output manifest change;
all 808 protected file hashes remain unchanged.

Terminal `d3c40bdd574172bc835d8d95821f7903a7a2f4525b0722a29398cb23a43903ca`
and independent raw-receipt audit
`28562427eb87041800f7548ccaac84cb0a869552cfe9ef977aa52b9bd01d3200`
bind the exact five-file product identity, canonical compiler bytes, registered
commands, 22 original payload backups and both real build results. The ordinary
preparation itself takes 3,566.8875 seconds (about 59.45 minutes); this includes
the complete inventory, repair, recheck and direct dependents, not just generation.

This supersedes only the pending ordinary synchronization and complete-inventory
checks above. The failed 900-second operator attempt remains failed and retained;
the later run followed two verified governed corrections, not an unchanged replay.
This is dirty-source engineering evidence: zero authenticated performance samples,
zero authoritative profiles and no freeze, signing or trust promotion. Remaining
prerequisites, exact-path commit, fresh clean-source preparation and both complete
authoritative campaigns still precede formal H08 closure. H08 remains OPEN.

## Completed sample-free prerequisites — 2026-10-18 05:38 UTC

All 18 source-bound engineering stages finish with exit 0: governance, exact
runtimes, script-mode preflight, independent-setup/readiness regressions, lint,
hygiene, formatting, contracts, three security checks, attestation contract,
the immutable artifact-only prefix, and complete tooling-unit discovery/execution.
The prefix checks all 36 registered families and remains explicitly diagnostic,
not a complete PR profile. Security risk reports 54 passed checks and only the
approved VSCE license waiver covering the same ten development-only dependencies.

The WSL suite discovers 1,493 cases: 1,492 execute successfully and the single
Windows-only live-probe integration is explicitly skipped on that platform.
That exact case subsequently runs natively: one passed, zero skips, successful
CPU-20 metadata probe and attestation consistency. It is not CPU-1 conditioning,
baseline admission or performance qualification. No host-wide settings change.

Prerequisite terminal
`f60331f52c1cbdc81b3255c2b1c5ecb1ee26aa37b70c190c9115de31febcb536`
and independent audit
`d0f685f453d7e232b8ff1da888fb49001f622d5ab0fc4aa2b09037d44b1cebf9`
reconstruct all 18 guarded executions, 36 streams, exact commands and the real
unit denominator. All 2,310 source/generated/Git snapshot entries, 808 protected
hashes and 603 retained operation/calibration JSON receipts remain unchanged.
Native-unit terminal
`8dc05f7b7d269f96088182b2d3537d692daa8fc8b76f8903c914314b2ab0d714`
also preserves source and retained receipts. These results produce zero new
authenticated performance samples and zero authoritative profiles. They supersede
only the pending working-tree prerequisites, not clean-source preparation,
candidate freeze, actual campaigns, signing, pinned verification or formal closure.

## ECMAScript allocation correction — 2026-10-19 engineering checkpoint

Candidate `d4e38a0ee1838afd08ef95d28ffecb6705459240` completed actual Local 38
and PR 80, then fresh sample-free Full readiness. Full stopped at operation
23/126: 21 PASS, the sole VSCE license waiver, one FAIL and 103 unreached.
ECMAScript lower/serialize semantic-common latency was 43,843 ns versus unchanged
39,592 ns relative and 43,192 ns absolute ceilings. All 25 completed coordinates
and 1,475 authenticated samples remain preserved (1,411 request/resource and 64
paired CLI controls). The earlier semantic-analysis coordinate now passes at
23,033 ns. D4 is consumed and will not be replayed unchanged.

Failed Full profile `b05846eebe89af31f26b97ec23974f790c142d6022616271808945ed9f1e0180`
and independent failed-attempt audit
`eb52a32eb4b335903704ef616206925f2065b38ad0feee06177a5bedcf95af88`
remain failed evidence, not qualification authority. No Release or signing followed.

The serializer now borrows plain scalar UTF-8 from a reusable four-byte buffer
and fixed short escapes from static strings. Exact spellings, owned output,
validation, limits and errors are unchanged. Four focused tests pass twice,
including every 1,112,064 valid Unicode scalar and the exact 16 MiB boundary;
22 direct tests and 502 core tests across 91 harnesses pass, together with Clippy,
formatting and contracts. Component terminal
`674825b919e243e678c9adaa7a38b291c9fdaf0fde4af90b36b1d04bbe7b2631`
binds the uncommitted source, not a new frozen candidate.

Independent atomic audit
`d447a8602e0cf91b547d018348c71ef09fb09f6d38d16a5cb1bb0e56e4ee3a60`
reconstructs both seven-round wall/CPU cohorts, exact commands, equal complete
TargetArtifact and all 161 held hashes. Serialization median wall/CPU improves
from 17,427/17,166 to 13,844/13,351 ns; lowering stays stable. Both combined
distributions retain unfavorable late-round increases. Their different medians
are not a stable 51% speedup or performance PASS. Two earlier operator guard
failures are preserved; the corrected diagnostic audits exact dependency code
and inputs without rewriting metadata, rebuilding the completed runner or
weakening any certification rule.

Six registered checks then preserve all 2,353 held hashes. Deep-quality,
shared-engine, stdlib and performance identities pass unchanged. Only LSP input
fingerprints and adversarial source identity are stale. Terminal
`da4542dbf06d664418e7fd1beda592e7510a1d0de4f2b934ecababfd2cb70a89`
preserves both failures; governed adversarial execution and canonical ordinary
LSP repair, complete 36-family integrity and direct dependents remain pending.
No baseline, calibration, lockfile or network-evidence refresh is indicated.

This engineering adds zero authenticated samples and zero authoritative profile
results. Both fresh qualification/promotion campaigns, independent Releases,
signing, immutable verification and guarded clean formal closure remain pending.
H08 is OPEN; autonomous continuation remains ACTIVE.

The specific governed adversarial refresh subsequently passes all six stages:
governance, real repeated canonical observations, check, a second byte-idempotent
real generation, recheck and 39 direct regressions. Terminal
`9089b7b4fbe88899bfc9b59fd480ed598ff411f582ca449932ed6e7657539a11`
preserves 2,375 other hashes. Independent reconstruction verifies all 12 streams,
the original index backup and unchanged raw shards. Each governed run covers
41 cases, 95 subjects, 205 target-profile compiles and 1,531 runtime executions,
with zero findings. Semantic material, runtime identities and denominators do
not change; only the serializer source identity and provenance metadata change.
This supersedes adversarial pending status only. LSP ordinary preparation,
complete 36-family integrity and prerequisites remain before a new candidate;
zero authenticated performance samples or authoritative profiles are produced.

### Canonical preparation independently audited — 2026-10-19 02:10 UTC

The actual ordinary preparation completes at 02:03:20 UTC. Its initial 35 fresh
families and one stale LSP family become all 36 registered families passed.
Only the kernel payload and derived package manifest change; the editor-core
binary remains identical. Canonical repair is byte-idempotent, all 37 registered
direct tests pass, and two real independent immutable builds reproduce the same
22-file payload. The original 22 payload backups and all 2,445 held file hashes
remain unchanged in the original production compiler context.

Terminal `b42c067d793c43a5270911093454c170db09c9da8fdb9006a5dc2bc13bf5c6b4`
and independent data-only audit
`68c7aa562a33fa819dc63a2a9cad4be0f3681ae68f4620d2931a2ab2db3ec844`
bind the actual commands, complete inventory, raw results and exact two-file
diff. No preparation or build was rerun to produce that audit. This supersedes
only ordinary LSP/full-inventory preparation pending status. It is dirty-source,
sample-free engineering evidence: zero new authenticated samples, authoritative
profiles, candidate freezes, signatures or trust promotions. Source-bound
prerequisites and fresh clean-source campaign admission remain required.

### Sample-free prerequisites and preserved interruption — 2026-10-19 05:30 UTC

A WSL boot change interrupts the first prerequisite owner's unit stage after
17 guarded operations. That attempt retains 760 completed test lines but no
suite summary, child completion or terminal receipt; its exit is unknown and
it remains incomplete. Independent audit
`d809e8c4bfc80415da9ff3431bfe279d9dec84fc17734999453e6c9858262381`
verifies the completed predecessors, actual immutable 36-family prefix, 2,452
protected hashes and 605 measurement receipts. No completed predecessor is
replayed, and no original terminal is fabricated.

A separate unit-only completion performs fresh discovery and the complete
1,493-case suite: 1,492 execute successfully and only the exact Windows-only
integration is skipped. Terminal
`2fadf36550e35e4d96bebf64edcfdcd92d97b870d1be083fc26d8ca67f46dabd`
and independent audit
`ef4fa875946cc8e557aafd5c01c88d3708fc957de7a3a9f6d245e4c938da43cf`
preserve the interrupted namespace and all prior authority. That exact native
case then passes one of one with zero skips and successful CPU-20 metadata
probe; terminal
`584bea283ea392598111bf4fc828affd4ffbe538a8d6c66cf6f4a7280a6ec458`
and independent native audit
`e0e42aeaf04ec7a46b95a7220d6dca490c58a28e962e667c4ab944094346a5ad`
remain non-authoritative platform-unit evidence, not CPU-1 baseline admission.

Final joined audit
`d61b629786842c80995893cfe7299d2bdae8b658c7ec27dfc3831894823974ac`
verifies 18 unique prerequisite operations from 19 guarded executions (one
repeated discovery), 1,493 distinct complementary unit cases, all 72 original
interrupted files, 2,310 source/generated/Git entries, 2,460 protected hashes and
the unchanged 605-receipt measurement inventory. The compiler context is
unchanged. These are pre-annotation dirty-source proofs, not a frozen candidate.
Zero authenticated performance samples or authoritative profiles are created.
Only prerequisite pending status is superseded; fresh clean-source preparation,
admission, both whole campaigns and signed/trusted formal closure remain required.

### Qualification stop and UI receipt disappearance — 2026-10-19

Clean `6f2e7c751ee1069105277c38ebe5cffd2bbed329` completed fresh
36-family preparation, 17 prerequisites, complementary 1,493 unit cases and
strict original CPU-1 admission before freeze. Actual Local passes all 38
operations and its controller guards. PR executes 12/80: 11 PASS, one FAIL,
68 unreached. `generate_check@repository` exits 2 while inspecting an
application-owned `.git/refs/codex/turn-diffs/captures` receipt. Terminal
`0fa2683beab4fa53f21469430fb158677f4acc54f3a80aba981342be8159f308`
and failed PR artifact
`e7a37936dafbf9ec1f67461fdec03d22a80ed1fe97ac068e0db776e8f66b38d9`
remain immutable; this candidate is consumed and is not replayed unchanged.

Atomic fixtures reproduce disappearance at lstat, digest read and symbolic-ref
read for both already-excluded UI namespaces, on Native Windows and WSL.
The correction tolerates only FileNotFoundError followed by a second lstat
confirming absence in those exact namespaces. Real/adjacent refs, present or
replaced nodes, aliases, permission errors and other I/O failures remain fatal.
No source-authority scope, profile membership or certification contract changes.
The original diagnostic omitted its underlying OS exception; this limitation
is retained, and the failed PR is not reclassified as passing.

All five affected generated-artifact modules pass twice: 122 tests each WSL
run with zero skips; Native runs have zero failures/errors and 12 existing
filesystem-capability skips covered by WSL. Ruff 0.15.21 format/check passes.
Independent receipt reconstruction validates both actual artifacts, commands,
ordered intervals, streams and all 605 retained measurement hashes. A later
WSL boot changes mount-device metadata: all 16 original Git-node digests are
reconstructed from identical bytes, inode and mode using the uniquely matching
original device 84. Raw cross-boot hashes are not called equal, and production
node-identity guards are not relaxed. The only source changes at that audit
are the two intended tooling/test paths; these record annotations follow it.

This supersedes only diagnosis and focused correction pending status. Exact-path
commit, complete 36-family new-source gate, fresh prerequisites/admission and
both whole 38/80/126/126 campaigns remain required, with independent Releases,
actual signing, isolated immutable qualification/pinned verification and guarded
formal closure. Correction tests produce no new authoritative profile, sample,
signature or trust evidence. H08 remains OPEN; continuation remains ACTIVE.

### Engineering validator index guard — 2026-10-19

The first dirty-source validation executes all 122 direct cases successfully
but fails its strict source/Git postguard; terminal
`1fb3879c3c7cea19b5ddc37cd3a5ea6fca3b2375bdd66394fb748dd4709a6928`
is retained as FAILED, not accepted validation. No later static check runs.
The five held source bytes remain unchanged; independent postmortem attribution
isolates the index node, while the other 15 Git identities reconstruct exactly.
The original validator did not retain its after-snapshot, so that diagnostic
limitation is preserved rather than inventing a missing original observation.

An atomic disposable existing Git fixture reproduces the operator's exact
`git --no-optional-locks diff --name-only --` replacing the index:
Git trace records `do_write_index` on the fixture authority index. The existing
canonical governance private-index collector reports the same real change and
preserves the source index's bytes, inode, device and mode; writes occur only
in its disposable private copy. This is an operator-helper defect, not evidence
of a product regression. The failed helper and its six receipts remain immutable.

A new ignored helper uses that existing canonical collector and a read-only
cached plumbing comparison, retains full source/generated/Git node guards,
and records exact after-snapshots before accepting any stage. New helper guard
tests and actual source-bound static validation remain pending at this annotation.
No threshold, baseline, profile, sample, security, license or trust contract
changes. The consumed 6f campaign is not replayed; H08 remains OPEN/ACTIVE.

### Engineering record parse correction — 2026-10-19

Corrected operator v2 passes all 122 direct cases without skips and its strict
whole-source/generated/Git and held-receipt guards. Its later governance command
exits 2 because the previous operator annotation indented the root `commits`
key by two spaces. Terminal
`f6b88e564afba5bd76091bdd2d6bae6f4143d9b9421e346ff00ac093343b77ad`
remains FAILED; lint, hygiene and formatting were not reached. The exact raw
parser error and all eleven v2 output files are preserved.

Canonical parser reproduction fails on the same bytes. An in-memory control
changes only that key's root indentation and passes the unchanged task-record
schema with the same 54 commits and 37 prior checkpoints. This annotation defect
is not a product or certification-contract defect. The real-file correction
restores the root key and adds this truthful checkpoint; no historical claim
is changed. Registry mapping again finds no affected generated family.

The corrected private-index operator's 28 Native/WSL guard cases remain helper
tests, not certification evidence. A fresh static-only continuation must now
validate the exact updated records through governance, lint, hygiene and full
format checking, retaining both failed validators and the earlier guarded unit
proof. Independent reconstruction, exact-path commit, fresh clean-source gates
and both whole authoritative campaigns remain required. H08 stays OPEN/ACTIVE;
no new profile, authenticated sample, signature, trust or closure is claimed.

### Completed receipt-correction engineering proof — 2026-10-19

Independent audit
`d974d93e422d796ec9347f01e3c1fb6f91245538e47a58c85e069b3eb2b0b115`
reconstructs the real 122-case guarded direct run and all four later static
commands from ten exact raw streams, their original child/guard receipts and
ordered intervals. Governance passes four controls and 33 architecture rules;
lint has zero findings, hygiene covers 2,270 tracked files with zero findings,
and both full repository formatters pass. Static terminal
`431e737e24f19039466c270131dab8c801169666d7aaf67e6c56cf7e07aa2578`
is successful; earlier v1/v2 validation failures stay FAILED.

All 645 held hashes, including the original 605 measurement receipts, remain
unchanged. The independent current 2,310-entry source/generated/Git snapshot
equals the original v3 snapshot exactly, including all 16 Git node identities;
the later WSL boot happens to retain device 84. No production guard is
normalized. Only the three documented migration-record annotations separate
the guarded v2 unit source from the v3 static source. These are dirty-source
engineering proofs, not exact-candidate profile or performance evidence.

This checkpoint supersedes only correction engineering validation pending
status. Final evidence-only record schema/format checks and exact five-path
commit precede fresh clean-source complete 36-family preparation/recheck/direct
dependents, prerequisites, complete unit discovery, native CPU-1 admission and
source-bound helpers. Both whole source-distinct 38/80/126/126 campaigns,
independent fresh Releases, actual signing and isolated immutable qualification
then pinned verification remain mandatory before guarded formal closure.
H08 remains OPEN; autonomous continuation remains ACTIVE.

### Certification feedback-time optimization — 2026-10-19

The human explicitly prioritizes earlier actionable failure and faster complete
certification, with every feature, check, workload, threshold, independent fresh
execution and evidence safeguard retained. Reconstructed historical timings are
a baseline, not a controlled speedup: consumed 6f Local took 6,750.184 monotonic
seconds; generated integrity plus generation checks took 3,024.557 seconds
(44.81%). Its first profile start to typed PR failure took 10,749 UTC seconds.
Complete successful qualification/promotion/Release/signing/closure duration is
still unmeasured; no numeric end-to-end saving or estimate is claimed.

Clean engineering parent `72817d00` completed canonical 36-family preparation:
35 initially fresh plus one ordinary stale LSP manifest became 36 passing
families. Independent audit
`426371cd5b063412c0eb4eac8613600c777f347ffd4692fb8ce266c302d4c43b`
reconstructs 37 direct tests and two fresh immutable 22-file builds. Only the
manifest's source commit, timestamp and fingerprint changed; payload fingerprint
`sha256:f184cb79bb1dcbd8606f1e8a508ef128136729a08d51e05e17a4453a583559ca`
remained identical. These are preparation proofs, not a frozen candidate or
authoritative profile. The subsequent scheduling change invalidates prospective
728 qualification and requires a new clean-source gate.

Three fresh full 2,310-entry snapshot diagnostics took 32.043, 34.736 and
27.908 monotonic seconds. Directional profiling identified serial Git-reference
validation as a dominant cost; overlapping thread/profile times are not summed.
The narrow correction schedules the same lazy reference census through the
existing bounded eight-reader mechanism. Every node, including both excluded UI
namespaces, retains fresh metadata/content, alias and symbolic-reference checks.
HEAD precedes parallel work; results and node failures retain census order;
workers join before return. Original raw Git read errors remain raw, while
other snapshot callers keep their existing wrapped errors. No pruning, cached
acceptance, identity normalization or guard boundary is introduced or removed.

Fixed three-pair alternating comparisons use the same 344 physical fixture nodes
and modes, including both UI namespaces, with fresh reads each execution.
Successful validation retains exact nine-entry authority output and full node
coverage. A separate late-census alias fault measures typed actionable rejection.
All six success and six rejection executions, including the unfavorable 8.091s
bounded rejection, remain retained. Median monotonic validation time changes
26.817715s to 5.014217s (81.30% lower); median rejection time changes 31.303731s
to 5.359125s (82.88% lower). Parent CPU medians change 1.376910s to 0.729905s
and 1.421673s to 0.711116s respectively. UTC intervals remain separately recorded.
The entire diagnostic, including fixture and preservation overhead, took
1,168.821482 monotonic seconds / 1,231.024795 UTC seconds, not the duration of
a certification campaign.

Comparison terminal
`36c426a0fb620c4cf8ceb3f5f47d68437bd1dcaa4d8e804bbb8f9624741e6b58`
and independent data-only report
`0ea6fe42145ada7491cd1b5c9fd46a8b7765ade7633c7ebe487769f265a2dce2`
bind all 12 rows, 22 raw input files, exact fixture identities/restoration,
2,310 fresh source/generated/Git entries and 3,157 held hashes including all
605 historical measurement receipts. The auditor imports no candidate helper or
verifier and reruns no benchmark. These are unconditioned atomic engineering
measurements, not governed performance acceptance or full-path speedups.
The original measured Python bytes are retained; subsequent canonical Ruff
formatting preserves both complete Python ASTs exactly.

The seven added regressions cover full census/digest/order equivalence, lazy
bounded scheduling, eight real workers, HEAD rejection before parallel work,
original error identity, joined first-error handling and uncached rereads.
Focused 86-case WSL validation has zero skips; Native has five existing
platform-specific skips covered by WSL. Broader source-bound direct/static
validation, exact-path commit, complete 36-family preparation/direct dependents,
fresh prerequisites/whole unit/CPU-1 admission and both complete source-distinct
38/80/126/126 campaigns remain mandatory. Each campaign needs fresh independent
no-reuse Release, actual signing, isolated reviewed qualification before pin-only
promotion, immutable pinned verification and guarded formal closure.
All failed/consumed evidence and statistical, security, license, architecture,
conditioning, isolation and trust requirements remain unchanged.
H08 remains OPEN; autonomous continuation remains ACTIVE.

### Scheduling correction validation completed — 2026-10-19

Independent report
`286e522c14ebf365b32df9c560af884f44801d4688d14059691d3e7bdfa67902`
reconstructs all six guarded stages and 12 original streams: 129 complete direct
cases twice in WSL with zero skips, four governance controls and 33 architecture
rules, lint, hygiene over 2,270 tracked files and both repository formatters.
Original terminal
`6f1e84442cf7cadec670f60c60eb5bd0916dbd2acf80e70b31cc419310cfb484`
is successful. All 33 original namespace files, 3,186 original held hashes,
3,220 audit-held hashes, 605 measurement receipts and the complete 2,310-entry
current source/generated/Git identity remain intact. No check is rerun to audit.

This supersedes only broader correction validation pending status above.
These final evidence-only annotations follow the audited source; the two
formatted Python files are unchanged. Final record schema/format checks and the
exact five-path engineering commit still precede fresh clean-source 36-family
preparation, direct dependents and all required prerequisites/admission.
Neither the completed engineering validation nor the measured atomic savings
complete an authoritative profile, performance gate, independent Release,
signature, trust qualification or closure. H08 remains OPEN and ACTIVE.

### Lossless early-input feedback after consumed qualification — 2026-10-20 (UTC)

Frozen source `8a941b5572c4bf9bcf9c6a38a000c0e0ad6a1ce7` completed actual
Local 38/38 PASS, then consumed PR failed outside the operation list: generated
integrity passed, but the required exact-environment preflight found
`STRLING_CPYTHON_311_BINARY` missing. PR therefore has one completed PASS and
79 unreached operations, not a completed 80-operation result. No PR artifact,
Full, Release, new authenticated sample, signature or trust result was created.
Terminal `68ba205ac13699fc7f508e52edc1b2a87d972a4c83284b61096fcc00ba4988af`
and independent raw audit
`fd4f8384116a1cc3e217e123d14455ea46c1fcc744803a0a6eb725071c6a6a34`
retain that failure permanently. The failed source must never be replayed
unchanged. Its owner retired only through an acknowledged live handoff; exact
source originals and every failed helper/test receipt remain preserved.

The independently reconstructed Local duration was 5,527.765440 monotonic
seconds / 5,949.419902 UTC seconds, with 877.098604 user and 910.651900 system
child CPU seconds. PR took 1,070.327264 monotonic / 1,153.728106 UTC seconds,
with 139.577011 user and 109.246879 system child CPU seconds. Actionable failure
was observed 6,959.405269 monotonic seconds after owner start, or 7,255.332656
UTC seconds after the Local child started; the later mandatory postguard
terminal is recorded separately. Dominant Local stage observations were core
tests 1,327.634s, generated integrity 1,177.636s and generation checks 979.787s.
PR spent 1,036.205s on generated integrity before this missing-input failure.
These are actual failed-path observations, not controlled whole-path gains.

The orchestration handoff retained the compiler/build context but omitted the
six exact-runtime, Java and Maven environment exports used by the earlier
successful preflight. A controlled atomic diagnostic proved the unchanged
validator rejects the missing CPython key in 0.339062s and passes with the
complete canonical handoff in 3.843886s, including the original offline Maven
compile probe. This establishes a certification integration defect, not a
product runtime regression. Future source-bound requests must explicitly bind
all compiler/build settings and the complete canonical runtime handoff.

The correction adds a read-only early input validator. It freshly verifies
exact runtimes, every governed Maven artifact hash, the prepared bridge and
Maven availability without compiling. The complete immutable generated prefix
still executes, followed by the original full build-capable preflight with a
fresh input verification and offline compile probe. A source-drift guard also
fences the early hook. No profile membership, check, threshold, workload,
sample, independence, conditioning, security, license or trust guarantee is
removed. Two existing synthetic tests now inject their home and Maven lookup
instead of depending on the Windows host; real Linux compile evidence remains
separate. All rejected guard/test attempts remain failed and immutable.

Fixed three-pair alternating atomic comparisons retain all 15 executions,
including unfavorable timings: six complete old/new validator executions,
six exact missing-key rejections and three additional read-only input checks.
Every complete result is identical and every full offline compile is retained.
Full-validator medians were 3.145990s original and 3.126697s current; missing-key
medians were 0.378668s and 0.385647s. The additional input check costs 0.668581s
median on passing inputs. Baseline source uses an explicit immutable-source
compile loader, so these unconditioned atomic numbers do not establish causal
throughput gains. Earlier scheduling avoids discovering configuration defects
after expensive work; the historical 1,036.205s is an opportunity, not a paired
measured saving. Successful end-to-end certification duration and its gain
remain unmeasured; no numeric estimate is claimed.

Independent report
`7a1256152216c0e194b769d005aa8dbcf38250751f1e218ae04e771e43a150cf`
reconstructs comparison report
`696d680699b9c7026a19765c125333183aa4a260a32a1064bb1f2190f3fcecfb`
and seven actual regression runs: 49 Native cases, two 49-case WSL rounds,
and two expanded 143-case rounds on each platform. WSL has zero skips. Seven
Native fixture-symlink skip events affect six methods; all 143 actual case
identities match and every affected method passes in WSL. The data-only audit
replays no test or workload and imports no candidate product, generator or
verifier code. It preserves all 2,310 source/generated/Git entries, 3,801 held
files and 605 historical measurement receipts, with only the five explicitly
recorded engineering source differences and no identity normalization.

These are dirty-source engineering and atomic proofs, not a new frozen
candidate or certification acceptance. Final source-bound governance, lint,
hygiene, complete format/schema checks and the exact eight-path engineering
commit precede fresh clean-source complete 36-family canonical preparation,
recheck, direct dependents, actual complete unit discovery, exact-runtime and
security prerequisites, original CPU-1 admission and fresh helper guards.
Both whole source-distinct 38/80/126/126 campaigns, fresh independent no-reuse
Release each, actual signing, isolated reviewed qualification before pin-only
promotion, immutable pinned verification and guarded formal closure remain
mandatory. H08 stays OPEN; autonomous continuation stays ACTIVE.

Actual pre-commit validation subsequently completed all five unchanged commands:
record schema, repository lint, hygiene, complete format checking and governance.
Static terminal
`adb1af2f6f72e3698bf0b66cbed13f1902497fa44ed546ab3d2688e9aa13e363`
retains 1,072.469534 monotonic / 1,072.576138 UTC seconds. The children took
353.637674s; all sixty mandatory fresh guard phases took 717.976615s.
These costs are reported, not removed or extrapolated into certification gains.
Lint retained 53 managed suppressions and five waivers; hygiene checked 2,270
tracked files; governance passed four controls and all 33 architecture rules.

Independent raw audit
`caf1877f72df5d2db3cccaa0b1a4b14d01f5789a5863c83488ab4991f60cc3a9`
reconstructs every command, all ten streams, all sixty ordered guard intervals,
the complete 29 declared controls (23 compiler/build plus six runtime handoff
exports), all 2,310 source/generated/Git entries, 3,832 held files and all
605 historical measurement receipts. It replays no check, profile or workload
and imports no candidate product, generator or verifier code. The original
static source and these three pre-annotation records remain byte-preserved;
the five tested code/test files are unchanged by the final annotations.

This supersedes final static validation pending status only. The exact
eight-path local engineering commit, final annotation schema/format validation
and fresh clean-source preparation do not certify a release. All 36 registered
families, every direct dependent and prerequisite, both whole source-distinct
campaigns and their fresh independent no-reuse Releases, actual signing and
immutable trusted verification remain mandatory. No actionable failure
occurred in this static run; total successful certification time and its
improvement remain unmeasured. H08 remains OPEN and ACTIVE.

### Fresh-source Lua bootstrap dependency ordering — 2026-10-21 (UTC)

Consumed source 3d9bdad30739a59fc0d51567dd808d7248cf9519 completed actual
Local 38/38, PR 80/80 and the canonical Full child: 125 PASS plus only
WVR-SEC-VSCE-LICENSE-001 across 126 operations, with zero failed, unavailable
or incomplete. Guarded acceptance
ba6981922fc8df7219113eb72686b30a870845d5f24ae5e26dc25161b59445f8 binds independent
source/container and raw performance reconstruction of all 54 coordinates and
3,332 values under unchanged ceilings and sample counts. The original Full
wrapper failure 476c34c90d94f5e6d7eb257699180b055408b6714294a28f8abf910a6924c3b9
remains FAILED: it compared the registry base command with the complete
canonical atomic invocation. Later acceptance checks every exact argument and
the original raw container; it neither relabels nor replays the failed attempt.

Fresh independent sample-free readiness subsequently failed during setup,
before any readiness profile, Release profile or new performance sampling.
Receipt cf73fa0a17fd6d316ee8597ebf4b9aebf3ac65e31e982543b4cd391f74005e18 and terminal
200bcabe4b54e831484f72e95197254ba60529104ba2698ba254f8f962c32a21 preserve that failure.
The independent source under nonperformance-readiness run
64a49e0e65a1473eaf98943c15342a69 remains untouched and must not be reused.
Setup reported 17 successful bindings and one Lua failure: the generated
numeric rockspec set was empty. Both governed launchers placed ordinary
preparation after setup, although Lua correctly requires its canonical
current-version rockspec before any LuaRocks action.

The failed child took 386.111204 monotonic / 422.978251 UTC seconds, including
88.095142 user and 43.641489 system CPU seconds. A read-only atomic check
reproduced the exact missing-output rejection in 0.179136 seconds against
identical source bytes; diagnostic
609c56de20f669332e297116df51bf42dc6c3142107860f568c9b4e0a7720c7e retains the pins.
These are different workloads, not a measured speedup or a whole-path estimate.

The correction shares the registered ordinary Lua generator and its exact
integrity check between both governed entrypoints before installers and setup.
Malformed, protected, noncanonical and redirected definitions fail closed.
Complete 36-family preparation remains after setup and before the immutable
profile; Lua setup remains check-only. No lock, baseline, authenticated
evidence, waiver, threshold, workload, sample count or profile is weakened.

Live retirement terminal
3882f70206d5533b7d05c42709e5858949ceb1b1b78f5473d81da046b9ae6e46 and release
fd7f9fc34cb95e212665834852972cca620c6aa2f78a4b36f263f520c8c0e753 preceded every
tracked edit. Twelve fresh guard phases retained 4,206 held files, 2,310 source
entries, 22 payload files, 607 receipts and all 29 execution controls. The
consumed source is retired, never eligible for unchanged authoritative replay;
its good partial results cannot certify the corrected new candidate.

Two actual 49-case rounds per platform pass: Native has 47 PASS plus two
explicitly POSIX-only fixture skips each round; WSL has 49 PASS and zero skips.
All case identities match and both skipped Native methods genuinely pass WSL.
Proofs c695906aefd5d711767366f3de141b647add2a0ec6f3691ff5c5bdd9c5d98240 and
20a7529217f0f0483f589aec4f294ad68613022dcd98d06115efa9077464bdf8 retain the runs.
An initial sandbox-denied Native fixture run remains failed; its already
tool-truncated output is explicitly incomplete, not full raw verification
proof. Scoped test access did not change security or privilege settings.

The first affected-subsystem run reported 191 cases and one failed isolated
readiness fixture; failure
dc7607936afd03a2a038508930e93c243e785129b05e4ffd4470338e18fc8aa7 is preserved.
That fixture replaced the repository with an empty temporary root without
injecting the new registered bootstrap plan. Its narrow correction in
tooling/tests/test_certification_readiness.py supplies the real registered
commands and asserts both precede npm/setup. The previously failing case
genuinely passes on Native and WSL. The complete corrected 191-case selection
then passes on both platforms: Native reports 14 skip events affecting 13
methods, all of which genuinely pass in the zero-skip WSL run. All 191 actual
case identities match. Proof
daa2c540a2afc75a2edd894a7795cacc9c0a285a250022b5c138b99ffb00299e retains every
case and skip row. This seventh direct-dependent test path adds no product
behavior, omitted check or broader waiver.

These dirty-source engineering proofs do not establish a certified SHA or
end-to-end gain. Broader/static/record-schema/full-format checks, exact-path
commit, complete registered check/preparation/recheck and affected dependents,
all fresh prerequisites and exact-candidate guards precede the next clean
freeze. Both source-distinct 38/80/126/126 campaigns, fresh independent no-reuse
Release each, signing, isolated reviewed qualification before pin-only
promotion, immutable pinned verification and guarded formal closure remain
mandatory. Successful total certification duration and gain remain unmeasured.
H08 stays OPEN and autonomous continuation stays ACTIVE.

### Source-bound bootstrap validation and index epoch — 2026-10-21 (UTC)

The first seven-path static operator failed its Git-identity guard before
executing any static command. Terminal
c64c0ba495a6ff745b853d2614922c9d55bc33a16c0ac5bce9425d8a6c3f6d14 remains FAILED.
Read-only diagnosis found only the physical index node differed from the
already retired frozen source. The writer and replacement time are unknown.
Independent bridge ce88aeb423b5e03fc8960b2f29664fd40b283b96578e92fabfde2c8b25e0c8eb
reconstructed all 2,270 staged entries and flags against the unchanged HEAD
tree, and retained three complete private-index observations with all 2,310
source/Git entries unchanged. This establishes a new dirty-engineering starting
epoch after genuine retirement; it does not normalize a frozen identity,
modify the real index, change a baseline, or excuse later mutation. The new
operator archives the actual index and requires its exact bytes, mode, device
and inode at every source fence. All failed sources and receipts remain intact.

The fresh static operator completed schema, repository lint, hygiene, complete
repository format checking and governance. Terminal
0fb45c64ceea503facefeae56b4e3b5fb1c9b73a6e6cc9af42345ae671ecc095 retains all five
actual results and all sixty mandatory guard intervals. Independent raw audit
6846118cd85fc4dc0db88cd30f76dd37a8f2867f68fbcb99d288145adadd34fb reconstructs every
command and ten whole streams, validates both fence boundaries, and freshly
checks all 2,310 source/Git entries, 4,238 retained files, 607 receipt paths,
22 payload files and the complete 29 execution controls. Twelve negative
guards pass on each platform with zero skips. No profile, workload or sample
was replayed; no candidate verifier was imported. The four tested code/test
files remain unchanged by these final record-only annotations, whose schema
and format still require final validation.

Actual static elapsed time was 1,270.205738 monotonic seconds: the five commands
sum to 409.250722s and sixty measured guard intervals to 725.942219s, leaving
135.012797s in other orchestration, census and receipt work. Guard attribution
is 249.500888s exact-source/private-index checking, 263.586139s whole-source
hashing, 185.549818s retained-file hashing, 20.979797s payload census, 6.300730s
compiler checks and 0.024847s physical context. These observations identify
lossless scheduling targets; they are not equivalent-workload before/after
results or a measured total-certification gain. No fence has been removed,
reused or weakened.

The registry maps none of the seven changed paths to an authoritative source
or generator input. Lua's existing registered commands and authority are
unchanged. Complete 36-family check/preparation/recheck and changed-family
dependents remain mandatory before a new clean candidate freeze. Old 3d9
results cannot certify that candidate. Both whole source-distinct campaigns,
fresh independent no-reuse Release each, signing, isolated reviewed verifier
qualification before pin-only promotion, pinned verification and guarded
formal closure remain uncompleted requirements. H08 remains OPEN and ACTIVE.
