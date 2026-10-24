//! Storage-only mocked ownership; never actual residency or certification.
#[path = "../resident_storage.rs"]
mod storage;
use std::collections::BTreeSet;
use storage::{Failure, PageOps, StorageLedger};

#[derive(Default)]
struct Ops {
    locked: BTreeSet<usize>,
    calls: Vec<(bool, usize)>,
}
impl PageOps for Ops {
    fn lock(&mut self, page: usize) -> Result<(), u32> {
        self.calls.push((true, page));
        assert!(self.locked.insert(page));
        Ok(())
    }
    fn unlock(&mut self, page: usize) -> Result<(), u32> {
        self.calls.push((false, page));
        assert!(self.locked.remove(&page));
        Ok(())
    }
}

#[test]
fn entire_pinned_object_is_owned_until_explicit_finish() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let address = backing.as_ref().get_ref() as *const _ as usize;
    let size = std::mem::size_of_val(backing.as_ref().get_ref());
    let expected: BTreeSet<_> = (address..address + size).map(|b| b / 4096 * 4096).collect();
    let mut ops = Ops::default();
    let session = backing.as_mut().start(&mut ops).unwrap();
    assert_eq!(ops.locked, expected);
    session.finish(&mut ops).unwrap();
    assert!(ops.locked.is_empty());
    assert!(!backing.is_poisoned());
    let count = ops.calls.len();
    assert!(matches!(
        backing.as_mut().start(&mut ops),
        Err(Failure::Poisoned)
    ));
    assert_eq!(ops.calls.len(), count);
}

#[test]
fn overlapping_client_release_cannot_unlock_storage() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let address = backing.as_ref().get_ref() as *const _ as usize;
    let mut ops = Ops::default();
    let mut session = backing.as_mut().start(&mut ops).unwrap();
    let root_pages = ops.locked.clone();
    let calls = ops.calls.len();
    let token = session.acquire(address, 1, &mut ops).unwrap();
    session.release(token, &mut ops).unwrap();
    assert_eq!(ops.locked, root_pages);
    assert_eq!(ops.calls.len(), calls);
    session.finish(&mut ops).unwrap();
    assert!(ops.locked.is_empty());
}

#[test]
fn live_client_blocks_teardown_before_any_unlock() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let mut session = backing.as_mut().start(&mut ops).unwrap();
    session.acquire(4096, 16, &mut ops).unwrap();
    let before = ops.calls.clone();
    assert_eq!(session.finish(&mut ops), Err(Failure::LiveLifetimes));
    assert_eq!(ops.calls, before);
    assert!(backing.is_poisoned());
}

#[test]
fn guessed_anchor_token_cannot_release_storage() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let mut session = backing.as_mut().start(&mut ops).unwrap();
    let before = ops.calls.clone();
    assert_eq!(session.release(1, &mut ops), Err(Failure::UnknownToken));
    assert_eq!(session.finish(&mut ops), Err(Failure::Poisoned));
    assert_eq!(ops.calls, before);
    assert!(backing.is_poisoned());
}

#[test]
fn abandoned_session_poison_never_attempts_native_cleanup() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let session = backing.as_mut().start(&mut ops).unwrap();
    let before = ops.calls.clone();
    drop(session);
    assert_eq!(ops.calls, before);
    assert!(backing.is_poisoned());
    assert!(matches!(
        backing.as_mut().start(&mut ops),
        Err(Failure::Poisoned)
    ));
    assert_eq!(ops.calls, before);
}

#[test]
fn bootstrap_capacity_failure_is_terminal_without_callbacks() {
    let mut backing = Box::pin(StorageLedger::<0, 0>::new());
    let mut ops = Ops::default();
    assert!(matches!(
        backing.as_mut().start(&mut ops),
        Err(Failure::Capacity)
    ));
    assert!(backing.is_poisoned());
    assert!(matches!(
        backing.as_mut().start(&mut ops),
        Err(Failure::Poisoned)
    ));
    assert!(ops.calls.is_empty());
}
