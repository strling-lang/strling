import importlib.util
import json
import os
import stat
import warnings
import zipfile
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[3]
LSP_ROOT = ROOT / "tooling" / "lsp-server"
SPEC = importlib.util.spec_from_file_location(
    "strling_package_extension", LSP_ROOT / "package_extension.py"
)
assert SPEC is not None and SPEC.loader is not None
package_extension = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_extension)


def _contract() -> dict:
    return package_extension.load_contract()


def _target(contract: dict, identifier: str = "win32-x64") -> dict:
    return next(target for target in contract["targets"] if target["id"] == identifier)


def _fake_payload(root: Path, contract: dict, target: dict) -> Path:
    root.mkdir()
    required = package_extension._expanded_paths(contract, target)
    for relative in sorted(required - {"strling-package-manifest.json"}):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture:{relative}\n".encode())
        path.chmod(0o755 if relative.startswith("server/bin/") else 0o644)
    package_extension._write_manifest(root, contract, target)
    return root


def test_host_target_resolution_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract()
    monkeypatch.setattr(package_extension, "_host_identity", lambda: ("win32", "x64"))
    monkeypatch.setattr(
        package_extension, "_rust_host", lambda: "x86_64-pc-windows-msvc"
    )
    assert package_extension.resolve_target(contract, "auto")["id"] == "win32-x64"
    with pytest.raises(package_extension.PackageError, match="does not match host"):
        package_extension.resolve_target(contract, "linux-x64")
    with pytest.raises(
        package_extension.PackageError, match="no declared package target"
    ):
        package_extension.resolve_target(contract, "plan9-x64")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is privilege-dependent")
def test_tool_preserves_multicall_symlink_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    multicall = tmp_path / "rustup"
    multicall.write_text("fixture\n", encoding="utf-8")
    rustc = tmp_path / "rustc"
    rustc.symlink_to(multicall)
    monkeypatch.setattr(package_extension.shutil, "which", lambda _name: str(rustc))
    assert package_extension._tool("rustc", "RUSTC") == rustc.absolute()


def test_node_entry_command_accepts_native_and_javascript_bins(tmp_path: Path) -> None:
    node = tmp_path / "node"
    native = tmp_path / "esbuild"
    native.write_bytes(b"\x7fELFfixture")
    script = tmp_path / "vsce.js"
    script.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    assert package_extension._node_or_native_command(node, native) == [str(native)]
    assert package_extension._node_or_native_command(node, script) == [
        str(node),
        str(script),
    ]


