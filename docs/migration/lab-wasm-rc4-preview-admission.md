# RC4 Lab Wasm Preview admission

Owner decision `STRL-LAB-WASM-RC4-PREVIEW-ADMISSION-2026-11-20` admits
`strling-lab-wasm 0.1.0-rc.4` for Preview certification. The scope covers canonical
formatting, proof-carrying semantic conversion, and bounded no-match explanation.
Interactive browser observations carry no Regex Conformance certification.

The table records the admission checkpoint. See the later [trusted certification](#rc4-preview-trusted-certification) for the signed disposition.

| Stage                     | Evidence                                                                                                                                                                                                                                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scope                     | **ADMITTED FOR PREVIEW CERTIFICATION** by [the machine record](../../governance/lab-wasm-preview.json).                                                                                                                                                                                                                   |
| Deterministic preparation | Use the registered generators and pinned dependencies before freezing each independent profile runner.                                                                                                                                                                                                                    |
| Reproduced bytes          | Two fresh Windows build roots and separately seeded registries reproduced the exact Git source and raw Wasm. [Hosted Windows replay](https://github.com/strling-lang/strling/actions/runs/44836577636/job/136634353910) used review commit `0ba39f047a5aa833fd05f6cbf3f7c1504908ca9b` with the identical frozen Git tree. |
| Full                      | Profile 1.34.0 requires the separately recorded Preview replay and the existing full supply-chain gate.                                                                                                                                                                                                                   |
| Independent Release       | Profile 1.34.0 also requires the Preview replay. The separate Release runner must disable reuse.                                                                                                                                                                                                                          |
| Trusted signing           | **PENDING TRUSTED CERTIFIER** until the exact-source Full and no-reuse Release succeed and the authentic closure verifies.                                                                                                                                                                                                |
| Distribution package      | Local raw Wasm, receipts, SHA256SUMS, draft SPDX 2.3 inventory, and unsigned source-bound provenance are staged for review. Authenticated certification and final distribution evidence remain pending.                                                                                                                   |
| P20-T05 and public asset  | Reserved coordinate only. Request protected publication approval after verification of the signed closure.                                                                                                                                                                                                                |
| Website shipping          | **WEBSITE SEALED — AWAITING PUBLISHED ARTIFACT**. Website `ba07385ac80f12eb1b432a93e925e465a8887cd1` selects its sealed compiler.                                                                                                                                                                                         |
| Netlify                   | Production approval is separate. The last verified deployed source is `3187d307e1d4707d706b1a7508f0cc5c067cadac`, deploy `6aff4b86748a3243796f055d`.                                                                                                                                                                      |

## Frozen artifact

| Input                                  | Identity                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------- |
| Artifact source                        | `a13009516b81d4acebf0cba6acf9a37877b41d58`                                                  |
| Git tree                               | `5602a5395bcf1962625f836071d720912dc43027`                                                  |
| Source archive SHA-256                 | `b18356bfe7af370e93888df5a7c92f6e785590a392e8015784aa63a9e820e92f`                          |
| Cargo.lock SHA-256                     | `7e09a8ec801d0ff7bd49c3de409082bed7651ab61a9c3b70fe060a532f95e506`                          |
| Compiler base                          | `4e58730bbf67eaff683268e285e7084ccda5fadd`                                                  |
| Protocol                               | `strling.lab-compiler-tools@1.0.0-rc.1`                                                     |
| Rust and target                        | Rust 1.97.1 and `wasm32-unknown-unknown`                                                    |
| Wasm                                   | 2,548,656 bytes, SHA-256 `266f3167537a40722682f436729468795a1672e3d277e5dac9237bd9c04d0181` |
| Each independent build receipt SHA-256 | `4cc7cc0d12af1a0c12ea0c772743c7d02bf4f164766aa26a17f4f7fa1a09181e`                          |
| Draft SPDX SHA-256                     | `86582d8f740bc7f5fcf65c0b3a149ac7ff57f4811e24c1c940656231c4dc6d37`                          |
| Memory and stack limits                | 64 MiB and 2 MiB                                                                            |

The replay script stages inputs in the fixed Windows `R:` layout. Moving the
canonical build paths changed code and data layout in the relocation experiment.
Separate workspaces and registries qualify under the fixed recorded layout.

The certification source is the clean Git revision containing this admission and
the profile definitions. The original artifact source is the independent input.
The Preview profile operation records both revisions and verifies that the
artifact source belongs to the certification source's history. The certifier
must sign the profile artifacts for the clean certification source and validate
the separate artifact identity within each profile.

The sealed npm archive is pinned by SHA-512 in the machine record. The replay
verified its four-operation ABI and embedded Wasm SHA-256
`6a24a334d5d7e78b17c09e6d9a62d33299d65ac79e52212c4f8db130250656d7`.
Node 22.23.5 ran 12 formatting cases, 3 exact reconstruction cases, 2 non-exact
conversions, 31 diagnostic cases, and 17 bounded explanation cases. The replay
also checked explanation privacy, elapsed limits, and embedded absolute paths.

## Certification and independent review

Use fresh independent clones for Full and no-reuse Release. Install the
lockfile-pinned root and LSP dependencies and prepare the Lua rockspec and LSP
extension through the registered generators before freezing the inputs. The
Release runner performs those preparations in its own staged worktree.

```sh
python3 -m tooling.lab_preview_certification --prepare "$candidate" --evidence "$inputs"
export STRLING_LAB_PREVIEW_EVIDENCE="$candidate"
export STRLING_LAB_PREVIEW_SEALED_ARCHIVE="$sealed_npm_archive"
./strling profile full --artifact "$full_receipt"
npm run test:all -- --profile release --all --no-reuse --plain
python3 -m tooling.lab_preview_certification --verify-signed-bundle "$bundle" \
    --certification-source "$certification_source" --json
```

The product-wide live supply-chain, runtime and release gates remain mandatory.
For Full and Release, set `STRLING_RELEASE_SUPPLY_CHAIN_EVIDENCE` to the genuine
live producer and clean-consumer evidence rooted in the exact frozen
certification source. The Preview package and isolated website transport
fixtures provide different evidence. Record both profile results independently
and verify the complete signed bundle against the configured release-candidate
trust policy. The preceding unsigned diagnostic at the original artifact
source stopped at the live product-wide evidence gate during its no-reuse
Release run. It did not yield a certifier closure.

## Proposed immutable distribution

**Draft GitHub release title** · STRling Lab Wasm 0.1.0-rc.4 Preview

**Draft body** · Browser compiler-tools Preview for canonical Semantic STRling
formatting, proof-carrying conversion and bounded no-match explanation.
The adapter uses `strling.lab-compiler-tools@1.0.0-rc.1` alongside the sealed
STRling 4.0.3 compiler. Verify the downloadable Wasm against SHA256SUMS, the
frozen source, and the exact signed certification evidence before consuming it.

**Reserved coordinate** · GitHub repository `strling-lang/strling`, tag
`lab-wasm-v0.1.0-rc.4`, asset `strling_lab_wasm.wasm`. The proposed tag points
to the frozen artifact source. The corresponding download is the
[reserved asset URL](https://github.com/strling-lang/strling/releases/download/lab-wasm-v0.1.0-rc.4/strling_lab_wasm.wasm).
Verify actual GitHub release metadata reports `immutable: true`, that the tag
resolves to the approved source, and that an independent download from the
allowed asset origin matches the complete digest and Wasm identity.

**P20-T05 request template** · Authorize publication of
`strling-lab-wasm 0.1.0-rc.4` for the reserved coordinate above from
`a13009516b81d4acebf0cba6acf9a37877b41d58` with artifact SHA-256
`266f3167537a40722682f436729468795a1672e3d277e5dac9237bd9c04d0181`.
Supply the approved protected run ID, clean certification source, the verified
closure digest, and the GitHub immutability verification before execution.
This template records future review inputs.

After independent download and authenticated verification, the website shipping
manifest can name the reserved asset URL and pinned bytes, digest, bounds,
protocol, sealed compiler version, artifact source, compiler base, and verified
closure SHA-256. Build from a clean website checkout and repeat shipping browser
and static-host acceptance. Netlify production release has its own approval.

## RC4 Preview trusted certification

The certified compiler source is `bab5a0aaf8d04a437d5c5f1aac3379a3c0511702`. The evidence-only
snapshot `c67080f17b0755a32c0a18dbb784fb623b5611ad` is retained in Git history and was
accepted by all four [hosted integrity jobs](https://github.com/strling-lang/strling/actions/runs/44983451950). The immutable
verification reader is `59f62e68ed72475b5cceb8ee5c8e80844ee3e2b0`.

Full 1.34.0 and independent no-reuse Release 1.34.0 each completed all
126 operations, with 125 passes, the existing `WVR-SEC-VSCE-LICENSE-001`
waiver, and zero failures. Both independently authenticated all 17 producer
routes and passed RC4 Preview replay. Staged product qualification passed
all 17 artifact protocols and all 15 Supported clean consumer scopes.

The signed evidence root is `95753563a98e1473fc065fa0256f058075ee702bf3706f661b154dccc9583a76`.
Attestation SHA-256 is `9ed60971bc08247b2f207864b3a912ca0f490a0a644c5d75e1670368a89614fa`.
Signature SHA-256 is `19f0720213ae1f8e9f3a30c2fe55fc6565785f2d1c4aaf6f84a0ec58e17c65ef`.
The nested package certificate root is
`efb5d2463a46ec38f5f34ccccab41664ce45517d452c78b0cf6f5d3078500aa5`.
The frozen 2,548,656-byte Wasm has SHA-256
`266f3167537a40722682f436729468795a1672e3d277e5dac9237bd9c04d0181`.

The published Fourth Edition certificate and fixed source remain available
through their recorded immutable refs. The default current-candidate view
continues to point to that product snapshot. P20-T05 approval, configured
GitHub release immutability, and a reviewed protected RC4 publication run
remain required. Website shipping and Netlify production have separate gates.
