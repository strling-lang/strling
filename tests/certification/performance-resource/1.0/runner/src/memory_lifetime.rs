//! Parent-owned observation of the exact child's process-lifetime peak RSS.
//! This does not prove absence of trimming, descendant coverage or admission.

use std::ffi::c_void;
use std::io;
use std::mem::size_of;
use std::os::windows::io::AsRawHandle;
use std::process::Child;
use std::time::{Duration, Instant};

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
    fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> Handle;
    fn SetInformationJobObject(job: Handle, class: i32, value: *const c_void, bytes: u32) -> i32;
    fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    fn QueryInformationJobObject(
        job: Handle,
        class: i32,
        value: *mut c_void,
        bytes: u32,
        returned: *mut u32,
    ) -> i32;
}

#[repr(C)]
#[derive(Default)]
struct BasicLimits {
    process_time: i64,
    job_time: i64,
    flags: u32,
    minimum_ws: usize,
    maximum_ws: usize,
    active_processes: u32,
    affinity: usize,
    priority: u32,
    scheduling: u32,
}

#[repr(C)]
#[derive(Default)]
struct ExtendedLimits {
    basic: BasicLimits,
    io: [u64; 6],
    process_memory: usize,
    job_memory: usize,
    peak_process_memory: usize,
    peak_job_memory: usize,
}

