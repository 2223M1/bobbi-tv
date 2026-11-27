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
    host.unattended = False
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


@pytest.mark.parametrize('scenario', ['delayed_dialog', 'rpc_false', 'foreign_dialog', 'reverted_timeout', 'already_active'])
def test_restore_skin_after_install_and_confirmer_contracts(monkeypatch, scenario):
    clock = [0.0]
    setting = ['skin.bobbi.cinema' if scenario == 'already_active' else 'skin.estuary']
    clicks = []
    dialog_state = {'visible': False, 'heading': '', 'body': ''}

    def wait(dt):
        clock[0] = round(clock[0] + dt, 4)
        if scenario == 'delayed_dialog':
            # Kodi Omega getSkinDir() updates immediately, while ReloadSkin(confirm) opens #13123 asynchronously at 0.3s
            if 0.3 <= clock[0] < 0.7 and 'SendClick(yesnodialog,11)' not in clicks:
                dialog_state.update(visible=True, heading='Keep skin?', body='Would you like to keep this change?')
            if 'SendClick(yesnodialog,11)' in clicks:
                dialog_state.update(visible=False, heading='', body='')
        elif scenario == 'reverted_timeout':
            if 0.3 <= clock[0] < 2.0:
                dialog_state.update(visible=True, heading='Keep skin?', body='Would you like to keep this change?')
            elif clock[0] >= 2.0:
                dialog_state.update(visible=False, heading='', body='')
                setting[0] = 'skin.estuary'
        return False

    def exec_builtin(cmd, *_a):
        clicks.append(cmd)
        if scenario == 'delayed_dialog' and cmd == 'SendClick(yesnodialog,11)':
            dialog_state.update(visible=False, heading='', body='')

    def fake_rpc(method, args):
        if method == 'Settings.SetSettingValue':
            if scenario == 'rpc_false':
                return False
            setting[0] = args['value']
            return True
        raise AssertionError(method)

    host = ui.KodiHost.__new__(ui.KodiHost)
    host.unattended = True
    host.skin = lambda: setting[0]
    host.details = lambda name: {'enabled': True, 'version': '0.1.44'}
    host.monitor = NS(waitForAbort=wait)
    host.xbmc = NS(
        # Mirror Kodi Omega ModuleXbmc.cpp: getSkinDir() reads lookandfeel.skin setting directly!
        getSkinDir=lambda: setting[0],
        getCondVisibility=lambda c: dialog_state['visible'] if c == 'Window.IsVisible(yesnodialog)' else False,
        getInfoLabel=lambda c: dialog_state['heading'] if c == 'Control.GetLabel(1)' else (
            dialog_state['body'] if c == 'Control.GetLabel(2)' else ''
        ),
        getLocalizedString=lambda n: 'Keep skin?' if n == 13123 else '',
        executebuiltin=exec_builtin,
        Player=lambda: NS(isPlaying=lambda: False),
    )
    monkeypatch.setattr(ui, 'time', NS(monotonic=lambda: clock[0]))
    monkeypatch.setattr(ui, 'rpc', fake_rpc)

    if scenario == 'foreign_dialog':
        # Test _skin_keep_confirmer directly: #13123 replaced by unrelated yesnodialog within 200ms settle window
        setting[0] = 'skin.bobbi.cinema'
        dialog_state.update(visible=True, heading='Keep skin?', body='Would you like to keep this change?')
        orig_is_keep = host._is_keep_skin_dialog
        checks = [0]

        def morphing_check(expected_skin=None):
            checks[0] += 1
            res = orig_is_keep(expected_skin)
            if checks[0] == 1:
                dialog_state.update(visible=True, heading='Delete library source?', body='Remove saved share?')
            return res

        host._is_keep_skin_dialog = morphing_check
        with host._skin_keep_confirmer(expected_skin='skin.bobbi.cinema'):
            import time as real_time
            real_time.sleep(0.35)
        assert clicks == []
        return

    if scenario == 'delayed_dialog':
        # Drive deterministic confirmer click when #13123 becomes visible
        orig_wait = host.monitor.waitForAbort

        def wait_with_auto_click(dt):
            res = orig_wait(dt)
            if host._is_keep_skin_dialog('skin.bobbi.cinema'):
                exec_builtin('SendClick(yesnodialog,11)', False)
            return res

        host.monitor.waitForAbort = wait_with_auto_click
        assert host.restore_skin_after_install('skin.bobbi.cinema') is True
        assert clock[0] >= 0.3
        assert 'SendClick(yesnodialog,11)' in clicks
        assert setting[0] == 'skin.bobbi.cinema'
    elif scenario == 'already_active':
        assert host.restore_skin_after_install('skin.bobbi.cinema') is True
        assert clock[0] == 0.0 and clicks == []
    else:
        # Both rpc_false and reverted_timeout must return False honestly (never hang or claim success)
        host._skin_keep_confirmer = lambda **_kw: ui.contextmanager(lambda: (yield))()
        assert host.restore_skin_after_install('skin.bobbi.cinema') is False
