"""NuGet indexing delay cannot admit F# before its authenticated C# companion."""

import json
import time
from types import SimpleNamespace
import urllib.error

import pytest

from tooling import publish_certified_artifact as publisher
from tooling.release_supply_chain import ReleaseSupplyChainError


def test_fsharp_waits_for_repository_authenticated_csharp_before_upload(
    tmp_path, monkeypatch
):
    events = []
    reads = 0
    package = tmp_path / "STRling.FSharp.4.0.1.nupkg"
    package.write_bytes(b"fixture certified FSharp payload")
    (tmp_path / "sbom").mkdir()
    sbom = {"fixture_only": "authenticated primary CSharp SBOM"}
    (tmp_path / "sbom/csharp.spdx.json").write_text(json.dumps(sbom))
    monkeypatch.setenv("NUGET_KEY", "fixture-only-no-publishing-access")
    monkeypatch.setattr(
        publisher, "_require_absent", lambda url: events.append("check-fsharp-absent")
    )
    monkeypatch.setattr(time, "sleep", lambda seconds: events.append("wait"))

    def http(url, **kwargs):
        nonlocal reads
        assert (
            url
            == "https://api.nuget.org/v3-flatcontainer/strling/4.0.1/strling.4.0.1.nupkg"
        )
        assert not kwargs
        reads += 1
        events.append("read-csharp")
        if reads == 1:
            raise urllib.error.HTTPError(url, 404, "not indexed yet", {}, None)
        return b"fixture repository-signed CSharp payload"

    def authenticate(payload, expected):
        assert (
            payload == b"fixture repository-signed CSharp payload" and expected == sbom
        )
        events.append("verify-repository-signature-and-sbom")
        return {"fixture_only": True}

    def submit(arguments, **kwargs):
        assert events[-1] == "check-fsharp-absent"
        assert "verify-repository-signature-and-sbom" in events
        assert arguments[:3] == ["dotnet", "nuget", "push"]
        assert package.read_bytes() == b"fixture certified FSharp payload"
        events.append("submit-fsharp-once")
        return SimpleNamespace(stdout=b"fixture accepted; no real upload")

    monkeypatch.setattr(publisher, "_http", http)
    monkeypatch.setattr(publisher, "verify_nuget_registry_payload", authenticate)
    monkeypatch.setattr(publisher.subprocess, "run", submit)
    result = publisher.upload(
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
    assert result == b"fixture accepted; no real upload"
    assert events == [
        "read-csharp",
        "wait",
        "read-csharp",
        "verify-repository-signature-and-sbom",
        "check-fsharp-absent",
        "submit-fsharp-once",
    ]


@pytest.fixture
def guarded_fsharp(tmp_path, monkeypatch):
    package = tmp_path / "STRling.FSharp.4.0.1.nupkg"
    package.write_bytes(b"fixture certified package")
    (tmp_path / "sbom").mkdir()
    (tmp_path / "sbom/csharp.spdx.json").write_text('{"fixture_only":true}')
    monkeypatch.setenv("NUGET_KEY", "fixture-only-no-publishing-access")
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("Unadmitted upload"),
    )

    def call(*, evidence=True):
        return publisher.upload(
            tmp_path,
            {
                "id": "release:fsharp",
                "delivery_kind": "package",
                "package_name": "STRling.FSharp",
            },
            "4.0.1",
            "a" * 40,
            [{"name": package.name}],
            verified_evidence=tmp_path / "fixture-evidence.json" if evidence else None,
        )

    return call


@pytest.mark.parametrize("failure", ["repository-signature", "trust-material-404"])
def test_fsharp_validation_failure_is_never_a_package_availability_retry(
    guarded_fsharp, monkeypatch, failure
):
    calls = []
    monkeypatch.setattr(
        time, "sleep", lambda seconds: pytest.fail("Invalid validation retry")
    )
    monkeypatch.setattr(
        publisher, "_http", lambda url: calls.append(url) or b"fixture package"
    )

    def reject(payload, sbom):
        if failure == "trust-material-404":
            raise urllib.error.HTTPError(
                "https://api.nuget.org/fixture-trust-material",
                404,
                "unavailable trust material",
                {},
                None,
            )
        raise ReleaseSupplyChainError(
            "nuget-signature", "invalid repository signature or SBOM"
        )

    monkeypatch.setattr(publisher, "verify_nuget_registry_payload", reject)
    expected = (
        urllib.error.HTTPError
        if failure == "trust-material-404"
        else ReleaseSupplyChainError
    )
    with pytest.raises(expected):
        guarded_fsharp()
    assert len(calls) == 1


def test_fsharp_missing_authenticated_companion_evidence_precedes_network(
    guarded_fsharp, monkeypatch
):
    monkeypatch.setattr(
        publisher, "_http", lambda url: pytest.fail("Unqualified request")
    )
    with pytest.raises(ReleaseSupplyChainError, match="checksums are required"):
        guarded_fsharp(evidence=False)


def test_fsharp_missing_primary_sbom_precedes_network(
    guarded_fsharp, tmp_path, monkeypatch
):
    (tmp_path / "sbom/csharp.spdx.json").unlink()
    monkeypatch.setattr(publisher, "_http", lambda url: pytest.fail("Missing evidence"))
    with pytest.raises(ReleaseSupplyChainError, match="cannot load"):
        guarded_fsharp()


@pytest.mark.parametrize("code", [401, 403, 503])
def test_fsharp_does_not_retry_nonabsence_service_responses(
    guarded_fsharp, monkeypatch, code
):
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("Unexpected retry"))

    def reject(url):
        raise urllib.error.HTTPError(url, code, "fixture response", {}, None)

    monkeypatch.setattr(publisher, "_http", reject)
    with pytest.raises(urllib.error.HTTPError) as caught:
        guarded_fsharp()
    assert caught.value.code == code


def test_fsharp_absence_deadline_never_admits_upload(guarded_fsharp, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, 1801))

    def absent(url):
        raise urllib.error.HTTPError(url, 404, "not indexed", {}, None)

    monkeypatch.setattr(publisher, "_http", absent)
    with pytest.raises(ReleaseSupplyChainError, match="F# was not uploaded"):
        guarded_fsharp()


def test_fsharp_validation_finishing_after_deadline_never_admits_upload(
    guarded_fsharp, monkeypatch
):
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(publisher, "_http", lambda url: b"fixture package")

    def late_validation(payload, sbom):
        clock[0] = 1801
        return {"fixture_only": True}

    monkeypatch.setattr(publisher, "verify_nuget_registry_payload", late_validation)
    with pytest.raises(ReleaseSupplyChainError, match="F# was not uploaded"):
        guarded_fsharp()
