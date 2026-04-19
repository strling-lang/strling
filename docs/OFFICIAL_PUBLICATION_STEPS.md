# STRling Official Publication Steps

This document defines the release and CD checklist for every STRling binding in this repository. It separates registry-backed packages from bindings that are distributed through source control, git tags, or build toolchains.

## 1. Binding Publication Matrix

| Binding    | Distribution platform                   | Release artifact               | Current repo signal                                                                  |
| ---------- | --------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| TypeScript | npm                                     | npm package                    | `bindings/typescript/package.json` and `bindings/typescript/README.md`               |
| Python     | PyPI                                    | wheel and sdist                | `bindings/python/pyproject.toml` and `bindings/python/README.md`                     |
| Rust       | crates.io                               | Cargo crate                    | `bindings/rust/Cargo.toml` and `bindings/rust/README.md`                             |
| Dart       | pub.dev                                 | Dart package                   | `bindings/dart/pubspec.yaml` and `bindings/dart/README.md`                           |
| PHP        | Packagist / Composer                    | Composer package from git tags | `bindings/php/composer.json` and `bindings/php/README.md`                            |
| Ruby       | RubyGems                                | gem                            | `bindings/ruby/strling.gemspec` and `bindings/ruby/README.md`                        |
| Lua        | LuaRocks                                | rockspec                       | `bindings/lua/strling-3.0.0alpha-1.rockspec` and `bindings/lua/README.md`            |
| Perl       | CPAN                                    | CPAN distribution              | `bindings/perl/README.md`, `bindings/perl/Makefile.PL`, and `bindings/perl/setup.sh` |
| Java       | Maven repository                        | jar + pom                      | `bindings/java/pom.xml` and `bindings/java/README.md`                                |
| Kotlin     | Maven repository                        | jar + pom                      | `bindings/kotlin/build.gradle.kts` and `bindings/kotlin/README.md`                   |
| C#         | NuGet                                   | nupkg                          | `bindings/csharp/src/STRling/STRling.csproj` and `bindings/csharp/README.md`         |
| F#         | NuGet                                   | nupkg                          | `bindings/fsharp/src/STRling/STRling.fsproj` and `bindings/fsharp/README.md`         |
| Go         | GitHub module                           | git tag / module path release  | `bindings/go/go.mod` and `bindings/go/README.md`                                     |
| Swift      | Swift Package Manager                   | git tag release                | `bindings/swift/Package.swift` and `bindings/swift/README.md`                        |
| C++        | Conan                                   | Conan package                  | `bindings/cpp/conanfile.py` and `bindings/cpp/README.md`                             |
| C          | Source distribution / build-from-source | source tarball or repo tag     | `bindings/c/Makefile`, `bindings/c/setup.sh`, and `bindings/c/README.md`             |

## 2. Required Release Inputs

Before any CD job is allowed to publish, gather and validate the following for each binding:

1. Package name or artifact ID exactly as the registry expects.
2. Release version, including prerelease suffixes and any registry-specific normalization rules.
3. Repository URL, homepage URL, issue tracker URL, and license identifier.
4. Public or private visibility, plus the intended release channel tag.
5. Registry owner, namespace, or organization account that will receive the package.
6. Authentication method for the CD job: trusted publishing, API token, or registry-specific signing credential.
7. Files that are allowed into the published artifact and files that must be excluded.
8. Runtime compatibility metadata such as supported language version, target framework, minimum SDK, or supported platforms.
9. Build and test command for the binding.
10. Verification command that proves a fresh consumer can install the published artifact.

## 3. Repository-Wide Release Gate

1. Sync the version across all published bindings before cutting a release.
2. Confirm the release branch or tag is the single source of truth for the version being shipped.
3. Run the full binding test matrix before packaging anything for publication.
4. Block publication if any binding fails its packaging dry run, lint step, or test suite.
5. Record the exact commit SHA that produced the release artifacts.

## 4. TypeScript and npm Publication Procedure

The TypeScript binding is the reference package for JS consumers and is published to npm.

### 4.1 Package creation requirements

