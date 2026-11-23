import json
from pathlib import Path
import subprocess
import sys

import pytest

from bobbi_platform.ce_installer import MANAGED, blocked
from bobbi_platform.updates import UpdateError
from ce_install_faults import installer
from test_ce_general_installer import signing, package


@pytest.fixture
def installed(tmp_path, signing):
    (tmp_path / 'trust.json').write_text(json.dumps(signing[1]))
    actor = installer(tmp_path)
    actor.apply(package(tmp_path / 'one.zip', signing, 1))
    # Preserve a deliberately mixed user enable vector and custom skin.
    actor.host.write(dict(enabled=sorted(MANAGED)[::2], skin='skin.before'))
    (tmp_path / 'user-history').write_text('new user data')
    package(tmp_path / 'two.zip', signing, 2, '2.0.0')
    return actor


def crash(actor, operation, fault):
    result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('ce_install_faults.py')),
        str(actor.addons.parent), operation, fault], capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stdout + result.stderr


@pytest.mark.parametrize('fault', ['phase:staged', 'phase:switching', 'move',
    'phase:activation_pending'] + ['activate:%d' % i for i in range(len(MANAGED))] + ['phase:complete'])
def test_real_process_loss_install_boundaries_reenter(installed, fault):
    actor = installed
    before = actor.host.read()
    crash(actor, 'apply', fault)
    pending = actor._read()['phase']
    assert blocked(actor.work) == (pending in ('staged', 'switching'))
    resumed = installer(actor.addons.parent)
    resumed.recover()
    expected = '1.0.0' if pending in ('staged', 'switching') else '2.0.0'
    assert all(expected in (actor.addons / n / 'addon.xml').read_text() for n in MANAGED)
    if expected == '1.0.0':
        assert resumed.host.read() == before
    else:
        assert set(resumed.host.enabled()) == MANAGED
        assert resumed._read()['high_watermark'] == 2
    assert not blocked(actor.work)
    assert not resumed.recover()
    assert (actor.addons.parent / 'user-history').read_text() == 'new user data'


@pytest.mark.parametrize('fault', ['phase:restoring', 'move', 'host:restore'] +
    ['restore:%d' % i for i in range(len(MANAGED))] + ['skin', 'phase:restored'])
def test_real_process_loss_restore_boundaries_reenter(installed, fault):
    actor = installed
    before = actor.host.read()
    actor.apply(actor.addons.parent / 'two.zip')
    crash(actor, 'rollback', fault)
    pending = actor._read()['phase']
    assert blocked(actor.work) == (pending == 'restoring')
    resumed = installer(actor.addons.parent)
    resumed.recover()
    assert resumed.host.read() == before
    assert all('1.0.0' in (actor.addons / n / 'addon.xml').read_text() for n in MANAGED)
    assert resumed._read()['phase'] == 'restored'
    assert resumed._read()['high_watermark'] == 2
    assert not resumed.recover()
    assert (actor.addons.parent / 'user-history').read_text() == 'new user data'
    with pytest.raises(UpdateError, match='GENERATION_NOT_NEWER'):
        resumed.apply(actor.addons.parent / 'two.zip')


@pytest.mark.parametrize('operation', ['activate', 'restore'])
def test_transient_rpc_failure_is_not_a_completed_transaction(installed, operation):
    actor = installed
    before = actor.host.read()
    if operation == 'restore': actor.apply(actor.addons.parent / 'two.zip')
    setattr(actor.host, operation + '_fail', True)
    with pytest.raises(RuntimeError, match='one RPC failure'):
        if operation == 'activate': actor.apply(actor.addons.parent / 'two.zip')
        else: actor.rollback()
    if operation == 'activate': assert actor._read()['phase'] == 'activation_pending'
    else:
        assert actor._read()['phase'] == 'restored'
        assert actor._read()['host_pending'] == 'restore'
        with pytest.raises(UpdateError, match='INSTALLATION_RECOVERY_REQUIRED'):
            actor.apply(actor.addons.parent / 'two.zip')
    assert not blocked(actor.work)
    resumed = installer(actor.addons.parent)
    assert resumed.recover()
    assert not resumed.recover()
    if operation == 'restore': assert resumed.host.read() == before
    else: assert set(resumed.host.enabled()) == MANAGED


@pytest.mark.parametrize('operation', ['activate', 'restore'])
def test_silent_rpc_noop_requires_readback_and_recovery(installed, operation):
    actor = installed
    if operation == 'restore': actor.apply(actor.addons.parent / 'two.zip')
    setattr(actor.host, operation, lambda *args: None)
    with pytest.raises(UpdateError, match='NOT_CONFIRMED'):
        if operation == 'activate': actor.apply(actor.addons.parent / 'two.zip')
        else: actor.rollback()
    assert installer(actor.addons.parent).recover()


def test_old_terminal_journal_remains_compatible(installed):
    # Existing CE2009 terminal journals are not guessed to be partial installs.
    assert installed._read()['schema'] == 1
    assert installed._read()['phase'] == 'complete'
    assert not installed.recover()


def test_intermediate_pending_restore_is_normalized_before_old_service_boot(installed):
    actor = installed
    actor.apply(actor.addons.parent / 'two.zip')
    actor.host.restore_fail = True
    with pytest.raises(RuntimeError): actor.rollback()
    state = actor._read()
    state.pop('host_pending')
    state['phase'] = 'restore_pending'
    actor._write(state)
    assert installer(actor.addons.parent).recover()
    assert installer(actor.addons.parent)._read()['phase'] == 'restored'
