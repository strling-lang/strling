"""Adversarial authority checks precede public registry integration."""

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tooling.public_distribution import (
    authenticate_archive,
    obligations,
    reduce_observations,
    strict_json,
)
from tooling.public_retrieval import (
    FixtureTransport,
    PublicTransport,
    RetrievalError,
    public_url,
)


def test_versioned_contract_matches_registry():
    from tooling.public_distribution import validate_contract

    assert validate_contract(ROOT)["artifacts"] == 17


def test_consumer_environment_drops_secrets_and_developer_paths(tmp_path):
    from tooling.release_consumers import public_consumer_environment

    environment = public_consumer_environment(
        tmp_path,
        {
            "PATH": "governed-sdk",
            "PYTHONPATH": "developer-checkout",
            "LD_LIBRARY_PATH": "unpublished-library",
            "STRLING_NATIVE_LIBRARY": "wrong",
            "AWS_ACCESS_KEY_ID": "fixture",
            "GITHUB_TOKEN": "fixture",
            "NPM_TOKEN": "fixture",
            "PIP_INDEX_URL": "private-registry",
            "RUSTC_WRAPPER": "untrusted-command",
        },
    )
    assert environment["PATH"] == "governed-sdk"
    assert not any(
        key in environment
        for key in (
            "PYTHONPATH",
            "LD_LIBRARY_PATH",
            "STRLING_NATIVE_LIBRARY",
            "AWS_ACCESS_KEY_ID",
            "GITHUB_TOKEN",
            "NPM_TOKEN",
            "PIP_INDEX_URL",
            "RUSTC_WRAPPER",
        )
    )
    assert environment["HOME"] == str(tmp_path / "home")


def test_public_consumer_requires_disposable_runner(tmp_path, manifest, monkeypatch):
    from tooling.release_consumers import verify_retrieved_consumer
    from tooling.release_supply_chain import ReleaseSupplyChainError

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ReleaseSupplyChainError, match="disposable"):
        verify_retrieved_consumer(
            "release:python",
            retrieval_root=tmp_path / "retrieved",
            fixture_root=ROOT,
            work=tmp_path / "consumer",
            manifest=manifest,
            version="4.0.0",
            sdk_environment={},
            retrieval_files={},
            authority="public",
        )


@pytest.mark.parametrize(
    "identity,scope",
    [("release:typescript", "linux-x86_64"), ("release:python", "linux-aarch64")],
)
def test_consumer_rejects_unqualified_runtime_scope(
    tmp_path, manifest, monkeypatch, identity, scope
):
    from tooling import release_consumers as consumers
    from tooling.release_supply_chain import ReleaseSupplyChainError

    monkeypatch.setattr("tooling.release_packaging.host_scope", lambda: scope)
    with pytest.raises(ReleaseSupplyChainError, match="Supported scope"):
        consumers.verify_retrieved_consumer(
            identity,
            retrieval_root=tmp_path / "retrieved",
            fixture_root=ROOT,
            work=tmp_path / "consumer",
            manifest=manifest,
            version="4.0.0",
            sdk_environment={},
            retrieval_files={},
            authority="staged",
        )


def test_caller_provided_native_dependency_is_mandatory(tmp_path):
    from tooling.release_consumers import consume_gds
    from tooling.release_supply_chain import ReleaseSupplyChainError

    with pytest.raises(
        ReleaseSupplyChainError, match="explicit canonical native runtime"
    ):
        consume_gds(tmp_path, {"id": "release:go"}, tmp_path, "4.0.0", {}, [], None)


def test_changed_retrieval_cannot_use_developer_fallback(
    tmp_path, manifest, monkeypatch
):
    from tooling import release_consumers as consumers
    from tooling.release_supply_chain import ReleaseSupplyChainError

    retrieved = tmp_path / "retrieved"
    retrieved.mkdir()
    (retrieved / "package.whl").write_bytes(b"substituted")
    monkeypatch.setattr("tooling.release_packaging.host_scope", lambda: "linux-x86_64")
    monkeypatch.setattr(
        "tooling.release_supply_chain._probe_toolchain",
        lambda *a, **kw: {"status": "passed"},
    )
    with pytest.raises(ReleaseSupplyChainError, match="changed before installation"):
        consumers.verify_retrieved_consumer(
            "release:python",
            retrieval_root=retrieved,
            fixture_root=ROOT,
            work=tmp_path / "consumer",
            manifest=manifest,
            version="4.0.0",
            sdk_environment={},
            retrieval_files={"package.whl": hashlib.sha256(b"authentic").hexdigest()},
            authority="staged",
        )
    assert not (tmp_path / "consumer").exists()


@pytest.mark.parametrize(
    "command",
    [
        "pip install wrong==4.0.0",
        "pip install STRling==3.0.0",
        "pip install STRling==4.0.0; do-evil",
        "pip install STRling==4.0.0\nother-command",
    ],
)
def test_documentation_cannot_change_identity_or_commands(manifest, command):
    from tooling.public_metadata import verify_documented_coordinate

    artifact = next(
        row for row in manifest["artifacts"] if row["id"] == "release:python"
    )
    with pytest.raises(RetrievalError):
        verify_documented_coordinate(command, artifact, "4.0.0")
    assert (
        verify_documented_coordinate("pip install STRling==4.0.0", artifact, "4.0.0")[
            "executed"
        ]
        is False
    )


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def manifest():
    return json.loads(
        (
            ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
        ).read_text()
    )


def results(manifest, authority="synthetic", status="READY"):
    return [
        {**row, "authority": authority, "status": status, "retrieval_sha256": "a" * 64}
        for row in obligations(manifest)
    ]


