use std::collections::BTreeSet;
use std::env;
use std::hint::black_box;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

use serde_json::{json, Value};
use strling_interop::execute_bytes;
use strling_kernel::capability_evaluation::evaluate_capabilities;
use strling_kernel::ecmascript_lowering::lower_ecmascript;
use strling_kernel::ecmascript_serialization::serialize_ecmascript;
use strling_kernel::editor_intelligence::{
    project as project_editor, EditorFrontend, EditorRequest, EDITOR_EVIDENCE_CONTRACT_VERSION,
};
use strling_kernel::normalization::normalize;
use strling_kernel::portability_planning::plan_portability;
use strling_kernel::protocol::CompileRequest;
use strling_kernel::python_re_lowering::lower_python_re;
use strling_kernel::python_re_serialization::serialize_python_re;
use strling_kernel::regex_frontend;
use strling_kernel::safety_analysis::analyze_safety;
use strling_kernel::semantic::SemanticProgram;
use strling_kernel::semantic_analysis::analyze;
use strling_kernel::semantic_frontend;
use strling_kernel::source::SourceDocument;
use strling_kernel::structural_analysis::analyze_structure;
use strling_kernel::target::TargetProfile;
use strling_kernel::target_lowering::lower_pcre2;
use strling_kernel::target_serialization::serialize_pcre2;
use strling_kernel::validation::Validate;

type RunResult<T> = Result<T, String>;
type PreparedOperation = Box<dyn Fn() -> RunResult<usize>>;

const RUNNER_VERSION: &str = "1.8.0";
const MAXIMUM_DESCHEDULING_NANOSECONDS: u64 = 50_000_000;
const MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER: usize = 2;

#[derive(Debug)]
struct Arguments {
    operation: String,
    fixture: String,
    warmups: usize,
    samples: usize,
    batch_iterations: Option<usize>,
    minimum_sample_nanoseconds: Option<u64>,
    maximum_batch_iterations: usize,
    expected_logical_cpu: Option<usize>,
    kernel_bin: Option<PathBuf>,
    ping: bool,
}

#[derive(Debug)]
struct ExecutionResource {
    platform: String,
    placement_mechanism: String,
    cgroup_path: String,
    effective_cpuset: String,
    cpu_quota: String,
    clocksource: String,
    processor_group: Option<u16>,
    selected_cpu_set_id: Option<u32>,
    cpu_set_allocation_state: Value,
    timer_source: String,
    process_power_policy: Value,
}

#[derive(Clone)]
struct MaterializedFixture {
    id: String,
    source: Option<String>,
    source_document: Option<SourceDocument>,
    semantic: SemanticProgram,
    request: CompileRequest,
    request_bytes: Vec<u8>,
    interop_request: Vec<u8>,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("strling-performance-runner: {error}");
        std::process::exit(1);
    }
}

