"""Exercise the staged producer against the independent CPAN decoder."""

import hashlib
import json
from pathlib import Path

import pytest

from tooling import public_fixtures
from tooling.public_registries import retrieve
from tooling.public_retrieval import RetrievalError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads(
    (ROOT / "tests/certification/release-supply-chain/1.0/manifest.json").read_text()
)
ARTIFACT = next(a for a in MANIFEST["artifacts"] if a["id"] == "release:perl")
SOURCE = "a" * 40
PAYLOAD = b"synthetic CPAN fixture payload; never a public release"


def staged_fixture(tmp_path, monkeypatch, version):
    subject = f"bindings/perl/STRling-{version}.tar.gz"
    subjects = {subject: hashlib.sha256(PAYLOAD).hexdigest()}
    monkeypatch.setattr(public_fixtures, "subject_checksums", lambda *_: subjects)
    package = tmp_path / "staged" / subject
    package.parent.mkdir(parents=True)
    package.write_bytes(PAYLOAD)
    for kind, suffix in (("sbom", ".spdx.json"), ("provenance", ".intoto.json")):
        sidecar = tmp_path / kind / ("perl" + suffix)
        sidecar.parent.mkdir()
        sidecar.write_bytes(b"{}")
    transport, destination, _ = public_fixtures.protocol_fixture(
        artifact=ARTIFACT,
        evidence=tmp_path / "release-supply-chain-evidence.json",
        staged=tmp_path / "staged",
        source=ROOT,
        source_sha=SOURCE,
        source_tree="b" * 40,
        version=version,
    )
    url = f"https://fastapi.metacpan.org/v1/release/STRLING/STRling-{version}"
    return transport, subjects, destination, url


@pytest.mark.parametrize("version", ["4.0.0", "4.0.1", "4.0.1-rc.1"])
def test_staged_cpan_fixture_matches_real_metadata_normalization(
    tmp_path, monkeypatch, version
):
    transport, subjects, destination, url = staged_fixture(
        tmp_path, monkeypatch, version
    )
    metadata = json.loads(transport.responses[url])["release"]
    assert metadata["version"] == "v" + version.partition("-rc.")[0]
    assert metadata["download_url"].endswith(f"/STRling-{version}.tar.gz")
    result = retrieve(
        transport, ARTIFACT, version, subjects, destination, source_sha=SOURCE
    )
    assert result["files"] == {next(iter(subjects)): PAYLOAD}
    assert transport.authority == "synthetic"


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "4.0.1"),
        ("version", "v4.0.2"),
        ("author", "OTHER"),
        (
            "download_url",
            "https://cpan.metacpan.org/authors/id/S/ST/STRLING/STRling-4.0.1.tar.gz",
        ),
    ],
)
def test_staged_cpan_fixture_still_rejects_substituted_prerelease_metadata(
    tmp_path, monkeypatch, field, value
):
    version = "4.0.1-rc.1"
    transport, subjects, destination, url = staged_fixture(
        tmp_path, monkeypatch, version
    )
    document = json.loads(transport.responses[url])
    document["release"][field] = value
    transport.responses[url] = json.dumps(document).encode()
    with pytest.raises(RetrievalError):
        retrieve(transport, ARTIFACT, version, subjects, destination, source_sha=SOURCE)
    assert [row["request_url"] for row in transport.observations] == [url]