def test_generated_manifest_validates_closed_schema_and_payload(tmp_path: Path) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    manifest = package_extension.validate_payload(payload, contract, target)
    schema = json.loads(
        (LSP_ROOT / "package_manifest.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(manifest)
    assert manifest["target"] == "win32-x64"
    assert len(manifest["entries"]) == 21


def test_payload_refuses_missing_unexpected_and_legacy_files(tmp_path: Path) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    (payload / "server" / "canonical_core.py").unlink()
    with pytest.raises(package_extension.PackageError, match="missing="):
        package_extension.validate_payload(payload, contract, target)

    payload = _fake_payload(tmp_path / "payload-two", contract, target)
    legacy = payload / "server" / "libs" / "STRling" / "parser.py"
    legacy.parent.mkdir()
    legacy.write_text("legacy", encoding="utf-8")
    with pytest.raises(package_extension.PackageError, match="unexpected="):
        package_extension.validate_payload(payload, contract, target)


def test_payload_refuses_content_and_manifest_mutation(tmp_path: Path) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    (payload / "server" / "bin" / "strling-kernel.exe").write_bytes(b"changed")
    with pytest.raises(package_extension.PackageError, match="entry hashes"):
        package_extension.validate_payload(payload, contract, target)

    payload = _fake_payload(tmp_path / "payload-two", contract, target)
    manifest_path = payload / "strling-package-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target"] = "linux-x64"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(package_extension.PackageError, match="target is incorrect"):
        package_extension.validate_payload(payload, contract, target)


def test_nondefault_existing_output_is_never_deleted(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "owned-by-caller"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(package_extension.PackageError, match="already exists"):
        package_extension._safe_output(output)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_certification_artifact_outputs_are_new_and_typed(tmp_path: Path) -> None:
    vsix = package_extension._new_artifact_path(
        tmp_path / "artifacts" / "package.vsix", suffix=".vsix"
    )
    assert vsix.parent.is_dir()
    vsix.write_bytes(b"owned")
    with pytest.raises(package_extension.PackageError, match="already exists"):
        package_extension._new_artifact_path(vsix, suffix=".vsix")
    with pytest.raises(package_extension.PackageError, match="must end"):
        package_extension._new_artifact_path(
            tmp_path / "artifacts" / "evidence.txt", suffix=".json"
        )


def test_vsix_entry_manifest_refuses_traversal_and_duplicates(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.vsix"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape", b"bad")
    with pytest.raises(package_extension.PackageError, match="unsafe or duplicate"):
        package_extension._zip_entries(traversal)

    duplicate = tmp_path / "duplicate.vsix"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("extension/package.json", b"one")
            archive.writestr("extension/package.json", b"two")
    with pytest.raises(package_extension.PackageError, match="unsafe or duplicate"):
        package_extension._zip_entries(duplicate)


def test_isolated_install_upgrade_uninstall_never_touches_user_state(
    tmp_path: Path,
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    vsix = tmp_path / "fixture.vsix"
    with zipfile.ZipFile(vsix, "w") as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, "extension/" + path.relative_to(payload).as_posix())
    lifecycle = package_extension._lifecycle_smoke(
        vsix, contract, target, tmp_path / "lifecycle-root"
    )
    assert lifecycle == {"install": True, "upgrade": True, "uninstall": True}
    assert not any((tmp_path / "lifecycle-root" / "extensions").iterdir())


def _read_only_target(monkeypatch: pytest.MonkeyPatch, target: dict) -> None:
    monkeypatch.setattr(package_extension, "resolve_target", lambda *_args: target)
    for name in (
        "assemble",
        "certify",
        "_build_binaries",
        "_bundle_client",
        "_package_vsix",
    ):
        monkeypatch.setattr(
            package_extension,
            name,
            lambda *_args, **_kwargs: pytest.fail(
                "integrity check attempted generation"
            ),
        )


def _rewrite_manifest(payload: Path, **changes: object) -> None:
    path = payload / package_extension.MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(changes)
    payload_material = {
        key: manifest[key]
        for key in (
            "contract_fingerprint",
            "extension_version",
            "target",
            "rust_host",
            "inputs",
            "entries",
        )
    }
    manifest["payload_fingerprint"] = package_extension._fingerprint(payload_material)
    material = dict(manifest)
    material.pop("manifest_fingerprint")
    manifest["manifest_fingerprint"] = package_extension._fingerprint(material)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_payload_integrity_check_is_fresh_read_only_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    _read_only_target(monkeypatch, target)
    before = package_extension._directory_bytes(payload)
    first = package_extension.check_payload(payload, "auto")
    assert first["status"] == "passed"
    assert first["mutated_candidate"] is False
    assert package_extension.check_payload(payload, "auto") == first
    assert package_extension._directory_bytes(payload) == before


@pytest.mark.parametrize(
    "field",
    [
        "inputs",
        "source_commit",
        "source_commit_timestamp",
        "extension_version",
        "rust_host",
    ],
)
def test_payload_integrity_rejects_rehashed_stale_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    replacements = {
        "inputs": {"stale": "sha256:" + "0" * 64},
        "source_commit": "0" * 40,
        "source_commit_timestamp": 0,
        "extension_version": "0.0.0",
        "rust_host": "x86_64-unknown-linux-gnu",
    }
    if field == "inputs":
        replacements[field] = {
            key: "sha256:" + "0" * 64 for key in package_extension._input_fingerprints()
        }
    _rewrite_manifest(payload, **{field: replacements[field]})
    _read_only_target(monkeypatch, target)
    before = package_extension._directory_bytes(payload)
    with pytest.raises(package_extension.PackageError, match="stale"):
        package_extension.check_payload(payload, "auto")
    assert package_extension._directory_bytes(payload) == before


def test_payload_integrity_rejects_malformed_and_missing_without_regeneration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    _read_only_target(monkeypatch, target)
    manifest = payload / package_extension.MANIFEST_NAME
    manifest.write_text("{}", encoding="utf-8")
    before = package_extension._directory_bytes(payload)
    with pytest.raises(package_extension.PackageError, match="malformed"):
        package_extension.check_payload(payload, "auto")
    assert package_extension._directory_bytes(payload) == before
    manifest.unlink()
    before = package_extension._directory_bytes(payload)
    with pytest.raises(package_extension.PackageError, match="missing="):
        package_extension.check_payload(payload, "auto")
    assert package_extension._directory_bytes(payload) == before


def test_payload_input_fingerprints_bind_all_registered_sources() -> None:
    inputs = package_extension._input_fingerprints()
    assert "file:core/internal/Cargo.toml" in inputs
    assert "file:core/cli/strling-kernel.rs" in inputs
    assert "file:tooling/lsp-server/client/extension.ts" in inputs
    assert "file:tooling/lsp-server/server/server.py" in inputs
    assert "file:tooling/lsp-server/package_extension.py" in inputs
    assert not any("__pycache__" in name for name in inputs)


def test_payload_integrity_detects_current_compiler_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    original = package_extension._file_fingerprint
    compiler = ROOT / "core" / "cli" / "strling-kernel.rs"
    monkeypatch.setattr(
        package_extension,
        "_file_fingerprint",
        lambda path: "sha256:" + "0" * 64 if path == compiler else original(path),
    )
    _read_only_target(monkeypatch, target)
    before = package_extension._directory_bytes(payload)
    with pytest.raises(
        package_extension.PackageError, match="input fingerprints are stale"
    ):
        package_extension.check_payload(payload, "auto")
    assert package_extension._directory_bytes(payload) == before


def test_payload_integrity_cli_never_invokes_package_producers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "payload", contract, target)
    _read_only_target(monkeypatch, target)
    before = package_extension._directory_bytes(payload)
    assert (
        package_extension.main(
            ["check-payload", "--target", "auto", "--output", str(payload)]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["mutated_candidate"] is False
    assert package_extension._directory_bytes(payload) == before


def _isolated_fixture_builder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contract: dict, target: dict
) -> list[Path]:
    _read_only_target(monkeypatch, target)
    monkeypatch.setattr(package_extension, "WORK_ROOT", tmp_path / "owned-build")
    calls: list[Path] = []

    def assemble_fixture(output: Path, requested: str) -> dict:
        assert requested == target["id"]
        calls.append(output)
        _fake_payload(output, contract, target)
        return {"output": str(output)}

    monkeypatch.setattr(package_extension, "assemble", assemble_fixture)
    return calls


def test_isolated_build_check_performs_build_without_candidate_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    original = package_extension._directory_state(payload)
    calls = _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)
    result = package_extension.build_check(payload, "auto")
    assert len(calls) == 1 and calls[0] != payload
    assert result["operation"] == "build-check"
    assert result["isolated_build"] is True
    assert result["authoritative"] is False
    assert result["mutated_candidate"] is False
    assert package_extension._directory_state(payload) == original
    assert not calls[0].exists()


@pytest.mark.parametrize("state", ["missing", "stale"])
def test_isolated_build_check_rejects_bad_prepared_state_before_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    if state == "missing":
        (payload / package_extension.MANIFEST_NAME).unlink()
    else:
        _rewrite_manifest(payload, source_commit="0" * 40)
    original = package_extension._directory_state(payload)
    calls = _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)
    with pytest.raises(package_extension.PackageError):
        package_extension.build_check(payload, "auto")
    assert calls == []
    assert package_extension._directory_state(payload) == original