fn run() -> RunResult<()> {
    let arguments = parse_arguments()?;
    if arguments.ping {
        println!(
            "{}",
            json!({"runner_version": RUNNER_VERSION, "status": "passed"})
        );
        return Ok(());
    }
    if arguments.warmups == 0 || arguments.samples == 0 {
        return Err("warmups and samples must be positive".to_owned());
    }
    let execution_resource = match arguments.expected_logical_cpu {
        Some(expected) => effective_execution_resource(expected)?,
        None => ExecutionResource {
            platform: String::new(),
            placement_mechanism: String::new(),
            cgroup_path: String::new(),
            effective_cpuset: String::new(),
            cpu_quota: String::new(),
            clocksource: String::new(),
            processor_group: None,
            selected_cpu_set_id: None,
            cpu_set_allocation_state: Value::Null,
            timer_source: String::new(),
            process_power_policy: Value::Null,
        },
    };
    let effective_cpu_affinity = match arguments.expected_logical_cpu {
        Some(expected) => {
            let effective = effective_cpu_affinity()?;
            if effective != [expected] {
                return Err(format!(
                    "effective CPU affinity {} does not equal expected logical CPU {expected}",
                    format_cpu_set(&effective)
                ));
            }
            effective
        }
        None => Vec::new(),
    };
    let mut observed_processor_groups = BTreeSet::new();
    let mut observed_logical_processors = BTreeSet::new();
    observe_execution_processor(
        &mut observed_processor_groups,
        &mut observed_logical_processors,
    )?;
    let fixture = materialize_fixture(&arguments.fixture)?;
    let operation = prepare_operation(
        &arguments.operation,
        &fixture,
        arguments.kernel_bin.as_deref(),
    )?;
    let control_operation = if arguments.operation == "latency:cli-startup" {
        Some(prepare_cli_launch_control(arguments.kernel_bin.as_deref())?)
    } else {
        None
    };
    let batch_iterations = match (
        arguments.batch_iterations,
        arguments.minimum_sample_nanoseconds,
    ) {
        (Some(batch_iterations), None) => batch_iterations,
        (None, Some(minimum_sample_nanoseconds)) => select_batch_iterations(
            &operation,
            minimum_sample_nanoseconds,
            arguments.maximum_batch_iterations,
        )?,
        (None, None) => 1,
        (Some(_), Some(_)) => {
            return Err(
                "--batch-iterations and --minimum-sample-nanoseconds are mutually exclusive"
                    .to_owned(),
            )
        }
    };
    if batch_iterations == 0 || batch_iterations > arguments.maximum_batch_iterations {
        return Err("batch iterations are outside the governed range".to_owned());
    }
    for _ in 0..arguments.warmups {
        black_box(execute_batch(&operation, batch_iterations)?);
        observe_execution_processor(
            &mut observed_processor_groups,
            &mut observed_logical_processors,
        )?;
    }
    let mut samples = Vec::with_capacity(arguments.samples);
    let mut batch_elapsed_samples = Vec::with_capacity(arguments.samples);
    let mut process_cpu_samples = Vec::with_capacity(arguments.samples);
    let mut process_cpu_batch_elapsed_samples = Vec::with_capacity(arguments.samples);
    let mut process_cpu_utilization_basis_points = Vec::with_capacity(arguments.samples);
    let mut control_samples = Vec::with_capacity(arguments.samples);
    let mut control_batch_elapsed_samples = Vec::with_capacity(arguments.samples);
    let mut control_process_cpu_samples = Vec::with_capacity(arguments.samples);
    let mut control_process_cpu_batch_elapsed_samples = Vec::with_capacity(arguments.samples);
    let mut control_process_cpu_utilization_basis_points = Vec::with_capacity(arguments.samples);
    let mut rejected_batch_elapsed_samples = Vec::new();
    let mut rejected_process_cpu_batch_elapsed_samples = Vec::new();
    let mut rejected_process_cpu_utilization_basis_points = Vec::new();
    let maximum_sample_attempts = arguments
        .samples
        .checked_mul(MAXIMUM_SAMPLE_ATTEMPT_MULTIPLIER)
        .ok_or_else(|| "sample attempt limit overflow".to_owned())?;
    let mut sample_attempts = 0usize;
    let mut checksum = 0usize;
    let divisor = u64::try_from(batch_iterations).map_err(|_| "batch overflow")?;
    if let Some(control) = &control_operation {
        for _ in 0..arguments.warmups {
            black_box(execute_batch(control, batch_iterations)?);
            observe_execution_processor(
                &mut observed_processor_groups,
                &mut observed_logical_processors,
            )?;
        }
    }
    let mut measure = |prepared: &PreparedOperation| -> RunResult<(u64, u64, u64, u64, u64)> {
        let cpu_started = process_cpu_time_nanoseconds()?;
        let started = Instant::now();
        checksum ^= black_box(execute_batch(prepared, batch_iterations)?);
        let nanoseconds = started.elapsed().as_nanos().max(1);
        let cpu_nanoseconds = process_cpu_time_nanoseconds()?
            .saturating_sub(cpu_started)
            .max(1);
        let batch_elapsed = u64::try_from(nanoseconds).map_err(|_| "sample overflow")?;
        let batch_cpu = u64::try_from(cpu_nanoseconds).map_err(|_| "CPU sample overflow")?;
        let normalized = batch_elapsed
            .saturating_add(divisor / 2)
            .checked_div(divisor)
            .ok_or_else(|| "batch divisor is zero".to_owned())?
            .max(1);
        let normalized_cpu = batch_cpu
            .saturating_add(divisor / 2)
            .checked_div(divisor)
            .ok_or_else(|| "batch divisor is zero".to_owned())?
            .max(1);
        let utilization_basis_points =
            u64::try_from((u128::from(batch_cpu) * 10_000 / u128::from(batch_elapsed)).min(10_000))
                .map_err(|_| "CPU utilization overflow".to_owned())?;
        observe_execution_processor(
            &mut observed_processor_groups,
            &mut observed_logical_processors,
        )?;
        Ok((
            normalized,
            batch_elapsed,
            normalized_cpu,
            batch_cpu,
            utilization_basis_points,
        ))
    };
    if let Some(control) = &control_operation {
        for sample_index in 0..arguments.samples {
            sample_attempts += 1;
            let (request, control_sample) = if sample_index % 2 == 0 {
                (measure(&operation)?, measure(control)?)
            } else {
                let control_sample = measure(control)?;
                (measure(&operation)?, control_sample)
            };
            samples.push(request.0);
            batch_elapsed_samples.push(request.1);
            process_cpu_samples.push(request.2);
            process_cpu_batch_elapsed_samples.push(request.3);
            process_cpu_utilization_basis_points.push(request.4);
            control_samples.push(control_sample.0);
            control_batch_elapsed_samples.push(control_sample.1);
            control_process_cpu_samples.push(control_sample.2);
            control_process_cpu_batch_elapsed_samples.push(control_sample.3);
            control_process_cpu_utilization_basis_points.push(control_sample.4);
        }
    } else {
        while samples.len() < arguments.samples {
            if sample_attempts >= maximum_sample_attempts {
                return Err(format!(
                    "measurement interference prevented {} authentic samples within {maximum_sample_attempts} attempts",
                    arguments.samples
                ));
            }
            sample_attempts += 1;
            let sample = measure(&operation)?;
            if !sample_is_authentic(sample.1, sample.3) {
                rejected_batch_elapsed_samples.push(sample.1);
                rejected_process_cpu_batch_elapsed_samples.push(sample.3);
                rejected_process_cpu_utilization_basis_points.push(sample.4);
                continue;
            }
            samples.push(sample.0);
            batch_elapsed_samples.push(sample.1);
            process_cpu_samples.push(sample.2);
            process_cpu_batch_elapsed_samples.push(sample.3);
            process_cpu_utilization_basis_points.push(sample.4);
        }
    }
    verify_execution_resource(&execution_resource, arguments.expected_logical_cpu)?;
    let peak_working_set_bytes = peak_working_set_bytes()?;
    println!(
        "{}",
        serde_json::to_string(&json!({
            "runner_version": RUNNER_VERSION,
            "operation_id": arguments.operation,
            "fixture_id": fixture.id,
            "unit": "nanoseconds",
            "warmup_iterations": arguments.warmups,
            "sample_iterations": arguments.samples,
            "batch_iterations": batch_iterations,
            "selected_logical_cpu": arguments.expected_logical_cpu,
            "effective_cpu_affinity": effective_cpu_affinity,
            "platform": execution_resource.platform,
            "placement_mechanism": execution_resource.placement_mechanism,
            "effective_cpuset": execution_resource.effective_cpuset,
            "cgroup_path": execution_resource.cgroup_path,
            "cpu_quota": execution_resource.cpu_quota,
            "clocksource": execution_resource.clocksource,
            "processor_group": execution_resource.processor_group,
            "selected_cpu_set_id": execution_resource.selected_cpu_set_id,
            "cpu_set_allocation_state": execution_resource.cpu_set_allocation_state,
            "timer_source": execution_resource.timer_source,
            "process_power_policy": execution_resource.process_power_policy,
            "observed_processor_groups": observed_processor_groups,
            "observed_logical_processors": observed_logical_processors,
            "peak_working_set_bytes": peak_working_set_bytes,
            "batch_elapsed_samples": batch_elapsed_samples,
            "samples": samples,
            "process_cpu_batch_elapsed_samples": process_cpu_batch_elapsed_samples,
            "process_cpu_samples": process_cpu_samples,
            "process_cpu_utilization_basis_points": process_cpu_utilization_basis_points,
            "maximum_descheduling_nanoseconds": MAXIMUM_DESCHEDULING_NANOSECONDS,
            "maximum_sample_attempts": maximum_sample_attempts,
            "sample_attempts": sample_attempts,
            "rejected_batch_elapsed_samples": rejected_batch_elapsed_samples,
            "rejected_process_cpu_batch_elapsed_samples": rejected_process_cpu_batch_elapsed_samples,
            "rejected_process_cpu_utilization_basis_points": rejected_process_cpu_utilization_basis_points,
            "control_batch_elapsed_samples": control_batch_elapsed_samples,
            "control_samples": control_samples,
            "control_process_cpu_batch_elapsed_samples": control_process_cpu_batch_elapsed_samples,
            "control_process_cpu_samples": control_process_cpu_samples,
            "control_process_cpu_utilization_basis_points": control_process_cpu_utilization_basis_points,
            "checksum": checksum,
        }))
        .map_err(|error| error.to_string())?
    );
    Ok(())
}

fn sample_is_authentic(wall_nanoseconds: u64, process_cpu_nanoseconds: u64) -> bool {
    wall_nanoseconds.saturating_sub(process_cpu_nanoseconds) <= MAXIMUM_DESCHEDULING_NANOSECONDS
}