#[repr(C)]
#[derive(Debug, Default)]
struct Accounting {
    times: [i64; 4],
    page_faults: u32,
    total: u32,
    active: u32,
    terminated: u32,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

// A signaled process handle does not synchronize the job's final accounting.
// Only bookkeeping may be pending here: finish has already proved exact-child
// exit. Never rerun work, accept another member, or terminate a job to pass.
fn await_natural_job_retirement(
    mut query: impl FnMut() -> io::Result<(Accounting, u32)>,
    mut elapsed: impl FnMut() -> Duration,
    mut pause: impl FnMut(),
) -> io::Result<()> {
    let mut observations = 0u32;
    loop {
        let (accounting, returned) = query()?;
        observations += 1;
        if returned == size_of::<Accounting>() as u32
            && accounting.total == 1
            && accounting.terminated == 0
        {
            if accounting.active == 0 {
                return Ok(());
            }
            if accounting.active == 1 && elapsed() < Duration::from_secs(5) {
                pause();
                continue;
            }
        }
        return Err(invalid(&format!(
            "memory worker job did not retire exactly one natural process: \
             returned={returned}, total={}, active={}, limit_terminated={}, \
             observations={observations}, elapsed_ms={}",
            accounting.total,
            accounting.active,
            accounting.terminated,
            elapsed().as_millis(),
        )));
    }
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

fn peaks(handle: Handle) -> io::Result<(u64, u64)> {
    let mut counters = MemoryCounters {
        cb: size_of::<MemoryCounters>() as u32,
        ..MemoryCounters::default()
    };
    if unsafe { K32GetProcessMemoryInfo(handle, &mut counters, size_of::<MemoryCounters>() as u32) }
        == 0
    {
        return Err(io::Error::last_os_error());
    }
    if counters.cb != size_of::<MemoryCounters>() as u32
        || counters.rss > counters.peak_rss
        || counters.commit > counters.peak_commit
    {
        return Err(invalid("memory observer received incomplete peak RSS"));
    }
    Ok((
        u64::try_from(counters.peak_rss).map_err(|_| invalid("peak RSS overflow"))?,
        u64::try_from(counters.peak_commit).map_err(|_| invalid("peak commit overflow"))?,
    ))
}

pub struct Observation {
    handle: Handle,
    pub pid: u32,
    pub birth_100ns: u64,
    initial_peak: u64,
    initial_commit: u64,
    private_job: Handle,
}

#[derive(Debug)]
pub struct Terminal {
    pub pid: u32,
    pub birth_100ns: u64,
    pub exit_100ns: u64,
    pub peak_rss_bytes: u64,
    pub peak_commit_bytes: u64,
    pub single_process_job: bool,
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
        Self::begin_context(child, false)
    }

    pub fn begin_workstation(child: &Child) -> io::Result<Self> {
        Self::begin_context(child, true)
    }

    fn begin_context(child: &Child, single_process: bool) -> io::Result<Self> {
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
            initial_commit: 0,
            private_job: std::ptr::null_mut(),
        };
        let (pid, birth, exit) = identity(handle)?;
        if pid != result.pid || exit != 0 || unsafe { WaitForSingleObject(handle, 0) } != 258 {
            return Err(invalid(
                "memory observation did not begin with a live owned child",
            ));
        }
        result.birth_100ns = birth;
        // A pre-entry process can legitimately have no resident pages yet.
        (result.initial_peak, result.initial_commit) = peaks(handle)?;
        if single_process {
            if size_of::<ExtendedLimits>() != 144 || size_of::<Accounting>() != 48 {
                return Err(invalid("unsupported native job ABI"));
            }
            result.private_job =
                unsafe { CreateJobObjectW(std::ptr::null_mut(), std::ptr::null()) };
            if result.private_job.is_null() {
                return Err(io::Error::last_os_error());
            }
            let mut limits = ExtendedLimits::default();
            // Only this owned child is affected. No breakaway, CPU quota, memory
            // cap or ancestor mutation; a second process cannot join this job.
            limits.basic.flags = 0x2008; // KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
            limits.basic.active_processes = 1;
            if unsafe {
                SetInformationJobObject(
                    result.private_job,
                    9,
                    (&limits as *const ExtendedLimits).cast(),
                    size_of::<ExtendedLimits>() as u32,
                )
            } == 0
                || unsafe { AssignProcessToJobObject(result.private_job, handle) } == 0
            {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(result)
    }

    pub fn finish(self) -> io::Result<Terminal> {
        if unsafe { WaitForSingleObject(self.handle, 0) } != 0 {
            return Err(invalid("memory lifetime observation requires process exit"));
        }
        let (pid, birth, exit) = identity(self.handle)?;
        let (terminal_peak, terminal_commit) = peaks(self.handle)?;
        validate_terminal(
            (self.pid, self.birth_100ns),
            (pid, birth, exit),
            self.initial_peak,
            terminal_peak,
        )?;
        if terminal_commit < self.initial_commit
            || (!self.private_job.is_null() && terminal_commit == 0)
        {
            return Err(invalid("terminal peak commit is inconsistent"));
        }
        if !self.private_job.is_null() {
            let started = Instant::now();
            await_natural_job_retirement(
                || {
                    let mut accounting = Accounting::default();
                    let mut returned = 0;
                    if unsafe {
                        QueryInformationJobObject(
                            self.private_job,
                            1,
                            (&mut accounting as *mut Accounting).cast(),
                            size_of::<Accounting>() as u32,
                            &mut returned,
                        )
                    } == 0
                    {
                        return Err(io::Error::last_os_error());
                    }
                    Ok((accounting, returned))
                },
                || started.elapsed(),
                || std::thread::sleep(Duration::from_millis(1)),
            )?;
        }
        Ok(Terminal {
            pid,
            birth_100ns: birth,
            exit_100ns: exit,
            peak_rss_bytes: terminal_peak,
            peak_commit_bytes: terminal_commit,
            single_process_job: !self.private_job.is_null(),
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
        if !self.private_job.is_null() {
            unsafe { CloseHandle(self.private_job) };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn accounting(total: u32, active: u32, terminated: u32) -> (Accounting, u32) {
        (
            Accounting {
                total,
                active,
                terminated,
                ..Accounting::default()
            },
            size_of::<Accounting>() as u32,
        )
    }

    #[test]
    fn signaled_child_allows_bounded_job_bookkeeping_lag() {
        let mut observations = [
            accounting(1, 1, 0),
            accounting(1, 1, 0),
            accounting(1, 0, 0),
        ]
        .into_iter();
        let mut pauses = 0;
        await_natural_job_retirement(
            || Ok(observations.next().unwrap()),
            || Duration::from_millis(2),
            || pauses += 1,
        )
        .unwrap();
        assert_eq!(pauses, 2);
        assert!(observations.next().is_none());
    }

    #[test]
    fn job_accounting_failure_and_deadline_preserve_exact_counts() {
        for (total, active, terminated) in [(0, 0, 0), (2, 0, 0), (1, 2, 0), (1, 0, 1), (1, 1, 0)] {
            let error = await_natural_job_retirement(
                || Ok(accounting(total, active, terminated)),
                || Duration::from_secs(5),
                || panic!("invalid or expired accounting cannot wait"),
            )
            .unwrap_err()
            .to_string();
            assert!(
                error.contains(&format!(
                    "total={total}, active={active}, limit_terminated={terminated}"
                )),
                "{error}"
            );
            assert!(error.contains("observations=1, elapsed_ms=5000"), "{error}");
        }
        let error = await_natural_job_retirement(
            || {
                let (a, _) = accounting(1, 0, 0);
                Ok((a, 0))
            },
            || Duration::ZERO,
            || panic!("incomplete accounting cannot wait"),
        )
        .unwrap_err()
        .to_string();
        assert!(error.contains("returned=0"));
        assert!(await_natural_job_retirement(
            || Err(invalid("native query failed")),
            || Duration::ZERO,
            || panic!("query failure cannot wait"),
        )
        .unwrap_err()
        .to_string()
        .contains("native query failed"));
    }

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
            peak_commit_bytes: 8,
            single_process_job: false,
        };
        assert!(terminal.validate_reported_peak(3).is_ok());
        assert!(terminal.validate_reported_peak(4).is_ok());
        assert!(terminal.validate_reported_peak(0).is_err());
        assert!(terminal.validate_reported_peak(5).is_err());
    }
}
