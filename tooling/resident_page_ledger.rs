//! Bounded lifetime bookkeeping, not process coverage or certification admission.
//! Callers must serialize all owners, prevent reentrancy, and release before free.
//! This primitive allocates no storage; native callbacks must not reenter it.

use core::cell::UnsafeCell;
use core::sync::atomic::{AtomicU8, Ordering};

pub const PAGE_BYTES: usize = 4096;

pub trait PageOps {
    fn lock(&mut self, page: usize) -> Result<(), u32>;
    fn unlock(&mut self, page: usize) -> Result<(), u32>;
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Failure {
    Poisoned,
    ConcurrentOrReentrant,
    LiveLifetimes,
    InvalidRange,
    Capacity,
    TokenExhausted,
    UnknownToken,
    ReferenceOverflow,
    Lock { page: usize, code: u32 },
    Unlock { page: usize, code: u32 },
    Retirement { code: u32 },
    Allocation { code: u32 },
}

#[derive(Clone, Copy)]
struct Lifetime {
    token: u64,
    first: usize,
    last: usize,
}

#[derive(Clone, Copy)]
struct Page {
    address: usize,
    owners: usize,
}

pub struct Ledger<const L: usize, const P: usize> {
    lifetimes: [Lifetime; L],
    pages: [Page; P],
    last_token: u64,
    poisoned: bool,
}

const READY: u8 = 0;
const BUSY: u8 = 1;
const POISONED: u8 = 2;

/// Optional bounded exclusive-entry wrapper, not a global allocator or coverage
/// proof. Contention is terminal: no spin, waiting, allocation or dropped event.
/// Native callbacks may finish an in-flight bounded operation after poison, but
/// it cannot publish success. Caller must retire the failed acquisition context.
pub struct SerializedLedger<const L: usize, const P: usize> {
    state: AtomicU8,
    ledger: UnsafeCell<Ledger<L, P>>,
}

// SAFETY: Only the successful READY -> BUSY owner dereferences the UnsafeCell.
// It holds Entry through all callbacks and mutation. No inner reference escapes.
// Release publishes mutation before another Acquire can obtain the cell. A
// competing/reentrant entry only accesses the atomic and poisons permanently;
// it never touches the cell, including while an earlier callback is in flight.
unsafe impl<const L: usize, const P: usize> Sync for SerializedLedger<L, P> {}

struct Entry<'a> {
    state: &'a AtomicU8,
    finished: bool,
}

impl Entry<'_> {
    fn complete<T>(mut self, result: Result<T, Failure>) -> Result<T, Failure> {
        if result.is_err() {
            self.state.store(POISONED, Ordering::Release);
            self.finished = true;
            return result;
        }
        // A callback can ignore a nested rejection. Never turn its outer
        // operation into success, or reset poison written by a racing thread.
        let publish = self
            .state
            .compare_exchange(BUSY, READY, Ordering::Release, Ordering::Relaxed)
            .is_ok();
        self.finished = true;
        if publish {
            result
        } else {
            Err(Failure::Poisoned)
        }
    }
}

impl Drop for Entry<'_> {
    fn drop(&mut self) {
        if !self.finished {
            // Includes a callback panic. Never unlock or restore uncertain state.
            self.state.store(POISONED, Ordering::Release);
        }
    }
}

impl<const L: usize, const P: usize> Default for SerializedLedger<L, P> {
    fn default() -> Self {
        Self::new()
    }
}

impl<const L: usize, const P: usize> SerializedLedger<L, P> {
    pub const fn new() -> Self {
        Self {
            state: AtomicU8::new(READY),
            ledger: UnsafeCell::new(Ledger::new()),
        }
    }

    pub fn is_poisoned(&self) -> bool {
        self.state.load(Ordering::Acquire) == POISONED
    }

    /// Abandon an incomplete acquisition without guessing native cleanup.
    pub fn invalidate(&self) {
        self.state.store(POISONED, Ordering::Release);
    }