fn parse_arguments() -> RunResult<Arguments> {
    let values = env::args().skip(1).collect::<Vec<_>>();
    if values == ["--ping"] {
        return Ok(Arguments {
            operation: String::new(),
            fixture: String::new(),
            warmups: 1,
            samples: 1,
            batch_iterations: None,
            minimum_sample_nanoseconds: None,
            maximum_batch_iterations: 1,
            expected_logical_cpu: None,
            kernel_bin: None,
            ping: true,
        });
    }
    let mut operation = None;
    let mut fixture = None;
    let mut warmups = None;
    let mut samples = None;
    let mut batch_iterations = None;
    let mut minimum_sample_nanoseconds = None;
    let mut maximum_batch_iterations = None;
    let mut expected_logical_cpu = None;
    let mut kernel_bin = None;
    let mut index = 0;
    while index < values.len() {
        let flag = &values[index];
        let value = values
            .get(index + 1)
            .ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--operation" => operation = Some(value.clone()),
            "--fixture" => fixture = Some(value.clone()),
            "--warmups" => warmups = Some(value.parse().map_err(|_| "invalid --warmups")?),
            "--samples" => samples = Some(value.parse().map_err(|_| "invalid --samples")?),
            "--batch-iterations" => {
                batch_iterations = Some(value.parse().map_err(|_| "invalid --batch-iterations")?)
            }
            "--minimum-sample-nanoseconds" => {
                minimum_sample_nanoseconds = Some(
                    value
                        .parse()
                        .map_err(|_| "invalid --minimum-sample-nanoseconds")?,
                )
            }
            "--maximum-batch-iterations" => {
                maximum_batch_iterations = Some(
                    value
                        .parse()
                        .map_err(|_| "invalid --maximum-batch-iterations")?,
                )
            }
            "--expected-logical-cpu" => {
                expected_logical_cpu = Some(
                    value
                        .parse()
                        .map_err(|_| "invalid --expected-logical-cpu")?,
                )
            }
            "--kernel-bin" => kernel_bin = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown argument {flag}")),
        }
        index += 2;
    }
    Ok(Arguments {
        operation: operation.ok_or_else(|| "missing --operation".to_owned())?,
        fixture: fixture.ok_or_else(|| "missing --fixture".to_owned())?,
        warmups: warmups.ok_or_else(|| "missing --warmups".to_owned())?,
        samples: samples.ok_or_else(|| "missing --samples".to_owned())?,
        batch_iterations,
        minimum_sample_nanoseconds,
        maximum_batch_iterations: maximum_batch_iterations.unwrap_or(1),
        expected_logical_cpu,
        kernel_bin,
        ping: false,
    })
}

#[cfg(target_os = "linux")]
fn effective_cpu_affinity() -> RunResult<Vec<usize>> {
    let status = std::fs::read_to_string("/proc/self/status")
        .map_err(|error| format!("read /proc/self/status: {error}"))?;
    let value = status
        .lines()
        .find_map(|line| line.strip_prefix("Cpus_allowed_list:"))
        .ok_or_else(|| "Cpus_allowed_list is absent from /proc/self/status".to_owned())?;
    parse_cpu_set(value.trim())
}

#[cfg(target_os = "linux")]
fn effective_execution_resource(expected: usize) -> RunResult<ExecutionResource> {
    let cgroup = std::fs::read_to_string("/proc/self/cgroup")
        .map_err(|error| format!("read /proc/self/cgroup: {error}"))?;
    let cgroup_path = cgroup
        .lines()
        .find_map(|line| line.strip_prefix("0::"))
        .ok_or_else(|| "unified cgroup v2 path is absent".to_owned())?;
    let cgroup_path = if cgroup_path.is_empty() {
        "/"
    } else {
        cgroup_path
    };
    let resource_root = Path::new("/sys/fs/cgroup").join(cgroup_path.trim_start_matches('/'));
    let effective_cpuset = std::fs::read_to_string(resource_root.join("cpuset.cpus.effective"))
        .map_err(|error| format!("read cgroup cpuset: {error}"))?
        .trim()
        .to_owned();
    if parse_cpu_set(&effective_cpuset)? != [expected] {
        return Err(format!(
            "effective cgroup cpuset {effective_cpuset} does not equal expected logical CPU {expected}"
        ));
    }
    let cpu_quota = std::fs::read_to_string(resource_root.join("cpu.max"))
        .map_err(|error| format!("read cgroup cpu.max: {error}"))?
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if !cpu_quota.starts_with("max ") {
        return Err(format!("governed CPU quota is not unlimited: {cpu_quota}"));
    }
    let clocksource =
        std::fs::read_to_string("/sys/devices/system/clocksource/clocksource0/current_clocksource")
            .map_err(|error| format!("read clocksource: {error}"))?
            .trim()
            .to_owned();
    if !matches!(clocksource.as_str(), "tsc" | "hyperv_clocksource_tsc_page") {
        return Err(format!("unsupported governed clocksource {clocksource}"));
    }
    Ok(ExecutionResource {
        platform: "linux".to_owned(),
        placement_mechanism: "cgroup-v2-cpuset".to_owned(),
        cgroup_path: cgroup_path.to_owned(),
        effective_cpuset,
        cpu_quota,
        timer_source: clocksource.clone(),
        clocksource,
        processor_group: None,
        selected_cpu_set_id: None,
        cpu_set_allocation_state: Value::Null,
        process_power_policy: Value::Null,
    })
}

#[cfg(target_os = "linux")]
fn verify_execution_resource(
    _resource: &ExecutionResource,
    _expected: Option<usize>,
) -> RunResult<()> {
    Ok(())
}

#[cfg(target_os = "linux")]
fn observe_execution_processor(
    groups: &mut BTreeSet<u16>,
    processors: &mut BTreeSet<usize>,
) -> RunResult<()> {
    groups.insert(0);
    processors.extend(effective_cpu_affinity()?);
    Ok(())
}

#[cfg(target_os = "linux")]
fn peak_working_set_bytes() -> RunResult<Option<u64>> {
    Ok(None)
}

