"""Data-only receipt attacks; all fixtures synthetic, no product evidence."""

import copy
import hashlib
import json
import unittest

from tooling import performance_envelope_receipts as reader


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(
            command=["C:/fixture.exe", "argument"],
            cwd="C:/fixture",
            source_sha="a" * 40,
            inputs={"C:/fixture.exe": "b" * 64},
            environment_sha256="c" * 64,
            selected_cpu=1,
            timeout_seconds=10,
            implementation_sha256="d" * 64,
            job_implementation_sha256="e" * 64,
            controls_implementation_sha256="f" * 64,
            observation_implementation_sha256="0" * 64,
        )
        self.files = {
            "plan.json": encoded(self.plan),
            "stdout.bin": b"raw\x00\xff",
            "stderr.bin": b"",
            "suspended.json": encoded(
                dict(
                    pid=17,
                    birth="1000",
                    exit="987654",
                    kernel=10,
                    user=20,
                    exited_before_query=False,
                )
            ),
            "root-exit.json": encoded(
                dict(
                    pid=17,
                    birth="1000",
                    exit="2000",
                    kernel=11,
                    user=21,
                    exited_before_query=True,
                )
            ),
            "lifecycle-wakeups.json": encoded(
                [
                    dict(
                        kind="completion-wakeup",
                        message=6,
                        pid=17,
                        observed_ns=41,
                        wait_milliseconds=100,
                    ),
                    dict(kind="wait-timeout", observed_ns=42, wait_milliseconds=1),
                ]
            ),
        }
        self.row = dict(
            contract="unqualified-process-tree-envelope-v2",
            status="observed",
            authoritative=False,
            certification_eligible=False,
            baseline_admission=False,
            plan_sha256=digest(self.files["plan.json"]),
            clock="perf_counter_ns",
            cpu_unit="raw-job-accounting-100ns",
            logs={},
            artifacts={},
            action_begin_ns=10,
            release_begin_ns=20,
            root_exit_observed_ns=40,
            action_end_ns=70,
            whole_action_ns=60,
            finished_ns=80,
            exit_code=0,
            controls=dict(
                affinity_mask=2,
                cpu_set_id=17,
                root_high_qos=True,
                job_limit_flags=0x2010,
                root_resumed=False,
                ancestor_quota_qualified=False,
                descendant_power_qualified=False,
            ),
            accounting=dict(
                query_begin_ns=50,
                query_end_ns=60,
                total_processes=2,
                active_processes=0,
                limit_terminated_processes=0,
                user_100ns=1,
                kernel_100ns=1,
            ),
            cleanup=dict(quiescent=True, terminated=False),
        )
        self.seal()

    def seal(self):
        for group, names in (("logs", reader.LOGS), ("artifacts", reader.ARTIFACTS)):
            self.row[group] = {
                name: dict(sha256=digest(self.files[name]), bytes=len(self.files[name]))
                for name in names
            }
        self.files["terminal.json"] = encoded(self.row)
        self.pin = digest(self.files["terminal.json"])

    def verify(self):
        return reader.verify_process_receipt(self.files, self.pin, self.plan)

    def test_complete_raw_bundle_never_grants_admission(self):
        value = self.verify()
        self.assertEqual(value["whole_action_ns"], 60)
        for field in (
            "authoritative",
            "certification_eligible",
            "baseline_admission",
            "ancestor_quota_qualified",
            "independence_qualified",
        ):
            self.assertIs(value[field], False)

    def test_each_byte_stream_tamper_rejected_by_original_pin(self):
        for name in reader.FILES:
            with self.subTest(name=name):
                self.setUp()
                self.files[name] += b" "
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_same_size_replacement_rejected(self):
        self.files["stdout.bin"] = b"raw\x00\xfe"
        with self.assertRaisesRegex(reader.ReceiptError, "hash"):
            self.verify()

    def test_inner_hash_refresh_cannot_replace_external_pin(self):
        old = self.pin
        self.files["stdout.bin"] = b"changed"
        self.seal()
        self.pin = old
        with self.assertRaisesRegex(reader.ReceiptError, "external terminal"):
            self.verify()

    def test_missing_or_extra_file_denominator(self):
        for name in reader.FILES:
            with self.subTest(name=name):
                self.setUp()
                del self.files[name]
                with self.assertRaises(reader.ReceiptError):
                    self.verify()
        self.setUp()
        self.files["../foreign"] = b""
        with self.assertRaises(reader.ReceiptError):
            self.verify()

    def test_independent_plan_every_field_is_enforced(self):
        for key in reader.PLAN:
            with self.subTest(key=key):
                self.setUp()
                value = self.plan[key]
                if type(value) is str:
                    self.plan[key] = "9" * len(value)
                elif type(value) is int:
                    self.plan[key] += 1
                elif type(value) is list:
                    self.plan[key] = value + ["extra"]
                else:
                    self.plan[key] = {**value, "extra": "9" * 64}
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_v1_and_failed_receipts_are_not_promoted(self):
        for key, value in (
            ("contract", "unqualified-process-tree-envelope-v1"),
            ("status", "failed"),
            ("certification_eligible", True),
            ("extra", 1),
        ):
            with self.subTest(key=key):
                self.setUp()
                self.row[key] = value
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_exact_types_clock_order_and_natural_retirement(self):
        attacks = [
            ((), "exit_code", False),
            ((), "whole_action_ns", 61),
            ((), "release_begin_ns", 41),
            ((), "finished_ns", 69),
            (("controls",), "affinity_mask", 4),
            (("controls",), "cpu_set_id", True),
            (("controls",), "ancestor_quota_qualified", True),
            (("controls",), "job_limit_flags", 0x2810),
            (("cleanup",), "terminated", True),
            (("cleanup",), "quiescent", 1),
            (("accounting",), "active_processes", 1),
            (("accounting",), "limit_terminated_processes", 1),
            (("accounting",), "total_processes", 0),
            (("accounting",), "query_begin_ns", 39),
            (("accounting",), "kernel_100ns", -1),
        ]
        for path, key, value in attacks:
            with self.subTest(path=path, key=key):
                self.setUp()
                target = self.row
                for part in path:
                    target = target[part]
                target[key] = value
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_identity_forgery_and_counter_discontinuity(self):
        for key, value in (
            ("pid", 18),
            ("birth", "1001"),
            ("exit", "999"),
            ("user", 19),
            ("kernel", False),
            ("exited_before_query", False),
            ("extra", 0),
        ):
            with self.subTest(key=key):
                self.setUp()
                row = json.loads(self.files["root-exit.json"])
                row[key] = value
                self.files["root-exit.json"] = encoded(row)
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_notifications_never_substitute_for_accounting(self):
        self.files["lifecycle-wakeups.json"] = b"[]"
        self.seal()
        self.verify()
        self.row["accounting"]["active_processes"] = 1
        self.seal()
        with self.assertRaises(reader.ReceiptError):
            self.verify()

    def test_malformed_lifecycle(self):
        for key, value in (
            ("kind", "invented"),
            ("observed_ns", 51),
            ("observed_ns", 39),
            ("wait_milliseconds", 101),
            ("message", True),
            ("pid", -1),
            ("extra", 0),
        ):
            with self.subTest(key=key, value=value):
                self.setUp()
                events = json.loads(self.files["lifecycle-wakeups.json"])
                events[0][key] = value
                self.files["lifecycle-wakeups.json"] = encoded(events)
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_duplicate_nonfinite_invalid_utf8_and_wrong_shapes(self):
        for data in (
            b'{"pid":17,"pid":18}',
            b'{"pid":NaN}',
            b'{"pid":Infinity}',
            b"\xff",
            b"[]",
            b"null",
        ):
            with self.subTest(data=data):
                self.setUp()
                self.files["root-exit.json"] = data
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()

    def test_input_byte_bundle_not_mutated(self):
        original = copy.deepcopy((self.files, self.plan))
        self.verify()
        self.assertEqual(original, (self.files, self.plan))

    def test_no_producer_import_or_execution_dependency(self):
        import ast
        from pathlib import Path

        tree = ast.parse(Path(reader.__file__).read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {"hashlib", "json", "pathlib", "re"})

    def test_expected_plan_does_not_allow_type_alias_or_relative_paths(self):
        for key, value in (
            ("selected_cpu", True),
            ("timeout_seconds", 1.0),
            ("cwd", "relative"),
        ):
            with self.subTest(key=key):
                self.setUp()
                self.plan[key] = value
                self.files["plan.json"] = encoded(self.plan)
                self.row["plan_sha256"] = digest(self.files["plan.json"])
                self.seal()
                with self.assertRaises(reader.ReceiptError):
                    self.verify()


if __name__ == "__main__":
    unittest.main()
