//! Parent-owned observation of the exact child's process-lifetime peak RSS.
//! This does not prove absence of trimming, descendant coverage or admission.

use std::ffi::c_void;
use std::io;
use std::mem::size_of;
use std::os::windows::io::AsRawHandle;
use std::process::Child;

type Handle = *mut c_void;

#[repr(C)]
#[derive(Default)]
struct MemoryCounters {
    cb: u32,
    faults: u32,
    peak_rss: usize,
    rss: usize,
    peak_paged: usize,
    paged: usize,
    peak_nonpaged: usize,
    nonpaged: usize,
    commit: usize,
    peak_commit: usize,
}

#[link(name = "kernel32")]
extern "system" {
    fn GetCurrentProcess() -> Handle;
    fn DuplicateHandle(
        source_process: Handle,
        source: Handle,
        target_process: Handle,
        target: *mut Handle,
        access: u32,
        inherit: i32,
        options: u32,
    ) -> i32;
    fn CloseHandle(handle: Handle) -> i32;
    fn GetProcessId(process: Handle) -> u32;
    fn GetProcessTimes(
        process: Handle,
        birth: *mut u64,
        exit: *mut u64,
        kernel: *mut u64,
        user: *mut u64,
    ) -> i32;
    fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
    fn TerminateProcess(process: Handle, exit_code: u32) -> i32;
    fn K32GetProcessMemoryInfo(process: Handle, counters: *mut MemoryCounters, size: u32) -> i32;
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn identity(handle: Handle) -> io::Result<(u32, u64, u64)> {
    let pid = unsafe { GetProcessId(handle) };
    let (mut birth, mut exit, mut kernel, mut user) = (0, 0, 0, 0);
    if pid == 0
        || unsafe { GetProcessTimes(handle, &mut birth, &mut exit, &mut kernel, &mut user) } == 0
    {
        return Err(io::Error::last_os_error());
    }
    if birth == 0 {
        return Err(invalid("memory observer received a zero process birth"));
    }
    Ok((pid, birth, exit))
}

fn peak(handle: Handle) -> io::Result<u64> {
    let mut counters = MemoryCounters {
        cb: size_of::<MemoryCounters>() as u32,
        ..MemoryCounters::default()
    };
    if unsafe { K32GetProcessMemoryInfo(handle, &mut counters, size_of::<MemoryCounters>() as u32) }
        == 0
    {
        return Err(io::Error::last_os_error());
    }
    if counters.cb != size_of::<MemoryCounters>() as u32 || counters.rss > counters.peak_rss {
        return Err(invalid("memory observer received incomplete peak RSS"));
    }
    u64::try_from(counters.peak_rss).map_err(|_| invalid("peak RSS overflow"))
}

pub struct Observation {
    handle: Handle,
    pub pid: u32,
    pub birth_100ns: u64,
    initial_peak: u64,
}

#[derive(Debug)]
pub struct Terminal {
    pub pid: u32,
    pub birth_100ns: u64,
    pub exit_100ns: u64,
    pub peak_rss_bytes: u64,
}

impl Terminal {
    pub fn validate_reported_peak(&self, reported_peak: u64) -> io::Result<()> {
        if reported_peak == 0 || reported_peak > self.peak_rss_bytes {
            return Err(invalid("worker report exceeds terminal peak RSS"));
        }
        Ok(())
    }
}

impl Observation {
    /// Called only while controlled_spawn still owns a singly suspended child.
    pub fn begin(child: &Child) -> io::Result<Self> {
        let mut handle = std::ptr::null_mut();
        let current = unsafe { GetCurrentProcess() };
        if unsafe {
            DuplicateHandle(
                current,
                child.as_raw_handle(),
                current,
                &mut handle,
                0,
                0,
                2,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let mut result = Self {
            handle,
            pid: child.id(),
            birth_100ns: 0,
            initial_peak: 0,
        };
        let (pid, birth, exit) = identity(handle)?;
        if pid != result.pid || exit != 0 || unsafe { WaitForSingleObject(handle, 0) } != 258 {
            return Err(invalid(
                "memory observation did not begin with a live owned child",
            ));
        }
        result.birth_100ns = birth;
        // A pre-entry process can legitimately have no resident pages yet.
        result.initial_peak = peak(handle)?;
        Ok(result)
    }

    pub fn finish(self) -> io::Result<Terminal> {
        if unsafe { WaitForSingleObject(self.handle, 0) } != 0 {
            return Err(invalid("memory lifetime observation requires process exit"));
        }
        let (pid, birth, exit) = identity(self.handle)?;
        let terminal_peak = peak(self.handle)?;
        validate_terminal(
            (self.pid, self.birth_100ns),
            (pid, birth, exit),
            self.initial_peak,
            terminal_peak,
        )?;
        Ok(Terminal {
            pid,
            birth_100ns: birth,
            exit_100ns: exit,
            peak_rss_bytes: terminal_peak,
        })
    }

    /// Failure-only cleanup of this exact retained child, never a PID lookup.
    pub fn retire(self) -> io::Result<Terminal> {
        match unsafe { WaitForSingleObject(self.handle, 0) } {
            0 => self.finish(),
            258 => {
                if unsafe { TerminateProcess(self.handle, 1) } == 0
                    && unsafe { WaitForSingleObject(self.handle, 0) } != 0
                {
                    return Err(io::Error::last_os_error());
                }
                if unsafe { WaitForSingleObject(self.handle, 5_000) } != 0 {
                    return Err(invalid("owned memory worker retirement did not complete"));
                }
                self.finish()
            }
            _ => Err(io::Error::last_os_error()),
        }
    }
}

fn validate_terminal(
    expected: (u32, u64),
    actual: (u32, u64, u64),
    initial_peak: u64,
    terminal_peak: u64,
) -> io::Result<()> {
    if expected.0 == 0
        || expected.1 == 0
        || (actual.0, actual.1) != expected
        || actual.2 <= actual.1
        || terminal_peak == 0
        || terminal_peak < initial_peak
    {
        return Err(invalid(
            "memory lifetime identity or peak RSS is inconsistent",
        ));
    }
    Ok(())
}

impl Drop for Observation {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.handle) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn terminal_identity_and_high_water_must_match() {
        assert!(validate_terminal((7, 10), (7, 10, 20), 2, 4).is_ok());
        for (expected, actual, initial, terminal) in [
            ((0, 10), (0, 10, 20), 2, 4),
            ((7, 0), (7, 0, 20), 2, 4),
            ((7, 10), (8, 10, 20), 2, 4),
            ((7, 10), (7, 11, 20), 2, 4),
            ((7, 10), (7, 10, 0), 2, 4),
            ((7, 10), (7, 10, 10), 2, 4),
            ((7, 10), (7, 10, 20), 5, 4),
            ((7, 10), (7, 10, 20), 0, 0),
        ] {
            assert!(validate_terminal(expected, actual, initial, terminal).is_err());
        }
        let terminal = Terminal {
            pid: 7,
            birth_100ns: 10,
            exit_100ns: 20,
            peak_rss_bytes: 4,
        };
        assert!(terminal.validate_reported_peak(3).is_ok());
        assert!(terminal.validate_reported_peak(4).is_ok());
        assert!(terminal.validate_reported_peak(0).is_err());
        assert!(terminal.validate_reported_peak(5).is_err());
    }
}
