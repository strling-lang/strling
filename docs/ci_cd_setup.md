# CI, certification and protected delivery

[Developer hub](index.md) | [Release procedure](releasing.md) | [Support matrix](support-matrix.md)

`toolchain.json` defines canonical Local, Pull Request, Full and Release
membership. CI invokes these profiles and retains structured nonpassing
results as evidence. Supplemental language jobs are component feedback;
an Ubuntu matrix does not establish all-platform binding support or replace
source-bound clean-consumer certification.

## Version and source authority

`governance/release-policy.json#/product/version` is the sole product authority.
The active repository projection is 4.0.0. The Python manifest and other
coordinated surfaces are generated projections; independently versioned
specification, ABI, transport, target and editor contracts remain separate.

```bash
python3 tooling/sync_versions.py --check
python3 tooling/release_policy.py --check
```

Edit the governed source inventory and use its registered generator when a
projection changes. Never bump one package manifest to manufacture an RC.
Internal candidates use an exact source commit. Public `4.0.0-rc.N` coordinates
are provisional until separately authorized, monotonic and immutable once used.
Stable promotion requires the exact terminal RC source plus fresh required
stable certification and only permitted generated coordinate differences.

## Signed certification and hosted acceptance

Full and independent no-reuse Release run in qualified environments. Independent
reconstruction precedes restricted signing by the existing authorized certifier.
The certification-integrity workflow reads candidate evidence as data using
immutable reviewed verifier checkouts and pinned actions. Hosted signature
acceptance does not run candidate code, rebuild packages or confer publication
authorization. Historical H08, packaging and public-verification certificates
retain their original source identities.

## Protected delivery

The release supply-chain manifest defines all 17 routes, package names,
registries, credentials policy, exact upload subjects and external prerequisites.
The generated support matrix links that scope. In particular, C++ uses Conan,
Java and Kotlin use Maven Central, Perl uses CPAN, and Rust publishes `strling`.
The governed Git/source routes retain their exact tag and subtree conventions.

The CD workflow separates dry-run assembly from exact-subject publication.
Publication requires an explicit owner authorization matching source, version,
channel, evidence roots, destinations, protected environment and artifact run.
Certified bytes are uploaded without rebuilding. A coordinate collision is a
failure to reconcile, not permission to skip or replace an immutable upload.
Partial-publication and post-publication verification failures remain explicit.

Configure ownership, trusted publishers, protected environment reviewers and
required secrets only through the separately authorized publication process.
Do not create production credentials while preparing or certifying a candidate.
No push, successful CI job, tag convention or locally signed bundle alone makes
a candidate publishable. Public retrieval and consumer verification run after
actual publication using the already qualified verifier.
