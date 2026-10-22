"""Online transport feeds the same signed transaction used by local installs."""
import hashlib
from http.client import IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.request import Request
import zipfile

import pytest

from bobbi_platform import ce_install_ui as ui, online_updates as online
from bobbi_platform.ce_installer import PlaybackActive
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import environment, package, signing
from test_onboarding import setup_ui


def offer_for(raw, sequence=1):
    return dict(schema=1, tag='ce2054', sequence=sequence, size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        url='https://github.com/2223M1/bobbi-tv/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip')


class Response(BytesIO):
    def __init__(self, raw, headers=None, status=200):
        super().__init__(raw)
        self.status = status
        self.headers = headers if headers is not None else {'Content-Length': str(len(raw))}


@pytest.mark.parametrize('change', [dict(schema=True), dict(sequence=True), dict(size=True),
    dict(size=online.MAX_BUNDLE+1), dict(size=0), dict(sequence=0), dict(extra='unexpected'),
    dict(tag='../ce2054'), dict(tag='CE2054'), dict(sha256='z'*64),
    dict(url='http://github.com/2223M1/bobbi-tv/releases/download/ce2054/BobbiTV-CE2054.bobbi-update.zip'),
    dict(url='https://github.com/elsewhere/file.zip'),
    dict(url='https://github.com/2223M1/bobbi-tv/releases/download/ce2053/BobbiTV-CE2053.bobbi-update.zip')])
def test_offer_rejects_unbounded_or_unrelated_release(change):
    with pytest.raises(UpdateError):
        online.parse_offer(json.dumps(dict(offer_for(b'valid'), **change)))


@pytest.mark.parametrize('raw', [b'{', b'null', b'[]', b'{"schema":1,"schema":1}', b'NaN'])
def test_offer_rejects_bad_json(raw):
    with pytest.raises(UpdateError): online.parse_offer(raw)


def test_latest_uses_fixed_index_and_limits_bytes(monkeypatch):
    offer = offer_for(b'valid')
    calls = []
    def open_response(url):
        calls.append(url)
        return Response(json.dumps(offer).encode())
    monkeypatch.setattr(online, '_open', open_response)
    assert online.latest() == offer
    assert calls == [online.OFFER_URL]
    monkeypatch.setattr(online, '_open', lambda _: Response(b' '*32769, headers={}))
    with pytest.raises(UpdateError, match='ONLINE_LENGTH_INVALID'): online.latest()


@pytest.mark.parametrize('url', ['http://github.com/file.zip', 'https://evil.invalid/file.zip',
    'https://github.com@evil.invalid/file.zip', 'https://release-assets.githubusercontent.com/file#fragment'])
def test_redirects_reject_before_following(url):
    with pytest.raises(UpdateError, match='ONLINE_REDIRECT_REJECTED'):
        online._Redirects().redirect_request(Request(offer_for(b'x')['url']), None, 302, '', {}, url)


def test_release_cdn_redirect_is_bounded():
    redirect = online._Redirects()
    request = Request(offer_for(b'x')['url'])
    url = 'https://release-assets.githubusercontent.com/example?signature=fixture'
    for _ in range(online.MAX_REDIRECTS):
        assert redirect.redirect_request(request, None, 302, '', {}, url).full_url == url
    with pytest.raises(UpdateError): redirect.redirect_request(request, None, 302, '', {}, url)


@pytest.mark.parametrize('headers,status,error', [
    ({'Content-Length': '9'}, 200, 'SHORT_READ'), ({'Content-Length': '21'}, 200, 'LENGTH_INVALID'),
    ({'Content-Length': '-1'}, 200, 'LENGTH_INVALID'), ({'Content-Length': 'x'}, 200, 'LENGTH_INVALID'),
    ({'Content-Encoding': 'gzip'}, 200, 'RESPONSE_INVALID'), ({}, 206, 'RESPONSE_INVALID')])
