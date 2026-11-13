"""Preserve qualification objects, including authenticated zero-byte streams."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from release_campaign_config import configuration

base, main, source, short = configuration()
root = Path('/var/tmp/strling-release-candidate-'+short+'-certification')
trusted = Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
assert subprocess.check_output(['git','-C',str(trusted),'rev-parse','HEAD'],text=True).strip() == 'f8ef1a62be536981927e36a19587f96edb69f911'
sys.path.insert(0,str(trusted))
from tooling import local_certification_attestation as attest
from tooling.structured_operation_execution import validate_result_directory
from tooling.evidence_bytes import encode, decode
from tooling.public_distribution import strict_json
from tooling.certification import validate_certification_artifact, profile_definition_fingerprint
from tooling.profile_composition import resolve_profile

digest = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: strict_json(path.read_bytes())
projected = base/('candidate-qualification-inputs-'+short)
archives = base/('candidate-original-bytes-'+short)
index_path = archives/'qualification-streams-index.json'
qualification_path = base/'qualification-evidence-projection.json'

def originals():
    rows = json.loads((base/('logs/profiles-'+short+'-qualify-attempt1/progress.json')).read_bytes())
    assert [row['profile'] for row in rows] == ['local','pull-request']
    result = {}
    for row in rows:
        assert row['source'] == source and row['exit_code'] == 0 and not row['nonpassing']
        path = Path(row['artifact']); profile = load(path)
        assert profile['deterministic_evidence']['repository'] == dict(commit=source,dirty=False)
        assert profile['evidence_fingerprint']
        paths = list(path.parent.rglob('*'))
        assert not any(value.is_symlink() for value in paths)
        result[row['profile']] = (path,profile,{value.relative_to(path.parent).as_posix():value for value in paths if value.is_file()})
    return result

def empty_streams(profile):
    expected = set()
    for operation in profile['deterministic_evidence']['operations']:
        integrity = operation.get('execution_integrity')
        if not isinstance(integrity,dict): continue
        assert integrity['source_sha'] == source
        for stream, identity in integrity['streams'].items():
            assert stream in ('stdout','stderr')
            if identity['bytes'] == 0:
                assert identity == dict(path=stream+'.txt',sha256=digest(b''),bytes=0)
                expected.add('operation-results/'+integrity['invocation_id']+'/'+stream+'.txt')
    return expected

def prepare():
    projected.mkdir(exist_ok=False)
    records=[]
    for name,(artifact,profile,files) in originals().items():
        expected=empty_streams(profile)
        for relative,path in sorted(files.items()):
            raw=path.read_bytes(); destination=projected/name/relative
            row=dict(profile=name,original_path=relative,bytes=len(raw),sha256=digest(raw))
            if raw:
                destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(raw)
                row['archive']=None
            else:
                assert relative in expected, 'Empty mandatory qualification data is not a diagnostic stream'
                filename='qualification-'+digest((name+'/'+relative).encode())+'.bytes.json'
                target=archives/filename; assert not target.exists()
                target.write_bytes(encode(raw,path.name,source)); row['archive']=filename
            records.append(row)
    with index_path.open('x') as output:
        output.write(json.dumps(dict(source=source,files=records),indent=2)+'\n')
    return finish()

def finish():
    result=verify()
    # Exercise the unchanged immutable copier against the complete corrected subjects.
    with tempfile.TemporaryDirectory(prefix='strling-qualification-copy-proof-',dir='/var/tmp') as temporary:
        entries=attest._copy_evidence(Path(temporary),[(f'qualification-{name}',projected/name) for name in originals()]+[('sealed-original-metadata',archives)])
        assert all(row['bytes'] > 0 for row in entries)
    with qualification_path.open('x') as output: output.write(json.dumps(result,indent=2)+'\n')
    return result

def verify():
    original=originals(); index=load(index_path)
    assert index['source'] == source
    rows=index['files']; keyed={(row['profile'],row['original_path']):row for row in rows}
    assert len(keyed)==len(rows)
    assert set(keyed)=={(name,relative) for name,(_,_,files) in original.items() for relative in files}
    expected_copies=set(); expected_archives=set(); claims=[]; producers=0
    toolchain=load(root/'toolchain.json')
    with tempfile.TemporaryDirectory(prefix='strling-qualification-raw-reconstruction-',dir='/var/tmp') as temporary:
        restored=Path(temporary)
        for name,(artifact,profile,files) in original.items():
            permitted_empty=empty_streams(profile)
            for relative,path in files.items():
                row=keyed[name,relative]; raw=path.read_bytes()
                assert row['bytes']==len(raw) and row['sha256']==digest(raw)
                if raw:
                    assert row['archive'] is None
                    selected=projected/name/relative
                    assert not selected.is_symlink() and selected.read_bytes()==raw
                    expected_copies.add(name+'/'+relative)
                else:
                    assert relative in permitted_empty
                    filename='qualification-'+digest((name+'/'+relative).encode())+'.bytes.json'
                    assert row['archive']==filename and not (archives/filename).is_symlink()
                    assert decode(load(archives/filename),source)==raw
                    expected_archives.add(filename)
                target=restored/name/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
            copied_profile=restored/name/artifact.name
            checked=load(copied_profile)
            validate_certification_artifact(trusted,checked)
            attest._nested_status_consistency(checked)
            deterministic=checked['deterministic_evidence']
            assert deterministic['repository']==dict(commit=source,dirty=False)
            assert deterministic['component_scope']==dict(mode='profile-default')
            definition=resolve_profile(toolchain['policy'],name)
            identity=deterministic['profile']
            assert identity['id']==name and identity['definition_version']==definition['definition_version']
            assert identity['definition_fingerprint']==profile_definition_fingerprint(definition)
            expected_ids=[]
            registry=toolchain['policy']['operation_registry']
            for member in definition['operations']:
                operation_id=member['operation']; operation=registry[operation_id]
                targets=[operation['component']] if operation['kind']=='repository' else member['targets']
                expected_ids.extend(operation_id+'@'+target for target in targets)
            assert [operation['result_id'] for operation in deterministic['operations']]==expected_ids
            assert deterministic['aggregate']['status']=='passed' and deterministic['aggregate']['exit_code']==0
            for operation in deterministic['operations']:
                contract=registry[operation['operation_id']]
                if contract.get('result_contract') is not None:
                    assert operation['structured_evidence']['operation_id']==contract['result_operation_id']
            claim=dict(profile=name,definition_version=identity['definition_version'],definition_fingerprint=identity['definition_fingerprint'],evidence_fingerprint=checked['evidence_fingerprint'],operation_count=len(expected_ids),status=deterministic['aggregate']['status'],counts=deterministic['aggregate']['counts'])
            claims.append(claim)
            for operation in checked['deterministic_evidence']['operations']:
                integrity=operation.get('execution_integrity')
                if not isinstance(integrity,dict): continue
                directory=restored/name/'operation-results'/integrity['invocation_id']
                context={key:integrity[key] for key in ('schema_version','producer_id','operation_id','source_sha','invocation_id','certification_profile','producer_profile')}
                raw=validate_result_directory(directory,expected_context=context,result_contract=integrity['result_contract'],actual_exit_code=0)
                expected={key:value for key,value in integrity.items() if key not in ('artifact_directory','streams')}
                expected.update(structured_result=operation['structured_evidence'],integrity_error=None)
                assert raw==expected
                for stream,identity in integrity['streams'].items():
                    payload=(directory/(stream+'.txt')).read_bytes()
                    assert identity==dict(path=stream+'.txt',bytes=len(payload),sha256=digest(payload))
                producers+=1
        all_projected=list(projected.rglob('*')); assert not any(path.is_symlink() for path in all_projected)
        assert {path.relative_to(projected).as_posix() for path in all_projected if path.is_file()}==expected_copies
    assert {path.name for path in archives.glob('qualification-*.bytes.json')}==expected_archives
    return dict(status='passed-exact-qualification-profiles-and-independent-producer-reconstruction',source=source,profiles=claims,producer_objects=producers,original_files=len(rows),verbatim_files=len(expected_copies),archived_empty_streams=len(expected_archives),index_sha256=digest(index_path.read_bytes()),helper_sha256=digest(Path(__file__).read_bytes()),private_key_read=False,producer_records_modified=False,publication_authorized=False)

if __name__=='__main__':
    result=verify() if '--verify' in sys.argv else (finish() if '--finish-existing' in sys.argv else prepare())
    if '--verify' in sys.argv: assert result==load(qualification_path)
    print(json.dumps(result),flush=True)
