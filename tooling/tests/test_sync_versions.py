from pathlib import Path
import copy
import json
import pytest

from tooling.sync_versions import (
    get_source_version,
    update_file,
    update_json,
    update_composer_json,
    update_yaml_pubspec,
    update_xml_csproj,
    update_c_source,
    update_lua_rockspec,
    update_ruby_version_file,
)
import tooling.sync_versions as sync_versions


def test_update_json_changes_version():
    inp = '{\n  "name": "foo",\n  "version": "1.2.3"\n}\n'
    out = update_json(inp, "3.0.0", Path("dummy"))
    assert '"version": "3.0.0"' in out


def test_update_composer_json_replace_and_insert():
    inp = '{"name": "pkg", "version": "0.0.1"}\n'
    out = update_composer_json(inp, "3.0.0", Path("dummy"))
    assert '"version": "3.0.0"' in out

    inp2 = '{"name": "pkg"}\n'
    out2 = update_composer_json(inp2, "3.0.0", Path("dummy"))
    assert '"version": "3.0.0"' in out2


def test_update_yaml_pubspec_replaces_line():
    inp = "name: example\nversion: 1.2.3\n"
    out = update_yaml_pubspec(inp, "3.0.0", Path("dummy"))
    assert "version: 3.0.0" in out


def test_update_xml_csproj_replace_and_insert():
    inp = "<Project>\n  <PropertyGroup>\n    <Version>0.1.2</Version>\n  </PropertyGroup>\n</Project>"
    out = update_xml_csproj(inp, "3.0.0", Path("dummy"))
    assert "<Version>3.0.0</Version>" in out

    inp2 = "<Project>\n  <PropertyGroup>\n    <Some>v</Some>\n  </PropertyGroup>\n</Project>"
    out2 = update_xml_csproj(inp2, "3.0.0", Path("dummy"))
    assert "<Version>3.0.0</Version>" in out2


def test_update_c_source_returns_replaced():
    inp = 'const char *strling_version(void) { return "1.0.0"; }\n'
    out = update_c_source(inp, "3.0.0", Path("dummy"))
    assert 'return "3.0.0"' in out


def test_update_ruby_version_preserves_protocol_and_abi_constants():
    inp = """module Strling
  VERSION = '2.0.0'
  INTEROP_PROTOCOL_VERSION = '1.0.0'
  NATIVE_ABI_VERSION = 1
end
"""
    out = update_ruby_version_file(inp, "3.0.0", Path("dummy"))
    assert "VERSION = '3.0.0'" in out
    assert "INTEROP_PROTOCOL_VERSION = '1.0.0'" in out
    assert "NATIVE_ABI_VERSION = 1" in out


def test_update_lua_rockspec_revision():
    inp = 'version = "1.2.3-1"\n'
    out = update_lua_rockspec(inp, "3.0.0", Path("dummy"))
    assert 'version = "3.0.0-1"' in out

    inp2 = 'version = "1.2.3"\n'
    out2 = update_lua_rockspec(inp2, "3.0.0-2", Path("dummy"))
    # when a revision is provided in the source version, it is preserved
    assert 'version = "3.0.0-2"' in out2


def test_update_file_dry_run_reports_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_versions, "ROOT_DIR", tmp_path)
    target = tmp_path / "package.json"
    target.write_text('{"version": "1.0.0"}\n', encoding="utf-8")

    assert not update_file(
        "package.json",
        "3.0.0",
        dry_run=True,
        updater_func=update_json,
    )
    assert target.read_text(encoding="utf-8") == '{"version": "1.0.0"}\n'


def test_update_file_dry_run_accepts_exact_content(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_versions, "ROOT_DIR", tmp_path)
    target = tmp_path / "package.json"
    target.write_text('{"version": "3.0.0"}\n', encoding="utf-8")

    assert update_file(
        "package.json",
        "3.0.0",
        dry_run=True,
        updater_func=update_json,
    )