#[cfg(target_os = "linux")]
fn process_cpu_time_nanoseconds() -> RunResult<u128> {
    #[repr(C)]
    struct Timespec {
        seconds: i64,
        nanoseconds: i64,
    }

    extern "C" {
        fn clock_gettime(clock_id: i32, time: *mut Timespec) -> i32;
    }

    const CLOCK_PROCESS_CPUTIME_ID: i32 = 2;
    let mut time = Timespec {
        seconds: 0,
        nanoseconds: 0,
    };
    if unsafe { clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &mut time) } != 0 {
        return Err(format!(
            "clock_gettime(CLOCK_PROCESS_CPUTIME_ID) failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    if time.seconds < 0 || !(0..1_000_000_000).contains(&time.nanoseconds) {
        return Err("process CPU clock returned an invalid value".to_owned());
    }
    Ok((time.seconds as u128) * 1_000_000_000 + time.nanoseconds as u128)
}

#[cfg(target_os = "windows")]
mod windows_placement {
    use super::{ExecutionResource, RunResult};
    use serde_json::json;
    use std::ffi::c_void;

    type Handle = *mut c_void;

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
        fn GetActiveProcessorGroupCount() -> u16;
        fn GetActiveProcessorCount(group: u16) -> u32;
        fn GetSystemCpuSetInformation(
            information: *mut c_void,
            buffer_length: u32,
            returned_length: *mut u32,
            process: Handle,
            flags: u32,
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
        fn QueryPerformanceFrequency(frequency: *mut i64) -> i32;
        fn GetCurrentProcessorNumberEx(processor_number: *mut ProcessorNumber);
        fn K32GetProcessMemoryInfo(
            process: Handle,
            counters: *mut ProcessMemoryCounters,
            size: u32,
        ) -> i32;
    }

    fn last_error(label: &str) -> String {
        format!("{label} failed: {}", std::io::Error::last_os_error())
    }

    fn current_process() -> Handle {
        unsafe { GetCurrentProcess() }
    }

    pub fn affinity() -> RunResult<Vec<usize>> {
        let mut process_mask = 0usize;
        let mut system_mask = 0usize;
        if unsafe { GetProcessAffinityMask(current_process(), &mut process_mask, &mut system_mask) }
            == 0
        {
            return Err(last_error("GetProcessAffinityMask"));
        }
        Ok((0..usize::BITS as usize)
            .filter(|index| process_mask & (1usize << index) != 0)
            .collect())
    }

    pub fn process_cpu_time_nanoseconds() -> RunResult<u128> {
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

    fn cpu_set_state(expected: usize, process: Handle) -> RunResult<(u32, u8, u8, u8, u64)> {
        let mut required = 0u32;
        unsafe { GetSystemCpuSetInformation(std::ptr::null_mut(), 0, &mut required, process, 0) };
        if required == 0 {
            return Err(last_error("GetSystemCpuSetInformation(size)"));
        }
        let mut buffer = vec![0u8; required as usize];
        if unsafe {
            GetSystemCpuSetInformation(
                buffer.as_mut_ptr().cast(),
                required,
                &mut required,
                process,
                0,
            )
        } == 0
        {
            return Err(last_error("GetSystemCpuSetInformation"));
        }
        let mut offset = 0usize;
        while offset < required as usize {
            if required as usize - offset < 32 {
                return Err("truncated Windows CPU-set record".to_owned());
            }
            let size = u32::from_le_bytes(buffer[offset..offset + 4].try_into().unwrap()) as usize;
            let record_type =
                u32::from_le_bytes(buffer[offset + 4..offset + 8].try_into().unwrap());
            if size < 8 || offset + size > required as usize {
                return Err("invalid Windows CPU-set record size".to_owned());
            }
            if record_type == 0 {
                let id = u32::from_le_bytes(buffer[offset + 8..offset + 12].try_into().unwrap());
                let group =
                    u16::from_le_bytes(buffer[offset + 12..offset + 14].try_into().unwrap());
                let logical = buffer[offset + 14];
                let core = buffer[offset + 15];
                let efficiency = buffer[offset + 18];
                let flags = buffer[offset + 19];
                let allocation_tag =
                    u64::from_le_bytes(buffer[offset + 24..offset + 32].try_into().unwrap());
                if group == 0 && logical as usize == expected {
                    return Ok((id, core, efficiency, flags, allocation_tag));
                }
            }
            offset += size;
        }
        Err(format!("Windows CPU set for group 0:{expected} is absent"))
    }

    fn cpu_set_allocation_state(flags: u8, allocation_tag: u64) -> RunResult<serde_json::Value> {
        let allocated = flags & 0x02 != 0;
        let allocated_to_target_process = flags & 0x04 != 0;
        if allocated_to_target_process && !allocated {
            return Err("Windows reported an inconsistent CPU-set allocation state".to_owned());
        }
        if allocated && !allocated_to_target_process {
            return Err("selected Windows CPU set is reserved to another process".to_owned());
        }
        Ok(json!({
            "allocated": allocated,
            "allocated_to_target_process": allocated_to_target_process,
            "realtime": flags & 0x08 != 0,
            "allocation_tag": format!("0x{allocation_tag:016x}"),
        }))
    }

    fn default_cpu_sets() -> RunResult<Vec<u32>> {
        let mut required = 0u32;
        let first = unsafe {
            GetProcessDefaultCpuSets(current_process(), std::ptr::null_mut(), 0, &mut required)
        };
        if first == 0 && required == 0 {
            return Err(last_error("GetProcessDefaultCpuSets(size)"));
        }
        if required == 0 {
            return Ok(Vec::new());
        }
        let mut values = vec![0u32; required as usize];
        if unsafe {
            GetProcessDefaultCpuSets(
                current_process(),
                values.as_mut_ptr(),
                values.len() as u32,
                &mut required,
            )
        } == 0
        {
            return Err(last_error("GetProcessDefaultCpuSets"));
        }
        values.truncate(required as usize);
        Ok(values)
    }

    fn require_unlimited_cpu_quota() -> RunResult<()> {
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

    fn enforce_high_qos() -> RunResult<serde_json::Value> {
        let state = ProcessPowerThrottlingState {
            version: PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            control_mask: PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            state_mask: 0,
        };
        if unsafe {
            SetProcessInformation(
                current_process(),
                PROCESS_POWER_THROTTLING_INFORMATION,
                (&state as *const ProcessPowerThrottlingState).cast(),
                std::mem::size_of::<ProcessPowerThrottlingState>() as u32,
            )
        } == 0
        {
            return Err(last_error("SetProcessInformation(ProcessPowerThrottling)"));
        }
        Ok(json!({
            "api": "SetProcessInformation(ProcessPowerThrottling)",
            "version": PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            "control_mask": PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            "state_mask": 0,
            "execution_speed_policy": "high-qos",
            "enforcement_result": "success",
        }))
    }

    pub fn enforce(expected: usize) -> RunResult<ExecutionResource> {
        let groups = unsafe { GetActiveProcessorGroupCount() };
        if groups != 1 {
            return Err("the governed Windows runner requires one processor group".to_owned());
        }
        let active = unsafe { GetActiveProcessorCount(0) } as usize;
        if expected >= active || expected >= usize::BITS as usize {
            return Err(format!(
                "logical processor {expected} is outside processor group 0"
            ));
        }
        let (set_id, core, efficiency, _, _) = cpu_set_state(expected, std::ptr::null_mut())?;
        if unsafe { SetProcessAffinityMask(current_process(), 1usize << expected) } == 0 {
            return Err(last_error("SetProcessAffinityMask"));
        }
        if unsafe { SetProcessDefaultCpuSets(current_process(), &set_id, 1) } == 0 {
            return Err(last_error("SetProcessDefaultCpuSets"));
        }
        if affinity()? != [expected] || default_cpu_sets()? != [set_id] {
            return Err("Windows affinity or CPU-set placement did not remain exact".to_owned());
        }
        let (reserved_set_id, reserved_core, reserved_efficiency, flags, allocation_tag) =
            cpu_set_state(expected, current_process())?;
        if (reserved_set_id, reserved_core, reserved_efficiency) != (set_id, core, efficiency) {
            return Err("Windows CPU-set topology changed during placement".to_owned());
        }
        let cpu_set_allocation_state = cpu_set_allocation_state(flags, allocation_tag)?;
        let process_power_policy = enforce_high_qos()?;
        require_unlimited_cpu_quota()?;
        let mut frequency = 0i64;
        if unsafe { QueryPerformanceFrequency(&mut frequency) } == 0 || frequency <= 0 {
            return Err(last_error("QueryPerformanceFrequency"));
        }
        Ok(ExecutionResource {
            platform: "windows".to_owned(),
            placement_mechanism: "process-affinity-cpu-sets-supported-controls".to_owned(),
            cgroup_path: String::new(),
            effective_cpuset: format!(
                "group-0:logical-{expected}:cpu-set-{set_id}:core-{core}:efficiency-{efficiency}"
            ),
            cpu_quota: "unlimited".to_owned(),
            clocksource: String::new(),
            processor_group: Some(0),
            selected_cpu_set_id: Some(set_id),
            cpu_set_allocation_state,
            timer_source: format!("QueryPerformanceCounter:{frequency}"),
            process_power_policy,
        })
    }

    pub fn verify_cpu_set_allocation_state(
        expected: usize,
        expected_set_id: Option<u32>,
        expected_state: &serde_json::Value,
    ) -> RunResult<()> {
        let (set_id, _, _, flags, allocation_tag) = cpu_set_state(expected, current_process())?;
        let observed = cpu_set_allocation_state(flags, allocation_tag)?;
        if Some(set_id) != expected_set_id || &observed != expected_state {
            return Err("Windows CPU-set allocation state changed during measurement".to_owned());
        }
        Ok(())
    }

    pub fn current_processor() -> (u16, usize) {
        let mut number = ProcessorNumber {
            group: 0,
            number: 0,
            reserved: 0,
        };
        unsafe { GetCurrentProcessorNumberEx(&mut number) };
        (number.group, number.number as usize)
    }

    pub fn peak_working_set_bytes() -> RunResult<u64> {
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

    #[cfg(test)]
    mod tests {
        use super::cpu_set_allocation_state;

        #[test]
        fn cpu_set_allocation_state_accepts_available_controls() {
            let ordinary = cpu_set_allocation_state(0x00, 0).unwrap();
            assert_eq!(ordinary["allocated"], false);
            assert_eq!(ordinary["allocated_to_target_process"], false);
            let accepted = cpu_set_allocation_state(0x06, 0xa11c).unwrap();
            assert_eq!(accepted["allocated"], true);
            assert_eq!(accepted["allocated_to_target_process"], true);
            assert_eq!(accepted["allocation_tag"], "0x000000000000a11c");
            assert!(cpu_set_allocation_state(0x07, 0).is_ok());
            assert!(cpu_set_allocation_state(0x02, 0).is_err());
            assert!(cpu_set_allocation_state(0x04, 0).is_err());
        }
    }
}

#[cfg(target_os = "windows")]
fn effective_cpu_affinity() -> RunResult<Vec<usize>> {
    windows_placement::affinity()
}

#[cfg(target_os = "windows")]
fn effective_execution_resource(expected: usize) -> RunResult<ExecutionResource> {
    windows_placement::enforce(expected)
}

#[cfg(target_os = "windows")]
fn verify_execution_resource(
    resource: &ExecutionResource,
    expected: Option<usize>,
) -> RunResult<()> {
    let expected = expected.ok_or_else(|| "expected Windows logical CPU is absent".to_owned())?;
    windows_placement::verify_cpu_set_allocation_state(
        expected,
        resource.selected_cpu_set_id,
        &resource.cpu_set_allocation_state,
    )
}

#[cfg(target_os = "windows")]
fn observe_execution_processor(
    groups: &mut BTreeSet<u16>,
    processors: &mut BTreeSet<usize>,
) -> RunResult<()> {
    let (group, processor) = windows_placement::current_processor();
    groups.insert(group);
    processors.insert(processor);
    Ok(())
}

#[cfg(target_os = "windows")]
fn peak_working_set_bytes() -> RunResult<Option<u64>> {
    windows_placement::peak_working_set_bytes().map(Some)
}

#[cfg(target_os = "windows")]
fn process_cpu_time_nanoseconds() -> RunResult<u128> {
    windows_placement::process_cpu_time_nanoseconds()
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn effective_cpu_affinity() -> RunResult<Vec<usize>> {
    Err("governed CPU affinity requires native Linux or Windows".to_owned())
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn effective_execution_resource(_expected: usize) -> RunResult<ExecutionResource> {
    Err("governed execution resource requires native Linux or Windows".to_owned())
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn verify_execution_resource(
    _resource: &ExecutionResource,
    _expected: Option<usize>,
) -> RunResult<()> {
    Err("execution-resource verification is unavailable".to_owned())
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn observe_execution_processor(
    _groups: &mut BTreeSet<u16>,
    _processors: &mut BTreeSet<usize>,
) -> RunResult<()> {
    Err("execution processor observation is unavailable".to_owned())
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn peak_working_set_bytes() -> RunResult<Option<u64>> {
    Err("peak working set observation is unavailable".to_owned())
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn process_cpu_time_nanoseconds() -> RunResult<u128> {
    Err("process CPU-time observation is unavailable".to_owned())
}

#[allow(dead_code)]
fn parse_cpu_set(value: &str) -> RunResult<Vec<usize>> {
    if value.is_empty() {
        return Ok(Vec::new());
    }
    let mut cpus = Vec::new();
    for part in value.split(',') {
        let mut bounds = part.split('-');
        let start = bounds
            .next()
            .ok_or_else(|| "CPU range is empty".to_owned())?
            .parse::<usize>()
            .map_err(|_| format!("invalid CPU range {part}"))?;
        let end = bounds
            .next()
            .map(|bound| {
                bound
                    .parse::<usize>()
                    .map_err(|_| format!("invalid CPU range {part}"))
            })
            .transpose()?
            .unwrap_or(start);
        if bounds.next().is_some() || end < start {
            return Err(format!("invalid CPU range {part}"));
        }
        cpus.extend(start..=end);
    }
    cpus.sort_unstable();
    cpus.dedup();
    Ok(cpus)
}

fn format_cpu_set(cpus: &[usize]) -> String {
    cpus.iter()
        .map(usize::to_string)
        .collect::<Vec<_>>()
        .join(",")
}

fn execute_batch(operation: &PreparedOperation, iterations: usize) -> RunResult<usize> {
    let mut checksum = 0usize;
    for iteration in 0..iterations {
        checksum ^= black_box(operation()?).rotate_left((iteration % usize::BITS as usize) as u32);
    }
    Ok(checksum)
}

fn select_batch_iterations(
    operation: &PreparedOperation,
    minimum_sample_nanoseconds: u64,
    maximum_batch_iterations: usize,
) -> RunResult<usize> {
    select_batch_iterations_with(
        minimum_sample_nanoseconds,
        maximum_batch_iterations,
        |iterations| {
            let started = Instant::now();
            black_box(execute_batch(operation, iterations)?);
            Ok(started.elapsed().as_nanos().max(1))
        },
    )
}

fn select_batch_iterations_with(
    minimum_sample_nanoseconds: u64,
    maximum_batch_iterations: usize,
    mut measure: impl FnMut(usize) -> RunResult<u128>,
) -> RunResult<usize> {
    if minimum_sample_nanoseconds == 0 || maximum_batch_iterations == 0 {
        return Err("batch selection bounds must be positive".to_owned());
    }
    let target = u128::from(minimum_sample_nanoseconds);
    let mut iterations = 1usize;
    loop {
        let mut elapsed = measure(iterations)?.max(1);
        if elapsed >= target {
            let confirmation = measure(iterations)?.max(1);
            if confirmation >= target {
                return Ok(iterations);
            }
            elapsed = confirmation;
        }
        if iterations == maximum_batch_iterations {
            return Ok(iterations);
        }
        let proportional = (iterations as u128)
            .saturating_mul(target)
            .saturating_add(elapsed - 1)
            / elapsed;
        let proposed = proportional.max((iterations + 1) as u128);
        iterations = usize::try_from(proposed)
            .unwrap_or(maximum_batch_iterations)
            .min(maximum_batch_iterations);
    }
}

fn repository_root() -> PathBuf {
    env::current_dir()
        .expect("current directory")
        .canonicalize()
        .expect("repository root")
}

fn target_profile(file: &str) -> RunResult<TargetProfile> {
    let path = repository_root().join("spec/targets/profiles").join(file);
    let source = std::fs::read_to_string(&path)
        .map_err(|error| format!("read {}: {error}", path.display()))?;
    serde_json::from_str(&source).map_err(|error| format!("parse {}: {error}", path.display()))
}

fn semantic_document(source: &str) -> RunResult<SourceDocument> {
    serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "source_id": "src:performance.semantic",
        "specification_version": "1.0-draft.1",
        "frontend": {"id": "strling.semantic", "dialect_version": "1.0.0"},
        "display_name": "performance.strling",
        "content": {
            "kind": "inline",
            "encoding": "utf-8",
            "media_type": "text/x-strling-semantic",
            "text": source,
        },
        "provenance": {"kind": "authored", "description": "governed performance fixture"},
    }))
    .map_err(|error| error.to_string())
}

fn legacy_document(source: &str) -> RunResult<SourceDocument> {
    serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "source_id": "src:performance.legacy",
        "specification_version": "1.0-draft.1",
        "frontend": {"id": "strling.regex-compat", "dialect_version": "1.0.0"},
        "display_name": "performance.regex",
        "content": {
            "kind": "inline",
            "encoding": "utf-8",
            "media_type": "text/strling-regex",
            "text": source,
        },
        "provenance": {"kind": "imported"},
    }))
    .map_err(|error| error.to_string())
}

fn semantic_source(fixture: &str) -> RunResult<String> {
    let pattern = match fixture {
        "fixture:semantic-tiny" => "text \"a\";".to_owned(),
        "fixture:semantic-common" => {
            let mut items = Vec::new();
            for index in 0..12 {
                if index % 3 == 0 {
                    items.push("any character excluding line terminators;".to_owned());
                } else {
                    items.push(format!("text \"item-{index}\";"));
                }
            }
            format!("sequence {{ {} }}", items.join(" "))
        }
        "fixture:semantic-large" => {
            let items = (0..2048)
                .map(|index| {
                    if index % 2 == 0 {
                        format!("text \"item-{index:04}-xxxxxx\";")
                    } else {
                        "any character excluding line terminators;".to_owned()
                    }
                })
                .collect::<Vec<_>>();
            format!("sequence {{ {} }}", items.join(" "))
        }
        "fixture:semantic-pathological" => {
            let mut node = "text \"z\";".to_owned();
            for _ in 0..127 {
                node = format!("without backtracking {{ {node} }}");
            }
            node
        }
        _ => return Err(format!("{fixture} is not a semantic fixture")),
    };
    Ok(format!(
        "semantic strling 1.0;\ncase sensitive;\npattern {pattern}\n"
    ))
}

fn legacy_source(fixture: &str) -> RunResult<String> {
    match fixture {
        "fixture:legacy-tiny" => Ok("a".to_owned()),
        "fixture:legacy-common" => Ok("(?<word>[A-Za-z]{1,32})-(cat|dog|bird)".to_owned()),
        "fixture:legacy-large" => Ok((0..2048)
            .map(|index| format!("item{index:04}xxxx"))
            .collect::<Vec<_>>()
            .join("|")),
        _ => Err(format!("{fixture} is not a legacy fixture")),
    }
}

fn literal(index: usize) -> Value {
    json!({
        "node_id": format!("node:performance.literal-{index}"),
        "kind": "literal",
        "text": format!("v{index:04}"),
    })
}

fn ascii_digit(index: usize) -> Value {
    json!({
        "node_id": format!("node:performance.set-{index}"),
        "kind": "character_set",
        "negated": false,
        "members": [{"kind": "builtin", "name": "digit", "domain": "ascii", "negated": false}],
    })
}

fn simply_program(fixture: &str) -> RunResult<SemanticProgram> {
    let (nodes, requirements) = match fixture {
        "fixture:simply-tiny" => (1, 0),
        "fixture:simply-common" => (32, 8),
        "fixture:simply-large" => (4096, 1024),
        _ => return Err(format!("{fixture} is not a Simply fixture")),
    };
    let root = if nodes == 1 {
        literal(0)
    } else {
        let requirement_interval = if requirements == 0 {
            usize::MAX
        } else {
            nodes / requirements
        };
        let items = (0..nodes)
            .map(|index| {
                if index % requirement_interval == 0 {
                    ascii_digit(index)
                } else {
                    literal(index)
                }
            })
            .collect::<Vec<_>>();
        json!({
            "node_id": "node:performance.root",
            "kind": "sequence",
            "items": items,
        })
    };
    serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "specification_version": "1.0-draft.1",
        "normalization": "canonical-v1",
        "case_matching": "sensitive",
        "root": root,
    }))
    .map_err(|error| error.to_string())
}

fn compile_request(program: &SemanticProgram) -> RunResult<CompileRequest> {
    serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "specification_version": "1.0-draft.1",
        "input": {"kind": "semantic", "program": program},
        "requested_outputs": ["semantic", "analysis"],
        "compiler_options": {
            "partial_semantics": "forbid",
            "diagnostic_policy": {"minimum_severity": "warning"},
        },
    }))
    .map_err(|error| error.to_string())
}

