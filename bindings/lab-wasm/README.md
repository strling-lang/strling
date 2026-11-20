# Lab compiler tools candidate

This crate builds the independently versioned browser adapter
`strling-lab-wasm 0.1.0-rc.4` from compiler base
`4e58730bbf67eaff683268e285e7084ccda5fadd`. The published STRling 4.0.3 package
and the `strling.interop@1.0.0` wire protocol retain their existing APIs.

The candidate protocol is `strling.lab-compiler-tools@1.0.0-rc.1`. It accepts
UTF-8 JSON with a `protocol` string and a tagged `request` object. Its response
contains `protocol`, `operation`, and either `result` or `error`. Unknown
fields and incompatible protocol versions are rejected. The request decoder
allows up to 272 JSON container levels to preserve the canonical frontend's
nesting allowance, with room for the protocol headers.

| Operation  | Request fields                                  | Result authority                                                                                                                                                                           |
| ---------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `describe` | None                                            | Adapter version, compiler base revision, operation list and buffer limits                                                                                                                  |
| `format`   | `document`                                      | [Semantic STRling 1.0](../../spec/frontends/semantic/1.0/README.md) canonical formatting or source diagnostics                                                                             |
| `convert`  | `program`, `destination`                        | [Semantic conversion 1.0](../../spec/conversions/semantic/1.0/README.md) with reconstruction evidence                                                                                      |
| `explain`  | `program`, `subject`, optional `target_profile` | [No-match explanation 1.0](../../spec/explanations/no-match/1.0/README.md) using [semantic explanation 1.0](../../spec/explanations/semantic/1.0/README.md) and the optional exact profile |

`explain` uses the contract's Search mode and default limits. The host supplies
monotonic milliseconds through `strling_lab.monotonic_milliseconds`. The
kernel enforces its elapsed and deterministic work limits with that clock.
The canonical response contains subject identity and spans. Raw subject
content stays in the caller and the worker that evaluates it.

The worker writes at most 1 MiB into the module-owned buffer returned by
`strling_lab_input_v1`. Calling `strling_lab_run_v1(length)` returns the
response length. Zero signals an invalid transport length. Copy the response
from `strling_lab_output_v1` before invoking the adapter again. Each export
can grow linear memory, so obtain the current memory buffer after calling
an export that supplies a pointer. Calls are serial and the host owns
cancellation by terminating the worker. The module imports only the clock.

Build from an exact Git revision on Windows with the locked dependencies
and Rust 1.97.1. The replay stages Git archive bytes at `R:\source`, uses
verified registry archives in a fresh `R:\cargo`, and builds into
`R:\target`. It records the Git tree, archive and lock hashes, compiler
and target library hashes, and the raw Wasm digest. The build also remaps
paths exposed in compiler diagnostics. The temporary drive is released on
exit.

```powershell
rustup toolchain install 1.97.1 --profile minimal --target wasm32-unknown-unknown
cargo +1.97.1 fetch --locked --manifest-path bindings/lab-wasm/Cargo.toml
$revision = git rev-parse HEAD
./bindings/lab-wasm/build-from-source.ps1 -SourceRevision $revision `
    -Workspace target/lab-tools -RegistrySeed "$env:USERPROFILE/.cargo/registry"
