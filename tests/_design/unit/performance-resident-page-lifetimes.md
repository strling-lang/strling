# Test Design — bounded resident-page lifetime ownership

## Authority and scope

The [VirtualLock contract](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtuallock)
has no per-page lock count. Multiple live allocations can share one page;
unlocking on every allocation release would remove another allocation's lock.
[VirtualUnlock](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualunlock)
also affects every page touched by the byte range, and must not be used as a
speculative cleanup operation on pages whose lock state is unknown.

Implement an allocation-free, fixed-capacity ownership primitive, not a global
allocator or live performance guard. Independently issued monotonic lifetime
tokens cover nonempty half-open byte ranges. Count overlapping page ownership;
lock a page only for its first owner and unlock only after its last owner.
Reacquiring a released address needs a new token and a fresh lock. Initial census,
image, stack and heap coverage can overlap, but this primitive cannot establish
that any of those sources are complete or that the caller reports every event.

## Fail-closed contract

-   Validate ranges, arithmetic, free lifetime/page slots and reference counts
    before invoking an operation. Reject null, empty and overflowing ranges.
-   Any invalid event, exhausted capacity, token exhaustion or native failure
    permanently poisons the instance. Subsequent calls cannot invoke operations
    or recover an admissible history. A failed lock may have unknown side effects;
    never attempt speculative unlock/rollback or retry to obtain success.
-   Require exclusive mutable access. This is not synchronization for a global
    allocator; callers must prevent reentrancy and serialize events without
    allocating through the allocator being observed. Primitive storage itself,
    callback code, stacks, images, other threads and descendants remain uncovered.
-   Release must occur while the underlying range is still committed, before
    deallocation/reuse, with all owners in the same ledger. Reject stale or unknown
    tokens. Native errors, including their page and raw error code, are retained.

## Prospective checks

Run integrated artifact integrity first. Build the primitive with Rust 1.75 as
a no-std library, then run deterministic Native and WSL unit tests. Exercise
same-page aliases, partial overlap, crossing page boundaries, last-owner release,
address reuse, stale release, capacity, integer edges, native lock/unlock failure,
partial-progress poison, and all bounded acquire/release histories against an
independent live-range union oracle. No product measurement is executed.

One new standalone Windows fixture compares a naive double-lock/single-unlock
counterexample on one owned page with the ledger on another newly owned page.
Observe raw working-set flags, then explicitly trim only the fixture process
while a ledger-owned page remains live. Require that page to remain resident and
locked; releasing its final token must unlock, and address reuse must relock.
Record every native operation, error, page flag and exact counts. Each fixture
executes once; a failed attempt is retained, never rerun unchanged for green.
All pages and the owned process retire. Do not enable privileges or change jobs,
other applications, system security, power, or workstation configuration.

## Completion boundary

Passing proves only finite lifetime bookkeeping and the declared owned-page
challenge. It does not prove whole-process coverage, freedom from constraints,
observer-effect neutrality, or lossless product admission. No RSS substitution,
ceiling/sample-count change, reference fitting or speedup claim is permitted.
Complete source-reviewed allocation/free/reuse/image/stack/descendant coverage,
fresh independent qualification, all conditioning obligations and immutable
trusted verification remain required before any product integration/promotion.
