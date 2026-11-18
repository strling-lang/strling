"""Actual registry/configuration contracts retain fail-closed publication checks."""

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import subprocess
import tarfile
import zipfile

import pytest

from tooling import publish_certified_artifact as publisher
from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ReleaseSupplyChainError,
    load_json,
)


@pytest.mark.parametrize(
    "payload",
    [b'{"release":null,"total":0,"took":1}', b'{"release":null,"total":0,"took":0.1}'],
)
def test_cpan_documented_empty_envelope_is_not_a_collision(monkeypatch, payload):
    monkeypatch.setattr(publisher, "_http", lambda url: payload)
    publisher._require_cpan_absent(
        "https://fastapi.metacpan.org/v1/release/STRLING/STRling-4.0.1"
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"release":{"name":"STRling-4.0.1"},"total":1,"took":0}',
        b'{"name":"STRling-4.0.1"}',
        b'{"release":null,"total":true,"took":0}',
        b'{"release":null,"total":0,"took":NaN}',
        b'{"errors":["backend unavailable"]}',
        b"not-json",
    ],
)
def test_cpan_present_or_unqualified_responses_never_admit_upload(monkeypatch, payload):
    monkeypatch.setattr(publisher, "_http", lambda url: payload)
    with pytest.raises(ReleaseSupplyChainError):
        publisher._require_cpan_absent(
            "https://fastapi.metacpan.org/v1/release/STRLING/STRling-4.0.1"
        )


@pytest.mark.parametrize(
    "status,absent", [(404, True), (401, False), (403, False), (500, False)]
)
def test_cpan_http_absence_does_not_confuse_authentication_or_service_failure(
    monkeypatch, status, absent
):
    def http(url):
        raise urllib.error.HTTPError(url, status, "fixture", None, None)

    monkeypatch.setattr(publisher, "_http", http)
    if absent:
        publisher._require_cpan_absent(
            "https://fastapi.metacpan.org/v1/release/STRLING/STRling-4.0.1"
        )
    else:
        with pytest.raises(ReleaseSupplyChainError):
            publisher._require_cpan_absent(
                "https://fastapi.metacpan.org/v1/release/STRLING/STRling-4.0.1"
            )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"module": None, "version": None},
        {"module": {"id": 12, "name": "strling", "user_id": 42}},
        {"module": {"id": 12, "name": "strling", "user_id": 42}, "version": None},
    ],
)
def test_luarocks_nil_omission_and_null_forms_are_owner_bound(document):
    publisher._require_luarocks_absent(document, 42)


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {"version": None},
        {"module": {}},
        {"module": None},
        {"module": None, "version": {}},
        {"module": None, "version": False},
        {"errors": []},
        {"errors": ["unavailable"]},
        {"module": {"id": 12, "name": "other", "user_id": 42}},
        {"module": {"id": 12, "name": "strling", "user_id": 41}},
        {"module": {"id": True, "name": "strling", "user_id": 42}},
    ],
)
def test_luarocks_existing_ambiguous_wrong_owner_or_error_forms_are_rejected(document):
    with pytest.raises(ReleaseSupplyChainError):
        publisher._require_luarocks_absent(document, 42)


def test_npm_publish_uses_distinct_private_empty_configuration_files(
    monkeypatch, tmp_path
):
    artifact = next(
        a
        for a in load_json(MANIFEST_PATH)["artifacts"]
        if a["id"] == "release:typescript"
    )
    package = tmp_path / "strling.tgz"
    package.write_bytes(b"fixture certified bytes")
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    observed = []

    def run(arguments, **kwargs):
        assert arguments[:2] == ["npm", "publish"]
        assert "--ignore-scripts" in arguments
        configs = [
            Path(
                next(
                    a.split("=", 1)[1]
                    for a in arguments
                    if a.startswith("--" + name + "=")
                )
            )
            for name in ("userconfig", "globalconfig")
        ]
        assert configs[0] != configs[1]
        assert all(path.is_file() and path.read_bytes() == b"" for path in configs)
        observed.extend(configs)
        return SimpleNamespace(stdout=b"fixture response")

    monkeypatch.setattr(publisher.subprocess, "run", run)
    assert (
        publisher.upload(
            tmp_path, artifact, "4.0.1", "a" * 40, [{"name": package.name}]
        )
        == b"fixture response"
    )
    assert len(observed) == 2 and not any(path.exists() for path in observed)


