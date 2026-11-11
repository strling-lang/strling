# Independent public distribution verification

Status: IMPLEMENTATION COMPLETE — PUBLIC EXECUTION PENDING.
Public execution has not occurred. This report supersedes the earlier in-progress account; historical source identities and failures remain preserved.

The frozen implementation is `3e7061271d906251cb17c3eb06b6c748ac3068e7`.
The current registry derives 256 obligations: eight artifact checks for each
of 17 routes (136), and eight consumer checks for each of 15 Supported platform
rows (120). Eleven distributions are Supported; six retain Preview boundaries.
The 42 independently built receipts cover 21 platform rows and 95 toolchain
coordinates. All 21 reproducibility comparisons pass. These are current-source
staged engineering observations; none establishes a public 4.0.0 download.

## Source and failure reconciliation

-   Failed candidate `fc0274e9ac4fdbd67a6eb93bc2b31477e860fc68` stopped Local at
    operation 15/38 because the product producer manifest omitted
    `public_distribution_contract`. Its 42 receipts remain historical evidence
    bound to that source and were not adopted for this implementation.
-   Corrected candidate `237607049c849f82621c88885f6348e7804e6c3b` completed all
    eight preparation stages and 40 generated families. LSP preparation passed
    in 65.7207379 seconds. Its Local subsequently failed at operation 28/38 on
    an unused `io` import, after 27 passes. The apparent LSP interruption was
    not an LSP failure.
-   Subsequent focused diagnostics corrected stale profile-version assertions,
    signed-bundle serialization ownership and five exact large-subject paths.
    The final public producer uses the existing structured result contract,
    preserving the historical reader's single atomic functional-resource result.
-   `1838ba890f825dd1c01173fcfb5414f88c742bd0` passed Local 38/38 but failed PR
    at operation 73/80 on a stale readiness-test denominator. The narrow successor
    derives membership from the governed registry and explicitly requires the
    public producer; it preserves exact ordered checks.
-   Final source `3e706127` passed all eight preparation stages, all 40 generated
    families, and a repository diagnostic with 2377 passes, 25 platform-specific
    skips and 4060 passing subtests. LSP preparation took 64.65627645199129 seconds.
    Targeted mutations reject absent, duplicate, renamed, stale, wrong-profile,
    incomplete, falsely passing and independently omitted public results.
-   Current-source acquisition preserved an initial Python SDK mismatch, then
    used the already prepared locked SDK. All 387 installed RECORD hashes and
    actual imports/pip consistency passed. No product evidence was reused.
-   A real Ubuntu Perl patch update made one first/second tool identity pair
    inconsistent. The old cohort was preserved; a fresh source-only first Perl
    build under the exact second-build tool identity restored strict coherence.
    Negative replay still rejects the old mismatched receipt.

-   Public reconstruction initially stopped on an operational adapter KeyError: the immutable verifier had returned a passing versioned envelope, while the recovery helper expected top-level fields. The corrected adapter reads the unique integrity check and verifies schema, operation, aggregate, source/head, exact attestation/root/signature, certifier, profiles and waiver inventory. The actual retained response passes and 18 adversarial substitutions/omissions fail. The immutable readers and frozen implementation are unchanged. A sole continuation owner resumed only reconstruction/signing, preserving the original package-owner bytes and adding explicit continuation/adapter evidence.

## Accepted profiles

| Profile             | Version | Result                                | Actual wrapper seconds | Evidence fingerprint                                               |
| ------------------- | ------- | ------------------------------------- | ---------------------: | ------------------------------------------------------------------ |
| Local               | 1.18.0  | 38 passed /38                         |      790.9924104749953 | `253edb457681c92366d884c6eceb0e636c00c634ca5a7238c7342c217173c6f1` |
| Pull Request        | 1.24.0  | 80 passed /80                         |     2621.3474850259954 | `9e4f73466319b9bb7d43e083c9742fd50aaa653902759d6ea1f0716b7cb0bfb4` |
| Full                | 1.33.0  | 124 passed + 1 authorized waiver /125 |         4893.460244952 | `ee585452192dc615f65ab9053bfe38621c6570eacc491c6afe11c55eb4f99b13` |
| Independent Release | 1.33.0  | 124 passed + 1 authorized waiver /125 |     5852.0006502609995 | `83f5df9556db988a9c1300b8a76e6ca812c72a995bc7dd6a77c3f540e3c0f719` |