fn interop_request(request: &CompileRequest) -> RunResult<Vec<u8>> {
    serde_json::to_vec(&json!({
        "interop_protocol_version": "1.0.0",
        "operation": "compile",
        "payload": {"compile_request": request},
    }))
    .map_err(|error| error.to_string())
}

fn materialize_fixture(fixture: &str) -> RunResult<MaterializedFixture> {
    let (source, source_document, semantic) = if fixture.starts_with("fixture:semantic-") {
        let source = semantic_source(fixture)?;
        let document = semantic_document(&source)?;
        let semantic = semantic_frontend::parse(&document)
            .map_err(|error| error.to_string())?
            .program;
        (Some(source), Some(document), semantic)
    } else if fixture.starts_with("fixture:legacy-") {
        let source = legacy_source(fixture)?;
        let document = legacy_document(&source)?;
        let semantic = regex_frontend::parse(&document)
            .map_err(|error| error.to_string())?
            .program;
        (Some(source), Some(document), semantic)
    } else if fixture.starts_with("fixture:simply-") {
        let generated = simply_program(fixture)?;
        let semantic = normalize(&generated).map_err(|errors| format!("{errors:?}"))?;
        (None, None, semantic)
    } else if fixture == "fixture:protocol-common" {
        let generated = simply_program("fixture:simply-common")?;
        let semantic = normalize(&generated).map_err(|errors| format!("{errors:?}"))?;
        (None, None, semantic)
    } else {
        return Err(format!(
            "fixture {fixture} is not executable by the benchmark runner"
        ));
    };
    let request = compile_request(&semantic)?;
    let request_bytes = serde_json::to_vec(&request).map_err(|error| error.to_string())?;
    let interop_request = interop_request(&request)?;
    Ok(MaterializedFixture {
        id: fixture.to_owned(),
        source,
        source_document,
        semantic,
        request,
        request_bytes,
        interop_request,
    })
}

