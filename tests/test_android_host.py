import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bobbi_platform import android_engine as engine, android_updates as updates
from bobbi_platform.updates import UpdateError


def test_engine_starts_lazily_and_returns_host_config(tmp_path):
    path = tmp_path/'no_backup/engine-backend.json'
    path.parent.mkdir()
    value = {'schema': 1, 'endpoint': 'http://127.0.0.1:8090', 'auth': None,
             'metadata_seconds': 30, 'buffering_seconds': 90}
    path.write_text(json.dumps(value))
    calls = []
    def rpc(action):
        calls.append(action)
        if action == 'engine_start':
            return {'state': 'REQUESTED'}
        return ({'state': 'STOPPED'} if len(calls) == 1 else
                {'state': 'RUNNING', 'config_path': str(path)})
    assert engine.configuration(call=rpc, wait=lambda _: False) == value
    assert calls == ['engine_status', 'engine_start', 'engine_status']


def test_cancelled_engine_does_not_start():
    calls = []
    with pytest.raises(RuntimeError, match='CANCELLED'):
        engine.configuration(cancelled=lambda: True, call=calls.append, wait=lambda _: False)
    assert calls == []


@pytest.mark.parametrize('state', ['STOPPING', 'STOP_UNCONFIRMED'])
def test_engine_does_not_duplicate_unconfirmed_owner(state):
    calls = []
    with pytest.raises(RuntimeError, match='STOPPING'):
        engine.configuration(call=lambda action: calls.append(action) or {'state': state}, wait=lambda _: False)
    assert calls == ['engine_status']


def test_engine_timeout_is_bounded():
    now = [0]
    def wait(amount):
        now[0] += amount
        return False
    with pytest.raises(RuntimeError, match='TIMEOUT'):
        engine.configuration(call=lambda _: {'state': 'STARTING'}, clock=lambda: now[0], wait=wait)
    assert 32 <= now[0] < 33


def offer(abi='arm64-v8a', version=2026102073):
    return dict(version_code=version, abi=abi, size=250*1024**2, sha256='a'*64,
        url='https://github.com/2223M1/bobbi-tv/releases/download/android2073/BobbiTV-2073-android-'+abi+'.apk')


def feed(rows):
    return json.dumps({'schema': 1, 'releases': rows})


def test_updates_choose_abi_and_monotonic_version():
    rows = [offer(), offer('armeabi-v7a')]
    assert updates.parse_feed(feed(rows), 'arm64-v8a', 2026102072) == rows[0]
    assert updates.parse_feed(feed(rows), 'arm64-v8a', 2026102073) is None
    assert updates.parse_feed(feed([]), 'arm64-v8a', 0) is None


def test_empty_mirror_does_not_hide_new_origin_release(monkeypatch):
    def transfer(url, maximum, consume, cancelled):
        consume(feed([] if url == updates.FEEDS[0] else [offer()]).encode())
    monkeypatch.setattr(updates, 'transfer', transfer)
    assert updates.latest('arm64-v8a', 2026102072) == offer()


@pytest.mark.parametrize('field,value', [('url', 'https://example.com/x.apk'), ('size', 2**40),
    ('version_code', True), ('sha256', 'broken'), ('abi', 'x86_64')])
def test_bad_android_offers_fail_closed(field, value):
    row = offer()
    row[field] = value
    with pytest.raises(UpdateError):
        updates.parse_feed(feed([row]), 'arm64-v8a', 0)


def test_duplicate_android_offers_are_not_arbitrarily_selected():
    with pytest.raises(UpdateError):
        updates.parse_feed(feed([offer(), offer()]), 'arm64-v8a', 0)


def test_cancelled_download_keeps_previous_candidate(tmp_path):
    directory = tmp_path/'bobbi-update'
    directory.mkdir()
    old = directory/'update.apk'
    old.write_bytes(b'old complete apk')
    def partial(stream):
        stream.write(b'partial')
        raise updates.Cancelled('cancelled')
    with pytest.raises(updates.Cancelled):
        updates.stage(directory, partial)
    assert old.read_bytes() == b'old complete apk'
    assert list(directory.iterdir()) == [old]


def test_completed_stage_publishes_only_after_writer_returns(tmp_path):
    directory = tmp_path/'bobbi-update'
    path = updates.stage(directory, lambda stream: stream.write(b'complete'))
    assert path.read_bytes() == b'complete'