The sole permitted waiver is `WVR-SEC-VSCE-LICENSE-001`, scoped to the existing
VSCE license finding. Local and PR have zero waived operations. Full has zero
failed, unavailable, incomplete, unconfigured, unenforceable or not-applicable
operations. Its public producer passed with fingerprint
`2abfbf896407373df28a6b8b19e02a2c72254082364d1363954e4152adb88335`.
Quantitative performance remains non-gating; functional resource safety passed.

Independent Release completed the canonical `--profile release --all --no-reuse` aggregate in a fresh source worktree. Its production receipt confirms clean detached source, regenerated artifacts, honored no-reuse and clean final source/root state. Original producer objects were retained and reconstructed before signing.

## Trust and historical preservation

The packaging reader is `642cc21f8f5d5ccabde1bb893076e02c624247a7`; the public
implementation certificate reader is `080107ed6d7893d60eb011fb83af09ac937eeb89`.
These roles are distinct from the future protected public execution pin.
The existing certifier is `strling-local-release-certifier-2026-01`, public key
fingerprint `SHA256:ZebV/h+7zLn9D6T4tUO0tI62oHiJV54iGWqmYla7oBA`.
No new authority or trust-key rotation is authorized.

The preservation audit confirms all 96 H08 certificate files exactly match
`2d8d897504663211d3768517f0be9f0e28d0f11e`, and all 154 packaging certificate
files exactly match `33e50ac033314dad089717a0ee20c0c7c310dea7`, including Git
blob and mode identities. Packaging implementation
`021239608ffa5066e59bdebde9869e193fbb3eab` remains certified. These are
preservation checks, not reopened historical certification.

## Closure acceptance

All implementation and certification obligations have passed. Real public execution remains separately pending publication.

## Distribution coverage

| Distribution          | Coordinate                                  | Tier      | Governed scope                                                            | Current-source outcome                                                           |
| --------------------- | ------------------------------------------- | --------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| C                     | strling-c                                   | Supported | windows-x86_64 and linux-x86_64 interop routes                            | windows-x86_64: passed; linux-x86_64: passed                                     |
| C++                   | strling                                     | Supported | windows-x86_64 and linux-x86_64 interop routes                            | windows-x86_64: passed; linux-x86_64: passed                                     |
| C#                    | STRling                                     | Supported | windows-x86_64 clean-consumer native assets                               | windows-x86_64: passed                                                           |
| Dart                  | strling                                     | Supported | linux-x86_64                                                              | linux-x86_64: passed                                                             |
| F#                    | STRling.FSharp                              | Supported | windows-x86_64 clean-consumer native assets                               | windows-x86_64: passed                                                           |
| Go                    | github.com/strling-lang/strling/bindings/go | Supported | linux-x86_64 with cgo                                                     | linux-x86_64: passed                                                             |
| Java                  | com.strling:strling                         | Supported | windows-x86_64 with caller-supplied absolute native path                  | windows-x86_64: passed                                                           |
| Kotlin                | com.strling:strling-kotlin                  | Supported | windows-x86_64 with caller-supplied absolute native path                  | windows-x86_64: passed                                                           |
| Lua                   | strling                                     | Preview   | linux-x86_64                                                              | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |
| Perl                  | STRling                                     | Preview   | linux-x86_64                                                              | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |
| PHP                   | strling/strling                             | Preview   | linux-x86_64 with caller-owned native payload discovery                   | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |
| Python                | STRling                                     | Supported | windows-x86_64 and linux-x86_64 with CPython 3.12 evidence                | windows-x86_64: passed; linux-x86_64: passed                                     |
| R                     | strling                                     | Preview   | linux-x86_64                                                              | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |
| Ruby                  | strling                                     | Preview   | linux-x86_64                                                              | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |
| Rust                  | strling                                     | Supported | windows-x86_64 and linux-x86_64 reference kernel/facade                   | windows-x86_64: passed; linux-x86_64: passed                                     |
| Swift                 | STRling                                     | Supported | linux-x86_64                                                              | linux-x86_64: passed                                                             |
| TypeScript/JavaScript | @strling-lang/strling                       | Preview   | Windows Node 24 observation and Chrome browser WASM certification harness | Artifact qualification passed; Preview consumer claims remain bounded/unexecuted |

## Runtime declarations versus tested scope