The package must contain a valid `package.json` with the required `name` and `version` fields. npm requires the package name to be lowercase with no spaces, and the version must follow semantic versioning. The package should also include a README and should keep the published file set intentionally small.

For STRling, the npm package metadata already signals the public package identity in `bindings/typescript/package.json`:

- Package name: `@strling-lang/strling`
- Version: `3.0.0`
- Published files: `dist`

### 4.2 Pre-publish validation

1. Build the package.
2. Run the binding test suite.
3. Run `npm pack --dry-run` to inspect the exact contents that would be published.
4. Confirm that the tarball does not contain secrets, generated junk, or build scratch files.
5. Confirm the README, license, repository link, and export map are correct.

### 4.3 CD publishing rules from official npm docs

1. Prefer trusted publishing for CI/CD releases. npm recommends trusted publishing for GitHub Actions and GitLab CI/CD because it uses OIDC instead of long-lived tokens.
2. If trusted publishing is unavailable, use a granular access token with the minimum required permissions.
3. For CD publishing with token fallback, store the token as a CI secret and expose it as `NPM_TOKEN` in the job environment.
4. Use a project-local `.npmrc` file with `//registry.npmjs.org/:_authToken=${NPM_TOKEN}` instead of hardcoding credentials.
5. Use a token with bypass 2FA only when the workflow must publish automatically and trusted publishing is not available.
6. Do not use legacy npm tokens; npm documentation notes those are removed as of November 2025.

### 4.4 Publish commands

1. Publish the current package with `npm publish`.
2. Publish a scoped public package with `npm publish --access public` when the scope is public.
3. Publish prereleases with an explicit dist-tag only when needed; stable releases use the default `latest` tag.
4. If supported by the workflow, enable provenance so npm links the published package to the build source.

### 4.5 Required npm verification after publish

1. Confirm the published version exists in the npm registry.
2. Confirm the package page shows the correct dist-tag and visibility.
3. Confirm install works from a clean checkout with `npm install @strling-lang/strling`.
4. Confirm consumers receive the intended build output from `dist` only.

## 5. Registry-Specific Publication Rules

### Python / PyPI

1. Build a wheel and an sdist from `bindings/python`.
2. Confirm `pyproject.toml` contains the canonical project metadata and package discovery rules.
3. Verify that the package name, version, and Python requirement are correct.
4. Upload the artifacts to PyPI from CD using the registry credential configured for the release job.
5. Confirm a clean `pip install strling` succeeds.

### Rust / crates.io

1. Validate the crate metadata in `bindings/rust/Cargo.toml`.
2. Confirm the crate name, version, license, description, homepage, repository, keywords, and categories are correct.
3. Run `cargo publish --dry-run` before the release job is allowed to upload.
4. Publish the crate to crates.io from the CD job.
5. Confirm a fresh consumer can run `cargo add strling`.

### Dart / pub.dev

1. Validate `bindings/dart/pubspec.yaml`.
2. Confirm the package name, version, SDK constraint, and dependency graph are correct.
3. Run the Dart test suite and a publication dry run.
4. Publish to pub.dev from the release workflow.
5. Confirm a fresh consumer can depend on `strling` from pub.dev.

### PHP / Packagist

1. Validate `bindings/php/composer.json`.
2. Confirm the package name, version, PHP requirement, autoload mapping, and minimum-stability settings are correct.
3. Tag the repository in git, because Packagist reads releases from the source repository.
4. Ensure Packagist is configured to watch the repository and has the correct webhook or update hook.
5. Confirm `composer require strling-lang/strling` resolves the new release.

### Ruby / RubyGems

1. Validate `bindings/ruby/strling.gemspec`.
2. Confirm the gem name, version, authors, homepage, license, required Ruby version, and file list are correct.
3. Run `gem build` in the Ruby binding directory.
4. Publish the built gem with `gem push` from the CD job using the RubyGems API credential.
5. Confirm `gem install strling` installs the published version.

### Lua / LuaRocks

