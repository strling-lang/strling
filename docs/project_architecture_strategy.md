# Project Architecture & Strategy

[← Back to Developer Hub](index.md)

## Durable direction

STRling develops as one semantic compiler platform with multiple authoring
surfaces, host adapters, target profiles, and tooling consumers. The ratified
[`product architecture`](../governance/product.md) and
[`architecture invariants`](../governance/architecture.md) control this
strategy.

Work proceeds contract first:

1. ratify semantic specifications or versioned contracts;
2. author independent conformance evidence;
3. implement the canonical compiler capability;
4. verify behavior and compatibility;
5. expose it through thin host adapters and shared tooling; and
6. certify target-specific artifacts against versioned profiles.

## Sources of authority

The ratified specification defines semantic behavior. Versioned formal contracts
and delegated specification-authored conformance cases define their declared
scopes. The reference implementation demonstrates conformance and cannot
silently extend those sources.

TypeScript is a thin host adapter, not the semantic source of truth. Retained
TypeScript-derived fixtures are data-only historical evidence and cannot drive
product generation or certification.

`governance/release-policy.json#/product/version` is the sole product-version
authority. The Python manifest and other coordinated package versions are
generated projections. Specification, source dialect, protocol, ABI and target
profile identities keep their independent versions.

## Target compiler model

```text
Semantic STRling / Simply / regex import
    -> canonical semantic representation
    -> analysis and portability planning
    -> target lowering and emission
    -> versioned target artifact
```

The implementation contains one canonical Rust compiler of semantic
meaning. Bindings are adapters that retain idiomatic public APIs,
interoperability, packaging, and error conversion without owning shadow
compilers.

Target engines are independent of host languages. New target support requires a
version-sensitive target profile, deliberate planning/lowering behavior, and an
emitter—not a new host binding.

## Current operating model

Semantic STRling, Simply and regex-compatible import converge on the canonical
Semantic IR and one normalization, analysis, planning and lowering pipeline.
CLI, LSP and editor transports delegate semantic decisions to that compiler.
All seventeen retained host routes use the same-source Rust facade or the
versioned native/WASM interop boundary. Removed shadow implementations cannot
return without failing the architecture and semantic-authority checks.

Public API compatibility and differential observations remain useful evidence,
but neither a historical implementation nor generated agreement creates
language authority. Existing target limitations and Supported/Preview scopes
remain explicit. The broader Semantic Specification draft is not ratified by
completion of the compiler implementation.

## Delivery stages

1. **Canonical semantic contracts:** define source, Semantic IR, diagnostics,
   compiler request/result, target profile, and target artifact without importing
   accidental choices from one binding.
2. **Reference compiler:** implement ratified contracts in the canonical Rust
   compiler while keeping the specification authoritative.
3. **Adapter migration:** move bindings to the stable boundary one at a time and
   retire duplicated semantics only after behavior-preservation certification.
4. **Tooling convergence:** route CLI, LSP, editors, and documentation tooling
   through the same interface.
5. **Target expansion:** add engine support through profiles, planning, lowering,
   emitters, and conformance evidence.

## Release readiness

The effective Local, Pull Request, Full and Release definitions in
`toolchain.json` determine required operations. Final certification requires
fresh source-bound Full and independent no-reuse Release evidence, reproducible
packages, isolated staged consumers, independent reconstruction, restricted
signing and trusted hosted verification. Functional resource safety is
mandatory; quantitative performance is informational.

Certification does not authorize publication. Separately authorized public
publication must be followed by real registry retrieval and consumer checks.
Staged installation and controlled registry fixtures do not establish a public
4.0.0 installation. Compatibility evidence may block readiness, but it does not
outrank the controlling specification.
