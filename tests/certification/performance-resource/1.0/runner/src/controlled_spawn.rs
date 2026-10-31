//! Per-child power policy before entry; this does not qualify ancestor quotas.
use std::io;
use std::process::{Child, Command};

#[cfg(not(target_os = "windows"))]
pub fn spawn(command: &mut Command) -> io::Result<Child> {
    command.spawn()
}

#[cfg(target_os = "windows")]
pub use native::{spawn, spawn_observed};

#[cfg(target_os = "windows")]
mod native {
    use super::*;
    use std::ffi::c_void;
    use std::mem::size_of;
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;

    type Handle = *mut c_void;
    const CREATE_SUSPENDED: u32 = 4;
    const PSS_CAPTURE_THREADS: u32 = 0x80;
    const PSS_WALK_THREADS: i32 = 3;
    const ERROR_NO_MORE_ITEMS: u32 = 259;
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
    struct FileTime {
        low: u32,
        high: u32,
    }

    // SDK PSS_THREAD_ENTRY, including the fields we do not request or use.
    #[repr(C)]
    struct ThreadEntry {
        exit_status: u32,
        teb: *mut c_void,
        owner_id: u32,
        thread_id: u32,
        affinity: usize,
        priority: i32,
        base_priority: i32,
        last_argument: *mut c_void,
        last_call: u16,
        create_time: FileTime,
        exit_time: FileTime,
        kernel_time: FileTime,
        user_time: FileTime,
        start_address: *mut c_void,
        capture_time: FileTime,
        flags: u32,
        suspend_count: u16,
        context_size: u16,
        context: *mut c_void,
    }

    impl Default for ThreadEntry {
        fn default() -> Self {
            // Every field is an integer, raw pointer or two-integer FILETIME;
            // zero is valid for all of them. The API fills the output record.
            unsafe { std::mem::zeroed() }
        }
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn PssCaptureSnapshot(
            process: Handle,
            flags: u32,
            context: u32,
            snapshot: *mut Handle,
        ) -> u32;
        fn PssWalkMarkerCreate(allocator: *const c_void, marker: *mut Handle) -> u32;
        fn PssWalkSnapshot(
            snapshot: Handle,
            class: i32,
            marker: Handle,
            data: *mut c_void,
            size: u32,
        ) -> u32;
        fn PssWalkMarkerFree(marker: Handle) -> u32;
        fn PssFreeSnapshot(process: Handle, snapshot: Handle) -> u32;
        fn GetCurrentProcess() -> Handle;
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

    fn pss_status(code: u32) -> io::Result<()> {
        if code == 0 {
            Ok(())
        } else {
            Err(io::Error::from_raw_os_error(code as i32))
        }
    }