def test_npm_bootstrap_keeps_user_and_global_config_isolated():
    import yaml

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.load(
        (root / ".github/workflows/cd.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(
        s
        for s in workflow["jobs"]["publish-typescript"]["steps"]
        if s.get("name") == "Install pinned npm trusted-publishing client"
    )
    script = step["run"]
    assert "npm@11.5.1" in script and "--ignore-scripts" in script
    assert 'mktemp "$RUNNER_TEMP/strling-npm-user-XXXXXX"' in script
    assert 'mktemp "$RUNNER_TEMP/strling-npm-global-XXXXXX"' in script
    assert '--userconfig="$npm_user_config"' in script
    assert '--globalconfig="$npm_global_config"' in script


def test_dart_certifies_only_public_members_and_still_rejects_payload_omissions(
    tmp_path,
):
    from tooling.release_packaging import stage_dart_public_payload
    from tooling.public_distribution import authenticate_assembled_archive
    from tooling.public_retrieval import RetrievalError

    root = tmp_path / "source"
    root.mkdir()
    source_files = {
        "bindings/dart/lib/strling.dart": b"fixture public code",
        "bindings/dart/pubspec.yaml": b"name: strling\nversion: 4.0.1\n",
        "bindings/dart/README.md": b"fixture readme",
        "bindings/dart/CHANGELOG.md": b"fixture changelog",
        "bindings/dart/.pubignore": b"fixture parent selection config",
        "LICENSE": b"fixture license",
    }
    for name, data in source_files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "--", "."], check=True, capture_output=True
    )
    stage = tmp_path / "package"
    stage_dart_public_payload(root, stage)
    actual = {
        str(p.relative_to(stage)).replace("\\", "/"): p.read_bytes()
        for p in stage.rglob("*")
        if p.is_file()
    }
    assert set(actual) == {
        "lib/strling.dart",
        "pubspec.yaml",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
    }
    assert not (stage / ".pubignore").exists()
    sbom = {
        "files": [
            {
                "fileName": "package/" + name,
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": hashlib.sha256(data).hexdigest(),
                    }
                ],
            }
            for name, data in actual.items()
        ]
    }

    def archive(files):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    assert (
        authenticate_assembled_archive(archive(actual), subject="package", sbom=sbom)
        == actual
    )
    with pytest.raises(RetrievalError, match="differs"):
        authenticate_assembled_archive(
            archive({k: v for k, v in actual.items() if k != "lib/strling.dart"}),
            subject="package",
            sbom=sbom,
        )


def test_subprocess_failure_retains_server_reason_without_credential_or_argument_leak(
    monkeypatch,
):
    token = "fixture-only-publication-token"
    monkeypatch.setenv("GEM_HOST_API_KEY", token)
    error = subprocess.CalledProcessError(
        1,
        ["gem", "push", "not-for-logging", token],
        output=b"server validation failed",
        stderr=(
            "Authentication rejected: "
            + token
            + " Bearer fixture-only-header-token https://example.invalid/?api_key=fixture-only-query-token"
        ).encode(),
    )
    result = publisher._safe_subprocess_diagnostic(error)
    encoded = json.dumps(result)
    assert result["exit_code"] == 1 and "Authentication rejected" in encoded
    assert "server validation failed" in encoded
    assert not any(
        value in encoded
        for value in (
            token,
            "fixture-only-header-token",
            "fixture-only-query-token",
            "not-for-logging",
        )
    )


def test_subprocess_diagnostics_bound_output_and_remove_private_key_blocks():
    error = subprocess.CalledProcessError(
        2,
        ["gpg"],
        stderr=(
            "x" * 20000
            + (
                "-----BEGIN PGP "
                + "PRIVATE KEY BLOCK-----\nfixture-private-block\n-----END PGP PRIVATE KEY BLOCK-----"
            )
        ).encode(),
    )
    result = publisher._safe_subprocess_diagnostic(error)
    assert len(result["diagnostic"]) <= 16384
    assert "fixture-private-block" not in result["diagnostic"]