    fn enter(&self) -> Result<Entry<'_>, Failure> {
        match self
            .state
            .compare_exchange(READY, BUSY, Ordering::Acquire, Ordering::Acquire)
        {
            Ok(_) => Ok(Entry {
                state: &self.state,
                finished: false,
            }),
            Err(POISONED) => Err(Failure::Poisoned),
            Err(_) => {
                self.state.store(POISONED, Ordering::Release);
                Err(Failure::ConcurrentOrReentrant)
            }
        }
    }

    pub fn acquire(
        &self,
        address: usize,
        bytes: usize,
        ops: &mut impl PageOps,
    ) -> Result<u64, Failure> {
        let entry = self.enter()?;
        // SAFETY: Entry owns exclusive access until complete/drop; no reference
        // to this cell is returned, and recursive entry cannot obtain an Entry.
        let result = unsafe { &mut *self.ledger.get() }.acquire(address, bytes, ops);
        entry.complete(result)
    }

    pub fn release(&self, token: u64, ops: &mut impl PageOps) -> Result<(), Failure> {
        let entry = self.enter()?;
        // SAFETY: Same exclusive-entry invariant as acquire.
        let result = unsafe { &mut *self.ledger.get() }.release(token, ops);
        entry.complete(result)
    }

    /// Hold entry across bounded allocation and page registration; return
    /// (token, address) only after both succeed. The caller must allocate bytes
    /// and satisfy alignment. This does not protect pages during allocation or
    /// establish allocator coverage. On failure, retire the enclosing context:
    /// an allocation may exist, and native ownership may be only partial.
    pub fn allocate(
        &self,
        bytes: usize,
        ops: &mut impl PageOps,
        allocate_memory: impl FnOnce() -> Result<usize, u32>,
    ) -> Result<(u64, usize), Failure> {
        let entry = self.enter()?;
        // SAFETY: Entry exclusively owns the cell. The preflight borrow ends
        // before the allocator callback, which cannot reenter successfully.
        let preflight = unsafe { &mut *self.ledger.get() }.preflight_allocation(bytes);
        let result = preflight.and_then(|()| {
            let address = allocate_memory().map_err(|code| Failure::Allocation { code })?;
            if self.is_poisoned() {
                return Err(Failure::Poisoned);
            }
            // SAFETY: The same Entry still owns the cell through page callbacks.
            let token = unsafe { &mut *self.ledger.get() }.acquire(address, bytes, ops)?;
            Ok((token, address))
        });
        // Contention after the poison check still prevents publishing success.
        entry.complete(result)
    }

    /// Keep exclusive ownership through a caller's bounded deallocation.
    /// The caller must free exactly the allocation identified by token, without
    /// invalidating pages shared by other lifetimes. This is not allocator
    /// coverage: callbacks, their storage and native behavior need qualification.
    pub fn retire(
        &self,
        token: u64,
        ops: &mut impl PageOps,
        release_allocation: impl FnOnce() -> Result<(), u32>,
    ) -> Result<(), Failure> {
        let entry = self.enter()?;
        // SAFETY: Entry owns the cell. Its temporary borrow ends before the
        // deallocation callback; Entry remains held through that callback.
        let released = unsafe { &mut *self.ledger.get() }.release(token, ops);
        let result = match released {
            Err(error) => Err(error),
            Ok(()) if self.is_poisoned() => Err(Failure::Poisoned),
            Ok(()) => release_allocation().map_err(|code| Failure::Retirement { code }),
        };
        // A racing rejection can occur after the poison check or during free.
        // The callback may finish, but complete must never publish success.
        entry.complete(result)
    }

    /// A storage anchor can retire only after every client lifetime has retired.
    pub fn release_last(&self, token: u64, ops: &mut impl PageOps) -> Result<(), Failure> {
        let entry = self.enter()?;
        // SAFETY: Entry exclusively owns the cell through validation/callbacks.
        let ledger = unsafe { &mut *self.ledger.get() };
        let result = if ledger.live_lifetimes() != 1 {
            ledger.fail(Failure::LiveLifetimes)
        } else {
            ledger.release(token, ops)
        };
        entry.complete(result)
    }
}

impl<const L: usize, const P: usize> Default for Ledger<L, P> {
    fn default() -> Self {
        Self::new()
    }
}

impl<const L: usize, const P: usize> Ledger<L, P> {
    pub const fn new() -> Self {
        Self {
            lifetimes: [Lifetime {
                token: 0,
                first: 0,
                last: 0,
            }; L],
            pages: [Page {
                address: 0,
                owners: 0,
            }; P],
            last_token: 0,
            poisoned: false,
        }
    }

    pub fn is_poisoned(&self) -> bool {
        self.poisoned
    }

    pub fn live_lifetimes(&self) -> usize {
        self.lifetimes.iter().filter(|v| v.token != 0).count()
    }

    pub fn live_pages(&self) -> usize {
        self.pages.iter().filter(|v| v.owners != 0).count()
    }

