#!/usr/bin/env python3
"""Read-only verification of reviewed dependency inputs and lock identities.

The manually reviewed catalog is integrity authority, not generated output.
This command neither resolves dependencies nor reproduces lock bytes. A changed
lock or manifest (including a non-dependency manifest edit) requires explicit
review of the dependency change and catalog; candidate preparation cannot
refresh that authority. Native repository-security checks remain mandatory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Mapping, NoReturn, Sequence

from tooling.generated_artifacts import load_registry
from tooling.security import (
    SecurityConfigurationError,
    SecurityEngine,
    load_policy,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = "governance/dependency-lock-verification.json"
POLICY_PATH = "governance/security-policy.json"
REGISTRY_PATH = "governance/generated-artifacts.json"
REGISTRY_SCHEMA_PATH = "governance/schemas/generated-artifact-registry.schema.json"
POLICY_SCHEMA_PATH = "governance/schemas/security-policy.schema.json"
ARTIFACT_ID = "package-manager-lockfiles"
CONTRACT = "reviewed-identities-and-native-integrity-v1"
REFRESH_POLICY = "explicit-reviewed-dependency-change-only"
CATALOG_FIELDS = {
    "catalog_version",
    "artifact_id",
    "verification_contract",
    "refresh_policy",
    "security_policy_sha256",
    "manifest_hashes",
    "lock_hashes",
}


class LockVerificationError(ValueError):
    """Untrustworthy reviewed lock verification inputs."""


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LockVerificationError(f"duplicate JSON property {key!r}")
        result[key] = value
    return result


def load_catalog(path: Path, *, root: Path = ROOT) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_json_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LockVerificationError(
            f"cannot read reviewed lock catalog: {exc}"
        ) from exc
    return validate_catalog(value, root=root)


def _safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative
        or "\0" in relative
        or "\\" in relative
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in relative.split("/"))
        or any(character in relative for character in ("*", "?", "[", ":"))
    ):
        raise LockVerificationError(
            f"invalid repository-relative exact path {relative!r}"
        )
    repository = root.resolve()
    candidate = repository / relative
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise LockVerificationError(
            f"dependency input cannot be resolved: {relative}"
        ) from exc
    if (
        not resolved.is_relative_to(repository)
        or candidate.is_symlink()
        or resolved != candidate
    ):
        raise LockVerificationError(
            f"dependency input escapes repository or is an alias: {relative}"
        )
    return candidate


def validate_catalog(value: object, *, root: Path = ROOT) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != CATALOG_FIELDS:
        raise LockVerificationError(
            "reviewed lock catalog has an invalid closed field set"
        )
    if (
        type(value["catalog_version"]) is not int
        or value["catalog_version"] != 1
        or value["artifact_id"] != ARTIFACT_ID
        or value["verification_contract"] != CONTRACT
        or value["refresh_policy"] != REFRESH_POLICY
    ):
        raise LockVerificationError("reviewed lock catalog contract/version differs")
    if not isinstance(value["security_policy_sha256"], str) or not re.fullmatch(
        "[0-9a-f]{64}", value["security_policy_sha256"]
    ):
        raise LockVerificationError("reviewed security policy identity is malformed")
    for field in ("manifest_hashes", "lock_hashes"):
        records = value[field]
        if not isinstance(records, dict) or not records:
            raise LockVerificationError(
                f"{field} must be a nonempty exact identity map"
            )
        for relative, fingerprint in records.items():
            if (
                not isinstance(relative, str)
                or not isinstance(fingerprint, str)
                or not re.fullmatch("[0-9a-f]{64}", fingerprint)
            ):
                raise LockVerificationError(f"{field} contains a malformed identity")
            _safe_path(root, relative)
    if set(value["manifest_hashes"]) & set(value["lock_hashes"]):
        raise LockVerificationError(
            "reviewed lock output cannot also be its own manifest source"
        )
    if CATALOG_PATH in {*value["manifest_hashes"], *value["lock_hashes"]}:
        raise LockVerificationError(
            "reviewed catalog cannot certify itself as dependency input/output"
        )
    return value


def _prohibit_commands(_command: Sequence[str], _cwd: Path) -> NoReturn:
    raise LockVerificationError(
        "package-manager/subprocess execution is prohibited during lock verification"
    )


def _fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git_dependency_inventory(root: Path) -> list[str]:
    """Read tracked and nonignored untracked paths without refreshing the index."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise LockVerificationError(f"cannot census dependency files: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise LockVerificationError(f"cannot census dependency files: {message}")
    return sorted(
        {
            item.decode("utf-8", errors="strict")
            for item in completed.stdout.split(b"\0")
            if item
        }
    )


