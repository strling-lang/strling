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

## Serialized access extension

The existing ledger requires exclusive mutable access but does not itself guard
allocator callbacks against reentrancy or concurrent callers. Add an optional
allocation-free, no-std wrapper with an atomic exclusive-entry state. It must
never expose the underlying ledger, wait, spin, or allocate on entry. A racing or
recursive entry is a terminal acquisition failure, not silently dropped work.
After such an entry, native failure, or unwinding panic, the wrapper is permanently
poisoned. An already-running bounded operation may finish its native callbacks,
but must not publish a successful token or release after concurrent poisoning.
No rollback or speculative unlock is allowed. This conservative wrapper does not
claim to provide a generally usable multithreaded global allocator.

Deterministic tests must cover sequential overlapping lifetimes, a recursive
callback that attempts another acquisition, a callback that tries to release an
earlier token, coordinated two-thread contention without timing sleeps, callback
panic, and native failure. Assert no nested callbacks, no false successful outer
completion, permanent poison and preservation of existing raw native errors.
Compile the same implementation as a Rust 1.75 no-std library and test on Native
and WSL. No live page-lock challenge or consumed product measurement is repeated.

The wrapper does not protect its own storage, callback code, allocator bootstrap,
stack growth, loaded images, other allocation routes, threads or descendants.
Those lifetime sources and observer effects still require separate coverage and
qualification before product integration. Admission and all ceilings/counts stay
unchanged.

## Completion boundary

Passing proves only finite lifetime bookkeeping and the declared owned-page
challenge. It does not prove whole-process coverage, freedom from constraints,
observer-effect neutrality, or lossless product admission. No RSS substitution,
ceiling/sample-count change, reference fitting or speedup claim is permitted.
Complete source-reviewed allocation/free/reuse/image/stack/descendant coverage,
fresh independent qualification, all conditioning obligations and immutable
trusted verification remain required before any product integration/promotion.
