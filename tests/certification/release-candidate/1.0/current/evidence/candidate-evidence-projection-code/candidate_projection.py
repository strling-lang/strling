"""Preserve exact nested inputs and SDK logs with the qualified byte codec."""
from pathlib import Path,PurePosixPath
import copy,hashlib,json,shutil,subprocess,sys
from release_campaign_config import configuration
base,main,source,short=configuration()
trusted=Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
assert subprocess.check_output(['git','-C',str(trusted),'rev-parse','HEAD'],text=True).strip()=='f8ef1a62be536981927e36a19587f96edb69f911'
assert not subprocess.check_output(['git','-C',str(trusted),'status','--porcelain']).strip()
sys.path.insert(0,str(trusted))
from tooling.evidence_bytes import encode,decode
from tooling.public_distribution import strict_json

def digest(data):return hashlib.sha256(data).hexdigest()
def exact(path,row):
 assert path.is_file() and not path.is_symlink()
 raw=path.read_bytes();assert len(raw)==row['bytes'] and digest(raw)==row['sha256'];return raw
def safe(relative):
 value=PurePosixPath(relative)
 assert not value.is_absolute() and value.parts and '..' not in value.parts and '\\' not in relative and ':' not in relative
 return value
def prepare():
 original=base/('public-staged-proof-'+short)
 projection=base/('candidate-public-proof-'+short)
 archives=base/('candidate-original-bytes-'+short)
 projection.mkdir(exist_ok=False);archives.mkdir(exist_ok=False)
 policy=strict_json((main/'governance/repository-hygiene.json').read_bytes())
 def archive(raw,name,target):
  assert not any(marker.encode() in raw for marker in policy['private_key_markers'])
  encoded=encode(raw,name,source);assert decode(strict_json(encoded),source)==raw
  target.write_bytes(encoded)
 proof_raw=(original/'proof.json').read_bytes();proof=strict_json(proof_raw)
 assert proof['source']==source and proof['status']=='passed-current-source-staged-qualification' and not proof['public_release_verified'] and not proof['publication_authorized']
 archive(proof_raw,'public-proof.json',archives/'original-public-proof.bytes.json')
 entries=[];selected_logs=[]
 for row in proof['evidence_files']:
  relative=safe(row['path']);raw=exact(original/relative,row);data=raw
  if relative.name=='preparation.log':
   assert relative.as_posix() in ('prerequisites/dart/preparation.log','prerequisites/kotlin/preparation.log')
   assert not any(marker.encode() in raw for marker in policy['private_key_markers'])
   selected_logs.append(relative.as_posix());relative=relative.with_name('preparation-output.json');data=encode(raw,'preparation.log',source)
  target=projection/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  entries.append(dict(path=relative.as_posix(),bytes=len(data),sha256=digest(data)))
 assert sorted(selected_logs)==['prerequisites/dart/preparation.log','prerequisites/kotlin/preparation.log']
 projected=copy.deepcopy(proof);projected['evidence_files']=entries
 projected['transport_projection']=dict(original_proof_sha256=digest(proof_raw),diagnostic_bytes_preserved=True,normalization_applied=False)
 (projection/'proof.json').write_text(json.dumps(projected,indent=2)+'\n')
 package=base/('signed-package-candidate-'+short)
 payload=strict_json((package/'attestation.json').read_bytes())['signed_payload']
 assert payload['certified_source']['commit']==source and payload['certified_source']['clean'] is True
 for row in payload['evidence_files']:
  relative=safe(row['path']);raw=exact(package/relative,row)
  target=archives/('package-'+digest(raw)+'.bytes.json')
  if target.exists():assert decode(strict_json(target.read_bytes()),source)==raw
  else:archive(raw,'evidence-'+digest(raw)+'.bin',target)
 return verify()
def verify():
 projection=base/('candidate-public-proof-'+short);archives=base/('candidate-original-bytes-'+short)
 original_bytes=decode(strict_json((archives/'original-public-proof.bytes.json').read_bytes()),source)
 original=strict_json(original_bytes);projected=strict_json((projection/'proof.json').read_bytes())
 plain=copy.deepcopy(projected);transport=plain.pop('transport_projection');plain['evidence_files']=original['evidence_files']
 assert plain==original and transport==dict(original_proof_sha256=digest(original_bytes),diagnostic_bytes_preserved=True,normalization_applied=False)
 expected={}
 for row in original['evidence_files']:
  relative=safe(row['path'])
  if relative.name=='preparation.log':
   relative=relative.with_name('preparation-output.json');data=(projection/relative).read_bytes();raw=decode(strict_json(data),source)
   assert len(raw)==row['bytes'] and digest(raw)==row['sha256']
  else:data=exact(projection/relative,row)
  expected[relative.as_posix()]=dict(path=relative.as_posix(),bytes=len(data),sha256=digest(data))
 assert {row['path']:row for row in projected['evidence_files']}==expected
 assert not any(p.is_symlink() for p in projection.rglob('*'))
 assert {p.relative_to(projection).as_posix() for p in projection.rglob('*') if p.is_file()}==set(expected)|{'proof.json'}
 package=base/('signed-package-candidate-'+short);payload=strict_json((package/'attestation.json').read_bytes())['signed_payload']
 assert payload['certified_source']['commit']==source
 for row in payload['evidence_files']:
  raw=decode(strict_json((archives/('package-'+row['sha256']+'.bytes.json')).read_bytes()),source)
  assert len(raw)==row['bytes'] and digest(raw)==row['sha256'] and raw==exact(package/safe(row['path']),row)
 return dict(status='passed-lossless-candidate-evidence-projection',source=source,original_proof_sha256=digest(original_bytes),projected_proof_sha256=digest((projection/'proof.json').read_bytes()),nested_package_root=payload['evidence_root_sha256'],nested_package_files=len(payload['evidence_files']),coverage_unchanged=True,artifact_routes=projected['artifact_routes'],consumer_scopes=projected['supported_consumer_scopes'],obligations=projected['public_obligations'],helper_sha256=digest(Path(__file__).read_bytes()),codec_sha256=digest((trusted/'tooling/evidence_bytes.py').read_bytes()),product_artifact_normalization_applied=False,private_key_read=False,publication_authorized=False)
if __name__=='__main__':
 result=verify() if '--verify' in sys.argv else prepare()
 if '--verify' not in sys.argv:
  with (base/'candidate-projection-qualification.json').open('x') as output:json.dump(result,output,indent=2);output.write('\n')
 print(json.dumps(result),flush=True)
