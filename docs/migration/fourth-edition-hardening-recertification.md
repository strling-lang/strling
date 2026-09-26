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
