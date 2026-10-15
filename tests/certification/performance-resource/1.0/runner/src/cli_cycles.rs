//! Explicit process-tree cycle domain. Never convert these counts into time.
use serde_json::{json, Value};
use std::process::Child;

pub const CONTRACT: &str = "native-cli-process-tree-cycles-v1";

#[derive(Clone, Copy, Default)]
pub struct Snapshot {
    launches: u64,
    cycles: u64,
}

impl Snapshot {
    pub fn observe(&mut self, cycles: u64) -> Result<(), String> {
        if cycles == 0 {
            return Err("CLI descendant cycle observation is zero".to_owned());
        }
        let launches = self
            .launches
            .checked_add(1)
            .ok_or("CLI launch count overflow")?;
        let total = self
            .cycles
            .checked_add(cycles)
            .ok_or("CLI cycle sum overflow")?;
        self.launches = launches;
        self.cycles = total;
        Ok(())
    }

    pub fn evidence(
        self,
        after: Self,
        expected_launches: u64,
        parent_started: u64,
        parent_ended: u64,
    ) -> Result<Value, String> {
        let launches = after
            .launches
            .checked_sub(self.launches)
            .ok_or("CLI count regressed")?;
        let child_cycles = after
            .cycles
            .checked_sub(self.cycles)
            .ok_or("CLI cycles regressed")?;
        let parent_cycles = parent_ended
            .checked_sub(parent_started)
            .ok_or("parent cycles regressed")?;
        if expected_launches == 0
            || launches != expected_launches
            || child_cycles == 0
            || parent_cycles == 0
        {
            return Err("incomplete CLI process-tree cycle evidence".to_owned());
        }
        let tree_cycles = parent_cycles
            .checked_add(child_cycles)
            .ok_or("tree cycle sum overflow")?;
        Ok(json!({
            "contract": CONTRACT, "counter_api": "QueryProcessCycleTime",
            "unit": "processor_cycles", "child_launches": launches,
            "parent_started": parent_started, "parent_ended": parent_ended,
            "parent_cycles": parent_cycles, "child_cycles": child_cycles,
            "tree_cycles": tree_cycles,
        }))
    }
}

pub fn validate_selection(
    native_windows: bool,
    operation: &str,
    samples: usize,
    batch: Option<usize>,
    enabled: bool,
) -> Result<(), String> {
    if enabled
        && (!native_windows
            || operation != "latency:cli-startup"
            || samples != 64
            || batch != Some(1))
    {
        return Err(
            "CLI cycle contract requires native Windows, all64 pairs and explicit batch1"
                .to_owned(),
        );
    }
    Ok(())
}

#[cfg(target_os = "windows")]
mod native {
    use super::Child;
    use std::ffi::c_void;
    use std::os::windows::io::AsRawHandle;
    type Handle = *mut c_void;
    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> Handle;
        fn DuplicateHandle(
            source: Handle,
            handle: Handle,
            target: Handle,
            out: *mut Handle,
            access: u32,
            inherit: i32,
            options: u32,
        ) -> i32;
        fn QueryProcessCycleTime(handle: Handle, value: *mut u64) -> i32;
        fn CloseHandle(handle: Handle) -> i32;
    }
    pub struct RetainedChild(Option<Handle>);
    impl RetainedChild {
        pub fn retain(child: &Child) -> Result<Self, String> {
            let parent = unsafe { GetCurrentProcess() };
            let mut retained = std::ptr::null_mut();
            if unsafe {
                DuplicateHandle(
                    parent,
                    child.as_raw_handle(),
                    parent,
                    &mut retained,
                    0,
                    0,
                    2,
                )
            } == 0
            {
                return Err(format!(
                    "retain CLI child: {}",
                    std::io::Error::last_os_error()
                ));
            }
            Ok(Self(Some(retained)))
        }
        pub fn read_and_close(mut self) -> Result<u64, String> {
            let handle = self.0.ok_or("CLI child handle absent")?;
            let mut cycles = 0;
            if unsafe { QueryProcessCycleTime(handle, &mut cycles) } == 0 {
                return Err(format!(
                    "CLI child cycles: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if unsafe { CloseHandle(handle) } == 0 {
                return Err(format!(
                    "close CLI child: {}",
                    std::io::Error::last_os_error()
                ));
            }
            self.0 = None;
            if cycles == 0 {
                return Err("CLI child cycles unavailable".to_owned());
            }
            Ok(cycles)
        }
    }
    impl Drop for RetainedChild {
        fn drop(&mut self) {
            if let Some(handle) = self.0.take() {
                unsafe {
                    CloseHandle(handle);
                }
            }
        }
    }
}

#[cfg(target_os = "windows")]
pub use native::RetainedChild;

#[cfg(not(target_os = "windows"))]
pub struct RetainedChild;
#[cfg(not(target_os = "windows"))]
impl RetainedChild {
    pub fn retain(_: &Child) -> Result<Self, String> {
        Err("native Windows CLI cycles required".to_owned())
    }
    pub fn read_and_close(self) -> Result<u64, String> {
        Err("native Windows CLI cycles required".to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cli_cycle_complete_counts_and_exact_sum() {
        let before = Snapshot::default();
        let mut after = before;
        after.observe(20).unwrap();
        let value = before.evidence(after, 1, 100, 110).unwrap();
        assert_eq!(value["tree_cycles"], 30);
        assert_eq!(value["unit"], "processor_cycles");
        assert!(before.evidence(after, 2, 100, 110).is_err());
        assert!(before.evidence(after, 1, 110, 100).is_err());
        assert!(before.evidence(after, 1, 100, 100).is_err());
        assert!(after.observe(0).is_err());
    }
    #[test]
    fn cli_cycle_overflow_and_counter_regression_reject() {
        let before = Snapshot {
            launches: 1,
            cycles: u64::MAX,
        };
        let mut after = before;
        assert!(after.observe(1).is_err());
        assert!(before.evidence(Snapshot::default(), 1, 1, 2).is_err());
        let before = Snapshot::default();
        assert!(before
            .evidence(
                Snapshot {
                    launches: 1,
                    cycles: u64::MAX
                },
                1,
                1,
                2
            )
            .is_err());
    }
    #[test]
    fn cli_cycle_selection_is_explicit_complete_and_native() {
        assert!(validate_selection(true, "latency:cli-startup", 64, Some(1), true).is_ok());
        for (native, operation, samples, batch) in [
            (false, "latency:cli-startup", 64, Some(1)),
            (true, "latency:compile", 64, Some(1)),
            (true, "latency:cli-startup", 63, Some(1)),
            (true, "latency:cli-startup", 64, None),
            (true, "latency:cli-startup", 64, Some(2)),
        ] {
            assert!(validate_selection(native, operation, samples, batch, true).is_err());
        }
    }
}