def test_transfer_rejects_invalid_responses(monkeypatch, headers, status, error):
    response = Response(b'12345678', headers, status)
    monkeypatch.setattr(online, '_open', lambda _: response)
    with pytest.raises(UpdateError, match='ONLINE_'+error):
        online._transfer('fixture', 20, lambda _: None, lambda: False, lambda _: None)
    assert response.closed


def test_transfer_handles_chunked_short_read_without_leaking_response(monkeypatch):
    class Broken(Response):
        def read(self, size): raise IncompleteRead(b'private-body')
    monkeypatch.setattr(online, '_open', lambda _: Broken(b''))
    with pytest.raises(UpdateError, match='^ONLINE_RESPONSE_INVALID$'):
        online._transfer('fixture', 20, lambda _: None, lambda: False, lambda _: None)


def test_transfer_budget_and_cancel_before_network(monkeypatch):
    monkeypatch.setattr(online, '_open', lambda _: pytest.fail('cancelled before request'))
    with pytest.raises(online.Cancelled):
        online._transfer('fixture', 20, lambda _: None, lambda: True, lambda _: None)
    clock = iter([0, 601])
    monkeypatch.setattr(online.time, 'monotonic', lambda: next(clock))
    with pytest.raises(UpdateError, match='ONLINE_TIMEOUT'):
        online._transfer('fixture', 20, lambda _: None, lambda: False, lambda _: None)


@pytest.mark.parametrize('known_length', [True, False])
def test_signed_download_checks_complete_generation(tmp_path, signing, monkeypatch, known_length):
    raw = package(tmp_path/'input.zip', signing).read_bytes()
    monkeypatch.setattr(online, '_open', lambda _: Response(raw, None if known_length else {}))
    progress = []
    path = online.download(offer_for(raw), tmp_path/'downloads', signing[1], progress=progress.append)
    assert path.read_bytes() == raw and progress[-1] == 100


@pytest.mark.parametrize('failure', ['hash', 'sequence', 'short', 'long', 'zip', 'signature', 'cancel', 'space'])
def test_download_failure_removes_only_its_temp_file(tmp_path, signing, monkeypatch, failure):
    raw = package(tmp_path/'input.zip', signing).read_bytes()
    offer = offer_for(raw)
    if failure == 'hash': offer['sha256'] = '0'*64
    if failure == 'sequence': offer['sequence'] = 2
    if failure == 'short': raw = raw[:-1]
    if failure == 'long': raw += b'x'
    if failure == 'zip': raw = b'not a zip'; offer = offer_for(raw)
    if failure == 'signature':
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as source, zipfile.ZipFile(output, 'w') as dest:
            for name in source.namelist():
                dest.writestr(name, b'a'*512 if name == 'release.sig' else source.read(name))
        raw = output.getvalue(); offer = offer_for(raw)
    if failure == 'space':
        monkeypatch.setattr(online.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(online, '_open', lambda _: Response(raw, {}))
    folder = tmp_path/'downloads'; folder.mkdir()
    (folder/'previous-backup.zip').write_bytes(b'keep')
    cancelled = [False]
    with pytest.raises(UpdateError):
        online.download(offer, folder, signing[1], lambda: cancelled[0],
                        lambda _: cancelled.__setitem__(0, failure == 'cancel'))
    assert [p.name for p in folder.iterdir()] == ['previous-backup.zip']


@pytest.fixture
def entry(environment, signing, monkeypatch):
    env = environment
    raw = package(env.root/'online.zip', signing).read_bytes()
    offer = offer_for(raw)
    state = SimpleNamespace(playing=False, cancelled=False, commands=[], dialogs=[],
        selections=[], confirmations=[], progress=[], closes=0, choice=4)
    def idle():
        if state.playing: raise PlaybackActive('PLAYBACK_ACTIVE')
    env.host.check_idle = idle
    env.host.monitor = SimpleNamespace(abortRequested=lambda: False)
    env.host.details = lambda _: None
    def select(title, options, **kwargs):
        state.selections.append(options)
        return state.choice
    def confirm(*args):
        state.confirmations.append(args)
        return True
    dialog = SimpleNamespace(select=select, yesno=confirm,
        ok=lambda *args: state.dialogs.append(args))
    progress = SimpleNamespace(create=lambda *args: None,
        update=state.progress.append, iscanceled=lambda: state.cancelled,
        close=lambda: setattr(state, 'closes', state.closes+1))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: dialog, DialogProgress=lambda: progress))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(LOGERROR=4,
        log=lambda *a: None, executebuiltin=state.commands.append))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(env.addons)))
    monkeypatch.setattr(ui, 'profile', lambda *a, **kw: env.work)
    monkeypatch.setattr(ui, 'KodiHost', lambda: env.host)
    monkeypatch.setattr(ui, 'Installer', lambda *a: env.installer)
    monkeypatch.setattr(online, 'latest', lambda cancelled: offer)
    monkeypatch.setattr(online, '_open', lambda _: Response(raw))
    state.env, state.dialog, state.offer = env, dialog, offer
    return state


