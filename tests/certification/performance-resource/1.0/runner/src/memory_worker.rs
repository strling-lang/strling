#[cfg(target_os = "windows")]
mod worker {
    use std::ffi::c_void;
    use std::hint::black_box;
    use std::io;
    use std::time::Instant;

    use serde_json::json;
    use strling_kernel::protocol::CompileRequest;

    type WorkerResult<T> = Result<T, String>;
    type Handle = *mut c_void;

    const MAXIMUM_DESCHEDULING_NANOSECONDS: u64 = 50_000_000;
    const MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER: usize = 2;
    const JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION: i32 = 15;
    const JOB_OBJECT_CPU_RATE_CONTROL_ENABLE: u32 = 0x1;
    const PROCESS_POWER_THROTTLING_INFORMATION: i32 = 4;
    const PROCESS_POWER_THROTTLING_CURRENT_VERSION: u32 = 1;
    const PROCESS_POWER_THROTTLING_EXECUTION_SPEED: u32 = 0x1;

    #[repr(C)]
    struct ProcessorNumber {
        group: u16,
        number: u8,
        reserved: u8,
    }

    #[repr(C)]
    struct ProcessMemoryCounters {
        cb: u32,
        page_fault_count: u32,
        peak_working_set_size: usize,
        working_set_size: usize,
        quota_peak_paged_pool_usage: usize,
        quota_paged_pool_usage: usize,
        quota_peak_non_paged_pool_usage: usize,
        quota_non_paged_pool_usage: usize,
        pagefile_usage: usize,
        peak_pagefile_usage: usize,
    }

    #[repr(C)]
    struct ProcessPowerThrottlingState {
        version: u32,
        control_mask: u32,
        state_mask: u32,
    }

    #[repr(C)]
    struct FileTime {
        low: u32,
        high: u32,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> Handle;
        fn GetProcessTimes(
            process: Handle,
            creation_time: *mut FileTime,
            exit_time: *mut FileTime,
            kernel_time: *mut FileTime,
            user_time: *mut FileTime,
        ) -> i32;
        fn GetProcessAffinityMask(
            process: Handle,
            process_mask: *mut usize,
            system_mask: *mut usize,
        ) -> i32;
        fn SetProcessAffinityMask(process: Handle, process_mask: usize) -> i32;
        fn SetProcessInformation(
            process: Handle,
            information_class: i32,
            information: *const c_void,
            information_size: u32,
        ) -> i32;
        fn SetProcessDefaultCpuSets(
            process: Handle,
            cpu_set_ids: *const u32,
            cpu_set_id_count: u32,
        ) -> i32;
        fn GetProcessDefaultCpuSets(
            process: Handle,
            cpu_set_ids: *mut u32,
            cpu_set_id_count: u32,
            required_id_count: *mut u32,
        ) -> i32;
        fn IsProcessInJob(process: Handle, job: Handle, result: *mut i32) -> i32;
        fn QueryInformationJobObject(
            job: Handle,
            information_class: i32,
            information: *mut c_void,
            information_length: u32,
            returned_length: *mut u32,
        ) -> i32;
        fn GetCurrentProcessorNumberEx(processor_number: *mut ProcessorNumber);
        fn K32GetProcessMemoryInfo(
            process: Handle,
            counters: *mut ProcessMemoryCounters,
            size: u32,
        ) -> i32;
    }

    #[derive(Debug)]
    struct Arguments {
        warmups: usize,
        samples: usize,
        expected_logical_cpu: usize,
        expected_cpu_set_id: u32,
    }