fn prepared_target_operation(
    fixture: &MaterializedFixture,
    profile_file: &str,
    target: &str,
) -> RunResult<PreparedOperation> {
    let semantic = fixture.semantic.clone();
    let foundational = analyze(&semantic).map_err(|error| error.to_string())?;
    let structural =
        analyze_structure(&semantic, &foundational).map_err(|error| error.to_string())?;
    let profile = target_profile(profile_file)?;
    let evaluation = evaluate_capabilities(&semantic, &foundational, &structural, &profile)
        .map_err(|error| error.to_string())?;
    let plan = plan_portability(&semantic, &foundational, &structural, &profile, &evaluation)
        .map_err(|error| error.to_string())?;
    match target {
        "pcre2" => Ok(Box::new(move || {
            let lowered =
                lower_pcre2(&semantic, &profile, &plan).map_err(|error| error.to_string())?;
            let artifact = serialize_pcre2(&lowered).map_err(|error| error.to_string())?;
            Ok(artifact.pattern.text.len())
        })),
        "ecmascript" => Ok(Box::new(move || {
            let lowered =
                lower_ecmascript(&semantic, &profile, &plan).map_err(|error| error.to_string())?;
            let artifact = serialize_ecmascript(&lowered).map_err(|error| error.to_string())?;
            Ok(artifact.pattern.text.len())
        })),
        "python-re" => Ok(Box::new(move || {
            let lowered =
                lower_python_re(&semantic, &profile, &plan).map_err(|error| error.to_string())?;
            let artifact = serialize_python_re(&lowered).map_err(|error| error.to_string())?;
            Ok(artifact.pattern.text.len())
        })),
        _ => Err(format!("unsupported target operation {target}")),
    }
}