Get-FileHash target/lab-tools/target/wasm32-unknown-unknown/release/strling_lab_wasm.wasm
```

Pin and independently verify the expected bytes declared in
[`qualification.json`](qualification.json). The GitHub qualification run
records the exact source revision used for its rebuild. The descriptor's
`compiler_base_revision` identifies the original kernel input base.

The host must pin that digest and verify the descriptor before accepting
results. The authorized qualification scope is the exact reviewed source and
the digest-matched Wasm in isolated Website candidate builds. Rebuild the Wasm
from the pinned compiler revision and locked toolchain. The hosted development
check independently verifies its digest and runtime behavior. This path does
not create a distribution channel. A governed release still requires separate
approval and independently reconstructed, signed certification under the
[release policy](../../docs/release-policy.md).

## Independent development checks

From the compiler repository root, run the Wasm verification with Node 22 and
an installed registry copy of `@strling-lang/strling` 4.0.3. Supply the path and
SHA-256 of the candidate build. The command reads both artifacts from disk.

```powershell
$artifact = 'target/lab-tools/target/wasm32-unknown-unknown/release/strling_lab_wasm.wasm'
$digest = (Get-Content ./bindings/lab-wasm/qualification.json -Raw | ConvertFrom-Json).sha256
node bindings/lab-wasm/verify-browser-artifact.mjs $artifact $digest ../website/node_modules/@strling-lang/strling
```

The check runs the authored formatter and default-limit explanation fixtures
against the candidate module. It verifies both exact conversion destinations
by replaying emitted artifacts through the sealed 4.0.3 compiler. It also checks
that partial and unsupported results carry the correct proof status, that an
elapsed limit produces an unknown outcome, and that the explanation returns
the digest of a synthetic subject without echoing its contents. It grows Wasm
memory to 64 MiB and verifies that the module refuses an additional page.

The preceding `0.1.0-rc.1` artifact's locked offline Windows rebuild used
Rust 1.97.1, Cargo 1.97.1,
a 64 MiB maximum memory, and a 2 MiB stack. It reproduced the existing
2,550,144-byte candidate with SHA-256
`640fd5c4c205cff8c69ca46c7933f1351194e3861306cef137d67e1354ea5d72`.
Node 22.12.0 and 24.4.1 both passed 12 formatting cases, 31 byte-span
diagnostic checks, 3 exact reconstruction checks, 2 non-exact conversion
checks, and 17 explanation cases, with separate elapsed and privacy checks.
The registry 4.0.3 Wasm digest was
`6a24a334d5d7e78b17c09e6d9a62d33299d65ac79e52212c4f8db130250656d7`.
Its live descriptor advertised `describe`, `compile`, `target_profile.inspect`,
and `simply.compile`. Each candidate operation returned the sealed protocol's
unsupported-operation error when sent to that released module.

The original Wasm included absolute Cargo registry paths. The second artifact,
`0.1.0-rc.2`, remapped the workspace and registry paths. Its 2,549,360 bytes
have SHA-256
`283ff9d319b4a28220aeac8b187834b12fc6634c9ad1beb9be3be4d4247cc04b`.
Two offline Windows builds from different worktrees, Cargo registries, and
output paths produced identical bytes, including a worktree and output path
containing spaces. A separate empty-cache prefetch and offline build with the
cache inside the source workspace reproduced the same digest. Hosted Windows
replay found a remaining difference. Standard-library panic locations still
contained the Rust installation path, which both local builds shared.

The historical third artifact maps the exact Rust sysroot and keeps the same wire
protocol. Its independent runtime test rejects embedded absolute Windows
paths to the project, standard library, and Cargo registry sources. An exact
named Rust 1.97.1 toolchain without `rust-src` and a separate installation
with `rust-src` built identical bytes from distinct workspace and cache paths.
The 2,548,656-byte SHA-256 is
`3da8047dbbc6402885634b4eb49475ad06cdf894c1eced13fee62b400e23cc81`.

Later clean Windows checkouts with identical tracked adapter and kernel
inputs produced `6df19a4a0c402cc4b88b98abaf3fcca23940276064ec9a0fcb02b5e73a0ee715`
and `4acdb6413c9c494fdf7f5b4bc90bd5d79030bf414b0f14a08ec34d008b06445b`.
The imports, exports and memory were identical. Function, element, code and
data sections differed despite identical sizes. Changing LTO and codegen
units did not remove the checkout sensitivity. Two independent Git archives
of compiler main `1cf698751e04d5b2130b0c2500358499657709fc`, with distinct
registry seeds staged at the same build path, produced identical raw
bytes at `19cdb2c261f6eeac1c1b5664f6a588c62cb859194d5d33ef91fa42c4eeb92869`.
Changing only the staged source path to `R:\relocated\source` reproduced the
`6df19a4a0c402cc4b88b98abaf3fcca23940276064ec9a0fcb02b5e73a0ee715` digest.
Those experiments use the historical adapter version and serve as diagnostic
evidence.

The separate RC4 pin uses that replay recipe with its own package identity.
The proposed immutable distribution is a Preview GitHub release at
`lab-wasm-v0.1.0-rc.4` with the Wasm asset `strling_lab_wasm.wasm`.
The release owner must admit the artifact, destination, support tier and
signing scope. The proposed release needs a source-bound SBOM, provenance,
signed Full and independent no-reuse Release evidence and a protected
publication record. GitHub immutability must be enabled before publication.
The current policy still keeps the crate private.

These checks qualify the declared development artifact scope after
independent replay. Browser integration and production distribution retain
their own evidence and approval requirements.