    fn fail<T>(&mut self, error: Failure) -> Result<T, Failure> {
        self.poisoned = true;
        Err(error)
    }

    fn page_index(&self, address: usize) -> Option<usize> {
        self.pages
            .iter()
            .position(|p| p.owners != 0 && p.address == address)
    }

    fn preflight_allocation(&mut self, bytes: usize) -> Result<(), Failure> {
        if self.poisoned {
            return Err(Failure::Poisoned);
        }
        if bytes == 0 {
            return self.fail(Failure::InvalidRange);
        }
        // This lower bound cannot reject a range that would fit. Exact page
        // overlap and alignment are checked after the address is known.
        if (bytes - 1) / PAGE_BYTES + 1 > P || self.live_lifetimes() == L {
            return self.fail(Failure::Capacity);
        }
        if self.last_token == u64::MAX {
            return self.fail(Failure::TokenExhausted);
        }
        Ok(())
    }

    pub fn acquire(
        &mut self,
        address: usize,
        bytes: usize,
        ops: &mut impl PageOps,
    ) -> Result<u64, Failure> {
        if self.poisoned {
            return Err(Failure::Poisoned);
        }
        let last_byte = match bytes.checked_sub(1).and_then(|n| address.checked_add(n)) {
            Some(last) if address != 0 => last,
            _ => return self.fail(Failure::InvalidRange),
        };
        let first = address & !(PAGE_BYTES - 1);
        let last = last_byte & !(PAGE_BYTES - 1);
        let count = (last - first) / PAGE_BYTES + 1;
        let slot = match self.lifetimes.iter().position(|v| v.token == 0) {
            Some(slot) if count <= P => slot,
            _ => return self.fail(Failure::Capacity),
        };
        let token = match self.last_token.checked_add(1) {
            Some(token) => token,
            None => return self.fail(Failure::TokenExhausted),
        };
        let mut needed = 0;
        for offset in 0..count {
            let page = first + offset * PAGE_BYTES;
            if let Some(index) = self.page_index(page) {
                if self.pages[index].owners == usize::MAX {
                    return self.fail(Failure::ReferenceOverflow);
                }
            } else {
                needed += 1;
            }
        }
        if needed > P - self.live_pages() {
            return self.fail(Failure::Capacity);
        }
        // Preflight is complete. Any partial native failure poisons permanently;
        // no rollback may unlock a page whose actual native state is unknown.
        for offset in 0..count {
            let page = first + offset * PAGE_BYTES;
            if let Some(index) = self.page_index(page) {
                self.pages[index].owners += 1;
            } else {
                if let Err(code) = ops.lock(page) {
                    return self.fail(Failure::Lock { page, code });
                }
                let index = self.pages.iter().position(|p| p.owners == 0).unwrap();
                self.pages[index] = Page {
                    address: page,
                    owners: 1,
                };
            }
        }
        self.lifetimes[slot] = Lifetime { token, first, last };
        self.last_token = token;
        Ok(token)
    }

