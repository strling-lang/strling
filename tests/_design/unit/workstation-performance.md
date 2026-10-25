# Test Design — Shared-workstation performance certification

The owner-authorized policy is `governance/workstation-performance-policy.json`.
It supersedes laboratory isolation prerequisites only for its explicitly named
context. The existing default laboratory worker and historical results retain
their meaning. An unknown ancestor quota stays unknown in every new raw report.

The actual runner and actual memory worker accept an explicit versioned context.
Unknown context values and a context mismatch between parent and child fail.
Legacy invocation must still reject unknown ancestry. All affinity, CPU-set,
HighQoS, semantic and transport errors remain failures in either context.

The memory parent retains the child while suspended, installs an owned private
one-process job, and retains both kernel high-water RSS and peak commit after
natural exit. Startup, native/Rust allocation, parsing, warmup, threads and
teardown contribute to those kernel counters. No observer-byte subtraction,
residency fiction or sampled peak is allowed. A child-creation attempt, surviving
member, limit termination, changed identity or zero/regressed counter fails.
Challenge native allocation/free churn and explicit working-set trimming: peak
commit must retain the allocated memory even when current RSS falls. A workload
above the prospective 64MiB ceiling must fail the memory policy. The existing
resident-allocation audit remains a separate, ineligible experiment.

Build frozen reference and candidate kernels independently with identical pinned
harness code. Record the mixed-source recipe honestly. Acquire nine adjacent
pairs in the policy's fixed alternating order, never choose the best attempt or
refit bounds. Revision 2 retains exactly 64 latency slots and one measured
memory compilation, with no replacements or discarded attempts. Scheduling
interference and product stalls remain measured. Preserve every raw byte and failure. Missing,
reused, reordered or forged observations fail independent reconstruction.

The median of nine pair ratios must not exceed the fixed 10% regression margin;
at least seven pairs must fit the fixed 25% pair margin. Test exact boundaries,
large integer arithmetic, two isolated large interference spikes, three bad
pairs, sustained 20% regressions and order drift. An injected slowdown in an
actual compiler measurement must fail while an independently built equivalent
candidate passes. Memory uses every observed peak commit, its fixed absolute
ceiling and its separate relative-plus-fixed allowance; RSS remains visible.

Nearest-rank p95 and whole-process pair ratios have a 25% median margin and a
50% per-pair margin, requiring seven of nine passing pairs. Intermittent stalls
with an unchanged median must fail the tail guard; startup/warmup-only delay
must fail the whole-process guard. Two transient bad pairs remain allowed;
three fail. Guard both CLI request and control marginals, retaining paired
ratios so common-mode slowdown cannot cancel from all guards. Independently
reconstruct CPU normalization, all fixed slots and child lifetime identity;
refreshing inner hashes must not make malformed evidence pass. The executor
and native APIs are trusted observations, with no hardware-attestation claim.

CLI retains 64 paired request/control samples but uses eight launch warmups in
this policy, avoiding hundreds of unrelated process launches per repetition.
In-process operations retain 512 warmups and 64 samples. Include all 54 governed
coordinates and five functional resource groups before adoption. Component or
synthetic tests alone do not constitute the native qualification campaign.

Process exit must precede terminal memory collection. A private job may still
report its one exited member briefly; allow at most five seconds of bookkeeping
observation after exact-child exit. Never repeat work or accept an extra member,
limit termination, incomplete accounting or a surviving member at the deadline.
Preserve exact counts in failures. Test delayed retirement, native-query failure,
invalid counts, deadline expiry and 128 fresh fast-child exits without replacement.

Formal cohorts use version 3 and bind the exact profile invocation in a canonical
input file written before acquisition. Reconstruct every command, all eight input
pins, complete source archives, mixed-source build recipes and raw streams from
verifier-owned code. Local and PR remain deterministic contract/resource checks;
Full and independent Release each require fresh complete acquisitions. Reject
invocation, build-root, root-process and memory-child reuse across profiles.
Include the observed hidden console host in outer-job accounting: two members
for in-process roots, three for memory roots and 146 for each fixed CLI root.
The memory child's separate private job must still retire exactly one process.
Exercise explicit main-module routing and controlled errors, malformed archives,
source-role substitutions, missing slots, invocation replacement and rehashed
metadata attacks. Candidate source is data for the trusted consumer.

Use a lossless bounded capsule for the complete profile payload. Require exact
compressed and expanded sizes and SHA-256 pins, a closed encoding contract,
strict JSON, complete decompression and no trailing or concatenated stream.
Reject forged sizes, expansion beyond 256MiB, corrupt/truncated streams and
rehashed duplicate/nonfinite documents before accepting evidence. Round-trip
all original raw bytes and exact integers. Source ZIP entries must preserve
their original names; reject platform-normalized names, traversal, absolute
paths, links, duplicates and excessive member/expansion counts.
