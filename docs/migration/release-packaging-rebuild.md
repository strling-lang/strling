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

In progress. Actual engineering proof includes:

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

Remaining work includes publication-route closure checks, canonical generated
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

Pending. Existing H08 evidence is historical and does not certify changed source.

## Checkpoint 5 — finalization and readiness

Pending. Publication remains disabled.

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
