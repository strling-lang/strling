//! Allocation-handle ownership tests; no native residency or workload execution.
#[path = "../resident_storage.rs"]
mod storage;
use std::collections::BTreeSet;
use storage::{Failure, PageOps, StorageLedger};

#[derive(Default)]
struct Ops {
    locked: BTreeSet<usize>,
    unlocks: usize,
}
impl PageOps for Ops {
    fn lock(&mut self, p: usize) -> Result<(), u32> {
        assert!(self.locked.insert(p));
        Ok(())
    }
    fn unlock(&mut self, p: usize) -> Result<(), u32> {
        assert!(self.locked.remove(&p));
        self.unlocks += 1;
        Ok(())
    }
}

#[test]
fn retirement_uses_captured_range_and_preserves_storage() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let session = backing.as_mut().start_owned(&mut ops).unwrap();
    let anchored = ops.locked.clone();
    let allocation = session.allocate_owned(13, &mut ops, || Ok(4096)).unwrap();
    assert_eq!((allocation.address(), allocation.bytes()), (4096, 13));
    allocation
        .retire(&mut ops, |address, bytes| {
            assert_eq!((address, bytes), (4096, 13));
            Ok(())
        })
        .unwrap();
    assert_eq!(ops.locked, anchored);
    session.finish(&mut ops).unwrap();
    assert!(ops.locked.is_empty());
}

#[test]
fn equal_local_tokens_on_two_issuers_cannot_cross_retire() {
    let mut first = Box::pin(StorageLedger::<4, 16>::new());
    let mut second = Box::pin(StorageLedger::<4, 16>::new());
    let mut a = Ops::default();
    let mut b = Ops::default();
    let one = first.as_mut().start_owned(&mut a).unwrap();
    let two = second.as_mut().start_owned(&mut b).unwrap();
    let x = one.allocate_owned(8, &mut a, || Ok(4096)).unwrap();
    let y = two.allocate_owned(8, &mut b, || Ok(4096)).unwrap();
    x.retire(&mut a, |_, _| Ok(())).unwrap();
    assert!(!a.locked.contains(&4096));
    assert!(b.locked.contains(&4096));
    one.finish(&mut a).unwrap();
    y.retire(&mut b, |_, _| Ok(())).unwrap();
    two.finish(&mut b).unwrap();
}

#[test]
fn overlapping_handles_keep_last_page_owner() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let session = backing.as_mut().start_owned(&mut ops).unwrap();
    let one = session.allocate_owned(8, &mut ops, || Ok(4096)).unwrap();
    let two = session.allocate_owned(8, &mut ops, || Ok(4104)).unwrap();
    one.retire(&mut ops, |_, _| Ok(())).unwrap();
    assert!(ops.locked.contains(&4096));
    two.retire(&mut ops, |_, _| Ok(())).unwrap();
    assert!(!ops.locked.contains(&4096));
    session.finish(&mut ops).unwrap();
}

#[test]
fn abandoned_handle_poison_has_no_native_cleanup() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let session = backing.as_mut().start_owned(&mut ops).unwrap();
    let a = session.allocate_owned(8, &mut ops, || Ok(4096)).unwrap();
    let before = ops.locked.clone();
    drop(a);
    assert_eq!(session.finish(&mut ops), Err(Failure::Poisoned));
    assert_eq!(ops.locked, before);
    assert_eq!(ops.unlocks, 0);
}

#[test]
fn forgotten_handle_blocks_successful_finish() {
    let mut backing = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let session = backing.as_mut().start_owned(&mut ops).unwrap();
    std::mem::forget(session.allocate_owned(8, &mut ops, || Ok(4096)).unwrap());
    assert_eq!(session.finish(&mut ops), Err(Failure::LiveLifetimes));
    assert_eq!(ops.unlocks, 0);
}

#[test]
fn failure_or_panic_during_retirement_cannot_finish() {
    for panic in [false, true] {
        let mut backing = Box::pin(StorageLedger::<4, 16>::new());
        let mut ops = Ops::default();
        let session = backing.as_mut().start_owned(&mut ops).unwrap();
        let a = session.allocate_owned(8, &mut ops, || Ok(4096)).unwrap();
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            a.retire(&mut ops, |address, bytes| {
                assert_eq!((address, bytes), (4096, 8));
                if panic {
                    panic!("retirement panic")
                }
                Err(1453)
            })
        }));
        if panic {
            assert!(result.is_err());
        } else {
            assert_eq!(result.unwrap(), Err(Failure::Retirement { code: 1453 }));
        }
        assert_eq!(session.finish(&mut ops), Err(Failure::Poisoned));
    }
}

fn main() {}

#[cfg(double_retire)]
fn duplicate_consumption() {
    let mut b = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let s = b.as_mut().start_owned(&mut ops).unwrap();
    let a = s.allocate_owned(8, &mut ops, || Ok(4096)).unwrap();
    a.retire(&mut ops, |_, _| Ok(())).unwrap();
    a.retire(&mut ops, |_, _| Ok(())).unwrap();
}

#[cfg(early_finish)]
fn finish_before_handle_use() {
    let mut b = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let s = b.as_mut().start_owned(&mut ops).unwrap();
    let a = s.allocate_owned(8, &mut ops, || Ok(4096)).unwrap();
    s.finish(&mut ops).unwrap();
    a.retire(&mut ops, |_, _| Ok(())).unwrap();
}

#[cfg(copy_handle)]
fn handle_is_not_copy() {
    fn require_copy<T: Copy>() {}
    require_copy::<storage::OwnedAllocation<'_, 4, 16>>();
}

#[cfg(raw_entry)]
fn raw_token_operation() {
    let mut b = Box::pin(StorageLedger::<4, 16>::new());
    let mut ops = Ops::default();
    let mut s = b.as_mut().start_owned(&mut ops).unwrap();
    std::mem::forget(s.allocate_owned(8, &mut ops, || Ok(4096)).unwrap());
    s.release(2, &mut ops).unwrap();
}
