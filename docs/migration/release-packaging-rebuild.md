# Fourth Edition release packaging rebuild

## Checkpoint 1 — scope and contract lock

Started 2026-11-06 on branch `dev`, commit
`2d8d897504663211d3768517f0be9f0e28d0f11e`. Both working tree and index
were clean. This is the independently closed H08 baseline. Its signed evidence,
source identities, trust roots, verifier pins, and historical records are
preserved. This work does not recertify or reinterpret that historical source.

Authority: `governance/release-policy.json`, versioned interop contracts,
`governance/deterministic-certification.md`, `toolchain.json`, and the existing
17-artifact `tests/certification/release-supply-chain/1.0/manifest.json`.
The ratified product identity is 4.0.0; the starting projection is 3.0.0.

The version inventory is `release-policy.json#/version_surfaces`: root private
tooling; public Rust crate; Python; npm; PHP manifest/runtime; Ruby runtime and
gemspec sentinel; Dart; C#/F#; Java/JVM/Kotlin and Java runtime; R; Perl module
and distribution; C CMake/header; C++ CMake; Lua template; Go/Swift tag mapping;
independent interop/fuzz crates and VS Code extension. Dependency references,
lockfile self-identities, and extension product compatibility also need checking.
Protocol, ABI, schemas, profiles, specification, interop crate, fuzz harness,
and editor version remain independent.

| Artifact   | Destination / coordinate                   | Tier      | Certified scope                                     |
| ---------- | ------------------------------------------ | --------- | --------------------------------------------------- |
| C          | organization Git / strling-c               | Supported | Windows/Linux x86_64                                |
| C++        | Conan / strling                            | Supported | Windows/Linux x86_64                                |
| C#         | NuGet / STRling                            | Supported | Windows x86_64                                      |
| Dart       | pub.dev / strling                          | Supported | Linux x86_64                                        |
| F#         | NuGet / STRling.FSharp                     | Supported | Windows x86_64                                      |
| Go         | organization Git module                    | Supported | Linux x86_64, cgo                                   |
| Java       | Maven Central / com.strling:strling        | Supported | Windows x86_64, explicit native path                |
| Kotlin     | Maven Central / com.strling:strling-kotlin | Supported | Windows x86_64, explicit native path                |
| Lua        | LuaRocks / strling                         | Preview   | Linux x86_64 observation                            |
| Perl       | CPAN / STRling                             | Preview   | Linux x86_64 observation                            |
| PHP        | organization Git / strling/strling         | Preview   | Linux x86_64, caller-owned native discovery         |
| Python     | PyPI / STRling, strling-lang organization  | Supported | Windows/Linux x86_64, CPython 3.12                  |
| R          | organization Git / strling                 | Preview   | Linux x86_64 observation                            |
| Ruby       | RubyGems / strling                         | Preview   | Linux x86_64 observation                            |
| Rust       | crates.io / strling                        | Supported | Windows/Linux x86_64                                |
| Swift      | organization Git / STRling                 | Supported | Linux x86_64                                        |
| TypeScript | npm / @strling-lang/strling                | Preview   | Windows Node 24 observation and Chrome WASM harness |

Existing mechanisms: repository-native version/projection generators, package
helpers, two-build receipts, SPDX/in-toto producer/verifier, protected `release`
environment, immutable GitHub Actions, and isolated signed-certification verifier.
Dart/Python/Ruby/Rust/npm policy requires OIDC; other registries retain protected
credential or organization-Git routes. External ownership and trusted-publisher
configuration are not verified by checked-in declarations.

Discrepancies recorded before implementation:

-   The version generator omits Python, C CMake/header, Perl distribution metadata,
    dependent JVM coordinates, and several lock/self identities. Kotlin's current
    expression is not matched by its updater. Missing substitutions can succeed.
-   CD still treats Python as version authority, uses obsolete manifest paths,
    builds again in publication jobs, exposes an npm token despite OIDC policy,
    and equates a non-dry-run dispatch with publication authorization.
-   The workflow qualifier still expects cloud Release execution despite the
    isolated trusted-verification model. Existing source-tag and registry-assembled
    surfaces require careful distinction from installable native payloads.
-   Release-policy prose retains performance/resource hardgate language superseded
    by deterministic certification. Quantitative diagnostics must remain excluded.
-   TypeScript Node evidence mismatch and dynamic-language Preview limitations
    remain explicit. No support promotion is authorized by package assembly alone.
-   Python source distributions have a recorded package-pipeline repair obligation.

Allowed: coordinated version activation, distribution metadata and packaging,
registered generators, release contracts/schema/tests, offline consumer machinery,
safe CD reconstruction, and related documentation/evidence. Prohibited: semantic
implementation duplication, support expansion, historical H08 mutation, new
waivers, production secrets, registry mutations, releases, production tags, push,
merge, reset, clean, or history rewriting.

Acceptance requires focused adversarial and generator tests, all affected
component checks, independent clean builds, exact-artifact verification, complete
dependency/security/license evidence, applicable profiles including fresh Full
and no-reuse Release on frozen committed source, and a separate documentation
finalization commit. Dry-run evidence is never public-install evidence or owner
publication authorization. No success will be inferred from unavailable checks.

Rollback boundaries: retain baseline commit and historical evidence; changes are
reviewable exact-path commits. Failed builds stay diagnostic; never replace
certified subjects or broaden normalizations to force agreement. No remote or
registry rollback is needed because this task cannot publish.

## Checkpoint 2 — contracts and verification design

Passed. The active projection now comes solely from product.version.
Release manifest and build receipts use schema 2.0.0; distribution contracts bind
all 17 identities to their existing support tiers and exact platform scope.
Publication authorization binds protected run identity, source, version, signed
Release root, manifest, destination/owner, channel and exact subject checksum.
All external registry ownership remains pending verification.

Native product markers and sealed WASM metadata add package identity checks
without changing the native exports, ABI 1, protocol 1.0.0 or compiler semantics.
WASM factories bind the checked module to the instantiated client; direct
WasmClient construction is intentionally retired for Fourth Edition.

Archive inspection rejects unsafe paths, aliases, links, oversized content,
wrong coordinates, absent payloads and missing license material. Live SPDX
production and independent verification compare the full inner file graph.
The historical H08 bundle and trust policy remain unchanged; packaging has a
separate trust context using the existing authorized certifier keys.

## Checkpoint 3 — implementation and targeted proof

Passed at the current-source closure below. Historical engineering proof includes:

-   Focused version/policy/supply-chain/security/notice tests: 107 of 108 passed,
    followed by correction of the synthetic receipt fixture's payload boundary.
-   Bounded payload/WASM tests: 23 passed; Python preload tests: 16 passed.
-   Node 22: five suites and 20 tests passed after factory binding changes.
-   CPython 3.12 with the existing hash-locked setuptools/wheel/build tools:
    Linux source distribution and wheel built; 134 content files inspected.
-   Governed Go/Dart/Swift runtime campaign: passed, five adversarial probes,
    four operations and three repeats per binding.