def verify_lockfiles(
    root: Path = ROOT,
    *,
    catalog: Mapping[str, object] | None = None,
    registry: Mapping[str, object] | None = None,
    policy: Mapping[str, object] | None = None,
    tracked_files: Sequence[str] | None = None,
) -> dict[str, object]:
    """Verify closed reviewed identities plus all existing native integrity checks.

    Dependency injection is only for isolated unit-test repositories. The CLI
    always loads the actual reviewed catalog, registry, security policy, and Git
    inventory; it exposes no write, refresh, acceptance, or bypass option.
    """
    findings: list[dict[str, str]] = []

    def fail(code: str, message: str, path: str | None = None) -> None:
        finding = {"code": code, "message": message}
        if path is not None:
            finding["path"] = path
        findings.append(finding)

    integrity: dict[str, object] | None = None
    manifest_count = lock_count = 0
    try:
        # Only file-backed authority participates here. Injected fixture dictionaries
        # are isolated test authority; no file is implicitly read or refreshed for them.
        authority_paths = (
            ([CATALOG_PATH] if catalog is None else [])
            + ([REGISTRY_PATH, REGISTRY_SCHEMA_PATH] if registry is None else [])
            + ([POLICY_PATH, POLICY_SCHEMA_PATH] if policy is None else [])
        )
        authority_before = {
            relative: _fingerprint(_safe_path(root, relative))
            for relative in authority_paths
        }
        reviewed = (
            validate_catalog(dict(catalog), root=root)
            if catalog is not None
            else load_catalog(root / CATALOG_PATH, root=root)
        )
        governed = (
            dict(registry)
            if registry is not None
            else load_registry(
                root / REGISTRY_PATH,
                root / REGISTRY_SCHEMA_PATH,
            )
        )
        security = (
            dict(policy)
            if policy is not None
            else load_policy(
                root / POLICY_PATH,
                root / POLICY_SCHEMA_PATH,
            )
        )
        families = governed.get("artifacts")
        if not isinstance(families, list):
            raise LockVerificationError("artifact registry inventory must be a list")
        family = [
            item
            for item in families
            if isinstance(item, dict) and item.get("id") == ARTIFACT_ID
        ]
        if len(family) != 1:
            raise LockVerificationError(
                "lockfile family must be registered exactly once"
            )
        registered = family[0].get("outputs")
        if not isinstance(registered, list) or any(
            not isinstance(path, str) for path in registered
        ):
            raise LockVerificationError("lockfile family output inventory is malformed")
        for relative in registered:
            _safe_path(root, relative)
        if len(registered) != len(set(registered)):
            raise LockVerificationError(
                "lockfile family contains duplicate output paths"
            )
        roots = security.get("dependency_roots")
        if not isinstance(roots, list) or any(
            not isinstance(item, dict) for item in roots
        ):
            raise LockVerificationError(
                "security dependency root inventory is malformed"
            )
        manifests: set[str] = set()
        locks: set[str] = set()
        for dependency in roots:
            declared_locks = dependency.get("locks")
            declared_manifests = dependency.get("manifests")
            if (
                not isinstance(declared_locks, list)
                or not isinstance(declared_manifests, list)
                or any(
                    not isinstance(path, str)
                    for path in [*declared_locks, *declared_manifests]
                )
            ):
                raise LockVerificationError(
                    "security dependency input inventory is malformed"
                )
            if declared_locks:
                locks.update(declared_locks)
                manifests.update(declared_manifests)
        if set(registered) != locks or set(reviewed["lock_hashes"]) != locks:
            raise LockVerificationError(
                "registry, security policy, and reviewed lock output inventories differ"
            )
        if set(reviewed["manifest_hashes"]) != manifests:
            raise LockVerificationError(
                "reviewed manifest inventory differs from all locked security roots"
            )
        manifest_count, lock_count = len(manifests), len(locks)
        before: dict[str, str | None] = {}
        expected = {
            **reviewed["manifest_hashes"],
            **reviewed["lock_hashes"],
            POLICY_PATH: reviewed["security_policy_sha256"],
        }
        for relative, fingerprint in sorted(expected.items()):
            path = _safe_path(root, relative)
            before[relative] = _fingerprint(path)
            if before[relative] is None:
                fail(
                    "LOCK-INPUT-MISSING",
                    "reviewed dependency input/output is missing",
                    relative,
                )
            elif before[relative] != fingerprint:
                fail(
                    "LOCK-IDENTITY-DRIFT",
                    "dependency input/output differs from its explicitly reviewed identity",
                    relative,
                )
        inventory = (
            list(tracked_files)
            if tracked_files is not None
            else git_dependency_inventory(root)
        )
        engine = SecurityEngine(
            root,
            security,
            tracked_files=inventory,
            command_runner=_prohibit_commands,
        )
        operation = engine.run_integrity()
        integrity = operation.as_dict()
        if operation.status != "passed":
            fail(
                "LOCK-NATIVE-INTEGRITY-FAILED",
                "native dependency integrity is not fully passed; no integrity waivers or unavailable results are accepted",
            )
        for relative, fingerprint in before.items():
            if _fingerprint(_safe_path(root, relative)) != fingerprint:
                fail(
                    "LOCK-INPUT-CHANGED-DURING-CHECK",
                    "dependency input/output changed during immutable verification",
                    relative,
                )
        if tracked_files is None and git_dependency_inventory(root) != inventory:
            fail(
                "LOCK-INVENTORY-CHANGED-DURING-CHECK",
                "tracked/nonignored dependency census changed during immutable verification",
            )
        for relative, fingerprint in authority_before.items():
            if _fingerprint(_safe_path(root, relative)) != fingerprint:
                fail(
                    "LOCK-AUTHORITY-CHANGED-DURING-CHECK",
                    "loaded catalog/registry/schema authority changed during immutable verification",
                    relative,
                )
    except (
        LockVerificationError,
        SecurityConfigurationError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OSError,
    ) as exc:
        fail("LOCK-VERIFICATION-CONFIGURATION", str(exc))
    return {
        "schema_version": "1.0.0",
        "operation": "generated_artifact_lockfile_integrity",
        "artifact": ARTIFACT_ID,
        "verification_contract": CONTRACT,
        "status": "failed" if findings else "passed",
        "network_mode": "offline",
        "read_only": True,
        "lock_reproduction_claimed": False,
        "automatic_refresh_permitted": False,
        "approved_manifest_count": manifest_count,
        "approved_lock_count": lock_count,
        "findings": sorted(
            findings,
            key=lambda item: (item["code"], item.get("path", ""), item["message"]),
        ),
        "native_dependency_integrity": integrity,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        required=True,
        help="verify only; never resolves or writes dependency state",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = verify_lockfiles()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Reviewed dependency lock integrity: {result['status']}")
        for finding in result["findings"]:
            print(f"{finding['code']}: {finding['message']}", file=sys.stderr)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
