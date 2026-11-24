"""Two generations via a packaged old client, a real journal and the same idle reader as the TV."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import runpy
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from bobbi_platform import ce_update_notice as notice, online_updates as online
from bobbi_platform.ce_installer import read_installation
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import environment, package, signing
from test_online_updates import Response
from test_onboarding import setup_ui

ROOT = Path(__file__).resolve().parents[1]
from ce_retired_launcher import launcher


def make_offer(bundle, tag):
    with ZipFile(bundle) as z:
        m = json.loads(z.read('release.json'))
    return dict(schema=2, tag=tag, sequence=m['sequence'], size=bundle.stat().st_size,
                url=online.release_url(tag, 'github'), sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
                track='stable', prerelease=False, manifest_channel=m['channel'],
                versions={c['id']: c['version'] for c in m['components']})


@pytest.mark.parametrize('retired', [False, True], ids=['published', 'ce2108'])
def test_two_signed_upgrades_discovered_by_published_client_and_live_service(environment, signing, monkeypatch, retired):
    e = environment
    old_feed = json.loads((ROOT / 'tests/fixtures/ce2108-stable.json').read_bytes())
    assert old_feed['tag'] == 'ce2108'
    if retired:
        client = launcher('stable/script.bobbi.start/script.bobbi.start-0.2.88.zip',
                          'b62775f36aecb6f22407ccca3eaff3a016c154a3223823bb89e73394050c594e')
    else:
        from xml.etree import ElementTree as ET
        directory = ROOT / 'repository/stable'
        version = ET.parse(directory/'addons.xml').find("addon[@id='script.bobbi.start']").get('version')
        client = directory / 'script.bobbi.start' / ('script.bobbi.start-' + version + '.zip')
        assert hashlib.sha256(client.read_bytes()).hexdigest() == client.with_suffix('.zip.sha256').read_text()
    e.installer.apply(package(e.root/'old.zip', signing, old_feed['sequence'], channel='private-stable'))
    # Start a fresh Python process with ONLY the actual CE2108 launcher's
    # bootstrap on the application import path. Only the two HTTP reads are replaced.
    frozen = """import json,sys
sys.path.insert(0,sys.argv[1]+'/script.bobbi.start/bootstrap')
from bobbi_platform import online_updates as old
assert sys.argv[1] in old.__file__
offers = json.loads(sys.stdin.read())
urls = []
def transfer(url,maximum,consume,*args,**kwargs):
    urls.append(url)
    consume(json.dumps(offers[len(urls)-1]).encode())
