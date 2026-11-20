# Lab compiler tools candidate

This crate builds the independently versioned browser adapter
`strling-lab-wasm 0.1.0-rc.1` from compiler base
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

Build from the compiler repository root with the locked dependencies and
the same memory settings used in browser qualification.

```powershell
rustup target add wasm32-unknown-unknown
$env:CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS = '-C link-arg=--max-memory=67108864 -C link-arg=-zstack-size=2097152'
cargo build --manifest-path bindings/lab-wasm/Cargo.toml --locked --target wasm32-unknown-unknown --target-dir target/lab-tools --release
Get-FileHash target/lab-tools/wasm32-unknown-unknown/release/strling_lab_wasm.wasm
```

The host must pin that digest and verify the descriptor before accepting
results. The website build accepts the candidate only through explicit
qualification settings. Admission of this adapter to a governed release
channel requires owner review, committed source provenance, and independent
candidate certification under the [release policy](../../docs/release-policy.md).

## Independent development checks

From the compiler repository root, run the Wasm verification with Node 22 and
an installed registry copy of `@strling-lang/strling` 4.0.3. Supply the path and
SHA-256 of the candidate build. The command reads both artifacts from disk.

```powershell
$artifact = 'target/lab-tools/wasm32-unknown-unknown/release/strling_lab_wasm.wasm'
$digest = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
node bindings/lab-wasm/verify-browser-artifact.mjs $artifact $digest ../website/node_modules/@strling-lang/strling
```

The check runs the authored formatter and default-limit explanation fixtures
against the candidate module. It verifies both exact conversion destinations
by replaying emitted artifacts through the sealed 4.0.3 compiler. It also checks
that partial and unsupported results carry the correct proof status, that an
elapsed limit produces an unknown outcome, and that the explanation returns
the digest of a synthetic subject without echoing its contents.

An independent locked offline build on Windows used Rust 1.97.1, Cargo 1.97.1,
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

These are local development checks. Browser integration and independent
distribution certification have separate evidence and acceptance gates.
