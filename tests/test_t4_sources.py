"""Synthetic T4 wire contracts and a real Registry -> Kodi submission boundary."""
import base64
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_core import t4
from bobbi_core.library_contract import LibraryError
from bobbi_platform import t4_ui as ui
from bobbi_platform.t4_http import resolve_selected
from bobbi_platform.libraries import Registry

BASE = 'https://t4.example.invalid/configs/config.json'
SAMPLES = Path(__file__).parent / 'fixtures/t4'


def sample(n):
    return next(SAMPLES.glob(n + '-*.json')).read_bytes()


def test_mixed_preview_registration_idempotence_and_failed_replacement(tmp_path):
    store = Registry(tmp_path / 'libraries.sqlite3')
    try:
        p = t4.preview(sample('02'), BASE)
        assert (len(p.sites), p.unsupported, p.invalid) == (1, 1, 0)
        assert p.sites[0]['api'].startswith('https://t4.example.invalid/t4/')
        item = p.source(BASE)
        store.save(item, expected_snapshot=(None, None))
        snap = store.source_snapshot(item.id)
        store.save(item, expected_snapshot=snap)
        assert store.source_snapshot(item.id) == snap
        assert 'fixture-token' not in repr(snap)
        for n, code in [('03', 'T4_NO_SITES'), ('04', 'T4_DUPLICATE')]:
            with pytest.raises(LibraryError, match=code):
                store.save(t4.preview(sample(n), BASE).source(BASE, item), expected_snapshot=snap)
            assert store.source_snapshot(item.id) == snap
    finally:
        store.close()


@pytest.mark.parametrize('bad', [
    b'{"sites":[],"sites":[]}', b'<html>login</html>', b'{"urls":[]}',
    b'{"x":' + b'[' * 34 + b'0' + b']' * 34 + b'}',
    b' ' * (2 * 1024**2 + 1)], ids=['duplicate', 'html', 'depot', 'deep', 'oversize'])
def test_no_ambiguous_deep_or_executable_config(bad):
    with pytest.raises(LibraryError):
        t4.preview(bad, BASE)


@pytest.mark.parametrize('url', ['http://127.0.0.1:80/x', 'http://0x7f000001/x', 'http://2130706433/x',
    'https://127.1/x', 'http://169.254.169.254/x', 'https://[::ffff:127.0.0.1]/', 'http://public.example/x',
    'https://name:pw@example.invalid/x', 'plugin://addon/entry'])
def test_refuse_unauthorized_endpoints(url):
    with pytest.raises(LibraryError):
        t4.endpoint(url)


def test_explicit_lan_http_private_path_supported_without_loosening_original_sources():
    from bobbi_core import source_library
    url = 'http://192.168.1.91:4567/reverse/config.json?token=test'
    assert t4.endpoint(url) == url
    with pytest.raises(source_library.SourceLibraryError):
        source_library.normalize(url, document=True)


def test_five_operations_original_query_and_opaque_play_ids():
    site = t4.preview(sample('01'), BASE).sites[0]
    site['extend'] = 'site-scoped'
    calls = []
    def fetch(url):
        key = parse_qs(urlsplit(url).query)
        calls.append(key)
        return sample('08' if 'play' in key else '07' if 'ids' in key else '06' if 'pg' in key else '05')
    c = t4.Client(site, fetch)
    assert ui._rows(c.home(), 'class', 'type_id', 'type_name')[0] == ('电影', 'movie')
    assert c.category('series', 1, {'year': '2026'})['pagecount'] == 2
    assert json.loads(base64.urlsafe_b64decode(calls[-1]['ext'][0])) == {'year': '2026'}
    assert c.search('海 风', 2)['total'] == 3 and calls[-1]['wd'] == ['海 风'] and calls[-1]['pg'] == ['2']
    groups = c.detail('xy:series:001')
    assert len(groups) == 2 and [len(rows) for _, rows in groups] == [2, 2]
    name, rows = groups[1]
    c.play(name, rows[1][1])
    assert calls[-1]['play'] == ['xy:series:001:ep:02:line:B'] and calls[-1]['flag'] == ['备用线路']
    assert all(q.get('profile') == ['fixture'] and q.get('extend') == ['site-scoped'] for q in calls)