The C# and F# packages target net9.0; the observed Windows SDK is9.0.302. Java and Kotlin produce JVM11 bytecode; the observed Windows JDK is21.0.12.1, with Maven3.9.11 and Gradle8.5. Those declarations do not establish additional tested JVM/OS combinations. Python explicitly requires >=3.12,<3.13 and was built with CPython3.12.10 on Windows and3.12.3 on Linux. Dart declares >=3.0.0,<4.0.0 and the registered Linux observation is3.12.2. Swift declares tools5.9 and was observed with6.3.3 on the governed Linux scope; package metadata does not establish macOS certification.

Native Windows scope requires the MSVC14.44-compatible v14 x64 runtime. Linux native scope is the governed GNU/glibc environment, observed on Ubuntu24.04/glibc2.39; musl and additional architectures/distributions are not certified. Rust/Cargo1.75.0 and Go1.22.2 are the registered observations. Preview assembly observations include Lua5.1.5, Perl5.38.2 (68 registered patches), PHP8.3.6, R4.3.3 and Ruby3.2.3. TypeScript's Linux artifact build used Node22.23.2/npm10.9.8; its existing bounded Windows Node24/Chrome WASM observations remain distinct from Supported public-consumer certification. No runtime or platform support is expanded by these observations.

## Sealed evidence transport

Windows SDK diagnostic logs retain their original CRLF bytes. A dedicated transport qualification demonstrated that ordinary Git staging would normalize those bytes. Exact no-filter Git objects and explicit index entries preserved all three serialized fixtures through fresh Windows and Linux/ext4 checkouts, with clean tracked state. A forced-text CRLF JSON negative was rejected. The registered JSON producers already emit LF. Closure must preserve the signed producer bytes and verify every indexed blob against the signed file inventory, then run the unchanged immutable verifier on a fresh checkout. No .gitattributes, source, producer, support or trust-policy change was required. The complete diagnostic qualification is embedded in the existing operational admission evidence; original metadata bytes remain preserved.

The first documentary seal passed cryptographic verification but was rejected by the unchanged hygiene policy for two missing final newlines and two diagnostic log paths. Its exact signed bundle and rejection remain preserved. The accepted replacement carries those supplemental bytes in bounded, lossless JSON archives, reproduces the original package certificate byte for byte, and passes positive and adversarial codec tests. All 256 obligation results and producer bytes remain unchanged. Prospective hygiene passed before signing and again on the signed replacement; no policy exception was added.

The evidence closure was pushed only to the dedicated codex/public-verification-3e706127-closure branch for the read-only certification-integrity workflow, with tag and submodule pushing explicitly disabled. The first commit request had a malformed operational argument vector and exited before running its helper; its terminal evidence is retained, and the corrected request committed the already validated bytes. This did not change the frozen implementation or signed evidence.

## Independent reconstruction and signed evidence

Both key-free independent reconstructions passed before their signing steps. Local signature verification used the unchanged immutable readers; its generic `CLOUD_VERIFIED` output label is not treated as proof of hosted execution. Actual hosted acceptance is recorded separately below.

| Subject                                      | SHA-256                                                            |
| -------------------------------------------- | ------------------------------------------------------------------ |
| Package evidence root                        | `b62f592e4fdd3021a98a2c6b08db76cd108bf827f0199ec73ae0212845d78ece` |
| Package signature                            | `9778384cdc8ae49916cbf138abf1dd11af36ba353b0ac43c9ea2b82dbb2669f2` |
| Public implementation evidence root          | `89a3ed2ab59f883463fcd5ed36e665d3fe18bdfd8bb2112d5c28a2435e23302e` |
| Public implementation signature              | `371375de748b807474c889d22523fb7e6838d1eb59855e812f0d90e9cc64f0c2` |
| package-reconstruction reconstruction record | `5d5512d3d3d64db5522d677390bea3cb0a008ae90c654067c104416bbb34e038` |
| public-reconstruction reconstruction record  | `dbd74bc217dcbb8ba08b543562f3712e58946f46f90a0d366c91e35af6a50947` |

The complete authenticated file and fingerprint inventory is in [the signed attestation](../../tests/certification/public-verification/1.0/current/attestation.json). It retains all mandatory producer subjects, Full/Release results, Local/PR qualifications, 42 current-source build receipts, supply-chain companions and the exact staged verification evidence. The public producer is required once in every authoritative profile. Its exact result contract, identity, source, documentation and obligation inventory are independently reconstructed; zero-exit execution without its result is incomplete.