def test_download_detects_corruption_before_candidate_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, 'transfer', lambda url, maximum, consume, *args: consume(b'bad'))
    with pytest.raises(UpdateError, match='INCOMPLETE'):
        updates.download(offer(), tmp_path/'bobbi-update')
    assert not (tmp_path/'bobbi-update/update.apk').exists()


def test_android_host_patch_declares_ui_locale_in_jsonrpc_schema():
    root = Path(__file__).resolve().parents[1]
    patch_text = (root / 'native/patches/0004-bobbi-android-host.patch').read_text(encoding='utf-8')
    added_lines = []
    in_methods = False
    for line in patch_text.splitlines():
        if line.startswith('+++ b/xbmc/interfaces/json-rpc/schema/methods.json'):
            in_methods = True
            continue
        if in_methods and line.startswith('diff --git '):
            break
        if in_methods and line.startswith('+') and not line.startswith('+++'):
            added_lines.append(line[1:])
    snippet = '{' + '\n'.join(added_lines).rstrip().rstrip(',') + '}'
    schema = json.loads(snippet)['System.BobiAndroid']
    action_param = next(p for p in schema['params'] if p['name'] == 'action')
    assert 'ui_locale' in action_param['enum']
    assert action_param['enum'] == ['info', 'engine_status', 'engine_start', 'engine_stop', 'install', 'ui_locale']


def test_sync_ui_locale_enforces_applied_readback_and_rejects_mismatch():
    calls = []

    def ok_call(action, argument=''):
        calls.append((action, argument))
        return {'state': 'APPLIED', 'ui_locale': 'en' if argument == 'en_gb' else 'zh'}

    assert engine.sync_ui_locale('zh_cn', call=ok_call) == {'state': 'APPLIED', 'ui_locale': 'zh'}
    assert engine.sync_ui_locale('resource.language.en_gb', call=ok_call) == {'state': 'APPLIED', 'ui_locale': 'en'}
    assert calls == [('ui_locale', 'zh_cn'), ('ui_locale', 'en_gb')]

    with pytest.raises(RuntimeError, match='ANDROID_LOCALE_SYNC_FAILED'):
        engine.sync_ui_locale('en_gb', call=lambda *a: {'state': 'REJECTED'})

    with pytest.raises(RuntimeError, match='ANDROID_LOCALE_SYNC_FAILED'):
        engine.sync_ui_locale('en_gb', call=lambda *a: {'state': 'APPLIED', 'ui_locale': 'zh'})


def test_live_zh_en_zh_syncs_running_android_engine_without_restart_and_syncs_vs10(tmp_path, monkeypatch):
    import sys
    root = Path(__file__).resolve().parents[1]
    bobbi_root = str(root / 'addons/plugin.video.bobbi')
    if bobbi_root not in sys.path:
        sys.path.insert(0, bobbi_root)

    active_locale = {'lang': 'resource.language.zh_cn'}
    home_props = {}
    rpc_calls = []

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        getInfoLabel=lambda key: active_locale['lang'] if key == 'System.Language' else '',
        getCondVisibility=lambda expr: True,
        Monitor=object,
        LOGINFO=1,
        LOGWARNING=2,
        LOGERROR=3,
        log=lambda *a, **kw: None,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Window=lambda wid: SimpleNamespace(
            setProperty=lambda k, v: home_props.__setitem__(k, v),
            getProperty=lambda k: home_props.get(k, ''),
        ),
    ))

    def fake_host_request(action, argument=''):
        rpc_calls.append((action, argument))
        if action == 'ui_locale':
            return {'state': 'APPLIED', 'ui_locale': 'en' if argument == 'en_gb' else 'zh'}
        return {'state': 'RUNNING'}

    monkeypatch.setattr(engine, 'available', lambda: True)
    monkeypatch.setattr(engine, 'request', fake_host_request)

    from lib import portable_runtime as pr
    pr._HOST_UI_STATE['android_locale'] = None

    # VS10 sysfs check + initial Android locale bind (ZH)
    sys_dir = tmp_path / 'sys'
    (sys_dir / 'module/amdolby_vision').mkdir(parents=True)
    pr._sync_host_ui_properties(force_locale=True, sys_root=sys_dir, platform_name='linux')
    assert home_props.get('Bobbi.Host.SupportsVS10') == 'true'
    assert rpc_calls == [('ui_locale', 'zh_cn')]

    # Non-VS10 host clears property
    empty_sys = tmp_path / 'sys_empty'
    empty_sys.mkdir()
    pr._sync_host_ui_properties(force_locale=False, sys_root=empty_sys, platform_name='linux')
    assert home_props.get('Bobbi.Host.SupportsVS10') == ''
    assert rpc_calls == [('ui_locale', 'zh_cn')]  # Unchanged locale does not spam RPC!

    # Live switch ZH -> EN -> ZH while EngineService stays RUNNING (zero engine_stop / engine_start!)
    active_locale['lang'] = 'resource.language.en_gb'
    pr._sync_android_locale(force=False)
    assert rpc_calls == [('ui_locale', 'zh_cn'), ('ui_locale', 'en_gb')]
    pr._sync_android_locale(force=False)
    assert len(rpc_calls) == 2

    active_locale['lang'] = 'resource.language.zh_cn'
    pr._sync_android_locale(force=False)
    assert rpc_calls == [('ui_locale', 'zh_cn'), ('ui_locale', 'en_gb'), ('ui_locale', 'zh_cn')]
    assert not any(act in ('engine_stop', 'engine_start') for act, _ in rpc_calls)


