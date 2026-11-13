"""Select complete actual candidate subjects without historical recovery placeholders."""
from pathlib import Path
import hashlib,json
from admission_archive import snapshot

def preserved_metadata(path,archives,source):
    """Select original JSON bytes or their already qualified lossless archive."""
    from tooling.public_distribution import strict_json
    from tooling.evidence_bytes import decode
    assert path.is_file() and not path.is_symlink()
    raw=path.read_bytes()
    assert strict_json(raw)['source']==source
    if raw.endswith(b'\n') and b'\r' not in raw and len(raw)<=900000:
        return path
    archived=archives/('package-'+hashlib.sha256(raw).hexdigest()+'.bytes.json')
    assert archived.is_file() and not archived.is_symlink()
    assert decode(strict_json(archived.read_bytes()),source)==raw
    return archived

def extra_inputs(base,main,source,full,release):
    short=source[:8]
    load=lambda p:json.loads(Path(p).read_bytes())
    from prepare_preview_evidence_inputs import current as verify_preview_projection
    preview_projection=verify_preview_projection(True)
    assert preview_projection['source']==source and preview_projection['producer_json_changed'] is False
    preview_regression=load(base/'preview-evidence-projection-regression.json')
    assert preview_regression['source']==source and preview_regression['status']=='passed-real-copier-and-adversarial-preview-projection-qualification'
    assert preview_regression['helper_sha256']==preview_projection['helper_sha256'] and preview_regression['count']==len(preview_regression['cases'])
    from prepare_qualification_evidence_inputs import verify as verify_qualifications
    qualification_projection=verify_qualifications()
    assert qualification_projection==load(base/'qualification-evidence-projection.json')
    freeze=load(base/'candidate-freeze.json')
    assert freeze['source']==source and freeze['state']=='CERTIFICATION_READY' and not freeze['publication_authorized']
    projection=load(base/'candidate-projection-qualification.json')
    assert projection['source']==source and projection['status']=='passed-lossless-candidate-evidence-projection'
    assert projection['helper_sha256']==hashlib.sha256((base/'candidate_projection.py').read_bytes()).hexdigest()
    package=base/('signed-package-candidate-'+short)
    payload=load(package/'attestation.json')['signed_payload']
    assert payload['certified_source']['commit']==source and payload['certified_source']['clean']
    assert projection['nested_package_root']==payload['evidence_root_sha256']
    def manifest_metadata(path):
        # Preserve original producer bytes; never repair signed metadata in place.
        return preserved_metadata(path,base/('candidate-original-bytes-'+short),source)
    recovery=load(base/'candidate-input-selection-recovery.json')
    recovered=load(base/'operational-metadata-selection-qualification.json')
    assert recovery['source']==recovered['source']==source
    assert recovery['status']=='passed-qualified-lossless-operational-metadata-selection'
    assert recovered['status']=='passed-real-copier-and-hygiene-operational-metadata-selection'
    assert recovered['qualified_verifier']=='f8ef1a62be536981927e36a19587f96edb69f911'
    assert recovery['selector_sha256']==recovered['selector_sha256']==hashlib.sha256((base/'candidate_evidence_inputs.py').read_bytes()).hexdigest()
    assert recovered['qualification_code_sha256']==hashlib.sha256((base/'qualify_operational_metadata_selection.py').read_bytes()).hexdigest()
    assert recovered['count']==len(recovered['cases'])
    assert recovery['original_metadata_sha256']==recovered['original_metadata_sha256']==hashlib.sha256((base/'operational-recipe-amendments.json').read_bytes()).hexdigest()
    assert recovery['previous_selector_sha256']==hashlib.sha256((base/'retained-input-selection-before-recovery.py').read_bytes()).hexdigest()
    frozen_recipe=load(base/'operational-recipe-amendments.json')
    assert frozen_recipe['source']==source
    assert next(row['sha256'] for row in frozen_recipe['current_helpers'] if row['path']=='candidate_evidence_inputs.py')==recovery['previous_selector_sha256']
    signed=load(base/('logs/package-signing-'+short+'/terminal.json'))
    assert signed['source']==source and signed['status']=='passed-local-original-key-signature-and-source-distinct-verification'
    assert signed['qualified_verifier']=='642cc21f8f5d5ccabde1bb893076e02c624247a7' and signed['evidence_root_sha256']==payload['evidence_root_sha256']
    archives=base/('candidate-original-bytes-'+short)
    archive_files=sorted(archives.glob('*.bytes.json'))
    index_files=[archives/'preview-diagnostics-index.json',archives/'qualification-streams-index.json']
    assert not any(path.is_symlink() for path in archives.rglob('*'))
    assert set(path for path in archives.rglob('*') if path.is_file())==set(archive_files+index_files)
    from tooling.evidence_bytes import decode
    for path in archive_files:decode(load(path),source)
    qualification=load(base/('logs/profiles-'+short+'-qualify-attempt1/progress.json'))
    assert [row['profile'] for row in qualification]==['local','pull-request']
    profiles=[]
    for row in qualification:
        assert row['source']==source and row['exit_code']==0 and not row['nonpassing'] and row['summary']['status']=='passed'
        artifact=Path(row['artifact']);data=load(artifact)
        assert data['deterministic_evidence']['repository']==dict(commit=source,dirty=False)
        # Keep verbatim profiles/producer objects and seal indexed zero-byte streams.
        profiles.append(('qualification-'+row['profile'],base/('candidate-qualification-inputs-'+short)/row['profile']))
    return [
        ('release-supply-chain',base/('supply-chain-'+short+'-release')),
        ('staged-package-attestation',package/'attestation.json'),
        *[('sealed-original-metadata',path) for path in archive_files],
        *[('candidate-evidence-byte-index',path) for path in index_files],
        ('public-staged-qualification',base/('candidate-public-proof-'+short)),
        ('candidate-documentation',base/('candidate-documentation-inputs-'+short)),
        ('candidate-preview-projection-qualification',base/'preview-evidence-projection-qualification.json'),
        ('candidate-preview-projection-code',base/'prepare_preview_evidence_inputs.py'),
        ('candidate-preview-projection-regression',base/'preview-evidence-projection-regression.json'),
        ('candidate-preview-projection-regression-code',base/'qualify_preview_evidence_inputs.py'),
        ('candidate-qualification-projection',base/'qualification-evidence-projection.json'),
        ('candidate-qualification-projection-code',base/'prepare_qualification_evidence_inputs.py'),
        ('candidate-operational-recipe-amendments',manifest_metadata(base/'operational-recipe-amendments.json')),
        ('candidate-input-selection-recovery',base/'candidate-input-selection-recovery.json'),
        ('candidate-input-selection-recovery-qualification',base/'operational-metadata-selection-qualification.json'),
        ('candidate-input-selection-recovery-qualification-code',base/'qualify_operational_metadata_selection.py'),
        ('candidate-input-selection-prior-code',base/'retained-input-selection-before-recovery.py'),
        ('coordinate-preflight',base/'coordinate-preflight/report.json'),
        ('candidate-source-scope',manifest_metadata(base/'candidate-scope-preflight.json')),
        ('candidate-readiness-freeze',manifest_metadata(base/'candidate-freeze.json')),
        ('candidate-canonical-preparation',manifest_metadata(base/'preparation-acceptance.json')),
        ('candidate-verifier-qualification',main/'target/release-candidate/reader-f8ef1a62/logs/immutable-reader-qualification-attempt1/terminal.json'),
        ('candidate-evidence-projection-qualification',base/'candidate-projection-qualification.json'),
        ('candidate-evidence-projection-code',base/'candidate_projection.py'),
        ('candidate-evidence-input-selection',base/'candidate_evidence_inputs.py'),
        ('candidate-evidence-codec',Path('/var/tmp/strling-candidate-verifier-f8ef1a62/tooling/evidence_bytes.py')),
        ('execution-admission-archive-qualification',base/'admission-archive-qualification.json'),
        ('execution-admission-journal',snapshot(base,source,'public')),
        *profiles,
    ]
