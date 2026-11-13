"""Qualify unique-role signing without changing any selected evidence identity."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from release_campaign_config import configuration

base,main,source,short=configuration()
trusted=Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
pin='f8ef1a62be536981927e36a19587f96edb69f911'
assert subprocess.check_output(['git','-C',str(trusted),'rev-parse','HEAD'],text=True).strip()==pin
sys.path.insert(0,str(trusted))
from tooling.evidence_bytes import encode
from tooling.local_certification_attestation import _copy_evidence, _parse_evidence_argument
from candidate_role_groups import prepare_group,verify_group
from audited_signing_arguments import supplemental_arguments

began=time.monotonic();cases=[]
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()

def fixture(root):
    originals=root/'originals';originals.mkdir()
    files=[]
    for index in range(2):
        path=originals/(str(index)+'.bytes.json')
        path.write_bytes(encode(('original-'+str(index)+'\r\n').encode(),'fixture-'+str(index),source))
        files.append(path)
    group=prepare_group('sealed-original-metadata',files,root/'group',source)
    return files,group

with tempfile.TemporaryDirectory(prefix='strling-role-group-positive-',dir='/var/tmp') as temp:
    root=Path(temp);files,group=fixture(root)
    automatic=[]
    for role in ('profile-full','profile-release','release-supply-chain'):
        path=root/(role+'.json');path.write_bytes(b'{"fixture":true}\n');automatic.append((role,path))
    flat=[*automatic,*[('sealed-original-metadata',path) for path in files]]
    try:supplemental_arguments(flat)
    except ValueError as error:
        assert 'Duplicate supplemental evidence role' in str(error)
        cases.append('reproduce-strict-adapter-duplicate-role-refusal')
    else:raise AssertionError('Original duplicate roles admitted')
    grouped=[*automatic,('sealed-original-metadata',group)]
    arguments=supplemental_arguments(grouped)
    assert arguments[::2]==['--evidence','--evidence']
    parsed=[_parse_evidence_argument(value) for value in arguments[1::2]]
    assert [role for role,_ in parsed]==['release-supply-chain','sealed-original-metadata']
    for label,inputs in (('flat',flat),('grouped',grouped),('cli',[*automatic[:2],*parsed])):
        out=root/label;out.mkdir();entries=_copy_evidence(out,inputs)
        if label=='flat':expected=entries
        else:assert entries==expected
    cases.extend(['unique-role-cli-round-trip','immutable-copier-identical-path-role-size-and-sha256'])
    for label,inputs in (
        ('reject-duplicate-supply-boundary',[*automatic,automatic[-1]]),
        ('reject-reordered-automatic-profiles',[automatic[1],automatic[0],automatic[2]]),
        ('reject-unknown-duplicate-role',[*automatic,('unexpected',files[0]),('unexpected',files[1])]),
    ):
        try:supplemental_arguments(inputs)
        except ValueError:cases.append(label)
        else:raise AssertionError(label)

def wrong_source(files,group):
    data=encode(b'unchanged','fixture','b'*40)
    files[0].write_bytes(data);(group/files[0].name).write_bytes(data)

negative={
    'reject-duplicate-basename':lambda files,group:(files.append(files[0])),
    'reject-omitted-source-member':lambda files,group:files.pop(),
    'reject-missing-group-member':lambda files,group:(group/files[0].name).unlink(),
    'reject-extra-group-member':lambda files,group:(group/'extra.json').write_bytes(b'{}\n'),
    'reject-modified-group-bytes':lambda files,group:(group/files[0].name).write_bytes(b'{}\n'),
    'reject-normalized-container-bytes':lambda files,group:(group/files[0].name).write_bytes(files[0].read_bytes().replace(b'\n',b'\r\n')),
    'reject-substituted-source-in-both-copies':wrong_source,
    'reject-nested-unselected-member':lambda files,group:(group/'nested').mkdir(),
}
for label,mutate in negative.items():
    with tempfile.TemporaryDirectory(prefix='strling-role-group-negative-',dir='/var/tmp') as temp:
        files,group=fixture(Path(temp));mutate(files,group)
        try:verify_group('sealed-original-metadata',files,group,source)
        except (AssertionError,ValueError,FileNotFoundError,KeyError):cases.append(label)
        else:raise AssertionError(label)
for target in ('original','group-member','group-root'):
    with tempfile.TemporaryDirectory(prefix='strling-role-group-link-',dir='/var/tmp') as temp:
        files,group=fixture(Path(temp))
        link=files[0] if target=='original' else group/files[0].name if target=='group-member' else group
        retained=link.with_name(link.name+'.retained');link.rename(retained);link.symlink_to(retained)
        try:verify_group('sealed-original-metadata',files,group,source)
        except AssertionError:cases.append('reject-'+target+'-symlink')
        else:raise AssertionError('Linked group admitted')

def metadata_ast(path):
    return ast.dump(next(node for node in ast.parse(path.read_bytes()).body if isinstance(node,ast.FunctionDef) and node.name=='preserved_metadata'))
assert metadata_ast(base/'candidate_evidence_inputs.py')==metadata_ast(base/'retained-input-selection-before-grouping.py')
cases.append('previously-qualified-metadata-selector-ast-unchanged')
signing=ast.parse((base/'sign_candidate_evidence.py').read_bytes())
plans=[node.lineno for node in ast.walk(signing) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='supplemental_arguments']
private=[node.lineno for node in ast.walk(signing) if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='private' for target in node.targets)]
assert len(plans)==len(private)==1 and plans[0]<private[0]
assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='supplemental_arguments' for block in signing.body if isinstance(block,ast.With) for node in ast.walk(block))
cases.append('argument-plan-before-private-key-inspection-and-copy')
probe='''import json,runpy,sys
from pathlib import Path
base=Path(sys.argv[1]);touched=[]
sys.path.insert(0,str(base))
def hook(event,args):
 if event=='open' and 'h08-certifier' in str(args[0]):
  touched.append(str(args[0]));raise RuntimeError('private key access attempted')
sys.addaudithook(hook)
sys.argv=[str(base/'sign_candidate_evidence.py'),'--audit','/nonexistent-audit','--full','/nonexistent-full','--release','/nonexistent-release','--attempt','0']
try:runpy.run_path(sys.argv[0],run_name='__main__')
except AssertionError:pass
else:raise AssertionError('Invalid signing attempt admitted')
assert not touched
print(json.dumps(dict(status='rejected-before-key-access',private_key_access_attempted=False)))
'''
tested=subprocess.run([sys.executable,'-B','-c',probe,str(base)],capture_output=True,text=True)
assert tested.returncode==0,tested.stdout+tested.stderr
assert json.loads(tested.stdout)['private_key_access_attempted'] is False
cases.append('actual-signing-entrypoint-invalid-attempt-rejected-before-key-access')

archives=base/('candidate-original-bytes-'+short)
archive_files=sorted(archives.glob('*.bytes.json'))
indices=[archives/'preview-diagnostics-index.json',archives/'qualification-streams-index.json']
groups=[]
for role,files,name in (
    ('sealed-original-metadata',archive_files,'candidate-sealed-inputs-'),
    ('candidate-evidence-byte-index',indices,'candidate-index-inputs-'),
):
    directory=base/(name+short)
    if directory.exists():verify_group(role,files,directory,source)
    else:prepare_group(role,files,directory,source)
    groups.append((role,directory))
with tempfile.TemporaryDirectory(prefix='strling-current-role-equivalence-',dir='/var/tmp') as temp:
    root=Path(temp);left=root/'flat';left.mkdir();right=root/'grouped';right.mkdir()
    flat=_copy_evidence(left,[*[('sealed-original-metadata',path) for path in archive_files],*[('candidate-evidence-byte-index',path) for path in indices]])
    grouped=_copy_evidence(right,groups)
    assert flat==grouped
    cases.append('all-current-archive-and-index-identities-unchanged')
result=dict(status='passed-real-copier-and-signing-role-grouping',source=source,qualified_verifier=pin,
            cases=cases,count=len(cases),grouped_evidence_files=len(grouped),
            selector_sha256=digest(base/'candidate_evidence_inputs.py'),
            grouping_code_sha256=digest(base/'candidate_role_groups.py'),
            signing_code_sha256=digest(base/'sign_candidate_evidence.py'),
            evidence_step_code_sha256=digest(base/'run_evidence_step.py'),
            strict_arguments_code_sha256=digest(base/'audited_signing_arguments.py'),
            qualification_code_sha256=digest(Path(__file__)),
            grouped_entries_sha256=hashlib.sha256(json.dumps(grouped,sort_keys=True).encode()).hexdigest(),
            original_entry_paths_roles_sizes_and_hashes_unchanged=True,private_key_read=False,
            metadata_normalized=False,publication_authorized=False,seconds=time.monotonic()-began)
output=base/'candidate-role-group-qualification.json';assert not output.exists()
output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