def test_host_rechecks_exact_line_episode_and_rejects_unapproved_cdn():
    source = t4.preview(sample('01'), BASE).source(BASE)
    site = source.metadata['sites'][0]
    choice = ui.selection(site, 'xy:series:001', '备用线路', 'xy:series:001:ep:02:line:B')
    calls = []
    def fetch(url):
        calls.append(parse_qs(urlsplit(url).query))
        return sample('08') if 'play' in calls[-1] else sample('07')
    with pytest.raises(LibraryError, match='T4_MEDIA_ORIGIN'):
        resolve_selected(source, choice, fetch=fetch)
    assert len(calls) == 2 and calls[-1]['flag'] == ['备用线路']
    url, headers, title = resolve_selected(source, choice, fetch=lambda u:
        fetch(u).replace(b'media.example.invalid', b't4.example.invalid'))
    assert url.startswith('https://t4.example.invalid/') and headers['User-Agent'] and title == '第 2 集'
    calls.clear()
    with pytest.raises(LibraryError, match='T4_CHANGED'):
        resolve_selected(source, dict(choice, episode='0'*64), fetch=fetch)
    assert len(calls) == 1 and 'play' not in calls[0]
    with pytest.raises(LibraryError):
        ui.selection(site, 'https://secret.invalid/item?token=do-not-send', 'A', 'B')


def test_unresolved_parser_and_unsafe_headers_never_submitted():
    site = t4.preview(sample('01'), BASE).sites[0]
    for raw, code in ((sample('09'), 'T4_PLAY_UNSUPPORTED'),
            (b'{"parse":0,"url":"https://example.invalid/file","header":{"Cookie":"token"}}', 'T4_HEADERS')):
        with pytest.raises(LibraryError, match=code):
            t4.Client(site, lambda _: raw).play('line', 'id')
    data = json.loads(sample('08'))
    data['header'] = json.dumps(data['header'])
    assert 'Referer' in t4.Client(site, lambda _: json.dumps(data).encode()).play('A', 'B')[1]


def test_401_classified_from_http_status_not_json_body(monkeypatch):
    from bobbi_platform import source_media_http, t4_http
    # IO stub; authentication failure precedes any body inspection/redirect.
    class Conn:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return SimpleNamespace(status=401, read1=io.BytesIO(sample('10')).read)
        def close(self): pass
    monkeypatch.setattr(source_media_http, 'HTTPSConnection', Conn)
    with pytest.raises(LibraryError, match='T4_AUTH'):
        t4_http.read(BASE, 10**12, lambda: False)


