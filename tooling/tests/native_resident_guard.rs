//! Standalone mechanism challenge, never linked into a performance producer.
//! Only explicitly promised pages are covered; this is not admission.

const PAGE: usize = 4096;
const LOCKED: usize = 1 << 22;

fn resident_and_locked(flags: usize) -> bool {
    flags & 1 != 0 && flags & LOCKED != 0
}

fn page_address(working_set_block: usize) -> usize {
    working_set_block & !(PAGE - 1)
}

#[cfg(windows)]
mod native {
    use super::{page_address, resident_and_locked, PAGE};
    use std::ffi::c_void;
    use std::mem::size_of;
    use std::time::Instant;

    #[repr(C)]
    #[derive(Default)]
    struct Memory {
        cb: u32,
        faults: u32,
        peak_ws: usize,
        ws: usize,
        peak_paged: usize,
        paged: usize,
        peak_nonpaged: usize,
        nonpaged: usize,
        pagefile: usize,
        peak_pagefile: usize,
        private: usize,
    }

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct PageStatus {
        address: usize,
        flags: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn GetLastError() -> u32;
        fn GetProcessWorkingSetSizeEx(
            process: *mut c_void,
            minimum: *mut usize,
            maximum: *mut usize,
            flags: *mut u32,
        ) -> i32;
        fn K32GetProcessMemoryInfo(process: *mut c_void, memory: *mut Memory, cb: u32) -> i32;
        fn K32QueryWorkingSet(process: *mut c_void, buffer: *mut c_void, cb: u32) -> i32;
        fn K32QueryWorkingSetEx(process: *mut c_void, buffer: *mut c_void, cb: u32) -> i32;
        fn K32EmptyWorkingSet(process: *mut c_void) -> i32;
        fn VirtualLock(address: *mut c_void, size: usize) -> i32;
        fn VirtualAlloc(
            address: *mut c_void,
            size: usize,
            kind: u32,
            protection: u32,
        ) -> *mut c_void;
    }

    fn check(ok: bool, label: &str) -> Result<(), String> {
        if ok {
            Ok(())
        } else {
            Err(format!("{label}: {}", unsafe { GetLastError() }))
        }
    }

    fn snapshot(stage: &str) -> Result<(), String> {
        let mut memory = Memory {
            cb: size_of::<Memory>() as u32,
            ..Memory::default()
        };
        let (mut minimum, mut maximum, mut flags) = (0, 0, 0);
        unsafe {
            check(
                K32GetProcessMemoryInfo(GetCurrentProcess(), &mut memory, 80) != 0,
                "memory query",
            )?;
            check(
                GetProcessWorkingSetSizeEx(
                    GetCurrentProcess(),
                    &mut minimum,
                    &mut maximum,
                    &mut flags,
                ) != 0,
                "control query",
            )?;
        }
        println!(
            "{{\"stage\":\"{stage}\",\"minimum\":{minimum},\"maximum\":{maximum},\"flags\":{flags},\"peak_rss\":{},\"rss\":{},\"private\":{},\"peak_commit\":{},\"faults\":{}}}",
            memory.peak_ws, memory.ws, memory.private, memory.peak_pagefile, memory.faults
        );
        Ok(())
    }

    fn verify_pages(addresses: &[usize], stage: &str) -> Result<(), String> {
        let mut rows: Vec<_> = addresses
            .iter()
            .map(|address| PageStatus {
                address: *address,
                flags: 0,
            })
            .collect();
        unsafe {
            check(
                K32QueryWorkingSetEx(
                    GetCurrentProcess(),
                    rows.as_mut_ptr().cast(),
                    (rows.len() * size_of::<PageStatus>()) as u32,
                ) != 0,
                "page query",
            )?;
        }
        print!("{{\"stage\":\"{stage}\",\"pages\":[");
        for (index, row) in rows.iter().enumerate() {
            if index != 0 {
                print!(",");
            }
            print!("[{},{}]", row.address, row.flags);
        }
        println!("]}}");
        if rows.iter().all(|row| resident_and_locked(row.flags)) {
            Ok(())
        } else {
            Err("promised page is absent or unlocked".into())
        }
    }

