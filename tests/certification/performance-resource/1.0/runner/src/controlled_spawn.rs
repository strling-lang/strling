//! Per-child power policy before entry; this does not qualify ancestor quotas.
use std::io;
use std::process::{Child, Command};

#[cfg(not(target_os = "windows"))]
pub fn spawn(command: &mut Command) -> io::Result<Child> {
    command.spawn()
}

#[cfg(target_os = "windows")]
pub use native::spawn;

#[cfg(target_os = "windows")]
mod native {
    use super::*;
    use std::ffi::c_void;
    use std::mem::size_of;
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;

    type Handle = *mut c_void;
    const CREATE_SUSPENDED: u32 = 4;
    const TH32CS_SNAPTHREAD: u32 = 4;
    const THREAD_SUSPEND_RESUME: u32 = 2;
    const THREAD_QUERY_LIMITED_INFORMATION: u32 = 0x0800;
    const PROCESS_POWER_THROTTLING: i32 = 4;
    const CLEANUP_MILLISECONDS: u32 = 5_000;

    #[repr(C)]
    #[derive(Debug, PartialEq, Eq)]
    struct Power {
        version: u32,
        control_mask: u32,
        state_mask: u32,
    }

    const HIGH_QOS: Power = Power {
        version: 1,
        control_mask: 1,
        state_mask: 0,
    };

