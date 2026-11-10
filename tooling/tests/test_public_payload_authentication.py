"""Archive equivalence and public companion evidence must retain exact authority."""

import hashlib
import io
import json
import tarfile
import tempfile
import zipfile
from unittest.mock import Mock

import pytest

from tooling.public_distribution import (
    authenticate_archive,
    authenticate_source_archive,
)
from tooling.public_retrieval import FixtureTransport, RetrievalError
from tooling.public_verification import verify_associations
from tooling.release_supply_chain import ReleaseSupplyChainError, canonical_json


def sbom_file(name, data):
    return {
        "fileName": name,
        "checksums": [
            {"algorithm": "SHA256", "checksumValue": hashlib.sha256(data).hexdigest()}
        ],
    }


def zip_bytes(year=2020, mode=0o100644, data=b"certified", comment=b""):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("package/data", (year, 1, 1, 0, 0, 0))
        info.external_attr = mode << 16
        archive.writestr(info, data)
        archive.comment = comment
    return stream.getvalue()


def compare(payload, exemplar, *, allowed=True):
    return authenticate_archive(
        payload,
        subject="package.zip",
        expected_sha256=hashlib.sha256(exemplar).hexdigest(),
        certified_payload=exemplar,
        artifact={
            "reproducibility": {
                "mode": "normalized" if allowed else "byte-for-byte",
                "allowed_normalizations": ["archive-entry-timestamp"]
                if allowed
                else [],
            }
        },
        sbom={"files": [sbom_file("package.zip!/package/data", b"certified")]},
    )


def test_only_registered_archive_timestamp_equivalence_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert compare(zip_bytes(2021), zip_bytes())["comparison"] == "normalized"
    with pytest.raises(RetrievalError):
        compare(zip_bytes(2021), zip_bytes(), allowed=False)


