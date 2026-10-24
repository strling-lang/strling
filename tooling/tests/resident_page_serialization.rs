//! Deterministic ownership tests only; no native page locks or product samples.
#[path = "../resident_page_ledger.rs"]
mod ledger;

use ledger::{Failure, PageOps, SerializedLedger};
use std::sync::{Arc, Barrier};

#[derive(Default)]
struct Ops(Vec<(bool, usize)>);
impl PageOps for Ops {
    fn lock(&mut self, page: usize) -> Result<(), u32> {
        self.0.push((true, page));
        Ok(())
    }
    fn unlock(&mut self, page: usize) -> Result<(), u32> {
        self.0.push((false, page));
        Ok(())
    }
}

#[test]
fn serialized_overlaps_preserve_last_owner_semantics() {
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Ops::default();
    let first = ledger.acquire(4096, 8, &mut ops).unwrap();
    let second = ledger.acquire(4104, 8, &mut ops).unwrap();
    ledger.release(first, &mut ops).unwrap();
    assert_eq!(ops.0, [(true, 4096)]);
    ledger.release(second, &mut ops).unwrap();
    assert_eq!(ops.0, [(true, 4096), (false, 4096)]);
    assert!(!ledger.is_poisoned());
}

struct Recursive<'a> {
    ledger: &'a SerializedLedger<4, 4>,
    release_token: Option<u64>,
    callbacks: usize,
}
impl PageOps for Recursive<'_> {
    fn lock(&mut self, _: usize) -> Result<(), u32> {
        self.callbacks += 1;
        let mut nested = Ops::default();
        let result = match self.release_token {
            Some(token) => self.ledger.release(token, &mut nested),
            None => self.ledger.acquire(8192, 8, &mut nested).map(|_| ()),
        };
        assert_eq!(result, Err(Failure::ConcurrentOrReentrant));
        assert!(nested.0.is_empty());
        // Even a callback that ignores the inner failure cannot hide poison.
        Ok(())
    }
    fn unlock(&mut self, _: usize) -> Result<(), u32> {
        panic!("no speculative unlock allowed")
    }
}

#[test]
fn recursive_acquisition_cannot_publish_outer_success() {
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Recursive {
        ledger: &ledger,
        release_token: None,
        callbacks: 0,
    };
    assert_eq!(ledger.acquire(4096, 8, &mut ops), Err(Failure::Poisoned));
    assert_eq!(ops.callbacks, 1);
    assert!(ledger.is_poisoned());
    let mut later = Ops::default();
    assert_eq!(ledger.acquire(8192, 8, &mut later), Err(Failure::Poisoned));
    assert!(later.0.is_empty());
}

#[test]
fn recursive_release_cannot_unlock_an_existing_owner() {
    let ledger = SerializedLedger::<4, 4>::new();
    let mut plain = Ops::default();
    let token = ledger.acquire(8192, 8, &mut plain).unwrap();
    let mut ops = Recursive {
        ledger: &ledger,
        release_token: Some(token),
        callbacks: 0,
    };
    assert_eq!(ledger.acquire(4096, 8, &mut ops), Err(Failure::Poisoned));
    assert_eq!(ledger.release(token, &mut plain), Err(Failure::Poisoned));
    assert_eq!(plain.0, [(true, 8192)]);
}

struct Blocking {
    entered: Arc<Barrier>,
    finish: Arc<Barrier>,
}
impl PageOps for Blocking {
    fn lock(&mut self, _: usize) -> Result<(), u32> {
        self.entered.wait();
        self.finish.wait();
        Ok(())
    }
    fn unlock(&mut self, _: usize) -> Result<(), u32> {
        self.lock(0)
    }
}

fn concurrent(release: bool) {
    let ledger = Arc::new(SerializedLedger::<4, 4>::new());
    let mut plain = Ops::default();
    let token = if release {
        Some(ledger.acquire(4096, 8, &mut plain).unwrap())
    } else {
        None
    };
    let entered = Arc::new(Barrier::new(2));
    let finish = Arc::new(Barrier::new(2));
    let worker_ledger = Arc::clone(&ledger);
    let mut ops = Blocking {
        entered: Arc::clone(&entered),
        finish: Arc::clone(&finish),
    };
    let worker = std::thread::spawn(move || match token {
        Some(token) => worker_ledger.release(token, &mut ops),
        None => worker_ledger.acquire(4096, 8, &mut ops).map(|_| ()),
    });
    entered.wait();
    let mut nested = Ops::default();
    let rejected = ledger.acquire(8192, 8, &mut nested);
    finish.wait(); // Retire worker even if the following assertions fail.
    let completed = worker.join().unwrap();
    assert_eq!(rejected, Err(Failure::ConcurrentOrReentrant));
    assert_eq!(completed, Err(Failure::Poisoned));
    assert!(nested.0.is_empty());
    assert!(ledger.is_poisoned());
    assert_eq!(
        ledger.release(token.unwrap_or(1), &mut nested),
        Err(Failure::Poisoned)
    );
    assert!(nested.0.is_empty());
}

#[test]
fn racing_acquisition_poison_is_visible_before_outer_publication() {
    concurrent(false);
}

#[test]
fn racing_release_cannot_publish_success_after_poison() {
    concurrent(true);
}

struct Failing(bool);
impl PageOps for Failing {
    fn lock(&mut self, _: usize) -> Result<(), u32> {
        if self.0 {
            panic!("fixture callback panic")
        } else {
            Err(1453)
        }
    }
    fn unlock(&mut self, _: usize) -> Result<(), u32> {
        unreachable!()
    }
}

#[test]
fn callback_panic_permanently_poisoned_without_cleanup_calls() {
    let ledger = SerializedLedger::<4, 4>::new();
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        ledger.acquire(4096, 8, &mut Failing(true))
    }));
    assert!(result.is_err());
    assert!(ledger.is_poisoned());
    let mut later = Ops::default();
    assert_eq!(ledger.acquire(8192, 8, &mut later), Err(Failure::Poisoned));
    assert!(later.0.is_empty());
}

#[test]
fn native_failure_preserves_original_error_and_permanent_poison() {
    let ledger = SerializedLedger::<4, 4>::new();
    assert_eq!(
        ledger.acquire(4096, 8, &mut Failing(false)),
        Err(Failure::Lock {
            page: 4096,
            code: 1453
        })
    );
    assert!(ledger.is_poisoned());
    let mut later = Ops::default();
    assert_eq!(ledger.acquire(8192, 8, &mut later), Err(Failure::Poisoned));
    assert!(later.0.is_empty());
}
