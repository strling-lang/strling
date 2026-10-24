//! Deterministic allocation-route checks, not native allocator qualification.
#[path = "../resident_page_ledger.rs"]
mod ledger;
#[path = "../resident_storage.rs"]
mod storage;
use ledger::{Failure, PageOps, SerializedLedger};
use std::cell::RefCell;

struct Ops<'a>(&'a RefCell<Vec<(&'static str, usize)>>);
impl PageOps for Ops<'_> {
    fn lock(&mut self, page: usize) -> Result<(), u32> {
        self.0.borrow_mut().push(("lock", page));
        Ok(())
    }
    fn unlock(&mut self, page: usize) -> Result<(), u32> {
        self.0.borrow_mut().push(("unlock", page));
        Ok(())
    }
}

#[test]
fn allocation_registers_before_publish_and_preserves_shared_reuse() {
    let log = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Ops(&log);
    let (one, address) = ledger
        .allocate(8, &mut ops, || {
            log.borrow_mut().push(("allocate", 4096));
            Ok(4096)
        })
        .unwrap();
    assert_eq!(address, 4096);
    assert_eq!(*log.borrow(), [("allocate", 4096), ("lock", 4096)]);
    let (two, _) = ledger.allocate(8, &mut ops, || Ok(4104)).unwrap();
    ledger
        .retire(one, &mut ops, || {
            log.borrow_mut().push(("free", 4096));
            Ok(())
        })
        .unwrap();
    assert_eq!(log.borrow().len(), 3);
    ledger.retire(two, &mut ops, || Ok(())).unwrap();
    let (three, _) = ledger.allocate(8, &mut ops, || Ok(4096)).unwrap();
    assert!(three > two);
    assert_eq!(&log.borrow()[3..], [("unlock", 4096), ("lock", 4096)]);
}

#[test]
fn impossible_request_rejects_before_allocator() {
    for bytes in [0, 8193, usize::MAX] {
        let log = RefCell::new(Vec::new());
        let ledger = SerializedLedger::<1, 2>::new();
        assert_eq!(
            ledger.allocate(bytes, &mut Ops(&log), || panic!("allocator forbidden")),
            Err(if bytes == 0 {
                Failure::InvalidRange
            } else {
                Failure::Capacity
            })
        );
        assert!(log.borrow().is_empty());
        assert!(ledger.is_poisoned());
    }
    let log = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<1, 2>::new();
    let mut ops = Ops(&log);
    ledger.acquire(4096, 1, &mut ops).unwrap();
    assert_eq!(
        ledger.allocate(1, &mut ops, || panic!("no lifetime slot")),
        Err(Failure::Capacity)
    );
}

#[test]
fn invalid_allocator_ranges_never_lock_or_publish() {
    for address in [0, usize::MAX] {
        let log = RefCell::new(Vec::new());
        let ledger = SerializedLedger::<2, 2>::new();
        assert_eq!(
            ledger.allocate(2, &mut Ops(&log), || Ok(address)),
            Err(Failure::InvalidRange)
        );
        assert!(log.borrow().is_empty());
        assert!(ledger.is_poisoned());
    }
    let log = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<2, 1>::new();
    assert_eq!(
        ledger.allocate(4096, &mut Ops(&log), || Ok(4097)),
        Err(Failure::Capacity)
    );
    assert!(log.borrow().is_empty());
}

#[test]
fn allocator_failure_and_panic_poison_without_retry() {
    for panic in [false, true] {
        let log = RefCell::new(Vec::new());
        let ledger = SerializedLedger::<2, 2>::new();
        let mut ops = Ops(&log);
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            ledger.allocate(8, &mut ops, || {
                if panic {
                    panic!("allocator panic");
                }
                Err(1453)
            })
        }));
        if panic {
            assert!(result.is_err());
        } else {
            assert_eq!(result.unwrap(), Err(Failure::Allocation { code: 1453 }));
        }
        assert_eq!(
            ledger.allocate(8, &mut ops, || panic!("no retry")),
            Err(Failure::Poisoned)
        );
        assert!(log.borrow().is_empty());
    }
}

#[test]
fn allocator_reentry_prevents_page_callbacks() {
    let log = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<2, 2>::new();
    assert_eq!(
        ledger.allocate(8, &mut Ops(&log), || {
            assert_eq!(
                ledger.acquire(8192, 8, &mut Ops(&log)),
                Err(Failure::ConcurrentOrReentrant)
            );
            Ok(4096)
        }),
        Err(Failure::Poisoned)
    );
    assert!(log.borrow().is_empty());
}

#[test]
fn concurrent_allocator_entry_cannot_publish_success() {
    let ledger = SerializedLedger::<2, 2>::new();
    let entered = std::sync::Barrier::new(2);
    let rejected = std::sync::Barrier::new(2);
    std::thread::scope(|scope| {
        let owner = scope.spawn(|| {
            let log = RefCell::new(Vec::new());
            let result = ledger.allocate(8, &mut Ops(&log), || {
                entered.wait();
                rejected.wait();
                Ok(4096)
            });
            assert!(log.borrow().is_empty());
            result
        });
        entered.wait();
        let log = RefCell::new(Vec::new());
        let mut called = false;
        let contender = ledger.allocate(8, &mut Ops(&log), || {
            called = true;
            Ok(8192)
        });
        rejected.wait();
        let completed = owner.join().unwrap();
        assert_eq!(contender, Err(Failure::ConcurrentOrReentrant));
        assert!(!called);
        assert_eq!(completed, Err(Failure::Poisoned));
    });
}

#[test]
fn partial_lock_failure_preserves_raw_error_without_cleanup() {
    struct Failing(Vec<usize>);
    impl PageOps for Failing {
        fn lock(&mut self, p: usize) -> Result<(), u32> {
            self.0.push(p);
            if p == 8192 {
                Err(1453)
            } else {
                Ok(())
            }
        }
        fn unlock(&mut self, _: usize) -> Result<(), u32> {
            panic!("no speculative cleanup")
        }
    }
    let ledger = SerializedLedger::<2, 2>::new();
    let mut ops = Failing(Vec::new());
    assert_eq!(
        ledger.allocate(4097, &mut ops, || Ok(4096)),
        Err(Failure::Lock {
            page: 8192,
            code: 1453
        })
    );
    assert_eq!(ops.0, [4096, 8192]);
    assert!(ledger.is_poisoned());
}

#[test]
fn storage_session_allocation_keeps_anchor_until_finish() {
    struct StorageOps(std::collections::BTreeSet<usize>);
    impl storage::PageOps for StorageOps {
        fn lock(&mut self, p: usize) -> Result<(), u32> {
            assert!(self.0.insert(p));
            Ok(())
        }
        fn unlock(&mut self, p: usize) -> Result<(), u32> {
            assert!(self.0.remove(&p));
            Ok(())
        }
    }
    let mut backing = Box::pin(storage::StorageLedger::<4, 16>::new());
    let mut ops = StorageOps(Default::default());
    let mut session = backing.as_mut().start(&mut ops).unwrap();
    let anchored = ops.0.clone();
    let (token, address) = session.allocate(8, &mut ops, || Ok(4096)).unwrap();
    assert_eq!(address, 4096);
    session.retire(token, &mut ops, || Ok(())).unwrap();
    assert_eq!(ops.0, anchored);
    session.finish(&mut ops).unwrap();
    assert!(ops.0.is_empty());
}
