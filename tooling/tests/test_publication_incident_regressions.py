"""Incident regressions use governed companion names and scoped GitHub reads."""

import json
import secrets
from types import SimpleNamespace
import urllib.error

import pytest

from tooling import publish_certified_artifact as publisher
from tooling.release_supply_chain import MANIFEST_PATH, ROOT, ReleaseSupplyChainError


def test_fsharp_uses_registered_primary_surface_from_certified_bundle(
    tmp_path, monkeypatch
):
    manifest = json.loads(MANIFEST_PATH.read_text())
    primary = next(a for a in manifest["artifacts"] if a["id"] == "release:csharp")
    destination = tmp_path / MANIFEST_PATH.relative_to(ROOT)
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(manifest))
    sbom = {"fixture_only": primary["surface"]}
    (tmp_path / "sbom").mkdir()
    (tmp_path / "sbom" / (primary["surface"] + ".spdx.json")).write_text(
        json.dumps(sbom)
    )
    assert not (tmp_path / "sbom/csharp.spdx.json").exists()
    package = tmp_path / "STRling.FSharp.4.0.1.nupkg"
    package.write_bytes(b"unchanged certified fixture payload")
    monkeypatch.setenv("NUGET_KEY", secrets.token_hex(24))
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    monkeypatch.setattr(publisher, "_http", lambda url: b"fixture public CSharp bytes")
    events = []

    def verify(payload, expected):
        assert payload == b"fixture public CSharp bytes" and expected == sbom
        events.append("authenticated-primary")

    def submit(arguments, **kwargs):
        assert events == ["authenticated-primary"]
        assert arguments[:3] == ["dotnet", "nuget", "push"]
        assert package.read_bytes() == b"unchanged certified fixture payload"
        events.append("synthetic-upload")
        return SimpleNamespace(stdout=b"controlled fixture acceptance")

    monkeypatch.setattr(publisher, "verify_nuget_registry_payload", verify)
    monkeypatch.setattr(publisher.subprocess, "run", submit)
    publisher.upload(
        tmp_path,
        {
            "id": "release:fsharp",
            "delivery_kind": "package",
            "package_name": "STRling.FSharp",
        },
        "4.0.1",
        "a" * 40,
        [{"name": package.name}],
        verified_evidence=tmp_path / "fixture-evidence.json",
    )
    assert events == ["authenticated-primary", "synthetic-upload"]


def test_source_tag_availability_uses_same_scoped_identity_as_exact_creation(
    tmp_path, monkeypatch
):
    token = secrets.token_hex(24)
    monkeypatch.setenv("GITHUB_TOKEN", token)
    requests = []
    source = "a" * 40

    def http(url, **kwargs):
        assert url.startswith("https://api.github.com/repos/strling-lang/strling/git/")
        assert kwargs["headers"]["Authorization"] == "Bearer " + token
        requests.append((url, kwargs.get("method", "GET")))
        if kwargs.get("method", "GET") == "GET":
            assert url.endswith("/ref/tags/r-v4.0.1")
            raise urllib.error.HTTPError(url, 404, "controlled absence", {}, None)
        assert kwargs["method"] == "POST"
        assert json.loads(kwargs["data"]) == {
            "ref": "refs/tags/r-v4.0.1",
            "sha": source,
        }
        return b"controlled fixture reference"

    monkeypatch.setattr(publisher, "_http", http)
    publisher.upload(
        tmp_path,
        {
            "id": "release:r",
            "delivery_kind": "source-tag",
            "registry": "github-tag:r-vVERSION",
        },
        "4.0.1",
        source,
        [],
    )
    assert [method for _, method in requests] == ["GET", "POST"]


@pytest.mark.parametrize("status", [301, 401, 403, 409, 429, 500, 502, 503])
def test_availability_failure_retains_only_status_and_never_creates_tag(
    tmp_path, monkeypatch, status
):
    token = secrets.token_hex(24)
    monkeypatch.setenv("GITHUB_TOKEN", token)
    methods = []

    def reject(url, **kwargs):
        methods.append(kwargs.get("method", "GET"))
        raise urllib.error.HTTPError(url, status, token, {}, None)

    monkeypatch.setattr(publisher, "_http", reject)
    with pytest.raises(ReleaseSupplyChainError, match="HTTP " + str(status)) as caught:
        publisher.upload(
            tmp_path,
            {
                "id": "release:r",
                "delivery_kind": "source-tag",
                "registry": "github-tag:r-vVERSION",
            },
            "4.0.1",
            "a" * 40,
            [],
        )
    assert token not in str(caught.value)
    assert methods == ["GET"]


def test_source_tag_missing_protected_identity_precedes_registry_read(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        publisher, "_http", lambda *a, **k: pytest.fail("Unapproved request")
    )
    with pytest.raises(ReleaseSupplyChainError, match="GITHUB_TOKEN"):
        publisher.upload(
            tmp_path,
            {
                "id": "release:r",
                "delivery_kind": "source-tag",
                "registry": "github-tag:r-vVERSION",
            },
            "4.0.1",
            "a" * 40,
            [],
        )


def test_non_github_availability_never_receives_github_identity(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", secrets.token_hex(24))

    def absent(url, **kwargs):
        assert url == "https://registry.npmjs.org/example/4.0.1"
        assert not kwargs
        raise urllib.error.HTTPError(url, 404, "controlled absence", {}, None)

    monkeypatch.setattr(publisher, "_http", absent)
    publisher._require_absent("https://registry.npmjs.org/example/4.0.1")


def test_existing_source_tag_never_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", secrets.token_hex(24))
    methods = []

    def exists(url, **kwargs):
        methods.append(kwargs.get("method", "GET"))
        return b'{"ref":"refs/tags/r-v4.0.1"}'

    monkeypatch.setattr(publisher, "_http", exists)
    with pytest.raises(ReleaseSupplyChainError, match="already exists"):
        publisher.upload(
            tmp_path,
            {
                "id": "release:r",
                "delivery_kind": "source-tag",
                "registry": "github-tag:r-vVERSION",
            },
            "4.0.1",
            "a" * 40,
            [],
        )
    assert methods == ["GET"]