def test_ruby_requires_explicit_protected_identity_and_never_falls_back(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("GEM_HOST_API_KEY", raising=False)
    monkeypatch.setenv("RUBYGEMS_API_KEY", "fixture-unapproved-fallback")
    monkeypatch.setattr(
        publisher,
        "_require_absent",
        lambda url: pytest.fail("No registry request before credential guard"),
    )
    artifact = {"id": "release:ruby", "delivery_kind": "package"}
    with pytest.raises(ReleaseSupplyChainError, match="GEM_HOST_API_KEY"):
        publisher.upload(
            tmp_path, artifact, "4.0.1", "a" * 40, [{"name": "strling-4.0.1.gem"}]
        )


def test_ruby_failed_upload_retains_safe_error_and_exact_payload(tmp_path, monkeypatch):
    token = "fixture-protected-ruby-identity"
    monkeypatch.setenv("GEM_HOST_API_KEY", token)
    parent_context = {
        "GITHUB_ACTIONS": "true",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/fixture-oidc",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-unused-oidc-token",
        "GITHUB_TOKEN": "fixture-unused-github-token",
        "GH_TOKEN": "fixture-unused-gh-token",
    }
    for name, value in parent_context.items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "strling-4.0.1.gem"
    path.write_bytes(b"controlled exact gem payload")
    checks = []
    monkeypatch.setattr(publisher, "_require_absent", lambda url: checks.append(url))

    def reject(arguments, **kwargs):
        environment = kwargs["env"]
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 120
        assert environment["GEM_HOST_API_KEY"] == token
        assert all(name not in environment for name in parent_context)
        if arguments == ["gem", "--version"]:
            return SimpleNamespace(stdout=b"4.1.0\n")
        assert arguments == ["gem", "push", str(path), "--host", "https://rubygems.org"]
        assert path.read_bytes() == b"controlled exact gem payload"
        raise subprocess.CalledProcessError(
            1, arguments, stderr=("fixture server refusal " + token).encode()
        )

    monkeypatch.setattr(publisher.subprocess, "run", reject)
    with pytest.raises(
        ReleaseSupplyChainError, match="fixture server refusal"
    ) as caught:
        publisher.upload(
            tmp_path,
            {"id": "release:ruby", "delivery_kind": "package"},
            "4.0.1",
            "a" * 40,
            [{"name": path.name}],
        )
    assert token not in str(caught.value)
    assert all(
        publisher.os.environ[name] == value for name, value in parent_context.items()
    )
    assert checks == [
        "https://rubygems.org/api/v2/rubygems/strling/versions/4.0.1.json"
    ]
    assert path.read_bytes() == b"controlled exact gem payload"


@pytest.mark.parametrize("banner", [b"3.4.20\n", b"4.1.1\n", b"4.1.0\nextra", b""])
def test_ruby_wrong_or_unavailable_client_cannot_contact_registry(
    tmp_path, monkeypatch, banner
):
    monkeypatch.setenv("GEM_HOST_API_KEY", "fixture-publishing-key")
    monkeypatch.setattr(
        publisher,
        "_require_absent",
        lambda url: pytest.fail("No registry access with an unqualified client"),
    )

    def version_only(arguments, **kwargs):
        assert arguments == ["gem", "--version"]
        return SimpleNamespace(stdout=banner)

    monkeypatch.setattr(publisher.subprocess, "run", version_only)
    with pytest.raises(ReleaseSupplyChainError, match="qualified RubyGems 4.1.0"):
        publisher.upload(
            tmp_path,
            {"id": "release:ruby", "delivery_kind": "package"},
            "4.0.1",
            "a" * 40,
            [{"name": "strling-4.0.1.gem"}],
        )


def test_ruby_timeout_is_controlled_and_does_not_expose_captured_credentials(
    tmp_path, monkeypatch
):
    token = "fixture-scoped-gem-token"
    monkeypatch.setenv("GEM_HOST_API_KEY", token)
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    package = tmp_path / "strling-4.0.1.gem"
    package.write_bytes(b"fixture-certified-bytes")

    def timeout(arguments, **kwargs):
        if arguments == ["gem", "--version"]:
            return SimpleNamespace(stdout=b"4.1.0\n")
        raise subprocess.TimeoutExpired(arguments, 120, output=token, stderr=token)

    monkeypatch.setattr(publisher.subprocess, "run", timeout)
    with pytest.raises(
        ReleaseSupplyChainError, match="requires reconciliation"
    ) as caught:
        publisher.upload(
            tmp_path,
            {"id": "release:ruby", "delivery_kind": "package"},
            "4.0.1",
            "a" * 40,
            [{"name": package.name}],
        )
    assert token not in str(caught.value)
    assert package.read_bytes() == b"fixture-certified-bytes"


def test_ruby_publication_pins_reviewed_client_and_preserves_protected_provenance():
    import yaml
    from tooling.release_supply_chain import ROOT

    jobs = yaml.safe_load((ROOT / ".github/workflows/cd.yml").read_text())["jobs"]
    publisher_job = jobs["publish-ruby"]
    ruby = [
        step
        for step in publisher_job["steps"]
        if step.get("uses", "").startswith("ruby/setup-ruby@")
    ]
    assert len(ruby) == 1 and ruby[0]["with"]["rubygems"] == "4.1.0"
    assert publisher_job["environment"] == "release"
    assert publisher_job["permissions"]["id-token"] == "write"
    assert "RELEASE_AUTHORIZED_RUN_ID" in publisher_job["if"]
    assert "RELEASE_AUTHORIZED_RUN_ATTEMPT" in publisher_job["if"]
    attestation = jobs["attest-release-subjects"]
    assert attestation["environment"] == "release-attestation"
    assert attestation["permissions"]["attestations"] == "write"
    actions = [
        step
        for step in attestation["steps"]
        if step.get("uses", "").startswith("actions/attest@")
    ]
    assert len(actions) == 1
    assert (
        actions[0]["uses"] == "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d"
    )
    assert actions[0]["with"]["subject-checksums"] == ".cert/subjects.sha256"


@pytest.mark.parametrize("version", ["4.0.0", "4.0.1", "4.0.2", "4.0.3"])
@pytest.mark.parametrize("layout", ["platlib", "purelib"])
@pytest.mark.parametrize("metadata", ["valid", "wrong-tag", "pure-root"])
def test_native_wheel_contract_preserves_history_and_rejects_new_bad_layouts(
    tmp_path, monkeypatch, version, layout, metadata
):
    from tooling import release_payload

    native = b"controlled native fixture"
    monkeypatch.setattr(
        release_payload, "native_identity", lambda data, product: "linux-x86_64"
    )
    monkeypatch.setattr(release_payload, "inspect_native", lambda data: None)
    tag = "manylinux_2_34_x86_64"
    path = tmp_path / f"strling-{version}-cp312-none-{tag}.whl"
    prefix = f"strling-{version}.data/purelib/" if layout == "purelib" else ""
    package = prefix + "STRling/_native/"
    wheel = "Root-Is-Purelib: " + ("true" if metadata == "pure-root" else "false")
    wheel += (
        "\nTag: cp312-none-"
        + ("linux_x86_64" if metadata == "wrong-tag" else tag)
        + "\n"
    )
    files = {
        package + "libstrling_interop.so": native,
        package + "kernel-identity.json": json.dumps(
            {
                "product_version": version,
                "native_sha256": hashlib.sha256(native).hexdigest(),
            }
        ).encode(),
        "strling.dist-info/METADATA": f"Name: STRling\nVersion: {version}\nRequires-Python: <3.13,>=3.12\nLicense-Expression: Apache-2.0\n".encode(),
        "strling.dist-info/WHEEL": wheel.encode(),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    artifact = {
        "id": "release:python",
        "artifact_policy": {
            "subject_kind": "file",
            "platform_patterns": {
                "linux-x86_64": [f"strling-VERSION-cp312-none-{tag}.whl"]
            },
        },
        "payload_contract": {
            "required_file_groups": [["*STRling/_native/libstrling_interop.so"]]
        },
    }
    if metadata != "valid" or (layout == "purelib" and version != "4.0.0"):
        with pytest.raises(ValueError, match="wheel layout or platform metadata"):
            release_payload.inspect_payload(
                tmp_path, artifact, version, [{"name": path.name}]
            )
    else:
        # Historical certification remains interpretable, without becoming a
        # new public-installation or future-release qualification claim.
        assert release_payload.inspect_payload(
            tmp_path, artifact, version, [{"name": path.name}]
        )


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "newer-abi",
        "external-library",
        "purelib",
        "isa",
        "missing-field",
        "boolean-version",
        "changed-native",
    ],
)
def test_linux_wheel_audit_blocks_unsafe_tags_and_payload_changes(
    tmp_path, monkeypatch, defect
):
    from tooling import release_packaging as packaging

    root = tmp_path / "source"
    root.mkdir()
    (root / "requirements.lock").write_text("auditwheel==6.8.2\n")
    (root / "toolchain.json").write_text(
        json.dumps(
            {
                "tools": {
                    "auditwheel": {
                        "resolution": {
                            "model": "repository_managed",
                            "file": "requirements.lock",
                            "file_pattern": r"auditwheel==([0-9.]+)",
                        },
                        "version_pattern": r"auditwheel ([0-9.]+)",
                    }
                }
            }
        )
    )
    artifact = {
        "artifact_policy": {
            "platform_patterns": {
                "linux-x86_64": [
                    "dist/strling-VERSION-cp312-none-manylinux_2_34_x86_64.whl"
                ]
            }
        }
    }
    directory = root / "dist"
    directory.mkdir()
    original = directory / "strling-4.0.1-cp312-none-linux_x86_64.whl"
    destination = directory / "strling-4.0.1-cp312-none-manylinux_2_34_x86_64.whl"
    files = {
        "STRling/_native/libstrling_interop.so": b"fixture native bytes",
        "strling.dist-info/WHEEL": b"fixture wheel metadata",
        "strling.dist-info/RECORD": b"fixture record",
    }

    def write_archive(path, payload):
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in payload.items():
                archive.writestr(name, data)

    write_archive(original, files)
    monkeypatch.setattr(packaging.importlib.metadata, "version", lambda name: "6.8.2")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert "-I" in arguments
        if "auditwheel" in arguments:
            report = {
                "version": 1,
                "wheel": Path(arguments[-1]).name,
                "pure": False,
                "pyfpe": False,
                "ucs2": False,
                "unsupported_isa": False,
                "overall_tag": "manylinux_2_34_x86_64",
                "sym_tag": "manylinux_2_34_x86_64",
                "external_libs": {},
            }
            if defect == "newer-abi":
                report["overall_tag"] = "manylinux_2_39_x86_64"
            if defect == "external-library":
                report["external_libs"] = {"libunexpected.so": "/fixture"}
            if defect == "purelib":
                report["pure"] = True
            if defect == "isa":
                report["unsupported_isa"] = True
            if defect == "missing-field":
                report.pop("ucs2")
            if defect == "boolean-version":
                report["version"] = True
            return SimpleNamespace(stdout=json.dumps(report).encode())
        assert "wheel" in arguments and "--platform-tag" in arguments
        changed = dict(files)
        changed["strling.dist-info/WHEEL"] = b"qualified metadata"
        changed["strling.dist-info/RECORD"] = b"qualified record"
        if defect == "changed-native":
            changed["STRling/_native/libstrling_interop.so"] = (
                b"substituted native bytes"
            )
        write_archive(destination, changed)
        return SimpleNamespace(stdout=b"fixture")

    monkeypatch.setattr(packaging.subprocess, "run", run)
    if defect:
        with pytest.raises(ReleaseSupplyChainError):
            packaging.qualify_linux_python_wheel(root, artifact, "4.0.1", {})
        assert original.exists()
        if defect != "changed-native":
            assert len(calls) == 1
    else:
        result = packaging.qualify_linux_python_wheel(root, artifact, "4.0.1", {})
        assert (
            result["payload_bytes_unchanged"] is True
            and result["platform_tag"] == "manylinux_2_34_x86_64"
        )
        assert destination.exists() and not original.exists()
