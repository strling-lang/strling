"""Retain one exclusive, foreground owner for a post-profile evidence step."""
from pathlib import Path
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from continuity_io import write_json
from release_campaign_config import configuration

parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=('audit-package', 'sign-package', 'projection', 'audit-candidate', 'diagnose-selection', 'sign-candidate', 'handoff', 'verify-handoff'))
parser.add_argument('--audit', type=Path)
parser.add_argument('--attempt', type=int, default=1)
args = parser.parse_args()
assert args.attempt > 0
base, main, source, short = configuration()
root = Path('/var/tmp/strling-release-candidate-' + short + '-certification')
trusted = Path('/var/tmp/strling-candidate-verifier-f8ef1a62')
load = lambda path: json.loads(path.read_bytes())
full_rows = load(base / ('logs/profiles-' + short + '-full-attempt1/progress.json'))
assert len(full_rows) == 1
full_result = full_rows[0]
release_result = load(base / ('logs/production-' + short + '-attempt1/terminal.json'))
denominators = load(base / 'candidate-freeze.json')['scope']['profile_denominators']
for profile, result in (('full', full_result), ('release', release_result)):
    assert result['source'] == source and result['exit_code'] == 0
    summary = result['summary']
    assert summary['total'] == denominators[profile]
    assert summary['passed'] + summary['waived'] == summary['total']
    assert not any(summary.get(key, 0) for key in ('failed', 'unavailable', 'incomplete'))
full = Path(full_result['artifact'])
release = Path(release_result['profile'])
assert full.is_file() and release.is_file()
common = ['--full', str(full), '--release', str(release)]
commands = {
    'audit-package': [sys.executable, str(base / 'package_audit_final_evidence.py'), *common, '--full-bundle', str(base / ('supply-chain-' + short + '-full')), '--release-bundle', str(base / ('supply-chain-' + short + '-release'))],
    'projection': [sys.executable, str(base / 'candidate_projection.py')],
    'audit-candidate': [sys.executable, str(base / 'audit_candidate_evidence.py'), *common],
    'diagnose-selection': [sys.executable, str(base / 'diagnose_candidate_selection.py')],
}
if args.stage in ('sign-package', 'sign-candidate'):
    assert args.audit is not None and args.audit.is_file()
    helper = 'package_sign_certified_source.py' if args.stage == 'sign-package' else 'sign_candidate_evidence.py'
    commands[args.stage] = [sys.executable, str(base / helper), '--audit', str(args.audit.resolve()), *common]
    if args.stage == 'sign-candidate':
        commands[args.stage].extend(['--attempt', str(args.attempt)])
handoff = base / 'final-release-candidate-handoff.json'
handoff_command = [sys.executable, '-I', '-B', str(trusted / 'tooling/candidate_integrity.py'), '--repository-root', str(root), '--trust-root', str(trusted), '--bundle', str(base / ('signed-release-candidate-' + short)), '--handoff', str(handoff), '--json']
commands['handoff'] = [*handoff_command, '--write-handoff']
commands['verify-handoff'] = handoff_command
lock = open('/var/tmp/strling-public-verification-controller.lock', 'a+')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
out = base / 'logs' / (args.stage + '-owner-attempt' + str(args.attempt))
out.mkdir(exist_ok=False)
owner = dict(pid=os.getpid(), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), start_ticks=Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19], source=source, lease='/var/tmp/strling-public-verification-controller.lock', controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
write_json(out / 'owner.json', owner)
(out / 'controller.py').write_bytes(Path(__file__).read_bytes())
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
os.nice(10)
previous = load(base / 'continuation.json')

def identity():
    for directory in (root, main):
        assert subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip() == source
        assert not subprocess.check_output(['git', '-C', str(directory), 'status', '--porcelain']).strip()

def save(child=None, terminal=None, error=None):
    active = child is not None and child.poll() is None
    record = dict(state='CERTIFYING' if active else 'ENGINEERING_REQUIRED', current_source_sha=source, execution_owner=owner if active else None, source_lease=owner['lease'] if active else None, current_stage=args.stage, current_operation=args.stage, child_pid=child.pid if active else None, healthy_worker_active=active, controller_waiting_for_protected_owner=False, last_accepted_checkpoint=(str(out / 'terminal.json') if terminal and terminal['exit_code'] == 0 else previous['last_accepted_checkpoint']), terminal_logs=str(out), pending_mandatory=['remaining independent evidence reconstruction and original-authority signing', 'all staged public and consumer qualification', 'candidate signing and whole-object handoff', 'actual four-job hosted verification and formal closure'], active_blockers=[error] if error else [], next_action='Inspect actual terminal evidence and run the next dependency-ready evidence step', physical_d_free_bytes=shutil.disk_usage(main).free, wsl_free_bytes=shutil.disk_usage('/').free, updated_utc=dt.datetime.now(dt.UTC).isoformat(), publication_authorized=False)
    if terminal:
        record['stage_terminal'] = terminal
    write_json(base / 'continuation.json', record)
    write_json(main / 'target/release-candidate/preparation-d2844467/continuation.json', record)

child = None
try:
    identity()
    command = commands[args.stage]
    write_json(out / 'request.json', dict(source=source, command=command, publication_authorized=False))
    started = time.monotonic()
    with (out / 'stdout').open('x') as stdout, (out / 'stderr').open('x') as stderr:
        child = subprocess.Popen(command, cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), stdout=stdout, stderr=stderr)
        while child.poll() is None:
            save(child)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    terminal = dict(source=source, stage=args.stage, exit_code=child.returncode, seconds=time.monotonic()-started, publication_authorized=False)
    write_json(out / 'terminal.json', terminal)
    identity()
    save(terminal=terminal, error='Actual evidence step failed; retain original output' if child.returncode else None)
    print(json.dumps(terminal), flush=True)
    raise SystemExit(child.returncode)
except SystemExit:
    raise
except BaseException as error:
    save(child=child, error=repr(error))
    raise
