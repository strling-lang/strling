//! Standalone synthetic page-history fixture, not a product performance worker.
const PAGE: usize = 4096;
const PAGES: usize = 512;
const BYTES: usize = PAGE * PAGES;

fn offsets(reverse: bool) -> Vec<usize> {
    let mut values: Vec<_> = (0..PAGES).map(|i| i * PAGE).collect();
    if reverse {
        values.reverse();
    }
    values
}

#[cfg(windows)]
mod native {
    use super::*;
    use std::ffi::c_void;
    use std::io::{self, Write};
    #[link(name = "kernel32")]
    extern "system" {
        fn VirtualAlloc(address: *mut c_void, bytes: usize, kind: u32, protection: u32) -> *mut u8;
        fn GetCurrentProcess() -> *mut c_void;
        fn GetLastError() -> u32;
        fn K32EmptyWorkingSet(process: *mut c_void) -> i32;
        fn DebugBreak();
        fn IsDebuggerPresent() -> i32;
    }
    fn pause(phase: u32, a: usize, b: usize, checksum: u64, trim: i32, error: u32) {
        println!("{{\"phase\":{phase},\"a\":{a},\"b\":{b},\"checksum\":{checksum},\"trim\":{trim},\"error\":{error}}}");
        io::stdout().flush().unwrap();
        unsafe { DebugBreak() };
    }
    pub fn run() -> Result<(), String> {
        unsafe {
            if IsDebuggerPresent() == 0 {
                return Err("owned debugger required before synthetic work".into());
            }
            pause(0, 0, 0, 0, 0, 0);
            let a = VirtualAlloc(std::ptr::null_mut(), BYTES, 0x3000, 4);
            if a.is_null() {
                return Err(format!("allocation A {}", GetLastError()));
            }
            let mut checksum = 0u64;
            for offset in offsets(false) {
                std::ptr::write_volatile(a.add(offset), 1);
                checksum += std::ptr::read_volatile(a.add(offset)) as u64;
            }
            pause(1, a as usize, 0, checksum, 0, 0);
            let trim = K32EmptyWorkingSet(GetCurrentProcess());
            let error = if trim == 0 { GetLastError() } else { 0 };
            pause(2, a as usize, 0, checksum, trim, error);
            let b = VirtualAlloc(std::ptr::null_mut(), BYTES, 0x3000, 4);
            if b.is_null() {
                return Err(format!("allocation B {}", GetLastError()));
            }
            for offset in offsets(true) {
                std::ptr::write_volatile(b.add(offset), 3);
                checksum += std::ptr::read_volatile(b.add(offset)) as u64;
                checksum += std::ptr::read_volatile(a.add(offset)) as u64;
            }
            pause(3, a as usize, b as usize, checksum, 0, 0);
            let trim = K32EmptyWorkingSet(GetCurrentProcess());
            let error = if trim == 0 { GetLastError() } else { 0 };
            pause(4, a as usize, b as usize, checksum, trim, error);
            // Retain both dedicated regions until process exit, including all
            // debugger observation boundaries. The owned process retires them.
            println!("{{\"complete\":true,\"touches\":1536,\"checksum\":{checksum}}}");
            Ok(())
        }
    }
}

fn main() {
    #[cfg(windows)]
    if let Err(error) = native::run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
    #[cfg(not(windows))]
    std::process::exit(2);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_page_coordinates() {
        let forward = offsets(false);
        assert_eq!(forward.len(), 512);
        assert_eq!(forward[0], 0);
        assert_eq!(forward[511] + PAGE, BYTES);
        assert!(forward.windows(2).all(|p| p[1] - p[0] == PAGE));
    }
    #[test]
    fn reverse_has_identical_work_and_fixed_checksum() {
        assert_eq!(
            offsets(true).into_iter().rev().collect::<Vec<_>>(),
            offsets(false)
        );
        assert_eq!(PAGES * (1 + 3 + 1), 2560);
        assert_eq!(PAGES * 3, 1536);
    }
}