fn prepare_cli_operation(
    fixture: &MaterializedFixture,
    kernel_bin: Option<&Path>,
) -> RunResult<PreparedOperation> {
    let executable = kernel_bin
        .ok_or_else(|| "latency:cli-startup requires --kernel-bin".to_owned())?
        .to_owned();
    if !executable.is_file() {
        return Err(format!(
            "kernel executable is absent: {}",
            executable.display()
        ));
    }
    let (arguments, input) = if let Some(source) = &fixture.source {
        if fixture.id.starts_with("fixture:semantic-") {
            (
                vec![
                    "check",
                    "--input",
                    "-",
                    "--frontend",
                    "semantic",
                    "--format",
                    "json",
                ],
                source.as_bytes().to_vec(),
            )
        } else {
            (
                vec![
                    "check",
                    "--input",
                    "-",
                    "--frontend",
                    "regex",
                    "--format",
                    "json",
                ],
                source.as_bytes().to_vec(),
            )
        }
    } else {
        (
            vec!["check", "--request", "-", "--format", "json"],
            fixture.request_bytes.clone(),
        )
    };
    Ok(Box::new(move || {
        let mut child = Command::new(&executable)
            .args(&arguments)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| error.to_string())?;
        child
            .stdin
            .take()
            .ok_or_else(|| "CLI stdin unavailable".to_owned())?
            .write_all(&input)
            .map_err(|error| error.to_string())?;
        let output = child
            .wait_with_output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err(format!(
                "CLI failed with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        Ok(output.stdout.len())
    }))
}

fn prepare_cli_launch_control(kernel_bin: Option<&Path>) -> RunResult<PreparedOperation> {
    let executable = kernel_bin
        .ok_or_else(|| "latency:cli-startup requires --kernel-bin".to_owned())?
        .to_owned();
    Ok(Box::new(move || {
        let output = Command::new(&executable)
            .arg("--help")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err(format!(
                "CLI launch control failed with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        Ok(output.stdout.len())
    }))
}

fn prepare_operation(
    operation: &str,
    fixture: &MaterializedFixture,
    kernel_bin: Option<&Path>,
) -> RunResult<PreparedOperation> {
    match operation {
        "latency:semantic-parse" => {
            let document = fixture
                .source_document
                .clone()
                .ok_or_else(|| "semantic parse requires a source document".to_owned())?;
            Ok(Box::new(move || {
                let parsed =
                    semantic_frontend::parse(&document).map_err(|error| error.to_string())?;
                Ok(parsed.program.root.node_id().as_str().len())
            }))
        }
        "latency:legacy-import" => {
            let document = fixture
                .source_document
                .clone()
                .ok_or_else(|| "legacy import requires a source document".to_owned())?;
            Ok(Box::new(move || {
                let parsed = regex_frontend::parse(&document).map_err(|error| error.to_string())?;
                Ok(parsed.program.root.node_id().as_str().len())
            }))
        }
        "latency:kernel-request" => {
            let bytes = fixture.request_bytes.clone();
            Ok(Box::new(move || {
                let request: CompileRequest =
                    serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
                request.validate().map_err(|errors| format!("{errors:?}"))?;
                Ok(request.requested_outputs.len())
            }))
        }
        "latency:normalization" => {
            let semantic = fixture.semantic.clone();
            Ok(Box::new(move || {
                let normalized = normalize(&semantic).map_err(|errors| errors.to_string())?;
                Ok(normalized.root.node_id().as_str().len())
            }))
        }
        "latency:semantic-analysis" => {
            let semantic = fixture.semantic.clone();
            Ok(Box::new(move || {
                let facts = analyze(&semantic).map_err(|errors| errors.to_string())?;
                Ok(facts.len())
            }))
        }
        "latency:structural-safety" => {
            let semantic = fixture.semantic.clone();
            let foundational = analyze(&semantic).map_err(|errors| errors.to_string())?;
            Ok(Box::new(move || {
                let structural = analyze_structure(&semantic, &foundational)
                    .map_err(|errors| errors.to_string())?;
                let safety = analyze_safety(&semantic, &foundational, &structural)
                    .map_err(|errors| errors.to_string())?;
                let finding_count = safety.findings().len();
                Ok(structural.len() ^ finding_count)
            }))
        }
        "latency:capability-portability" => {
            let semantic = fixture.semantic.clone();
            let foundational = analyze(&semantic).map_err(|errors| errors.to_string())?;
            let structural =
                analyze_structure(&semantic, &foundational).map_err(|errors| errors.to_string())?;
            let profile = target_profile("pcre2-10.43.json")?;
            Ok(Box::new(move || {
                let evaluation =
                    evaluate_capabilities(&semantic, &foundational, &structural, &profile)
                        .map_err(|errors| errors.to_string())?;
                let plan =
                    plan_portability(&semantic, &foundational, &structural, &profile, &evaluation)
                        .map_err(|errors| errors.to_string())?;
                Ok(plan.decisions.len())
            }))
        }
        "latency:pcre2-lower-serialize" => {
            prepared_target_operation(fixture, "pcre2-10.43.json", "pcre2")
        }
        "latency:ecmascript-lower-serialize" => {
            prepared_target_operation(fixture, "ecmascript-2024.json", "ecmascript")
        }
        "latency:python-re-lower-serialize" => {
            prepared_target_operation(fixture, "python-re-3.11.json", "python-re")
        }
        "latency:end-to-end" | "memory:kernel-peak-rss" => {
            let request = fixture.request.clone();
            Ok(Box::new(move || {
                let result =
                    strling_kernel::compile(&request, None).map_err(|error| error.to_string())?;
                serde_json::to_vec(&result)
                    .map(|bytes| bytes.len())
                    .map_err(|error| error.to_string())
            }))
        }
        "latency:cli-startup" => prepare_cli_operation(fixture, kernel_bin),
        "latency:editor-interaction" => {
            let source = fixture
                .source
                .clone()
                .ok_or_else(|| "editor interaction requires source text".to_owned())?;
            let request = EditorRequest {
                contract_version: EDITOR_EVIDENCE_CONTRACT_VERSION.to_owned(),
                source_id: "src:performance.editor".to_owned(),
                frontend: if fixture.id.starts_with("fixture:legacy-") {
                    EditorFrontend::Regex
                } else {
                    EditorFrontend::Semantic
                },
                cursor_byte: Some(source.len()),
                source,
            };
            Ok(Box::new(move || {
                let evidence = project_editor(&request).map_err(|error| error.to_string())?;
                Ok(evidence.tokens.len()
                    ^ evidence.completions.len()
                    ^ evidence.symbols.len()
                    ^ evidence.rewrite_actions.len())
            }))
        }
        "latency:interop-roundtrip" => {
            let bytes = fixture.interop_request.clone();
            Ok(Box::new(move || Ok(execute_bytes(&bytes).len())))
        }
        "latency:supported-host-overhead" => {
            let request: strling::CompileRequest = serde_json::from_slice(&fixture.request_bytes)
                .map_err(|error| error.to_string())?;
            Ok(Box::new(move || {
                let result = strling::compile(&request, None).map_err(|error| error.to_string())?;
                serde_json::to_vec(&result)
                    .map(|bytes| bytes.len())
                    .map_err(|error| error.to_string())
            }))
        }
        other => Err(format!("unsupported runner operation {other}")),
    }
}

#[cfg(test)]
mod affinity_tests {
    use super::{
        format_cpu_set, parse_cpu_set, sample_is_authentic, select_batch_iterations_with,
        MAXIMUM_DESCHEDULING_NANOSECONDS,
    };

    #[test]
    fn cpu_sets_are_parsed_and_rendered_deterministically() {
        assert_eq!(parse_cpu_set("0-2,5,7-8").unwrap(), vec![0, 1, 2, 5, 7, 8]);
        assert_eq!(format_cpu_set(&[20]), "20");
        assert!(parse_cpu_set("4-2").is_err());
    }

    #[test]
    fn batch_selection_confirms_a_candidate_after_a_cold_outlier() {
        let mut observations =
            vec![(1, 2_500_000), (1, 700_000), (3, 2_100_000), (3, 2_050_000)].into_iter();
        let mut requested = Vec::new();
        let selected = select_batch_iterations_with(2_000_000, 4096, |iterations| {
            requested.push(iterations);
            let (expected, elapsed) = observations
                .next()
                .ok_or_else(|| "unexpected selector probe".to_owned())?;
            if expected != iterations {
                return Err(format!("expected batch {expected}, observed {iterations}"));
            }
            Ok(elapsed)
        })
        .unwrap();

        assert_eq!(selected, 3);
        assert_eq!(requested, [1, 1, 3, 3]);
        assert!(observations.next().is_none());
    }

    #[test]
    fn sample_authenticity_rejects_only_excess_descheduling() {
        assert!(sample_is_authentic(
            100_000_000,
            100_000_000 - MAXIMUM_DESCHEDULING_NANOSECONDS
        ));
        assert!(!sample_is_authentic(
            100_000_001,
            100_000_000 - MAXIMUM_DESCHEDULING_NANOSECONDS
        ));
        assert!(sample_is_authentic(100_000_000, 110_000_000));
    }
}
