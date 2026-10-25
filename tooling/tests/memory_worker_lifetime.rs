//! Native integration of the same launch and lifetime observer used by the runner.
#[cfg(windows)]
#[path = "../../tests/certification/performance-resource/1.0/runner/src/controlled_spawn.rs"]
mod controlled_spawn;
#[cfg(windows)]
#[path = "../../tests/certification/performance-resource/1.0/runner/src/memory_lifetime.rs"]
mod memory_lifetime;

#[cfg(windows)]
mod native {
    use super::*;
    use std::ffi::c_void;
    use std::io::Write;
    use std::process::{Command, Stdio};

    #[link(name = "kernel32")]
    extern "system" {
        fn VirtualAlloc(address: *mut c_void, bytes: usize, kind: u32, protect: u32)
            -> *mut c_void;
        fn VirtualFree(address: *mut c_void, bytes: usize, kind: u32) -> i32;
        fn GetCurrentProcess() -> *mut c_void;
        fn K32EmptyWorkingSet(process: *mut c_void) -> i32;
    }

    struct LateNativeMemory;
    impl Drop for LateNativeMemory {
        fn drop(&mut self) {
            let bytes = 32 * 1024 * 1024;
            let memory = unsafe { VirtualAlloc(std::ptr::null_mut(), bytes, 0x3000, 4) };
            assert!(!memory.is_null());
            for offset in (0..bytes).step_by(4096) {
                unsafe { memory.cast::<u8>().add(offset).write_volatile(0x5a) };
            }
            assert_ne!(unsafe { VirtualFree(memory, 0, 0x8000) }, 0);
        }
    }

    fn commit_and_trim(bytes: usize) {
        let memory = unsafe { VirtualAlloc(std::ptr::null_mut(), bytes, 0x3000, 4) };
        assert!(!memory.is_null());
        // Deliberately do not touch the committed pages. Residency is not the
        // measurement: their private commit still consumes the resource budget.
        assert_ne!(unsafe { K32EmptyWorkingSet(GetCurrentProcess()) }, 0);
        assert_ne!(unsafe { VirtualFree(memory, 0, 0x8000) }, 0);
        println!("COMMIT_CHALLENGE={bytes}");
    }

    #[test]
    #[ignore = "owned child entry point for the native commit qualification"]
    fn child_with_small_commit_and_trim() {
        commit_and_trim(2 * 1024 * 1024);
    }

    #[test]
    #[ignore = "owned child entry point for the negative native commit qualification"]
    fn child_with_over_budget_commit_and_trim() {
        commit_and_trim(96 * 1024 * 1024);
    }