    pub fn main() -> WorkerResult<()> {
        let arguments = parse_arguments()?;
        if arguments.warmups == 0 || arguments.samples == 0 {
            return Err("warmups and samples must be positive".to_owned());
        }
        enforce_controls(
            arguments.expected_logical_cpu,
            arguments.expected_cpu_set_id,
        )?;
        let mut observed_processors = Vec::new();
        observe_processor(arguments.expected_logical_cpu, &mut observed_processors)?;
        let request: CompileRequest =
            serde_json::from_reader(io::stdin().lock()).map_err(|error| error.to_string())?;
        for _ in 0..arguments.warmups {
            black_box(execute(&request)?);
            observe_processor(arguments.expected_logical_cpu, &mut observed_processors)?;
        }
        let maximum_sample_attempts = arguments
            .samples
            .checked_mul(MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER)
            .ok_or_else(|| "sample attempt limit overflow".to_owned())?;
        let mut accepted_samples = 0usize;
        let mut sample_attempts = 0usize;
        let mut checksum = 0usize;
        while accepted_samples < arguments.samples {
            if sample_attempts >= maximum_sample_attempts {
                return Err(format!(
                    "measurement interference prevented {} authentic samples within {maximum_sample_attempts} attempts",
                    arguments.samples
                ));
            }
            sample_attempts += 1;
            let cpu_started = process_cpu_time_nanoseconds()?;
            let started = Instant::now();
            checksum ^= black_box(execute(&request)?);
            let elapsed = u64::try_from(started.elapsed().as_nanos().max(1))
                .map_err(|_| "sample overflow".to_owned())?;
            let cpu_elapsed = u64::try_from(
                process_cpu_time_nanoseconds()?
                    .saturating_sub(cpu_started)
                    .max(1),
            )
            .map_err(|_| "CPU sample overflow".to_owned())?;
            observe_processor(arguments.expected_logical_cpu, &mut observed_processors)?;
            if elapsed.saturating_sub(cpu_elapsed) <= MAXIMUM_DESCHEDULING_NANOSECONDS {
                accepted_samples += 1;
            }
        }
        let peak_working_set_bytes = peak_working_set_bytes()?;
        println!(
            "{}",
            serde_json::to_string(&json!({
                "worker_contract": "isolated-peak-rss-v1",
                "effective_cpu_affinity": [arguments.expected_logical_cpu],
                "observed_processor_groups": [0],
                "observed_logical_processors": observed_processors,
                "peak_working_set_bytes": peak_working_set_bytes,
                "sample_attempts": sample_attempts,
                "checksum": checksum,
            }))
            .map_err(|error| error.to_string())?
        );
        Ok(())
    }

    fn parse_arguments() -> WorkerResult<Arguments> {
        let values = std::env::args().skip(1).collect::<Vec<_>>();
        let mut warmups = None;
        let mut samples = None;
        let mut expected_logical_cpu = None;
        let mut expected_cpu_set_id = None;
        let mut index = 0usize;
        while index < values.len() {
            let flag = &values[index];
            let value = values
                .get(index + 1)
                .ok_or_else(|| format!("missing value for {flag}"))?;
            match flag.as_str() {
                "--warmups" => warmups = Some(value.parse().map_err(|_| "invalid --warmups")?),
                "--samples" => samples = Some(value.parse().map_err(|_| "invalid --samples")?),
                "--expected-logical-cpu" => {
                    expected_logical_cpu = Some(
                        value
                            .parse()
                            .map_err(|_| "invalid --expected-logical-cpu")?,
                    )
                }
                "--expected-cpu-set-id" => {
                    expected_cpu_set_id =
                        Some(value.parse().map_err(|_| "invalid --expected-cpu-set-id")?)
                }
                _ => return Err(format!("unknown argument {flag}")),
            }
            index += 2;
        }
        Ok(Arguments {
            warmups: warmups.ok_or_else(|| "missing --warmups".to_owned())?,
            samples: samples.ok_or_else(|| "missing --samples".to_owned())?,
            expected_logical_cpu: expected_logical_cpu
                .ok_or_else(|| "missing --expected-logical-cpu".to_owned())?,
            expected_cpu_set_id: expected_cpu_set_id
                .ok_or_else(|| "missing --expected-cpu-set-id".to_owned())?,
        })
    }

    fn execute(request: &CompileRequest) -> WorkerResult<usize> {
        let result = strling_kernel::compile(request, None).map_err(|error| error.to_string())?;
        serde_json::to_vec(&result)
            .map(|bytes| bytes.len())
            .map_err(|error| error.to_string())
    }

    fn current_process() -> Handle {
        unsafe { GetCurrentProcess() }
    }

    fn last_error(label: &str) -> String {
        format!("{label} failed: {}", io::Error::last_os_error())
    }

