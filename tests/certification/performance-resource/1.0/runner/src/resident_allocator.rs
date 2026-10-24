//! Qualification-only integration with the worker's real global allocator.
//! Native/loader allocations and stack/image lifetimes are not intercepted.

#[path = "../../../../../../tooling/resident_page_ledger.rs"]
mod ledger;

use ledger::{PageOps, SerializedLedger, PAGE_BYTES};
use std::alloc::{GlobalAlloc, Layout, System};
use std::ffi::c_void;
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};

#[link(name = "kernel32")]
extern "system" {
    fn VirtualLock(address: *mut c_void, bytes: usize) -> i32;
    fn VirtualUnlock(address: *mut c_void, bytes: usize) -> i32;
    fn GetLastError() -> u32;
    fn GetStdHandle(kind: u32) -> *mut c_void;
    fn WriteFile(
        handle: *mut c_void,
        buffer: *const u8,
        bytes: u32,
        written: *mut u32,
        overlapped: *mut c_void,
    ) -> i32;
}

struct NativePages;

fn system_allocation_address(pointer: *mut u8) -> Result<usize, u32> {
    if pointer.is_null() {
        // GlobalAlloc provides no error code. HeapAlloc does not set LastError;
        // zero marks an unknown allocation cause, not a Win32 success result.
        Err(0)
    } else {
        Ok(pointer as usize)
    }
}

impl PageOps for NativePages {
    fn lock(&mut self, page: usize) -> Result<(), u32> {
        if unsafe { VirtualLock(page as *mut c_void, PAGE_BYTES) } == 0 {
            Err(unsafe { GetLastError() })
        } else {
            Ok(())
        }
    }

    fn unlock(&mut self, page: usize) -> Result<(), u32> {
        if unsafe { VirtualUnlock(page as *mut c_void, PAGE_BYTES) } == 0 {
            Err(unsafe { GetLastError() })
        } else {
            Ok(())
        }
    }
}

/// A private header binds System's exact allocation to the ledger's token.
/// Clients see only the payload. The entire System allocation remains locked
/// until the ledger retires the token and invokes its exact deallocation.
pub struct ResidentAllocator<const L: usize, const P: usize> {
    ledger: SerializedLedger<L, P>,
    initialized: AtomicU8,
    allocations: AtomicU64,
    retirements: AtomicU64,
}

impl<const L: usize, const P: usize> ResidentAllocator<L, P> {
    pub const fn new() -> Self {
        Self {
            ledger: SerializedLedger::new(),
            initialized: AtomicU8::new(0),
            allocations: AtomicU64::new(0),
            retirements: AtomicU64::new(0),
        }
    }

    fn begin(&self) -> bool {
        match self
            .initialized
            .compare_exchange(0, 1, Ordering::Acquire, Ordering::Acquire)
        {
            Ok(_) => {
                // Global instances are stable in the image before first use.
                // Tests must likewise pin/retain the allocator through all use.
                let result = self.ledger.acquire(
                    self as *const Self as usize,
                    std::mem::size_of::<Self>(),
                    &mut NativePages,
                );
                if let Err(error) = result {
                    self.fail(error);
                    return false;
                }
                self.initialized
                    .compare_exchange(1, 2, Ordering::Release, Ordering::Relaxed)
                    .is_ok()
            }
            Err(2) => !self.ledger.is_poisoned(),
            Err(_) => {
                self.ledger.invalidate();
                self.initialized.store(3, Ordering::Release);
                false
            }
        }
    }

    fn fail(&self, error: ledger::Failure) {
        self.ledger.invalidate();
        self.initialized.store(3, Ordering::Release);
        // No Rust formatting, stdout initialization or heap allocation in an
        // allocator callback. Preserve supplied failure codes on the raw stream;
        // allocation failure code zero explicitly means no cause is available.
        let (kind, code) = match error {
            ledger::Failure::Lock { code, .. } => (b'L', code),
            ledger::Failure::Unlock { code, .. } => (b'U', code),
            ledger::Failure::Allocation { code } => (b'A', code),
            ledger::Failure::Retirement { code } => (b'R', code),
            ledger::Failure::Capacity => (b'C', 0),
            ledger::Failure::ConcurrentOrReentrant => (b'E', 0),
            _ => (b'P', 0),
        };
        let mut message = *b"resident-memory-audit failure X 00000000\n";
        message[30] = kind;
        for index in 0..8 {
            let nibble = ((code >> ((7 - index) * 4)) & 15) as u8;
            message[32 + index] = if nibble < 10 {
                b'0' + nibble
            } else {
                b'a' + nibble - 10
            };
        }
        let mut written = 0;
        unsafe {
            WriteFile(
                GetStdHandle((-12i32) as u32),
                message.as_ptr(),
                message.len() as u32,
                &mut written,
                std::ptr::null_mut(),
            );
        }
    }

    pub fn counts(&self) -> (u64, u64) {
        (
            self.allocations.load(Ordering::Acquire),
            self.retirements.load(Ordering::Acquire),
        )
    }

    fn combined(layout: Layout) -> Option<(Layout, usize)> {
        Layout::new::<u64>()
            .extend(layout)
            .ok()
            .map(|(combined, offset)| (combined.pad_to_align(), offset))
    }

