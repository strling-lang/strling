"""Cargo payload identity and host-independent release archive assembly."""

import gzip
import io
import tarfile

import pytest

from tooling.release_packaging import canonical_rust_archive
from tooling.release_payload import archive_files
from tooling.release_supply_chain import ReleaseSupplyChainError


FILES = {
    "strling-4.0.0/Cargo.toml": b'[package]\nname="strling"\nversion="4.0.0"\n',
    "strling-4.0.0/src/lib.rs": b'pub const VERSION: &str = "4.0.0";\n',
    "strling-4.0.0/docs/" + "long/" * 24 + "guide.md": b"# Exact source\n",
}


def source_archive(path, timestamp, *, reverse=False, mode=0o644):
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(FILES, reverse=reverse):
            row = tarfile.TarInfo(name)
            row.size = len(FILES[name])
            row.mtime = timestamp
            row.mode = mode
            archive.addfile(row, io.BytesIO(FILES[name]))


def test_canonical_crate_keeps_every_payload_byte_and_rejects_host_timestamps(tmp_path):
    outputs = []
    for index, stamp in enumerate((1153704088, 123456789)):
        source = tmp_path / f"cargo-{index}.crate"
        target = tmp_path / f"release-{index}.crate"
        source_archive(source, stamp, reverse=bool(index))
        canonical_rust_archive(source, target, version="4.0.0", epoch=1770000000)
        assert archive_files(target) == FILES
        with tarfile.open(target) as archive:
            assert archive.getnames() == sorted(FILES)
            assert {row.mtime for row in archive} == {1770000000}
        assert gzip.decompress(target.read_bytes())
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]


def test_canonical_crate_preserves_executable_mode_and_is_idempotent(tmp_path):
    source, target, repeated = [
        tmp_path / name for name in ("a.crate", "b.crate", "c.crate")
    ]
    source_archive(source, 1153704088, mode=0o755)
    canonical_rust_archive(source, target, version="4.0.0", epoch=0)
    canonical_rust_archive(target, repeated, version="4.0.0", epoch=0)
    with tarfile.open(target) as archive:
        assert {row.mode for row in archive} == {0o755}
    assert target.read_bytes() == repeated.read_bytes()


@pytest.mark.parametrize(
    "version,epoch", [("3.0.0", 0), ("4.0.0", -1), ("4.0.0", 2**32)]
)
def test_canonical_crate_rejects_wrong_product_root_or_epoch(tmp_path, version, epoch):
    source, target = tmp_path / "source.crate", tmp_path / "target.crate"
    source_archive(source, 0)
    with pytest.raises(ReleaseSupplyChainError):
        canonical_rust_archive(source, target, version=version, epoch=epoch)


def test_canonical_crate_rejects_symlinks(tmp_path):
    source, target = tmp_path / "source.crate", tmp_path / "target.crate"
    with tarfile.open(source, "w:gz") as archive:
        link = tarfile.TarInfo("strling-4.0.0/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    with pytest.raises(ValueError):
        canonical_rust_archive(source, target, version="4.0.0", epoch=0)