old._transfer=transfer
assert old.latest(track='stable') == offers[1]
assert urls == [old.feed_url('stable', source) for source in (('gitcode','github') if 'gitcode.com' in old.OFFER_URL else ('gitee','github'))]
"""
    calls, notifications = [], []
    for version, sequence in [('2.0.0', 2026102165), ('3.0.0', 2026102166)]:
        tag = 'ce' + str(sequence)[-4:]
        artifact = package(e.root/(tag+'.zip'), signing, sequence, version, channel='private-stable')
        new = make_offer(artifact, tag)
        subprocess.run([sys.executable, '-IB', '-c', frozen, str(client)],
                       input=json.dumps([old_feed, new]), text=True, check=True)
        def response(url):
            calls.append(url)
            return Response(json.dumps(old_feed if url == online.feed_url('stable', 'gitcode') else new).encode())
        monkeypatch.setattr(online, '_open', response)
        before = (e.work/'installation.json').read_bytes()
        assert notice.check(e.work, lambda: False, notifications.append) == 'notified'
        assert notice.check(e.work, lambda: False, notifications.append) == 'seen'
        assert (e.work/'installation.json').read_bytes() == before
        assert set(calls) == {online.feed_url('stable', source) for source in ('gitcode', 'github')}
        # Installation only at the separate, explicit acceptance boundary.
        e.installer.apply(artifact)
        assert read_installation(e.work)['high_watermark'] == sequence
        assert notice.check(e.work, lambda: False, notifications.append) == 'current'
        assert (e.user/'watching').read_text() == 'user-history'
    assert notifications == ['CE2165', 'CE2166']


def write_journal(work, **kwargs):
    row = dict(schema=1, tx='a'*32, items=[], sequence=7, high_watermark=9, phase='complete')
    (work/'installation.json').write_text(json.dumps(dict(row, **kwargs)))


def reject(*args, **kwargs):
    pytest.fail('unexpected network or notification')


@pytest.mark.parametrize('mode', ['uninstalled', 'muted', 'busy', 'recovering', 'restore-pending', 'broken'])
def test_background_never_migrates_repairs_or_installs(tmp_path, mode):
    if mode != 'uninstalled':
        write_journal(tmp_path, **({'phase': 'restored', 'host_pending': 'restore'} if mode == 'restore-pending'
                      else {'phase': 'switching'} if mode == 'recovering' else {}))
    if mode == 'muted':
        notice.enabled(tmp_path, False)
    if mode == 'broken':
        (tmp_path/'installation.json').write_bytes(b'{}')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    if mode == 'broken':
        with pytest.raises(UpdateError, match='JOURNAL_INVALID'):
            notice.check(tmp_path, lambda: False, reject, lookup=reject)
    else:
        assert notice.check(tmp_path, lambda: mode == 'busy', reject, lookup=reject) in ('inactive', 'deferred')
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize('change', ['start-playing', 'owner-stopped', 'track', 'mute', 'new-journal', 'rollback', 'offline'])
def test_late_discovery_rechecks_context(tmp_path, change):
    write_journal(tmp_path)
    stopped = []
    def lookup(cancelled, *, track):
        assert track == 'stable'
        if change in ('start-playing', 'owner-stopped'): stopped.append(True)
        if change == 'track': online.selected_track(tmp_path, 'preview')
        if change == 'mute': notice.enabled(tmp_path, False)
        if change == 'new-journal': write_journal(tmp_path, tx='b'*32)
        if change == 'offline': raise TimeoutError()
        return {'tag': 'ce2200', 'sequence': 9 if change == 'rollback' else 100}
    if change == 'offline':
        with pytest.raises(TimeoutError):
            notice.check(tmp_path, lambda: bool(stopped), reject, lookup=lookup)
    else:
        assert notice.check(tmp_path, lambda: bool(stopped), reject, lookup=lookup) in ('current', 'deferred')
    assert not list(tmp_path.glob('update-notified-*.json'))


def test_uses_os_identity_not_optional_settings_addon(tmp_path, monkeypatch):
    release = tmp_path/'os-release'
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert not notice.coreelec(release)
    release.write_text('NAME="CoreELEC like"\nID=libreelec\n')
    assert not notice.coreelec(release)
    release.write_text('ID="coreelec"\n')
    assert notice.coreelec(release)
    monkeypatch.setattr(sys, 'platform', 'win32')
    assert not notice.coreelec(release)


@pytest.mark.parametrize('state,apk,expected', [
    ('absent', False, False), ('complete', False, True), ('restored', False, True),
    ('switching', False, False), ('pending', False, False), ('bad', False, False),
    ('complete', True, False)])
def test_signed_zip_notices_use_install_owner_on_stock_kodi(tmp_path, monkeypatch, state, apk, expected):
    from bobbi_platform import android_ui
    monkeypatch.setattr(android_ui, 'bundled_host', lambda: apk)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))
    if state == 'bad':
        (tmp_path/'installation.json').write_bytes(b'{}')
    elif state != 'absent':
        write_journal(tmp_path, **({'phase':'restored', 'host_pending':'restore'}
                                    if state == 'pending' else {'phase':state}))
    assert notice.supported() is expected


def test_real_service_retries_then_sleeps_and_obeys_owner_stop(monkeypatch):
    waits, calls, logs = [], [], []
    monitor = SimpleNamespace(waitForAbort=lambda delay: waits.append(delay) or len(waits) == 4)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=object, LOGWARNING=2))
    for name in ('xbmcaddon', 'xbmcvfs'):
        monkeypatch.setitem(sys.modules, name, SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.settings', SimpleNamespace(update_delay=lambda: 45))
    names = 'ADDON_VERSION clear_cached_settings clear_property dialog_ok get_kodi_version get_setting set_property_no_fallback set_setting translatePath translation'
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils',
                        SimpleNamespace(**dict.fromkeys(names.split()), kodilog=lambda msg, **kw: logs.append(msg)))
    worker = runpy.run_path(str(ROOT/'addons/plugin.video.bobbi/lib/services/background_service.py'))['UpdateCheck'](monitor)
    def discover(*, automatic, monitor):
        calls.append((automatic, monitor))
        if len(calls) == 1:
            raise TimeoutError('private URL must not be logged')
        return 'deferred' if len(calls) == 2 else 'notified'
    monkeypatch.setitem(worker.run.__globals__, 'updates_check_addon', discover)
    monkeypatch.setattr(notice, 'supported', lambda: False)
    worker.run()
    assert not waits
    monkeypatch.setattr(notice, 'supported', lambda: True)
    worker.run()
    assert waits == [45, 900, 60, 21600] and calls == [(True, monitor)] * 3
    assert logs == ['Update discovery: TimeoutError']


@pytest.mark.parametrize('mode', ['playing', 'modal', 'active', 'switched', 'stopped', 'idle'])
def test_kodi_automatic_entry_never_controls_player(tmp_path, monkeypatch, mode):
    state = SimpleNamespace(root=tmp_path, stop=False)
    current = lambda: state.root
    xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: mode == 'playing'),
        getGlobalIdleTime=lambda: 2 if mode == 'active' else 60, getCondVisibility=lambda _: mode == 'modal',
        executebuiltin=reject)
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(current())))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(ADDON_VERSION='test'))
    calls, messages = [], []
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(
        notification=lambda *a, **kw: messages.append((a, kw)))))
    write_journal(tmp_path)
    check = notice.check
    def lookup(cancelled, *, track):
        calls.append(track)
        if mode == 'switched': state.root = tmp_path/'other'
        if mode == 'stopped': state.stop = True
        return {'tag': 'ce2200', 'sequence': 100}
    monkeypatch.setattr(notice, 'check', lambda *a: check(*a, lookup=lookup))
    updater = runpy.run_path(str(ROOT/'addons/plugin.video.bobbi/lib/updater.py'))['updates_check_addon']
    assert updater(True, SimpleNamespace(abortRequested=lambda: state.stop)) == (
        'notified' if mode == 'idle' else 'deferred')
    assert bool(calls) == (mode not in ('playing', 'modal', 'active'))
    assert bool(messages) == (mode == 'idle') == (tmp_path/'update-notified-stable.json').exists()


@pytest.mark.parametrize('choice,switched', [(1, False), (0, False), (-1, False), (1, True)])
def test_preference_tv_route_preselect_cancel_and_profile(setup_ui, tmp_path, monkeypatch, choice, switched):
    work = tmp_path/'profiles'/'A'
    active = [work]
    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda _: str(active[0]))
    calls = []
    def select(title, rows, **kw):
        calls.append(title)
        if len(calls) == 1:
            return rows.index('新版本提醒')
        assert title == '新版本提醒' and kw['preselect'] == 0
        if switched: active[0] = tmp_path/'profiles'/'B'
        return choice
    setup_ui.dialog.select = select
    assert setup_ui.module.show_updates(setup_ui.dialog) == (choice >= 0 and not switched)
    assert notice.enabled(work) == (choice != 1 or switched)
    assert work.exists() == (choice >= 0 and not switched)
    assert not (tmp_path/'profiles'/'B').exists() and not setup_ui.builtins
