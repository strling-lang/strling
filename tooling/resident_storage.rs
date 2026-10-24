//! One-shot stable-address backing ownership; not whole-process residency.
//! PageOps, session handles, callbacks, stacks and other lifetimes need separate
//! coverage. A failed/abandoned session requires enclosing process retirement;
//! this module never speculates about native cleanup after failure.

#[path = "resident_page_ledger.rs"]
mod ledger;
use ledger::SerializedLedger;
pub use ledger::{Failure, PageOps};

use core::marker::PhantomPinned;
use core::pin::Pin;

pub struct StorageLedger<const L: usize, const P: usize> {
    ledger: SerializedLedger<L, P>,
    started: bool,
    _pin: PhantomPinned,
}

impl<const L: usize, const P: usize> Default for StorageLedger<L, P> {
    fn default() -> Self {
        Self::new()
    }
}

impl<const L: usize, const P: usize> StorageLedger<L, P> {
    pub const fn new() -> Self {
        Self {
            ledger: SerializedLedger::new(),
            started: false,
            _pin: PhantomPinned,
        }
    }

    pub fn is_poisoned(&self) -> bool {
        self.ledger.is_poisoned()
    }

    /// Begin a session that never exposes raw token operations.
    pub fn start_owned(
        self: Pin<&mut Self>,
        ops: &mut impl PageOps,
    ) -> Result<OwnedStorageSession<'_, L, P>, Failure> {
        Ok(OwnedStorageSession {
            session: self.start(ops)?,
        })
    }

    pub fn start<'a>(
        self: Pin<&'a mut Self>,
        ops: &mut impl PageOps,
    ) -> Result<StorageSession<'a, L, P>, Failure> {
        let address = self.as_ref().get_ref() as *const Self as usize;
        let bytes = core::mem::size_of::<Self>();
        // SAFETY: No pinned field is moved or replaced. Only the plain boolean
        // changes; the returned borrow keeps the entire backing object alive.
        // PhantomPinned prevents safe extraction/movement from an owning Pin.
        let this = unsafe { self.get_unchecked_mut() };
        if this.started {
            this.ledger.invalidate();
            return Err(Failure::Poisoned);
        }
        // Set before native callbacks, including those that fail or unwind.
        this.started = true;
        let anchor = this.ledger.acquire(address, bytes, ops)?;
        Ok(StorageSession {
            ledger: &this.ledger,
            anchor,
            finished: false,
        })
    }
}

pub struct StorageSession<'a, const L: usize, const P: usize> {
    ledger: &'a SerializedLedger<L, P>,
    anchor: u64,
    finished: bool,
}

/// Kept distinct from the raw-token session so forgotten handles cannot be
/// released by guessing a local token. The inner session is never exposed.
pub struct OwnedStorageSession<'a, const L: usize, const P: usize> {
    session: StorageSession<'a, L, P>,
}

impl<const L: usize, const P: usize> OwnedStorageSession<'_, L, P> {
    /// Borrow this session until an allocation is consumed or abandoned. Private
    /// ownership binds retirement to its issuer; callbacks still need separate
    /// qualification and must honor the captured allocation range.
    pub fn allocate_owned(
        &self,
        bytes: usize,
        ops: &mut impl PageOps,
        allocate_memory: impl FnOnce() -> Result<usize, u32>,
    ) -> Result<OwnedAllocation<'_, L, P>, Failure> {
        let (token, address) = self.session.ledger.allocate(bytes, ops, allocate_memory)?;
        Ok(OwnedAllocation {
            ledger: self.session.ledger,
            token,
            address,
            bytes,
            retired: false,
        })
    }

    pub fn finish(self, ops: &mut impl PageOps) -> Result<(), Failure> {
        self.session.finish(ops)
    }
}

impl<const L: usize, const P: usize> StorageSession<'_, L, P> {
    pub fn allocate(
        &mut self,
        bytes: usize,
        ops: &mut impl PageOps,
        allocate_memory: impl FnOnce() -> Result<usize, u32>,
    ) -> Result<(u64, usize), Failure> {
        self.ledger.allocate(bytes, ops, allocate_memory)
    }

    pub fn acquire(
        &mut self,
        address: usize,
        bytes: usize,
        ops: &mut impl PageOps,
    ) -> Result<u64, Failure> {
        self.ledger.acquire(address, bytes, ops)
    }

    pub fn release(&mut self, token: u64, ops: &mut impl PageOps) -> Result<(), Failure> {
        if token == self.anchor {
            self.ledger.invalidate();
            return Err(Failure::UnknownToken);
        }
        self.ledger.release(token, ops)
    }

    pub fn finish(mut self, ops: &mut impl PageOps) -> Result<(), Failure> {
        self.ledger.release_last(self.anchor, ops)?;
        self.finished = true;
        Ok(())
    }

    pub fn retire(
        &mut self,
        token: u64,
        ops: &mut impl PageOps,
        release_allocation: impl FnOnce() -> Result<(), u32>,
    ) -> Result<(), Failure> {
        if token == self.anchor {
            self.ledger.invalidate();
            return Err(Failure::UnknownToken);
        }
        self.ledger.retire(token, ops, release_allocation)
    }
}

impl<const L: usize, const P: usize> Drop for StorageSession<'_, L, P> {
    fn drop(&mut self) {
        if !self.finished {
            self.ledger.invalidate();
        }
    }
}

/// An optional linear allocation handle, not proof of allocator coverage.
/// Abandonment poisons without native cleanup. Forgetting the handle leaves a
/// live ledger lifetime, so the owning session still cannot finish successfully.
#[must_use = "retire the allocation or the owning context becomes unusable"]
pub struct OwnedAllocation<'a, const L: usize, const P: usize> {
    ledger: &'a SerializedLedger<L, P>,
    token: u64,
    address: usize,
    bytes: usize,
    retired: bool,
}

impl<const L: usize, const P: usize> OwnedAllocation<'_, L, P> {
    pub fn address(&self) -> usize {
        self.address
    }

    pub fn bytes(&self) -> usize {
        self.bytes
    }

    pub fn retire(
        mut self,
        ops: &mut impl PageOps,
        release_allocation: impl FnOnce(usize, usize) -> Result<(), u32>,
    ) -> Result<(), Failure> {
        self.ledger.retire(self.token, ops, || {
            release_allocation(self.address, self.bytes)
        })?;
        self.retired = true;
        Ok(())
    }
}

impl<const L: usize, const P: usize> Drop for OwnedAllocation<'_, L, P> {
    fn drop(&mut self) {
        if !self.retired {
            self.ledger.invalidate();
        }
    }
}
