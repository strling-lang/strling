# Releasing STRling

[← Back to Developer Hub](index.md)

The authoritative Fourth Edition version, support, compatibility, release,
publication, and post-publication rules are maintained in
[`governance/release-policy.json`](../governance/release-policy.json). Read its
generated [`Release Policy`](release-policy.md) projection before changing
package metadata or release automation.

## Current preparation boundary

STRling `4.0.2` is the owner-authorized fix-forward identity and active coordinated
package projection. The version generator reads `product/version` in the release
policy and validates the complete inventory before updating any file. Independent
specification, protocol, ABI, transport-crate, and editor versions are preserved.
Never edit an individual product version as an independent authority.

The canonical projection check is:

```bash
python3 tooling/sync_versions.py --check
python3 tooling/release_policy.py --check
```

The Python manifest is a generated projection. Swift and Go use
product-mapped immutable tags; the Lua rockspec and Ruby gemspec use governed
release-time materialization/sentinel rules; the VS Code extension has an
independent Preview version and must state its exact compatible product range.

## Release lifecycle

Ruby publication pins the reviewed RubyGems 4.1.0 client and checks its version
before registry access. After the parent process verifies the protected exact
handoff, only the Ruby uploader child omits `GITHUB_ACTIONS` and unused GitHub/OIDC
credentials. RubyGems 4.1.0 otherwise attempts an opportunistic `sigstore-cli`
installation and signing operation. The child retains its scoped short-lived
`GEM_HOST_API_KEY` and uploads the exact certified gem bytes. The child is
noninteractive and has a bounded request deadline. Parent authorization
checks retain the real workflow context. Required original signatures, SBOMs,
provenance and the protected `attest-release-subjects` job are unchanged; this
does not create a replacement signing authority or bypass deployment review.

CPAN retrieval checks MetaCPAN's normalized metadata version separately from
the exact archive coordinate. The indexer normalizes a three-part version to
`v4.0.2`; its metadata omits a prerelease suffix. The approved owner, full
stable or prerelease archive URL and authenticated artifact checksum must still
match exactly. This normalization does not permit substituting a stable archive
for a requested prerelease.

Central publication and NuGet indexing are asynchronous. Dependent publishers
use a 30-minute readiness deadline for missing public companions. Kotlin checks
Java's JVM POM and JAR against Java's signed checksums. F# retains the existing
NuGet repository-signature and SBOM verification of the C# package. Only missing
package retrievals are polled; integrity failures, unavailable trust material
and responses other than HTTP 404 fail immediately. An exhausted deadline keeps
the dependent package unsubmitted. Existing HTTP request timeouts remain in
effect. Further publication attempts follow the incident and authorization
process.

Release work advances only through the machine-registered states:

```text
source candidate
→ deterministic verified
→ certified
→ publishable
→ published
→ verified
```

Full and no-reuse Release certification are required for a stable candidate.
They execute once in the authorized qualified local environment and are bound
to an immutable SHA-256 evidence root signed by the governed local certifier.
Normal cloud CI invokes the certification verifier from a separate trusted
checkout with isolated Python imports. It checks the trusted
signature, exact source and profile identities, every evidence hash, producer
aggregates, runtime declarations, samples, and waivers without repeating Full,
Release, real-engine execution, or performance sampling. Certification does not
make a release publishable. Publication may run only
after explicit owner authorization naming the exact version, source SHA,
artifact identities, destinations, and run. Registry uploads, Marketplace
publication, GitHub Releases, and production release tags are all publication.

The canonical structured product-certification entrypoint is:

```bash
python3 tooling/product_certification.py --run-profile --artifact target/certification/product-certification.json --report target/certification/product-certification.md
```

Its machine artifact aggregates the registered profile results and evidence;
it does not confer `publishable` state or authorize any public action.

The canonical local evidence workflow is:

