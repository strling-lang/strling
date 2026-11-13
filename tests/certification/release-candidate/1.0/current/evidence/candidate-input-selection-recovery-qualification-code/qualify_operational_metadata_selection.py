"""Reproduce CRLF refusal and qualify exact-byte metadata selection."""
from pathlib import Path
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import time

from release_campaign_config import configuration

base, main, source, short = configuration()
trusted=Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
pin='f8ef1a62be536981927e36a19587f96edb69f911'
assert subprocess.check_output(['git','-C',str(trusted),'rev-parse','HEAD'],text=True).strip()==pin
assert not subprocess.check_output(['git','-C',str(trusted),'status','--porcelain']).strip()
sys.path.insert(0,str(trusted))
from tooling.evidence_bytes import encode, decode
from tooling.public_distribution import strict_json
from tooling.local_certification_attestation import _copy_evidence
from candidate_evidence_inputs import preserved_metadata

started=time.monotonic()
cases=[]
digest=lambda raw: hashlib.sha256(raw).hexdigest()

def fixture(root, raw=None):
    raw=raw if raw is not None else (json.dumps(dict(source=source,observation='original'))+'\r\n').encode()
    original=root/'operational-recipe-amendments.json'
    original.write_bytes(raw)
    archives=root/'archives';archives.mkdir()
    archive=archives/('package-'+digest(raw)+'.bytes.json')
    archive.write_bytes(encode(raw,'operational-recipe-amendments.json',source))
    return original,archives,archive,raw

with tempfile.TemporaryDirectory(prefix='strling-operational-metadata-positive-',dir='/var/tmp') as temp:
    root=Path(temp)
    for name,ending in (('canonical-lf-verbatim',b'\n'),('crlf-lossless',b'\r\n'),('missing-final-newline-lossless',b'')):
        directory=root/name;directory.mkdir()
        original,archives,archive,raw=fixture(directory,json.dumps(dict(source=source,observation='unchanged')).encode()+ending)
        selected=preserved_metadata(original,archives,source)
        assert selected==(original if ending==b'\n' else archive)
        if selected==archive:assert decode(strict_json(selected.read_bytes()),source)==raw
        assert original.read_bytes()==raw
        cases.append(name)
    original,archives,archive,raw=fixture(root)
    for label,inputs,expected in (
        ('original-crlf-hygiene-refusal',[('candidate-operational-recipe-amendments',original)],1),
        ('lossless-archive-hygiene-acceptance',[('candidate-operational-recipe-amendments',preserved_metadata(original,archives,source)),('sealed-original-metadata',archive)],0),
    ):
        evidence=root/label;evidence.mkdir()
        entries=_copy_evidence(evidence,inputs)
        entries_path=root/(label+'.json');entries_path.write_text(json.dumps(entries)+'\n')
        result=subprocess.run([sys.executable,str(base/'preflight_candidate_hygiene.py'),str(evidence),str(entries_path)],capture_output=True,text=True)
        assert result.returncode==expected, result.stdout+result.stderr
        report=strict_json(result.stdout.encode())
        if expected:
            assert len(report['findings'])==1 and report['findings'][0]['rule']=='line-endings'
        else:
            assert report['status']=='passed' and not report['findings'] and report['normalization_applied'] is False
        assert original.read_bytes()==raw
        cases.append(label)

def rewrite(archive, change):
    document=strict_json(archive.read_bytes());change(document)
    archive.write_text(json.dumps(document)+'\n')

negatives={
    'wrong-original-source':lambda p,a,f,r:p.write_bytes((json.dumps(dict(source='b'*40))+'\r\n').encode()),
    'wrong-archive-source':lambda p,a,f,r:rewrite(f,lambda d:d.update(source='b'*40)),
    'normalized-substitution':lambda p,a,f,r:f.write_bytes(encode(r.replace(b'\r\n',b'\n'),'operational-recipe-amendments.json',source)),
    'missing-archive':lambda p,a,f,r:f.unlink(),
    'changed-original-after-archival':lambda p,a,f,r:p.write_bytes(r.replace(b'original',b'changed')),
    'corrupt-payload':lambda p,a,f,r:rewrite(f,lambda d:d.update(payload='!')),
    'wrong-checksum':lambda p,a,f,r:rewrite(f,lambda d:d.update(sha256='0'*64)),
    'extra-archive-field':lambda p,a,f,r:rewrite(f,lambda d:d.update(extra=True)),
    'duplicate-original-json-field':lambda p,a,f,r:p.write_bytes(('{"source":"'+source+'","source":"'+source+'"}\r\n').encode()),
    'archive-trailing-bytes':lambda p,a,f,r:rewrite(f,lambda d:d.update(payload=base64.b64encode(base64.b64decode(d['payload'])+b'x').decode())),
}
for label,mutate in negatives.items():
    with tempfile.TemporaryDirectory(prefix='strling-operational-metadata-negative-',dir='/var/tmp') as temp:
        original,archives,archive,raw=fixture(Path(temp))
        mutate(original,archives,archive,raw)
        try:preserved_metadata(original,archives,source)
        except (AssertionError,ValueError,FileNotFoundError,KeyError):cases.append(label)
        else:raise AssertionError('Invalid metadata selection admitted: '+label)
for target in ('original','archive'):
    with tempfile.TemporaryDirectory(prefix='strling-operational-metadata-link-',dir='/var/tmp') as temp:
        original,archives,archive,raw=fixture(Path(temp))
        linked=original if target=='original' else archive
        retained=linked.with_suffix('.retained');linked.rename(retained);linked.symlink_to(retained)
        try:preserved_metadata(original,archives,source)
        except AssertionError:cases.append('reject-'+target+'-symlink')
        else:raise AssertionError('Linked metadata admitted')

original=base/'operational-recipe-amendments.json'
raw=original.read_bytes()
assert raw.count(b'\r\n')>0
selected=preserved_metadata(original,base/('candidate-original-bytes-'+short),source)
assert decode(strict_json(selected.read_bytes()),source)==raw
cases.append('genuine-signed-operational-metadata-round-trip')
result=dict(status='passed-real-copier-and-hygiene-operational-metadata-selection',
            source=source,qualified_verifier=pin,cases=cases,count=len(cases),
            selector_sha256=digest((base/'candidate_evidence_inputs.py').read_bytes()),
            qualification_code_sha256=digest(Path(__file__).read_bytes()),
            original_metadata_sha256=digest(raw),original_metadata_bytes=len(raw),
            original_metadata_crlf=raw.count(b'\r\n'),selected_archive_sha256=digest(selected.read_bytes()),
            source_and_signed_bytes_modified=False,normalization_applied=False,
            private_key_read=False,publication_authorized=False,seconds=time.monotonic()-started)
output=base/'operational-metadata-selection-qualification.json'
assert not output.exists()
output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
