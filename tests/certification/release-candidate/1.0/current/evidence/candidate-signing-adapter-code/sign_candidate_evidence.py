"""Use the original certifier only after complete unchanged candidate reconstruction."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,shutil,stat,subprocess,sys,tempfile,time
from release_campaign_config import configuration
from candidate_evidence_inputs import extra_inputs
from audited_signing_arguments import supplemental_arguments
base,main,source,short=configuration()
root=Path('/var/tmp/strling-release-candidate-'+short+'-certification')
trusted=Path('/var/tmp/strling-candidate-verifier-f8ef1a62');pin='f8ef1a62be536981927e36a19587f96edb69f911'
parser=argparse.ArgumentParser();parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--full',type=Path,required=True);parser.add_argument('--release',type=Path,required=True)
parser.add_argument('--attempt',type=int,default=1)
args=parser.parse_args();audit_path=args.audit.resolve();full=args.full.resolve();release=args.release.resolve()
assert args.attempt>0
for directory,sha in ((main,source),(root,source),(trusted,pin)):
 assert subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'],text=True).strip()==sha
 assert not subprocess.check_output(['git','-C',str(directory),'status','--porcelain']).strip()
sys.path.insert(0,str(trusted))
from tooling import local_certification_attestation as attest
load=lambda path:json.loads(Path(path).read_bytes())
def identity(path):
 assert path.is_file() and not path.is_symlink()
 return dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
audit=load(audit_path)
assert audit['status']=='passed-key-free-independent-candidate-reconstruction' and audit['source']==source and audit['qualified_verifier']==pin and audit['source_distinct']
assert audit['private_key_read'] is False and audit['signature_created'] is False and audit['publication_authorized'] is False and audit['public_release_verified'] is False
assert audit['candidate']['status']=='passed' and audit['candidate']['source']==source
assert audit['prospective_hygiene']['status']=='passed' and audit['prospective_hygiene']['source']==source
assert audit['input_selection_sha256']==hashlib.sha256((base/'candidate_evidence_inputs.py').read_bytes()).hexdigest()
projection=load(base/'candidate-projection-qualification.json')
assert projection==audit['projection'] and projection['status']=='passed-lossless-candidate-evidence-projection'
inputs=[('profile-full',full),('profile-release',release),*attest._production_evidence_inputs(release),*attest._execution_evidence_inputs(root,full,release),*extra_inputs(base,main,source,full,release)]
entries=[]
for role,supplied in inputs:
 assert supplied.exists() and not supplied.is_symlink()
 paths=[supplied] if supplied.is_file() else sorted(path for path in supplied.rglob('*') if path.is_file())
 assert not supplied.is_dir() or not any(path.is_symlink() for path in supplied.rglob('*'))
 for path in paths:
  suffix=Path(path.name) if supplied.is_file() else path.relative_to(supplied)
  relative=(PurePosixPath('evidence')/role/PurePosixPath(suffix.as_posix())).as_posix()
  entries.append(dict(path=relative,role=role,**identity(path)))
entries.sort(key=lambda row:row['path'])
assert entries==audit['evidence_files'],'Original inputs changed after the complete key-free audit'
for row in entries:assert identity(audit_path.parent/'evidence-root'/row['path'])=={key:row[key] for key in ('bytes','sha256')}
signing_arguments=supplemental_arguments(inputs)
trust=attest.validate_contract(root,trusted,'release-candidate-certification-trust.json')
certifier=attest._certifier(trust,'strling-local-release-certifier-2026-01')
assert certifier['ssh_key_fingerprint']=='SHA256:ZebV/h+7zLn9D6T4tUO0tI62oHiJV54iGWqmYla7oBA'
logs=base/('logs/candidate-signing-'+short+('' if args.attempt==1 else '-attempt'+str(args.attempt)));logs.mkdir(exist_ok=False)
output=base/('signed-release-candidate-'+short);assert not output.exists()
(logs/'key-free-admission.json').write_text(json.dumps(dict(source=source,qualified_verifier=pin,audit=str(audit_path),audit_identity=identity(audit_path),evidence_files=len(entries),private_key_read=False,signature_created=False,publication_authorized=False),indent=2)+'\n')
steps=[]
def run(label,command):
 started=time.monotonic()
 with (logs/(label+'.stdout')).open('x') as stdout,(logs/(label+'.stderr')).open('x') as stderr:
  completed=subprocess.run(command,cwd=root,stdout=stdout,stderr=stderr)
 steps.append(dict(stage=label,exit_code=completed.returncode,seconds=time.monotonic()-started))
 assert completed.returncode==0,'Actual signing/verification failed; original output retained'
 return load(logs/(label+'.stdout'))
# No approved private material is inspected until every gate above has passed.
private=main/'target/codex-tools/h08-certifier'
assert private.is_file() and not private.is_symlink();before=private.stat()
metadata=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_size,value.st_mtime_ns)
common=[sys.executable,'-I','-B',str(trusted/'tooling/local_certification_attestation.py'),'--repository-root',str(root),'--trust-root',str(trusted),'--trust-policy','release-candidate-certification-trust.json']
with tempfile.TemporaryDirectory(prefix='strling-candidate-original-certifier-',dir='/var/tmp') as temporary:
 directory=Path(temporary);assert stat.S_IMODE(directory.stat().st_mode)==0o700 and directory.stat().st_uid==os.getuid()
 key=directory/'certifier';shutil.copyfile(private,key);os.chmod(key,0o600);assert stat.S_IMODE(key.stat().st_mode)==0o600
 signed=run('attest',[*common,'attest','--full-artifact',str(full),'--release-artifact',str(release),*signing_arguments,'--private-key',str(key),'--certifier-id',certifier['certifier_id'],'--output-dir',str(output),'--json'])
assert not directory.exists() and metadata(before)==metadata(private.stat())
assert signed['status']=='passed' and signed['certified_source_sha']==source
assert load(output/'attestation.json')['signed_payload']['evidence_files']==entries
verified=run('verify',[*common,'verify','--bundle',str(output),'--json'])
assert verified['status']=='passed' and all(row['status']=='passed' for row in verified['checks'])
terminal=dict(status='passed-original-key-candidate-signature-and-source-distinct-verification',source=source,qualified_verifier=pin,evidence_root_sha256=signed['evidence_root_sha256'],signature_sha256=signed['signature_sha256'],bundle=str(output),steps=steps,original_key_preserved=True,ephemeral_key_removed=True,actual_cloud_execution=False,public_release_verified=False,publication_authorized=False)
(logs/'terminal.json').write_text(json.dumps(terminal,indent=2)+'\n');print(json.dumps(terminal),flush=True)