```bash
export STRLING_RELEASE_SUPPLY_CHAIN_EVIDENCE=/absolute/path/to/full-bundle/release-supply-chain-evidence.json
./strling profile full --artifact target/certification/profile-full.json
python3 tooling/production_certification.py \
  --profile release --all --no-reuse --plain
python3 -I "$TRUSTED_VERIFIER_ROOT/tooling/local_certification_attestation.py" \
  --repository-root . --trust-root "$TRUSTED_VERIFIER_ROOT" \
  --trust-policy release-certification-trust.json attest \
  --full-artifact target/certification/profile-full.json \
  --release-artifact artifacts/production-certification/<source>/<run>/profile-release.json \
  --evidence release-supply-chain=/absolute/path/to/release-bundle \
  --private-key /secure/path/to/authorized-certifier \
  --certifier-id strling-local-release-certifier-2026-01 \
  --output-dir tests/certification/release-packaging/1.0/current
python3 -I "$TRUSTED_VERIFIER_ROOT/tooling/local_certification_attestation.py" \
  --repository-root . --trust-root "$TRUSTED_VERIFIER_ROOT" \
  --trust-policy release-certification-trust.json verify \
  --bundle tests/certification/release-packaging/1.0/current
```

The private key is never checked in. Adding or rotating a trusted public key is
an owner-reviewed governance change. Required evidence remains in the signed
checked-in bundle; large build trees and disposable execution scratch remain
outside Git. A failed verification is repaired by deliberately producing and
signing fresh same-source evidence, never by cloud fallback or accepting a bare
hash.

The compiler certificate remains at historical closure
`2d8d897504663211d3768517f0be9f0e28d0f11e`, with original verifier
`dd9d7702237ba9c56e1269418d5a9bd5b582b9f0`. The packaging certificate remains
at `33e50ac033314dad089717a0ee20c0c7c310dea7`, with original verifier
`642cc21f8f5d5ccabde1bb893076e02c624247a7`. The public-verification certificate
retains closure `d284446710c8164efc870d60071eeb5faf542a95` and original verifier
`080107ed6d7893d60eb011fb83af09ac937eeb89`.

Current workflows preserve those exact closed records through qualified
immutable reader `c653d82504bf28f4d18bc0f80c9426912a2fb3e7` and its frozen
`governance/closed-certifications.json`. The reader verifies original authority,
signatures, Git identities, evidence roots and complete file inventories. This
preservation does not renew a historical waiver or certify a new source.

New package and complete-product certificates use the same qualified reader
with live current-source policy and exact-waiver enforcement. Protected
publishers use that trust checkout separately from their approved publisher
implementation. Delivery additionally verifies the current candidate certificate
before enabled publication; historical preservation cannot satisfy that check.
All verification contexts read candidate source and evidence as data. They cannot
fall back to candidate tooling. Certification and a valid signature do not
authorize production credentials, package publication or a public coordinate.

## Maven artifact signing

Java, Kotlin and the shared JVM bridge use one dedicated organizational RSA
primary signing key, at least 3072 bits, with a nonempty passphrase and finite
validity. The initial identity uses RSA4096 and one-year validity. Detached
ASCII-armored signatures use SHA-256 and the exact owner-approved primary
fingerprint. Signing subkeys, expired or revoked keys, unavailable secrets and
different Java/Kotlin signer identities are rejected. Signing adds registry
transport signatures and checksums over certified bytes; it does not rebuild
packages or authorize publication.

`GPG_PRIVATE_KEY` and `GPG_PASSPHRASE` belong to the protected `release`
environment. The owner-selected `SONATYPE_USERNAME` and `SONATYPE_PASSWORD`
remain repository secrets, consumed only by protected Maven publication jobs.
Environment approval, exact source, artifact, workflow and run authorization
remain mandatory. The primary secret is available to these approved jobs;
this provides less isolation than an offline primary key. Passphrase protection,
purpose isolation, restricted custody, manual deployment review and independent
signature checks compensate for that distinction.

The owner must retain an encrypted recovery archive containing the protected key,
signing passphrase, public certificate and revocation certificate. Its separate
recovery passphrase must be recorded physically, apart from encrypted on-device and
off-device copies. Recovery imports only into a restricted isolated key store;
verify the full primary fingerprint and a synthetic detached signature before
restoring environment secrets. Renew before expiration through owner-reviewed
custody and public-certificate redistribution; revocation or rotation requires
fresh public fingerprint approval and secret replacement. Never reuse a revoked
identity. Public-key distribution is separately authorized; successful local
signing is not Central Portal acceptance or permission to upload.

