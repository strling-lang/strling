# Test Design — pinned observer-storage lifetime

## Scope and authority

Extend the bounded resident-page ownership primitive with a one-shot storage
session. Before any client lifetime is admitted, acquire ownership of every page
touched by the complete ledger object at its final address. Use Rust `Pin` and
`PhantomPinned` to keep that address stable until destruction. The session must
borrow its backing object, expose no inner ledger, and conceal its anchor token.
Address stability is not itself native residency: `PageOps` must supply the
separately qualified lock/unlock implementation.

This remains an unqualified mechanism, with no product integration or metric
change. Session handles, callbacks, caller stacks, images, allocator routes,
other threads and descendants remain outside this storage-only scope. The
bootstrap's work before successful locking is outside any measurement interval.
No claim of continuous whole-process coverage or observer neutrality is allowed.

## Failure and retirement contract

-   Start at most once per backing object. Failure cannot reopen initialization.
-   Native acquisition must cover the entire object, including bookkeeping and
    synchronization state, without dynamic allocation by the implementation.
-   Session allocation/free operations use the same page-owner ledger, so data
    overlapping the backing object's page cannot unlock that page early.
-   Reject an attempt to release the concealed storage token without callbacks.
-   Successful finish requires exactly the storage lifetime to remain. Reject
    outstanding client lifetimes before unlocking anything; do not silently
    discard obligations or normalize them into success.
-   Dropping a session without successful finish permanently poisons it and
    performs no speculative native unlock. Native error and panic remain terminal.
    Failed native ownership is retired by the containing process, not guessed
    cleanup in this primitive.

## Prospective deterministic checks

After integrated artifact integrity, demonstrate the missing implementation;
then test complete byte-to-page storage coverage, overlap with storage, explicit
finish, outstanding allocation rejection, concealed-token rejection, abandoned
session poison and capacity failure before callbacks. Use independent page-set
expectations. Include a negative compilation example proving safe code cannot
move the borrowed pinned backing object while the session is used afterward.
Compile as Rust 1.75 no-std on Native and WSL, and run the existing serialization
tests as direct dependents. No consumed native page challenge, reference cohort
or manual diagnostic runs. No timing comparison or speedup claim is implied.
