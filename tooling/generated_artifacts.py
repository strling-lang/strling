#!/usr/bin/env python3
"""Generate or verify registered repository artifacts."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Callable, Mapping, Sequence, TypeVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

try:
    from tooling.profile_composition import resolve_profiles
    from tooling.security import KNOWN_LOCK_NAMES
except ModuleNotFoundError:
    from profile_composition import resolve_profiles
    from security import KNOWN_LOCK_NAMES


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / "governance/generated-artifacts.json"
DEFAULT_SCHEMA = ROOT / "governance/schemas/generated-artifact-registry.schema.json"
SNAPSHOT_READ_WORKERS = 8
SnapshotInput = TypeVar("SnapshotInput")


class RegistryError(ValueError):
    """Raised when the artifact registry cannot be trusted."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ArtifactResult:
    artifact: str
    status: str
    command: list[str] | None
    exit_code: int | None
    reason: str | None
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact": self.artifact,
            "status": self.status,
            "command": self.command,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


Executor = Callable[[Sequence[str], Path], CommandResult]
Snapshotter = Callable[[Path], Mapping[str, str]]


def closed_json_object(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for name, item in pairs:
        if name in value:
            raise RegistryError(f"duplicate JSON property: {name}")
        value[name] = item
    return value


def load_json(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=closed_json_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from exc


def validate_registry(registry: object, schema: object) -> dict[str, object]:
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(registry)
    except (SchemaError, ValidationError) as exc:
        raise RegistryError(f"malformed artifact registry: {exc.message}") from exc
    if not isinstance(registry, dict):
        raise RegistryError("artifact registry root must be an object")
    artifacts = registry["artifacts"]
    assert isinstance(artifacts, list)
    identifiers = [artifact["id"] for artifact in artifacts]
    if len(identifiers) != len(set(identifiers)):
        raise RegistryError("artifact identifiers must be unique")
    return registry


def load_registry(
    registry_path: Path = DEFAULT_REGISTRY,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, object]:
    return validate_registry(load_json(registry_path), load_json(schema_path))


def expand_paths(root: Path, patterns: Sequence[str]) -> set[Path]:
    matches: set[Path] = set()
    for pattern in patterns:
        absolute_pattern = str(root / pattern)
        matches.update(
            Path(os.path.abspath(match))
            for match in glob.glob(absolute_pattern, recursive=True)
        )
    return matches


def missing_patterns(root: Path, patterns: Sequence[str]) -> list[str]:
    return [pattern for pattern in patterns if not expand_paths(root, [pattern])]


def confined_registered_paths(
    root: Path, patterns: Sequence[str], description: str
) -> set[Path]:
    """Registered inputs and outputs are confined paths, never external aliases."""
    repository = root.resolve()
    for pattern in patterns:
        if (
            not isinstance(pattern, str)
            or not pattern
            or "\0" in pattern
            or "\\" in pattern
            or ":" in pattern
            or Path(pattern).is_absolute()
            or PureWindowsPath(pattern).drive
            or PureWindowsPath(pattern).root
            or ".." in pattern.split("/")
        ):
            raise RegistryError(f"{description} pattern must be repository-relative")
        # A missing leaf must not hide an existing parent link/alias from globbing.
        literal_parts = []
        for part in pattern.split("/"):
            if any(marker in part for marker in "*?["):
                break
            literal_parts.append(part)
        prefix = repository.joinpath(*literal_parts)
        try:
            resolved_prefix = prefix.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise RegistryError(
                f"{description} prefix cannot be resolved: {prefix}"
            ) from exc
        if (
            prefix.is_symlink()
            or not resolved_prefix.is_relative_to(repository)
            or resolved_prefix != prefix
        ):
            raise RegistryError(
                f"{description} prefix must be a regular repository path: {prefix}"
            )
    matches = expand_paths(repository, patterns)
    for path in matches:
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise RegistryError(
                f"{description} path cannot be resolved: {path}"
            ) from exc
        if (
            not path.is_relative_to(repository)
            or path.is_symlink()
            or resolved != path
            or not (path.is_file() or path.is_dir())
        ):
            raise RegistryError(
                f"{description} must be a regular repository path: {path}"
            )
    return matches


def validate_artifact_relationships(registry: Mapping[str, object], root: Path) -> None:
    artifacts = registry["artifacts"]
    assert isinstance(artifacts, list)
    toolchain: object | None = None
    for artifact in artifacts:
        assert isinstance(artifact, dict)
        sources = artifact["authoritative_sources"]
        inputs = artifact["generator_inputs"]
        outputs = artifact["outputs"]
        implementations = artifact["generator"]["implementation_paths"]
        assert isinstance(sources, list)
        assert isinstance(inputs, list)
        assert isinstance(outputs, list)
        assert isinstance(implementations, list)
        source_files = confined_registered_paths(
            root,
            [*sources, *inputs, *implementations],
            f"{artifact['id']} source/input/implementation",
        )
        output_files = confined_registered_paths(
            root, outputs, f"{artifact['id']} governed output"
        )
        overlap = sorted(
            str(path.relative_to(root)) for path in source_files & output_files
        )
        if overlap:
            raise RegistryError(
                f"{artifact['id']} uses generated output as its own input: "
                + ", ".join(overlap)
            )
        enforcement = artifact["enforcement"]
        profile_enforcement = artifact.get("profile_enforcement")
        if enforcement != "profile-enforced":
            if profile_enforcement is not None:
                raise RegistryError(
                    f"{artifact['id']} declares profile enforcement without "
                    "profile-enforced status"
                )
            continue
        assert isinstance(profile_enforcement, dict)
        if toolchain is None:
            toolchain = load_json(root / "toolchain.json")
        if not isinstance(toolchain, dict):
            raise RegistryError("toolchain.json root must be an object")
        policy = toolchain.get("policy")
        if not isinstance(policy, dict):
            raise RegistryError("toolchain.json is missing policy")
        operations = policy.get("operation_registry")
        profiles = resolve_profiles(policy)
        if not isinstance(operations, dict) or not isinstance(profiles, dict):
            raise RegistryError("toolchain operation/profile policy is malformed")
        operation_id = profile_enforcement["operation"]
        governed_profiles = profile_enforcement["profiles"]
        assert isinstance(operation_id, str)
        assert isinstance(governed_profiles, list)
        operation = operations.get(operation_id)
        if not isinstance(operation, dict):
            raise RegistryError(
                f"{artifact['id']} references unknown profile operation {operation_id}"
            )
        verification = artifact["verification"]
        assert isinstance(verification, dict)
        if operation.get("command") != verification["command"]:
            raise RegistryError(
                f"{artifact['id']} profile operation command differs from its "
                "registered verification command"
            )
        for profile_name, profile in profiles.items():
            if not isinstance(profile, dict):
                raise RegistryError(f"malformed profile {profile_name}")
            profile_operations = profile.get("operations")
            if not isinstance(profile_operations, list):
                raise RegistryError(f"profile {profile_name} has no operation list")
            count = sum(
                1
                for item in profile_operations
                if isinstance(item, dict) and item.get("operation") == operation_id
            )
            expected = 1 if profile_name in governed_profiles else 0
            if count != expected:
                raise RegistryError(
                    f"{artifact['id']} expects {operation_id} exactly {expected} "
                    f"time(s) in profile {profile_name}, found {count}"
                )


def host_command(command: Sequence[str], cwd: Path) -> list[str]:
    arguments = list(command)
    if os.name != "nt" or not arguments:
        return arguments
    if arguments[0] == "python3":
        arguments[0] = sys.executable
    elif arguments[:2] == ["./strling", "contracts"]:
        arguments = [
            sys.executable,
            str(cwd / "tooling/public_contracts.py"),
            *arguments[2:],
        ]
    return arguments


def execute_command(command: Sequence[str], cwd: Path) -> CommandResult:
    arguments = host_command(command, cwd)
    try:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_OPTIONAL_LOCKS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return CommandResult(127, stderr=str(exc))
    return CommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def confined_working_directory(root: Path, declared: object, artifact_id: str) -> Path:
    """Validate the registered directory immediately before every execution."""
    if not isinstance(declared, str) or not declared or "\0" in declared:
        raise RegistryError(f"{artifact_id} working directory must be a literal path")
    windows_path = PureWindowsPath(declared)
    if (
        Path(declared).is_absolute()
        or ":" in declared
        or windows_path.drive
        or windows_path.root
        or ".." in declared.replace("\\", "/").split("/")
    ):
        raise RegistryError(f"{artifact_id} working directory escapes repository")
    repository = root.resolve()
    directory = repository / declared
    try:
        resolved = directory.resolve()
    except (OSError, RuntimeError) as exc:
        raise RegistryError(
            f"{artifact_id} working directory cannot be resolved"
        ) from exc
    if not resolved.is_relative_to(repository) or resolved != directory:
        raise RegistryError(f"{artifact_id} working directory escapes repository")
    if not directory.is_dir():
        raise RegistryError(f"{artifact_id} missing working directory: {declared}")
    return directory


def _snapshot_entries(
    inputs: Sequence[SnapshotInput],
    reader: Callable[[SnapshotInput], tuple[str, str] | None],
    *,
    workers: int = SNAPSHOT_READ_WORKERS,
) -> dict[str, str]:
    """Read every census item with a fixed bound, retaining original path order."""
    if not 1 <= workers <= SNAPSHOT_READ_WORKERS:
        raise RegistryError("snapshot read concurrency must be between one and eight")
    iterator = iter(inputs)
    pending: deque[Future[tuple[str, str] | None]] = deque()
    snapshot: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in range(workers):
            try:
                item = next(iterator)
            except StopIteration:
                break
            pending.append(pool.submit(reader, item))
        while pending:
            try:
                result = pending.popleft().result()
            except OSError as error:
                raise RegistryError(
                    f"cannot read repository snapshot: {error}"
                ) from error
            if result is not None:
                relative, digest = result
                snapshot[relative] = digest
            try:
                item = next(iterator)
            except StopIteration:
                continue
            pending.append(pool.submit(reader, item))
    return snapshot


def _snapshot_tracked_path(root: Path, relative: str) -> tuple[str, str]:
    path = root / relative
    if path.is_symlink():
        payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
    elif path.is_file():
        payload = path.read_bytes()
    else:
        payload = b"<missing>"
    mode = stat.S_IMODE(path.lstat().st_mode) if path.exists() else 0
    digest = hashlib.sha256(str(mode).encode("ascii") + b"\0" + payload).hexdigest()
    return relative, digest


def _snapshot_governed_path(root: Path, path: Path) -> tuple[str, str] | None:
    if (
        not path.is_relative_to(root.resolve())
        or path.is_symlink()
        or path.resolve() != path
    ):
        raise RegistryError(
            f"governed output must be a regular repository file: {path}"
        )
    if path.is_dir():
        return None
    if not path.is_file():
        raise RegistryError(
            f"governed output must be a regular repository file: {path}"
        )
    relative = path.relative_to(root.resolve()).as_posix()
    mode = stat.S_IMODE(path.lstat().st_mode)
    digest = hashlib.sha256(
        str(mode).encode("ascii") + b"\0" + path.read_bytes()
    ).hexdigest()
    return relative, digest


def snapshot_repository(root: Path) -> Mapping[str, str]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RegistryError(
            "cannot snapshot repository state: "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    paths = [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in completed.stdout.split(b"\0")
        if raw
    ]
    return _snapshot_entries(
        paths, lambda relative: _snapshot_tracked_path(root, relative)
    )


def run_registry(
    registry: Mapping[str, object],
    root: Path,
    *,
    check: bool,
    selected: str | None = None,
    complete: bool = False,
    fail_fast: bool | None = None,
    executor: Executor = execute_command,
    snapshotter: Snapshotter = snapshot_repository,
) -> list[ArtifactResult]:
    validate_artifact_relationships(registry, root)
    if complete and (not check or selected is not None):
        raise RegistryError(
            "complete inventory is check-only and cannot select a family"
        )
    initial_state = integrity_snapshot(registry, root, snapshotter) if check else {}
    if fail_fast is None:
        fail_fast = complete
    artifacts = registry["artifacts"]
    assert isinstance(artifacts, list)
    known_ids = {artifact["id"] for artifact in artifacts}
    if selected is not None and selected not in known_ids:
        raise RegistryError(f"unknown artifact '{selected}'")

    results: list[ArtifactResult] = []
    if complete:
        validate_inventory(registry, root, initial_state)
        for artifact in artifacts:
            phase = artifact["verification"].get("phase", "static")
            if phase not in {"static", "build-backed"}:
                raise RegistryError(f"{artifact['id']} has unknown verification phase")
        # Stable partition preserves each phase's registry order and all exact checks.
        artifacts = sorted(
            artifacts,
            key=lambda item: (
                item["verification"].get("phase", "static") == "build-backed"
            ),
        )
    for artifact in artifacts:
        assert isinstance(artifact, dict)
        artifact_id = str(artifact["id"])
        if selected is not None and artifact_id != selected:
            continue
        enforcement = artifact["enforcement"]
        if enforcement == "profile-enforced" and not complete:
            profile_enforcement = artifact["profile_enforcement"]
            assert isinstance(profile_enforcement, dict)
            profiles = profile_enforcement["profiles"]
            assert isinstance(profiles, list)
            results.append(
                ArtifactResult(
                    artifact_id,
                    "profile-enforced",
                    None,
                    None,
                    "verification is delegated exactly to profiles: "
                    + ", ".join(str(profile) for profile in profiles),
                )
            )
            continue
        if enforcement not in {"enforced", "verification-only", "profile-enforced"}:
            if complete:
                results.append(
                    ArtifactResult(
                        artifact_id,
                        "failed",
                        None,
                        None,
                        "complete inventory cannot delegate unverified coverage",
                    )
                )
                if fail_fast:
                    break
                continue
            transition = artifact.get("transition")
            assert isinstance(transition, dict)
            results.append(
                ArtifactResult(
                    artifact_id,
                    str(enforcement),
                    None,
                    None,
                    str(transition["rationale"]),
                )
            )
            continue

        generator = artifact["generator"]
        verification = artifact["verification"]
        assert isinstance(generator, dict)
        assert isinstance(verification, dict)
        sources = artifact["authoritative_sources"]
        inputs = artifact["generator_inputs"]
        outputs = artifact["outputs"]
        implementations = generator["implementation_paths"]
        assert isinstance(sources, list)
        assert isinstance(inputs, list)
        assert isinstance(outputs, list)
        assert isinstance(implementations, list)

        missing_sources = missing_patterns(root, [*sources, *inputs, *implementations])
        if missing_sources:
            results.append(
                ArtifactResult(
                    artifact_id,
                    "failed",
                    None,
                    None,
                    "missing authoritative source or generator input: "
                    + ", ".join(missing_sources),
                )
            )
            if fail_fast:
                break
            continue
        missing_outputs = missing_patterns(root, outputs)
        if check and missing_outputs:
            results.append(
                ArtifactResult(
                    artifact_id,
                    "failed",
                    None,
                    None,
                    "missing expected output: " + ", ".join(missing_outputs),
                )
            )
            if fail_fast:
                break
            continue

        command_value = (
            verification.get("integrity_command", verification["command"])
            if check and complete
            else verification["command"]
            if check
            else generator["command"]
        )
        if command_value is None:
            results.append(
                ArtifactResult(
                    artifact_id,
                    "failed",
                    None,
                    None,
                    "no canonical generator; specific governed refresh required",
                )
            )
            if fail_fast:
                break
            continue
        assert isinstance(command_value, list)
        command = [str(part) for part in command_value]
        working_directory = confined_working_directory(
            root, generator["working_directory"], artifact_id
        )
        execution = executor(command, working_directory)
        reason = None
        status = "passed"
        if execution.returncode != 0:
            status = "failed"
            action = "verification" if check else "generation"
            reason = f"{action} command exited with status {execution.returncode}"
        elif missing_patterns(root, outputs):
            status = "failed"
            reason = "generator completed without producing every expected output"
        results.append(
            ArtifactResult(
                artifact_id,
                status,
                command,
                execution.returncode,
                reason,
                execution.stdout,
                execution.stderr,
            )
        )
        if check and integrity_snapshot(registry, root, snapshotter) != initial_state:
            results.append(
                ArtifactResult(
                    "repository-state",
                    "failed",
                    None,
                    None,
                    "check mode modified repository files: "
                    + ", ".join(
                        changed_paths(
                            initial_state,
                            integrity_snapshot(registry, root, snapshotter),
                        )
                    ),
                )
            )
            return results
        if fail_fast and status == "failed":
            break

    if check:
        final_state = integrity_snapshot(registry, root, snapshotter)
        if final_state != initial_state:
            changed = sorted(
                path
                for path in set(initial_state) | set(final_state)
                if initial_state.get(path) != final_state.get(path)
            )
            results.append(
                ArtifactResult(
                    "repository-state",
                    "failed",
                    None,
                    None,
                    "check mode modified repository files: " + ", ".join(changed),
                )
            )
    return results


def matches_path(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def git_authority_digest(path: Path, *, allow_directory: bool = False) -> str:
    """Preserve Git authority node identity and mode, not only identical bytes."""
    try:
        metadata = path.lstat()
        if path.is_symlink() or path.resolve() != path:
            raise RegistryError(f"Git authority must be a regular node: {path}")
        if stat.S_ISREG(metadata.st_mode):
            payload = path.read_bytes()
        elif allow_directory and stat.S_ISDIR(metadata.st_mode):
            payload = b"<directory>"
        else:
            raise RegistryError(f"Git authority must be a regular node: {path}")
    except (OSError, RuntimeError) as exc:
        raise RegistryError(f"cannot inspect Git authority node: {path}") from exc
    identity = f"{metadata.st_mode}:{metadata.st_dev}:{metadata.st_ino}".encode("ascii")
    return hashlib.sha256(identity + b"\0" + payload).hexdigest()


def git_reference_snapshot(directory: Path, prefix: str) -> dict[str, str]:
    """Protect repository refs, excluding only external UI turn-diff receipts.

    These two application-owned namespaces are not source, release or verifier
    authority. Keep node validation even there; symbolic refs elsewhere must not
    alias them. HEAD resolution, index, packed refs and configuration remain
    independently protected by integrity_snapshot. Only confirmed disappearance
    of an already-excluded UI node is harmless; other read failures stay fatal.
    """
    bookkeeping = (
        "refs/codex/turn-diffs/captures",
        "refs/codex/turn-diffs/checkpoints",
    )
    containers = {"refs/codex", "refs/codex/turn-diffs"}
    state = {}
    head = directory / "HEAD"
    if head.is_file():
        git_authority_digest(head)
        payload = head.read_bytes()
        if payload.startswith(b"ref:"):
            target = payload[4:].strip().decode("ascii", errors="replace").casefold()
            if any(
                target == namespace or target.startswith(namespace + "/")
                for namespace in bookkeeping
            ):
                raise RegistryError("Git authority cannot alias UI bookkeeping refs")
    for path in (directory / "refs").rglob("*"):
        relative = path.relative_to(directory).as_posix()
        external = any(
            relative == namespace or relative.startswith(namespace + "/")
            for namespace in bookkeeping
        )
        try:
            digest = git_authority_digest(path, allow_directory=True)
            if path.is_file():
                payload = path.read_bytes()
                if payload.startswith(b"ref:"):
                    target = (
                        payload[4:].strip().decode("ascii", errors="replace").casefold()
                    )
                    if any(
                        target == namespace or target.startswith(namespace + "/")
                        for namespace in bookkeeping
                    ):
                        raise RegistryError(
                            "Git authority cannot alias UI bookkeeping refs"
                        )
        except (RegistryError, OSError) as exc:
            cause = exc.__cause__ if isinstance(exc, RegistryError) else exc
            if not external or not isinstance(cause, FileNotFoundError):
                raise
            # Do not hide a replacement, alias, permission error, or real ref.
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            raise
        if external or (relative in containers and path.is_dir()):
            continue
        state[f"{prefix}/{relative}"] = digest
    return state


def integrity_snapshot(
    registry: Mapping[str, object], root: Path, snapshotter: Snapshotter
) -> dict[str, str]:
    """Include ignored governed outputs and Git authority, not build caches."""
    state = dict(snapshotter(root))
    patterns = [
        pattern for item in registry["artifacts"] for pattern in item["outputs"]
    ]
    inventory = registry.get("inventory", {})
    # Unanchored census globs apply to tracked/nonignored candidates only. Never
    # descend into ignored retained verifier/Release copies or dependency caches.
    patterns.extend(
        pattern
        for pattern in inventory.get("governed_output_patterns", [])
        if not pattern.startswith("**/")
    )
    state.update(
        _snapshot_entries(
            sorted(expand_paths(root, patterns)),
            lambda path: _snapshot_governed_path(root, path),
        )
    )
    # Detect staging, commits, reference moves and worktree identity changes.
    if (root / ".git").exists():
        completed = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise RegistryError("cannot inspect Git authority")
        git_dir = (root / completed.stdout.strip()).resolve()
        authority = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if authority.returncode:
            raise RegistryError("cannot inspect committed/common Git authority")
        common_dir = (root / authority.stdout.strip()).resolve()
        commit = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode:
            # Preparation also supports an unborn fixture/initial checkout;
            # authoritative profile source validation separately requires SHA.
            symbolic = subprocess.run(
                ["git", "symbolic-ref", "--quiet", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if symbolic.returncode:
                raise RegistryError("cannot inspect committed Git authority")
            state["@git/commit"] = "unborn:" + symbolic.stdout.strip()
        else:
            state["@git/commit"] = commit.stdout.strip()
        state["@git/entry"] = git_authority_digest(root / ".git", allow_directory=True)
        state["@git/directory"] = git_authority_digest(git_dir, allow_directory=True)
        if (root / ".git").is_file():
            state["@git/indirection"] = git_authority_digest(root / ".git")
        for name in ("HEAD", "index", "packed-refs", "config", "refs"):
            path = git_dir / name
            if path.exists() or path.is_symlink():
                state[f"@git/{name}"] = git_authority_digest(
                    path, allow_directory=name == "refs"
                )
        state.update(git_reference_snapshot(git_dir, "@git"))
        if common_dir != git_dir:
            state["@git/common/directory"] = git_authority_digest(
                common_dir, allow_directory=True
            )
            for name in ("packed-refs", "config", "refs"):
                path = common_dir / name
                if path.exists() or path.is_symlink():
                    state[f"@git/common/{name}"] = git_authority_digest(
                        path, allow_directory=name == "refs"
                    )
            state.update(git_reference_snapshot(common_dir, "@git/common"))
    return state


def validate_inventory(
    registry: Mapping[str, object], root: Path, state: Mapping[str, str]
) -> None:
    """Fail closed against a separately declared governed output census."""
    inventory = registry.get("inventory")
    if not isinstance(inventory, dict):
        raise RegistryError("complete inventory requires governed output census")
    identifiers = {item["id"] for item in registry["artifacts"]}
    if identifiers != set(inventory["required_families"]):
        raise RegistryError(
            "registered families differ from complete governed inventory"
        )
    outputs = [pattern for item in registry["artifacts"] for pattern in item["outputs"]]
    for relative in state:
        if matches_path(
            relative, inventory["governed_output_patterns"]
        ) and not matches_path(relative, outputs):
            raise RegistryError(f"unregistered governed derived output: {relative}")
    # Independently declared hygiene-derived outputs cannot disappear with a family.
    hygiene_path = root / "governance/repository-hygiene.json"
    if hygiene_path.is_file():
        hygiene = load_json(hygiene_path)
        for group in hygiene.get("generated_paths", []):
            patterns = group["paths"]
            if (
                group.get("owner")
                == "Explicit non-normative migration-history fixture set"
            ):
                # Hygiene authority marks these as retained, non-current archaeology.
                if group.get("text_normalization") != "serializer_owned":
                    raise RegistryError("historical fixture classification changed")
                continue
            for relative in state:
                if matches_path(relative, patterns) and not matches_path(
                    relative, outputs
                ):
                    raise RegistryError(
                        f"unregistered hygiene-derived output: {relative}"
                    )


PROTECTED_FAMILIES = frozenset(
    {
        "package-manager-lockfiles",
        "dependency-license-evidence",
        "performance-resource-source-identities",
    }
)
PROTECTED_OUTPUTS = (
    ".git",
    ".git/**",
    "toolchain.json",
    ".github/workflows",
    ".github/workflows/**",
    "governance/generated-artifacts.json",
    "governance/schemas/generated-artifact-registry.schema.json",
    "tests/certification/performance-resource/**",
    "tests/certification/hardened-core/**",
    "tests/conformance/evidence/**",
    "tests/conformance/adversarial/**",
    "tests/adapters/**/legacy-baseline.json",
    "tests/architecture/**/evidence.*",
    "governance/contracts/snapshots/**",
    "governance/dependency-license-evidence.json",
    "governance/dependency-lock-verification.json",
    "governance/security-policy.json",
    "governance/local-certification-trust.json",
    "governance/release-policy.json",
    "docs/migration/**",
) + tuple(
    pattern for name in sorted(KNOWN_LOCK_NAMES) for pattern in (name, f"**/{name}")
)


def protected_control_patterns(root: Path) -> tuple[str, ...]:
    """Resolve current/common Git authority without granting outside-output rights."""
    patterns = list(PROTECTED_OUTPUTS)
    repository = root.resolve()
    if (repository / ".git").exists():
        for option in ("--git-dir", "--git-common-dir"):
            completed = subprocess.run(
                ["git", "rev-parse", option],
                cwd=repository,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode or not completed.stdout.strip():
                raise RegistryError("cannot inspect protected Git control paths")
            directory = (repository / completed.stdout.strip()).resolve()
            if directory.is_relative_to(repository):
                relative = directory.relative_to(repository).as_posix()
                if relative == ".":
                    raise RegistryError(
                        "Git control directory cannot occupy the checkout root"
                    )
                patterns.extend((relative, relative + "/**"))
    return tuple(dict.fromkeys(patterns))


def protected_output_declaration(output: str, patterns: Sequence[str]) -> bool:
    """Broad output globs cannot preauthorize writing a protected control subtree."""
    if matches_path(output, patterns) or any(
        matches_path(pattern, [output]) for pattern in patterns
    ):
        return True
    if not any(marker in output for marker in "*?["):
        return False

    def literal_prefix(pattern: str) -> str:
        parts = []
        for part in pattern.split("/"):
            if any(marker in part for marker in "*?["):
                break
            parts.append(part)
        return "/".join(parts)

    declared = literal_prefix(output)
    for pattern in patterns:
        protected = literal_prefix(pattern)
        if (
            not declared
            or declared == protected
            or protected.startswith(declared + "/")
            or declared.startswith(protected + "/")
        ):
            return True
    return False


def preparation_allowed(
    artifact: Mapping[str, object],
    *,
    protected_patterns: Sequence[str] = PROTECTED_OUTPUTS,
) -> bool:
    """Authority is deny-by-default; registry permission alone cannot waive it."""
    return (
        artifact["id"] not in PROTECTED_FAMILIES
        and not any(
            protected_output_declaration(output, protected_patterns)
            for output in artifact["outputs"]
        )
        and artifact["authority"]
        in {"operational-projection", "non-normative-projection"}
        and artifact["determinism"] == "verified"
        and artifact["enforcement"] in {"enforced", "profile-enforced"}
        and artifact.get("preparation", {}).get("automatic_regeneration") == "canonical"
        and bool(artifact.get("preparation", {}).get("direct_dependents"))
        and isinstance(artifact["generator"]["command"], list)
    )


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )


def prepare_registry(
    registry: Mapping[str, object],
    root: Path,
    *,
    executor: Executor = execute_command,
    snapshotter: Snapshotter = snapshot_repository,
) -> dict[str, object]:
    """Repair ordinary projections before freeze; never create certification authority.

    Canonical commands are constrained to their declared outputs. Any unexpected
    mutation stops preparation and is reported, never erased or silently accepted.
    Existing dirty files outside selected outputs are preserved. Protected stale
    families block the whole preparation before any generator is executed.
    """
    protected_patterns = protected_control_patterns(root)
    initial = run_registry(
        registry,
        root,
        check=True,
        complete=True,
        executor=executor,
        snapshotter=snapshotter,
        fail_fast=False,
    )
    families = {item["id"]: item for item in registry["artifacts"]}
    failed = [item for item in initial if item.status == "failed"]
    blocked = [
        item.artifact
        for item in failed
        if item.artifact not in families
        or not preparation_allowed(
            families[item.artifact], protected_patterns=protected_patterns
        )
        or (
            item.command is None
            and not (item.reason or "").startswith("missing expected output")
        )
    ]
    for item in failed:
        if item.artifact in families:
            for path in expand_paths(root, families[item.artifact]["outputs"]):
                if matches_path(
                    path.relative_to(root.resolve()).as_posix(), protected_patterns
                ):
                    blocked.append(item.artifact)
                    break
    blocked = sorted(set(blocked))
    report: dict[str, object] = {
        "operation": "generated-artifact-preparation",
        "authoritative": False,
        "candidate_frozen": False,
        "status": "blocked" if blocked else "passed",
        "initial_check": [item.as_dict() for item in initial],
        "blocked_families": blocked,
        "repairs": [],
        "final_check": [],
    }
    if blocked:
        return report
    for result in failed:
        family = families[result.artifact]
        before = integrity_snapshot(registry, root, snapshotter)
        command = family["generator"]["command"]
        cwd = confined_working_directory(
            root, family["generator"]["working_directory"], result.artifact
        )
        execution = executor(command, cwd)
        after = integrity_snapshot(registry, root, snapshotter)
        delta = changed_paths(before, after)
        unexpected = [
            path
            for path in delta
            if path.startswith("@git/")
            or matches_path(path, protected_patterns)
            or not matches_path(path, family["outputs"])
        ]
        repair = {
            "artifact": result.artifact,
            "command": command,
            "exit_code": execution.returncode,
            "changed_paths": delta,
            "unexpected_paths": unexpected,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "idempotent": False,
            "direct_dependents": [],
        }
        report["repairs"].append(repair)
        if execution.returncode or unexpected:
            report["status"] = "failed"
            return report
        # A second canonical generation must leave every source/output/identity byte unchanged.
        cwd = confined_working_directory(
            root, family["generator"]["working_directory"], result.artifact
        )
        repetition = executor(command, cwd)
        if (
            repetition.returncode
            or integrity_snapshot(registry, root, snapshotter) != after
        ):
            repair["idempotence_failure"] = True
            report["status"] = "failed"
            return report
        repair["idempotent"] = True
    # Full deterministic recheck comes before any dependent operation.
    final = run_registry(
        registry,
        root,
        check=True,
        complete=True,
        executor=executor,
        snapshotter=snapshotter,
    )
    report["final_check"] = [item.as_dict() for item in final]
    if any(item.status != "passed" for item in final):
        report["status"] = "failed"
        return report
    for repair in report["repairs"]:
        family = families[repair["artifact"]]
        for command in family["preparation"]["direct_dependents"]:
            before = integrity_snapshot(registry, root, snapshotter)
            cwd = confined_working_directory(root, ".", str(repair["artifact"]))
            execution = executor(command, cwd)
            mutation = changed_paths(
                before, integrity_snapshot(registry, root, snapshotter)
            )
            repair["direct_dependents"].append(
                {
                    "command": command,
                    "exit_code": execution.returncode,
                    "unexpected_paths": mutation,
                    "stdout": execution.stdout,
                    "stderr": execution.stderr,
                }
            )
            if execution.returncode or mutation:
                report["status"] = "failed"
                return report
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or verify registered artifacts."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--artifact")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def render_human(results: Sequence[ArtifactResult]) -> None:
    for result in results:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(
                result.stderr,
                end="" if result.stderr.endswith("\n") else "\n",
                file=sys.stderr,
            )
        suffix = f" ({result.reason})" if result.reason else ""
        print(f"[{result.status}] {result.artifact}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        registry = load_registry(args.registry.resolve(), args.schema.resolve())
        if args.prepare:
            if args.check or args.artifact or args.complete:
                raise RegistryError(
                    "preparation is complete-inventory only; not --check, --complete or --artifact"
                )
            report = prepare_registry(registry, ROOT)
            print(
                json.dumps(
                    report, sort_keys=True, indent=None if args.json_output else 2
                )
            )
            return 0 if report["status"] == "passed" else 1
        if not args.check:
            raise RegistryError(
                "use --prepare for guarded ordinary regeneration; governed refreshes use their specific native procedures"
            )
        results = run_registry(
            registry,
            ROOT,
            check=args.check,
            selected=args.artifact,
            complete=args.complete,
        )
    except (RegistryError, OSError) as exc:
        if args.json_output and args.prepare:
            print(
                json.dumps(
                    {
                        "operation": "generated-artifact-preparation",
                        "status": "failed",
                        "exit_code": 2,
                        "authoritative": False,
                        "candidate_frozen": False,
                        "reason": str(exc),
                        "initial_check": [],
                        "blocked_families": [],
                        "repairs": [],
                        "final_check": [],
                    },
                    sort_keys=True,
                )
            )
        elif args.json_output and args.complete:
            print(
                json.dumps(
                    {
                        "operation_id": "certification.generated-artifact-integrity",
                        "schema_version": "certification-result-v1",
                        "operation": "generate",
                        "mode": "check",
                        "status": "failed",
                        "exit_code": 1,
                        "authoritative": False,
                        "results": [],
                        "checks": [
                            {
                                "id": "certification.generated-artifact-integrity.inventory",
                                "status": "failed",
                                "details": {"reason": str(exc)},
                            }
                        ],
                        "reason": str(exc),
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2 if args.prepare else 1 if args.complete else 2

    failed = any(result.status == "failed" for result in results)
    exit_code = 1 if failed else 0
    operation = "check" if args.check else "write"
    if args.json_output:
        print(
            json.dumps(
                {
                    "operation": "generate",
                    **(
                        {
                            "operation_id": "certification.generated-artifact-integrity",
                            "schema_version": "certification-result-v1",
                            "authoritative": False,
                            "checks": [
                                {
                                    "id": "certification.generated-artifact-integrity."
                                    + result.artifact,
                                    "status": result.status,
                                    "details": {
                                        "command": result.command,
                                        "reason": result.reason,
                                    },
                                }
                                for result in results
                            ],
                        }
                        if args.complete
                        else {}
                    ),
                    "mode": operation,
                    "status": "failed" if failed else "passed",
                    "exit_code": exit_code,
                    "results": [result.as_dict() for result in results],
                },
                sort_keys=True,
            )
        )
    else:
        render_human(results)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