## Immutable candidates and releases

Public release candidates use `MAJOR.MINOR.PATCH-rc.N`. Published prerelease
and stable coordinates are immutable and are never overwritten or reused. A
source, dependency, generated-output, artifact-content, or waiver change after
an RC forces a new RC and fresh required certification.

Stable promotion uses the terminal RC source commit. Stable artifacts are
rebuilt from the product policy, compared for approved coordinate-only
differences, and certified again; RC evidence is not treated as publication
authorization.

## Public verification

Publication success leaves a release in `published`, not `verified`. P20-T03's
contract independently fetches every public artifact, verifies exact metadata
and identity, installs into clean consumer environments, runs public API/CLI
smoke checks, confirms binding/core compatibility, resolves provenance and
SBOM associations, and tests the published installation documentation.

If verification fails, stop remaining publication when safe, preserve the
exact partial state, and fix forward under a new immutable version after fresh
certification and authorization. Never silently republish the same coordinate.

The sole currently accepted waiver is `WVR-SEC-VSCE-LICENSE-001`. It remains
explicitly scoped and does not grant publication authority.

## Exact artifact authorization

`tooling.release_supply_chain handoff` verifies the restored artifact against
its checksum, SPDX, provenance, and same-source signed Release evidence. Include
the supply-chain evidence file in the signed bundle with the role
`release-supply-chain`; a signature over unrelated profile results is insufficient.
The owner approval document follows `publicationAuthorization` in the existing
release-supply-chain schema. It binds the product coordinate, source SHA,
manifest/evidence fingerprints, signed evidence root, exact destination/owner,
support tier, subject checksum, workflow SHA, protected environment, run ID and
attempt, and release channel.

The canonical approval digest and reviewed workflow SHA must be configured by
the owner in the protected environment as `RELEASE_AUTHORIZATION_SHA256` and
`RELEASE_APPROVED_WORKFLOW_SHA`. Candidate output and dispatch inputs cannot
supply those trusted values. Approval does not replace registry ownership
verification. Every externally pending ownership row blocks publication.

Java and Kotlin use the same protected `release` environment secrets for
the Central namespace `io.github.strling-lang`. Configure the Central Portal
token pair as `SONATYPE_USERNAME` and `SONATYPE_PASSWORD`, and the approved
OpenPGP signing material as `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE`.
Each destination authorization must bind the approved signing fingerprint.

Exclude `release:cpp` from the current publication authorization. ConanCenter
deployment is deferred by the owner. Build, stage and verify the C++ package
on its governed platforms. Developers can install it from the STRling source
checkout using the [CMake build and install instructions](../bindings/cpp/README.md).
Record ConanCenter delivery as deferred in the release handoff. A future
ConanCenter contribution requires separate authorization, maintainer acceptance
and independent verification of the recipe and package revisions.

