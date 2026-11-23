"""Cross the stock skin-confirmation window before disturbing a live cinema."""
from types import SimpleNamespace as NS

import pytest
from bobbi_platform import ce_install_ui as ui, runtime
from test_ce_general_installer import environment, signing, package


@pytest.mark.parametrize('outcome', ['keep', 'decline', 'never-loaded', 'missed-dialog', 'started-playing'])
def test_kodi_skin_handoff_waits_for_native_decision(monkeypatch, outcome):
    clock, setting, events = [0.], ['skin.bobbi.cinema'], []
    target = 'skin.estuary'
    def wait(dt):
        clock[0] = round(clock[0] + dt, 4)
        if outcome == 'decline' and clock[0] >= 1.4:
            setting[0] = 'skin.bobbi.cinema'
        return False
    def change(method, args):
        assert method == 'Settings.SetSettingValue' and args['value'] == target
        setting[0] = target
        events.append('request')
        return True
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.skin = lambda: setting[0]
    host.monitor = NS(waitForAbort=wait)
    host.xbmc = NS(getSkinDir=lambda: target if clock[0] >= .7 and outcome != 'never-loaded' else 'skin.bobbi.cinema',
        getCondVisibility=lambda _: 1 <= clock[0] < 1.4 and outcome != 'missed-dialog',
        getInfoLabel=lambda _: 'Keep skin?', getLocalizedString=lambda n: 'Keep skin?' if n == 13123 else '',
        Player=lambda: NS(isPlaying=lambda: outcome == 'started-playing' and clock[0] > .8))
    monkeypatch.setattr(ui, 'time', NS(monotonic=lambda: clock[0]))
    monkeypatch.setattr(ui, 'rpc', change)
    if outcome in ('keep', 'missed-dialog'):
        host.prepare_install_skin()
        assert clock[0] >= (1.4 if outcome == 'keep' else 12.7)
    else:
        with pytest.raises(ui.UpdateError, match='PLAYBACK_ACTIVE|INSTALL_SKIN_NOT_CONFIRMED'):
            host.prepare_install_skin()
    assert events == ['request']


@pytest.mark.parametrize('operation', ['apply', 'rollback'])
def test_declined_native_confirmation_preserves_previous_receipt(environment, signing, operation):
    e = environment
    e.installer.apply(package(e.root/'one.zip', signing, 1))
    e.installer.apply(package(e.root/'two.zip', signing, 2, '2.0.0'))
    prior = e.installer.state.read_bytes()
    def declined():
        raise ui.UpdateError('INSTALL_SKIN_NOT_CONFIRMED')
    e.host.prepare_install_skin = declined
    e.calls.clear()
    with pytest.raises(ui.UpdateError, match='INSTALL_SKIN_NOT_CONFIRMED'):
        if operation == 'apply':
            e.installer.apply(package(e.root/'three.zip', signing, 3, '3.0.0'))
        else:
            e.installer.rollback()
    assert e.installer.state.read_bytes() == prior and 'quiesce' not in e.calls
    assert (e.user/'watching').read_text() == 'user-history'


@pytest.mark.parametrize('drained', [True, False])
def test_unknown_drain_response_is_reconciled_only_by_lease(tmp_path, monkeypatch, drained):
    from bobbi_platform.instance_lock import InstanceLock
    marker = tmp_path/'runtime.json'
    marker.write_text('{}')
    lease = InstanceLock(str(marker) + '.lock')
    lease.acquire()
    clock, sent, disabled = [0.], [], []
    def call(action, body, timeout):
        if action == 'status':
            return {'quiesce_protocol': 1}
        assert action == 'quiesce' and not sent
        sent.append(action)
        if drained:
            lease.close()
        raise OSError('lost response')
    host = ui.KodiHost.__new__(ui.KodiHost)
    host.skin = lambda: 'skin.estuary'
    host.check_idle = lambda: None
    host.xbmc = NS(Player=lambda: NS(isPlaying=lambda: False))
    host.monitor = NS(waitForAbort=lambda dt: clock.__setitem__(0, clock[0]+dt) or False)
    host.details = lambda name: {'enabled': name == 'plugin.video.bobbi' and not disabled}
    monkeypatch.setattr(ui, 'profile', lambda **k: marker)
    monkeypatch.setattr(ui, 'time', NS(monotonic=lambda: clock[0]))
    monkeypatch.setattr(runtime, 'call', call)
    monkeypatch.setattr(ui, 'rpc', lambda method, args: disabled.append(args['addonid']))
    try:
        if drained:
            host.quiesce()
            assert disabled == ['plugin.video.bobbi']
        else:
            with pytest.raises(ui.UpdateError, match='CINEMA_SERVICE_NOT_STOPPED'):
                host.quiesce()
            assert not disabled and marker.exists()
        assert sent == ['quiesce']
    finally:
        host.close()
        lease.close()