-   Dart publication dry run from an exact isolated relocation: zero warnings;
    nine assembly/control files inspected. Pub excludes hidden control files
    according to its [published file-selection rules](https://dart.dev/tools/pub/publishing).
-   Windows C#/F#: two package consumers passed, one native payload, exact
    win-x64 package scope and complete existing 16-external-package graph.
-   Default attestation and publication authorization tests: 83 passed. The
    existing H08 trust policy and signed bundle have no diff.

These checks use development outputs. They do not establish two independent
clean builds, Full/Release certification, external ownership or public registry
installation. Failed development attempts are retained under ignored target
logs; stale package outputs, parent Git-ignore behavior and cross-platform
NuGet asset paths were diagnosed explicitly.

All 15 Supported platform rows have passed isolated engineering consumers:
C/C++/Python/Rust on Windows and Linux; C#/F#/Java/Kotlin on Windows;
Go/Dart/Swift on Linux. These are local staged installations, with no claim of
public registry installation. The platform contract now requires 42 retained
build records over 21 build rows (including six Preview rows), and 95 distinct
platform-qualified toolchain records. Each Supported record includes its own
canonical compilation and compatibility-refusal consumer proof. Reusing an
invocation UUID or workspace identity between rebuilds fails closed.

The integrated release/native/payload/Maven/Conan/authorization suite passes
151 tests. The Windows linker engineering pair initially differed because its
private PDB path was embedded despite `/Brepro`. Disabling the unshipped debug
record at link time produces identical fresh DLLs, SHA-256
`c429c81f5a56f3153a60a9104bc61abacdc3e7fdd19a1905f3bd15c3b1540705`.
No binary rewriting or additional reproducibility normalization is used.
Packaged PE/ELF inspection verifies the exact three exports, permitted system
dependencies, and absence of embedded library search paths without loading code.

The CD build matrix uploads only the receipt-authenticated file graph. Production
publication does not rebuild: it retrieves separate `certified-*` assets from
the owner-approved retained run and verifies them against the signed local root.
The certified implementation SHA and evidence-closure SHA remain separate.
Kotlin and F# consume staged primary companions, and their publishers verify the
public companion bytes before releasing dependents. PyPI's immutable trusted
action has a separate exact-file receipt check; this is not an installation claim.

At this historical checkpoint, remaining work included publication-route closure checks, canonical generated
refresh, source freeze, independent reproducibility and fresh certification.
The existing approved certifier's local signing-key location has been requested;
no new certifier, key, or trust authority is introduced.
The initial Go major-module concern is resolved without a policy revision.
An isolated local repository test consumed `@go-v4.0.0` through Go's explicit
version query, obtained a canonical pseudo-version and verified its Origin.Hash
against the exact fixture commit. This preserves both the governed module path
and source-tag mapping; the pseudo-version is a transport identity, while the
product tag remains 4.0.0. The earlier owner question is withdrawn. See the
[Go module version-query contract](https://go.dev/ref/mod#version-queries).
The fixture result is local qualification, not a public registry installation.

### Additional engineering proof — isolated package consumers

The new `tooling.release_consumers` harness stages the exact inspected subjects
outside the checkout. It installs platform wheels and NuGet packages, restores
Conan packages into empty caches, builds and installs the C source delivery,
and consumes Go, Dart, Swift and Rust packages from their staged distribution
inputs. Consumers exercise registered successful source and target requests,
assert the literal `a` and emitted pattern `abc`, and reject mismatched native
products. Rust binds its kernel to the same crate, asserts the linked product
version, and rejects the wrong exact target profile.

Observed passes include Python on both Windows/Linux CPython 3.12; C on both
Windows/Linux; C++ on Windows/Linux; Linux Go, Dart and Swift; Windows C#/F#;
Windows Java/Kotlin; and Rust on Windows/Linux. This covers all eleven Supported
distributions and fifteen registered Supported platform rows. Earlier development outputs are not promoted to committed
source or reproducibility evidence. Each retained engineering receipt explicitly
sets `engineering: true`, `source: null` and `publication_authorized: false`.

The isolated C build exposed three omitted canonical conformance-data inputs.
All source/tag handoff contracts now bind those exact files. Rust archive
verification exposed two omitted facade modules; the manifest now includes
them. Cargo verifies its crate in disposable scratch space before its original
archive bytes are retained. No archive normalization was added to hide these
failures. C installation also retains the project license and canonical native
third-party notices.

Windows Maven and Kotlin package builds use actual Windows Java/Maven/Gradle.
Kotlin now declares Java 11 bytecode consistently with its shared Java bridge.
The wrapper is pinned to Gradle's official 8.5 distribution SHA-256. Public JVM
runtime JARs used by consumers are checked against the reviewed Gradle checksum
inventory before staging. A disposable SDK preparation project retrieves only
compiler prerequisites with strict checksum verification; consumers remain
offline. Ambient product packages copied with SDK caches were quarantined
before the Windows Maven build.

The workspace-local Windows CPython 3.12.10 SDK was authenticated against its
NuGet catalog SHA-512 and the Python Software Foundation's valid Authenticode
signature. This follows the [official Python CI distribution instructions](https://docs.python.org/3.12/using/windows.html#the-nuget-org-packages).
The build uses the repository's hash-locked build requirements. Neither a
Linux cross-build nor a Python 3.13 host substitutes for the Windows 3.12 row.

SPDX documents now validate against the pinned, offline [official SPDX 2.3 JSON
schema](https://github.com/spdx/spdx-spec/blob/v2.3/schemas/spdx-schema.json).
The schema's upstream license is CC-BY-3.0 and its attribution and original
SHA-256 are retained beside it; the generated SBOM data license remains CC0-1.0.
Live content graphs carry actual SHA-256 and compatibility SHA-1 digests, with
an independently checked SPDX package verification code. File license
conclusions remain `NOASSERTION` instead of attributing embedded third-party
files to the project's Apache license. The native dependency SBOM excludes
unreachable fuzz-workspace components and requires the complete reachable lock
graph. These improvements do not replace the required security/license checks.

The canonical repository unit command now runs pytest, which also discovers
existing unittest cases. Its prior unittest-only discovery omitted eight
pytest-style modules, including the new packaging security regressions. A
collection-only check discovers 2,034 tests. Focused toolchain/quality/Maven
checks passed 118 tests and 23 subtests; release evidence/payload checks passed
53 tests. Node 22/WASM passes five suites and all 21 tests, including the private
constructor-token bypass refusal. Full integration is still pending.

### Platform evidence integration — in progress

The manifest retains seventeen distribution identities and now declares twenty-one
build rows. Public support platforms are explicit projections of the existing
ratified claims; no tier or platform has been promoted. TypeScript's Linux
assembly row is internal Preview build context, not a Supported runtime claim.
The schema and producer now distinguish ninety-five platform/toolchain records.
Forty-two build receipts are required, two per build row, with independent
workspace and invocation identities. Supported receipts embed isolated consumer
proofs and exact companion identities. Integration into workflow transport,
aggregate evidence, adversarial fixtures and profile gates remains in progress;
these draft changes have not yet passed the complete targeted suite.

Actual Windows native outputs contained wall-clock PE timestamps. The build
now requests deterministic MSVC linking and object/archive creation, and Python
sdist native assembly remaps its actual embedded source root. These are build
input corrections; the permitted normalization rules have not been broadened.
The resulting independent binary comparison is still required.

Workflow transport is being changed to stage only each receipt's complete file
graph, including required hidden control files. Extra build directories must not
become source-package uploads. Cross-platform restoration rejects conflicting
bytes at a shared subject path. Full/Release package checks now require live
exact-source evidence; a synthetic contract-only pass cannot satisfy them.

Remaining publication integration must consume the exact locally certified
artifact bytes rather than treat a new cloud rebuild as the signed local
artifact. Future owner approval must bind the certified artifact handoff as
well as its source, evidence and run. The closure commit carrying signed evidence
must remain distinct from the certified implementation source. Historical H08
verification remains on its original source and verifier pins.

## Checkpoint 4 — integration and certification

Passed on the independently certified packaging source recorded below. Existing H08 evidence remains historical and does not certify changed source.

## Checkpoint 5 — finalization and readiness

Passed at the signed and hosted current-source closure below. Publication remains disabled.

## Generated-artifact impact map

Matched from the actual changed paths. Each entry distinguishes authoritative
source matches from generator-input matches; output ownership remains with the
registered family. Package-manager locks remain a governed reviewed refresh,
not a claim of canonical lock reproduction.

### public-contract-snapshots

Authority: compatibility-baseline; enforcement: enforced.

Authoritative matches: `Cargo.toml`, `bindings/c/include/strling.h`, `bindings/cpp/include/strling/native.hpp`, `bindings/csharp/src/STRling/Native/NativeClient.cs`, `bindings/csharp/src/STRling/STRling.csproj`, `bindings/dart/lib/src/native_client.dart`, `bindings/dart/pubspec.yaml`, `bindings/fsharp/src/STRling.FSharp/STRling.FSharp.fsproj`, `bindings/go/native_cgo.go`, `bindings/java/pom.xml`, `bindings/java/src/main/java/com/strling/Strling.java`, `bindings/jvm/pom.xml`, `bindings/jvm/src/main/java/com/strling/jvm/NativeClient.java`, `bindings/kotlin/build.gradle.kts`, `bindings/kotlin/src/main/kotlin/strling/STRling.kt`, `bindings/php/composer.json`, `bindings/python/src/STRling/_product_version.py`, `bindings/python/src/STRling/interop.py`, `bindings/typescript/package.json`, `bindings/typescript/src/STRling/interop.ts`, `bindings/typescript/src/STRling/product_version.ts`.

Generator-input matches: `Cargo.toml`, `bindings/c/include/strling.h`, `bindings/cpp/include/strling/native.hpp`, `bindings/csharp/src/STRling/Native/NativeClient.cs`, `bindings/csharp/src/STRling/STRling.csproj`, `bindings/dart/lib/src/native_client.dart`, `bindings/dart/pubspec.yaml`, `bindings/fsharp/src/STRling.FSharp/STRling.FSharp.fsproj`, `bindings/go/native_cgo.go`, `bindings/java/pom.xml`, `bindings/java/src/main/java/com/strling/Strling.java`, `bindings/jvm/pom.xml`, `bindings/jvm/src/main/java/com/strling/jvm/NativeClient.java`, `bindings/kotlin/build.gradle.kts`, `bindings/kotlin/src/main/kotlin/strling/STRling.kt`, `bindings/php/composer.json`, `bindings/python/src/STRling/_product_version.py`, `bindings/python/src/STRling/interop.py`, `bindings/typescript/package.json`, `bindings/typescript/src/STRling/interop.ts`, `bindings/typescript/src/STRling/product_version.ts`.

Outputs: `governance/contracts/snapshots/c-public-api.json`, `governance/contracts/snapshots/cpp-public-api.json`, `governance/contracts/snapshots/csharp-public-api.json`, `governance/contracts/snapshots/fsharp-public-api.json`, `governance/contracts/snapshots/dart-public-api.json`, `governance/contracts/snapshots/strling-interop.json`, `governance/contracts/snapshots/go-public-api.json`, `governance/contracts/snapshots/java-public-api.json`, `governance/contracts/snapshots/jvm-public-api.json`, `governance/contracts/snapshots/kotlin-public-api.json`, `governance/contracts/snapshots/lua-public-api.json`, `governance/contracts/snapshots/perl-public-api.json`, `governance/contracts/snapshots/php-public-api.json`, `governance/contracts/snapshots/python-public-api.json`, `governance/contracts/snapshots/strling-kernel.json`, `governance/contracts/snapshots/r-public-api.json`, `governance/contracts/snapshots/ruby-public-api.json`, `governance/contracts/snapshots/rust-public-api.json`, `governance/contracts/snapshots/root-cli.json`, `governance/contracts/snapshots/schema-cli.json`, `governance/contracts/snapshots/schema-conformance-fixture.json`, `governance/contracts/snapshots/schema-pcre2-target.json`, `governance/contracts/snapshots/schema-target-artifact.json`, `governance/contracts/snapshots/swift-public-api.json`, `governance/contracts/snapshots/typescript-package-entrypoints.json`, `governance/contracts/snapshots/typescript-public-api.json`.

Generator: `./strling contracts`.

Verification: `./strling contracts --check`.

### dynamic-language-adapter-release-graphs

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `bindings/php/composer.json`, `bindings/r/DESCRIPTION`.

Generator-input matches: `bindings/php/composer.json`, `bindings/r/DESCRIPTION`.

Outputs: `tests/adapters/dynamic-languages-3.0/release-graphs.json`.

Generator: `python3 tooling/dynamic_language_adapter_package.py --write-graph`.

Verification: `python3 tooling/dynamic_language_adapter_package.py --check`.

### jvm-adapter-release-graph

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `bindings/java/pom.xml`, `bindings/jvm/pom.xml`, `bindings/kotlin/build.gradle.kts`.

Generator-input matches: `bindings/java/pom.xml`, `bindings/jvm/pom.xml`, `bindings/kotlin/build.gradle.kts`, `tooling/jvm_adapter_package.py`.

Outputs: `tests/adapters/3.0/release-graph.json`.

Generator: `python3 tooling/jvm_adapter_package.py --write-graph`.

Verification: `python3 tooling/jvm_adapter_package.py --check`.

### dotnet-adapter-release-graph

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `bindings/csharp/src/STRling/STRling.csproj`, `bindings/fsharp/src/STRling.FSharp/STRling.FSharp.fsproj`.

Generator-input matches: `bindings/csharp/src/STRling/STRling.csproj`, `bindings/fsharp/src/STRling.FSharp/STRling.FSharp.fsproj`, `tooling/dotnet_adapter_package.py`.

Outputs: `tests/adapters/dotnet-3.0/release-graph.json`.

Generator: `python3 tooling/dotnet_adapter_package.py --write-graph`.

Verification: `python3 tooling/dotnet_adapter_package.py --check`.

### version-synchronized-metadata

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `governance/release-policy.json`.

Generator-input matches: `governance/release-policy.json`, `tooling/sync_versions.py`.

Outputs: `Cargo.lock`, `Cargo.toml`, `bindings/c/CMakeLists.txt`, `bindings/c/include/strling.h`, `bindings/cpp/CMakeLists.txt`, `bindings/cpp/include/strling/native.hpp`, `bindings/csharp/src/STRling.Cli/STRling.Cli.csproj`, `bindings/csharp/src/STRling/STRling.csproj`, `bindings/dart/lib/src/native_client.dart`, `bindings/dart/pubspec.yaml`, `bindings/fsharp/src/STRling.FSharp/STRling.FSharp.fsproj`, `bindings/go/native_cgo.go`, `bindings/interop/src/product_version.rs`, `bindings/java/pom.xml`, `bindings/java/src/main/java/com/strling/Strling.java`, `bindings/jvm/pom.xml`, `bindings/jvm/src/main/java/com/strling/jvm/NativeClient.java`, `bindings/kotlin/build.gradle.kts`, `bindings/kotlin/gradle.lockfile`, `bindings/kotlin/src/main/kotlin/strling/STRling.kt`, `bindings/perl/dist.ini`, `bindings/perl/lib/STRling.pm`, `bindings/php/composer.json`, `bindings/php/src/STRling.php`, `bindings/python/pyproject.toml`, `bindings/python/src/STRling/_product_version.py`, `bindings/r/DESCRIPTION`, `bindings/ruby/lib/strling.rb`, `bindings/swift/Sources/STRling/Version.swift`, `bindings/typescript/package-lock.json`, `bindings/typescript/package.json`, `bindings/typescript/src/STRling/product_version.ts`.

Generator: `python3 tooling/sync_versions.py --write`.

Verification: `python3 tooling/sync_versions.py --check`.

### package-manager-lockfiles

Authority: operational-projection; enforcement: verification-only.

Authoritative matches: `Cargo.toml`, `bindings/dart/pubspec.yaml`, `bindings/kotlin/build.gradle.kts`, `bindings/perl/dist.ini`, `bindings/php/composer.json`, `bindings/python/pyproject.toml`, `bindings/r/DESCRIPTION`, `bindings/typescript/package.json`, `tooling/lsp-server/package.json`.

Generator-input matches: `Cargo.toml`, `bindings/dart/pubspec.yaml`, `bindings/kotlin/build.gradle.kts`, `bindings/perl/dist.ini`, `bindings/php/composer.json`, `bindings/python/pyproject.toml`, `bindings/r/DESCRIPTION`, `bindings/typescript/package.json`, `tooling/lsp-server/package.json`.

Outputs: `package-lock.json`, `bindings/dart/pubspec.lock`, `bindings/kotlin/gradle.lockfile`, `bindings/kotlin/gradle/verification-metadata.xml`, `bindings/lua/luarocks.lock`, `bindings/perl/cpanfile.snapshot`, `bindings/php/composer.lock`, `bindings/python/requirements.lock.txt`, `bindings/r/renv.lock`, `bindings/ruby/Gemfile.lock`, `bindings/interop/Cargo.lock`, `Cargo.lock`, `core/internal/Cargo.lock`, `tests/certification/performance-resource/1.0/runner/Cargo.lock`, `bindings/typescript/package-lock.json`, `tooling/lsp-server/package-lock.json`.

Generator: `none; governed reviewed refresh only`.

Verification: `python3 -m tooling.dependency_lock_verification --check --json`.

### lua-release-rockspec

Authority: operational-projection; enforcement: profile-enforced.

Authoritative matches: `governance/release-policy.json`.

Generator-input matches: `governance/release-policy.json`.

Outputs: `bindings/lua/strling-[0-9]*.rockspec`.

Generator: `python3 tooling/lua_rockspec.py materialize --version-from-source --output-dir bindings/lua`.

Verification: `python3 tooling/lua_rockspec.py check-template --version-from-source --json`.

### lsp-extension-payload

Authority: non-normative-projection; enforcement: profile-enforced.

Authoritative matches: `tooling/lsp-server/package.json`.

Generator-input matches: `tooling/lsp-server/package.json`.

Outputs: `tooling/lsp-server/dist/**`.

Generator: `python3 tooling/lsp-server/package_extension.py assemble --target auto`.

Verification: `python3 tooling/lsp-server/package_extension.py certify --target auto`.

### binding-support-certification-evidence

Authority: certification-evidence; enforcement: enforced.

Authoritative matches: `toolchain.json`.

Generator-input matches: .

Outputs: `tests/adapters/binding-support-4.0/evidence.json`.

Generator: `python3 tooling/binding_support_certification.py --write-evidence`.

Verification: `python3 tooling/binding_support_certification.py --check`.

### profile-source-definitions

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `toolchain.json`.

Generator-input matches: `toolchain.json`, `tooling/local_certification_attestation.py`.

Outputs: `tests/certification/profile-source/1.0/definitions.json`.

Generator: `python3 -m tooling.profile_source_identity --write-definitions`.

Verification: `python3 -m tooling.profile_source_identity --check-definitions`.

### target-adapter-certification-matrices

Authority: certification-evidence; enforcement: enforced.

Authoritative matches: `toolchain.json`.

Generator-input matches: `toolchain.json`.

Outputs: `tests/certification/target-adapter/1.0/evidence.json`, `tests/certification/target-adapter/1.0/evidence.md`.

Generator: `python3 -m tooling.target_adapter_certification_matrix --source-evidence tests/certification/target-adapter/1.0/source-profile-evidence.json --write`.

Verification: `python3 -m tooling.target_adapter_certification_matrix --check --json`.

### semantic-authority-retirement-evidence

Authority: certification-evidence; enforcement: enforced.

Authoritative matches: `governance/generated-artifacts.json`, `toolchain.json`.

Generator-input matches: `governance/generated-artifacts.json`, `toolchain.json`.

Outputs: `tests/architecture/semantic-authority/1.0/evidence.json`.

Generator: `python3 -m tooling.semantic_authority --write`.

Verification: `python3 -m tooling.semantic_authority --check --json`.

### legacy-removal-inventory-evidence

Authority: certification-evidence; enforcement: enforced.

Authoritative matches: `governance/generated-artifacts.json`.

Generator-input matches: `governance/generated-artifacts.json`.

Outputs: `tests/architecture/legacy-removal/1.0/evidence.json`, `tests/architecture/legacy-removal/1.0/evidence.md`.

Generator: `python3 -m tooling.legacy_removal_inventory --write`.

Verification: `python3 -m tooling.legacy_removal_inventory --check --json`.

### release-policy-documentation

Authority: non-normative-projection; enforcement: enforced.

Authoritative matches: `governance/release-policy.json`.

Generator-input matches: `governance/release-policy.json`, `tests/certification/release-supply-chain/1.0/manifest.json`, `tooling/release_policy.py`.

Outputs: `docs/release-policy.md`.

Generator: `python3 tooling/release_policy.py --write`.

Verification: `python3 tooling/release_policy.py --check`.

### release-supply-chain-contract-fixture

Authority: operational-projection; enforcement: enforced.

Authoritative matches: `tests/certification/release-supply-chain/1.0/manifest.json`.

Generator-input matches: `governance/schemas/release-supply-chain-certification.schema.json`, `tests/certification/release-supply-chain/1.0/manifest.json`, `tooling/release_supply_chain.py`.

Outputs: `tests/certification/release-supply-chain/1.0/fixtures/valid-evidence.json`.

Generator: `python3 -m tooling.release_supply_chain write-contract-fixture`.

Verification: `python3 -m tooling.release_supply_chain check --json`.

### release-certification-trust

Authority: operational-projection; enforcement: enforced.

Authoritative matches: .

Generator-input matches: `tooling/release_supply_chain.py`.

Outputs: `governance/release-certification-trust.json`.

Generator: `python3 -m tooling.release_supply_chain write-release-trust`.

Verification: `python3 -m tooling.release_supply_chain check-release-trust`.

### native-kernel-third-party-notices

Authority: operational-projection; enforcement: enforced.

Authoritative matches: .

Generator-input matches: `tooling/release_notices.py`.

Outputs: `bindings/interop/THIRD_PARTY_NOTICES.txt`.

Generator: `python3 tooling/release_notices.py --output bindings/interop/THIRD_PARTY_NOTICES.txt`.

Verification: `python3 tooling/release_notices.py --output bindings/interop/THIRD_PARTY_NOTICES.txt --check`.

The R distribution coordinate is reconciled to the existing `Package: strling`
and `library(strling)` installation contract. The display brand remains STRling;
no CRAN namespace or new registry route is introduced. Preview build commands
retain their explicit `--preview` classification in both the manifest and matrix.

Cross-platform JVM engineering comparison found only ZIP permission-bit drift
between Windows and the Linux filesystem. Canonical binary JAR assembly now
retains each original inner byte while setting data-file modes to `0644` and
placing the manifest first. Both observed JVM archives then have SHA-256
`1b9861ed7249b7fd572d317d8347f9a950f3658d6c5e3dc1cc59bc1c31cc942a`.
This is an assembly correction, with no expansion of verifier normalizations.
The JVM dependency-cache warmup uses disposable tracked source copies without
credentials; release assembly still cleans and independently rebuilds both roots.

Full and Release definition versions advance from 1.30.0 to 1.31.0 for the
release-blocking live packaging gate. A synthetic contract result cannot satisfy
that gate. Local and Pull Request retain their profile identities and offline
contract checks. Release remains a separate fresh invocation without operation
reuse. The existing versioned specification, compiler protocols, ABI, kernel,
interop crate, and VS Code Preview identity are unchanged.

Independent engineering native builds in separate temporary workspaces now
match exactly on both platforms: Linux shared library
`6a23904fe0cb83f86cee090f68858c93eee710c5986fea2463925115acbbd06e`
and static library
`fddb9d3bbb67f1ff104049addd25ae6536a068658bd39425ad5335c853be037f`;
Windows DLL
`5542b10913723bacc28b0977f95fbdc13f8ee28415007973748a423f17b660f3`
and static library
`a1495b749097c20758cb8048e0b29b37f8a5419e6d6a2f04603286881ad4cf98`.
The original and intermediate Conan attempts remain failed engineering
observations: absolute external-workspace package identities and MSVC object
paths prevented reproducibility. The final assembly helper places unchanged
kernel and interop inputs under one disposable Cargo root. Tests preserve all
nonworkspace manifest fields, source bytes and the governed dependency lock.
No compiler source is changed and no verifier normalization is broadened.

The focused release suite passed 91 tests with two Windows unavailable-tool
skips; later dependency, partial-upload, workflow-output and native-workspace
regressions passed 57 tests with one unavailable-tool skip. The prior broad
tooling run recorded 1,992 passed, 32 failed and 25 skipped while implementation
was still changing; it is not a passing frozen-source certification result.
Fresh qualification remains mandatory. The approved local signing key is absent
from both expected Windows and WSL paths; its location has been requested.
The V0–V12 master-plan source was not found beside the repository or in its
governance, certification and migration documents; its location was requested
rather than inventing that acceptance mapping.

The retained H08 authority-recovery snapshot identifies the original campaign's
[Notion phase](https://app.notion.com/p/3b97d940647581d7908ce8d2c952ccbe?pvs=204)
and [package task](https://app.notion.com/p/3b97d940647581139950d85c9b1dc4a1?pvs=204).
It records the historical V0–V12 wording and mandatory V10/V12 clean-room
release obligations, with Full/Release and all retained package checks explicit
for this task. The current connector returns object-not-found for those pages;
the retained retrieval is historical context, not a new source of authority.
Current executable obligations remain the deterministic policy and toolchain
profiles required by this assignment. No missing V-label definition is invented.

The existing approved local certifier was located through its retained H08
signing instructions. Its public key fingerprint matches the unchanged trust
authority. The earlier signer-location question is resolved; private-key
contents have not been read during engineering preparation.

The generated-registry validator rejected Composer metadata mistakenly listed
as an input to its own partial version projection. Those self-input entries
were removed; canonical version and reviewed dependency-lock checks pass.
The obsolete ignored Lua 3.0.0 rockspec is retained outside the active generated
set. Security policy now requires every checkout to disable persisted
credentials, confines the existing attestation write permissions to the
protected attester, and recognizes the owner-gated C Git-source publisher.
The proposed mapping passed all six content/workflow security checks before
application. The initial automatic approval rejection was resolved through
read-only inspection of the scanner's exception-list semantics and exact
protected-job validation; no production action occurred.

The final independent Conan engineering pairs pass on both platforms. Linux
normalized identity is
`fd66b77e7c140d6a44a0c53d313a8d325216b8d7dfcdbb2627e34e4756e6893d`;
Windows is
`107c2424855be366e8807c5c0bd6e17a1367a9cbd441d3109222a7278bea1c3e`.
Each platform's preassembled upload ZIP is byte-identical across its pair.
Latest isolated C#, F#, Java, Kotlin, C++ and Python consumers pass; the
rebuilt Preview WASM/npm route passes five Node suites and 21 tests. All 95
registered platform/tool coordinates pass actual SDK preflight (42 Windows,
53 Linux). The integrated security/governance suite passes 209 tests and
32 subtests; the final metadata and native-builder mutation guards pass 52
tests. These remain engineering proof until clean-source acquisition.

The public Rust minimum is corrected to the tested Rust 1.75 toolchain; its
locked serde_json, syn and zmij sources require at least 1.71, so the old 1.70
claim was false. No dependency version is changed. The Python architecture
guard follows the actual shared builder and rejects removal of the pinned
compiler, locked dependency or offline arguments. Windows C assembly selects
the exact installed toolset authenticated by its receipt. Caller overrides
of Rust compiler, target and release profile settings are removed.

The new signed bundle has eight exact size-only hygiene allowances matching
its required profile, product, execution and 42-receipt evidence objects. The
global 1 MiB limit and all credential/path checks remain active. Neighboring
oversized objects and private-key markers are rejected by the new tests; all
25 hygiene/formatting tests pass. The attestation producer owns formatting
only within the new signed bundle. Historical H08 policy entries and bytes
remain preserved. The resulting deep-quality identity projection is refreshed
by its registered identity-only generator, without calibration or live evidence.

Checkpoint 2 is passed: the complete scoped receipt contract, exact artifact
handoff, publication authorization and negative verification boundaries are
implemented and tested. Checkpoint 3 remains open through committed-source
verifier qualification and pin promotion. Checkpoint 4 still requires fresh
committed-source artifact acquisition, generated preparation, Full and
independent no-reuse Release; no engineering output is substituted for them.

The live pre-freeze risk audit initially found three first-party license
metadata failures and a stale runner product dependency. Canonical version
projection now also owns the Maven/Gradle local companion license versions,
the NuGet companion license coordinate, and the public `strling` entry in the
independently versioned runner lock. The runner remains 0.1.0 and all resolved
third-party versions are unchanged. The pinned OSV scanner receives a hashed,
disposable XML projection that resolves only a unique literal project Version
and exact NuGet ranges; floating, unresolved and duplicate versions fail closed.
No MSBuild or package script executes in that projection. First-party Apache
metadata comes from the governed package manifests and repository license;
public registry availability or ownership is not inferred.

The repeated live risk audit records 54 passed, zero failed, zero incomplete,
zero unavailable and one existing `WVR-SEC-VSCE-LICENSE-001` waiver. No new
waiver or permitted-license category is introduced. Its regression run passes
88 tests plus 18 subtests. The runner's locked offline metadata inventory and
the historical performance-artifact integrity check pass without any performance
execution, calibration, evidence relabeling or new admission requirement.

The implementation is committed at
`642cc21f8f5d5ccabde1bb893076e02c624247a7`. A detached checkout freezes that
verifier independently of the packaging source and the eventual evidence
closure. It verifies the unchanged historical H08 bundle successfully with
Windows Git. The first WSL invocation could not resolve the Windows worktree's
Git pointer; that environment failure is retained separately and is not a
failed historical signature or evidence check.

The integration promotes this immutable verifier in all eighteen protected
publisher/attester jobs and adds inexpensive, data-only packaging verification
jobs to CI and certification integrity. Existing H08 verification remains in
place. The workflow promotion passes 131 focused tests and eighteen subtests;
the governed content-security check passes all six checks. Full frozen-verifier
qualification, fresh source-bound artifact acquisition and Full/Release remain
open until their actual retained results are available.

Clean-checkout preparation of integration source
`3f1d841008522c0a34b2a2fc98fd3bc1cd10374b` exposed three remaining defects before
any authoritative profile executed. The Rust public snapshot still recorded
the superseded 1.70 minimum. Twenty upstream CRLF notice lines disagreed with
Git's LF checkout normalization. Production JDK 11 and release JDK 21 produce
different bridge class bytes and manifest data, so one first-party checksum
could not validate both declared compiler contexts. Canonical notices now use
LF and one final newline; the public snapshot is regenerated. Kotlin's canonical
projection consumes a reviewed pair of actual compiler-output hashes bound to
every bridge source/resource, POM and license byte. It rejects stale source,
unknown compiler variants, output substitution and duplicate input fields;
third-party verification remains unchanged. Windows JDK 21 generation and
production JDK 11 verification both pass, with 32 focused tests passing and one
platform-inapplicable test skipped. The reviewed lock catalog changes only the
first-party verification metadata hash; resolved dependencies do not change.

The original source-bound acquisition attempts are retained as diagnostics.
Their completed C and Windows Conan captures are not reused for the next source
freeze. The deep Windows Conan attempt exceeded the MSVC linker path limit;
an independent shorter-root build and isolated consumer passed. Future Windows
Conan acquisition uses short, separate source roots. No Full or Release success
is claimed for the superseded source.

The integrated repair suite passes 120 tests and 21 subtests with two
platform-inapplicable skips. All public-contract projections pass after canonical
regeneration, as do version projection, release policy, release contract and
reviewed dependency-integrity verification. The corrected source is frozen
before restarting independent acquisition.

The next complete generated check rejected the migration record's bare commit
SHA, which the task-record schema requires to be an object with `sha` and
`subject`. The record now uses that exact schema for all implementation commits.
This documentation/control defect was found before any whole profile ran.
Partial acquisition from `c5d464fb9c673ef584c4983d790b3d776d647af4` remains
diagnostic and will not be relabeled for a different source. The final freeze
requires full task-record schema validation and the complete generated check.

The frozen verifier qualification is complete: 128 Windows tests pass; Linux
passes 52 attestation tests and 76 workflow/authorization tests after correcting
the Git-pointer environment issue. The unchanged H08 bundle passes frozen
verification. Current-source security acquisition records 54 passed, zero failed,
zero incomplete, zero unavailable and the single existing VS Code license waiver.
Those security results identify their original source and are reacquired for the
final freeze.

The actual scope/architecture preflight then rejected global upload counts after
the second trusted verification job was added. Retention qualification now checks
each certification job independently, requires immutable upload actions throughout,
and confines the new job to fixed verifier code, data-only candidate inputs,
pinned runtime setup and unconditional non-authoritative evidence retention.
Negative tests reject branch-based verifier code, candidate execution, added shell
commands and authoritative retention. The full governance check passes.

The Windows bounded-command regression also exposed a liveness probe using
`os.kill(pid, 0)`. Python's documented Windows behavior uses
[`TerminateProcess` for non-console signals](https://docs.python.org/3/library/os.html#os.kill).
The probe now opens a read-only synchronization handle and queries it with a
zero-time [Windows wait](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).
The new regression proves a running child survives the probe; the existing
descendant-cleanup regression passes. The combined governance, public-contract
and supply-chain suite records 141 passed, one platform skip and 22 subtests.
One earlier synthetic producer failure did not reproduce; its diagnostics and
subsequent isolated runs are retained without treating them as live evidence.

The complete generated run checked all forty families. Its only remaining
failure was a declaration naming unchanged Java and Kotlin API signatures;
those two unrelated surface entries are removed. The binding READMEs now use
the canonical JVM assembly helper, state the actual release build scope and
caller-supplied native dependency, and describe F#'s companion without a stale
3.0.0 version literal. None of those README paths is a generated-family input.

Historical compiler integrity is now pinned to the preserved
`2d8d897504663211d3768517f0be9f0e28d0f11e` closure, with the original
`dd9d7702237ba9c56e1269418d5a9bd5b582b9f0` verifier. That exact source/verifier
combination passes an independent Windows check. The current packaging job
continues to verify the event source separately with the qualified frozen
verifier. This avoids treating package implementation changes as historical
compiler closure changes. The original trust policy, H08 bundle, core and
specification bytes remain unchanged.

Clean source `9a446043271d282b8d893f6827bea2eef71bfa3f` passes all forty
generated families and fresh security acquisition (54 passed and the existing
single waiver). Its first whole Local run passes 23 operations, then stops at
two noncanonical Python source layouts. The canonical Python formatter fixes
only argument/decorator wrapping and blank lines; AST comparisons prove both
files retain identical syntax trees. All nine formatter targets required by
Full pass through the canonical CLI, and fourteen existing native-builder and
adapter architecture tests pass. Package-pair acquisition was deliberately held
until whole qualification, so this formatting correction invalidates no claimed
release-artifact evidence. The stopped Local result remains retained with its
actual source identity and is not promoted to a pass.

Source `c854b0b18bcece75181eea5985991223cbf6bd78` passes the complete Local
profile: 37 operations, zero failures or waivers, in 11 minutes 10 seconds.
Its Pull Request run passes 21 operations before the JVM runtime validator
rejects the correct 4.0.0 bridge because that validator still requires a literal
3.0.0 coordinate. The sibling exact-runtime provisioning check has the same
obsolete requirement. Both now read the canonical active product-version
authority; stale, duplicated and substituted bridge routes fail closed. The
source-bound 3.0 migration suite identities remain unchanged. Package-pair
acquisition is still held, so this correction invalidates no current artifact
receipts. The original failed whole-profile result remains retained.
The focused repair suite passes 56 tests and eighteen subtests on both Windows
and Linux. Actual Linux JDK 11 Java/Kotlin parity passes two repetitions of
three operations, and the offline Maven probe accepts the prepared 4.0.0 bridge
and four governed third-party artifacts. This targeted proof does not replace
fresh whole-profile certification on the next committed source.

Source `575062382dd3c49acb7d311fd9bc239ae5de4be6` passes all forty generated
families, fresh security acquisition (54 passed and the existing single waiver)
and the complete Local profile (37 passed). Its Pull Request run passes 71
operations before the repository suite finds two stale assertions expecting
Full/Release definition 1.30.0. The effective definitions were already advanced
to 1.31.0 for live supply-chain admission; the tests now assert that authority.
The original suite records 2,101 passed, two failed, 25 platform skips and 4,036
subtests. It remains a failed whole-profile result.

All forty-two actual package captures and transports complete for that source,
including thirty Supported consumer executions. Aggregate restoration then
rejects conflicting Windows/Linux Rust archive bytes. Every file and mode is
identical, but pinned Cargo's host tar implementations use different fixed
source timestamps. Pair analysis also finds NuGet's random core-properties
paths and relationship IDs; all managed assemblies, native libraries and other
package contents are identical. Those captures remain diagnostic and cannot be
relabeled for a later source.

Assembly now writes canonical Rust tar/gzip headers from the source epoch and
content-derived NuGet OPC identifiers before capture. This supersedes the
earlier raw-Cargo-archive retention implementation described above. Both
serializers verify exact payload preservation; NuGet additionally rejects signed
inputs and ambiguous relationships. Rust comparison remains byte-for-byte with
no normalizations, and NuGet comparison still allows only archive timestamps.
No comparison rule or support scope is broadened.

Real retained Windows and Linux Rust archives produce the same canonical bytes
under both pinned Python SDKs, and both host Rust consumers pass. Both actual
C#/F# pairs become byte-for-byte identical; four temporary consumers outside
the checkout pass canonical compilation and incompatible-kernel rejection.
The final focused archive, profile-identity, publication-security and payload
suite passes 171 tests and 23 subtests on each host. An additional isolated
Python sdist build/install passes and reconstructs exactly the native-library
SHA-256 in the release wheel. These targeted repairs and observations precede
the next clean source freeze; fresh acquisition, Full and independent production
Release remain required.

Source `a7cfd50841dabd4223416fd2b6180dafeec5f252` again passes all forty
generated families, fresh security acquisition and all 37 Local operations.
Its Windows C# assembly exposes an integration lookup using the repository root
for a project path relative to the binding directory. The corrected lookup now
finds and canonicalizes the SDK's actual output. A regression models that
binding-relative SDK layout, and complete corrected C#/F# assembly plus two
isolated consumers pass in an explicitly engineering-only diagnostic fixture.
The diagnostic receipt-reader mistake is also retained; it does not change a
producer result. Superseded Pull Request and Linux acquisition processes are
explicitly interrupted with their raw partial results preserved. No PR, Full,
Release or complete package set is claimed for this source. The next committed
source requires fresh profiles and artifact receipts.
The final focused routing/archive/profile suite passes 172 tests and 23 subtests
on each host, and the routing correction changes neither artifact payloads nor
verification normalizations.

Source `40d9f5bf4886037c3650ef5299e73b29ec67b669` passes the complete Local
and Pull Request profiles: 37 and 79 operations respectively, with no failures,
waivers or incomplete operations. All forty-two actual package captures and
transports complete; aggregate restoration and all twenty-one independent
rebuild comparisons pass, covering ninety-five tool coordinates, thirty
Supported consumer executions and twelve Preview observations. An uncached,
offline reconstruction from the produced Python sdist also passes its isolated
consumer and reproduces the release wheel's native-library hash.

The first live Full-type supply-chain producer remains incomplete for fifteen
distributions because its license consumer rejects the security producer's
explicit null optional selection. The producer already classifies each full
reported expression, and the SPDX writer already preserves it when no branch
is selected. The corrected consumer treats absent and null selection equally;
invalid explicit selections still fail closed. It changes no license policy,
classification, waiver or permitted normalization. Expanded validation of all
seventeen actual SBOMs passes with the original unchanged risk evidence. This
targeted diagnostic is not a passing Full or Release profile.

The focused Linux run also exposes an intermittent synthetic fixture defect:
the Conan upload ZIP fixture was written as gzip with a wall-clock header.
Injected clocks reproduce different compared hashes. The fixture now writes a
valid deterministic ZIP, with an explicit two-clock regression; production
artifact comparisons remain unchanged. The original failed run and retry are
retained. These implementation corrections require another committed source
freeze and fresh artifact, security and whole-profile evidence.
The corrected focused supply-chain, publication-authorization and packaging-
security suite passes 114 tests and four subtests on each host. Both registered
release contract and trust projections regenerate without a tracked diff and
their registered verification commands pass.

Source `e3d0ec87f8b5d745d8f885ba8c38748f62bada2a` passes all forty generated
families, fresh security acquisition (54 passed and the existing VSCE waiver),
and all 37 Local operations in 13m15s. All twenty-one first captures and eleven
second Linux captures complete, for thirty-two retained receipts. Pull Request
qualification and the remaining acquisitions are explicitly interrupted when
the final evidence-size preflight identifies a missing closure-path allowance.
Their partial raw results and task-owned cancellation records remain retained;
there is no completed PR, Full or Release claim for this source.

The actual complete C++ SPDX graph is 2,072,161 bytes. Its final signed evidence
path was missing from the existing size-only allowance list. A ninth exact-path
allowance preserves this full graph without truncation, compression, changes to
SPDX content or a larger global threshold. This supersedes the earlier
eight-path inventory. All thirteen hygiene tests pass on both hosts, including
oversized neighboring-file and private-key-marker rejection for every allowed
path. No registered generated family matches these policy/test/document paths.
Fresh committed-source acquisition and certification remain required.
The complete-inventory preflight passes with all 2,492 tracked files plus all
52 actual supply-chain files at their intended signed-closure paths. Both
oversized supply-chain objects are retained intact, and there are no hygiene
findings. The registered repository hygiene check also passes all 2,492 files.

Source `52e9eb4c542afcc657a66331716a7b49feaacdc8` passes all forty generated
families, fresh security acquisition, Local (37/37) and Pull Request (79/79).
All forty-two actual captures and transports complete. Aggregate restoration
and all twenty-one independent comparisons pass; both Full-type and
Release-type live supply-chain bundles pass all seventeen artifacts with
ninety-five tool coordinates. The uncached offline Python sdist reconstruction
passes and reproduces the release wheel's native-library hash. All seventeen
certified exports, restorations and credential-free publication plans pass
under immutable verifier `642cc21f`. The first additional rehearsal's diagnostic
assertion expected the wrong error identifier after correct tamper rejection;
a complete fresh second rehearsal passes, including `publication-substitution`
rejection. Both original and corrected logs remain retained. No registry write
or public installation is claimed.

The actual whole Full run then fails its Local supply-chain contract subcheck:
the inherited live Full evidence variable was applied to every profile CLI
invocation, including Local and Pull Request contract-only subchecks. Their
profile mismatch rejection is correct. The bounded correction restricts only
automatic environment fallback to Full/Release. Explicit evidence still has
precedence, explicit profile mismatches still fail, and live profiles without
evidence still fail closed. The failed Full result retains three passed
operations, the existing single waiver and one failure; no independent Release
or signing starts.

The correction passes 118 integrated supply-chain, publication-authorization and
packaging-security tests with fourteen subtests on each host. A real twelve-case
CLI matrix against unchanged retained evidence confirms all four profile paths,
explicit overrides, missing-input rejection and mismatched-profile rejection.
Both affected registered projections regenerate and verify without a diff.
Additional targeted preflight on clean `52e9eb4c` passes native/WASM interop (77
cases) and reproducible LSP packaging, runtime and install/upgrade/uninstall
lifecycle checks. Those diagnostics do not replace fresh certification on the
next committed source. The approved private key remains unread.

## Storage recovery and exact-source completion — 2026-11-09

Recovery started on clean local `dev` at
`879081506061bb363b5c1563b94d3e32a34676b5`, eleven implementation commits
ahead of the independently closed H08 source. The remote development branch
still pointed to `2d8d897504663211d3768517f0be9f0e28d0f11e`. H08 remains
CLOSED, with its unchanged signed bundle and successful hosted integrity run
[42204135587](https://github.com/strling-lang/strling/actions/runs/42204135587).
No historical hardened-core campaign was repeated or trusted verifier promoted.

All three requested storage reports were present and read: the November 9
cleanup report, deletion/verification manifest, and manual TRIM follow-up under
`target/storage-cleanup-execution-20261109`. Fresh physical D: admission measured
327,340,867,584 available bytes, above the unchanged 112 GiB reserve. Ubuntu
was writable with zero recorded ext4 errors. No storage maintenance was repeated.
Pinned runtimes, protected inputs, Git identities, worktrees, ownership and
retained transport hashes were checked before execution. Missing disposable
compiler caches were rebuilt from governed source and locks.

The original `storage-blocker-87908150.json` records 1,042,149,376 available
physical bytes, Windows error 112, and Linux Dart SIGBUS/read-only failures.
Only Local had started; PR, Full and independent Release had not. Twenty-one
valid receipts and their complete transports were authenticated and retained.
Only the remaining twenty-one captures were rebuilt, producing all forty-two
receipts over twenty-one platform rows and ninety-five tool coordinates.
The interrupted Windows Python sdist directory was hashed and relocated into
task evidence before retrying its clean-source guard; no protected input was lost.

Recovery Local attempt 2 is a genuine retained failure: 35 passed, one failed
of 36 executed operations. The interrupted November 7 Rust incremental tree
contained a 4,128-byte zero-filled object; the compiler also suffered a recorded
OOM kill. The object's SHA-256 is
`2e534ef0107d592d1706ac38ad58596b85ef3375d360a6d669f974792df5cb5a`.
Physical D: remained above 300 GiB and ext4 remained writable. A fresh bounded
scratch build passed eleven regex-frontend tests and compiled the editor binary
harness. Subsequent builds used process-local `CARGO_INCREMENTAL=0` and
`CARGO_BUILD_JOBS=2`; no source, toolchain, dependency lock or supported scope
changed. The object, failed profile, kernel diagnostic and build-environment
record remain retained.

Whole accepted results on clean `87908150` were:

| Profile             | Definition | Required | Passed | Waived | Failed / unavailable / incomplete |        Wall seconds |
| ------------------- | ---------- | -------: | -----: | -----: | --------------------------------- | ------------------: |
| Local               | 1.16.0     |       37 |     37 |      0 | 0 / 0 / 0                         |             811.989 |
| Pull Request        | 1.22.0     |       79 |     79 |      0 | 0 / 0 / 0                         |            2685.143 |
| Full                | 1.31.0     |      124 |    123 |      1 | 0 / 0 / 0                         |            4626.881 |
| Independent Release | 1.31.0     |      124 |    123 |      1 | 0 / 0 / 0                         | 5611.139 controller |

Full and Release correctly report aggregate `waived`, exit zero, with the sole
existing `WVR-SEC-VSCE-LICENSE-001`. Their fingerprints are respectively
`bd3bdef9be2b06c8658ab3391ff5830db866c24b85ea51f24414e7e48107dc0a`
and `eb83fdf39077ab1eec73a2610fffc5b9f1c98ef69d71bb576590b10c9d6c0cdd`.
Local fingerprint is
`6ffe5827cf6ec98786fb660fcce4c0f2c864f8ba569a62f3cb34afaa4450b797`;
PR fingerprint is
`07110615d3e155cf4b893152ac754e68c5839f8ce1458edbebc30730fd5f5d88`.
The production controller ran `--profile release --all --no-reuse` in a fresh
independent source checkout, prepared all forty registered families, and retained
its production and execution manifests. No quantitative performance hardgates
were reintroduced. Every major stage rechecked actual physical D: capacity.

All seventeen Full-type and Release-type live supply-chain artifacts passed
their registered comparisons, SHA-256, complete SPDX 2.3 graph and in-toto/SLSA
provenance checks. All twenty-one independent comparisons passed, including
thirty Supported consumers and twelve Preview captures. Canonical 4.0.0 version
and release-policy checks passed. An uncached offline Python sdist reconstruction
reproduced the wheel's native hash. Seventeen exact-artifact handoff and
credential-free publication plans passed; altered Rust export bytes were rejected
as `publication-substitution`. No registry requests or production credentials
were used. Support tiers and operating-system/runtime scopes remain exactly
those in the inventory above.

Independent key-free reconstruction under qualified immutable verifier
`642cc21f8f5d5ccabde1bb893076e02c624247a7` passed, followed by signing with
the original authorized certifier and independent signature verification.
The retained 152-file, 19,240,650-byte bundle has evidence root
`52bb868586e758beec165989cb644e9646e46eaefc8805c976da6add0f7134dc`
and signature SHA-256
`99a77377939f627fa3ab88784111242f6e3789f7645ee230dfd508b64cf246c6`.
The original key remains intact; its temporary ext4 copy was removed. This is
local signed evidence, with no hosted result claimed for this candidate.

The healthy Fortress quality-certificate worker completed normally. Only this
task's outer controller was deferred while that worker owned large compilation;
its already-running PR child completed normally. No Fortress process was
signaled, file removed or staged work changed. Its independent commit advanced
to `f9815fbad4000fe794b89fc4f9bcb31a0d11d1fe`.

### Signed-closure formatter correction

Final integration exposed a genuine additional defect after the successful
87908150 campaigns: the serializer ownership declaration was mistakenly placed
in the disposition-name list, and the executable repository formatter still
selected signed packaging evidence. A read-only Prettier check rejected the
actual attestation bytes. Reformatting would invalidate hashes and signatures.

Move the existing ownership declaration into `generated_or_serialized` and
exclude only `tests/certification/release-packaging/1.0/current/*` from the
competing repository formatter, matching the existing hardened-core boundary.
The regression verifies preservation of nested JSON/Markdown evidence while
neighboring authored files remain selected. All thirteen formatting tests pass.
The complete closure preflight also identified CRLF in the task-local additional
build-environment record. Its original signed bytes remain retained; the new
candidate will serialize its own environment record with governed LF endings
before reconstruction and signing. No hygiene policy exception is introduced.
This corrects enforcement of existing ownership; it creates no waiver and
removes no certification operation. The complete 87908150 signed bundle and
all successful and failed execution evidence remain historical and immutable.
A new committed candidate requires fresh source-bound acquisition and whole
profiles, including a fresh independent no-reuse Release, before final closure.

## Current-source packaging closure — 2026-11-10

The corrected implementation is frozen at `021239608ffa5066e59bdebde9869e193fbb3eab` on local `dev`.
Its source-tree SHA-256 is
`61a6d5207cdc319e7cb82a3dd465a08fddbc4f1dbbbe3ae9a9dbbc37b92610c0`.
The resume started at `879081506061bb363b5c1563b94d3e32a34676b5`;
the original implementation campaign started at the closed H08 baseline.
The exact signed-bundle closure checkpoint is `6fcc56dc7b1b18a1019817b0b990833fbf73dc3d`. Subsequent changes
are limited to the closure documentation allowed by the frozen trust policy.
The final repository SHA, clean-index result, hosted result and physical
capacity are retained in the final operational report under
`target/release-packaging/recovery-02123960/FINAL-REPORT.md`.

The formatter ownership correction, its thirteen regression tests, and the
retained predecessor report are the only implementation-source changes in
this resume. Their generated-artifact impact is zero registered families.
The new candidate nevertheless acquired its own complete forty-two receipts
and whole profiles; no predecessor profile or receipt was relabeled.
All eighteen setup targets and all forty registered generated families passed.
`python3 tooling/sync_versions.py --check` and
`python3 tooling/release_policy.py --check` both passed with product 4.0.0.
Specification, schema, protocol, ABI, toolchain and Preview-extension identities
remain independently governed. The final `core`, `spec`, historical H08 trust
policy and historical signed H08 bundle have no diff from the closed baseline.

### Accepted deterministic certification

| Profile             | Definition | Required | Passed | Waived | Failed / unavailable / incomplete |        Wall seconds |
| ------------------- | ---------- | -------: | -----: | -----: | --------------------------------- | ------------------: |
| Local               | 1.16.0     |       37 |     37 |      0 | 0 / 0 / 0                         |             858.387 |
| Pull Request        | 1.22.0     |       79 |     79 |      0 | 0 / 0 / 0                         |            2803.775 |
| Full                | 1.31.0     |      124 |    123 |      1 | 0 / 0 / 0                         |            4920.257 |
| Independent Release | 1.31.0     |      124 |    123 |      1 | 0 / 0 / 0                         | 5737.613 controller |

Full and Release aggregate status is `waived`, exit zero, with exactly the
existing `WVR-SEC-VSCE-LICENSE-001`; neither is described as all passed.
There are no new waivers, missing operations or quantitative performance
hardgates. The Release controller used
`python3 tooling/production_certification.py --profile release --all --no-reuse --plain`
in its own newly created source worktree, reconstructed generated artifacts,
retained production/execution manifests and engine identities, and verified
the final clean source. Accepted Local, PR and Full stages were not rerun.

-   Local: `f515b55e4c72120d045c1600114bb64597451c78017f290e16c1a4051754127a`.
-   Pull Request: `a1ee1a763d900ab7b0c9f67672efef4a6a2f8096adad29212581d0f1bd9e27f0`.
-   Full: `1f12e8df2c0b040ffe38a0a0900959036ebdd52a51e75065f36f93e5eec337ca`.
-   Independent Release: `7bab7a6586cfcf28d7734f6a60b6a4b80a58a67147d6ed70dc2cb848f7095d17`.
-   Full-type supply chain: `bab8bf28d3da5ad8e1ac5357e62f146bb97aac164173c5b87ed92e625642bb28`.
-   Release-type supply chain: `1d178e0e3edd8ac7b8bddbe9afbc01c072b919b064167407489a5b89c8fe918a`.

### Current-source distribution outcomes

All rows below passed both independent artifact assembly and the registered
comparison, metadata, checksum, SPDX 2.3, provenance and exact-handoff checks.
Build platforms are assembly scope; the ratified runtime/support declarations
in Checkpoint 1 remain unchanged. Preview captures grant no Supported claim.
Complete subject hashes and file graphs are retained in the signed
`evidence/release-supply-chain/release-supply-chain-evidence.json` and its
`checksums`, `sbom` and `provenance` subdirectories.

| Distribution          | Package                                       | Tier      | Build platforms              | Comparison mode | Outcome |
| --------------------- | --------------------------------------------- | --------- | ---------------------------- | --------------- | ------- |
| C                     | `strling-c`                                   | Supported | windows-x86_64, linux-x86_64 | source-identity | Passed  |
| C++                   | `strling`                                     | Supported | windows-x86_64, linux-x86_64 | normalized      | Passed  |
| C#                    | `STRling`                                     | Supported | windows-x86_64               | normalized      | Passed  |
| Dart                  | `strling`                                     | Supported | linux-x86_64                 | normalized      | Passed  |
| F#                    | `STRling.FSharp`                              | Supported | windows-x86_64               | normalized      | Passed  |
| Go                    | `github.com/strling-lang/strling/bindings/go` | Supported | linux-x86_64                 | source-identity | Passed  |
| Java                  | `com.strling:strling`                         | Supported | windows-x86_64               | normalized      | Passed  |
| Kotlin                | `com.strling:strling-kotlin`                  | Supported | windows-x86_64               | normalized      | Passed  |
| Lua                   | `strling`                                     | Preview   | linux-x86_64                 | normalized      | Passed  |
| Perl                  | `STRling`                                     | Preview   | linux-x86_64                 | normalized      | Passed  |
| PHP                   | `strling/strling`                             | Preview   | linux-x86_64                 | source-identity | Passed  |
| Python                | `STRling`                                     | Supported | windows-x86_64, linux-x86_64 | normalized      | Passed  |
| R                     | `strling`                                     | Preview   | linux-x86_64                 | source-identity | Passed  |
| Ruby                  | `strling`                                     | Preview   | linux-x86_64                 | normalized      | Passed  |
| Rust                  | `strling`                                     | Supported | windows-x86_64, linux-x86_64 | byte-for-byte   | Passed  |
| Swift                 | `STRling`                                     | Supported | linux-x86_64                 | source-identity | Passed  |
| TypeScript/JavaScript | `@strling-lang/strling`                       | Preview   | linux-x86_64                 | byte-for-byte   | Passed  |

All coordinated product versions are 4.0.0. All seventeen routes have
credential-free publication plans and exact certified-byte handoff proof.
Registry/account ownership and production publisher configuration remain
external prerequisites for the separately authorized publication process.
The handoff rehearsal issued zero registry requests and read no publication
credentials; dependency acquisition used governed inputs.

### Native, WASM and supply-chain integrity

All twenty-one platform comparisons pass under their registered byte-for-byte,
normalized or source-identity comparison mode. Forty-two unique build invocations
cover fifteen Supported platform rows with thirty actual isolated consumer
proofs, plus twelve captures over six Preview rows. Preview receipts do not
claim Supported runtime certification. All ninety-five toolchain coordinates
and exact source/lock inputs are present. Both complete supply-chain bundles
pass all seventeen artifacts with zero failed, unavailable or incomplete subjects.
Every applicable subject has SHA-256, an independently validated complete
SPDX 2.3 graph and in-toto/SLSA provenance. No normalization or waiver was added
to force agreement; file-level `NOASSERTION` remains distinct from unresolved
dependency components, of which there are zero.

| Payload               | SHA-256                                                            |
| --------------------- | ------------------------------------------------------------------ |
| Linux static kernel   | `fddb9d3bbb67f1ff104049addd25ae6536a068658bd39425ad5335c853be037f` |
| Windows static kernel | `a1495b749097c20758cb8048e0b29b37f8a5419e6d6a2f04603286881ad4cf98` |
| Linux shared kernel   | `6a23904fe0cb83f86cee090f68858c93eee710c5986fea2463925115acbbd06e` |
| Windows DLL           | `5542b10913723bacc28b0977f95fbdc13f8ee28415007973748a423f17b660f3` |
| TypeScript WASM       | `1d353fb38bb60c342f0266d42d48c932d3e28f8165624eeac5c737170ac64b1e` |

The uncached, isolated, offline Python sdist rebuild and installed consumer
pass; its native hash matches the certified Linux wheel. Its rebuilt wheel
SHA-256 is `af2b9376d28c7d5dde571d9293136b7a9b8057431486095e48da8cd3ae34b288`.
All seventeen exact certified exports, restorations and credential-free
publication plans pass. Actual altered Rust export bytes are rejected as
`publication-substitution`. The rehearsal made zero registry requests, read
no publication credentials and performed no public installation.

Publication workflows default to dry run, bind owner/run, exact source,
version, manifest, signed Release root, destination and checksums, and consume
the certified artifact instead of rebuilding a replacement. Production
credentials remain behind separately authorized protected boundaries.

### Independent reconstruction, signing and hosted integrity

Source-distinct verifier
`642cc21f8f5d5ccabde1bb893076e02c624247a7` independently reconstructed
the complete evidence and artifact graph before any private key was read.
The first corrected-source unsigned audit failed after 33.918 seconds because
the task-local helper passed the qualification progress array to an object-only
JSON loader. Its terminal, original helper and logs remain immutable. Correcting
only that helper's array parser passed a focused check against the actual two
qualification entries; the complete second audit then passed. No product source,
governed input or trusted verifier changed, and accepted profiles were not rerun.
The existing approved certifier then signed the actual accepted evidence;
independent original-signature verification passed. Its authorized key
fingerprint remains `SHA256:ZebV/h+7zLn9D6T4tUO0tI62oHiJV54iGWqmYla7oBA`.
The original key was preserved and its temporary owner-only ext4 copy removed.
No verifier implementation or trust identity changed, so no additional
qualification or promotion was required.

The exact copied bundle has 154 files and 20,043,816
bytes, evidence root `19533d8d1de2248367616df5a6a6782156125efefe6c8e3be47e316ed7c0d2b0` and signature
SHA-256 `2fb3adfae64054a14ddce799db20b161cc58e57c9a9c529af4fed8cc779f15c9`. It includes whole Local and PR evidence
in addition to Full, independent Release, production/execution/engine records,
the complete release supply chain, offline sdist proof and exact handoff proof.
The complete closure preflight passed hygiene and confirmed zero signed files
selected by a competing formatter. Signed bytes were not reformatted.

Hosted integrity passed at
[42810405265](https://github.com/strling-lang/strling/actions/runs/42810405265) on `codex/release-packaging-certification-20261110`,
exact closure source `6fcc56dc7b1b18a1019817b0b990833fbf73dc3d`. Both the packaging verification
job and preserved H08 verification job succeeded. The qualified verifier
executes independently; event candidate content is treated as data. This is
hosted signature/source/evidence verification, not a second cloud Release
campaign. H08 remains CLOSED at
`2d8d897504663211d3768517f0be9f0e28d0f11e`, with its original hosted run
42204135587 and historical failures unchanged. The nonproduction review
branch upload and read-only workflow dispatch implement this resume's required
hosted verification; the original Checkpoint 1 remote-push prohibition remains
historical. No `main`/`dev` update, production tag, registry mutation or release
was performed.

### Resource coordination and measured timing

Every major authoritative stage checked actual physical D: capacity against
the unchanged 112 GiB reserve and inspected competing work. The independent
Release admission measured 290,193,010,688 free physical bytes. The Linux
acquisition and qualification resource holds were respectively 1,319.381 and
4,674.133 seconds while healthy Fortress certificate workers owned compilation.
No Fortress process was interrupted, build data removed or source changed by this task.
Only current missing compiler outputs were rebuilt from governed inputs.

The corrected candidate's first Linux admission attempt started no build:
legacy Windows PowerShell rejected the unsigned read-only observer. Its genuine
terminal and transcript remain in `certify-admission-attempt1*`. The existing
PowerShell 7 runtime executed the same observer successfully under its default
policy; no execution-policy bypass or change was used. This failed admission
is preserved as an orchestration failure, not relabeled as a passing operation.

| Stage                                          | Exit | Recorded wall seconds |
| ---------------------------------------------- | ---: | --------------------: |
| Windows acquisition                            |    0 |              3633.687 |
| clean-roots                                    |    0 |                30.017 |
| canonical-preparation                          |    0 |               305.857 |
| security                                       |    0 |                20.843 |
| linux-acquisition                              |    0 |              1595.660 |
| qualification                                  |    0 |              3665.089 |
| aggregate-supply-chain                         |    0 |                34.394 |
| python-sdist                                   |    0 |                88.086 |
| exact-handoff                                  |    0 |                81.575 |
| full                                           |    0 |              4921.748 |
| independent-production-release                 |    0 |              5738.256 |
| independent-key-free-reconstruction            |    1 |                33.918 |
| independent-key-free-reconstruction-attempt2   |    0 |                47.867 |
| Original-key attest                            |    0 |                25.370 |
| Original-key verify                            |    0 |                10.906 |
| Complete signing and closure-preflight wrapper |    0 |               225.831 |

The tables distinguish per-profile runner time, production-controller time
and enclosing orchestration stages; overlapping scopes must not be summed.
The earlier artifact-only aggregate and handoff were adopted only after
complete exact-source verification, rather than repeated. Their observed
outer intervals were 404.305 and 410.986 seconds; these are explicitly observed
intervals rather than subprocess monotonic measurements. Actual original
producer timings and adoption timings remain in task execution records.
As of `2026-11-10T11:50:14.862231+00:00`, elapsed time from this resume's original recovery
start is 48870.687 seconds, and elapsed time from
the corrected candidate preparation start is 27820.860
seconds, including resource holds. Final operational elapsed time and capacity
are captured after final documentation and hosted verification.

The independently reconstructed real-engine claim records
41 semantic cases, 95 subjects,
205 target-profile compiles,
48 governed refusals,
1129 cross-profile comparisons and
1531 runtime executions, with 0
findings. These are current-source deterministic results, not historical H08
evidence substituted for the packaging candidate.

### Final completion matrix and reserved publication

Implementation, all seventeen distribution routes, all version projections,
reproducibility, supply chain, Local, PR, Full, independent no-reuse Release,
independent reconstruction, signing and hosted integrity are complete.
No interrupted operation, unresolved implementation defect or required
packaging-certification obligation remains. All genuine historical failures
and the successful predecessor evidence remain immutable and source-bound.

External registry/account ownership, trusted-publisher configuration and
protected production credentials remain prerequisites of the separately
authorized public release process. Actual publication, production tags,
GitHub Releases and public-registry installation verification remain reserved
for that process. This closure supplies no publication authorization.

### External production publisher prerequisites

All rows require verified package/namespace ownership, protected `release`
environment controls and separate explicit owner authorization. The declared
secret identifiers below are public policy metadata; no corresponding production secret value was read
or tested. OIDC rows require the registry-side repository/workflow/environment
trusted-publisher binding. Governed Git rows require the authorized tag/source
route and applicable branch/tag protection. Registry/account configuration
remains unverified and unchanged in this task.

| Route              | Registry / governed source mapping | Publisher boundary                                 | Declared protected secret names                                               |
| ------------------ | ---------------------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| release:c          | `github-tag:c-vVERSION`            | Governed Git owner/tag permission                  | None declared                                                                 |
| release:cpp        | `conan`                            | Registry account and protected release credentials | `CONAN_PASSWORD`, `CONAN_USERNAME`                                            |
| release:csharp     | `nuget.org`                        | Registry account and protected release credentials | `NUGET_KEY`                                                                   |
| release:dart       | `pub.dev`                          | Owner-approved OIDC trusted publisher              | None declared                                                                 |
| release:fsharp     | `nuget.org`                        | Registry account and protected release credentials | `NUGET_KEY`                                                                   |
| release:go         | `github-tag:go-vVERSION`           | Governed Git owner/tag permission                  | None declared                                                                 |
| release:java       | `maven-central`                    | Registry account and protected release credentials | `GPG_PASSPHRASE`, `GPG_PRIVATE_KEY`, `SONATYPE_PASSWORD`, `SONATYPE_USERNAME` |
| release:kotlin     | `maven-central`                    | Registry account and protected release credentials | `GPG_KEY`, `GPG_PASSPHRASE`, `MAVEN_PASSWORD`, `MAVEN_USERNAME`               |
| release:lua        | `luarocks.org`                     | Registry account and protected release credentials | `LUAROCKS_API_KEY`                                                            |
| release:perl       | `cpan`                             | Registry account and protected release credentials | `PAUSE_PASSWORD`, `PAUSE_USERNAME`                                            |
| release:php        | `github-tag:php-vVERSION`          | Governed Git owner/tag permission                  | None declared                                                                 |
| release:python     | `pypi.org`                         | Owner-approved OIDC trusted publisher              | None declared                                                                 |
| release:r          | `github-tag:r-vVERSION`            | Governed Git owner/tag permission                  | None declared                                                                 |
| release:ruby       | `rubygems.org`                     | Owner-approved OIDC trusted publisher              | None declared                                                                 |
| release:rust       | `crates.io`                        | Owner-approved OIDC trusted publisher              | None declared                                                                 |
| release:swift      | `github-tag:swift-vVERSION`        | Governed Git owner/tag permission                  | None declared                                                                 |
| release:typescript | `npmjs.org`                        | Owner-approved OIDC trusted publisher              | None declared                                                                 |
