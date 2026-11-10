"""Trust, network, and request mutations for independent public verification."""

import hashlib
import io
import json
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

from tooling.public_distribution import CONTRACT, obligations
from tooling.public_retrieval import PublicTransport, RetrievalError
from tooling.public_verification_request import validate_request
from tooling.release_supply_chain import canonical_json, document_fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_dns_resolution_has_bounded_isolated_process(monkeypatch):
    from tooling.public_retrieval import resolve_addresses

    runner = Mock(side_effect=subprocess.TimeoutExpired("resolver", 2))
    monkeypatch.setattr("tooling.public_retrieval.subprocess.run", runner)
    monkeypatch.setenv("PUBLICATION_TOKEN", "must-not-inherit")
    with pytest.raises(TimeoutError, match="DNS deadline"):
        resolve_addresses("registry.example", 443, 2)
    assert runner.call_args.kwargs["timeout"] == 2
    assert runner.call_args.args[0][1] == "-I"
    assert "PUBLICATION_TOKEN" not in runner.call_args.kwargs["env"]


def request_fixture():
    manifest = json.loads(
        (
            ROOT / "tests/certification/release-supply-chain/1.0/manifest.json"
        ).read_text()
    )
    authentication = {
        "certified_source_sha": "a" * 40,
        "closure_source_sha": "b" * 40,
        "signed_evidence_root": "c" * 64,
    }
    request = {
        "contract": CONTRACT,
        "version": "4.0.0",
        "channel": "stable",
        **authentication,
        "manifest_fingerprint": document_fingerprint(manifest),
        "destinations": [
            {
                "artifact_id": a["id"],
                "registry": a["registry"],
                "package_name": a["package_name"],
                "registry_owner": "fixture",
                "tier": a["distribution_contract"]["tier"],
                **(
                    {"registry_endpoint": "https://conan.example.test"}
                    if a["registry"] == "conan"
                    else {}
                ),
            }
            for a in manifest["artifacts"]
        ],
        "documents": [
            {
                "artifact_id": a["id"],
                **{
                    kind: {
                        "url": "https://evidence.example.test/" + kind,
                        "sha256": "d" * 64,
                    }
                    for kind in ("sbom", "provenance", "documentation")
                },
            }
            for a in manifest["artifacts"]
        ],
        "publication_receipts": [
            {"artifact_id": a["id"], "receipt": None} for a in manifest["artifacts"]
        ],
        "obligations": obligations(manifest),
        "lifecycle_state": "certified",
        "authority": "synthetic",
    }
    authentication["product_version"] = "4.0.0"
    return request, manifest, authentication


def validate(request, manifest, authentication):
    return validate_request(
        request,
        expected_sha256=hashlib.sha256(canonical_json(request)).hexdigest(),
        manifest=manifest,
        authentication=authentication,
        authority=request["authority"],
    )


def test_complete_synthetic_request_does_not_authorize_publication():
    assert validate(*request_fixture())["publication_authorized"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "http://conan.example.test",
        "https://" + "user:secret" + "@conan.example.test",
        "https://conan.example.test?token=x",
    ],
)
def test_request_requires_exact_conan_endpoint(endpoint):
    request, manifest, authentication = request_fixture()
    destination = next(
        row for row in request["destinations"] if row["registry"] == "conan"
    )
    if endpoint is None:
        destination.pop("registry_endpoint")
    else:
        destination["registry_endpoint"] = endpoint
    with pytest.raises(RetrievalError):
        validate(request, manifest, authentication)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "channel",
        "source",
        "closure",
        "signature-root",
        "manifest",
        "missing-destination",
        "duplicate-destination",
        "wrong-registry",
        "wrong-package",
        "promote-preview",
        "missing-document",
        "missing-receipt",
        "missing-obligation",
        "duplicate-obligation",
        "lifecycle",
        "extra-command",
        "document-credentials",
        "document-insecure",
    ],
)
def test_request_rejects_mutated_authority(mutation):
    request, manifest, authentication = request_fixture()
    if mutation == "version":
        request["version"] = "3.0.0"
    elif mutation == "channel":
        request["channel"] = "release-candidate"
    elif mutation == "source":
        request["certified_source_sha"] = "e" * 40
    elif mutation == "closure":
        request["closure_source_sha"] = "e" * 40
    elif mutation == "signature-root":
        request["signed_evidence_root"] = "e" * 64
    elif mutation == "manifest":
        request["manifest_fingerprint"] = "e" * 64
    elif mutation == "missing-destination":
        request["destinations"].pop()
    elif mutation == "duplicate-destination":
        request["destinations"].append(request["destinations"][0])
    elif mutation == "wrong-registry":
        request["destinations"][0]["registry"] = "alternate"
    elif mutation == "wrong-package":
        request["destinations"][0]["package_name"] = "substituted"
    elif mutation == "promote-preview":
        next(row for row in request["destinations"] if row["tier"] == "Preview")[
            "tier"
        ] = "Supported"
    elif mutation == "missing-document":
        request["documents"][0].pop("sbom")
    elif mutation == "missing-receipt":
        request["publication_receipts"].pop()
    elif mutation == "missing-obligation":
        request["obligations"].pop()
    elif mutation == "duplicate-obligation":
        request["obligations"].append(request["obligations"][0])
    elif mutation == "lifecycle":
        request["lifecycle_state"] = "published"
    elif mutation == "extra-command":
        request["command"] = "publish"
    elif mutation == "document-credentials":
        request["documents"][0]["sbom"]["url"] = (
            "https://" + "user:secret" + "@example.test/a"
        )
    elif mutation == "document-insecure":
        request["documents"][0]["sbom"]["url"] = "http://example.test/a"
    with pytest.raises(RetrievalError):
        validate(request, manifest, authentication)


