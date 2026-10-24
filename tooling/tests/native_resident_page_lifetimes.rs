//! One-use owned-page mechanism challenge, never a product or admission result.

#[path = "../resident_page_ledger.rs"]
mod ledger;

#[cfg(windows)]
mod native {
    use super::ledger::{Ledger, PageOps, PAGE_BYTES};
    use std::ffi::c_void;

    #[repr(C)]
    struct SystemInfo {
        architecture: u16,
        reserved: u16,
        page_size: u32,
        minimum: *mut c_void,
        maximum: *mut c_void,
        mask: usize,
        processors: u32,
        processor_type: u32,
        granularity: u32,
        level: u16,
        revision: u16,
    }
    #[repr(C)]
    struct PageStatus {
        address: usize,
        flags: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn GetLastError() -> u32;
        fn GetSystemInfo(info: *mut SystemInfo);
        fn VirtualAlloc(address: *mut c_void, bytes: usize, kind: u32, protect: u32)
            -> *mut c_void;
        fn VirtualFree(address: *mut c_void, bytes: usize, kind: u32) -> i32;
        fn VirtualLock(address: *mut c_void, bytes: usize) -> i32;
        fn VirtualUnlock(address: *mut c_void, bytes: usize) -> i32;
        fn K32EmptyWorkingSet(process: *mut c_void) -> i32;
        fn K32QueryWorkingSetEx(process: *mut c_void, info: *mut c_void, bytes: u32) -> i32;
    }

    struct Region(usize);
    impl Region {
        fn new() -> Self {
            let pointer = unsafe { VirtualAlloc(std::ptr::null_mut(), PAGE_BYTES, 0x3000, 4) };
            assert!(!pointer.is_null(), "VirtualAlloc error {}", unsafe {
                GetLastError()
            });
            unsafe { std::ptr::write_volatile(pointer.cast::<u8>(), 17) };
            println!(
                "{{\"event\":\"allocate\",\"page\":{},\"bytes\":4096}}",
                pointer as usize
            );
            Self(pointer as usize)
        }
    }
    impl Drop for Region {
        fn drop(&mut self) {
            let result = unsafe { VirtualFree(self.0 as *mut c_void, 0, 0x8000) };
            let code = if result == 0 {
                unsafe { GetLastError() }
            } else {
                0
            };
            println!(
                "{{\"event\":\"free\",\"page\":{},\"result\":{},\"error\":{}}}",
                self.0, result, code
            );
            assert_ne!(result, 0, "owned allocation did not retire");
        }
    }

    #[derive(Default)]
    struct NativeOps {
        locks: usize,
        unlocks: usize,
    }
    impl PageOps for NativeOps {
        fn lock(&mut self, page: usize) -> Result<(), u32> {
            self.locks += 1;
            let result = unsafe { VirtualLock(page as *mut c_void, PAGE_BYTES) };
            let code = if result == 0 {
                unsafe { GetLastError() }
            } else {
                0
            };
            println!("{{\"event\":\"lock\",\"page\":{page},\"result\":{result},\"error\":{code}}}");
            if result != 0 {
                Ok(())
            } else {
                Err(code)
            }
        }
        fn unlock(&mut self, page: usize) -> Result<(), u32> {
            self.unlocks += 1;
            let result = unsafe { VirtualUnlock(page as *mut c_void, PAGE_BYTES) };
            let code = if result == 0 {
                unsafe { GetLastError() }
            } else {
                0
            };
            println!(
                "{{\"event\":\"unlock\",\"page\":{page},\"result\":{result},\"error\":{code}}}"
            );
            if result != 0 {
                Ok(())
            } else {
                Err(code)
            }
        }
    }
    fn flags(label: &str, page: usize) -> usize {
        let mut state = PageStatus {
            address: page,
            flags: 0,
        };
        let result = unsafe {
            K32QueryWorkingSetEx(
                GetCurrentProcess(),
                (&mut state as *mut PageStatus).cast(),
                std::mem::size_of::<PageStatus>() as u32,
            )
        };
        let code = if result == 0 {
            unsafe { GetLastError() }
        } else {
            0
        };
        println!("{{\"event\":\"query\",\"label\":\"{label}\",\"page\":{page},\"flags\":{},\"result\":{result},\"error\":{code}}}", state.flags);
        assert_ne!(result, 0);
        state.flags
    }
    fn locked(value: usize) -> bool {
        value & 1 != 0 && value & (1 << 22) != 0
    }

    pub fn run() {
        assert_eq!(std::mem::size_of::<usize>(), 8);
        assert_eq!(std::mem::size_of::<SystemInfo>(), 48);
        let mut info: SystemInfo = unsafe { std::mem::zeroed() };
        unsafe { GetSystemInfo(&mut info) };
        assert_eq!(info.page_size as usize, PAGE_BYTES);
        let naive = Region::new();
        let mut raw = NativeOps::default();
        raw.lock(naive.0).unwrap();
        raw.lock(naive.0).unwrap();
        assert!(locked(flags("naive-two-locks", naive.0)));
        raw.unlock(naive.0).unwrap();
        assert!(!locked(flags("naive-one-release", naive.0)));

        let shared = Region::new();
        assert_ne!(shared.0, naive.0);
        let mut ops = NativeOps::default();
        let mut ledger = Ledger::<3, 1>::new();
        let a = ledger.acquire(shared.0, 8, &mut ops).unwrap();
        let b = ledger.acquire(shared.0 + 8, 8, &mut ops).unwrap();
        ledger.release(a, &mut ops).unwrap();
        assert_eq!((ops.locks, ops.unlocks), (1, 0));
        let trim = unsafe { K32EmptyWorkingSet(GetCurrentProcess()) };
        let code = if trim == 0 {
            unsafe { GetLastError() }
        } else {
            0
        };
        println!("{{\"event\":\"trim\",\"result\":{trim},\"error\":{code}}}");
        assert_ne!(trim, 0);
        assert!(locked(flags(
            "shared-after-first-release-and-trim",
            shared.0
        )));
        assert_eq!(
            unsafe { std::ptr::read_volatile(shared.0 as *const u8) },
            17
        );
        ledger.release(b, &mut ops).unwrap();
        assert!(!locked(flags("shared-after-last-release", shared.0)));
        let reused = ledger.acquire(shared.0, 8, &mut ops).unwrap();
        assert!(reused > b);
        assert!(locked(flags("shared-reused", shared.0)));
        ledger.release(reused, &mut ops).unwrap();
        assert!(!locked(flags("shared-reused-released", shared.0)));
        assert_eq!((ops.locks, ops.unlocks), (2, 2));
        assert_eq!((ledger.live_lifetimes(), ledger.live_pages()), (0, 0));
        assert!(!ledger.is_poisoned());
        drop(shared);
        drop(naive);
        println!("{{\"status\":\"owned-page-lifetimes-demonstrated\",\"naive_locks\":2,\"naive_unlocks\":1,\"ledger_locks\":2,\"ledger_unlocks\":2,\"lifetime_tokens\":3,\"freed_regions\":2,\"certification_eligible\":false,\"whole_process_coverage\":false}}");
    }
}

#[cfg(windows)]
fn main() {
    native::run();
}
#[cfg(not(windows))]
fn main() {
    panic!("Windows-only synthetic fixture");
}