def test_android_engine_show_presents_100_percent_english_under_en_gb(tmp_path, monkeypatch):
    import re
    import sys

    cjk_re = re.compile(r'[\u4e00-\u9fff]')
    active = {'lang': 'resource.language.en_gb', 'playing': False, 'state': 'STOPPED', 'choice': 0}
    seen_texts = []

    cfg_path = tmp_path / 'no_backup/engine-backend.json'
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({
        'schema': 1, 'endpoint': 'http://127.0.0.1:8090', 'auth': None,
        'metadata_seconds': 30, 'buffering_seconds': 90,
    }), encoding='utf-8')

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        getInfoLabel=lambda key: active['lang'] if key == 'System.Language' else '',
        getCondVisibility=lambda _: False,
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda _: False),
        Player=lambda: SimpleNamespace(isPlaying=lambda: active['playing']),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda p: str(tmp_path / 'vfs')))
    monkeypatch.setattr('bobbi_platform.bt_setup.adapter_state', lambda _: None)
    monkeypatch.setattr(
        'bobbi_platform.bt_setup._backend_module',
        lambda: SimpleNamespace(Backend=lambda _cfg: SimpleNamespace(ready=lambda _c: None, close=lambda: None)),
    )
    monkeypatch.setattr(engine, 'available', lambda: True)

    def fake_request(action, argument=''):
        if action == 'ui_locale':
            return {'state': 'APPLIED', 'ui_locale': 'en' if argument == 'en_gb' else 'zh'}
        if action == 'engine_start':
            active['state'] = 'RUNNING'
            return {'state': 'REQUESTED'}
        if action == 'engine_stop':
            active['state'] = 'STOPPED'
            return {'state': 'REQUESTED'}
        if action == 'engine_status':
            if active['state'] == 'UNAVAILABLE':
                raise RuntimeError('ANDROID_HOST_UNAVAILABLE')
            return {'state': active['state'], 'config_path': str(cfg_path)}
        raise AssertionError(action)

    monkeypatch.setattr(engine, 'request', fake_request)

    dialog = SimpleNamespace(
        select=lambda heading, opts: (seen_texts.extend([heading, *opts]) or active['choice']),
        ok=lambda heading, body: seen_texts.extend([heading, body]),
    )

    # 1. Start & ready
    assert engine.show(dialog) is True
    # 2. Stop blocked while playing
    active['choice'] = 1
    active['playing'] = True
    assert engine.show(dialog) is False
    # 3. Stop when idle
    active['playing'] = False
    assert engine.show(dialog) is False
    # 4. Error fallback dialog
    active['state'] = 'UNAVAILABLE'
    assert engine.show(dialog) is False

    assert len(seen_texts) >= 12
    for text in seen_texts:
        assert text and not cjk_re.search(text), f'Unexpected CJK in English Android BT UI: {text!r}'
