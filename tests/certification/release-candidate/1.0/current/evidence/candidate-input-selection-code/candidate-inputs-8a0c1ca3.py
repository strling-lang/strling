"""Select the complete candidate subjects, preserving the original nested package."""
from pathlib import Path
import importlib.util
import hashlib
import json

BASE = Path(__file__).resolve().parent
SOURCE = '8a0c1ca31484b537bcff596922182bb66ab1e392'
PIN = 'c653d82504bf28f4d18bc0f80c9426912a2fb3e7'
ROOT = Path('/var/tmp/strling-publication-8a0c1ca3-certification')
READER = Path('/var/tmp/strling-publication-verifier-c653d825')

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
    package_cfg = helper('current_package_selection', 'package-inputs-8a0c1ca3.py')
    full, release, _, _ = package_cfg.inputs(attestation)
    projection = helper('current_candidate_projection', 'candidate-projection-8a0c1ca3.py').verify()
    preview = helper('current_preview_projection', 'prepare-preview-evidence-inputs-8a0c1ca3.py').current(True)
    assert projection['source'] == preview['source'] == SOURCE
    assert projection['coverage_unchanged'] and not preview['producer_json_changed']
    regression = json.loads((BASE / 'preview-evidence-projection-regression-8a0c1ca3.json').read_text())
    assert regression['status'] == 'passed-real-copier-and-adversarial-preview-projection-qualification'
    assert regression['source'] == SOURCE and regression['count'] == len(regression['cases'])
    assert regression['helper_sha256'] == preview['helper_sha256']
    assert regression['helper_sha256'] == hashlib.sha256((BASE / 'prepare-preview-evidence-inputs-8a0c1ca3.py').read_bytes()).hexdigest()
    selection_regression = json.loads((BASE / 'candidate-input-selection-qualification-8a0c1ca3.json').read_bytes())
    assert selection_regression['status'] == 'passed-archive-role-regression-and-adversarial-selection'
    assert selection_regression['source'] == SOURCE and selection_regression['count'] == len(selection_regression['cases'])
    assert all(case['status'] == 'passed' for case in selection_regression['cases'])
    assert selection_regression['helper_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert selection_regression['qualification_code_sha256'] == hashlib.sha256((BASE / 'qualify-candidate-input-selection-8a0c1ca3.py').read_bytes()).hexdigest()
    package = BASE / 'signed-package-candidate-8a0c1ca3'
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
        archived = BASE / 'candidate-original-bytes-8a0c1ca3' / ('candidate-code-' + digest + '.bytes.json')
        if not archived.exists():
            with archived.open('xb') as output:
                output.write(encode(raw, path.name, SOURCE))
        assert archived.is_file() and not archived.is_symlink()
        assert decode(json.loads(archived.read_bytes()), SOURCE) == raw
        return archived
    extras = [
        ('release-supply-chain', BASE / 'supply-chain-8a0c1ca3-release'),
        ('public-staged-qualification', BASE / 'candidate-public-proof-8a0c1ca3'),
        ('candidate-documentation', BASE / 'candidate-documentation-inputs-8a0c1ca3'),
        ('coordinate-preflight', BASE / 'coordinate-preflight-8a0c1ca3/report.json'),
        ('staged-package-attestation', package / 'attestation.json'),
        ('candidate-projection-qualification', BASE / 'candidate-projection-qualification-8a0c1ca3.json'),
        ('candidate-preview-projection-qualification', BASE / 'preview-evidence-projection-qualification-8a0c1ca3.json'),
        ('candidate-preview-projection-regression', BASE / 'preview-evidence-projection-regression-8a0c1ca3.json'),
        ('candidate-preview-projection-regression-code', code_input(BASE / 'qualify-preview-projection-8a0c1ca3.py')),
        ('candidate-evidence-codec', READER / 'tooling/evidence_bytes.py'),
        ('candidate-evidence-projection-code', code_input(BASE / 'candidate-projection-8a0c1ca3.py')),
        ('candidate-preview-projection-code', code_input(BASE / 'prepare-preview-evidence-inputs-8a0c1ca3.py')),
        ('candidate-input-selection-code', code_input(Path(__file__))),
        ('candidate-input-selection-qualification', BASE / 'candidate-input-selection-qualification-8a0c1ca3.json'),
        ('candidate-input-selection-regression-code', code_input(BASE / 'qualify-candidate-input-selection-8a0c1ca3.py')),
    ]
    extras += sealed_metadata_inputs(BASE / 'candidate-original-bytes-8a0c1ca3', BASE / 'candidate-sealed-metadata-8a0c1ca3', SOURCE)
    return full, release, [
        ('profile-full', full), ('profile-release', release),
        *attestation._production_evidence_inputs(release),
        *attestation._execution_evidence_inputs(ROOT, full, release), *extras,
    ], extras
