"""Closed evidence is immutable history and cannot grant current release authority."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tooling import closed_certification_integrity as closed


@pytest.fixture
def packaging():
    subject = closed.registered_subject("packaging")
    files = closed.bundle_bytes(closed.ROOT, subject)
    policy = json.loads(
        closed.git(
            closed.ROOT,
            "show",
            subject["original_verifier_sha"] + ":" + subject["trust_policy"],
        )
    )
    return subject, files, policy


@pytest.mark.parametrize(
    "identity", ["compiler", "packaging", "public-verification", "final-candidate"]
)
def test_exact_closed_certificates_have_no_current_authority(identity):
    result = closed.verify(closed.ROOT, identity)
    assert result["status"] == "preserved-historical-certification"
    assert result["evidence_files"] > 0
    assert result["current_release_certification"] is False
    assert result["waiver_renewed"] is False
    assert result["publication_authorized"] is False


@pytest.mark.parametrize("identity", ["current", "release", "new-certificate"])
def test_unregistered_source_cannot_be_certified(identity):
    with pytest.raises(ValueError, match="unregistered"):
        closed.verify(closed.ROOT, identity)


def test_changed_certificate_bytes_rejected(packaging):
    subject, files, policy = packaging
    files["attestation.json"] += b"\n"
    with pytest.raises(ValueError, match="exact previously accepted"):
        closed.verify_snapshot(subject, files, policy)


@pytest.mark.parametrize("change", ["missing", "changed", "additional"])
def test_incomplete_or_substituted_producer_inventory_rejected(packaging, change):
    subject, files, policy = packaging
    path = next(path for path in files if path != "attestation.json")
    if change == "missing":
        del files[path]
    elif change == "changed":
        files[path] += b"substituted"
    else:
        files["evidence/unsigned/extra.json"] = b"{}"
    with pytest.raises(ValueError, match="evidence|additional"):
        closed.verify_snapshot(subject, files, policy)


def test_different_source_identity_rejected(packaging):
    subject, files, policy = packaging
    subject["certified_source_sha"] = "1" * 40
    with pytest.raises(ValueError, match="source identity"):
        closed.verify_snapshot(subject, files, policy)


def test_different_expected_evidence_root_rejected(packaging):
    subject, files, policy = packaging
    subject["evidence_root_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="signed evidence root"):
        closed.verify_snapshot(subject, files, policy)


def test_forged_signature_rejected_even_with_updated_container_digests(packaging):
    subject, files, policy = packaging
    document = json.loads(files["attestation.json"])
    signature = bytearray(base64.b64decode(document["signature"]["signature_base64"]))
    signature[-35] ^= 1
    document["signature"]["signature_base64"] = base64.b64encode(signature).decode()
    document["signature"]["signature_sha256"] = hashlib.sha256(signature).hexdigest()
    files["attestation.json"] = json.dumps(document).encode()
    subject["attestation_sha256"] = hashlib.sha256(
        files["attestation.json"]
    ).hexdigest()
    with pytest.raises(closed.attestation.AttestationError):
        closed.verify_snapshot(subject, files, policy)


def test_changed_signature_namespace_rejected(packaging):
    subject, files, policy = packaging
    policy["signature_namespace"] = "untrusted-context"
    with pytest.raises(ValueError, match="signature authority"):
        closed.verify_snapshot(subject, files, policy)


def test_duplicate_registry_subject_rejected(tmp_path, monkeypatch):
    data = json.loads(closed.REGISTRY.read_bytes())
    data["subjects"].append(copy.deepcopy(data["subjects"][0]))
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(closed, "REGISTRY", path)
    with pytest.raises(ValueError, match="duplicate"):
        closed.registered_subject("compiler")


@pytest.mark.parametrize(
    "field", ["current_certification_authority", "publication_authority"]
)
def test_registry_cannot_expand_into_current_authority(tmp_path, monkeypatch, field):
    data = json.loads(closed.REGISTRY.read_bytes())
    data[field] = True
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(closed, "REGISTRY", path)
    with pytest.raises(ValueError, match="preservation authority"):
        closed.registered_subject("compiler")


def test_linked_bundle_object_rejected(monkeypatch):
    subject = closed.registered_subject("packaging")

    def git(_repository, *arguments, **_kwargs):
        if arguments[0] == "rev-parse":
            return (subject["bundle_tree"] + "\n").encode()
        return (
            "120000 blob " + "1" * 40 + "\t" + subject["bundle_path"] + "/link\0"
        ).encode()

    monkeypatch.setattr(closed, "git", git)
    with pytest.raises(ValueError, match="linked or non-file"):
        closed.bundle_bytes(Path("unused"), subject)


def test_wrong_bundle_tree_rejected(monkeypatch):
    subject = closed.registered_subject("packaging")
    monkeypatch.setattr(closed, "git", lambda *_args, **_kwargs: b"incorrect\n")
    with pytest.raises(ValueError, match="bundle tree"):
        closed.bundle_bytes(Path("unused"), subject)