    fn enforce_controls(expected_cpu: usize, expected_set_id: u32) -> WorkerResult<()> {
        if expected_cpu >= usize::BITS as usize {
            return Err("logical CPU is outside the affinity mask".to_owned());
        }
        if unsafe { SetProcessAffinityMask(current_process(), 1usize << expected_cpu) } == 0 {
            return Err(last_error("SetProcessAffinityMask"));
        }
        if unsafe { SetProcessDefaultCpuSets(current_process(), &expected_set_id, 1) } == 0 {
            return Err(last_error("SetProcessDefaultCpuSets"));
        }
        let mut process_mask = 0usize;
        let mut system_mask = 0usize;
        if unsafe { GetProcessAffinityMask(current_process(), &mut process_mask, &mut system_mask) }
            == 0
        {
            return Err(last_error("GetProcessAffinityMask"));
        }
        let mut required = 0u32;
        let first = unsafe {
            GetProcessDefaultCpuSets(current_process(), std::ptr::null_mut(), 0, &mut required)
        };
        if first == 0 && required == 0 {
            return Err(last_error("GetProcessDefaultCpuSets(size)"));
        }
        let mut default_sets = vec![0u32; required as usize];
        if required == 0
            || unsafe {
                GetProcessDefaultCpuSets(
                    current_process(),
                    default_sets.as_mut_ptr(),
                    default_sets.len() as u32,
                    &mut required,
                )
            } == 0
        {
            return Err(last_error("GetProcessDefaultCpuSets"));
        }
        default_sets.truncate(required as usize);
        if process_mask != 1usize << expected_cpu || default_sets != [expected_set_id] {
            return Err("memory worker placement controls are not exact".to_owned());
        }
        let power = ProcessPowerThrottlingState {
            version: PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            control_mask: PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            state_mask: 0,
        };
        if unsafe {
            SetProcessInformation(
                current_process(),
                PROCESS_POWER_THROTTLING_INFORMATION,
                (&power as *const ProcessPowerThrottlingState).cast(),
                std::mem::size_of::<ProcessPowerThrottlingState>() as u32,
            )
        } == 0
        {
            return Err(last_error("SetProcessInformation(ProcessPowerThrottling)"));
        }
        require_unlimited_cpu_quota()
    }

    fn require_unlimited_cpu_quota() -> WorkerResult<()> {
        let mut in_job = 0i32;
        if unsafe { IsProcessInJob(current_process(), std::ptr::null_mut(), &mut in_job) } == 0 {
            return Err(last_error("IsProcessInJob"));
        }
        if in_job == 0 {
            return Ok(());
        }
        let mut values = [0u32; 2];
        let mut returned = 0u32;
        if unsafe {
            QueryInformationJobObject(
                std::ptr::null_mut(),
                JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION,
                values.as_mut_ptr().cast(),
                std::mem::size_of_val(&values) as u32,
                &mut returned,
            )
        } == 0
        {
            return Err(last_error("QueryInformationJobObject(CPU rate)"));
        }
        if values[0] & JOB_OBJECT_CPU_RATE_CONTROL_ENABLE != 0 {
            return Err("the Windows job imposes a CPU rate limit".to_owned());
        }
        Ok(())
    }

    fn observe_processor(expected: usize, observed: &mut Vec<usize>) -> WorkerResult<()> {
        let mut processor = ProcessorNumber {
            group: 0,
            number: 0,
            reserved: 0,
        };
        unsafe { GetCurrentProcessorNumberEx(&mut processor) };
        if processor.group != 0 || processor.number as usize != expected {
            return Err("memory worker executed outside the selected logical CPU".to_owned());
        }
        if !observed.contains(&expected) {
            observed.push(expected);
        }
        Ok(())
    }

    fn process_cpu_time_nanoseconds() -> WorkerResult<u128> {
        let mut creation = FileTime { low: 0, high: 0 };
        let mut exit = FileTime { low: 0, high: 0 };
        let mut kernel = FileTime { low: 0, high: 0 };
        let mut user = FileTime { low: 0, high: 0 };
        if unsafe {
            GetProcessTimes(
                current_process(),
                &mut creation,
                &mut exit,
                &mut kernel,
                &mut user,
            )
        } == 0
        {
            return Err(last_error("GetProcessTimes"));
        }
        let kernel_ticks = (u64::from(kernel.high) << 32) | u64::from(kernel.low);
        let user_ticks = (u64::from(user.high) << 32) | u64::from(user.low);
        Ok(u128::from(kernel_ticks.saturating_add(user_ticks)) * 100)
    }

    fn peak_working_set_bytes() -> WorkerResult<u64> {
        let mut counters = ProcessMemoryCounters {
            cb: std::mem::size_of::<ProcessMemoryCounters>() as u32,
            page_fault_count: 0,
            peak_working_set_size: 0,
            working_set_size: 0,
            quota_peak_paged_pool_usage: 0,
            quota_paged_pool_usage: 0,
            quota_peak_non_paged_pool_usage: 0,
            quota_non_paged_pool_usage: 0,
            pagefile_usage: 0,
            peak_pagefile_usage: 0,
        };
        if unsafe { K32GetProcessMemoryInfo(current_process(), &mut counters, counters.cb) } == 0 {
            return Err(last_error("K32GetProcessMemoryInfo"));
        }
        u64::try_from(counters.peak_working_set_size)
            .map_err(|_| "peak working set overflow".to_owned())
    }
}

#[cfg(target_os = "windows")]
fn main() {
    if let Err(error) = worker::main() {
        eprintln!("strling-performance-memory-worker: {error}");
        std::process::exit(1);
    }
}

#[cfg(not(target_os = "windows"))]
fn main() {
    eprintln!("strling-performance-memory-worker: Windows-only");
    std::process::exit(1);
}