Pub.dev additionally requires a version-tag push for trusted publication; a
manual non-tag dispatch cannot publish Dart. This registry constraint does not
authorize creating or pushing any tag during package preparation. See the
[official automated publication contract](https://dart.dev/tools/pub/automated-publishing).

The governing certification contract is deterministic. Functional resource
safety remains mandatory; quantitative performance diagnostics do not gate
acceptance. Historical performance-inclusive evidence keeps its original meaning.

## Certified transport preparation

Build receipts are platform qualified: `{surface}-{scope}-{first|second}.json`.
The registered 17 distributions require 21 platform rows, two independent builds
per row, and the isolated Supported consumer results inside each receipt.
`prepare-upload` exports only the captured file graph for dry-run Actions transport.
Its upload must preserve hidden files such as Pub's selection controls.

After successful clean-source Release verification, export each primary package
with `python -m tooling.release_supply_chain prepare-certified-upload --artifact-id
release:python --source-root <certified-source> --evidence
<bundle>/release-supply-chain-evidence.json --output-dir <new-transport-directory>`.
The command reports its exact `certified-{surface}-{source-sha}` artifact name;
it creates local files only. A future owner-controlled immutable handoff must
retain these bytes and the signed bundle. This task does not upload them.

Owner approval additionally binds `artifact_run_id` and `certification_ref`.
Configure `RELEASE_CERTIFIED_RUN_ID`, `RELEASE_CERTIFICATION_REF`, and
`RELEASE_AUTHORIZED_DESTINATIONS` (an exact JSON array of artifact IDs) along with
the protected approval digest. The certification ref is the evidence-only closure
commit; it is distinct from the certified implementation source. Neither ref is
inferred from the other. The publisher checks out the closure as data and restores
the package only after verifying the signed evidence and approval.

PyPI upload receipts use the [version JSON API](https://docs.pypi.org/api/json/)
to compare the complete retained filename/SHA-256 set to the approved subjects.
CPAN collision checks use the documented
[author/release endpoint](https://github.com/metacpan/metacpan-api/blob/master/docs/API-docs.md).
LuaRocks collision checks address the exact owner manifest's versioned rockspec,
using its [documented manifest file routes](https://luarocks.org/docs).
Registry receipt checks do not establish public consumer installation success.

Credential-bearing jobs additionally require repository controls
`RELEASE_AUTHORIZED_RUN_ID` and `RELEASE_AUTHORIZED_RUN_ATTEMPT` to match the exact
run before the job can enter its protected environment. The signed owner document
independently binds those same values. An ordinary dispatch cannot select them.
For a future publication, first inspect a publication-disabled run, then explicitly
approve its source, immutable asset run, workflow, destinations, and next attempt.
Protected variables and environment approval remain owner responsibilities.

NuGet.org adds its repository signature after receiving the exact certified
package. Public verification checks every certified inner file hash and rejects
all extra files except `.signature.p7s`; it then requires the .NET signature
verifier to validate that seal against the live NuGet.org repository-signing
fingerprints. This separately governed registry check never changes the allowed
independent-build normalizations. See the official
[NuGet repository signatures contract](https://learn.microsoft.com/en-us/nuget/api/repository-signatures-resource)
and [signed-package reference](https://learn.microsoft.com/en-us/nuget/reference/signed-packages-reference).

Native release assembly uses `tooling/native_release_build.py` with Python 3.12
or newer and the governed Rust 1.75 toolchain. It copies canonical source bytes
into a disposable common Cargo workspace, changes only the two development
workspace tables, and retains the exact interop dependency lock. This avoids
Cargo 1.75 embedding the external kernel workspace path in package identities;
see its [package identity hashing](https://github.com/rust-lang/cargo/blob/rust-1.75.0/src/cargo/core/compiler/context/compilation_files.rs#L539-L545).
The canonical compiler source, crate versions, dependency versions and ABI stay
unchanged. MSVC uses deterministic compilation and path mapping; native linkage
omits unshipped PDB paths. These are build inputs, not verifier normalizations.

Rust assembly first lets pinned Cargo verify its produced crate. The assembler
then writes canonical tar/gzip headers using the source commit epoch, preserving
all payload bytes and executable modes. Cargo 1.75 uses different source-header
timestamps on Windows and Linux; this build step produces one portable registry
subject. Capture, independent builds and publication compare and retain its
exact final bytes. Rust's comparison policy remains byte-for-byte with no
allowed normalizations.

NuGet assembly assigns content-derived identifiers to the unsigned SDK package's
core-properties part and its OPC relationship. Every managed/native payload and
the properties document remain exact; signed input and ambiguous relationships
are rejected. Canonical ZIP headers are written before capture. Independent
verification continues to permit only the registered archive timestamps.

Each protected publisher retains an authenticated attempt receipt before its
first registry request. A failed multi-file upload remains
`upload-failed-or-indeterminate`; the receipt does not claim complete upload or
public installation. An owner must reconcile registry state before authorizing
a subsequent attempt. LuaRocks authorization also binds the existing uploader's
numeric `registry_user_id` returned by its authenticated status endpoint.

`TRUSTED_VERIFIER_ROOT` must be a separate immutable checkout of the qualified
verifier commit. Preserve the historical hardened-core bundle and trust context.
The Full-type supply-chain input is independently verified by both governed
profile invocations; the separate Release-type bundle carries the same
certified subjects and all build receipts for publication handoff. Retain that
whole directory under the `release-supply-chain` evidence role when signing.
A passing Full operation cannot authorize publication, and Release execution
remains fresh with operation reuse disabled.

## Independent public verification

`governance/public-distribution.json` defines the read-only
`strling-public-distribution-v1` contract. Product identity and support scope
remain owned by release policy and the release-supply-chain manifest. The
current denominator is 17 artifact routes with eight checks each, plus 15
Supported platform consumers with eight checks each: 256 obligations. Preview
packages receive artifact, metadata, source, SBOM, provenance, documentation,
coordinate and scope checks; they do not acquire Supported consumer claims.
The implementation derives these rows from the manifest rather than storing
the total as an acceptance constant.

The owner's 4.0.0 publication scope and authorized 4.0.2 fix forward defer
ConanCenter. All 17 build
routes and all 256 controlled implementation obligations remain mandatory.
Actual initial public execution covers 16 destinations and 13 Supported platform
consumers: 232 obligations. The request and aggregate must explicitly account
for the remaining 24 C++ ConanCenter obligations as deferred; they cannot be
reported as passed or publicly verified. Supported direct C++ source builds
remain available under their existing platform and runtime requirements.
Only the exact manifest eligibility `owner-deferred-conancenter-4.0.0` permits
this exclusion for those two explicitly approved versions. Other routes, later
release versions, missing public evidence,
and partial publication remain subject to the complete applicable checks.

The optional `export-certified-bytes` job in `certification-integrity.yml`
restores the original certified packages into the artifact names consumed by
the publisher. It runs only after all four integrity jobs pass, on a manually
dispatched exact closure/workflow identity, with protected `release-attestation`
approval. Reading an unpublished draft requires `contents: write` in this job;
its reviewed commands retrieve and export existing bytes. It does not compile
or publish packages. The exact permission and workflow identity require approval.
The qualified `tooling/certified_transport.py seal` command prepares a local
lossless capsule from the complete exports, original signed package bundle and
accepted full candidate closure. The importer independently verifies both
certificates and their exact nesting before accepting the entire file graph.

Private remote staging requires a separate owner-authorized action. No draft
release, tag, asset upload or staging grant is created by this importer.
If the owner authorizes private GitHub draft staging, protected nonsecret
configuration must record `RELEASE_EXPORT_SOURCE_SHA`,
`RELEASE_EXPORT_CLOSURE_SHA`, `RELEASE_EXPORT_WORKFLOW_SHA`,
`RELEASE_EXPORT_PACKAGE_ROOT_SHA256`, `RELEASE_EXPORT_CAPSULE_SHA256`,
`RELEASE_EXPORT_STAGING_RELEASE_ID` and `RELEASE_EXPORT_STAGING_ASSET_ID`.
`RELEASE_EXPORT_ENABLED` defaults to disabled. The staging draft must remain
unpublished and target the exact source; its named capsule asset must match
the approved full checksum and bounded size. A successful immutable export
run supplies `RELEASE_CERTIFIED_RUN_ID`. Neither a local sealing proof nor
a skipped export job establishes that hosted byte transport has completed.

The offline check is `python3 -m tooling.public_distribution --check`. Local,
Pull Request, Full and Release all include this contract. Offline fixtures and
certified staged packages can establish engineering `READY` only. They cannot
establish public `VERIFIED`, and a publication receipt is never a verification
authority. Historical packaging and H08 certificates retain their own trust
contexts. Verification infrastructure certification uses
`governance/public-verification-certification-trust.json` and a separate bundle.
Public package authentication continues to use
`governance/release-certification-trust.json` and its immutable packaging reader;
the implementation certificate does not replace a package release certificate.

The protected `public-verification.yml` workflow is manual, defaults to disabled,
and runs only from the repository's default branch. Its `public-verification`
environment must require owner review and contain these nonsecret approved
values:

-   `PUBLIC_VERIFICATION_ENABLED=true` for an authorized public verification run.
-   `PUBLIC_VERIFIER_SHA`, an independently qualified immutable verifier commit.
-   `PUBLIC_REQUEST_JSON` and `PUBLIC_REQUEST_SHA256`, the approved request and the
    SHA-256 of its canonical UTF-8 JSON representation (sorted keys, no insignificant
    whitespace). Dispatch callers cannot replace either value.
-   `PUBLIC_CERTIFIED_SOURCE_SHA`, `PUBLIC_CERTIFICATION_CLOSURE_SHA`, and
    `PUBLIC_CERTIFIED_RUN_ID`, identifying the exact signed release and retained
    `certified-*` and `signed-release-*` artifacts.

The request must satisfy
`governance/schemas/public-verification-request.schema.json`. It binds the exact
version/channel, source, signed root, complete manifest, every destination,
every public evidence/document association, publication receipt correlations,
and the exact derived obligation list. Registry ownership must already be
governed as verified. Existing externally-pending account placeholders cannot
authorize public success. The public lifecycle input must be `published`.

The workflow checks out candidate and closure source as data, executes only the
approved verifier, authenticates the original signature through the immutable
packaging verifier, and independently downloads public bytes. Certified exports
are comparison exemplars only. A failed download never selects an exemplar as
the consumer payload. Git routes bind tag, commit, tree and selected source
files; Conan binds recipe/package revisions and all transport files. NuGet
permits only its registered repository signature addition and verifies that
signature with the official signing identities. No additional archive
normalization is introduced.

Fresh consumer environments install only authenticated retrieved files. SDK
dependencies are separate: Rust uses the governed locks, JVM jars must match
reviewed verification metadata, Kotlin prepares a fresh compiler-only cache,
and Dart restores its exact locked runtime prerequisites with lock enforcement.
No developer initialization script or inherited native-library search path is
accepted. Caller-supplied native modes use the authenticated host library from
the independently retrieved Python wheel, with its source and file identity
retained. The shared canonical consumer contracts exercise compilation and
incompatible-kernel rejection; they do not implement language semantics.

Both disposable hosted platform jobs must report the same protected request and
execution identity. Reconciliation rejects missing/duplicate scopes, changed
denominators, synthetic receipts, other workflow runs and unbound consumer
results. Only complete public success can return `release_transition=verified`.
The result follows `governance/schemas/public-verification-result.schema.json`.
This is evidence for the lifecycle transition, not a registry or repository
mutation. The workflow has only content/action read permissions, no production
publication secrets, and no publication operation.

An exact-coordinate HTTP 404 is `NOT_PUBLISHED`; timeouts, throttling and
unavailable registries are `INDETERMINATE`; incorrect identities, payloads or
behavior are `FAILED`. Every attempt retains its observed response identity
and raw bytes. Retries and redirects are bounded. Missing artifacts mixed with
successful public observations produce an explicit partial-publication result.
Preserve those observations and require separate owner authorization for any
repair, replacement version, withdrawal or renewed publication. Never relabel
an earlier attempt or repair a registry from the verifier.

### Separate publication-control tags

An already published official version tag remains immutable at the certified
implementation. A corrected, independently qualified publisher may instead run
from a separately approved `publication-vVERSION` control tag. That control tag
identifies delivery code, not a new product source or artifact build.

This route requires the exact `publication_ref` in the protected canonical owner
authorization, the real tag-push workflow/run/attempt, and
`RELEASE_PRODUCT_SOURCE_SHA` selecting the original clean certified source.
`RELEASE_CERTIFICATION_REF` still selects its accepted evidence closure.
The publisher verifies the original package certificate against the implementation,
retains the separate closure binding, and requires `vVERSION` to resolve to that
same certified implementation before any upload. Original signatures, artifact
checksums, support scopes and immutable verifier pins remain enforced.

Pub.dev's configured tag pattern must match the explicitly approved control tag
(for example `publication-v{{version}}`) while retaining the `release` environment.
Changing that persistent association and creating the control tag require their
own applicable owner approvals. This route never authorizes moving an existing
version tag, rebuilding certified packages, changing package ownership, or using
a different publication run. Missing source pins or an unapproved tag fail closed.
