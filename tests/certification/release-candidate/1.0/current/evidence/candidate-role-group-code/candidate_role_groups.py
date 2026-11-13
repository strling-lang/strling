"""Preserve exact flat evidence identities behind unique supplemental roles."""
from pathlib import Path
import shutil

ROLES={'sealed-original-metadata','candidate-evidence-byte-index'}

def verify_group(role,files,directory,source):
    from tooling.public_distribution import strict_json
    from tooling.evidence_bytes import decode
    assert role in ROLES and files
    assert len({path.name for path in files})==len(files)
    assert directory.is_dir() and not directory.is_symlink()
    expected={path.name for path in files}
    assert {path.name for path in directory.iterdir()}==expected
    for original in files:
        target=directory/original.name
        assert original.is_file() and not original.is_symlink()
        assert target.is_file() and not target.is_symlink()
        raw=original.read_bytes()
        document=strict_json(raw)
        assert document['source']==source
        if role=='sealed-original-metadata':decode(document,source)
        assert target.read_bytes()==raw
    return directory

def prepare_group(role,files,directory,source):
    assert role in ROLES and files
    assert len({path.name for path in files})==len(files)
    assert all(path.is_file() and not path.is_symlink() for path in files)
    directory.mkdir(exist_ok=False)
    for original in files:shutil.copyfile(original,directory/original.name)
    return verify_group(role,files,directory,source)
