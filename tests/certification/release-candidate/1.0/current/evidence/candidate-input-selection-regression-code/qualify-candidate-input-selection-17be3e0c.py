from pathlib import Path
import hashlib,importlib.util,json,sys,tempfile
BASE=Path(__file__).resolve().parent
TRUST=Path('/var/tmp/strling401-verifier-ea03dd4c')
sys.path.insert(0,str(TRUST))
from tooling.evidence_bytes import encode,decode
spec=importlib.util.spec_from_file_location('candidate_inputs',BASE/'candidate-inputs-17be3e0c.py')
cfg=importlib.util.module_from_spec(spec);spec.loader.exec_module(cfg)
original_index=BASE/'candidate-original-bytes-17be3e0c/preview-diagnostics-index.json'
try:decode(json.loads(original_index.read_bytes()),cfg.SOURCE)
except ValueError as e:assert str(e)=='archive fields'
else:raise AssertionError('Original archive-role failure did not reproduce')
cases=[]
def run(name, mutate=None):
    with tempfile.TemporaryDirectory(prefix='strling-archive-role-test-',dir='/var/tmp') as tmp:
        root=Path(tmp);a=root/'archives';a.mkdir();v=root/'selected'
        (a/'preview-diagnostics-index.json').write_bytes(original_index.read_bytes())
        (a/'one.bytes.json').write_bytes(encode(b'original\r\nbytes\n','one.bin',cfg.SOURCE))
        if mutate:mutate(a,v)
        try:rows=cfg.sealed_metadata_inputs(a,v,cfg.SOURCE)
        except (AssertionError,ValueError):
            assert mutate is not None,name
        else:
            assert mutate is None,name
            assert [r for r,_ in rows]==['sealed-original-metadata','candidate-preview-diagnostics-index']
            assert rows[1][1].read_bytes()==original_index.read_bytes()
            assert decode(json.loads((rows[0][1]/'one.bytes.json').read_bytes()),cfg.SOURCE)==b'original\r\nbytes\n'
        cases.append(dict(name=name,status='passed'))
run('valid archive selected and exact index retained under separate role')
run('unregistered nonarchive rejected',lambda a,v:(a/'other.json').write_text('{}'))
run('wrong-source archive rejected',lambda a,v:(a/'one.bytes.json').write_bytes(encode(b'x','one.bin','0'*40)))
run('index-shaped document rejected as codec archive',lambda a,v:(a/'extra.bytes.json').write_bytes(original_index.read_bytes()))
run('missing required index rejected',lambda a,v:(a/'preview-diagnostics-index.json').unlink())
run('substituted selected bytes rejected',lambda a,v:(v.mkdir(),(v/'one.bytes.json').write_bytes(b'changed')))
run('unexpected selected file rejected',lambda a,v:(v.mkdir(),(v/'extra.bytes.json').write_bytes(b'changed')))
run('linked archive rejected',lambda a,v:(a/'alias.bytes.json').symlink_to(a/'one.bytes.json'))
result=dict(status='passed-archive-role-regression-and-adversarial-selection',source=cfg.SOURCE,helper_sha256=hashlib.sha256((BASE/'candidate-inputs-17be3e0c.py').read_bytes()).hexdigest(),qualification_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_failure_reproduced=True,cases=cases,count=len(cases),verifier_changed=False,producer_bytes_changed=False,publication_authorized=False)
(BASE/'candidate-input-selection-qualification-17be3e0c.json').write_text(json.dumps(result,indent=2)+'\n')
from tooling import local_certification_attestation as attestation
_,_,inputs,_=cfg.inputs(attestation)
selected=[p for role,p in inputs if role=='sealed-original-metadata'];assert len(selected)==1
for p in selected[0].iterdir():decode(json.loads(p.read_bytes()),cfg.SOURCE)
assert len([p for role,p in inputs if role=='candidate-preview-diagnostics-index'])==1
result['actual_archive_files']=len(list(selected[0].iterdir()))
(BASE/'candidate-input-selection-qualification-17be3e0c.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('status','count','actual_archive_files','original_failure_reproduced','producer_bytes_changed')}))
