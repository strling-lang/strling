# Test Design — bounded governance pattern compilation

Governance path syntax and findings remain authoritative as currently implemented
in `tooling/governance.py`. Cache only the pure translation from an immutable
pattern string to an immutable regular expression. Keep the cache bounded to512
entries. Never cache concrete-path validation, file discovery/content, Git state,
rule findings, exemptions, profile results or certification evidence.

Verify exact case-sensitive directory-aware matching against explicit examples,
including recursive paths, character classes, literals and invalid patterns.
Repeated invalid patterns must still fail and must not populate the cache.
Unsafe concrete paths must be rejected even with a warm pattern entry. Verify
that eviction causes recomputation with unchanged results and that clearing the
cache does not alter behavior. Run existing governance and contract tests as
direct dependents.

Profile the actual governance gate before changing it. Compare fresh subprocess
runs on identical held repository inputs with only this pure cache enabled or
disabled, using a fixed uncached/cached/cached/uncached order. Require complete
JSON output equality, successful status, every check and architecture rule, and
unchanged source bytes. Preserve raw timings and outputs. Profiler overhead is
diagnostic; this comparison measures only governance execution, not authoritative
product performance or total certification time. No required checks are omitted.
