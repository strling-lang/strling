# Test Design — Certification memory worker lifetime

The governed metric remains process peak RSS. A worker self-report taken before
serialization cannot cover reporting, destructors or process teardown. Retain the
exact child's kernel handle before its initial thread resumes, record its birth,
and read the original kernel peak after that process exits. Never subtract
observer memory or use commit, a sampled maximum, or a page union as RSS.

Tests must reject live-process finalization, changed identities, zero or regressed
peaks, malformed native replies and failed queries. A native child exercises Rust
and native allocations, another thread and allocation after its preliminary
report. Its retained terminal peak must include that later work. Observer state
lives in the parent. No quota query result is transferred between processes.

The actual worker also has a separately identified residency-audit build. Its
global allocator must intercept allocations before argument/input parsing,
warmup and compiler execution; registration and retirement use the existing
serialized page ledger. Reallocation must keep the old allocation protected
until the replacement is copied and registered. No callback allocates metadata.
Allocation failure, lock failure, capacity exhaustion, reentry and contention
are terminal; unregistered pointers must never be returned as success.

System's allocator returns a pointer or null without an error code. A null
allocation must retain an explicitly unknown cause (allocation failure code
zero), independent of unrelated thread-local Windows last-error values. Native
lock and unlock failures still retain their documented Windows error codes.
Test the production pointer conversion with distinct last-error markers and
both null and non-null pointers; it must preserve the thread's last-error value.

Positive and negative native tests exercise the integrated allocator and the
actual worker's compiler path. The audit build cannot supply authoritative
evidence: native allocator bypasses, loader/bootstrap, images, stack growth,
descendants, observer effects and inherited control provenance require independent
qualification. The original acceptance policy, counts, ceilings and failed
attempts remain unchanged. A blocked actual launch is retained as a failure,
never replaced with a test process's favorable environment.

Raw nested stream evidence must preserve requested input and every returned
stdout/stderr byte, including malformed UTF-8 and NULs. Independent reconstruction
requires a unique closed packet, exact child identity/placement/peak agreement,
containment within the retained parent lifetime and no repeated child identity
across memory cohort observations. A reused child under different parent receipts
must fail even when every nested hash has been refreshed. Failed transport with
incomplete output remains failed; it cannot fill a successful cohort slot.
