# Temporary picomatch development-tooling exception

The Program Owner conditionally authorized `WVR-SEC-PICOMATCH-REDOS-001` on
November 17, 2026, through **November 24, 2026 inclusive UTC**. The exception
accepts risk; it does not resolve or downgrade the high-severity
`GHSA-fc5q-39xc-vjpf` / `CVE-2026-112366` vulnerability. Its original failed
prerequisite evidence for `61fb4141faa5034964c5de17eb8b39a559b6cec9` remains
unchanged. Fresh successor certification is required.

The frozen-source [assessment](picomatch-402-exposure.json) independently
inspected both lockfiles, the npm dry-run package file list and an esbuild
dependency graph. The diagnostic client bundle equals the prepared extension
client byte for byte. This is preparation evidence, not a public installation
or a substitute for fresh certified artifacts.

| Root and scanner check                                    | Installed picomatch path                                | Version |
| --------------------------------------------------------- | ------------------------------------------------------- | ------- |
| LSP packaging: `security.vulnerability.lsp-npm`           | `node_modules/picomatch`                                | 4.0.7   |
| TypeScript tests: `security.vulnerability.typescript-npm` | `node_modules/picomatch`                                | 2.3.2   |
| TypeScript tests                                          | `node_modules/@parcel/watcher/node_modules/picomatch`   | 4.0.7   |
| TypeScript tests                                          | `node_modules/jest-haste-map/node_modules/picomatch`    | 4.0.7   |
| TypeScript tests                                          | `node_modules/jest-message-util/node_modules/picomatch` | 4.0.7   |
| TypeScript tests                                          | `node_modules/jest-util/node_modules/picomatch`         | 4.0.7   |

Every listed lock entry is `dev: true`. Neither package manifest declares
production or optional dependencies. The LSP path is through VSCE's tinyglobby
packaging dependency. The TypeScript paths are through Jest, its watcher and
anymatch. They run during development and packaging; they are not the STRling
compiler's regex engine or public runtime API.

The TypeScript package includes its declared `dist` files and package
documentation, excluding `node_modules` and these development dependencies.
The extension client graph contains neither picomatch, tinyglobby nor VSCE;
its closed payload has no `node_modules` tree. VSCE packages that payload with
`--no-dependencies`. Native, WASM, Python and the remaining host routes do not
load these npm development trees. Governed Git source distributions retain
development manifests and locks; installing developer tools from source is a
development context covered by the warning, not proof of runtime exposure.
No demonstrated attacker-controlled glob path was found in published runtime
functionality or exposed services. The vulnerability remains reproducible when
malicious globs are deliberately passed to the developer library.

Compensating controls are reviewed exact-source builds, locked dependency
identities, repository-controlled packaging/test patterns, isolated bounded
build/test processes, no service accepting untrusted globs through these tools,
closed artifact payload validation, unchanged vulnerability scans and severity
thresholds, complete source-bound evidence, and protected production approval.
Do not run packaging or Jest against attacker-supplied configuration as a
trusted operation. Ordinary validation jobs retain their existing restricted
permissions and cannot consume production secrets.

The engine matches only `SEC-VULN-BLOCKING`, package `picomatch`, the exact
advisory URL, severity `high`, the two enumerated check IDs and their exact
versions. Its Cartesian matching accounts for three findings across six
installed paths. All four manifest/lock input paths must match exactly.
Different advisories, packages, versions, severity, roots, missing findings,
duplicate findings, stale scope, expiration and overlap remain blocking.
The separate VSCE license waiver is unchanged. Runtime-source identities and
development-only boundaries are enforced by focused tests included in the
registered tooling test operation; fresh package/consumer evidence must retain
those boundaries. Any demonstrated published-runtime exploit path rejects this
exception rather than extending it.

Check the [official npm registry](https://registry.npmjs.org/picomatch) and
[upstream releases](https://github.com/micromatch/picomatch/releases) during
continuing preparation and before publication authorization. The
[advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) currently lists
all published versions through 4.0.7 as affected with no patched version.
Its referenced PR is unmerged and is not an accepted replacement artifact.
Qualify a verified compatible fix in the next governed release, update exact
locks and required source-bound evidence, then retire the waiver and its
registrations. If findings disappear, stale matching fails closed. There is
no implicit renewal after November 24 and no publication authorization in this
exception.
