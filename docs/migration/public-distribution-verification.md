# Independent public distribution verification

Status: implementation in progress. Public execution has not occurred.

## Recovered authority

The clean starting source is `33e50ac033314dad089717a0ee20c0c7c310dea7`,
descended from certified packaging implementation
`021239608ffa5066e59bdebde9869e193fbb3eab`. The existing packaging root is
`19533d8d1de2248367616df5a6a6782156125efefe6c8e3be47e316ed7c0d2b0`.
Its immutable verifier is `642cc21f8f5d5ccabde1bb893076e02c624247a7`.
Historical H08 and packaging certificates remain preserved.

The local `dev` branch contains the closure and was clean, fourteen commits
ahead of `origin/dev`, before this task. No merge, remote development-branch
update, production tag, publication, or registry mutation is part of this work.
Existing worktree registrations and prior evidence remain untouched.

## Denominator and implementation gaps

The release-supply-chain manifest owns seventeen distribution artifacts,
twenty-one platform rows, fifteen Supported consumer rows, and six Preview
rows. Public verification derives its obligations from those rows: eight
identity/evidence checks for each distribution and eight functional/isolation
checks for each Supported platform row, currently 256 obligations. Preview
rows retain their explicit runtime limitations and do not gain support claims.

Existing payload inspection, signed supply-chain reconstruction, source
authentication, and consumer contracts are reused. The packaging consumer
entrypoint currently reads checkout-local subjects; this cannot by itself
establish public installation. The new retrieval boundary must authenticate
actual public bytes before isolated consumer execution. Registry metadata,
fixtures, staged packages, and publication receipts are not trust roots.

New implementation remains subject to focused mutation tests and fresh
source-bound certification. Historical profile results do not certify these
changes. No narrower certification exception has been assumed.

## Checkpoints

1. Source and contract recovery: baseline and denominator recovered. The
   unchanged immutable verifier authenticated the original signed source and
   closure, followed by complete supply-chain companion verification.
2. Schemas and trusted boundaries: in progress. Credential-free bounded HTTP,
   synthetic transport separation, exact obligation inventory, and explicit
   result-state reduction are under adversarial test.
3. Retrieval and consumers: pending.
4. Integration and certification: pending.
5. Independent closure: pending.

Actual public verification remains pending separately authorized publication.
Engineering fixtures can establish `READY`; they cannot establish `VERIFIED`.

## Engineering observations

-   The focused Windows suite passes 232 tests covering all seventeen retrieval
    routes, denominator and scope, authority separation, unsafe payloads and
    locations, network-versus-absence outcomes, consumer contracts, and existing
    publication security regressions. Further implementation is still in progress.
-   `target/public-verification/baseline-authentication-05/authentication.json`
    records successful independent baseline authentication. Earlier attempts are
    retained: Windows temporary-directory permissions, the non-secret
    `PROGRAMDATA` prerequisite of Windows OpenSSH, and a corrected distinction
    between implementation and evidence-closure checkouts. No signature or
    historical evidence was changed.
-   The exact certified Windows CPython 3.12 wheel passed complete file-graph
    authentication and installation in a fresh consumer environment through the
    new retrieval-only root. Canonical source and target compilation, expected
    native DLL SHA-256, and incompatible-kernel rejection passed. This is staged
    qualification, not public installation evidence. The first sandboxed attempt
    failed filesystem path resolution and was not relabeled successful.
-   Synthetic Conan revision files reconstructed both Windows and Linux consumer
    caches, each with 1,094 files, matching the existing registered normalized
    identities. Executable payload bytes came from the emulated retrieval set;
    only authenticated cache-layout metadata came from the certified exemplar.
-   No public release coordinate has been verified. Integration, remaining
    consumer scopes, comprehensive mutations, fresh source-bound profiles,
    independent reconstruction, and final clean committed closure remain pending.

The `staged-artifacts-01` and `staged-artifacts-02` runs independently
authenticated the preserved packaging certificate and passed all 17 artifact
routes. The second run preserves Conan empty directory headers required by
the real cache restore operation; normalized payload identity alone had not
exercised that installation requirement. Both runs are synthetic and record
zero qualified consumers themselves.

