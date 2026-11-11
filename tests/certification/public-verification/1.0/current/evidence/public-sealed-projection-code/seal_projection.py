"""Preserve exact diagnostic bytes while projecting compliant certificate paths."""
from pathlib import Path
import copy,hashlib,json,shutil
from metadata_bytes import encode,decode
SOURCE='3e7061271d906251cb17c3eb06b6c748ac3068e7'
LOGS={'prerequisites/dart/preparation.log','prerequisites/kotlin/preparation.log'}
def verify(projection,archives,source):
    original_bytes=decode(json.loads((archives/'original-public-proof.bytes.json').read_text()),source)
    original=json.loads(original_bytes);current=json.loads((projection/'proof.json').read_text())
    stripped=copy.deepcopy(current);stripped.pop('transport_projection');stripped['evidence_files']=original['evidence_files']
    assert stripped==original and current['transport_projection']['original_proof_sha256']==hashlib.sha256(original_bytes).hexdigest()
    expected={}
    for row in original['evidence_files']:
        relative=row['path']
        if relative in LOGS:
            relative=str(Path(relative).parent/'preparation-output.json')
            data=(projection/relative).read_bytes()
            raw=decode(json.loads(data),source)
            assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        else:
            data=(projection/relative).read_bytes()
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        expected[relative]=dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    assert {r['path']:r for r in current['evidence_files']}==expected
    assert {p.relative_to(projection).as_posix() for p in projection.rglob('*') if p.is_file()}==set(expected)|{'proof.json'}
    return dict(status='passed-lossless-public-evidence-projection',source=source,original_proof_sha256=hashlib.sha256(original_bytes).hexdigest(),
        projected_proof_sha256=hashlib.sha256((projection/'proof.json').read_bytes()).hexdigest(),
        coverage_unchanged=True,artifact_routes=current['artifact_routes'],consumer_scopes=current['supported_consumer_scopes'],obligations=current['public_obligations'])
def prepare(base):
    original=base/'public-staged-proof-3e706127';projection=base/'public-staged-proof-3e706127-sealed-v2'
    archives=base/'metadata-originals-v2';projection.mkdir(exist_ok=False);archives.mkdir(exist_ok=False)
    raw_proof=(original/'proof.json').read_bytes();proof=json.loads(raw_proof)
    policy=json.loads((base.parents[2]/'governance/repository-hygiene.json').read_text())
    def archive(raw,name):
        assert not any(marker.encode() in raw for marker in policy['private_key_markers'])
        return encode(raw,name,SOURCE)
    (archives/'original-public-proof.bytes.json').write_bytes(archive(raw_proof,'proof.json'))
    for name in ('resume-recipe-preparation.json','execution-owner-resume-3.json'):
        (archives/(name+'.bytes.json')).write_bytes(archive((base/name).read_bytes(),name))
    entries=[]
    assert {r['path'] for r in proof['evidence_files'] if r['path'].endswith('preparation.log')}==LOGS
    for row in proof['evidence_files']:
        raw=(original/row['path']).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        relative=row['path'];data=raw
        if relative in LOGS:
            relative=str(Path(relative).parent/'preparation-output.json');data=archive(raw,'preparation.log')
        target=projection/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        entries.append(dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    projected=copy.deepcopy(proof);projected['evidence_files']=entries
    projected['transport_projection']=dict(original_proof_sha256=hashlib.sha256(raw_proof).hexdigest(),diagnostic_bytes_preserved=True,normalization_applied=False)
    (projection/'proof.json').write_text(json.dumps(projected,indent=2)+'\n')
    return verify(projection,archives,SOURCE)
if __name__=='__main__':
    base=Path(__file__).resolve().parent
    result=prepare(base);(base/'sealed-projection-qualification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