    unsafe fn allocate(&self, layout: Layout, zeroed: bool) -> *mut u8 {
        if !self.begin() {
            return std::ptr::null_mut();
        }
        let Some((combined, offset)) = Self::combined(layout) else {
            self.fail(ledger::Failure::InvalidRange);
            return std::ptr::null_mut();
        };
        let result = self.ledger.allocate(combined.size(), &mut NativePages, || {
            // System is invoked directly, so observer metadata cannot recurse
            // through the Rust global allocator. Native bypass remains unproved.
            let pointer = if zeroed {
                System.alloc_zeroed(combined)
            } else {
                System.alloc(combined)
            };
            system_allocation_address(pointer)
        });
        match result {
            Ok((token, address)) => {
                (address as *mut u64).write(token);
                self.allocations.fetch_add(1, Ordering::Release);
                (address as *mut u8).add(offset)
            }
            Err(error) => {
                // Partial registration is terminal. Never return an unprotected
                // pointer or guess cleanup of the failed enclosing context.
                self.fail(error);
                std::ptr::null_mut()
            }
        }
    }
}

// SAFETY: Each successful pointer contains a private token and System layout.
// Layout extension preserves payload alignment. Ledger callbacks serialize page
// ownership; failure never publishes a pointer. Realloc uses allocate/copy/retire
// and never System.realloc, so shared/old pages remain registered until copying
// completes. GlobalAlloc's caller must provide the original pointer and layout.
unsafe impl<const L: usize, const P: usize> GlobalAlloc for ResidentAllocator<L, P> {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        self.allocate(layout, false)
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        self.allocate(layout, true)
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        let Some((combined, offset)) = Self::combined(layout) else {
            std::process::abort();
        };
        let address = pointer.sub(offset);
        let token = address.cast::<u64>().read();
        if let Err(error) = self.ledger.retire(token, &mut NativePages, || {
            System.dealloc(address, combined);
            Ok(())
        }) {
            self.fail(error);
            std::process::abort();
        }
        self.retirements.fetch_add(1, Ordering::Release);
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, bytes: usize) -> *mut u8 {
        let Ok(replacement_layout) = Layout::from_size_align(bytes, layout.align()) else {
            self.fail(ledger::Failure::InvalidRange);
            return std::ptr::null_mut();
        };
        let replacement = self.alloc(replacement_layout);
        if !replacement.is_null() {
            std::ptr::copy_nonoverlapping(pointer, replacement, layout.size().min(bytes));
            self.dealloc(pointer, layout);
        }
        replacement
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    extern "system" {
        fn SetLastError(code: u32);
    }

    #[test]
    fn system_allocator_failure_does_not_claim_thread_last_error() {
        let pointer = std::ptr::NonNull::<u8>::dangling().as_ptr();
        for marker in [0, 5, 0xdead_beef] {
            unsafe { SetLastError(marker) };
            let failed = system_allocation_address(std::ptr::null_mut());
            let after_failure = unsafe { GetLastError() };
            let succeeded = system_allocation_address(pointer);
            let after_success = unsafe { GetLastError() };
            assert_eq!(failed, Err(0));
            assert_eq!(after_failure, marker);
            assert_eq!(succeeded, Ok(pointer as usize));
            assert_eq!(after_success, marker);
        }
    }

    #[test]
    fn actual_native_allocator_zeroes_aligns_reallocates_and_retires() {
        // A static allocator intentionally retains its bookkeeping anchor until
        // process exit, just like the real worker's global instance.
        static ALLOCATOR: ResidentAllocator<16, 32> = ResidentAllocator::new();
        unsafe {
            let layout = Layout::from_size_align(257, 64).unwrap();
            let pointer = ALLOCATOR.alloc_zeroed(layout);
            assert!(!pointer.is_null());
            assert_eq!(pointer as usize % 64, 0);
            for index in 0..257 {
                assert_eq!(pointer.add(index).read(), 0);
                pointer.add(index).write((index % 251) as u8);
            }
            let replacement = ALLOCATOR.realloc(pointer, layout, 1025);
            assert!(!replacement.is_null());
            for index in 0..257 {
                assert_eq!(replacement.add(index).read(), (index % 251) as u8);
            }
            ALLOCATOR.dealloc(replacement, Layout::from_size_align(1025, 64).unwrap());
        }
        assert_eq!(ALLOCATOR.counts(), (2, 2));
        assert!(!ALLOCATOR.ledger.is_poisoned());
    }

    #[test]
    fn exhausted_allocator_never_publishes_or_recovers() {
        // The only lifetime slot is consumed by the allocator's own anchor.
        static ALLOCATOR: ResidentAllocator<1, 4> = ResidentAllocator::new();
        unsafe {
            let layout = Layout::from_size_align(8, 8).unwrap();
            assert!(ALLOCATOR.alloc(layout).is_null());
            assert!(ALLOCATOR.alloc(layout).is_null());
        }
        assert_eq!(ALLOCATOR.counts(), (0, 0));
        assert!(ALLOCATOR.ledger.is_poisoned());
    }

    #[test]
    fn concurrent_bootstrap_never_returns_an_unregistered_pointer() {
        static ALLOCATOR: ResidentAllocator<4, 4> = ResidentAllocator::new();
        ALLOCATOR.initialized.store(1, Ordering::Release);
        unsafe {
            assert!(ALLOCATOR.alloc(Layout::new::<u64>()).is_null());
        }
        assert_eq!(ALLOCATOR.counts(), (0, 0));
        assert!(ALLOCATOR.ledger.is_poisoned());
        assert_eq!(ALLOCATOR.initialized.load(Ordering::Acquire), 3);
    }
}
