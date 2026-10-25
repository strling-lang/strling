//! Immediate-job observations cannot prove an unlimited ancestor chain.

pub const LABORATORY: &str = "laboratory-isolated-v1";
pub const WORKSTATION: &str = "shared-workstation-v1";

pub fn validate_context(context: &str) -> Result<(), String> {
    if matches!(context, LABORATORY | WORKSTATION) {
        Ok(())
    } else {
        Err("unknown certification context".to_owned())
    }
}

fn describe(context: &str, in_job: bool, flags: u32, rate: u32) -> Result<String, String> {
    validate_context(context)?;
    if context == LABORATORY {
        classify(in_job, flags)?;
        return Ok("unlimited".to_owned());
    }
    Ok(if in_job {
        format!("observed-immediate-job:flags={flags}:rate={rate}:ancestors=unknown")
    } else {
        "observed-no-job-at-query".to_owned()
    })
}

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
pub fn for_context(context: &str) -> Result<String, String> {
    validate_context(context)?;
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
        return describe(context, false, 0, 0);
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
    describe(context, true, values[0], values[1])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shared_context_observes_limits_without_claiming_unlimited_ancestors() {
        for flags in [0, 1, 5, u32::MAX] {
            let report = describe(WORKSTATION, true, flags, 100).unwrap();
            assert!(report.contains("ancestors=unknown"));
            assert!(report.contains(&format!("flags={flags}:rate=100")));
            assert!(describe(LABORATORY, true, flags, 100).is_err());
        }
        assert_eq!(describe(LABORATORY, false, 0, 0).unwrap(), "unlimited");
        assert_eq!(
            describe(WORKSTATION, false, 0, 0).unwrap(),
            "observed-no-job-at-query"
        );
        assert!(describe("shared-workstation-v0", false, 0, 0).is_err());
    }

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
