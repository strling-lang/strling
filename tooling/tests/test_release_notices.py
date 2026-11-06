import hashlib
import io
import tarfile

import pytest

from tooling.release_notices import notices


def source_fixture(tmp_path, *, license_payload=b"Fixture license text", unsafe=False):
    root, cache = tmp_path / "source", tmp_path / "cargo"
    interop = root / "bindings/interop"
    interop.mkdir(parents=True)
    (interop / "Cargo.toml").write_text(
        '[package]\nname="strling-interop"\nversion="0.1.0"\n'
    )
    crate = cache / "registry/cache/index/runtime-1.2.3.crate"
    crate.parent.mkdir(parents=True)
    with tarfile.open(crate, "w:gz") as archive:
        if license_payload is not None:
            info = tarfile.TarInfo("runtime-1.2.3/LICENSE")
            info.size = len(license_payload)
            archive.addfile(info, io.BytesIO(license_payload))
        if unsafe:
            info = tarfile.TarInfo("../outside")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    checksum = hashlib.sha256(crate.read_bytes()).hexdigest()
    (interop / "Cargo.lock").write_text(
        '''version = 3
[[package]]
name="strling-interop"
version="0.1.0"
dependencies=["runtime"]
[[package]]
name="runtime"
version="1.2.3"
source="registry+https://github.com/rust-lang/crates.io-index"
checksum="'''
        + checksum
        + '''"
[[package]]
name="independent-fuzz-only"
version="0.0.0"
source="registry+https://github.com/rust-lang/crates.io-index"
checksum="'''
        + "0" * 64
        + """"
"""
    )
    return root, cache, crate


def test_notices_are_deterministic_and_exclude_unreachable_fuzz_dependencies(tmp_path):
    root, cache, _ = source_fixture(tmp_path)
    first, second = notices(root, cache), notices(root, cache)
    assert first == second
    assert "Fixture license text" in first
    assert "runtime 1.2.3" in first
    assert "independent-fuzz-only" not in first
    assert str(cache) not in first


def test_unverified_dependency_archive_is_rejected(tmp_path):
    root, cache, crate = source_fixture(tmp_path)
    crate.write_bytes(crate.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum-verified"):
        notices(root, cache)


def test_upstream_notice_line_endings_survive_a_git_text_checkout(tmp_path):
    root, cache, _ = source_fixture(
        tmp_path, license_payload=b"First line\r\nSecond line\rThird line\n"
    )
    expected = notices(root, cache)
    assert "First line\nSecond line\nThird line" in expected
    assert "\r" not in expected
    assert expected.endswith("\n") and not expected.endswith("\n\n")
    output = root / "notices.txt"
    output.write_text(expected, encoding="utf-8", newline="\n")
    assert output.read_text(encoding="utf-8") == expected


def test_missing_notices_are_rejected(tmp_path):
    root, cache, _ = source_fixture(tmp_path, license_payload=None)
    with pytest.raises(ValueError, match="notice"):
        notices(root, cache)


def test_unsafe_upstream_paths_are_rejected_without_extraction(tmp_path):
    root, cache, _ = source_fixture(tmp_path, unsafe=True)
    with pytest.raises(ValueError, match="unsafe"):
        notices(root, cache)
    assert not (tmp_path / "outside").exists()