def test_source_version_comes_from_governed_projection(tmp_path, monkeypatch):
    source = tmp_path / "release-policy.json"
    source.write_text(
        '{"product":{"version":"4.0.0-rc.1","repository_projection":{"version":"4.0.0-rc.1","status":"active"}}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_versions, "SOURCE_FILE", source)
    assert get_source_version() == "4.0.0-rc.1"


def _projection_fixture(tmp_path):
    path = tmp_path / "bindings/python/pyproject.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[project]\nname = "STRling"\nversion = "3.0.0"\n')
    policy = {
        "version_surfaces": [
            {
                "id": "python",
                "path": "bindings/python/pyproject.toml",
                "probe": {
                    "kind": "regex",
                    "pattern": r'(?m)^version = "([^\"]+)"',
                    "expected": "repository_projection",
                },
            }
        ]
    }
    return path, policy


def test_registry_projection_is_complete_idempotent_and_preserves_contracts(tmp_path):
    path, policy = _projection_fixture(tmp_path)
    interop = tmp_path / "bindings/interop/Cargo.toml"
    interop.parent.mkdir(parents=True)
    interop.write_text('[package]\nname="strling-interop"\nversion="0.1.0"\n')
    independent = copy.deepcopy(policy["version_surfaces"][0])
    independent.update(
        id="interop",
        path="bindings/interop/Cargo.toml",
        probe={"kind": "regex", "pattern": r'version="([^\"]+)"', "expected": "0.1.0"},
    )
    policy["version_surfaces"].append(independent)
    plan = sync_versions.projected_contents(tmp_path, policy, "4.0.0")
    assert 'version = "4.0.0"' in plan[path]
    assert plan[interop] == interop.read_text()
    for file, content in plan.items():
        file.write_text(content)
    assert sync_versions.projected_contents(tmp_path, policy, "4.0.0") == plan
    interop.write_text(interop.read_text().replace("0.1.0", "4.0.0"))
    with pytest.raises(ValueError, match="Independent version drift"):
        sync_versions.projected_contents(tmp_path, policy, "4.0.0")


@pytest.mark.parametrize(
    "content",
    ['[project]\nname="x"\n', '[project]\nversion="1"\nversion="2"\n', "broken toml"],
)
def test_malformed_or_missing_version_field_refuses_all_writes(tmp_path, content):
    path, policy = _projection_fixture(tmp_path)
    path.write_text(content)
    with pytest.raises(ValueError):
        sync_versions.projected_contents(tmp_path, policy, "4.0.0")
    assert path.read_text() == content


def test_unregistered_public_manifest_is_rejected(tmp_path):
    path, policy = _projection_fixture(tmp_path)
    extra = tmp_path / "bindings/new/package.json"
    extra.parent.mkdir(parents=True)
    extra.write_text('{"name":"unregistered","version":"3.0.0"}')
    with pytest.raises(ValueError, match="Unregistered public manifest"):
        sync_versions.projected_contents(tmp_path, policy, "4.0.0")
    assert "3.0.0" in path.read_text()


@pytest.mark.parametrize(
    "version,status,projection",
    [
        ("04.0.0", "active", "04.0.0"),
        ("4.0.0", "preparation", "4.0.0"),
        ("4.0.0", "active", "9.9.9"),
        ("4.0.0+override", "active", "4.0.0+override"),
    ],
)
def test_invalid_or_override_product_version_is_rejected(
    tmp_path, monkeypatch, version, status, projection
):
    source = tmp_path / "policy.json"
    source.write_text(
        json.dumps(
            {
                "product": {
                    "version": version,
                    "repository_projection": {"version": projection, "status": status},
                }
            }
        )
    )
    monkeypatch.setattr(sync_versions, "SOURCE_FILE", source)
    with pytest.raises(ValueError):
        get_source_version()


def test_duplicate_json_package_version_is_rejected(tmp_path):
    path = tmp_path / "bindings/new/package.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"version":"3.0.0","version":"4.0.0"}')
    policy = {
        "version_surfaces": [
            {
                "id": "npm",
                "path": "bindings/new/package.json",
                "probe": {
                    "kind": "json",
                    "pointer": "/version",
                    "expected": "repository_projection",
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="Duplicate JSON"):
        sync_versions.projected_contents(tmp_path, policy, "4.0.0")


def test_failed_multifile_projection_rolls_back(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_bytes(b"first original\r\n")
    second.write_bytes(b"second original\r\n")
    replace = sync_versions.os.replace

    def fail_second(source, destination):
        if destination == second:
            raise OSError("simulated replacement failure")
        replace(source, destination)

    monkeypatch.setattr(sync_versions.os, "replace", fail_second)
    with pytest.raises(OSError, match="replacement failure"):
        sync_versions.write_projection({first: "new first\n", second: "new second\n"})
    assert first.read_bytes() == b"first original\r\n"
    assert second.read_bytes() == b"second original\r\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["first", "second"]


def test_cargo_probe_cannot_substitute_a_dependency_version(tmp_path):
    path = tmp_path / "bindings/new/Cargo.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[package]\nname="x"\n[dependencies.serde]\nversion="1.0"\n')
    policy = {
        "version_surfaces": [
            {
                "id": "crate",
                "path": "bindings/new/Cargo.toml",
                "probe": {
                    "kind": "regex",
                    "pattern": r'(?ms)^\[package\].*?^version\s*=\s*"([^\"]+)"',
                    "expected": "repository_projection",
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="Cargo package version is missing"):
        sync_versions.projected_contents(tmp_path, policy, "4.0.0")
    assert 'version="1.0"' in path.read_text()


def test_composer_projection_updates_only_native_metadata_hash():
    original = json.loads(
        (sync_versions.ROOT_DIR / "bindings/php/composer.lock").read_text(
            encoding="utf-8"
        )
    )
    manifest = (sync_versions.ROOT_DIR / "bindings/php/composer.json").read_text(
        encoding="utf-8"
    )
    stale = copy.deepcopy(original)
    stale["content-hash"] = "0" * 32
    projected = json.loads(
        sync_versions.composer_lock_projection(manifest, json.dumps(stale))
    )
    assert projected == original
    assert projected["packages-dev"] == stale["packages-dev"]
    assert sync_versions.composer_lock_projection(
        manifest, json.dumps(projected)
    ) == json.dumps(projected)


def test_composer_metadata_hash_detects_product_version_and_keeps_nested_order():
    manifest = '{"name":"strling/strling","version":"4.0.0","require":{"php":"^8.2","ext-ffi":"*"}}'
    lock = '{"content-hash":"00000000000000000000000000000000","packages":[]}'
    first = sync_versions.composer_lock_projection(manifest, lock)
    assert first != sync_versions.composer_lock_projection(
        manifest.replace("4.0.0", "3.0.0"), lock
    )
    with pytest.raises(ValueError, match="Duplicate JSON"):
        sync_versions.composer_lock_projection(
            manifest, '{"content-hash":"a","content-hash":"b"}'
        )
