"""Rebuild a signed nested package certificate solely from public audit evidence."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,shutil,subprocess,sys

def verified_evidence(document, attestation, source, attestation_sha256):
    """Read the immutable CLI's versioned result envelope without weakening it."""
    def need(condition, message):
        if not condition: raise ValueError(message)
    need(isinstance(document,dict) and document.get('schema_version')=='1.0.0', 'verification schema changed')
    need(document.get('operation_id')=='certification.local-attestation-verification' and document.get('status')=='passed', 'verification identity or status changed')
    need(document.get('summary')==dict(failed=0,incomplete=0,passed=1,unavailable=0,waived=0), 'verification aggregate changed')
    checks=document.get('checks')
    need(isinstance(checks,list) and len(checks)==1, 'exactly one integrity result required')
    check=checks[0]
    need(isinstance(check,dict) and check.get('check_id')=='certification.local-attestation-verification.integrity' and check.get('status')=='passed', 'integrity producer changed')
    evidence=check.get('evidence')
    need(isinstance(evidence,dict), 'integrity evidence missing')
    payload=attestation['signed_payload']
    need(evidence.get('certified_source_sha')==source and evidence.get('verified_head_sha')==source, 'verified source changed')
    need(evidence.get('evidence_root_sha256')==payload['evidence_root_sha256'], 'verified evidence root changed')
    need(evidence.get('attestation_sha256')==attestation_sha256, 'verified attestation bytes changed')
    need(evidence.get('signature_sha256')==attestation['signature']['signature_sha256'], 'verified signature changed')
    need(evidence.get('certifier_id')==attestation['signature']['certifier_id'], 'verified certifier changed')
    need(evidence.get('profile_results')==payload['profile_results'], 'verified profiles changed')
    need(evidence.get('waiver_inventory')==payload['waiver_inventory']==['WVR-SEC-VSCE-LICENSE-001'], 'verified waiver inventory changed')
    return evidence

def reconstruct(evidence,entries,output,root,source):
    trusted=Path('/var/tmp/strling-release-verifier-642cc21f')
    pin='642cc21f8f5d5ccabde1bb893076e02c624247a7'
    assert subprocess.check_output(['git','-C',str(trusted),'rev-parse','HEAD'],text=True).strip()==pin
    assert not subprocess.check_output(['git','-C',str(trusted),'status','--porcelain']).strip()
    (attested,)=[r for r in entries if r['role']=='staged-package-attestation']
    signed_bytes=(evidence/attested['path']).read_bytes()
    assert hashlib.sha256(signed_bytes).hexdigest()==attested['sha256']
    attestation=json.loads(signed_bytes)
    payload=attestation['signed_payload']; assert payload['certified_source']['commit']==source
    by_identity={(r['bytes'],r['sha256']):r['path'] for r in entries}
    from metadata_bytes import decode
    archived={}
    for row in entries:
        if row['role']=='sealed-original-metadata':
            raw=decode(json.loads((evidence/row['path']).read_text()),source)
            archived[(len(raw),hashlib.sha256(raw).hexdigest())]=(row['path'],raw)
    decoded=output/'decoded-original-metadata';decoded.mkdir(exist_ok=False)
    bundle=output/'reconstructed-package-bundle';bundle.mkdir(exist_ok=False)
    (bundle/'attestation.json').write_bytes(signed_bytes)
    used=[]
    for item in payload['evidence_files']:
        rel=PurePosixPath(item['path']);assert not rel.is_absolute() and '..' not in rel.parts and rel.parts[0]=='evidence' and re.fullmatch('[a-f0-9]{64}',item['sha256'])
        identity=(item['bytes'],item['sha256'])
        if identity in by_identity:
            origin=by_identity[identity];data=evidence/origin
        else:
            archive_path,raw=archived[identity]
            origin=archive_path+'#exact-decoded-bytes';data=decoded/item['sha256'];data.write_bytes(raw)
        assert data.is_file() and not data.is_symlink() and data.stat().st_size==item['bytes']
        dest=bundle/rel;dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();shutil.copyfile(data,dest)
        assert hashlib.sha256(dest.read_bytes()).hexdigest()==item['sha256']
        used.append(dict(package_path=str(rel),public_evidence_path=origin,sha256=item['sha256']))
    cmd=[sys.executable,'-I','-B',str(trusted/'tooling/local_certification_attestation.py'),'--repository-root',str(root),'--trust-root',str(trusted),'--trust-policy','release-certification-trust.json','verify','--bundle',str(bundle),'--json']
    with (output/'nested-package-verification.stdout').open('x') as stdout,(output/'nested-package-verification.stderr').open('x') as stderr:
        result=subprocess.run(cmd,cwd=trusted,stdout=stdout,stderr=stderr)
    assert result.returncode==0,'Reconstructed nested package certificate rejected; originals retained'
    verified=json.loads((output/'nested-package-verification.stdout').read_text())
    verified_evidence(verified,attestation,source,hashlib.sha256(signed_bytes).hexdigest())
    report=dict(status='passed-package-reconstruction-from-public-evidence-alone',source=source,verifier=pin,evidence_root_sha256=payload['evidence_root_sha256'],files=used,private_key_read=False,publication_authorized=False)
    with (output/'nested-package-reconstruction.json').open('x') as f:json.dump(report,f,indent=2)
    return {k:v for k,v in report.items() if k!='files'}|{'file_count':len(used)}
