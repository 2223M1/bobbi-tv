import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from bobbi_platform.ce_installer import MANAGED, program_tree
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import signing, environment, package


def test_actual_local_back_during_ipc_recovery_never_dispatches():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-X', 'utf8', str(root/'tests/repros/ce2047_local_cancel.py'),
        '--repo', str(root), '--expect-dispatches', '0'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr
    assert json.loads(result.stdout)['dispatches'] == []


def test_actual_optional_subtitle_and_final_phase_cancel_both_dispatch_forms():
    result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('ce2048_late_cancel_probe.py'))],
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_shipped_requests_real_header_body_cancel_and_deadline():
    result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('ce2048_http_probe.py'))],
        capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert len(report['cases']) == 14
    assert all(row['workers_at_return'] == 0 for row in report['cases'])


@pytest.mark.parametrize('fault', ['directory', 'missing', 'changed', 'extra', 'mode', 'symlink'])
def test_full_backup_preflight_keeps_live_and_host_untouched(environment, signing, fault):
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    state = env.installer._read()
    old = env.work/state['tx']/'backup'/sorted(MANAGED)[0]
    if fault == 'directory': shutil.rmtree(old)
    elif fault == 'missing': (old/'addon.xml').unlink()
    elif fault == 'changed': (old/'addon.xml').write_text('broken')
    elif fault == 'extra': (old/'unrecorded.py').write_text('extra')
    elif fault == 'mode':
        if sys.platform == 'win32': pytest.skip('POSIX mode is device/Linux coverage')
        (old/'addon.xml').chmod(0o755)
    else:
        try: (old/'injected').symlink_to(env.user)
        except OSError: pytest.skip('Windows symlink privilege unavailable; device covers this')
    before = {name:program_tree(env.addons/name) for name in MANAGED}
    calls, journal = list(env.calls), env.installer.state.read_bytes()
    with pytest.raises((UpdateError, ValueError)):
        env.installer.rollback()
    assert env.calls == calls and env.installer.state.read_bytes() == journal
    assert {name:program_tree(env.addons/name) for name in MANAGED} == before


def test_bytecode_does_not_invalidate_but_extra_source_does(environment, signing):
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    old = env.work/env.installer._read()['tx']/'backup'/sorted(MANAGED)[0]
    pyc = old/'__pycache__'; pyc.mkdir(); (pyc/'default.cpython-311.pyc').write_bytes(b'cache')
    env.installer.rollback()
    assert env.installer._read()['phase'] == 'restored'


def test_legacy_terminal_without_receipt_can_upgrade_but_not_invent_rollback_proof(environment, signing):
    env = environment
    env.installer.apply(package(env.root/'one.zip', signing))
    env.installer.apply(package(env.root/'two.zip', signing, 2, '2.0.0'))
    state = env.installer._read()
    for row in state['items']: row.pop('old_tree', None)
    env.installer._write(state)
    assert not env.installer.recover()
    calls = list(env.calls)
    with pytest.raises(UpdateError, match='RECEIPT_REQUIRED'): env.installer.rollback()
    assert env.calls == calls
    env.installer.apply(package(env.root/'three.zip', signing, 3, '3.0.0'))
    env.installer.rollback()
    assert all('2.0.0' in (env.addons/name/'addon.xml').read_text() for name in MANAGED)
