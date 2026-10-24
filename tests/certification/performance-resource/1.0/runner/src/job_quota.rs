//! Immediate-job observations cannot prove an unlimited ancestor chain.

fn classify(in_job: bool, flags: u32) -> Result<(), String> {
    if !in_job {
        return Ok(());
    }
    if flags & 1 != 0 {
        return Err("the Windows job imposes a CPU rate limit".to_owned());
    }
    Err("the Windows ancestor CPU quota is unknown (only the immediate job was queried)".to_owned())
}

#[cfg(target_os = "windows")]
pub fn require_unlimited() -> Result<(), String> {
    use std::ffi::c_void;
    type Handle = *mut c_void;
    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> Handle;
        fn IsProcessInJob(process: Handle, job: Handle, result: *mut i32) -> i32;
        fn QueryInformationJobObject(
            job: Handle,
            information_class: i32,
            information: *mut c_void,
            information_length: u32,
            returned_length: *mut u32,
        ) -> i32;
    }
    let mut in_job = 0;
    if unsafe { IsProcessInJob(GetCurrentProcess(), std::ptr::null_mut(), &mut in_job) } == 0 {
        return Err(format!(
            "IsProcessInJob failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    if in_job == 0 {
        return classify(false, 0);
    }
    let mut values = [0u32; 2];
    let mut returned = 0u32;
    let size = std::mem::size_of_val(&values) as u32;
    if unsafe {
        QueryInformationJobObject(
            std::ptr::null_mut(),
            15,
            values.as_mut_ptr().cast(),
            size,
            &mut returned,
        )
    } == 0
    {
        return Err(format!(
            "QueryInformationJobObject(CPU rate) failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    if returned != size {
        return Err("incomplete Windows CPU quota information".to_owned());
    }
    classify(true, values[0])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_job_does_not_invent_a_limit() {
        assert_eq!(classify(false, 0), Ok(()));
    }

    #[test]
    fn every_enabled_control_is_rejected() {
        for flags in [1, 3, 5, 9, 17, u32::MAX] {
            assert!(classify(true, flags)
                .unwrap_err()
                .contains("CPU rate limit"));
        }
    }

    #[test]
    fn disabled_immediate_job_cannot_prove_ancestors_unlimited() {
        for flags in [0, 2, 4, 8, 16, u32::MAX - 1] {
            assert!(classify(true, flags)
                .unwrap_err()
                .contains("ancestor CPU quota is unknown"));
        }
    }
}