def test_denominator_comes_from_manifest(manifest):
    rows = obligations(manifest)
    assert len({row["artifact_id"] for row in rows}) == len(manifest["artifacts"]) == 17
    assert len(rows) == 17 * 8 + 15 * 8
    subset = copy.deepcopy(manifest)
    subset["artifacts"].pop()
    assert len(obligations(subset)) == len(rows) - 8


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "extra", "tier", "platform"]
)
def test_obligation_mutations_fail(manifest, mutation):
    rows = results(manifest)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "extra":
        rows.append({**rows[0], "id": "extra"})
    elif mutation == "tier":
        rows[0]["tier"] = "Preview"
    else:
        rows[0]["platform"] = "macos-arm64"
    with pytest.raises(RetrievalError):
        reduce_observations(manifest, rows, authority="synthetic")


@pytest.mark.parametrize("authority", ["synthetic", "staged"])
def test_engineering_cannot_verify_public_release(manifest, authority):
    assert (
        reduce_observations(
            manifest, results(manifest, authority), authority=authority
        )["status"]
        == "READY"
    )
    with pytest.raises(RetrievalError):
        reduce_observations(
            manifest, results(manifest, authority, "VERIFIED"), authority=authority
        )


def test_public_success_requires_retrieval(manifest):
    rows = results(manifest, "public", "VERIFIED")
    assert (
        reduce_observations(manifest, rows, authority="public")["status"] == "VERIFIED"
    )
    rows[0].pop("retrieval_sha256")
    with pytest.raises(RetrievalError):
        reduce_observations(manifest, rows, authority="public")


@pytest.mark.parametrize(
    "state", ["NOT_PUBLISHED", "INDETERMINATE", "FAILED", "VERIFYING"]
)
def test_partial_results_never_verify(manifest, state):
    rows = results(manifest, "public", "VERIFIED")
    rows[0]["status"] = state
    result = reduce_observations(manifest, rows, authority="public")
    assert result["release_transition"] is None
    assert result["publication_authorized"] is False
    assert result["registry_mutation_authorized"] is False
    assert result["partial_publication"] == (state == "NOT_PUBLISHED")


def test_preview_has_no_invented_supported_consumer(manifest):
    preview = {
        a["id"]
        for a in manifest["artifacts"]
        if a["distribution_contract"]["tier"] == "Preview"
    }
    assert all(
        row["platform"] is None
        for row in obligations(manifest)
        if row["artifact_id"] in preview
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.example/a",
        "https://evil.example/a",
        "https://" + "user:password" + "@registry.example/a",
        "https://registry.example:8443/a",
        "https://registry.example/a#fragment",
        "file:///tmp/package",
        "https://registry.example/a\n",
        "https://registry.example\\evil/a",
    ],
)
def test_unapproved_url_fails_before_network(url):
    with (
        patch("tooling.public_retrieval.resolve_addresses") as dns,
        pytest.raises(RetrievalError),
    ):
        public_url(url, {"https://registry.example"})
    dns.assert_not_called()


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_private_registry_resolution_fails(ip):
    with (
        patch(
            "tooling.public_retrieval.resolve_addresses",
            return_value=[(0, 0, 0, "", (ip, 443))],
        ),
        pytest.raises(RetrievalError),
    ):
        public_url("https://registry.example/a", {"https://registry.example"})


def test_fixture_never_falls_back_to_network():
    fixture = FixtureTransport({"https://registry.example/a": b"data"})
    assert fixture.get("https://registry.example/a") == b"data"
    assert fixture.observations[0]["authority"] == "synthetic"
    with pytest.raises(RetrievalError, match="unregistered"):
        fixture.get("https://registry.example/missing")


@pytest.mark.parametrize(
    "payload", [b'{"name":"a","name":"b"}', b"[]", b"null", b"{", b"\xff"]
)
def test_malformed_metadata(payload):
    with pytest.raises(RetrievalError):
        strict_json(payload)


def archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as stream:
        for name, value in entries.items():
            stream.writestr(name, value)
    return buffer.getvalue()


def test_inner_payload_authentication():
    payload = archive({"package/version.txt": b"4.0.0"})
    digest = hashlib.sha256(payload).hexdigest()
    sbom = {
        "files": [
            {
                "fileName": "package.zip!/package/version.txt",
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": hashlib.sha256(b"4.0.0").hexdigest(),
                    }
                ],
            }
        ]
    }
    artifact = {
        "reproducibility": {"mode": "byte-for-byte", "allowed_normalizations": []}
    }
    assert (
        authenticate_archive(
            payload,
            subject="package.zip",
            expected_sha256=digest,
            artifact=artifact,
            sbom=sbom,
        )["files"]
        == 1
    )
    for entries in (
        {"package/version.txt": b"3.0.0"},
        {"package/version.txt": b"4.0.0", "extra": b""},
        {"../escape": b""},
    ):
        with pytest.raises(RetrievalError):
            authenticate_archive(
                archive(entries),
                subject="package.zip",
                expected_sha256=digest,
                artifact=artifact,
                sbom=sbom,
            )
    with pytest.raises(RetrievalError):
        authenticate_archive(
            payload,
            subject="package.zip",
            expected_sha256="0" * 64,
            artifact=artifact,
            sbom=sbom,
        )
    with pytest.raises(RetrievalError):
        authenticate_archive(
            payload,
            subject="unrelated.zip",
            expected_sha256=digest,
            artifact=artifact,
            sbom=sbom,
        )


def test_budget_and_existing_evidence_are_protected(tmp_path):
    with pytest.raises(ValueError):
        PublicTransport(tmp_path / "bad", set(), attempts=4)
    PublicTransport(tmp_path / "retained", set())
    with pytest.raises(FileExistsError):
        PublicTransport(tmp_path / "retained", set())
