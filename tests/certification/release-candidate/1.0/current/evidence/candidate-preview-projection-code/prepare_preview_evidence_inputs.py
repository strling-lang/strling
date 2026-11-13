"""Retain mandatory Preview JSON verbatim and every diagnostic byte losslessly."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import subprocess
import sys
from release_campaign_config import configuration

TRUSTED = Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
PIN = 'f8ef1a62be536981927e36a19587f96edb69f911'
assert subprocess.check_output(['git', '-C', str(TRUSTED), 'rev-parse', 'HEAD'], text=True).strip() == PIN
sys.path.insert(0, str(TRUSTED))
from tooling.evidence_bytes import encode, decode
from tooling.public_distribution import strict_json

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def files(root):
    paths = list(root.rglob('*'))
    assert not any(path.is_symlink() for path in paths)
    return {path.relative_to(root).as_posix(): path for path in paths if path.is_file()}

def safe(name):
    path = PurePosixPath(name)
    assert path.parts and not path.is_absolute() and '..' not in path.parts
    assert '\\' not in name and ':' not in name
    return path

def required(original, source, expected):
    reports = sorted(original.glob('*/result.json'))
    assert {strict_json(path.read_bytes())['artifact_id'] for path in reports} == expected
    assert len(reports) == len(expected)
    selected = set()
    for path in reports:
        report = strict_json(path.read_bytes())
        assert report['artifact_id'] == 'release:' + path.parent.name
        assert report['source']['commit'] == source and report['source']['dirty'] is False
        assert report['status'] == 'passed' and report['supported_claim'] is False
        assert report['authority'] == 'bounded-preview-documentation'
        selected.add(path.relative_to(original).as_posix())
        for command in report['command_evidence']:
            name = command['metadata']
            assert safe(name).name == name and name.endswith('.json')
            metadata = path.parent / name
            raw = metadata.read_bytes()
            assert digest(raw) == command['metadata_sha256']
            terminal = strict_json(raw)
            assert terminal['command'] == command['command']
            assert terminal['exit_code'] == command['exit_code'] == 0
            relative = metadata.relative_to(original).as_posix()
            assert relative not in selected
            selected.add(relative)
    assert {name for name in files(original) if name.endswith('.json')} == selected
    return selected

def project(original, projected, archives, source, expected, markers):
    selected = required(original, source, expected)
    projected.mkdir(exist_ok=False)
    archives.mkdir(exist_ok=True)
    rows = []
    for relative, path in sorted(files(original).items()):
        raw = path.read_bytes()
        assert not any(marker.encode() in raw for marker in markers)
        if relative in selected:
            assert raw and raw.endswith(b'\n')
            destination = projected / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            transport = relative
            kind = 'mandatory-json'
        else:
            assert path.suffix in ('.stdout', '.stderr')
            transport = 'preview-' + digest(relative.encode()) + '.bytes.json'
            destination = archives / transport
            assert not destination.exists()
            destination.write_bytes(encode(raw, path.name, source))
            assert decode(strict_json(destination.read_bytes()), source) == raw
            kind = 'diagnostic-bytes'
        rows.append(dict(original_path=relative, kind=kind, bytes=len(raw), sha256=digest(raw), transport_path=transport, transport_sha256=digest(destination.read_bytes())))
    index = archives / 'preview-diagnostics-index.json'
    assert not index.exists()
    index.write_text(json.dumps(dict(schema_version='strling-preview-evidence-projection-v1', source=source, files=rows), indent=2)+'\n')
    return verify(original, projected, archives, source, expected)

def verify(original, projected, archives, source, expected):
    selected = required(original, source, expected)
    index_path = archives / 'preview-diagnostics-index.json'
    index = strict_json(index_path.read_bytes())
    assert index['schema_version'] == 'strling-preview-evidence-projection-v1' and index['source'] == source
    rows = index['files']
    originals = files(original)
    assert len(rows) == len(originals) and {row['original_path'] for row in rows} == set(originals)
    assert set(files(projected)) == selected
    archived = set()
    zero = 0
    for row in rows:
        relative = row['original_path']
        raw = originals[relative].read_bytes()
        assert row['bytes'] == len(raw) and row['sha256'] == digest(raw)
        if relative in selected:
            assert row['kind'] == 'mandatory-json' and row['transport_path'] == relative
            path = projected / relative
            assert path.read_bytes() == raw
        else:
            assert row['kind'] == 'diagnostic-bytes' and Path(relative).suffix in ('.stdout', '.stderr')
            name = row['transport_path']
            assert safe(name).name == name
            assert name == 'preview-' + digest(relative.encode()) + '.bytes.json'
            assert name not in archived
            archived.add(name)
            path = archives / name
            assert not path.is_symlink()
            assert decode(strict_json(path.read_bytes()), source) == raw
            zero += len(raw) == 0
        assert digest(path.read_bytes()) == row['transport_sha256']
    assert {path.name for path in archives.glob('preview-*.bytes.json')} == archived
    return dict(status='passed-lossless-preview-evidence-projection', source=source, mandatory_json_files=len(selected), diagnostic_archives=len(archived), empty_diagnostics=zero, original_files=len(originals), index_sha256=digest(index_path.read_bytes()), helper_sha256=digest(Path(__file__).read_bytes()), codec_sha256=digest((TRUSTED/'tooling/evidence_bytes.py').read_bytes()), producer_json_changed=False, product_artifact_normalization_applied=False, private_key_read=False, publication_authorized=False)

def current(verify_only=False):
    base, main, source, short = configuration()
    scope = strict_json((base/'candidate-scope-preflight.json').read_bytes())
    assert scope['source'] == source
    expected = {row['artifact_id'] for row in scope['routes'] if row['tier'] == 'Preview'}
    arguments = (base/('candidate-documentation-'+short), base/('candidate-documentation-inputs-'+short), base/('candidate-original-bytes-'+short), source, expected)
    if verify_only:
        result = verify(*arguments)
        assert result == strict_json((base/'preview-evidence-projection-qualification.json').read_bytes())
    else:
        markers = strict_json((main/'governance/repository-hygiene.json').read_bytes())['private_key_markers']
        result = project(*arguments, markers)
        with (base/'preview-evidence-projection-qualification.json').open('x') as output:
            output.write(json.dumps(result, indent=2)+'\n')
    return result

if __name__ == '__main__':
    print(json.dumps(current('--verify' in sys.argv)), flush=True)
