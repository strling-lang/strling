# Bounded language relations review candidate

This repository-only tool proposes `strling.language-relation.review/1`.
The language relation has draft status and awaits compiler-owner acceptance.
The package is private, the tool consumes the canonical kernel, and the
published Rust facade, CLI, interop and rewrite registry have no dependency on
it. The compiler's [authority rules](../../../governance/authority.md) and
[specification hub](../../../spec/README.md) govern any promotion.

## Relation and input premises

Use two case-sensitive, validated `canonical-v1` Semantic IR programs with
contract `1.0.0` and specification identity `1.0-draft.1`. The draft label
identifies the admitted inputs. This relation interprets only the closed
projection below. All comparisons consume the whole input, which is a finite
sequence of Unicode scalar values. A canonical frontend operated by the same
kernel can produce the inputs. The owner's
[Semantic IR data contract](../../../spec/contracts/1.0/README.md#semantic-ir)
and [source mapping](../../../spec/frontends/semantic/1.0/mapping.json) are the
representation evidence.

| Canonical node | Projected whole-input language |
| --- | --- |
| `empty` | {ε} |
| `literal` | The exact scalar sequence in the literal |
| Nonnegated `character_set` with literal and inclusive range members | Union of one-scalar languages over the described ranges |
| `sequence` | Concatenation in item order |
| `alternation` | Union of branch languages for membership |
| Greedy or lazy `repeat` | Union of concatenation powers from min to max or unbounded, with power zero equal to {ε} |

The candidate refuses insensitive, complemented, builtin and Unicode-property
members, wildcard, positions, lookaround, captures, references, atomic nodes,
possessive repetition and unknown contract or specification versions. An
unsupported child remains refused even inside a repeat with maximum zero.
There is no target runtime, profile, grapheme, folding, normalization of
subject text, or engine operation in this relation.

Canonical IR has a node for the empty word. It has no node in this projection
for the empty language, and a character set must have at least one member.
An empty reachable state set represents an empty residual language as an
internal automaton fact. Disjointness can establish an empty intersection.

The queries are `equivalent` (sets equal), `contains` (left includes right),
and `disjoint` (intersection empty). On refutation, each record contains the
shortest counterexample in scalar length and membership on both sides. Search
uses increasing scalar-class representatives to choose deterministically among
equal-length words. A proven containment lets a validator author conclude that
the right program admits no new whole input relative to the left, under these
premises.

## Checkable argument and budgets

Build a Thompson ε-NFA recursively. For primitive fragments, taking the complete
path from entry to exit consumes exactly the primitive's words. Composition
connects exits to entries, or branches and rejoins on ε edges. A finite repeat
admits an exit after every legal number of body copies. An unbounded repeat
after its minimum permits another body traversal and an ε exit. This gives the
projected denotation by structural induction. ε-closure uses a visited set, so
nullable repeat cycles terminate.

Split the shared scalar alphabet at all inclusive-range endpoints, plus Unicode
scalar domain boundaries, and choose the minimum scalar in each nonempty cell.
All consuming predicates have the same membership decision for every scalar in
a cell. Induction on word length makes traversal over representatives exact.
Each reachable pair of ε-closed state sets corresponds to one word class.
Breadth-first search either finds the shortest pair whose accepting bits
contradict the query, or establishes that no reachable pair can contradict it
by closing all representative transitions. A direct finite-word denotation
evaluated from the original IR independently replays both acceptance bits
before a refutation can be returned.

The candidate serializes source bytes and canonical program digests separately,
pins the model in each result, and reports actual search work and hard limits.
It returns `invalid` on a malformed input, `unsupported` on an unmodeled
construct, and `unknown` on work, graph, search, witness or independent replay
exhaustion. A replay disagreement is `unknown` and invalidates acceptance of
that candidate run. No partial search discharges a proof.

The hard caps are 65,536 bytes per input, 1,024 NFA states per operand, 256
representative alphabet classes, 4,096 reachable state pairs, 96 witness
scalars, 8,000,000 metered traversal operations and 300,000 direct replay
operations per operand. The byte, graph and alphabet caps bound preparation.
The traversal meter charges scans of state slots and predicate intervals,
closure edges and initial seeds. State-pair growth is bounded and may still
be exponential before limits in general. A depth-limited search can refute
at its limit but cannot claim closure if a new successor lies beyond it.

## Observable boundary and draft disposition

This is analysis-only. For example, the IR languages of choices `a|ab` and
`ab|a` are equal under this projection. CPython search on `ab` can select
different spans in those orders, and replacing the selected span can yield
different text. There is no currently accepted observable-preserving
transformation family in this candidate. Moving it to a production API requires
an accepted scoped contract, independent review of the mapping and fixtures,
and certification of the intended public surface. The existing rewrite
registry is independent of this decision.

The [candidate task record](../../../docs/migration/records/bounded-language-relations-review.yaml)
is available for owner scope review. Compiler development currently selects
the historical final release candidate task. Its scope excludes this private
tool, so a normal governance run cannot clear promotion. The candidate does
not switch the active governance task. The smallest owner decision is to
review the declared relation and admit the scoped tool task. Product exposure
and certification require a separate accepted contract.

## Run the review candidate

From the repository root, with the kernel's locked dependencies available:

```sh
cargo +1.75.0 run --locked --manifest-path core/tools/language-relations/Cargo.toml -- contains --semantic before.strling after.strling
cargo +1.75.0 run --locked --manifest-path core/tools/language-relations/Cargo.toml -- equivalent --ir before.json after.json
cargo +1.75.0 test --locked --manifest-path core/tools/language-relations/Cargo.toml
```

Both operands use the selected input format. Use a complete canonical Semantic
STRling source document or the canonical Semantic IR JSON. A proof or refutation
is a JSON record. Callers must interpret the explicit status field.

See [authored expectations](fixtures.json) for independently specified source
pairs, including scalar, repeat, budget and refusal boundaries. They are
candidate evidence and have no normative conformance designation. The
[independent reference tests](src/tests.rs) exercise a second method under its
own finite envelope. The earlier research used a separate implementation and
finite alphabet. [Bounded language relation study](https://github.com/strling-lang/research-intelligence/blob/dfa8ede1e30607511fc333ad039a9898e22df972/inquiries/regex-equivalence-and-rewrite-verification/reports/bounded-language-relation-study.md)

## Candidate validation

Base source `4e58730bbf67eaff683268e285e7084ccda5fadd`. On Windows x64 and
Ubuntu WSL2 x64, six tests passed under Rust and Cargo 1.75.0 with the same
lockfile and offline dependency resolution. The authored fixture corpus
contains 17 pairs. Independent derivatives cross-checked all three queries
for every ordered pair of nine expressions, yielding 243 relation and
witness checks. A separate direct IR evaluator agreed with 360 bounded
membership queries over those expressions. Refutation replay operates on
the original IR and never invokes a target regex engine.

The existing canonical semantic frontend contract check and the narrow
kernel public contract snapshot check passed. Clippy passed for the private
candidate with warnings denied. The broad Windows contract run failed in
the Swift toolchain before it could complete. Full repository certification
and compiler owner disposition remain open. CPython 3.13.5 separately
reproduced the search span, replacement text, capture value and capture
participation differences underpinning the analysis-only disposition.

Two isolated source mutations were compiled and exercised against existing
tests. Replacing a traversal limit result with a proof failed the exhaustion
test. Reversing left containment failed the authored token-validator fixtures.
The untouched compiler `dev` baseline reproduced the CI profile-routing and
previous change-declaration failures from the default governance run. The
candidate's extra path findings came from applying the historical release
task's allowlist to this branch.

### Release-mode candidate measurements

Both artifacts came from offline locked builds using Rust 1.75.0. These are
local numbered source candidates and have no release authority.

```sh
cargo +1.75.0 build --release --offline --locked --manifest-path core/tools/language-relations/Cargo.toml
```

| Local target | Binary SHA-256 |
| --- | --- |
| Windows MSVC x64 | `e6a770d770eed0b8879e24acbfa4dc54d2aa69ea02af7beb42ca306189717942` |
| Ubuntu WSL2 GNU x64 | `19e006f0760372b3096fa44cb9e9b24733b2105ce207379fa6d6254abb5ef626` |

Use the following named cases from [the fixtures](fixtures.json). For each
operand, write UTF-8 bytes with LF line endings. Prefix
`semantic strling 1.0;\ncase sensitive;\npattern ` and append one LF. For the
80-scalar case use the same `text` literal on both sides, comprising the 80
consecutive Unicode scalar values beginning at U+0390.

| Input | Query | Answer | Pairs / transitions | Windows p50 / p95 ms | Ubuntu WSL2 p50 / p95 ms | Peak working set KiB, Windows / WSL2 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Variable bounds on a practical token validator | Contains | Proven | 9 / 90 | 33.4 / 36.8 | 159.7 / 196.4 | 6,476 / 2,832 |
| Newly admitted whole value | Contains | Refuted | 7 / 60 | 33.5 / 39.3 | 164.3 / 208.4 | 6,484 / 2,832 |
| Nullable unbounded loop closes | Equivalent | Proven | 6 / 24 | 36.9 / 41.8 | 159.3 / 203.3 | 6,456 / 2,840 |
| Maximum Unicode scalar remains in the alphabet | Disjoint | Refuted | 4 / 12 | 33.8 / 41.2 | 165.1 / 200.9 | 6,468 / 2,824 |
| 80 distinct scalar literal | Equivalent | Proven | 82 / 6,806 | 36.6 / 42.1 | 185.4 / 216.6 | 6,500 / 2,888 |

For each row, run the release-mode binary with
`<query> --semantic <left-file> <right-file>`. Make one preliminary run and
measure 30 fresh processes per row with a monotonic clock. The p95 is the
29th ordered sample. Peak working set is the maximum of
`GetProcessMemoryInfo`'s `PeakWorkingSetSize` on Windows and GNU
`/usr/bin/time -f %M` on WSL2. Timings include startup, I/O, canonical parsing,
comparison and report emission. The measurements cover Windows 11 build
26300 and Ubuntu WSL2 kernel 5.15.167.4, with the WSL2 binary on the mounted
Windows drive. A preliminary timing-only pass showed a higher Windows p95
for the token validator. These observations establish the tested cases and
deterministic caps rather than a platform-wide latency or memory guarantee.
[Microsoft working set counter](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters)

The five deterministic JSON records were identical between platforms after
key sorting. Their SHA-256 digests, in table order, are
`2fa38b8a793b0e6d67ea59671238e5d0c5103cdc9e3ffa3c4dedef9d02091901`,
`0b26cf281cb35f1e7fd43d635433a6f22eea5babea3944658d41c1ad4d42905d`,
`44359e8b5f284d262019fc42b3d647502b7361dc2bd7c04adce9787562911eca`,
`d1f1ea81e0263e0fb273e6997c16a7a354d6179a8f0242b682e07f0be7560c8e`,
and `63e08586935db59296abf8802d922937a6f2b9e297bacd86cca9ceca57d7c052`.
For hashing, serialize the parsed report with Python
`json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"))`
and encode it as UTF-8 without a final newline.