def test_browse_search_and_single_submission_without_raw_endpoint_in_host_ipc(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from urllib.parse import parse_qsl
    from bobbi_platform import owned_playback, paths
    store = Registry(tmp_path / 'libraries.sqlite3')
    src = t4.preview(sample('01'), BASE).source(BASE)
    store.save(src)
    submit, control, rendered = [], [], []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    monkeypatch.setitem(
        sys.modules,
        'xbmcgui',
        SimpleNamespace(
            Dialog=lambda: SimpleNamespace(input=lambda *_: '中文搜索', yesno=lambda *_: True, ok=lambda *_: None),
            ListItem=lambda label='': SimpleNamespace(
                label=label,
                setInfo=lambda *a: None,
                setArt=lambda *a: None,
                setProperty=lambda *a: None,
                setLabel2=lambda *a: None,
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        'xbmcplugin',
        SimpleNamespace(
            setPluginCategory=lambda *a: None,
            setContent=lambda *a: None,
            addDirectoryItems=lambda _h, rows, _n: rendered.extend(rows),
            endOfDirectory=lambda *a, **kw: None,
            setResolvedUrl=lambda *a: None,
        ),
    )
    monkeypatch.setattr(paths, 'ProfileBinding', lambda: SimpleNamespace(root=lambda: tmp_path, is_current=lambda: True))
    monkeypatch.setattr(ui, 'read', lambda url, *_: sample('07' if 'ids=' in url else '06' if 'wd=' in url else '05'))

    @contextmanager
    def fake_reserve(target, scope, **kw):
        yield SimpleNamespace(
            request_id='a' * 32,
            require_current=lambda: None,
            host_call=lambda op, body, timeout=18: (
                control.append((op, body))
                or {'url': 'http://127.0.0.1:3189/stream/' + 'b' * 32 + '/video.mkv', 'size': 2048}
            ),
            submit=lambda handle, media_url, **skw: submit.append((handle, media_url, skw['ready']())),
        )

    monkeypatch.setattr(owned_playback, 'reserve_playback', fake_reserve)

    def make_item(label, target, folder=True, label2='', properties=None, info=None, *, playable=True):
        li = sys.modules['xbmcgui'].ListItem(label)
        return target, li, folder

    try:
        # 1. Browse home -> click Search
        ui.execute_directory(11, {'action': 'browse', 'source': src.id}, store, make_item)
        search_url = rendered[0][0]
        assert 'fixture-token' not in search_url
        # 2. Search -> select first result
        rendered.clear()
        ui.execute_directory(11, dict(parse_qsl(urlsplit(search_url).query)), store, make_item)
        detail_url = rendered[0][0]
        assert 'xy:series:001' not in detail_url
        # 3. Detail -> select second line, second episode (index 3)
        rendered.clear()
        ui.execute_directory(11, dict(parse_qsl(urlsplit(detail_url).query)), store, make_item)
        play_url = rendered[3][0]
        assert 'line:B' not in play_url and 'xy:series:001' not in play_url
        # 4. Play -> single Host IPC submission without raw endpoint/vod_id/line in IPC
        ui.execute_directory(11, dict(parse_qsl(urlsplit(play_url).query)), store, make_item)
        assert len(control) == len(submit) == 1
        assert control[0][0] == 'source_stream_open'
        assert 'fixture-token' not in str(control) and 'line:B' not in str(control) and 'xy:series:001' not in str(control)
        assert submit[0][0] == 11 and submit[0][2] and submit[0][1].startswith('http://127.0.0.1:')
    finally:
        store.close()


def test_existing_add_source_entry_previews_origins_and_keeps_old_subscription(tmp_path, monkeypatch):
    from bobbi_platform import library_ui, paths, source_library_ui
    source_db = Registry(tmp_path / 'libraries.sqlite3')
    outcomes, confirmations = [], []
    data = [sample('02')]
    def choose(heading, options):
        return options.index('小雅 / TVBox（T4）') if heading == '添加来源' else 0
    def confirm(heading, body):
        confirmations.append(body)
        return True
    dialog = SimpleNamespace(select=choose, input=lambda *_: BASE, yesno=confirm, ok=lambda *a:outcomes.append(a))
    monkeypatch.setattr(library_ui.cd2_mounts, 'discover', lambda: ())
    monkeypatch.setattr(paths, 'ProfileBinding', lambda: SimpleNamespace(require_current=lambda:None))
    monkeypatch.setattr(source_library_ui, 'operation', lambda f:f(10**12, lambda:False))
    monkeypatch.setattr(ui, 'read', lambda *args:data[0])
    try:
        assert library_ui.add_source(dialog, None, source_db)
        assert len(source_db.sources()) == 1
        saved = source_db.source_snapshot(source_db.sources()[0].id)
        assert 't4.example.invalid' in confirmations[0] and 'fixture-token' not in confirmations[0]
        assert library_ui.add_source(dialog, None, source_db)
        assert source_db.source_snapshot(saved[0].id) == saved and len(source_db.sources()) == 1
        data[0] = sample('03')
        assert not library_ui.add_source(dialog, None, source_db)
        assert source_db.source_snapshot(saved[0].id) == saved
        assert '没有可用' in outcomes[-1][1]
    finally:
        source_db.close()
