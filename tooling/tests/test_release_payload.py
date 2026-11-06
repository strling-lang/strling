from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile

import pytest

from tooling.interop_wasm import attach_product_identity
from tooling.tests.test_interop_wasm import governed_exports, module_with
from tooling.release_payload import archive_files, inspect_payload, native_identity
from tooling.release_payload import unique_yaml


@pytest.mark.parametrize(
    "content",
    [
        b"name: strling\nname: substitute\n",
        b"version: 4.0.0\nversion: 3.0.0\n",
        b"[not, a, package]",
    ],
)
def test_pub_metadata_rejects_duplicate_keys_and_non_mapping(content):
    with pytest.raises(ValueError):
        unique_yaml(content)


def write_zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            entry = zipfile.ZipInfo(name)
            # Preserve deliberately unsafe bytes even on Windows, where the
            # ordinary ZipInfo constructor normalizes its filename immediately.
            entry.filename = name
            archive.writestr(entry, payload)


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "a/../b", "a\\b", "C:/path", "a//b"]
)
def test_archive_rejects_unsafe_members(tmp_path, name):
    path = tmp_path / "unsafe.zip"
    write_zip(path, {name: b"payload"})
    with pytest.raises(ValueError, match="unsafe"):
        archive_files(path)


def test_archive_rejects_duplicate_members(tmp_path):
    path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload", b"first")
        with pytest.warns(UserWarning):
            archive.writestr("payload", b"second")
    with pytest.raises(ValueError, match="duplicate"):
        archive_files(path)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_archive_rejects_links_and_special_members(tmp_path, kind):
    path = tmp_path / "unsafe.tar"
    with tarfile.open(path, "w") as archive:
        entry = tarfile.TarInfo("member")
        entry.type, entry.linkname = kind, "outside"
        archive.addfile(entry)
    with pytest.raises(ValueError, match="special"):
        archive_files(path)


def test_native_identity_checks_product_format_and_architecture():
    elf = (
        b"\x7fELF\x02\x01"
        + b"\0" * 12
        + b"\x3e\0"
        + b"\0STRLING-PRODUCT-VERSION:4.0.0\0"
    )
    assert native_identity(elf, "4.0.0") == "linux-x86_64"
    for invalid in (
        elf.replace(b"4.0.0", b"3.0.0"),
        elf + elf,
        elf.replace(b"\x3e\0", b"\xb7\0"),
        b"plain-text" + elf[20:],
    ):
        with pytest.raises(ValueError):
            native_identity(invalid, "4.0.0")


def npm_files():
    return {
        "package/package.json": json.dumps(
            {
                "name": "@strling-lang/strling",
                "version": "4.0.0",
                "license": "Apache-2.0",
            }
        ).encode(),
        "package/dist/strling_interop.wasm": attach_product_identity(
            module_with(governed_exports()), "4.0.0"
        ),
        "package/dist/index.js": b"export {};",
        "package/dist/index.d.ts": b"export {};",
        "package/dist/node.js": b"export {};",
        "package/dist/node.d.ts": b"export {};",
        "package/LICENSE": b"Apache License, Version 2.0",
    }


def inspect_npm(tmp_path, files):
    path = tmp_path / "package.tgz"
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return inspect_payload(
        tmp_path,
        {
            "id": "release:typescript",
            "package_name": "@strling-lang/strling",
            "artifact_policy": {"subject_kind": "file"},
            "payload_contract": {"required_file_groups": [["*!/package/LICENSE"]]},
        },
        "4.0.0",
        [{"name": path.name}],
    )


def test_package_graph_contains_actual_inner_file_hashes(tmp_path):
    files = npm_files()
    graph = inspect_npm(tmp_path, files)
    assert len(graph) == len(files)
    assert {row["name"].split("!/", 1)[1]: row["sha256"] for row in graph} == {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }


@pytest.mark.parametrize(
    "missing",
    ["package/dist/strling_interop.wasm", "package/dist/index.d.ts", "package/LICENSE"],
)
def test_package_rejects_missing_payload_and_license(tmp_path, missing):
    files = npm_files()
    del files[missing]
    with pytest.raises(ValueError):
        inspect_npm(tmp_path, files)


def test_package_rejects_wrong_coordinate_and_product(tmp_path):
    files = npm_files()
    files["package/package.json"] = (
        b'{"name":"wrong","version":"4.0.0","license":"Apache-2.0"}'
    )
    with pytest.raises(ValueError, match="coordinate"):
        inspect_npm(tmp_path, files)
    files = npm_files()
    files["package/dist/strling_interop.wasm"] = files[
        "package/dist/strling_interop.wasm"
    ].replace(b"4.0.0", b"3.0.0")
    with pytest.raises(ValueError, match="identity"):
        inspect_npm(tmp_path, files)


def test_spdx_verification_code_covers_actual_inner_file_bytes(tmp_path):
    from tooling.release_supply_chain import _spdx_document, _validate_spdx

    files = npm_files()
    graph = inspect_npm(tmp_path, files)
    document = _spdx_document(
        {
            "id": "release:typescript",
            "surface": "typescript",
            "package_name": "@strling-lang/strling",
        },
        [],
        "a" * 64,
        [],
        "4.0.0",
        graph,
    )
    _validate_spdx(document)
    sha1s = sorted(
        hashlib.sha1(data, usedforsecurity=False).hexdigest() for data in files.values()
    )
    expected = hashlib.sha1("".join(sha1s).encode(), usedforsecurity=False).hexdigest()
    assert document["packages"][0]["filesAnalyzed"] is True
    assert document["packages"][0]["packageVerificationCode"] == {
        "packageVerificationCodeValue": expected
    }
    assert all(row["licenseConcluded"] == "NOASSERTION" for row in document["files"])
    assert document["packages"][0]["licenseDeclared"] == "Apache-2.0"
    for row in document["files"]:
        assert row["checksums"][1]["algorithm"] == "SHA1"


def test_crate_rejects_stale_rust_minimum_before_consumer_execution(tmp_path):
    path = tmp_path / "strling-4.0.0.crate"
    data = b'[package]\nname="strling"\nversion="4.0.0"\nrust-version="1.70"\nlicense="Apache-2.0"\n'
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("strling-4.0.0/Cargo.toml")
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    with pytest.raises(ValueError, match="runtime metadata"):
        inspect_payload(
            tmp_path,
            {"id": "release:rust", "artifact_policy": {"subject_kind": "archive"}},
            "4.0.0",
            [{"name": path.name}],
        )