def test_protected_digest_cannot_be_supplied_by_candidate():
    request, manifest, authentication = request_fixture()
    with pytest.raises(RetrievalError, match="protected"):
        validate_request(
            request,
            expected_sha256="0" * 64,
            manifest=manifest,
            authentication=authentication,
            authority="synthetic",
        )


def test_real_public_request_cannot_use_pending_registry_ownership():
    request, manifest, authentication = request_fixture()
    request.update(authority="public", lifecycle_state="published")
    with pytest.raises(RetrievalError, match="ownership"):
        validate(request, manifest, authentication)


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Length": str(len(data))}


def transport(tmp_path, monkeypatch, sequence):
    monkeypatch.setattr(
        "tooling.public_retrieval.public_url", lambda url, origins, **kwargs: url
    )
    monkeypatch.setattr("tooling.public_retrieval.time.sleep", lambda _: None)
    client = PublicTransport(
        tmp_path / "observations", {"https://registry.example.test"}
    )
    client.opener = Mock()
    client.opener.open.side_effect = sequence
    return client


def error(code, headers=None):
    return urllib.error.HTTPError(
        "https://registry.example.test/package", code, "fixture", headers or {}, None
    )


def test_transport_retains_exact_bytes_and_response_identity(tmp_path, monkeypatch):
    client = transport(tmp_path, monkeypatch, [Response(b"exact bytes")])
    assert client.get("https://registry.example.test/package") == b"exact bytes"
    assert (client.output / "00000.body").read_bytes() == b"exact bytes"
    request = client.opener.open.call_args.args[0]
    assert request.get_method() == "GET"
    assert not any(
        key.lower() in {"authorization", "cookie"} for key in request.headers
    )


def test_404_is_absence_without_retry(tmp_path, monkeypatch):
    client = transport(tmp_path, monkeypatch, [error(404)])
    with pytest.raises(RetrievalError) as failure:
        client.get("https://registry.example.test/package")
    assert failure.value.status == "NOT_PUBLISHED"
    assert client.opener.open.call_count == 1
    assert client.observations[0]["http_status"] == 404


def test_transient_failure_retries_and_preserves_each_attempt(tmp_path, monkeypatch):
    client = transport(tmp_path, monkeypatch, [error(503), error(429), Response(b"ok")])
    assert client.get("https://registry.example.test/package") == b"ok"
    assert [row["http_status"] for row in client.observations] == [503, 429, 200]


def test_timeout_never_becomes_absence(tmp_path, monkeypatch):
    client = transport(tmp_path, monkeypatch, [TimeoutError()] * 3)
    with pytest.raises(RetrievalError) as failure:
        client.get("https://registry.example.test/package")
    assert failure.value.status == "INDETERMINATE"
    assert len(client.observations) == 3


def test_truncated_response_cannot_pass(tmp_path, monkeypatch):
    client = transport(
        tmp_path, monkeypatch, [Response(b"partial", {"Content-Length": "100"})]
    )
    with pytest.raises(RetrievalError) as failure:
        client.get("https://registry.example.test/package")
    assert failure.value.status == "INDETERMINATE"
    assert client.observations[0]["error_kind"] == "truncated-response"


def test_redirect_is_revalidated_before_following(tmp_path, monkeypatch):
    client = transport(
        tmp_path,
        monkeypatch,
        [error(302, {"Location": "https://untrusted.example/evil"})],
    )

    def check(url, origins, **kwargs):
        if url.startswith("https://untrusted"):
            raise RetrievalError("security", "unapproved redirect")
        return url

    monkeypatch.setattr("tooling.public_retrieval.public_url", check)
    with pytest.raises(RetrievalError, match="redirect"):
        client.get("https://registry.example.test/package")
    assert client.opener.open.call_count == 1
