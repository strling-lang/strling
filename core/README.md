# STRling canonical compiler kernel

`core/src` contains the sole semantic compiler implementation. Versioned
contracts in `spec/` remain authoritative over this reference implementation;
agreement with generated fixtures cannot create language meaning.

The public Rust package is a same-source curated facade assembled from this
kernel. `core/internal/Cargo.toml` supports repository development and the
canonical CLI. The internal compiler-description version is independent of
the product package version 4.0.0.

## Compiler flow

Explicit source frontends select `strling.semantic@1.0.0` or
`strling.regex-compat@1.0.0`. The Semantic frontend parses the ratified DSL;
regex import preserves its frozen compatibility grammar. `simply` records a
versioned construction graph and reconstructs canonical semantic values.
All routes converge on the sole normalization and semantic pipeline.

`kernel::compile` and `compile_with_evidence` orchestrate validation,
normalization, semantic and structural analysis, safety diagnostics, factual
capability evaluation, portability planning, target lowering and artifact
serialization. Private orchestration modules prevent external callers from
substituting a second pipeline. The canonical AST and Semantic Regex IR are
versioned contracts, not binding-local compiler implementations.

PCRE2, ECMAScript and Python `re` lowering and serialization are separate
target modules. An exact target profile supplies facts; unknown or unsupported
behavior remains explicit. The kernel neither discovers a target from a host
language nor executes the target regex engine. Runtime evidence is acquired
by separately governed conformance tools.

## Additional semantic operations

Explanation, bounded no-match evidence, semantic conversion and rewrite
modules consume canonical structures and correspondence-checked evidence.
Exact conversion requires reconstruction equality. Partial, unsupported and
resource-exhausted outcomes remain explicit; neither conversion nor no-match
evidence establishes a general language-inclusion or exploitability proof.

`SimplyBuilder` implements construction protocol 1.0 and its compatible 1.1
standard-helper extension. Helpers select registered kernel meanings. Host
adapters serialize these requests; they do not implement an emitter or infer
target capabilities. Lexical-shape helpers are not complete semantic validators.

## Integration and authority

The kernel forbids unsafe Rust. Its semantic stages do not depend on filesystem
discovery, networks, editor state or host-binding implementations. Bounded CLI,
native/WASM interop, LSP and host adapters live at separate integration
boundaries and delegate to the kernel. Their allocation, loading, package and
ABI obligations require their own tests; kernel purity alone does not prove
those obligations.

See [the current architecture](../docs/architecture.md),
[contract authority](../spec/README.md), [support matrix](../docs/support-matrix.md)
and [migration guide](../docs/migration-guide.md). Architecture fitness and
semantic-authority checks reject reintroduced binding-owned compilers and
retired implementation graphs.
