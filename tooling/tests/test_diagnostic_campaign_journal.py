"""Sample-free journal tests; never execute a product or certification workload."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tooling import diagnostic_campaign_journal as journal


ROOT = Path(__file__).resolve().parents[2]


class DiagnosticCampaignJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="diagnostic-journal-unit-", dir=ROOT / "target/codex-tools"
        )
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "campaign"
        self.pins = {
            "source_sha": "a" * 40,
            "source_tree": "b" * 40,
            "recipe_sha256": "c" * 64,
            "implementation_sha256": "d" * 64,
            "environment_sha256": "e" * 64,
        }
        self.plan = {
            "version": 1,
            "kind": "session-bound-sample-free-diagnostic",
            "authoritative": False,
            "certification_eligible": False,
            "pins": self.pins,
            "units": [
                {"id": mode + str(i), "maximum_elapsed_ns": 1_000_000_000}
                for i, mode in enumerate(("s", "c", "c", "s", "s", "c"))
            ],
        }
        self.owner = {"pid": os.getpid(), "birth": "134371884171628812"}
        self.plan_hash = journal.create(self.path, self.plan)

    def claim(self, index=0, previous=None, **kwargs):
        return journal.claim(
            self.path,
            index,
            expected_plan_sha256=self.plan_hash,
            expected_previous_sha256=previous or self.plan_hash,
            observed_pins=self.pins,
            owner=self.owner,
            **kwargs,
        )

    def finish(self, claim, **kwargs):
        options = dict(
            status="passed",
            result_sha256="f" * 64,
            elapsed_ns=123,
            observed_pins=self.pins,
            owner=self.owner,
            children_quiescent=True,
        )
        options.update(kwargs)
        return journal.finish(claim, **options)

    def inspect(self):
        return journal.inspect(self.path, expected_plan_sha256=self.plan_hash)

    def test_complete_all_six_units_and_no_seventh(self):
        previous = self.plan_hash
        for index in range(6):
            self.assertEqual(self.inspect()["next_unit"], index)
            previous = self.finish(self.claim(index, previous))
        result = self.inspect()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["completed"], 6)
        self.assertEqual(result["checkpoint_sha256"], previous)
        self.assertIsNone(result["next_unit"])
        self.assertFalse(result["certification_eligible"])
        with self.assertRaises(journal.JournalError):
            self.claim(6, previous)

    def test_claim_is_consumed_before_work_and_cannot_be_replayed(self):
        self.claim()
        self.assertEqual(self.inspect()["status"], "incomplete")
        self.assertIsNone(self.inspect()["next_unit"])
        for index in (0, 1):
            with self.assertRaises(journal.JournalError):
                self.claim(index)

    def test_exact_previous_checkpoint_required(self):
        previous = self.finish(self.claim())
        with self.assertRaises(journal.JournalError):
            self.claim(1)
        self.finish(self.claim(1, previous))

    def test_terminal_is_exclusive(self):
        claim = self.claim()
        self.finish(claim)
        original = (self.path / "0000.terminal.json").read_bytes()
        with self.assertRaises(journal.JournalError):
            self.finish(claim)
        self.assertEqual((self.path / "0000.terminal.json").read_bytes(), original)

    def test_failed_and_incomplete_results_block_later_units(self):
        claim = self.claim()
        self.finish(claim, status="failed")
        self.assertEqual(self.inspect()["status"], "failed")
        self.assertEqual(self.inspect()["completed"], 0)
        with self.assertRaises(journal.JournalError):
            self.claim(1, self.inspect()["checkpoint_sha256"])

    def test_elapsed_bound_failure_is_retained_not_filtered(self):
        self.finish(self.claim(), elapsed_ns=1_000_000_001)
        terminal = json.loads((self.path / "0000.terminal.json").read_bytes())
        self.assertEqual(terminal["reported_status"], "passed")
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["elapsed_ns"], 1_000_000_001)
        self.assertIn("elapsed-bound", terminal["failures"])
        self.assertEqual(self.inspect()["status"], "failed")

    def test_source_drift_after_claim_is_retained_and_blocks_success(self):
        changed = {**self.pins, "source_sha": "0" * 40}
        self.finish(self.claim(), observed_pins=changed)
        self.assertEqual(self.inspect()["status"], "failed")
        terminal = json.loads((self.path / "0000.terminal.json").read_bytes())
        self.assertEqual(terminal["observed_pins"], changed)
        self.assertIn("pin-drift", terminal["failures"])

    def test_live_children_cannot_close_successfully(self):
        self.finish(self.claim(), children_quiescent=False)
        self.assertEqual(self.inspect()["status"], "failed")

    def test_foreign_owner_cannot_seal_claim(self):
        claim = self.claim()
        with self.assertRaises(journal.JournalError):
            self.finish(claim, owner={**self.owner, "birth": "134371884171628813"})
        self.assertFalse((self.path / "0000.terminal.json").exists())

    def test_preclaim_pins_and_plan_hash_fail_before_acquisition(self):
        for field in self.pins:
            changed = {**self.pins, field: "0" * len(self.pins[field])}
            with self.assertRaises(journal.JournalError):
                journal.claim(
                    self.path,
                    0,
                    expected_plan_sha256=self.plan_hash,
                    expected_previous_sha256=self.plan_hash,
                    observed_pins=changed,
                    owner=self.owner,
                )
        with self.assertRaises(journal.JournalError):
            journal.inspect(self.path, expected_plan_sha256="0" * 64)
        self.assertEqual(list(self.path.iterdir()), [self.path / "plan.json"])

    def test_plan_rejects_authority_and_denominator_mutations(self):
        mutations = [
            ("version", True),
            ("kind", "certification"),
            ("authoritative", True),
            ("certification_eligible", 0),
            ("units", []),
            ("units", [self.plan["units"][0]] * 2),
            ("pins", {**self.pins, "extra": "0" * 64}),
            ("extra", True),
            ("units", [{"id": "../escape", "maximum_elapsed_ns": 3}]),
            ("units", [{"id": "unit", "maximum_elapsed_ns": True}]),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                invalid = {**self.plan, key: value}
                destination = Path(self.temporary.name) / "invalid"
                with self.assertRaises(journal.JournalError):
                    journal.create(destination, invalid)
                self.assertFalse(destination.exists())

    def test_malformed_and_partial_receipts_are_never_repaired(self):
        claim = self.claim()
        path = self.path / "0000.claim.json"
        for content in (b"{", b'{"index":0,"index":0}', b"{}", b"[]"):
            path.write_bytes(content)
            with self.assertRaises(journal.JournalError):
                self.inspect()
            with self.assertRaises(journal.JournalError):
                self.finish(claim)
            self.assertEqual(path.read_bytes(), content)

    def test_missing_or_transplanted_prefix_is_rejected(self):
        first = self.finish(self.claim())
        self.finish(self.claim(1, first))
        path = self.path / "0001.terminal.json"
        path.write_bytes((self.path / "0000.terminal.json").read_bytes())
        with self.assertRaises(journal.JournalError):
            self.inspect()

    def test_unexpected_receipt_does_not_extend_the_plan(self):
        (self.path / "9999.claim.json").write_bytes(b"{}")
        with self.assertRaises(journal.JournalError):
            self.inspect()

    def test_hardlinked_receipt_rejected(self):
        os.link(self.path / "plan.json", Path(self.temporary.name) / "alias")
        with self.assertRaises(journal.JournalError):
            self.inspect()

    def test_noncanonical_plan_rejected_even_with_matching_hash(self):
        path = self.path / "plan.json"
        raw = json.dumps(self.plan, indent=2).encode()
        path.write_bytes(raw)
        with self.assertRaises(journal.JournalError):
            journal.inspect(
                self.path, expected_plan_sha256=hashlib.sha256(raw).hexdigest()
            )

    def test_real_competing_claimants_and_interrupted_owner(self):
        code = (
            "import json,sys; from pathlib import Path; "
            "from tooling import diagnostic_campaign_journal as j; "
            "p=Path(sys.argv[1]); d=json.loads((p/'plan.json').read_bytes()); "
            "j.claim(p,0,expected_plan_sha256=sys.argv[2],"
            "expected_previous_sha256=sys.argv[2],observed_pins=d['pins'],"
            "owner={'pid':123,'birth':'123'}); print('claimed')"
        )
        processes = [
            subprocess.Popen(
                [sys.executable, "-B", "-c", code, str(self.path), self.plan_hash],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(2)
        ]
        for child in processes:
            child.communicate(timeout=30)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        self.assertEqual(self.inspect()["status"], "incomplete")
        with self.assertRaises(journal.JournalError):
            self.claim()

    def test_reader_recomputes_failure_disposition(self):
        self.finish(self.claim(), elapsed_ns=1_000_000_001)
        path = self.path / "0000.terminal.json"
        terminal = json.loads(path.read_bytes())
        terminal["status"] = "passed"
        terminal["failures"] = []
        path.write_bytes(journal.canonical_bytes(terminal))
        with self.assertRaises(journal.JournalError):
            self.inspect()

    def test_real_separate_processes_advance_only_completed_units(self):
        code = (
            "import json,os,sys; from pathlib import Path; "
            "from tooling import diagnostic_campaign_journal as j; "
            "p=Path(sys.argv[1]); d=json.loads((p/'plan.json').read_bytes()); "
            "o={'pid':os.getpid(),'birth':'123'}; "
            "c=j.claim(p,int(sys.argv[4]),expected_plan_sha256=sys.argv[2],"
            "expected_previous_sha256=sys.argv[3],observed_pins=d['pins'],owner=o); "
            "print(j.finish(c,status='passed',result_sha256='f'*64,elapsed_ns=123,"
            "observed_pins=d['pins'],owner=o,children_quiescent=True))"
        )
        previous = self.plan_hash
        for index in range(6):
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    code,
                    str(self.path),
                    self.plan_hash,
                    previous,
                    str(index),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            previous = result.stdout.strip()
            self.assertEqual(previous, self.inspect()["checkpoint_sha256"])
        self.assertEqual(self.inspect()["status"], "complete")

    def test_partial_terminal_and_explicit_incomplete_block_next_unit(self):
        self.finish(self.claim(), status="incomplete")
        self.assertEqual(self.inspect()["status"], "incomplete")
        with self.assertRaises(journal.JournalError):
            self.claim(1, self.inspect()["checkpoint_sha256"])
        (self.path / "0000.terminal.json").write_bytes(b'{"status":')
        with self.assertRaises(journal.JournalError):
            self.claim(1)

    def test_malformed_completion_rejected_without_fabricated_terminal(self):
        claim = self.claim()
        for kwargs in (
            {"elapsed_ns": True},
            {"elapsed_ns": -1},
            {"result_sha256": "?"},
            {"status": "waived"},
            {"children_quiescent": 1},
            {"owner": {"pid": True, "birth": "123"}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(journal.JournalError):
                self.finish(claim, **kwargs)
        self.assertFalse((self.path / "0000.terminal.json").exists())


if __name__ == "__main__":
    unittest.main()
