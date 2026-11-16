"""Asynchronous Central delivery must precede Kotlin signing and submission."""

import hashlib
import json
import time
import urllib.error

import pytest

from tooling import maven_release
from tooling import publish_certified_artifact as publisher
from tooling.release_supply_chain import ReleaseSupplyChainError


VERSION = "4.0.1"
POM_NAME = "bindings/jvm/pom.xml"
JAR_NAME = "bindings/jvm/target/strling-jvm-4.0.1.jar"
POM = b"fixture certified primary bridge POM"
JAR = b"fixture certified primary bridge binary"
EXPECTED = {
    POM_NAME: hashlib.sha256(POM).hexdigest(),
    JAR_NAME: hashlib.sha256(JAR).hexdigest(),
}


def test_kotlin_waits_for_exact_primary_companion_before_signing_or_upload(
    tmp_path, monkeypatch
):
    events = []
    pom_reads = 0
    for name in ["GPG_PRIVATE_KEY", "SONATYPE_USERNAME", "SONATYPE_PASSWORD"]:
        monkeypatch.setenv(name, "fixture-only-no-publishing-access")
    monkeypatch.setattr(publisher, "_require_absent", lambda url: None)
    monkeypatch.setattr(publisher, "_companion_checksums", lambda path, name: EXPECTED)
    monkeypatch.setattr(maven_release, "central_files", lambda *args: {})
    monkeypatch.setattr(time, "sleep", lambda seconds: events.append("wait"))

    def http(url, **kwargs):
        nonlocal pom_reads
        if kwargs.get("method") == "POST":
            assert events[-1] == "sign"
            events.append("submit-kotlin-once")
            return b"11111111-2222-3333-4444-555555555555"
        if url.endswith(".pom"):
            pom_reads += 1
            events.append("read-pom")
            if pom_reads == 1:
                raise urllib.error.HTTPError(url, 404, "not propagated yet", {}, None)
            return POM
        assert url.endswith(".jar")
        events.append("read-jar")
        return JAR

    def sign(*args):
        assert pom_reads == 2 and "read-jar" in events
        events.append("sign")
        return b"fixture signed envelope", "a" * 64

    monkeypatch.setattr(publisher, "_http", http)
    monkeypatch.setattr(maven_release, "signed_envelope", sign)
    authorization = {
        "destinations": [
            {"artifact_id": "release:" + name, "signing_key_fingerprint": "F" * 40}
            for name in ["java", "kotlin"]
        ]
    }
    result = publisher.upload(
        tmp_path,
        {"id": "release:kotlin", "delivery_kind": "package"},
        VERSION,
        "a" * 40,
        [],
        authorization=authorization,
        verified_evidence=tmp_path / "fixture-authenticated-evidence",
    )
    assert json.loads(result)["deployment_id"] == "11111111-2222-3333-4444-555555555555"
    assert events == [
        "read-pom",
        "read-jar",
        "wait",
        "read-pom",
        "sign",
        "submit-kotlin-once",
    ]


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503])
def test_companion_wait_does_not_reinterpret_authentication_or_service_errors(
    monkeypatch, code
):
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("Unexpected retry"))

    def unavailable(url, **kwargs):
        assert not kwargs, "Public companion requests must not carry credentials"
        raise urllib.error.HTTPError(url, code, "fixture service response", {}, None)

    monkeypatch.setattr(publisher, "_http", unavailable)
    with pytest.raises(urllib.error.HTTPError) as caught:
        publisher._wait_for_jvm_companion(VERSION, EXPECTED)
    assert caught.value.code == code


@pytest.mark.parametrize("extension", ["pom", "jar"])
def test_companion_wait_rejects_substituted_bytes_without_retry(monkeypatch, extension):
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("Unexpected retry"))

    def retrieve(url):
        if url.endswith("." + extension):
            return b"substituted companion"
        return POM if url.endswith(".pom") else JAR

    monkeypatch.setattr(publisher, "_http", retrieve)
    with pytest.raises(ReleaseSupplyChainError, match="differs"):
        publisher._wait_for_jvm_companion(VERSION, EXPECTED)


@pytest.mark.parametrize("name", [POM_NAME, JAR_NAME])
@pytest.mark.parametrize("value", [None, "", "F" * 64, "invalid", 123])
def test_companion_wait_requires_exact_signed_evidence_before_network(
    monkeypatch, name, value
):
    expected = dict(EXPECTED)
    expected[name] = value
    monkeypatch.setattr(
        publisher, "_http", lambda url: pytest.fail("Unqualified request")
    )
    with pytest.raises(ReleaseSupplyChainError, match="checksums are invalid"):
        publisher._wait_for_jvm_companion(VERSION, expected)


def test_companion_wait_bounds_absence_without_retrying_any_upload(monkeypatch):
    clock = [0.0]
    requests = []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    def absent(url, **kwargs):
        assert not kwargs
        requests.append(url)
        raise urllib.error.HTTPError(url, 404, "fixture propagation delay", {}, None)

    monkeypatch.setattr(publisher, "_http", absent)
    with pytest.raises(ReleaseSupplyChainError, match="Kotlin was not uploaded"):
        publisher._wait_for_jvm_companion(
            VERSION, EXPECTED, timeout_seconds=2, poll_interval_seconds=1
        )
    assert clock[0] == 2
    assert 2 <= len(requests) <= 6


def test_companion_response_after_deadline_cannot_admit_kotlin(monkeypatch):
    clock = [0.0]
    requests = []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("Unexpected retry"))

    def late(url):
        requests.append(url)
        clock[0] = 3
        return POM

    monkeypatch.setattr(publisher, "_http", late)
    with pytest.raises(ReleaseSupplyChainError, match="deadline exceeded"):
        publisher._wait_for_jvm_companion(VERSION, EXPECTED, timeout_seconds=2)
    assert len(requests) == 1


@pytest.mark.parametrize("duration", [0, -1, 1801, float("inf"), float("nan")])
def test_companion_wait_cannot_exceed_the_fixed_bound(monkeypatch, duration):
    monkeypatch.setattr(
        publisher, "_http", lambda url: pytest.fail("Unbounded request")
    )
    with pytest.raises(ReleaseSupplyChainError):
        publisher._wait_for_jvm_companion(VERSION, EXPECTED, timeout_seconds=duration)
