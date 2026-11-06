import os

import pytest
import tomllib
from tooling.native_release_build import stage_workspace


def test_native_workspace_preserves_exact_sources_and_nonworkspace_manifest_fields(
    monkeypatch, tmp_path
):
    source = tmp_path / "source"
    inputs = {
        "bindings/interop/Cargo.toml": '[package]\nname="strling-interop"\nversion="0.1.0"\n[workspace]\nmembers=[".","fuzz"]\n[dependencies]\nserde="1"\n',
        "core/internal/Cargo.toml": '[package]\nname="strling-kernel"\nversion="0.1.0"\n[workspace]\n[lib]\npath="../src/lib.rs"\n',
        "bindings/interop/Cargo.lock": "# exact governed dependency graph\n",
        "core/src/lib.rs": "// exact canonical source bytes\n",
    }
    for relative, data in inputs.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8", newline="\n")
    monkeypatch.setattr("tooling.native_release_build.SOURCE_PATHS", tuple(inputs))
    for label in ["first", "second"]:
        output = tmp_path / label
        stage_workspace(source, output)
        for relative in inputs:
            assert (source / relative).read_text(encoding="utf-8") == inputs[relative]
            if relative.endswith("Cargo.toml"):
                original = tomllib.loads(inputs[relative])
                original.pop("workspace")
                assert tomllib.loads((output / relative).read_text()) == original
            else:
                assert (output / relative).read_bytes() == (
                    source / relative
                ).read_bytes()
    assert (tmp_path / "first/Cargo.lock").read_bytes() == (
        source / "bindings/interop/Cargo.lock"
    ).read_bytes()
    with pytest.raises(ValueError, match="must be new"):
        stage_workspace(source, tmp_path / "first")


def test_native_workspace_rejects_missing_workspace_table(monkeypatch, tmp_path):
    source = tmp_path / "source"
    paths = (
        "bindings/interop/Cargo.toml",
        "bindings/interop/Cargo.lock",
        "core/internal/Cargo.toml",
    )
    for relative in paths:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[package]\nname="fixture"\n', encoding="utf-8")
    monkeypatch.setattr("tooling.native_release_build.SOURCE_PATHS", paths)
    with pytest.raises(ValueError, match="one independent workspace"):
        stage_workspace(source, tmp_path / "output")


def test_repository_wrapper_has_checkout_independent_toolchain_identity(
    monkeypatch, tmp_path
):
    import subprocess
    from tooling import release_supply_chain as supply

    monkeypatch.setattr(supply, "_validate_toolchain_version", lambda *a, **k: None)
    monkeypatch.setattr(
        supply.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Gradle 8.5\n"),
    )
    name = "gradlew.bat" if os.name == "nt" else "gradlew"
    rows = []
    for label in ["first", "second"]:
        root = tmp_path / label
        wrapper = root / "bindings/kotlin" / name
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes(b"governed wrapper fixture")
        rows.append(
            supply._probe_toolchain(
                root,
                artifact_id="release:kotlin",
                toolchain_id="gradle",
                policy_sha256="a" * 64,
            )
        )
    assert rows[0] == rows[1]
    assert rows[0]["status"] == "passed"
    assert rows[0]["executable"] == "repository:bindings/kotlin/" + name


def test_windows_cmake_uses_the_authenticated_installed_toolset(monkeypatch, tmp_path):
    from tooling.release_packaging import windows_cmake_toolset
    from tooling.release_supply_chain import ReleaseSupplyChainError
    from pathlib import Path

    monkeypatch.setattr("tooling.release_packaging.load_json", lambda path: {})
    compiler = Path("C:/VS/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe")
    monkeypatch.setattr(
        "tooling.release_supply_chain._probe_toolchain",
        lambda *a, **k: {"status": "passed", "executable": str(compiler)},
    )
    assert windows_cmake_toolset(tmp_path) == "v143,version=14.44.35207"
    monkeypatch.setattr(
        "tooling.release_supply_chain._probe_toolchain",
        lambda *a, **k: {"status": "unavailable"},
    )
    with pytest.raises(ReleaseSupplyChainError, match="MSVC compiler"):
        windows_cmake_toolset(tmp_path)


@pytest.mark.parametrize("flag", ["+1.75.0", "--locked", "--offline"])
def test_python_boundary_checks_the_actual_shared_cargo_builder(tmp_path, flag):
    import json
    import shutil
    from pathlib import Path
    from tooling.architecture_fitness import native_adapter_boundary_findings
    from tooling.governance import matches_any

    root = Path(__file__).resolve().parents[2]
    rules = json.loads(
        (root / "governance/architecture-rules.json").read_text(encoding="utf-8")
    )
    configuration = next(
        row["configuration"]
        for row in rules["rules"]
        if row["id"] == "python-native-adapter-boundary"
    )
    for row in configuration["required_markers"]:
        source, target = root / row["path"], tmp_path / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    assert native_adapter_boundary_findings(tmp_path, configuration, matches_any) == []
    helper = tmp_path / "tooling/native_release_build.py"
    helper.write_text(
        helper.read_text(encoding="utf-8").replace(flag, "removed-governed-input"),
        encoding="utf-8",
    )
    findings = native_adapter_boundary_findings(tmp_path, configuration, matches_any)
    assert any(
        "tooling/native_release_build.py" in message and flag in message
        for message, _ in findings
    )