    pub fn run() -> Result<(), String> {
        assert_eq!(size_of::<usize>(), 8);
        assert_eq!(size_of::<Memory>(), 80);
        assert_eq!(size_of::<PageStatus>(), 16);
        let started = Instant::now();
        let mut census = vec![0usize; 32769];
        let mut addresses = Vec::with_capacity(32768 + 2048);
        snapshot("initial")?;
        unsafe {
            check(
                K32QueryWorkingSet(
                    GetCurrentProcess(),
                    census.as_mut_ptr().cast(),
                    (census.len() * size_of::<usize>()) as u32,
                ) != 0,
                "bounded census (no automatic retry)",
            )?;
        }
        if census[0] == 0 || census[0] >= census.len() {
            return Err("invalid census count".into());
        }
        for &entry in &census[1..=census[0]] {
            let address = page_address(entry);
            unsafe {
                check(
                    VirtualLock(address as *mut c_void, PAGE) != 0,
                    &format!("initial page lock {} at {address}", addresses.len()),
                )?;
            }
            addresses.push(address);
        }
        let initial_pages = addresses.len();
        verify_pages(&addresses, "initial-locked-pages")?;
        snapshot("initial-locked")?;
        let mut checksum = 0u64;
        let mut regions = Vec::with_capacity(2);
        for part in 0..2 {
            let region = unsafe { VirtualAlloc(std::ptr::null_mut(), 4 << 20, 0x3000, 4) };
            check(!region.is_null(), "allocation")?;
            regions.push(region);
            unsafe { check(VirtualLock(region, 4 << 20) != 0, "region lock")? };
            for offset in (0..4 << 20).step_by(PAGE) {
                addresses.push(region as usize + offset);
            }
            for repetition in 0..4 {
                for index in 0..1024 {
                    let value = ((part * 1024 + index + repetition) % 251) as u8;
                    unsafe {
                        (region as *mut u8).add(index * PAGE).write_volatile(value);
                    }
                    checksum += u64::from(value);
                }
            }
            snapshot(&format!("before-trim-{part}"))?;
            let ok = unsafe { K32EmptyWorkingSet(GetCurrentProcess()) };
            let error = if ok == 0 {
                unsafe { GetLastError() }
            } else {
                0
            };
            println!(
                "{{\"stage\":\"trim-{part}\",\"success\":{},\"error\":{error}}}",
                ok != 0
            );
            snapshot(&format!("after-trim-{part}"))?;
            verify_pages(&addresses, &format!("after-trim-{part}-pages"))?;
        }
        std::hint::black_box((&census, &regions));
        println!("{{\"stage\":\"complete\",\"initial_pages\":{initial_pages},\"promised_pages\":{},\"allocated_bytes\":8388608,\"page_touches\":8192,\"checksum\":{checksum},\"elapsed_ns\":{},\"certification_eligible\":false}}", addresses.len(), started.elapsed().as_nanos());
        // Dedicated disposable process: the OS retires all locks and regions at
        // exit. Do not unlock pages of a caller that could have prior locks.
        Ok(())
    }
}

fn main() {
    #[cfg(windows)]
    if let Err(error) = native::run() {
        println!("{{\"stage\":\"failed\",\"error\":\"{error}\",\"certification_eligible\":false}}");
        std::process::exit(1);
    }
    #[cfg(not(windows))]
    {
        eprintln!("native Windows mechanism fixture only");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_and_locked_are_both_required() {
        for flags in [0, 1, LOCKED, 1 << 23, (1 << 23) | LOCKED] {
            assert!(!resident_and_locked(flags));
        }
        assert!(resident_and_locked(1 | LOCKED));
    }

    #[test]
    fn page_decoding_preserves_full_native_address() {
        assert_eq!(page_address(0x0000_7fff_ffff_f1ff), 0x0000_7fff_ffff_f000);
        assert_eq!(page_address(0x1000), 0x1000);
    }

    #[test]
    fn invalid_page_ignores_other_flag_bits() {
        assert!(!resident_and_locked(usize::MAX & !1));
        assert!(resident_and_locked(usize::MAX));
    }
}