@pytest.mark.parametrize("mutation", ["mode", "content", "comment"])
def test_normalization_cannot_hide_other_mutations(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    changed = {
        "mode": {"mode": 0o100755},
        "content": {"data": b"substituted"},
        "comment": {"comment": b"undeclared"},
    }[mutation]
    with pytest.raises(RetrievalError):
        compare(zip_bytes(**changed), zip_bytes())


def source_archive(name, data=b"certified"):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    return stream.getvalue()


@pytest.mark.parametrize(
    "mutation", ["tree", "source", "root", "missing-sbom", "duplicate-sbom"]
)
def test_git_source_authentication_rejects_substitution(mutation):
    sha, tree = "a" * 40, "b" * 40
    rows = [sbom_file("bindings/go/go.mod", b"certified")]
    payload = source_archive("strling-" + sha + "/bindings/go/go.mod")
    observed = tree
    if mutation == "tree":
        observed = "c" * 40
    elif mutation == "source":
        payload = source_archive("strling-" + sha + "/bindings/go/go.mod", b"other")
    elif mutation == "root":
        payload = source_archive("untrusted/bindings/go/go.mod")
    elif mutation == "missing-sbom":
        rows = []
    elif mutation == "duplicate-sbom":
        rows *= 2
    with pytest.raises(RetrievalError):
        authenticate_source_archive(
            payload,
            source_sha=sha,
            expected_tree=tree,
            observed_tree=observed,
            sbom={"files": rows},
            artifact={"artifact_policy": {"patterns": ["bindings/go"]}},
        )


@pytest.mark.parametrize("kind", ["sbom", "provenance", "documentation"])
def test_public_evidence_must_match_both_approved_bytes_and_signed_subject(
    tmp_path, kind
):
    source = tmp_path / "source"
    (source / "bindings/python").mkdir(parents=True)
    (source / "governance").mkdir()
    (source / "governance/release-policy.json").write_text(
        '{"product":{"version":"4.0.0"}}'
    )
    readme = b"```bash\npip install STRling==4.0.0\n```\n"
    (source / "bindings/python/README.md").write_bytes(readme)
    evidence = tmp_path / "evidence/evidence.json"
    documents, responses = {}, {}
    for name, suffix in (("sbom", ".spdx.json"), ("provenance", ".intoto.json")):
        directory = evidence.parent / name
        directory.mkdir(parents=True)
        payload = canonical_json({"certified-subject": "expected"})
        (directory / ("python" + suffix)).write_bytes(payload)
        documents[name] = {
            "url": "https://fixture.test/" + name,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        responses[documents[name]["url"]] = payload
    documents["documentation"] = {
        "url": "https://fixture.test/readme",
        "sha256": hashlib.sha256(readme).hexdigest(),
    }
    responses[documents["documentation"]["url"]] = readme
    artifact = {
        "id": "release:python",
        "registry": "pypi.org",
        "package_name": "STRling",
        "surface": "python",
        "package_root": "bindings/python",
    }
    assert verify_associations(
        FixtureTransport(responses),
        documents,
        evidence=evidence,
        artifact=artifact,
        source=source,
    )
    changed = (
        b"unrelated"
        if kind == "documentation"
        else canonical_json({"certified-subject": "wrong"})
    )
    responses[documents[kind]["url"]] = changed
    # Even approval of these bytes cannot substitute an unrelated signed subject.
    documents[kind]["sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(RetrievalError):
        verify_associations(
            FixtureTransport(responses),
            documents,
            evidence=evidence,
            artifact=artifact,
            source=source,
        )


def test_nuget_repository_verification_is_mandatory_and_credential_free(
    tmp_path, monkeypatch
):
    from tooling.nuget_signature import verify_nuget_registry_payload

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fixture-secret")
    monkeypatch.setenv("NUGET_KEY", "fixture-secret")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("data", b"certified")
        archive.writestr(".signature.p7s", b"repository-seal")
    sbom = {"files": [sbom_file("package.nupkg!/data", b"certified")]}
    fetch = Mock(
        return_value=json.dumps(
            {
                "allRepositorySigned": True,
                "signingCertificates": [
                    {"fingerprints": {"2.16.840.1.101.3.4.2.1": "a" * 64}}
                ],
            }
        ).encode()
    )
    verify = Mock()
    monkeypatch.setattr("tooling.nuget_signature.subprocess.run", verify)
    result = verify_nuget_registry_payload(stream.getvalue(), sbom, fetch=fetch)
    assert (
        result["repository_signature_sha256"]
        == hashlib.sha256(b"repository-seal").hexdigest()
    )
    assert "--all" in verify.call_args.args[0]
    assert "--certificate-fingerprint" in verify.call_args.args[0]
    assert "AWS_ACCESS_KEY_ID" not in verify.call_args.kwargs["env"]
    assert "NUGET_KEY" not in verify.call_args.kwargs["env"]
    assert verify.call_args.kwargs["timeout"] == 120
    fetch.return_value = b'{"allRepositorySigned":false,"signingCertificates":[]}'
    with pytest.raises(ReleaseSupplyChainError):
        verify_nuget_registry_payload(stream.getvalue(), sbom, fetch=fetch)


@pytest.mark.parametrize("mutation", [None, "missing", "substituted"])
def test_conan_reconstruction_preserves_restore_directories_without_payload_fallback(
    tmp_path, mutation
):
    from tooling.conan_release import materialize_upload, upload_inventory
    from tooling.public_conan import reconstruct_cache

    revision, package_id, binary_revision = "a" * 32, "b" * 40, "c" * 32
    layout = {
        "strling/4.0.0": {
            "revisions": {
                revision: {
                    "recipe_folder": "recipe",
                    "packages": {
                        package_id: {
                            "revisions": {
                                binary_revision: {
                                    "package_folder": "b/binary/p",
                                    "metadata_folder": "b/binary/d/metadata",
                                }
                            }
                        }
                    },
                }
            }
        }
    }
    payloads = {
        "pkglist.json": canonical_json(layout),
        "recipe/e/conanfile.py": b"# never execute while verifying\n",
        "recipe/e/conanmanifest.txt": b"0\n",
        "b/binary/p/conaninfo.txt": b"settings",
        "b/binary/p/conanmanifest.txt": b"0\n",
        "b/binary/p/lib/kernel.a": b"public native payload",
    }
    exemplar = tmp_path / "certified.tgz"
    with tarfile.open(exemplar, "w:gz") as archive:
        directory = tarfile.TarInfo("b/binary/d/metadata")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, data in payloads.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    upload = tmp_path / "upload.zip"
    materialize_upload(exemplar, upload, "4.0.0")
    inventory, files = upload_inventory(upload, "4.0.0")
    endpoint = "https://conan.example.test"
    base = endpoint + "/v2/conans/strling/4.0.0/_/_/revisions/" + revision
    public_files = {}
    for name, data in files.items():
        if name.startswith("recipe/"):
            url = base + "/files/" + name.removeprefix("recipe/")
        else:
            url = (
                base
                + "/packages/"
                + package_id
                + "/revisions/"
                + binary_revision
                + "/files/"
                + name.split("/")[-1]
            )
        public_files[url] = data
    binary = next(name for name in public_files if name.endswith("conan_package.tgz"))
    if mutation == "missing":
        del public_files[binary]
    elif mutation == "substituted":
        public_files[binary] = b"wrong archive"
    arguments = dict(
        exemplar=exemplar,
        expected_sha256=hashlib.sha256(exemplar.read_bytes()).hexdigest(),
        inventory=inventory,
        public_files=public_files,
        endpoint=endpoint,
        version="4.0.0",
        output=tmp_path / "retrieved.tgz",
    )
    if mutation:
        with pytest.raises(RetrievalError):
            reconstruct_cache(**arguments)
    else:
        assert reconstruct_cache(**arguments)["status"] == "passed"
        with tarfile.open(arguments["output"]) as restored:
            assert restored.getmember("b/binary/d/metadata").isdir()
            assert (
                restored.extractfile("b/binary/p/lib/kernel.a").read()
                == b"public native payload"
            )