def test_isolated_build_check_rejects_rebuilt_content_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    original = package_extension._directory_state(payload)
    _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)

    def changed_build(output: Path, requested: str) -> dict:
        _fake_payload(output, contract, target)
        (output / "package.json").write_bytes(b"different canonical-build fixture\n")
        package_extension._write_manifest(output, contract, target)
        return {"output": str(output)}

    monkeypatch.setattr(package_extension, "assemble", changed_build)
    with pytest.raises(package_extension.PackageError, match="isolated build differs"):
        package_extension.build_check(payload, "auto")
    assert package_extension._directory_state(payload) == original


def test_isolated_build_failure_preserves_prepared_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    original = package_extension._directory_state(payload)
    _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)

    def failed_build(*_args: object) -> dict:
        raise package_extension.PackageError("fixture compiler failure")

    monkeypatch.setattr(package_extension, "assemble", failed_build)
    with pytest.raises(
        package_extension.PackageError, match="fixture compiler failure"
    ):
        package_extension.build_check(payload, "auto")
    assert package_extension._directory_state(payload) == original


def test_isolated_build_detects_actual_prepared_mode_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)
    snapshot = package_extension._directory_state
    calls = 0

    def changed_actual_mode(root: Path) -> dict:
        nonlocal calls
        state = snapshot(root)
        if root == payload:
            calls += 1
            if calls > 1:
                data, mode = state["package.json"]
                state["package.json"] = (data, mode ^ stat.S_IWUSR)
        return state

    monkeypatch.setattr(package_extension, "_directory_state", changed_actual_mode)
    with pytest.raises(
        package_extension.PackageError, match="prepared payload changed"
    ):
        package_extension.build_check(payload, "auto")


def test_isolated_build_uses_portable_manifest_modes_across_filesystems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    original = package_extension._directory_state(payload)
    _isolated_fixture_builder(monkeypatch, tmp_path, contract, target)

    def different_actual_mode(output: Path, requested: str) -> dict:
        _fake_payload(output, contract, target)
        (output / "package.json").chmod(0o600)
        return {"output": str(output)}

    monkeypatch.setattr(package_extension, "assemble", different_actual_mode)
    assert package_extension.build_check(payload, "auto")["status"] == "passed"
    assert package_extension._directory_state(payload) == original


def test_payload_rejects_rehashed_portable_manifest_mode_mutation(
    tmp_path: Path,
) -> None:
    contract = _contract()
    target = _target(contract)
    payload = _fake_payload(tmp_path / "prepared", contract, target)
    manifest = package_extension._load_json(payload / package_extension.MANIFEST_NAME)
    entries = manifest["entries"]
    entries[0]["mode"] = "0755" if entries[0]["mode"] == "0644" else "0644"
    _rewrite_manifest(payload, entries=entries)
    with pytest.raises(package_extension.PackageError, match="entry hashes"):
        package_extension.validate_payload(payload, contract, target)


def test_isolated_build_cli_routes_to_read_only_build_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    payload = tmp_path / "prepared"
    calls: list[tuple[Path, str]] = []

    def fixture_check(output: Path, target: str) -> dict:
        calls.append((output, target))
        return {"operation": "build-check", "status": "passed"}

    monkeypatch.setattr(package_extension, "build_check", fixture_check)
    assert package_extension.main(["build-check", "--output", str(payload)]) == 0
    assert calls == [(payload, "auto")]
    assert json.loads(capsys.readouterr().out)["operation"] == "build-check"
