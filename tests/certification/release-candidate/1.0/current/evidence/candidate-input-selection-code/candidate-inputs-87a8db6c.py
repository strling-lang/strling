"""Select the complete candidate subjects, preserving the original nested package."""
from pathlib import Path
import importlib.util
import hashlib
import json

BASE = Path(__file__).resolve().parent
SOURCE = '87a8db6c1d08efceb13045dbcde69d2d4ed6d9d6'
PIN = '4154155adcf60c74d145936d442b4a45d7865145'
ROOT = Path('/var/tmp/strling-publication-87a8db6c-certification')
READER = Path('/var/tmp/strling402-verifier-4154155a')

def helper(name, file):
    spec = importlib.util.spec_from_file_location(name, BASE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sealed_metadata_inputs(archives, output, source):
    from tooling.evidence_bytes import decode
    from tooling.public_distribution import strict_json
    assert archives.is_dir() and not archives.is_symlink()
    index = archives / 'preview-diagnostics-index.json'
    assert index.is_file() and not index.is_symlink()
    manifest = strict_json(index.read_bytes())
    assert set(manifest) == {'schema_version', 'source', 'files'}
    assert manifest['schema_version'] == 'strling-preview-evidence-projection-v1' and manifest['source'] == source
    selected = {}
    for path in sorted(archives.iterdir()):
        assert path.is_file() and not path.is_symlink()
        if path == index:
            continue
        assert path.name.endswith('.bytes.json')
        raw = path.read_bytes()
        decode(strict_json(raw), source)
        selected[path.name] = raw
    assert selected
    output.mkdir(exist_ok=True)
    assert not output.is_symlink()
    for name, raw in selected.items():
        target = output / name
        if target.exists():
            assert target.is_file() and not target.is_symlink() and target.read_bytes() == raw
        else:
            target.write_bytes(raw)
    assert {p.name for p in output.iterdir()} == set(selected)
    return [('sealed-original-metadata', output), ('candidate-preview-diagnostics-index', index)]

def inputs(attestation):
    from tooling.evidence_bytes import encode, decode
    package_cfg = helper('current_package_selection', 'package-inputs-87a8db6c.py')
    full, release, _, _ = package_cfg.inputs(attestation)
    projection = helper('current_candidate_projection', 'candidate-projection-87a8db6c.py').verify()
    preview = helper('current_preview_projection', 'prepare-preview-evidence-inputs-87a8db6c.py').current(True)
    assert projection['source'] == preview['source'] == SOURCE
    assert projection['coverage_unchanged'] and not preview['producer_json_changed']
    regression = json.loads((BASE / 'preview-evidence-projection-regression-87a8db6c.json').read_text())
    assert regression['status'] == 'passed-real-copier-and-adversarial-preview-projection-qualification'
    assert regression['source'] == SOURCE and regression['count'] == len(regression['cases'])
    assert regression['helper_sha256'] == preview['helper_sha256']
    assert regression['helper_sha256'] == hashlib.sha256((BASE / 'prepare-preview-evidence-inputs-87a8db6c.py').read_bytes()).hexdigest()
    selection_regression = json.loads((BASE / 'candidate-input-selection-qualification-87a8db6c.json').read_bytes())
    assert selection_regression['status'] == 'passed-archive-role-regression-and-adversarial-selection'
    assert selection_regression['source'] == SOURCE and selection_regression['count'] == len(selection_regression['cases'])
    assert all(case['status'] == 'passed' for case in selection_regression['cases'])
    assert selection_regression['helper_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert selection_regression['qualification_code_sha256'] == hashlib.sha256((BASE / 'qualify-candidate-input-selection-87a8db6c.py').read_bytes()).hexdigest()
    package = BASE / 'signed-package-candidate-87a8db6c'
    signed = json.loads((package / 'attestation.json').read_text())['signed_payload']
    assert signed['certified_source'] == dict(commit=SOURCE, tree=signed['certified_source']['tree'], clean=True)
    assert signed['evidence_root_sha256'] == projection['nested_package_root']
    def code_input(path):
        # Preserve exact qualified helper bytes across Windows line endings.
        # Git text normalization must never silently change a signed subject.
        assert path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        if b'\r' not in raw and raw.endswith(b'\n') and len(raw) <= 900000:
            return path
        digest = hashlib.sha256(raw).hexdigest()
        archived = BASE / 'candidate-original-bytes-87a8db6c' / ('candidate-code-' + digest + '.bytes.json')
        if not archived.exists():
            with archived.open('xb') as output:
                output.write(encode(raw, path.name, SOURCE))
        assert archived.is_file() and not archived.is_symlink()
        assert decode(json.loads(archived.read_bytes()), SOURCE) == raw
        return archived
    extras = [
        ('release-supply-chain', BASE / 'supply-chain-87a8db6c-release'),
        ('public-staged-qualification', BASE / 'candidate-public-proof-87a8db6c'),
        ('candidate-documentation', BASE / 'candidate-documentation-inputs-87a8db6c'),
        ('coordinate-preflight', BASE / 'coordinate-preflight-87a8db6c/report.json'),
        ('staged-package-attestation', package / 'attestation.json'),
        ('candidate-projection-qualification', BASE / 'candidate-projection-qualification-87a8db6c.json'),
        ('candidate-preview-projection-qualification', BASE / 'preview-evidence-projection-qualification-87a8db6c.json'),
        ('candidate-preview-projection-regression', BASE / 'preview-evidence-projection-regression-87a8db6c.json'),
        ('candidate-preview-projection-regression-code', code_input(BASE / 'qualify-preview-projection-87a8db6c.py')),
        ('candidate-evidence-codec', READER / 'tooling/evidence_bytes.py'),
        ('candidate-evidence-projection-code', code_input(BASE / 'candidate-projection-87a8db6c.py')),
        ('candidate-preview-projection-code', code_input(BASE / 'prepare-preview-evidence-inputs-87a8db6c.py')),
        ('candidate-input-selection-code', code_input(Path(__file__))),
        ('candidate-input-selection-qualification', BASE / 'candidate-input-selection-qualification-87a8db6c.json'),
        ('candidate-input-selection-regression-code', code_input(BASE / 'qualify-candidate-input-selection-87a8db6c.py')),
    ]
    extras += sealed_metadata_inputs(BASE / 'candidate-original-bytes-87a8db6c', BASE / 'candidate-sealed-metadata-87a8db6c', SOURCE)
    return full, release, [
        ('profile-full', full), ('profile-release', release),
        *attestation._production_evidence_inputs(release),
        *attestation._execution_evidence_inputs(ROOT, full, release), *extras,
    ], extras