Separate staged Windows consumers now pass C, C++, C#, F#, Java, Python, and
Rust. Attempts `staged-consumers-windows-02` and `-03` remain failed evidence:
Conan directory layout and missing Windows SDK environment prerequisites
were corrected before fresh attempts. The restrictive environment now retains
only named nonsecret Windows SDK paths, disables .NET first-run certificate
generation, and rejects Gradle user initialization scripts. The C and Rust
consumers took 144.484 and 56.000 seconds respectively in attempt `-05`.
The protected-execution and request boundary suite separately passes 51 tests.
These are engineering observations, not current-source profile certification.

All fifteen registered Supported platform consumers subsequently passed staged
qualification: eight Windows rows and seven Linux rows. Windows Kotlin passed
in attempt `-06` using a fresh compiler-only Gradle cache. Linux attempt `-01`
passed C++, Go, Python, and Swift; its Dart failure remains retained. After
restoring only the two lockfile-authenticated Dart dependencies into a fresh
cache, attempt `-02` passed C, Dart, and Rust. No Preview scope was promoted.
The Linux receipts are retained under
`target/public-verification/linux-consumer-receipts`; original WSL workspaces
remain available. Separate runtime admission verified all 22 Windows and 20
Linux artifact/toolchain rows.

The focused public boundary suite passed 222 tests after the endpoint,
payload, metadata, and protected-execution corrections. A bounded resolver
control subsequently retrieved the official NuGet repository-signing index
without credentials. An earlier NUnit repository-signature control passed;
an author-primary FSharp.Core signature was rejected under the narrower
registered repository-signature comparison mode. Neither control establishes
public STRling installation. The broader regression run retains its genuine
stale profile-version assertion failures; corrected focused assertions pass.

The shared consumer executor now retains command, timing, exit status, and
stdout/stderr diagnostics. Public findings bind expected and observed identity,
environment, and supporting evidence. Canonical profile registration adds one
offline public contract operation to each profile; generated profile and
semantic-authority projections have been synchronized. Current-source profile
execution, independent reconstruction, signing, hosted verification, and clean
closure remain mandatory and pending.

The final focused public suite passes 228 tests, and the staged content-security
scan passes all seven checks. Missing aggregate scope receipts now retain an
explicit `INDETERMINATE` incident instead of losing the reconciliation report.
Additional consumer negatives reject missing native dependencies, unsupported
architectures, Preview promotion, and changed retrieved bytes before install.

Complete generated-artifact verification retained two failed attempts. The first
repository-state guard detected a concurrent task-record edit by this execution
owner. The source-stable second attempt stopped at the disposable
LSP payload, which still contained Linux executables on the Windows host. The
first registered Windows assembly attempt then found Linux esbuild in the
subtree's disposable dependency cache. A lockfile-preserving Windows `npm ci`
succeeded; canonical assembly is being rerun. These are preparation failures,
not historical certificate invalidation or waived checks.

The second Windows LSP assembly passed. The original broad regression run
completed in 3,059.29 seconds with 405 passed tests, 23 passed subtests, and
two failed stale profile-version assertions. Both assertions were corrected and
passed focused reruns; the original run remains failed. The 52 attestation tests
in that run passed. The authenticator now obtains its approved trust context
from the immutable verifier contract, allowing this task's separate certificate
without accepting a candidate-selected policy; both registered contexts reject
an invalid signature in focused tests.

The third complete generated check passed 38 families and failed the final
Kotlin product check because this shell lacked the preserved Maven path. The
registered focused command then passed with Maven 3.9.11 and the established
dependency cache; zero third-party verification entries changed. The original
complete attempt remains failed. Canonical preparation and complete generated
verification will run on the final frozen certification checkout.

Before verifier freeze, the complete public boundary suite passed 230 tests on
Linux. Windows passed 244 tests comprising the same public suite, all thirteen
profile-source identity tests, and the corrected canonical membership test.

Verifier revision `080107ed6d7893d60eb011fb83af09ac937eeb89` is frozen in a
separate clean checkout. It independently authenticated the preserved packaging
closure with the original packaging policy and rejected the same certificate
under the new public-verification policy. This is reader qualification, not a
rerun or reopening of H08 or packaging campaigns.

The integration preserves both historical certificate jobs and adds a separate
event-source public-verification certificate job to CI and hosted integrity.
The new jobs execute only the immutable reader and its new trust policy.
The public retrieval contract uses the same approved context; candidate request
data cannot select a different policy or reader. Four targeted workflow tests
and 29 hostile-mutation subtests passed, followed by repository governance.
