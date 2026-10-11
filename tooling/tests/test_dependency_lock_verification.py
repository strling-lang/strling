from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from tooling import dependency_lock_verification as locks
from tooling.security import ENGINE_VERSION, SecurityEngine


class DependencyLockVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {
            "name": "fixture",
            "version": "1.0.0",
            "dependencies": {"example": "1.2.3"},
        }
        self.lock = {
            "name": "fixture",
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"example": "1.2.3"}},
                "node_modules/example": {
                    "version": "1.2.3",
                    "resolved": "https://example.invalid/example.tgz",
                    "integrity": "sha512-fixture",
                },
            },
        }
        self.policy = {
            "engine": {"version": ENGINE_VERSION},
            "dependency_roots": [
                {
                    "id": "fixture-npm",
                    "ecosystem": "npm",
                    "manifests": ["package.json"],
                    "locks": ["package-lock.json"],
                    "lock_policy": "required",
                    "integrity_mode": "npm_lock_v3",
                }
            ],
            "manifest_names": ["package.json"],
            "manifest_suffixes": [],
            "dependency_rules": {"require_npm_integrity": True},
            "security_waivers": [],
        }
        self.registry = {
            "artifacts": [{"id": locks.ARTIFACT_ID, "outputs": ["package-lock.json"]}]
        }
        self.write_json("package.json", self.manifest)
        self.write_json("package-lock.json", self.lock)
        self.write_json(locks.POLICY_PATH, self.policy)
        self.catalog = {
            "catalog_version": 1,
            "artifact_id": locks.ARTIFACT_ID,
            "verification_contract": locks.CONTRACT,
            "refresh_policy": locks.REFRESH_POLICY,
            "security_policy_sha256": self.sha(locks.POLICY_PATH),
            "manifest_hashes": {"package.json": self.sha("package.json")},
            "lock_hashes": {"package-lock.json": self.sha("package-lock.json")},
        }
        self.tracked = ["package.json", "package-lock.json"]

    def write_json(self, relative: str, value: object) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    def sha(self, relative: str) -> str:
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    def run_check(self) -> dict[str, object]:
        return locks.verify_lockfiles(
            self.root,
            catalog=self.catalog,
            registry=self.registry,
            policy=self.policy,
            tracked_files=self.tracked,
        )

    def assert_failed(self, code: str | None = None) -> dict[str, object]:
        result = self.run_check()
        self.assertEqual("failed", result["status"], result)
        if code is not None:
            self.assertIn(code, [item["code"] for item in result["findings"]])
        return result

    def test_fresh_reviewed_lock_and_native_integrity_pass(self) -> None:
        result = self.run_check()
        self.assertEqual("passed", result["status"], result)
        self.assertEqual(1, result["approved_manifest_count"])
        self.assertEqual(1, result["approved_lock_count"])
        self.assertEqual("passed", result["native_dependency_integrity"]["status"])
        self.assertFalse(result["lock_reproduction_claimed"])
        self.assertFalse(result["automatic_refresh_permitted"])
        self.assertTrue(result["read_only"])

    def test_identical_repeated_checks_are_deterministic_and_read_only(self) -> None:
        before = {
            path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        self.assertEqual(self.run_check(), self.run_check())
        after = {
            path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)

    def test_lock_identity_drift_fails_even_if_native_integrity_passes(self) -> None:
        self.lock["packages"]["node_modules/example"]["version"] = "1.2.4"
        self.write_json("package-lock.json", self.lock)
        result = self.assert_failed("LOCK-IDENTITY-DRIFT")
        self.assertEqual("passed", result["native_dependency_integrity"]["status"])

    def test_full_manifest_identity_drift_fails_even_without_graph_change(self) -> None:
        self.manifest["description"] = "only a documentation change"
        self.write_json("package.json", self.manifest)
        self.assert_failed("LOCK-IDENTITY-DRIFT")

    def test_dependency_policy_identity_drift_fails(self) -> None:
        self.write_json(locks.POLICY_PATH, {**self.policy, "unapproved": True})
        self.assert_failed("LOCK-IDENTITY-DRIFT")

    def test_missing_registered_lock_fails_without_regeneration(self) -> None:
        (self.root / "package-lock.json").unlink()
        self.assert_failed("LOCK-INPUT-MISSING")
        self.assertFalse((self.root / "package-lock.json").exists())

    def test_missing_manifest_fails(self) -> None:
        (self.root / "package.json").unlink()
        self.assert_failed("LOCK-INPUT-MISSING")

    def test_malformed_lock_is_rejected_even_if_catalog_is_reapproved(self) -> None:
        (self.root / "package-lock.json").write_text("{broken", encoding="utf-8")
        self.catalog["lock_hashes"]["package-lock.json"] = self.sha("package-lock.json")
        result = self.assert_failed("LOCK-NATIVE-INTEGRITY-FAILED")
        checks = result["native_dependency_integrity"]["checks"]
        self.assertTrue(
            any("SEC-DEP-LOCK-MALFORMED" in check["finding_codes"] for check in checks)
        )

    def test_manifest_lock_inconsistency_is_rejected_even_with_current_identities(
        self,
    ) -> None:
        self.lock["packages"][""]["dependencies"] = {"example": "9.9.9"}
        self.write_json("package-lock.json", self.lock)
        self.catalog["lock_hashes"]["package-lock.json"] = self.sha("package-lock.json")
        self.assert_failed("LOCK-NATIVE-INTEGRITY-FAILED")

    def test_unregistered_tracked_lock_is_rejected_by_native_inventory(self) -> None:
        self.write_json("extra/package-lock.json", self.lock)
        self.tracked.append("extra/package-lock.json")
        self.assert_failed("LOCK-NATIVE-INTEGRITY-FAILED")

    def test_unregistered_nonignored_untracked_lock_is_rejected(self) -> None:
        self.write_json("extra/package-lock.json", self.lock)
        inventory = [*self.tracked, "extra/package-lock.json"]
        with patch.object(locks, "git_dependency_inventory", return_value=inventory):
            result = locks.verify_lockfiles(
                self.root,
                catalog=self.catalog,
                registry=self.registry,
                policy=self.policy,
            )
        self.assertEqual("failed", result["status"])
        self.assertIn(
            "LOCK-NATIVE-INTEGRITY-FAILED",
            [item["code"] for item in result["findings"]],
        )

    def test_git_census_is_read_only_cached_plus_nonignored_untracked(self) -> None:
        output = CompletedProcess(
            [], 0, b"package.json\0new/Cargo.lock\0package.json\0", b""
        )
        with patch.object(locks.subprocess, "run", return_value=output) as command:
            self.assertEqual(
                ["new/Cargo.lock", "package.json"],
                locks.git_dependency_inventory(self.root),
            )
        command.assert_called_once_with(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=self.root,
            stdout=locks.subprocess.PIPE,
            stderr=locks.subprocess.PIPE,
            check=False,
        )

    def test_git_census_error_fails_closed(self) -> None:
        with patch.object(
            locks.subprocess,
            "run",
            return_value=CompletedProcess([], 128, b"", b"not a repository"),
        ):
            with self.assertRaisesRegex(
                locks.LockVerificationError, "not a repository"
            ):
                locks.git_dependency_inventory(self.root)

    def test_file_census_change_during_verification_fails(self) -> None:
        with patch.object(
            locks,
            "git_dependency_inventory",
            side_effect=[self.tracked, [*self.tracked, "extra.lock"]],
        ):
            result = locks.verify_lockfiles(
                self.root,
                catalog=self.catalog,
                registry=self.registry,
                policy=self.policy,
            )
        self.assertEqual("failed", result["status"])
        self.assertIn(
            "LOCK-INVENTORY-CHANGED-DURING-CHECK",
            [item["code"] for item in result["findings"]],
        )

    def test_registered_lock_missing_from_security_policy_is_rejected(self) -> None:
        self.registry["artifacts"][0]["outputs"].append("extra/package-lock.json")
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_policy_lock_missing_from_registry_is_rejected(self) -> None:
        self.registry["artifacts"][0]["outputs"] = []
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_catalog_cannot_omit_approved_lock_or_add_unknown_lock(self) -> None:
        self.catalog["lock_hashes"] = {"unknown.lock": "a" * 64}
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_catalog_cannot_omit_approved_manifest(self) -> None:
        self.catalog["manifest_hashes"] = {"unknown.json": "a" * 64}
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_catalog_cannot_use_lock_output_as_manifest_source(self) -> None:
        self.catalog["manifest_hashes"]["package-lock.json"] = self.sha(
            "package-lock.json"
        )
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_catalog_cannot_certify_itself(self) -> None:
        self.catalog["manifest_hashes"][locks.CATALOG_PATH] = "a" * 64
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_catalog_contract_and_fields_are_closed(self) -> None:
        for field, bad in (
            ("catalog_version", True),
            ("catalog_version", 2),
            ("artifact_id", "not-lockfiles"),
            ("verification_contract", "locks-are-their-own-source"),
            ("refresh_policy", "automatic"),
            ("security_policy_sha256", "not-a-hash"),
        ):
            with self.subTest(field=field, bad=bad):
                candidate = copy.deepcopy(self.catalog)
                candidate[field] = bad
                with self.assertRaises(locks.LockVerificationError):
                    locks.validate_catalog(candidate)
        candidate = copy.deepcopy(self.catalog)
        candidate["write_permission"] = True
        with self.assertRaises(locks.LockVerificationError):
            locks.validate_catalog(candidate)

    def test_catalog_paths_must_be_literal_confined_repository_paths(self) -> None:
        for relative in (
            "../Cargo.lock",
            "/Cargo.lock",
            "C:\\Cargo.lock",
            "locks/*.lock",
            "./Cargo.lock",
            "Cargo.lock:stream",
            "Cargo.lock\0stream",
        ):
            with self.subTest(relative=relative):
                self.catalog["lock_hashes"] = {relative: "a" * 64}
                self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_same_root_ancestor_alias_is_rejected_without_native_execution(
        self,
    ) -> None:
        native_resolve = Path.resolve
        manifest = self.root / "package.json"

        def resolve(path, *arguments, **keywords):
            if path == manifest:
                return self.root / "same-root-alias" / "package.json"
            return native_resolve(path, *arguments, **keywords)

        with (
            patch.object(Path, "resolve", resolve),
            patch.object(SecurityEngine, "run_integrity") as operation,
        ):
            self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")
        operation.assert_not_called()

    def test_real_same_root_ancestor_symlink_is_rejected(self) -> None:
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        (real / "package.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(locks.LockVerificationError, "alias"):
            locks._safe_path(self.root, "alias/package.json")

    def test_unresolvable_dependency_alias_fails_closed(self) -> None:
        native_resolve = Path.resolve
        manifest = self.root / "package.json"

        def resolve(path, *arguments, **keywords):
            if path == manifest:
                raise RuntimeError("symlink loop")
            return native_resolve(path, *arguments, **keywords)

        with patch.object(Path, "resolve", resolve):
            self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_duplicate_json_catalog_properties_are_rejected(self) -> None:
        path = self.root / "catalog.json"
        path.write_text(
            '{"catalog_version": 1, "catalog_version": 1}', encoding="utf-8"
        )
        with self.assertRaisesRegex(locks.LockVerificationError, "duplicate"):
            locks.load_catalog(path)

    def test_duplicate_registry_family_or_output_is_rejected(self) -> None:
        self.registry["artifacts"].append(copy.deepcopy(self.registry["artifacts"][0]))
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")
        self.registry["artifacts"].pop()
        self.registry["artifacts"][0]["outputs"].append("package-lock.json")
        self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_package_manager_and_network_execution_are_prohibited(self) -> None:
        with patch(
            "tooling.security.subprocess.run",
            side_effect=AssertionError("unexpected process"),
        ):
            self.assertEqual("passed", self.run_check()["status"])
        with self.assertRaisesRegex(locks.LockVerificationError, "prohibited"):
            locks._prohibit_commands(["npm", "install"], self.root)

    def test_unexpected_native_command_is_failed_not_accepted(self) -> None:
        def forbidden(engine: SecurityEngine) -> object:
            return engine._command_runner(["npm", "install"], engine.root)

        with patch.object(SecurityEngine, "run_integrity", forbidden):
            self.assert_failed("LOCK-VERIFICATION-CONFIGURATION")

    def test_identity_change_during_native_check_is_rejected(self) -> None:
        original = SecurityEngine.run_integrity

        def mutate(engine: SecurityEngine) -> object:
            result = original(engine)
            (engine.root / "package.json").write_text("{}", encoding="utf-8")
            return result

        with patch.object(SecurityEngine, "run_integrity", mutate):
            self.assert_failed("LOCK-INPUT-CHANGED-DURING-CHECK")

    def test_loaded_catalog_registry_and_schema_changes_are_rejected(self) -> None:
        self.write_json(locks.CATALOG_PATH, self.catalog)
        self.write_json(locks.REGISTRY_PATH, self.registry)
        self.write_json(locks.REGISTRY_SCHEMA_PATH, {})
        self.write_json(locks.POLICY_SCHEMA_PATH, {})
        original = SecurityEngine.run_integrity
        for relative in (
            locks.CATALOG_PATH,
            locks.REGISTRY_PATH,
            locks.REGISTRY_SCHEMA_PATH,
            locks.POLICY_PATH,
            locks.POLICY_SCHEMA_PATH,
        ):
            with self.subTest(relative=relative):
                authority = self.root / relative
                before = authority.read_bytes()

                def mutate(engine: SecurityEngine) -> object:
                    result = original(engine)
                    authority.write_bytes(before + b"\n")
                    return result

                with (
                    patch.object(locks, "load_catalog", return_value=self.catalog),
                    patch.object(locks, "load_registry", return_value=self.registry),
                    patch.object(locks, "load_policy", return_value=self.policy),
                    patch.object(SecurityEngine, "run_integrity", mutate),
                ):
                    result = locks.verify_lockfiles(
                        self.root, tracked_files=self.tracked
                    )
                self.assertEqual("failed", result["status"], result)
                self.assertIn(
                    {
                        "code": "LOCK-AUTHORITY-CHANGED-DURING-CHECK",
                        "message": "loaded catalog/registry/schema authority changed during immutable verification",
                        "path": relative,
                    },
                    result["findings"],
                )
                authority.write_bytes(before)

    def test_injected_fixture_authority_never_loads_control_files(self) -> None:
        with (
            patch.object(
                locks,
                "load_catalog",
                side_effect=AssertionError("unexpected catalog load"),
            ),
            patch.object(
                locks,
                "load_registry",
                side_effect=AssertionError("unexpected registry load"),
            ),
            patch.object(
                locks,
                "load_policy",
                side_effect=AssertionError("unexpected policy load"),
            ),
        ):
            self.assertEqual("passed", self.run_check()["status"])

    def test_cli_has_no_write_refresh_or_alternate_catalog_flags(self) -> None:
        for arguments in (
            ["--write"],
            ["--refresh"],
            ["--check", "--catalog", "other.json"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                locks.main(arguments)

    def test_repository_catalog_initialization_preserves_current_inputs(self) -> None:
        result = locks.verify_lockfiles()
        self.assertEqual("passed", result["status"], result)
        self.assertEqual(16, result["approved_lock_count"])
        self.assertEqual(20, result["approved_manifest_count"])
        self.assertEqual(
            30, sum(result["native_dependency_integrity"]["summary"].values())
        )


if __name__ == "__main__":
    unittest.main()
