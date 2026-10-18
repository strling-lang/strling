# Test Design — bounded semantic identity streaming

## Purpose

Prevent a product identity-hashing optimization from changing the exact Serde
JSON byte stream, SHA-256 identity, error propagation, or bounded storage.
The controlling contracts are `spec/contracts/1.0/README.md` and
`spec/contracts/1.0/PROTOCOL.md`; timing observations do not define semantics.

## Description and scope

Exercise `core/src/validation/mod.rs` through its existing digest tests and
the direct semantic-analysis dependents. The writer retains its 512-byte
buffer and uses a short-write-free `write_all` fast path when bytes fit.
No cache, alternate digest, elided validation, performance baseline,
measurement threshold, sample count, or certification rule is introduced.

Private consumption/capture indexes may borrow immutable input identities
instead of cloning them. Public `SemanticFacts`, capture definitions and
backreference records remain fully owned, deterministically ordered and
usable after the analyzed input is dropped.

## Categories of tests

-   Positive: compare all output bytes with independent `serde_json::to_vec`
    followed by `sha2::Sha256::digest`, including canonical semantic fixtures
    and the five governed target-profile fingerprints.
-   Negative: serialization refusal before and after a valid large prefix must
    return the original error and never a successful prefix digest.
-   Edges: empty writes, exact full buffers, mixed `write`/`write_all`, explicit
    repeated flushes, arbitrary byte values, Unicode and JSON escaping, and
    chunks smaller than, equal to, and larger than 512 bytes.
-   Interactions: retain semantic-analysis, capture, consumption, normalization,
    structural, safety, capability, portability, and correspondence invariants;
    input data and fact ordering remain unchanged.
-   Ownership: analyze a scoped capture/reference program, drop its input, and
    prove the returned owned facts and logical identities still equal analysis
    of an independently reconstructed identical program.

## Completion criteria

All focused digest tests and affected semantic suites pass repeatedly with
the pinned toolchain. A separate bounded, non-authoritative atomic product
diagnostic retains every timing round and verifies exact fixture/digest
agreement; it creates no authenticated samples or authoritative profile result.
Registered generated families are checked and refreshed only through their
specific governance before a new candidate can be frozen. Component regressions
and atomic diagnostics never substitute for authoritative certification.