Current-source staged qualification passed 17 artifact routes and all 15 applicable clean-consumer scopes, accounting for exactly 256 registered obligations. Artifact authority remains synthetic and consumer authority staged; every observation is READY, not public VERIFIED. Native/WASM identity and applicable substituted-kernel/target-profile rejection passed.

## Actual hosted acceptance

[Trusted integrity run 43075532645](https://github.com/strling-lang/strling/actions/runs/43075532645) passed against closure `bc37d2a70a3336e6be624ea2f5f25c6245f83b9b` and certified implementation `3e7061271d906251cb17c3eb06b6c748ac3068e7`. All three required jobs passed: public implementation, historical packaging, and historical H08. The downloaded public verification result matches the exact attestation, evidence root, signature, source, profile fingerprints and waiver inventory.

## Recorded execution attempts and timings

Seconds below are recorded wrapper timings. They include admission waiting where applicable; the independent Release wrapper also includes fresh isolated preparation. Historical failed operational attempts remain visible and were followed by separately retained accepted recovery results. Timing is observational and non-gating.

| Stage/attempt                | Exit code |   Seconds |
| ---------------------------- | --------: | --------: |
| source-roots                 |         0 |    13.169 |
| windows-source-roots         |         0 |    13.446 |
| input-identities             |         0 |     0.434 |
| candidate-registration       |         0 |    41.074 |
| preparation                  |         0 |   325.314 |
| accept-preparation           |         0 |     0.181 |
| version-sync                 |         0 |     0.131 |
| release-policy               |         0 |     0.289 |
| repository-diagnostic        |         0 |   747.751 |
| security                     |         0 |   711.860 |
| local-pr                     |         0 |  6412.412 |
| windows-builds               |         0 | 14869.286 |
| linux-builds                 |         1 |   463.414 |
| linux-python-build-readiness |         0 |    75.155 |
| linux-builds                 |         0 |  2265.879 |
| receipt-pairs                |         1 |     2.396 |
| perl-toolchain-cohort-repair |         0 |    16.589 |
| receipt-pairs                |         0 |     1.113 |
| transport-kernels            |         0 |     1.213 |
| supply-chain                 |         0 |   300.452 |
| python-sdist                 |         0 |   107.139 |
| certified-handoff            |         0 |   350.839 |
| full-go                      |         0 |     4.557 |
| full                         |         0 |  5056.856 |
| independent-release          |         0 |  6114.049 |
| package-reconstruction       |         0 |    56.101 |
| package-signing              |         0 |    62.946 |
| public-artifacts             |         0 |   345.133 |
| public-kotlin-sdk            |         0 |   160.781 |
| public-jvm-sdk               |         0 |   369.772 |
| public-dart-sdk              |         0 |     4.369 |
| public-windows-consumers     |         0 |   459.340 |
| public-linux-consumers       |         0 |   763.481 |
| public-collection            |         0 |   232.839 |
| public-reconstruction        |         1 |    82.845 |
| public-reconstruction        |         0 |   115.824 |
| public-signing               |         0 |   129.033 |
| public-reconstruction        |         0 |   177.917 |
| public-signing               |         0 |   234.986 |
| public-seal-hygiene          |         0 |     9.900 |

The WSL recovery preserved terminal evidence, then used the explicitly authorized cancellation of the stalled unregister client and controlled service restart. No healthy STRling or Fortress worker was interrupted. Subsequent protected compiler reservations were respected. Physical D: capacity and Linux guest filesystem availability were measured separately; the 112 GiB physical certification admission reserve remained enforced.

Report observation: 2026-11-11T18:13:22.267636+00:00; physical D: free 227.18 GiB. The final operational completion report records the final Git commit, terminal hosted run and final capacity after documentation closure.

## Publication boundary and next authorized task

The qualified public-execution implementation is this source, distinct from the immutable certificate readers and the governed artifact source. Future release owners must verify exact namespaces/uploader ownership and configure the protected request, certified artifact/closure/run identities and verifier pin under the existing policy before separately authorized public publication and verification. Those external publication prerequisites remain explicit; Preview is not promoted. No package, production/RC tag, GitHub Release, registry upload, ownership change or production publication credential access occurred.

The earlier account is preserved at [implementation source 3e706127](https://github.com/strling-lang/strling/blob/3e7061271d906251cb17c3eb06b6c748ac3068e7/docs/migration/public-distribution-verification.md). The task record retains all historical checkpoints. Closed H08 and packaging certificate bytes and Git modes remain unchanged.