    pub fn release(&mut self, token: u64, ops: &mut impl PageOps) -> Result<(), Failure> {
        if self.poisoned {
            return Err(Failure::Poisoned);
        }
        let slot = match self
            .lifetimes
            .iter()
            .position(|v| token != 0 && v.token == token)
        {
            Some(slot) => slot,
            None => return self.fail(Failure::UnknownToken),
        };
        let lifetime = self.lifetimes[slot];
        let count = (lifetime.last - lifetime.first) / PAGE_BYTES + 1;
        for offset in 0..count {
            let page = lifetime.first + offset * PAGE_BYTES;
            let index = self.page_index(page).unwrap();
            if self.pages[index].owners == 1 {
                if let Err(code) = ops.unlock(page) {
                    return self.fail(Failure::Unlock { page, code });
                }
            }
            self.pages[index].owners -= 1;
        }
        self.lifetimes[slot].token = 0;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    #[derive(Default, Clone)]
    struct Mock {
        locked: BTreeSet<usize>,
        calls: Vec<(bool, usize)>,
        fail_on: Option<(bool, usize)>,
    }
    impl PageOps for Mock {
        fn lock(&mut self, page: usize) -> Result<(), u32> {
            self.calls.push((true, page));
            if self.fail_on == Some((true, page)) {
                return Err(1453);
            }
            assert!(self.locked.insert(page), "duplicate native lock");
            Ok(())
        }
        fn unlock(&mut self, page: usize) -> Result<(), u32> {
            self.calls.push((false, page));
            if self.fail_on == Some((false, page)) {
                return Err(158);
            }
            assert!(self.locked.remove(&page), "unlock without native ownership");
            Ok(())
        }
    }

    #[test]
    fn shared_page_releases_only_the_last_owner() {
        let (mut ledger, mut ops) = (Ledger::<4, 4>::new(), Mock::default());
        let a = ledger.acquire(4096, 8, &mut ops).unwrap();
        let b = ledger.acquire(4104, 8, &mut ops).unwrap();
        ledger.release(a, &mut ops).unwrap();
        assert_eq!(ops.calls, [(true, 4096)]);
        assert_eq!(ledger.live_pages(), 1);
        ledger.release(b, &mut ops).unwrap();
        assert_eq!(ops.calls, [(true, 4096), (false, 4096)]);
        assert_eq!(ledger.live_lifetimes(), 0);
    }

    #[test]
    fn crossing_and_overlapping_ranges_keep_exact_pages() {
        let (mut ledger, mut ops) = (Ledger::<4, 4>::new(), Mock::default());
        let a = ledger.acquire(8191, 2, &mut ops).unwrap();
        let b = ledger.acquire(8192, 4097, &mut ops).unwrap();
        ledger.release(a, &mut ops).unwrap();
        assert_eq!(ops.locked, BTreeSet::from([8192, 12288]));
        ledger.release(b, &mut ops).unwrap();
        assert!(ops.locked.is_empty());
    }

    #[test]
    fn address_reuse_requires_a_new_lock_and_token() {
        let (mut ledger, mut ops) = (Ledger::<1, 1>::new(), Mock::default());
        let a = ledger.acquire(4096, 4096, &mut ops).unwrap();
        ledger.release(a, &mut ops).unwrap();
        let b = ledger.acquire(4096, 4096, &mut ops).unwrap();
        assert_ne!(a, b);
        assert_eq!(ops.calls, [(true, 4096), (false, 4096), (true, 4096)]);
        assert_eq!(ledger.release(a, &mut ops), Err(Failure::UnknownToken));
        assert_eq!(ledger.release(b, &mut ops), Err(Failure::Poisoned));
        assert_eq!(ops.calls.len(), 3);
    }

    #[test]
    fn invalid_ranges_fail_before_callbacks() {
        for (address, bytes) in [(0, 1), (4096, 0), (usize::MAX, 2), (4096, usize::MAX)] {
            let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
            assert_eq!(
                ledger.acquire(address, bytes, &mut ops),
                Err(Failure::InvalidRange)
            );
            assert!(ops.calls.is_empty());
            assert!(ledger.is_poisoned());
        }
    }

    #[test]
    fn last_byte_of_address_space_does_not_wrap() {
        let (mut ledger, mut ops) = (Ledger::<1, 1>::new(), Mock::default());
        let token = ledger.acquire(usize::MAX, 1, &mut ops).unwrap();
        assert_eq!(ops.calls, [(true, usize::MAX & !4095)]);
        ledger.release(token, &mut ops).unwrap();
    }

    #[test]
    fn page_and_lifetime_capacity_fail_before_new_callbacks() {
        let (mut ledger, mut ops) = (Ledger::<2, 1>::new(), Mock::default());
        ledger.acquire(4096, 1, &mut ops).unwrap();
        assert_eq!(ledger.acquire(8192, 1, &mut ops), Err(Failure::Capacity));
        assert_eq!(ops.calls, [(true, 4096)]);
        let (mut ledger, mut ops) = (Ledger::<1, 2>::new(), Mock::default());
        ledger.acquire(4096, 1, &mut ops).unwrap();
        assert_eq!(ledger.acquire(4097, 1, &mut ops), Err(Failure::Capacity));
        assert_eq!(ops.calls, [(true, 4096)]);
        let (mut ledger, mut ops) = (Ledger::<0, 0>::new(), Mock::default());
        assert_eq!(ledger.acquire(4096, 1, &mut ops), Err(Failure::Capacity));
        assert!(ops.calls.is_empty());
    }

    #[test]
    fn huge_valid_range_is_bounded_before_enumeration() {
        let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
        assert_eq!(
            ledger.acquire(1, usize::MAX, &mut ops),
            Err(Failure::Capacity)
        );
        assert!(ops.calls.is_empty());
    }

    #[test]
    fn token_and_reference_overflow_poison_before_callbacks() {
        let serialized = SerializedLedger::<2, 2>::new();
        // SAFETY: This private fixture has no outstanding entry or references.
        unsafe { &mut *serialized.ledger.get() }.last_token = u64::MAX;
        let mut callbacks = Mock::default();
        assert_eq!(
            serialized.allocate(8, &mut callbacks, || panic!("exhausted token")),
            Err(Failure::TokenExhausted)
        );
        assert!(callbacks.calls.is_empty());
        assert!(serialized.is_poisoned());
        let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
        ledger.last_token = u64::MAX;
        assert_eq!(
            ledger.acquire(4096, 1, &mut ops),
            Err(Failure::TokenExhausted)
        );
        assert!(ops.calls.is_empty());
        let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
        ledger.acquire(4096, 1, &mut ops).unwrap();
        ledger.pages[0].owners = usize::MAX;
        assert_eq!(
            ledger.acquire(4097, 1, &mut ops),
            Err(Failure::ReferenceOverflow)
        );
        assert_eq!(ops.calls.len(), 1);
    }

    #[test]
    fn unknown_or_repeated_release_never_unlocks() {
        for token in [0, 1, u64::MAX] {
            let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
            assert_eq!(ledger.release(token, &mut ops), Err(Failure::UnknownToken));
            assert!(ops.calls.is_empty());
        }
    }

    #[test]
    fn partial_native_lock_failure_is_terminal_without_rollback() {
        let (mut ledger, mut ops) = (Ledger::<4, 4>::new(), Mock::default());
        let a = ledger.acquire(4096, 1, &mut ops).unwrap();
        ops.fail_on = Some((true, 12288));
        assert_eq!(
            ledger.acquire(4096, 12288, &mut ops),
            Err(Failure::Lock {
                page: 12288,
                code: 1453
            })
        );
        assert_eq!(ops.calls, [(true, 4096), (true, 8192), (true, 12288)]);
        assert_eq!(ledger.release(a, &mut ops), Err(Failure::Poisoned));
        assert_eq!(ledger.acquire(16384, 1, &mut ops), Err(Failure::Poisoned));
        assert_eq!(ops.calls.len(), 3);
    }

    #[test]
    fn partial_native_unlock_failure_is_terminal() {
        let (mut ledger, mut ops) = (Ledger::<2, 2>::new(), Mock::default());
        let a = ledger.acquire(4096, 8192, &mut ops).unwrap();
        ops.fail_on = Some((false, 8192));
        assert_eq!(
            ledger.release(a, &mut ops),
            Err(Failure::Unlock {
                page: 8192,
                code: 158
            })
        );
        assert_eq!(ops.calls.len(), 4);
        assert_eq!(ledger.release(a, &mut ops), Err(Failure::Poisoned));
        assert_eq!(ops.calls.len(), 4);
    }

    #[test]
    fn all_bounded_histories_match_independent_live_range_union() {
        // Five actions per step: acquire one of three overlapping ranges or
        // release the oldest/newest live token. 5^6 complete deterministic paths.
        for mut sequence in 0usize..5usize.pow(6) {
            let (mut ledger, mut ops) = (Ledger::<6, 4>::new(), Mock::default());
            let mut live = Vec::<(u64, usize, usize)>::new();
            for _ in 0..6 {
                let action = sequence % 5;
                sequence /= 5;
                if action < 3 {
                    let (address, bytes) = [(4096, 2), (8191, 2), (8192, 8)][action];
                    live.push((
                        ledger.acquire(address, bytes, &mut ops).unwrap(),
                        address,
                        bytes,
                    ));
                } else if !live.is_empty() {
                    let index = if action == 3 { 0 } else { live.len() - 1 };
                    let (token, _, _) = live.remove(index);
                    ledger.release(token, &mut ops).unwrap();
                }
                let expected: BTreeSet<_> = live
                    .iter()
                    .flat_map(|(_, address, bytes)| {
                        // Independent oracle enumerates individual bytes, not the
                        // ledger's inclusive first/last page arithmetic.
                        (*address..address + bytes).map(|byte| byte / 4096 * 4096)
                    })
                    .collect();
                assert_eq!(ops.locked, expected);
                assert_eq!(ledger.live_pages(), expected.len());
                assert_eq!(ledger.live_lifetimes(), live.len());
            }
            for (token, _, _) in live {
                ledger.release(token, &mut ops).unwrap();
            }
            assert!(ops.locked.is_empty());
        }
    }
}
