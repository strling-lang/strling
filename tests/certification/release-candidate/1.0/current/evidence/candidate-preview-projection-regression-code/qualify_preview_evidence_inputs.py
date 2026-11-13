"""Exercise the real empty-file refusal and lossless Preview evidence correction."""
from pathlib import Path
import hashlib
import json
import tempfile
import time
from prepare_preview_evidence_inputs import project, verify
from release_campaign_config import configuration
from tooling.local_certification_attestation import _copy_evidence, AttestationError

SOURCE = 'a' * 40
EXPECTED = {'release:lua'}
started = time.monotonic()
passed = []

def fixture(root):
    original, projected, archives = (root/name for name in ('original', 'projected', 'archives'))
    output = original/'lua'
    output.mkdir(parents=True)
    metadata = (json.dumps(dict(command=['lua', 'smoke.lua'], exit_code=0))+'\n').encode()
    (output/'command.json').write_bytes(metadata)
    report = dict(artifact_id='release:lua', source=dict(commit=SOURCE, dirty=False), status='passed', supported_claim=False, authority='bounded-preview-documentation', command_evidence=[dict(command=['lua', 'smoke.lua'], exit_code=0, metadata='command.json', metadata_sha256=hashlib.sha256(metadata).hexdigest())])
    (output/'result.json').write_text(json.dumps(report)+'\n')
    (output/'command.stdout').write_bytes(b'first\r\nsecond \t\r\n')
    (output/'command.stderr').write_bytes(b'')
    result = project(original, projected, archives, SOURCE, EXPECTED, [])
    assert result['mandatory_json_files'] == 2 and result['diagnostic_archives'] == 2
    assert result['empty_diagnostics'] == 1 and not result['producer_json_changed']
    return original, projected, archives

with tempfile.TemporaryDirectory(prefix='strling-preview-projection-positive-', dir='/var/tmp') as directory:
    root = Path(directory)
    original, projected, archives = fixture(root)
    passed.append('empty-and-non-normalized-diagnostic-bytes-round-trip')
    rejected = root/'rejected'; rejected.mkdir()
    try:
        _copy_evidence(rejected, [('candidate-documentation', original)])
    except AttestationError as error:
        assert 'evidence file is empty' in str(error)
        passed.append('immutable-copier-reproduces-original-empty-file-refusal')
    else:
        raise AssertionError('Original empty diagnostic unexpectedly admitted')
    accepted = root/'accepted'; accepted.mkdir()
    entries = _copy_evidence(accepted, [('candidate-documentation', projected), *[('sealed-original-metadata', path) for path in sorted(archives.glob('*.bytes.json'))], ('candidate-evidence-byte-index', archives/'preview-diagnostics-index.json')])
    assert len(entries) == 5 and all(row['bytes'] > 0 for row in entries)
    passed.append('immutable-copier-retains-all-mandatory-json-and-diagnostic-archives')

def index_change(archives, change):
    path = archives/'preview-diagnostics-index.json'
    value = json.loads(path.read_bytes()); change(value)
    path.write_text(json.dumps(value)+'\n')

cases = {
    'different-source': lambda o,p,a: None,
    'changed-original-diagnostic': lambda o,p,a: (o/'lua/command.stderr').write_bytes(b'x'),
    'changed-mandatory-json': lambda o,p,a: (p/'lua/command.json').write_bytes(b'{}\n'),
    'missing-command-metadata': lambda o,p,a: (p/'lua/command.json').unlink(),
    'corrupt-byte-archive': lambda o,p,a: next(a.glob('preview-*.bytes.json')).write_bytes(b'{}\n'),
    'duplicate-index-entry': lambda o,p,a: index_change(a, lambda v: v['files'].append(v['files'][0])),
    'missing-index-entry': lambda o,p,a: index_change(a, lambda v: v['files'].pop()),
    'archive-path-traversal': lambda o,p,a: index_change(a, lambda v: next(r for r in v['files'] if r['kind']=='diagnostic-bytes').update(transport_path='../escape')),
    'unindexed-original-diagnostic': lambda o,p,a: (o/'lua/extra.stderr').write_bytes(b''),
    'extra-projected-json': lambda o,p,a: (p/'lua/extra.json').write_bytes(b'{}\n'),
    'missing-producer-result': lambda o,p,a: (o/'lua/result.json').unlink(),
    'source-symlink': lambda o,p,a: (o/'lua/linked.stdout').symlink_to(o/'lua/command.stdout'),
}
for name, mutate in cases.items():
    with tempfile.TemporaryDirectory(prefix='strling-preview-projection-negative-', dir='/var/tmp') as directory:
        original, projected, archives = fixture(Path(directory))
        mutate(original, projected, archives)
        try:
            verify(original, projected, archives, 'b'*40 if name=='different-source' else SOURCE, EXPECTED)
        except (AssertionError, ValueError, FileNotFoundError):
            passed.append(name)
        else:
            raise AssertionError('Invalid projection accepted: '+name)
base, main, source, short = configuration()
result = dict(status='passed-real-copier-and-adversarial-preview-projection-qualification', source=source, cases=passed, count=len(passed), seconds=time.monotonic()-started, helper_sha256=hashlib.sha256((base/'prepare_preview_evidence_inputs.py').read_bytes()).hexdigest(), private_key_read=False, publication_authorized=False)
with (base/'preview-evidence-projection-regression.json').open('x') as output:
    output.write(json.dumps(result, indent=2)+'\n')
print(json.dumps(result), flush=True)