    // These are PSS descriptors, not kernel handles. Snapshots captured here
    // belong to this process even when the captured child is a different one.
    struct Snapshot(Handle);
    impl Snapshot {
        fn close(&mut self) -> io::Result<()> {
            if self.0.is_null() {
                return Ok(());
            }
            let raw = std::mem::replace(&mut self.0, std::ptr::null_mut());
            pss_status(unsafe { PssFreeSnapshot(GetCurrentProcess(), raw) })
        }
    }
    impl Drop for Snapshot {
        fn drop(&mut self) {
            let _ = self.close();
        }
    }
    struct Marker(Handle);
    impl Marker {
        fn close(&mut self) -> io::Result<()> {
            if self.0.is_null() {
                return Ok(());
            }
            let raw = std::mem::replace(&mut self.0, std::ptr::null_mut());
            pss_status(unsafe { PssWalkMarkerFree(raw) })
        }
    }
    impl Drop for Marker {
        fn drop(&mut self) {
            let _ = self.close();
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

    fn unique_thread(owner: u32, mut next: impl FnMut(&mut ThreadEntry) -> u32) -> io::Result<u32> {
        let mut entry = ThreadEntry::default();
        let status = next(&mut entry);
        if status == ERROR_NO_MORE_ITEMS {
            return Err(invalid("suspended child initial thread is absent"));
        }
        pss_status(status)?;
        validate_owner(entry.owner_id, owner)?;
        if entry.thread_id == 0
            || entry.flags != 0
            || entry.exit_status != 259
            || entry.suspend_count != 1
        {
            return Err(invalid("initial thread is not live and singly suspended"));
        }
        let thread_id = entry.thread_id;
        match next(&mut entry) {
            ERROR_NO_MORE_ITEMS => Ok(thread_id),
            0 => Err(invalid("suspended child has ambiguous initial threads")),
            error => Err(io::Error::from_raw_os_error(error as i32)),
        }
    }

    fn finish_lookup(
        found: io::Result<u32>,
        marker: io::Result<()>,
        snapshot: io::Result<()>,
    ) -> io::Result<u32> {
        match (found, marker, snapshot) {
            (Ok(id), Ok(()), Ok(())) => Ok(id),
            (found, marker, snapshot) => Err(invalid(&format!(
                "initial thread lookup/release failed: lookup={found:?}; marker={marker:?}; snapshot={snapshot:?}"
            ))),
        }
    }

    fn initial_thread(child: &Child) -> io::Result<OwnedHandle> {
        let mut snapshot = Snapshot(std::ptr::null_mut());
        let mut marker = Marker(std::ptr::null_mut());
        let found = (|| {
            pss_status(unsafe {
                PssCaptureSnapshot(
                    child.as_raw_handle(),
                    PSS_CAPTURE_THREADS,
                    0,
                    &mut snapshot.0,
                )
            })?;
            pss_status(unsafe { PssWalkMarkerCreate(std::ptr::null(), &mut marker.0) })?;
            unique_thread(child.id(), |entry| unsafe {
                PssWalkSnapshot(
                    snapshot.0,
                    PSS_WALK_THREADS,
                    marker.0,
                    (entry as *mut ThreadEntry).cast(),
                    size_of::<ThreadEntry>() as u32,
                )
            })
        })();
        // Both releases are attempted even when capture, creation or walking
        // failed. No child code runs until lookup AND both releases succeed.
        let marker_result = marker.close();
        let snapshot_result = snapshot.close();
        let thread_id = finish_lookup(found, marker_result, snapshot_result)?;
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

    /// Retain observer state while the child's initial thread is suspended.
    /// The observer never replaces preparation, inherited controls or cleanup.
    pub fn spawn_observed<T>(
        command: &mut Command,
        observe: impl FnOnce(&Child) -> io::Result<T>,
    ) -> io::Result<(Child, T)> {
        let mut observation = None;
        let child = spawn_with(command, |child| {
            observation = Some(observe(child)?);
            prepare_and_resume(child)
        })?;
        Ok((child, observation.unwrap()))
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
        fn thread_snapshot_rejects_missing_malformed_or_ambiguous_records() {
            for (owner, tid, flags, suspended, exit, first, second, valid) in [
                (42, 7, 0, 1, 259, 0, 259, true),
                (99, 7, 0, 1, 259, 0, 259, false),
                (0, 7, 0, 1, 259, 0, 259, false),
                (42, 0, 0, 1, 259, 0, 259, false),
                (42, 7, 1, 1, 259, 0, 259, false),
                (42, 7, 0, 0, 259, 0, 259, false),
                (42, 7, 0, 2, 259, 0, 259, false),
                (42, 7, 0, 1, 0, 0, 259, false),
                (42, 7, 0, 1, 259, 259, 259, false),
                (42, 7, 0, 1, 259, 24, 259, false),
                (42, 7, 0, 1, 259, 0, 0, false),
                (42, 7, 0, 1, 259, 0, 6, false),
            ] {
                let mut calls = 0;
                let result = unique_thread(42, |entry| {
                    calls += 1;
                    assert!(calls <= 2);
                    *entry = ThreadEntry {
                        owner_id: owner,
                        thread_id: tid,
                        flags,
                        suspend_count: suspended,
                        exit_status: exit,
                        ..Default::default()
                    };
                    if calls == 1 {
                        first
                    } else {
                        second
                    }
                });
                assert_eq!(result.is_ok(), valid);
            }
        }

        #[test]
        fn snapshot_layout_and_release_errors_are_checked() {
            if size_of::<usize>() == 8 {
                let entry = ThreadEntry::default();
                let base = &entry as *const ThreadEntry as usize;
                assert_eq!(size_of::<ThreadEntry>(), 120);
                assert_eq!(&entry.owner_id as *const u32 as usize - base, 16);
                assert_eq!(&entry.thread_id as *const u32 as usize - base, 20);
                assert_eq!(&entry.context as *const Handle as usize - base, 112);
            }
            assert_eq!(finish_lookup(Ok(7), Ok(()), Ok(())).unwrap(), 7);
            for (lookup, marker, snapshot) in [
                (false, true, true),
                (true, false, true),
                (true, true, false),
                (false, false, false),
            ] {
                let result = finish_lookup(
                    if lookup {
                        Ok(7)
                    } else {
                        Err(invalid("lookup failure"))
                    },
                    if marker {
                        Ok(())
                    } else {
                        Err(invalid("marker failure"))
                    },
                    if snapshot {
                        Ok(())
                    } else {
                        Err(invalid("snapshot failure"))
                    },
                );
                assert!(result.is_err());
                if !lookup && !marker && !snapshot {
                    let text = result.unwrap_err().to_string();
                    assert!(
                        text.contains("lookup failure")
                            && text.contains("marker failure")
                            && text.contains("snapshot failure")
                    );
                }
            }
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
        // Native qualification also runs from an isolated canonical build root.
        // Its marker must not depend on a repository target directory existing.
        let marker = std::env::temp_dir().join(format!(
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
