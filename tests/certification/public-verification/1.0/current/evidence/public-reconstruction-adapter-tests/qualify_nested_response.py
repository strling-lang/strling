"""Reproduce the response mismatch and reject adversarial envelope mutations."""
from pathlib import Path
import copy
import hashlib
import json
from reconstruct_nested_package import verified_evidence

base=Path(__file__).resolve().parent
source='3e7061271d906251cb17c3eb06b6c748ac3068e7'
response=base/'unsigned-reconstruction-3e706127-e689f4ca1510448b825117c2de3a14d8/nested-package-verification.stdout'
document=json.loads(response.read_text())
path=base/'signed-package-candidate-3e706127/attestation.json'
data=path.read_bytes(); attestation=json.loads(data); digest=hashlib.sha256(data).hexdigest()
try: document['certified_source_sha']
except KeyError: reproduced=True
else: raise AssertionError('Original adapter failure was not reproduced')
verified_evidence(document,attestation,source,digest)
mutations={
    'schema':lambda d:d.update(schema_version='incorrect'),
    'operation':lambda d:d.update(operation_id='incorrect'),
    'status':lambda d:d.update(status='failed'),
    'aggregate-failure':lambda d:d['summary'].update(failed=1),
    'aggregate-missing-pass':lambda d:d['summary'].update(passed=0),
    'missing-producer':lambda d:d.pop('checks'),
    'duplicate-producer':lambda d:d['checks'].append(copy.deepcopy(d['checks'][0])),
    'incorrect-check':lambda d:d['checks'][0].update(check_id='incorrect'),
    'failed-check':lambda d:d['checks'][0].update(status='failed'),
    'missing-evidence':lambda d:d['checks'][0].pop('evidence'),
}
for field in ('certified_source_sha','verified_head_sha','evidence_root_sha256','attestation_sha256','signature_sha256','certifier_id','profile_results','waiver_inventory'):
    mutations['substituted-'+field]=lambda d,f=field:d['checks'][0]['evidence'].update({f:'incorrect'})
rejected=[]
for name,mutate in mutations.items():
    changed=copy.deepcopy(document); mutate(changed)
    try: verified_evidence(changed,attestation,source,digest)
    except ValueError: rejected.append(name)
    else: raise AssertionError('Adversarial response accepted: '+name)
report=dict(status='passed-actual-immutable-response-and-adversarial-mutations',source=source,
    reproduced_original_key_error=reproduced,positive_actual_response=True,rejected_mutations=rejected,
    response_sha256=hashlib.sha256(response.read_bytes()).hexdigest(),attestation_sha256=digest,
    original_adapter_sha256=hashlib.sha256((base/'operational-amendment-originals/nested-verifier-response/reconstruct_nested_package.py').read_bytes()).hexdigest(),
    adapter_sha256=hashlib.sha256((base/'reconstruct_nested_package.py').read_bytes()).hexdigest(),
    frozen_source_changed=False,private_key_read=False,signature_created=False,publication_authorized=False)
(base/'nested-verifier-response-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