@pytest.mark.parametrize('route', ['fresh', 'explicit', 'menu'])
def test_real_entry_online_install_preserves_user_data(entry, monkeypatch, route):
    if route == 'menu': entry.env.host.details = lambda _: {'version': '0.1.0'}
    ui.main(online=route == 'explicit')
    env = entry.env
    assert env.installer._read()['phase'] == 'complete'
    assert env.installer._read()['sequence'] == 1
    assert entry.commands == ['RunScript(script.bobbi.setup)']
    assert (env.user/'watching').read_text() == 'user-history'
    assert (env.addons/'plugin.user.other/keep').read_text() == 'other-addon'
    assert not list((env.work/'downloads').glob('online-*.zip'))
    assert env.installer._read()['previous_skin'] == 'skin.user.original'
    assert env.host.skin() == 'skin.user.original'
    if route == 'menu': assert entry.selections[0][4] == '在线检查并安装最新正式版'


@pytest.mark.parametrize('when', ['initial', 'confirmation', 'downloading', 'cancel', 'decline'])
def test_entry_never_installs_when_playing_or_cancelled(entry, monkeypatch, when):
    if when == 'initial': entry.playing = True
    if when == 'confirmation':
        entry.dialog.yesno = lambda *args: setattr(entry, 'playing', True) or True
    if when == 'decline': entry.dialog.yesno = lambda *args: False
    if when in ('downloading', 'cancel'):
        class StartDuringDownload(Response):
            def read(self, size):
                setattr(entry, 'playing' if when == 'downloading' else 'cancelled', True)
                return super().read(size)
        raw = (entry.env.root/'online.zip').read_bytes()
        monkeypatch.setattr(online, '_open', lambda _: StartDuringDownload(raw))
    ui.main(online=True)
    assert entry.env.installer._read() is None
    assert entry.env.calls == [] and entry.commands == []
    assert not list((entry.env.work/'downloads').glob('online-*.zip'))
    assert (entry.env.user/'watching').read_text() == 'user-history'
    if when in ('initial', 'confirmation', 'downloading'):
        assert '请先停止播放' in str(entry.dialogs) and entry.playing


def test_current_version_does_not_download_or_replace(entry, monkeypatch):
    entry.env.installer.apply(entry.env.root/'online.zip')
    before = list(entry.env.calls)
    monkeypatch.setattr(online, '_open', lambda _: pytest.fail('No second download'))
    ui.main(online=True)
    assert '无需更新' in str(entry.dialogs)
    assert entry.env.calls == before and entry.commands == [] and not entry.confirmations


def test_entry_network_error_keeps_existing_install(entry, monkeypatch):
    def fail(*args): raise OSError('fixture-private-url')
    monkeypatch.setattr(online, 'latest', fail)
    ui.main(online=True)
    assert '网络连接或下载未完成' in str(entry.dialogs)
    assert 'fixture-private-url' not in str(entry.dialogs)
    assert entry.env.calls == [] and entry.commands == []


def test_setup_online_action_calls_entry_not_separate_updater(setup_ui):
    setup_ui.choice = 3
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert setup_ui.builtins == ['RunScript(script.bobbi.start,online)']