1. Validate the rockspec file name and version format.
2. Confirm the rockspec version follows the repo convention `3.0.0alpha-1`.
3. Run the Lua tests and any rockspec validation step available in the binding.
4. Upload the rock to LuaRocks or publish through the configured rockspec flow.
5. Confirm `luarocks install strling` resolves the new build.

### Perl / CPAN

1. Validate the module layout under `bindings/perl/lib`.
2. Ensure CPAN metadata, dependency declarations, and `Makefile.PL` are complete.
3. Build the distribution tarball in a clean tree.
4. Upload the distribution to CPAN/PAUSE using the release credentials assigned to the package owner.
5. Confirm `cpanm STRling` installs the published distribution.

### Java / Maven repository

1. Validate `bindings/java/pom.xml`.
2. Confirm `groupId`, `artifactId`, version, license, SCM, issue tracker, and compiler settings are correct.
3. Add or verify Maven release publishing configuration in the CD pipeline before declaring the package externally published.
4. Sign and deploy the artifact to the chosen Maven repository.
5. Confirm a clean consumer can resolve the artifact using the documented Maven coordinates.

### Kotlin / Maven repository

1. Validate `bindings/kotlin/build.gradle.kts`.
2. Confirm group, version, repository target, and dependency metadata are correct.
3. Add or verify Maven publish configuration in the CD pipeline before external release.
4. Sign and deploy the artifact to the chosen Maven repository.
5. Confirm the published coordinates match the README example.

### C# / NuGet

1. Validate `bindings/csharp/src/STRling/STRling.csproj`.
2. Add or verify the NuGet package metadata required for publication: package ID, authors, description, repository, license, and target framework.
3. Build a release package with `dotnet pack`.
4. Push the `.nupkg` artifact to NuGet from the CD job.
5. Confirm the published package can be installed with `dotnet add package`.

### F# / NuGet

1. Validate `bindings/fsharp/src/STRling/STRling.fsproj`.
2. Add or verify the NuGet package metadata required for publication: package ID, authors, description, repository, license, and target framework.
3. Build a release package with `dotnet pack`.
4. Push the `.nupkg` artifact to NuGet from the CD job.
5. Confirm the published package can be installed with `dotnet add package STRling.FSharp`.

### Go / Git-based module release

1. Validate `bindings/go/go.mod`.
2. Confirm the module path is stable and matches the repository tag layout.
3. Tag the repository for the release version so Go consumers can resolve the module version.
4. Verify that the package can be fetched with `go get` from a clean environment.

### Swift / Swift Package Manager

1. Validate `bindings/swift/Package.swift`.
2. Confirm the package name, platform minimums, target layout, and version tag are correct.
3. Cut a git tag for the release version because SwiftPM resolves packages from the repository tag.
4. Verify a clean consumer can add the package by URL and version range.

### C++ / Conan

1. Validate `bindings/cpp/conanfile.py`.
2. Confirm the Conan recipe name, version, license, authorship, source layout, and package info are correct.
3. Run the Conan test and package steps in CI.
4. Upload the package to the configured Conan remote if the release is intended for external consumers.
5. Verify a clean consumer can install the package from the remote or from the release artifact.

### C / source distribution

1. Build the C binding from source in a clean environment.
2. Confirm the setup script, headers, and Makefile continue to work on the supported platforms.
3. Produce a source tarball or release tag for downstream packagers.
4. Verify a clean consumer can build the binding without repository-local state.

## 6. Final CD Release Checklist

1. Version is aligned across all packages that are being shipped in the release.
2. Release notes are written and point to the exact commit SHA.
3. Every publishable binding passed tests and packaging validation.
4. Every registry credential or OIDC trust relationship is configured and scoped correctly.
5. Each package passed a clean install test from a fresh consumer workspace.
6. The release job recorded the published version, registry URL, and timestamp for auditability.

## 7. Notes For Future Automation

1. Prefer a single release orchestrator that builds each binding, runs its dry run, and publishes only after all checks pass.
2. Use release tags to drive versioned publication where the target platform consumes source control tags instead of a dedicated upload API.
3. For prereleases, publish to the correct channel or dist-tag instead of overwriting the stable channel.
4. Keep artifact inclusion lists explicit for every registry-backed package.
