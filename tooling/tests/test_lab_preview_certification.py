import json
import sys

import pytest

from tooling import lab_preview_certification as preview


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    entry = preview.admission(preview.ROOT)
    asset = inputs / entry["reserved_destination"]["asset"]
    asset.write_bytes(b"test artifact")
    entry["artifact"] = {"bytes": asset.stat().st_size, "sha256": preview.sha256(asset)}
    receipt = {
        field: entry[field]
        for field in (
            "source_revision",
            "source_tree",
            "source_archive_sha256",
            "cargo_lock_sha256",
            "target",
        )
    }
    for name in preview.RECEIPTS:
        receipt_path = inputs / name
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    entry["rebuild_receipt_sha256"] = preview.sha256(receipt_path)
    sbom = inputs / "draft-sbom.spdx.json"
    sbom.write_text("{}", encoding="utf-8")
    entry["draft_spdx_sha256"] = preview.sha256(sbom)
    monkeypatch.setattr(preview, "_validate_spdx", lambda document: None)
    return inputs, entry


@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("strling_lab_wasm.wasm", "admitted bytes"),
        ("rebuild-2-receipt.json", "independently reproduced receipt"),
        ("draft-sbom.spdx.json", "admitted artifact inventory"),
        ("SHA256SUMS", "checksum file"),
    ],
)
def test_prepared_package_rejects_changed_evidence(candidate, tmp_path, path, error):
    inputs, entry = candidate
    destination = tmp_path / "package"
    preview.prepare(inputs, destination, entry)
    (destination / path).write_bytes(b"changed evidence")
    with pytest.raises(ValueError, match=error):
        preview.verify_package(destination, entry)


def test_prepared_package_rejects_changed_source(candidate, tmp_path):
    inputs, entry = candidate
    destination = tmp_path / "package"
    preview.prepare(inputs, destination, entry)
    provenance = preview.read_json(destination / "unsigned-provenance.json")
    provenance["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"] = {
        "gitCommit": "a" * 40
    }
    (destination / "unsigned-provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="source-bound provenance"):
        preview.verify_package(destination, entry)


def test_preparation_cannot_report_profile_success(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["lab_preview", "--qualify", "--prepare", "preview"]
    )
    with pytest.raises(SystemExit) as error:
        preview.main()
    assert error.value.code == 2
