"""Run the unchanged frozen hygiene scanner at prospective certificate paths."""
from pathlib import Path
import hashlib,json,sys
root=Path('/var/tmp/strling-public-1838ba89-certification')
sys.path.insert(0,str(root))
from tooling.hygiene import Entry,load_policy,scan,tracked_entries
evidence=Path(sys.argv[1]);entries=json.loads(Path(sys.argv[2]).read_text())
prefix='tests/certification/public-verification/1.0/current/'
mapping={prefix+row['path']:evidence/row['path'] for row in entries}
class Overlay:
    def __truediv__(self,path):return mapping.get(str(path),root/str(path))
existing=tracked_entries(root)
assert not any(entry.path.startswith(prefix) for entry in existing)
policy=load_policy(root/'governance/repository-hygiene.json',root)
findings=scan(policy,[*existing,*(Entry(path,'100644') for path in mapping)],root=Overlay())
result=dict(status='failed' if findings else 'passed',source='3e7061271d906251cb17c3eb06b6c748ac3068e7',
    policy_sha256=hashlib.sha256((root/'governance/repository-hygiene.json').read_bytes()).hexdigest(),
    evidence_files=len(entries),findings=[dict(rule=f.rule,path=f.path,message=f.message) for f in findings],normalization_applied=False)
print(json.dumps(result));raise SystemExit(1 if findings else 0)