    #[test]
    fn workstation_commit_observation_survives_trim_and_free() {
        for (entry, bytes) in [
            ("native::child_with_small_commit_and_trim", 2 * 1024 * 1024),
            (
                "native::child_with_over_budget_commit_and_trim",
                96 * 1024 * 1024,
            ),
        ] {
            let (child, observer) = controlled_spawn::spawn_observed(
                Command::new(std::env::current_exe().unwrap())
                    .args(["--ignored", "--exact", entry, "--nocapture"])
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped()),
                memory_lifetime::Observation::begin_workstation,
            )
            .unwrap();
            let output = child.wait_with_output().unwrap();
            assert!(output.status.success(), "{output:?}");
            let terminal = observer.finish().unwrap();
            assert!(terminal.single_process_job);
            assert!(terminal.peak_commit_bytes >= bytes);
            if bytes > 64 * 1024 * 1024 {
                assert!(terminal.peak_rss_bytes < terminal.peak_commit_bytes);
            } else {
                assert!(terminal.peak_commit_bytes <= 64 * 1024 * 1024);
            }
            println!(
                "workstation bytes={bytes} peak_commit={} peak_rss={}",
                terminal.peak_commit_bytes, terminal.peak_rss_bytes
            );
        }
    }

    #[test]
    fn rapid_exact_children_retire_naturally_without_replacement() {
        // Stress the exit-signal/job-accounting boundary with fresh processes.
        // Every launch must succeed; a failed observation is never retried.
        for _ in 0..128 {
            let (child, observer) = controlled_spawn::spawn_observed(
                Command::new(std::env::current_exe().unwrap())
                    .arg("--list")
                    .stdout(Stdio::null())
                    .stderr(Stdio::null()),
                memory_lifetime::Observation::begin_workstation,
            )
            .unwrap();
            let pid = child.id();
            assert!(child.wait_with_output().unwrap().status.success());
            let terminal = observer.finish().unwrap();
            assert_eq!(terminal.pid, pid);
            assert!(terminal.single_process_job);
            assert!(terminal.peak_commit_bytes > 0);
        }
    }

    #[test]
    #[ignore = "owned child entry point for descendant prevention qualification"]
    fn child_attempting_a_grandchild() {
        match Command::new(std::env::current_exe().unwrap())
            .arg("--list")
            .output()
        {
            Ok(output) => {
                assert!(output.status.success());
                println!("DESCENDANT_ALLOWED");
            }
            Err(error) => println!("DESCENDANT_DENIED:{}", error.raw_os_error().unwrap_or(-1)),
        }
    }

    #[test]
    fn workstation_prevents_descendants_with_an_unrestricted_counterfactual() {
        for restricted in [false, true] {
            let (child, observation) = controlled_spawn::spawn_observed(
                Command::new(std::env::current_exe().unwrap())
                    .args([
                        "--ignored",
                        "--exact",
                        "native::child_attempting_a_grandchild",
                        "--nocapture",
                    ])
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped()),
                |child| {
                    if restricted {
                        memory_lifetime::Observation::begin_workstation(child)
                    } else {
                        memory_lifetime::Observation::begin(child)
                    }
                },
            )
            .unwrap();
            let output = child.wait_with_output().unwrap();
            assert!(output.status.success(), "{output:?}");
            let lines = String::from_utf8(output.stdout).unwrap();
            let terminal = observation.finish().unwrap();
            assert_eq!(terminal.single_process_job, restricted);
            if restricted {
                assert!(
                    lines.lines().any(|line| matches!(
                        line,
                        "DESCENDANT_DENIED:5" | "DESCENDANT_DENIED:1816"
                    )),
                    "{lines}"
                );
            } else {
                assert!(
                    lines.lines().any(|line| line == "DESCENDANT_ALLOWED"),
                    "{lines}"
                );
            }
            println!("restricted={restricted} terminal={terminal:?}");
        }
    }

    #[test]
    #[ignore = "owned child entry point; run only from the parent integration test"]
    fn child_with_late_native_thread_and_rust_allocations() {
        let _teardown = LateNativeMemory;
        println!("MEMORY_REPORT=1");
        std::io::stdout().flush().unwrap();
        std::thread::spawn(|| {
            let mut bytes = vec![0u8; 8 * 1024 * 1024];
            for offset in (0..bytes.len()).step_by(4096) {
                bytes[offset] = 17;
            }
            std::hint::black_box(bytes);
        })
        .join()
        .unwrap();
    }

    #[test]
    #[ignore = "owned child entry point; blocks until its parent retires it"]
    fn child_blocked_on_input() {
        let mut input = String::new();
        std::io::stdin().read_line(&mut input).unwrap();
    }

    #[test]
    fn a_live_process_cannot_supply_terminal_evidence() {
        let (mut child, observation) = controlled_spawn::spawn_observed(
            Command::new(std::env::current_exe().unwrap())
                .args(["--ignored", "--exact", "native::child_blocked_on_input"])
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(Stdio::null()),
            memory_lifetime::Observation::begin,
        )
        .unwrap();
        assert!(observation.finish().is_err());
        child.kill().unwrap();
        child.wait().unwrap();
    }

    #[test]
    fn failed_transport_retires_only_the_retained_child() {
        let (mut child, observation) = controlled_spawn::spawn_observed(
            Command::new(std::env::current_exe().unwrap())
                .args(["--ignored", "--exact", "native::child_blocked_on_input"])
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(Stdio::null()),
            memory_lifetime::Observation::begin,
        )
        .unwrap();
        let pid = child.id();
        let terminal = observation.retire().unwrap();
        assert_eq!(terminal.pid, pid);
        assert!(child.try_wait().unwrap().is_some());
        child.wait().unwrap();
    }

    #[test]
    fn terminal_observer_includes_late_work_on_the_exact_child() {
        let (child, observation) = controlled_spawn::spawn_observed(
            Command::new(std::env::current_exe().unwrap())
                .args([
                    "--ignored",
                    "--exact",
                    "native::child_with_late_native_thread_and_rust_allocations",
                    "--nocapture",
                ])
                .stdout(Stdio::piped())
                .stderr(Stdio::piped()),
            memory_lifetime::Observation::begin,
        )
        .unwrap();
        let expected_pid = child.id();
        let expected_birth = observation.birth_100ns;
        let output = child.wait_with_output().unwrap();
        assert!(output.status.success(), "{:?}", output);
        assert!(String::from_utf8_lossy(&output.stdout).contains("MEMORY_REPORT=1"));
        let terminal = observation.finish().unwrap();
        terminal.validate_reported_peak(1).unwrap();
        assert_eq!(terminal.pid, expected_pid);
        assert_eq!(terminal.birth_100ns, expected_birth);
        assert!(terminal.exit_100ns > expected_birth);
        assert!(terminal.peak_rss_bytes >= 32 * 1024 * 1024);
        println!("terminal_peak_rss_bytes={}", terminal.peak_rss_bytes);
    }

    #[test]
    fn observer_failure_retires_the_child_before_entry() {
        let result = controlled_spawn::spawn_observed(
            Command::new(std::env::current_exe().unwrap()).arg("--list"),
            |_| {
                Err::<(), _>(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    "injected observer failure",
                ))
            },
        );
        let error = result.unwrap_err().to_string();
        assert!(error.contains("owned child retired"));
        assert!(error.contains("injected observer failure"));
    }
}
