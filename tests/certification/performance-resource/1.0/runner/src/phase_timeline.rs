//! Opt-in diagnostic phase journal, never performance admission evidence.
//!
//! The origin is after argument parsing. Parent receipts must independently
//! enclose launch and exit. Journal I/O is included in the next phase interval;
//! its overhead must be qualified separately, never subtracted from samples.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use std::time::Instant;

const PHASES: [&str; 7] = [
    "preparation",
    "primary-warmups",
    "sample-setup",
    "control-warmups",
    "measurement",
    "post-measurement",
    "serialization",
];

pub fn validate_selection(
    operation: &str,
    warmups: usize,
    samples: usize,
    batch: Option<usize>,
) -> Result<(), String> {
    if !operation.starts_with("latency:")
        || warmups != 512
        || samples != 64
        || !matches!(batch, Some(1..=4096))
    {
        return Err(
            "phase diagnostic requires fixed-batch latency with 512 warmups/64 samples".into(),
        );
    }
    Ok(())
}

#[derive(Default)]
struct Progress {
    phase: usize,
    last_ns: u64,
}

impl Progress {
    fn close(&mut self, writer: &mut impl Write, phase: &str, end_ns: u64) -> io::Result<()> {
        if PHASES.get(self.phase) != Some(&phase) || end_ns < self.last_ns {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "phase order/clock changed",
            ));
        }
        writeln!(
            writer,
            "{{\"phase\":\"{phase}\",\"begin_ns\":{},\"end_ns\":{end_ns},\"completed\":true}}",
            self.last_ns
        )?;
        writer.flush()?;
        self.last_ns = end_ns;
        self.phase += 1;
        Ok(())
    }
}

pub struct Timeline {
    file: File,
    started: Instant,
    progress: Progress,
    completed: bool,
}

impl Timeline {
    pub fn open(path: &Path) -> io::Result<Self> {
        let started = Instant::now();
        let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
        writeln!(file, "{{\"contract\":\"diagnostic-runner-phase-timeline-v1\",\"authoritative\":false,\"origin\":\"post-argument-parse\",\"pid\":{}}}", std::process::id())?;
        file.sync_all()?;
        Ok(Self {
            file,
            started,
            progress: Progress::default(),
            completed: false,
        })
    }

    fn elapsed_ns(&self) -> io::Result<u64> {
        u64::try_from(self.started.elapsed().as_nanos())
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "phase clock overflow"))
    }

    pub fn close(&mut self, phase: &str) -> io::Result<()> {
        let elapsed = self.elapsed_ns()?;
        self.progress.close(&mut self.file, phase, elapsed)
    }

    pub fn finish(&mut self) -> io::Result<()> {
        if self.progress.phase != PHASES.len() || self.completed {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "incomplete/repeated phase completion",
            ));
        }
        writeln!(
            self.file,
            "{{\"status\":\"runner-body-complete\",\"authoritative\":false}}"
        )?;
        self.file.sync_all()?;
        self.completed = true;
        Ok(())
    }
}

impl Drop for Timeline {
    fn drop(&mut self) {
        if !self.completed {
            // Best-effort prefix preservation on failure is not completion.
            // The independent reader also requires the parent's zero exit.
            if let Ok(elapsed) = self.elapsed_ns() {
                let _ = writeln!(self.file, "{{\"status\":\"incomplete\",\"next_phase\":{},\"begin_ns\":{},\"end_ns\":{elapsed},\"authoritative\":false}}", self.progress.phase, self.progress.last_ns);
                let _ = self.file.sync_all();
            }
        }
    }
}

pub fn close(timeline: &mut Option<Timeline>, phase: &str) -> Result<(), String> {
    if let Some(timeline) = timeline {
        timeline.close(phase).map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT: AtomicUsize = AtomicUsize::new(0);

    fn fresh_path() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "strling-phase-{}-{}.jsonl",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::SeqCst)
        ))
    }

    #[test]
    fn selection_preserves_counts_and_batch() {
        assert!(validate_selection("latency:semantic-analysis", 512, 64, Some(76)).is_ok());
        for args in [
            ("memory:peak", 512, 64, Some(1)),
            ("latency:x", 1, 64, Some(1)),
            ("latency:x", 512, 1, Some(1)),
            ("latency:x", 512, 64, None),
            ("latency:x", 512, 64, Some(0)),
            ("latency:x", 512, 64, Some(4097)),
        ] {
            assert!(validate_selection(args.0, args.1, args.2, args.3).is_err());
        }
    }

    #[test]
    fn ordered_contiguous_intervals() {
        let mut progress = Progress::default();
        let mut raw = Vec::new();
        for (index, phase) in PHASES.iter().enumerate() {
            progress
                .close(&mut raw, phase, (index as u64 + 1) * 10)
                .unwrap();
        }
        let text = String::from_utf8(raw).unwrap();
        assert_eq!(text.lines().count(), 7);
        assert!(text.contains("\"begin_ns\":0,\"end_ns\":10"));
        assert!(text.contains("\"begin_ns\":60,\"end_ns\":70"));
        assert_eq!(progress.last_ns, 70);
    }

    #[test]
    fn order_and_clock_fail_without_advancing() {
        let mut progress = Progress::default();
        let mut raw = Vec::new();
        assert!(progress.close(&mut raw, "measurement", 10).is_err());
        assert!(raw.is_empty());
        progress.close(&mut raw, "preparation", 10).unwrap();
        assert!(progress.close(&mut raw, "primary-warmups", 9).is_err());
        assert_eq!(progress.phase, 1);
        assert_eq!(progress.last_ns, 10);
    }

    #[test]
    fn write_failure_never_advances() {
        struct Broken;
        impl Write for Broken {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::Error::new(io::ErrorKind::Other, "fixture failure"))
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        let mut progress = Progress::default();
        assert!(progress.close(&mut Broken, "preparation", 10).is_err());
        assert_eq!(progress.phase, 0);
    }

    #[test]
    fn disabled_has_no_io_or_phase_state() {
        assert!(close(&mut None, "not-a-phase").is_ok());
    }

    #[test]
    fn existing_attempt_is_never_replaced() {
        let path = fresh_path();
        let first = Timeline::open(&path).unwrap();
        let before = std::fs::read(&path).unwrap();
        assert!(Timeline::open(&path).is_err());
        assert_eq!(std::fs::read(&path).unwrap(), before);
        drop(first);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn partial_attempt_has_no_completion() {
        let path = fresh_path();
        {
            let mut timeline = Timeline::open(&path).unwrap();
            timeline.close("preparation").unwrap();
            assert!(timeline.finish().is_err());
        }
        let text = std::fs::read_to_string(&path).unwrap();
        assert!(text.contains("\"status\":\"incomplete\""));
        assert!(!text.contains("runner-body-complete"));
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn complete_is_explicit_and_not_authority() {
        let path = fresh_path();
        {
            let mut timeline = Timeline::open(&path).unwrap();
            for phase in PHASES {
                timeline.close(phase).unwrap();
            }
            timeline.finish().unwrap();
            assert!(timeline.finish().is_err());
        }
        let text = std::fs::read_to_string(&path).unwrap();
        assert!(text.contains("runner-body-complete"));
        assert!(!text.contains("\"status\":\"incomplete\""));
        assert!(!text.contains("\"authoritative\":true"));
        std::fs::remove_file(path).unwrap();
    }
}
