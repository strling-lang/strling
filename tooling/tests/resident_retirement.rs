//! Deterministic free-ordering checks, not native allocator qualification.
#[path = "../resident_page_ledger.rs"]
mod ledger;
#[path = "../resident_storage.rs"]
mod storage;

use ledger::{Failure, PageOps, SerializedLedger};
use std::cell::RefCell;

struct Ops<'a> {
    events: &'a RefCell<Vec<&'static str>>,
    fail_unlock: bool,
}
impl PageOps for Ops<'_> {
    fn lock(&mut self, _: usize) -> Result<(), u32> {
        self.events.borrow_mut().push("lock");
        Ok(())
    }
    fn unlock(&mut self, _: usize) -> Result<(), u32> {
        self.events.borrow_mut().push("unlock");
        if self.fail_unlock {
            Err(158)
        } else {
            Ok(())
        }
    }
}

#[test]
fn retirement_orders_unlock_before_free_and_allows_fresh_reuse() {
    let events = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Ops {
        events: &events,
        fail_unlock: false,
    };
    let token = ledger.acquire(4096, 8, &mut ops).unwrap();
    ledger
        .retire(token, &mut ops, || {
            events.borrow_mut().push("free");
            Ok(())
        })
        .unwrap();
    let next = ledger.acquire(4096, 8, &mut ops).unwrap();
    assert!(next > token);
    assert_eq!(*events.borrow(), ["lock", "unlock", "free", "lock"]);
}

#[test]
fn shared_page_stays_locked_when_one_allocation_retires() {
    let events = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Ops {
        events: &events,
        fail_unlock: false,
    };
    let one = ledger.acquire(4096, 8, &mut ops).unwrap();
    let two = ledger.acquire(4104, 8, &mut ops).unwrap();
    ledger
        .retire(one, &mut ops, || {
            events.borrow_mut().push("free");
            Ok(())
        })
        .unwrap();
    assert_eq!(*events.borrow(), ["lock", "free"]);
    ledger.release(two, &mut ops).unwrap();
    assert_eq!(*events.borrow(), ["lock", "free", "unlock"]);
}

#[test]
fn invalid_token_or_unlock_failure_never_invokes_free() {
    for invalid in [false, true] {
        let events = RefCell::new(Vec::new());
        let ledger = SerializedLedger::<4, 4>::new();
        let mut ops = Ops {
            events: &events,
            fail_unlock: true,
        };
        let token = ledger.acquire(4096, 8, &mut ops).unwrap();
        let result = ledger.retire(if invalid { token + 1 } else { token }, &mut ops, || {
            panic!("free forbidden")
        });
        assert_eq!(
            result,
            Err(if invalid {
                Failure::UnknownToken
            } else {
                Failure::Unlock {
                    page: 4096,
                    code: 158,
                }
            })
        );
        assert!(ledger.is_poisoned());
    }
}

#[test]
fn raw_free_failure_and_panic_poison_without_retry() {
    for panic in [false, true] {
        let events = RefCell::new(Vec::new());
        let ledger = SerializedLedger::<4, 4>::new();
        let mut ops = Ops {
            events: &events,
            fail_unlock: false,
        };
        let token = ledger.acquire(4096, 8, &mut ops).unwrap();
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            ledger.retire(token, &mut ops, || {
                if panic {
                    panic!("free panic")
                }
                Err(1453)
            })
        }));
        if panic {
            assert!(result.is_err());
        } else {
            assert_eq!(result.unwrap(), Err(Failure::Retirement { code: 1453 }));
        }
        assert!(ledger.is_poisoned());
        assert_eq!(
            ledger.retire(token, &mut ops, || panic!("no retry")),
            Err(Failure::Poisoned)
        );
    }
}

#[test]
fn reentrant_free_cannot_publish_success_or_reuse_address() {
    let events = RefCell::new(Vec::new());
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = Ops {
        events: &events,
        fail_unlock: false,
    };
    let token = ledger.acquire(4096, 8, &mut ops).unwrap();
    let result = ledger.retire(token, &mut ops, || {
        let mut nested = Ops {
            events: &events,
            fail_unlock: false,
        };
        assert_eq!(
            ledger.acquire(4096, 8, &mut nested),
            Err(Failure::ConcurrentOrReentrant)
        );
        Ok(())
    });
    assert_eq!(result, Err(Failure::Poisoned));
    assert_eq!(*events.borrow(), ["lock", "unlock"]);
}

#[test]
fn storage_anchor_cannot_be_freed_through_retirement() {
    struct StorageOps;
    impl storage::PageOps for StorageOps {
        fn lock(&mut self, _: usize) -> Result<(), u32> {
            Ok(())
        }
        fn unlock(&mut self, _: usize) -> Result<(), u32> {
            panic!("anchor unlock forbidden")
        }
    }
    let mut backing = Box::pin(storage::StorageLedger::<4, 16>::new());
    let mut ops = StorageOps;
    let mut session = backing.as_mut().start(&mut ops).unwrap();
    assert_eq!(
        session.retire(1, &mut ops, || panic!("anchor free forbidden")),
        Err(storage::Failure::UnknownToken)
    );
    assert_eq!(session.finish(&mut ops), Err(storage::Failure::Poisoned));
}

#[test]
fn concurrent_entry_during_free_cannot_publish_success() {
    struct QuietOps;
    impl PageOps for QuietOps {
        fn lock(&mut self, _: usize) -> Result<(), u32> {
            Ok(())
        }
        fn unlock(&mut self, _: usize) -> Result<(), u32> {
            Ok(())
        }
    }
    let ledger = SerializedLedger::<4, 4>::new();
    let token = ledger.acquire(4096, 8, &mut QuietOps).unwrap();
    let entered = std::sync::Barrier::new(2);
    let rejected = std::sync::Barrier::new(2);
    std::thread::scope(|scope| {
        let owner = scope.spawn(|| {
            ledger.retire(token, &mut QuietOps, || {
                entered.wait();
                rejected.wait();
                Ok(())
            })
        });
        entered.wait();
        assert_eq!(
            ledger.acquire(4096, 8, &mut QuietOps),
            Err(Failure::ConcurrentOrReentrant)
        );
        rejected.wait();
        assert_eq!(owner.join().unwrap(), Err(Failure::Poisoned));
    });
    assert!(ledger.is_poisoned());
}

#[test]
fn poison_during_unlock_skips_free() {
    struct ReentrantOps<'a>(&'a SerializedLedger<4, 4>);
    impl PageOps for ReentrantOps<'_> {
        fn lock(&mut self, _: usize) -> Result<(), u32> {
            Ok(())
        }
        fn unlock(&mut self, _: usize) -> Result<(), u32> {
            let ledger = self.0;
            assert_eq!(
                ledger.acquire(8192, 8, self),
                Err(Failure::ConcurrentOrReentrant)
            );
            Ok(())
        }
    }
    let ledger = SerializedLedger::<4, 4>::new();
    let mut ops = ReentrantOps(&ledger);
    let token = ledger.acquire(4096, 8, &mut ops).unwrap();
    assert_eq!(
        ledger.retire(token, &mut ops, || panic!("free forbidden after poison")),
        Err(Failure::Poisoned)
    );
}