    #[repr(C)]
    #[derive(Default)]
    struct ThreadEntry {
        size: u32,
        usage: u32,
        thread_id: u32,
        owner_id: u32,
        base_priority: i32,
        delta_priority: i32,
        flags: u32,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> Handle;
        fn Thread32First(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
        fn Thread32Next(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
        fn OpenThread(access: u32, inherit: i32, thread_id: u32) -> Handle;
        fn GetProcessIdOfThread(thread: Handle) -> u32;
        fn ResumeThread(thread: Handle) -> u32;
        fn SetProcessInformation(
            process: Handle,
            class: i32,
            data: *const c_void,
            size: u32,
        ) -> i32;
        fn GetProcessInformation(process: Handle, class: i32, data: *mut c_void, size: u32) -> i32;
        fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
        fn CloseHandle(handle: Handle) -> i32;
    }

    fn invalid(message: &str) -> io::Error {
        io::Error::new(io::ErrorKind::Other, message)
    }

    struct OwnedHandle(Handle);
    impl Drop for OwnedHandle {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }

    // Retain std's Child, so cycle accounting and piped output keep their exact
    // existing semantics. Only the child created here can be killed on failure.
    struct SuspendedChild(Option<Child>);
    impl SuspendedChild {
        fn cleanup(&mut self) -> io::Result<()> {
            if let Some(mut child) = self.0.take() {
                child.kill()?;
                let result =
                    unsafe { WaitForSingleObject(child.as_raw_handle(), CLEANUP_MILLISECONDS) };
                if result != 0 {
                    return Err(invalid(&format!(
                        "owned child cleanup wait returned {result}"
                    )));
                }
                child.wait()?;
            }
            Ok(())
        }
    }
    impl Drop for SuspendedChild {
        fn drop(&mut self) {
            let _ = self.cleanup();
        }
    }

    fn power(process: Handle) -> io::Result<Power> {
        let mut value = Power {
            version: 1,
            control_mask: 0,
            state_mask: 0,
        };
        if unsafe {
            GetProcessInformation(
                process,
                PROCESS_POWER_THROTTLING,
                (&mut value as *mut Power).cast(),
                size_of::<Power>() as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(value)
    }

    fn validate_power(value: &Power) -> io::Result<()> {
        if value != &HIGH_QOS {
            return Err(invalid(&format!(
                "child HighQoS readback differs: {value:?}"
            )));
        }
        Ok(())
    }

    fn validate_owner(actual: u32, expected: u32) -> io::Result<()> {
        if actual == 0 || actual != expected {
            return Err(invalid("initial thread does not belong to retained child"));
        }
        Ok(())
    }

    fn validate_resume(count: u32) -> io::Result<()> {
        if count == u32::MAX {
            return Err(io::Error::last_os_error());
        }
        if count != 1 {
            return Err(invalid(&format!(
                "initial thread resume count was {count}, expected 1"
            )));
        }
        Ok(())
    }

    fn record_thread(entry: &ThreadEntry, owner: u32, found: &mut Option<u32>) -> io::Result<()> {
        if entry.size < size_of::<ThreadEntry>() as u32 {
            return Err(invalid("short initial-thread snapshot entry"));
        }
        if entry.owner_id == owner && found.replace(entry.thread_id).is_some() {
            return Err(invalid("suspended child has ambiguous initial threads"));
        }
        Ok(())
    }

    fn initial_thread(child: &Child) -> io::Result<OwnedHandle> {
        let raw = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
        if raw == -1isize as Handle {
            return Err(io::Error::last_os_error());
        }
        let snapshot = OwnedHandle(raw);
        let mut entry = ThreadEntry {
            size: size_of::<ThreadEntry>() as u32,
            ..Default::default()
        };
        let mut present = unsafe { Thread32First(snapshot.0, &mut entry) };
        let mut thread_id = None;
        while present != 0 {
            record_thread(&entry, child.id(), &mut thread_id)?;
            entry.size = size_of::<ThreadEntry>() as u32;
            present = unsafe { Thread32Next(snapshot.0, &mut entry) };
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(18) {
            // ERROR_NO_MORE_FILES
            return Err(error);
        }
        let thread_id =
            thread_id.ok_or_else(|| invalid("suspended child initial thread is absent"))?;
        let raw = unsafe {
            OpenThread(
                THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION,
                0,
                thread_id,
            )
        };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        let thread = OwnedHandle(raw);
        validate_owner(unsafe { GetProcessIdOfThread(thread.0) }, child.id())?;
        Ok(thread)
    }

    fn prepare_and_resume(child: &Child) -> io::Result<()> {
        let thread = initial_thread(child)?;
        if unsafe {
            SetProcessInformation(
                child.as_raw_handle(),
                PROCESS_POWER_THROTTLING,
                (&HIGH_QOS as *const Power).cast(),
                size_of::<Power>() as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        validate_power(&power(child.as_raw_handle())?)?;
        validate_resume(unsafe { ResumeThread(thread.0) })
    }

    fn spawn_with(
        command: &mut Command,
        setup: impl FnOnce(&Child) -> io::Result<()>,
    ) -> io::Result<Child> {
        // These private runner call sites do not set any other creation flags.
        // std preserves argv quoting, stdio, environment and job inheritance.
        let child = command.creation_flags(CREATE_SUSPENDED).spawn()?;
        let mut owned = SuspendedChild(Some(child));
        if let Err(error) = setup(owned.0.as_ref().unwrap()) {
            let pid = owned.0.as_ref().unwrap().id();
            return Err(match owned.cleanup() {
                Ok(()) => invalid(&format!(
                    "child {pid} setup failed; owned child retired: {error}"
                )),
                Err(cleanup) => invalid(&format!(
                    "child {pid} setup failed: {error}; cleanup FAILED: {cleanup}"
                )),
            });
        }
        Ok(owned.0.take().unwrap())
    }

    pub fn spawn(command: &mut Command) -> io::Result<Child> {
        spawn_with(command, prepare_and_resume)
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn policy_owner_and_resume_mismatches_fail_closed() {
            assert!(validate_power(&HIGH_QOS).is_ok());
            for value in [
                Power {
                    version: 1,
                    control_mask: 0,
                    state_mask: 0,
                },
                Power {
                    version: 1,
                    control_mask: 1,
                    state_mask: 1,
                },
                Power {
                    version: 0,
                    control_mask: 1,
                    state_mask: 0,
                },
            ] {
                assert!(validate_power(&value).is_err());
            }
            assert!(validate_owner(42, 42).is_ok());
            assert!(validate_owner(0, 42).is_err());
            assert!(validate_owner(43, 42).is_err());
            assert!(validate_resume(1).is_ok());
            for count in [0, 2, u32::MAX] {
                assert!(validate_resume(count).is_err());
            }
        }

        #[test]
        fn thread_snapshot_rejects_short_or_ambiguous_records() {
            let mut found = None;
            let mut entry = ThreadEntry {
                size: size_of::<ThreadEntry>() as u32,
                thread_id: 7,
                owner_id: 42,
                ..Default::default()
            };
            record_thread(&entry, 99, &mut found).unwrap();
            assert_eq!(found, None);
            record_thread(&entry, 42, &mut found).unwrap();
            assert_eq!(found, Some(7));
            entry.thread_id = 8;
            assert!(record_thread(&entry, 42, &mut found).is_err());
            entry.size = 12;
            assert!(record_thread(&entry, 99, &mut None).is_err());
        }

        #[test]
        fn setup_failure_retires_suspended_child_without_entry() {
            let (mut command, marker) =
                super::super::tests::fixture_command("setup-failure", false);
            let started = std::time::Instant::now();
            let error = spawn_with(&mut command, |child| {
                assert!(!marker.exists());
                let _thread = initial_thread(child)?;
                Err(invalid("injected pre-resume setup failure"))
            })
            .unwrap_err();
            assert!(error.to_string().contains("owned child retired"), "{error}");
            assert!(error
                .to_string()
                .contains("injected pre-resume setup failure"));
            assert!(!marker.exists());
            assert!(started.elapsed().as_secs() < 10);
        }

        pub(super) fn assert_child_power() {
            extern "system" {
                fn GetCurrentProcess() -> Handle;
            }
            validate_power(&power(unsafe { GetCurrentProcess() }).unwrap()).unwrap();
        }
    }

    #[cfg(test)]
    pub(super) fn assert_child_power() {
        tests::assert_child_power();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::path::PathBuf;
    use std::process::Stdio;

    pub(super) fn fixture_command(kind: &str, piped: bool) -> (Command, PathBuf) {
        let marker = std::env::current_dir()
            .unwrap()
            .join("target")
            .join(format!(
                "controlled-spawn-{}-{kind}.marker",
                std::process::id()
            ));
        assert!(!marker.exists(), "test attempt marker already exists");
        let mut command = Command::new(std::env::current_exe().unwrap());
        // Works both standalone and within the runner's test module.
        let name = format!(
            "{}::child_fixture",
            module_path!().split_once("::").unwrap().1
        );
        command
            .args([
                "--exact",
                &name,
                "--nocapture",
                "--skip",
                "space and \"quoted\" Ω",
            ])
            .env("STRLING_CONTROLLED_SPAWN_FIXTURE", &marker)
            .env(
                "STRLING_CONTROLLED_SPAWN_INPUT",
                if piped { "input" } else { "" },
            )
            .env("STRLING_CONTROLLED_SPAWN_UNICODE", "space and \"quoted\" Ω")
            .stdin(if piped { Stdio::piped() } else { Stdio::null() })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        (command, marker)
    }

    #[test]
    fn child_fixture() {
        let Some(marker) = std::env::var_os("STRLING_CONTROLLED_SPAWN_FIXTURE") else {
            return;
        };
        #[cfg(target_os = "windows")]
        native::assert_child_power();
        assert_eq!(
            std::env::var("STRLING_CONTROLLED_SPAWN_UNICODE").unwrap(),
            "space and \"quoted\" Ω"
        );
        assert!(std::env::args().any(|arg| arg == "space and \"quoted\" Ω"));
        let mut input = Vec::new();
        std::io::stdin().read_to_end(&mut input).unwrap();
        assert_eq!(
            input,
            std::env::var("STRLING_CONTROLLED_SPAWN_INPUT")
                .unwrap()
                .as_bytes()
        );
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(marker)
            .unwrap()
            .write_all(b"entered with controls")
            .unwrap();
        std::io::stdout().write_all(b"exact stdout\0bytes").unwrap();
        std::io::stderr().write_all(b"exact stderr\0bytes").unwrap();
        if std::env::var_os("STRLING_CONTROLLED_SPAWN_NONZERO").is_some() {
            std::process::exit(7);
        }
    }

    #[test]
    fn request_and_control_preserve_streams_and_power() {
        for piped in [false, true] {
            let (mut command, marker) =
                fixture_command(if piped { "request" } else { "control" }, piped);
            let mut child = spawn(&mut command).unwrap();
            if piped {
                child.stdin.take().unwrap().write_all(b"input").unwrap();
            }
            let output = child.wait_with_output().unwrap();
            assert!(output.status.success(), "{:?}", output);
            assert!(output
                .stdout
                .windows(18)
                .any(|part| part == b"exact stdout\0bytes"));
            assert!(output
                .stderr
                .windows(18)
                .any(|part| part == b"exact stderr\0bytes"));
            assert_eq!(std::fs::read(&marker).unwrap(), b"entered with controls");
            std::fs::remove_file(marker).unwrap();
        }
    }

    #[test]
    fn absent_executable_fails_before_setup() {
        assert!(spawn(&mut Command::new("absent-controlled-spawn-test-executable")).is_err());
    }

    #[test]
    fn child_failure_status_and_stderr_are_preserved() {
        let (mut command, marker) = fixture_command("nonzero", false);
        command.env("STRLING_CONTROLLED_SPAWN_NONZERO", "1");
        let output = spawn(&mut command).unwrap().wait_with_output().unwrap();
        assert_eq!(output.status.code(), Some(7));
        assert!(output
            .stderr
            .windows(18)
            .any(|part| part == b"exact stderr\0bytes"));
        assert_eq!(std::fs::read(&marker).unwrap(), b"entered with controls");
        std::fs::remove_file(marker).unwrap();
    }
}
