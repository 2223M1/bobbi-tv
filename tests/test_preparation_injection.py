"""Preparation transport is explicit; subtitle capture stays on the real owner."""
import ast
import builtins
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread, get_ident
from types import SimpleNamespace

import pytest

from bobbi_core import preparation_client as client
from bobbi_core.capabilities import descriptor
from bobbi_core.subtitle_lookup_portable import SubtitleLookup
from bobbi_platform import prepared_sessions, runtime
from bobbi_platform.host import Host
from test_accounts import logged_in, credential

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = dict(account_id='115:' + 'a' * 64, epoch=1, authenticated=True)


def receipt(**changes):
    return dict(dict(native_instance='instance-a', request_id='a' * 32,
        file_identity='file-a', url_sha256='b' * 64,
        subtitle_intent=0, subtitle_auto_intent=0), **changes)


def drain(lookup):
    if lookup.worker is not None:
        lookup.worker.join(2)
        assert not lookup.worker.is_alive()
    lookup.tick()


def test_actual_core_io_never_imports_platform_or_kodi(monkeypatch):
    requests = []
    def host_call(action, body, timeout):
        assert 0 < timeout <= .3
        requests.append((action, deepcopy(body)))
        return ACCOUNT if action == 'account_status' else dict(component=descriptor(), state='unavailable')
    original = builtins.__import__
    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Core discovered its environment: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', imported)
    data = dict(request_id='c' * 32, ids={'tmdb_id': '1'}, mode='movie',
        prepared_resource_id='d' * 64, prepared_source_info_hash='e' * 40)
    assert client.capture_account(data, host_call=host_call) == ACCOUNT
    assert client.call('status', {}, host_call=host_call)['state'] == 'unavailable'
    assert client.prepare_fonts(data, dict(request_id=data['request_id']), host_call=host_call)['state'] == 'unavailable'
    entry = dict(key='d' * 64, prepared_source_info_hash='e' * 40)
    assert client.resolve_entry(data, dict(generation=1, account='fixture'), entry, host_call=host_call) is None
    missing = {}
    with pytest.raises(RuntimeError, match='BINDING_REQUIRED'):
        client.capture_account(missing)
    assert missing == {'_account': None}
    with pytest.raises(RuntimeError, match='BINDING_REQUIRED'):
        client.call('status', {}, expected_account=ACCOUNT)
    assert [body['method'] for action, body in requests if action == 'preparation'] == ['status', 'font_preflight', 'resolve']


@pytest.mark.parametrize('initial', [None, 'error'])
def test_same_receipt_failed_capture_never_adopts_later_login(initial):
    captures, calls, available = [], [], [False]
    def capture(row):
        captures.append(get_ident())
        if not available[0]:
            if initial == 'error':
                raise OSError('unavailable')
            return None
        def call(method, body, timeout):
            calls.append((get_ident(), body['request_id']))
            return dict(state='ready')
        return call
    owner = get_ident()
    lookup = SubtitleLookup(capture=capture)
    try:
        row = receipt()
        assert lookup.request(row)['state'] == 'unavailable'
        available[0] = True
        assert lookup.request(row)['state'] == 'unavailable'
        assert captures == [owner] and not calls and lookup.worker is None
        changed = receipt(subtitle_intent=1, subtitle_auto_intent=1)
        assert lookup.request(changed)['state'] == 'pending'
        drain(lookup)
        assert lookup.request(changed)['state'] == 'ready'
        # Result consumption clears the job key, never the account-binding slot.
        assert lookup.key is None
        assert lookup.request(changed)['state'] == 'pending'
        drain(lookup)
        assert captures == [owner, owner]
        assert all(thread != owner for thread, _ in calls)
    finally:
        lookup.close()


def test_latest_slot_and_cancellation_discard_stale_worker_even_on_aba():
    begun, release = Event(), Event()
    captures = []
    def capture(row):
        number = len(captures)
        captures.append(row['native_instance'])
        def call(method, body, timeout):
            if number == 0:
                begun.set()
                assert release.wait(2)
            return dict(state='ready', binding=number)
        return call
    lookup = SubtitleLookup(capture=capture)
    try:
        assert lookup.request(receipt())['state'] == 'pending'
        assert begun.wait(1)
        lookup.request(receipt(native_instance='instance-b'))
        lookup.request(receipt())
        release.set()
        drain(lookup)  # old A may complete, but cannot publish into new A's slot.
        drain(lookup)
        assert lookup.request(receipt()) == dict(state='ready', binding=2)
        lookup.cancel()
        assert lookup.request(receipt())['state'] == 'unavailable'
        assert captures == ['instance-a', 'instance-b', 'instance-a']
        assert lookup.request(receipt(subtitle_intent=1))['state'] == 'pending'
        drain(lookup)
        assert len(captures) == 4
    finally:
        release.set()
        lookup.close()


@pytest.fixture
def native_host(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    from lib.services.playback_control import PlaybackControlServer
    accounts, scope = logged_in(tmp_path)
    profile = [True]
    host = Host(tmp_path / 'platform', plugin_root=tmp_path / 'plugin', profile_current=lambda: profile[0])
    host.accounts = accounts
    calls, captures = [], []
    original = accounts.snapshot
    def snapshot():
        captures.append(get_ident())
        return original()
    monkeypatch.setattr(accounts, 'snapshot', snapshot)
    def request(method, body, expected):
        accounts.require_current(expected)
        calls.append((method, dict(expected), get_ident()))
        return dict(component=descriptor(), state='ready', account_scope=dict(expected))
    host.preparation = SimpleNamespace(request=request)
    control = PlaybackControlServer(path=None, host=host)
    native = control.native
    native.subtitle_fallback.accounts = accounts
    try:
        yield SimpleNamespace(native=native, host=host, accounts=accounts, scope=scope,
            calls=calls, captures=captures, profile=profile)
    finally:
        control.close()


def test_real_native_captures_actual_host_on_owner_and_never_rebinds_after_account_change(native_host, monkeypatch):
    p = native_host
    owner = get_ident()
    monkeypatch.setattr(prepared_sessions, 'capture', lambda *a, **kw: pytest.fail('Resident host must not use locator'))
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: pytest.fail('Resident host must not use HTTP locator'))
    assert p.native.subtitle_lookup.request(receipt())['state'] == 'pending'
    assert p.captures[0] == owner
    drain(p.native.subtitle_lookup)
    assert p.native.subtitle_lookup.request(receipt())['account_scope'] == p.scope
    assert p.calls[0][2] != owner
    p.accounts.logout(p.scope)
    p.accounts.install(credential(), p.accounts.snapshot())
    current = p.accounts.snapshot()
    assert current != p.scope
    p.native.subtitle_lookup.request(receipt())
    drain(p.native.subtitle_lookup)
    assert p.native.subtitle_lookup.request(receipt())['state'] == 'unavailable'
    assert len(p.calls) == 1
    next_row = receipt(native_instance='instance-b')
    p.native.subtitle_lookup.request(next_row)
    drain(p.native.subtitle_lookup)
    assert p.native.subtitle_lookup.request(next_row)['account_scope'] == current
    assert len(p.calls) == 2


def test_logged_out_native_keeps_fallback_and_same_slot_cancellation(native_host):
    p = native_host
    p.accounts.logout(p.scope)
    fallback = []
    p.native.subtitle_fallback.request = lambda row: fallback.append(row) or dict(state='candidate', origin='fixture')
    assert p.native.external_subtitle(receipt()) == dict(state='candidate', origin='fixture')
    assert p.native.subtitle_lookup.worker is None and not p.calls
    p.accounts.install(credential(), p.accounts.snapshot())
    assert p.native.external_subtitle(receipt())['state'] == 'candidate'
    assert not p.calls
    row = receipt(subtitle_intent=1)
    p.native.external_subtitle(row)
    drain(p.native.subtitle_lookup)
    p.native.cancel_external_subtitle_lookup()
    assert p.native.subtitle_lookup.request(row)['state'] == 'unavailable'
    assert p.native.subtitle_fallback.cancel.is_set()
    assert len(fallback) == 3


def test_real_native_profile_revoke_cannot_return_to_old_host(native_host):
    p = native_host
    p.native.subtitle_lookup.request(receipt())
    drain(p.native.subtitle_lookup)
    p.native.subtitle_lookup.request(receipt())
    p.profile[0] = False
    p.native.subtitle_lookup.request(receipt())
    drain(p.native.subtitle_lookup)
    assert p.native.subtitle_lookup.request(receipt())['state'] == 'unavailable'
    p.profile[0] = True
    p.native.subtitle_lookup.request(receipt(native_instance='instance-b'))
    assert p.native.subtitle_lookup.worker is None
    assert len(p.calls) == 1


def test_inflight_runtime_token_replacement_permanently_revokes_bound_session(tmp_path):
    path = tmp_path / 'runtime.json'
    begun, release = Event(), Event()
    calls = []
    def dispatch(action, body):
        calls.append(action)
        if action == 'account_status':
            return ACCOUNT
        begun.set()
        assert release.wait(2)
        return dict(component=descriptor(), state='ready')
    server = runtime.Runtime(dispatch, path)
    server.start()
    errors = []
    session = prepared_sessions.PreparedSession(tmp_path, runtime.bind_call(path), ACCOUNT, lambda: True)
    def work():
        try:
            session.call('status', {})
        except Exception as error:
            errors.append(type(error))
    worker = Thread(target=work)
    original = path.read_text()
    try:
        worker.start()
        assert begun.wait(1)
        value = json.loads(original)
        value['token'] = 'f' * 64 if value['token'] != 'f' * 64 else 'e' * 64
        path.write_text(json.dumps(value))
        release.set()
        worker.join(2)
        assert not worker.is_alive() and errors == [OSError]
        path.write_text(original)
        assert not session.account_current(ACCOUNT)
        assert calls == ['account_status', 'preparation']
    finally:
        release.set()
        worker.join(2)
        path.write_text(original)
        server.close()


def test_readiness_probe_executes_bound_session_without_fake_kodi():
    path = ROOT / 'tools/ce_transport_readiness_probe.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    remote = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Attribute) and target.attr == 'REMOTE' for target in node.targets))
    ast.parse(remote)
    assert 'bind_call(' in remote and 'session.load_index()' in remote
    assert 'session.call(' in remote and 'session.resolve_entry(' in remote
    assert "sys.modules['xbmcvfs']" not in remote


@pytest.mark.parametrize('order', ['legacy-first', 'core-first'])
def test_real_legacy_wrapper_runs_in_both_import_orders(tmp_path, order):
    script = r'''
import importlib, json, sys, types
from pathlib import Path
sys.path[:0] = sys.argv[1:4]
root = Path(sys.argv[4])
names = ['lib.cinema.preparation_client', 'bobbi_core.preparation_client']
if sys.argv[5] == 'core-first': names.reverse()
first, second = (importlib.import_module(name) for name in names)
legacy = importlib.import_module('lib.cinema.preparation_client')
core = importlib.import_module('bobbi_core.preparation_client')
assert legacy is not core and legacy.source_intent is core.source_intent
from bobbi_platform import runtime, prepared_sessions
from bobbi_core.capabilities import descriptor
scope = dict(account_id='115:'+'a'*64,epoch=1,authenticated=True)
calls=[]
resolves=[]
captures=[]
original_capture=prepared_sessions.capture
def capture(*args,**kwargs):
 captures.append(True)
 return original_capture(*args,**kwargs)
prepared_sessions.capture=capture
def dispatch(action,body):
 calls.append(action)
 if action == 'account_status': return scope
 if body['method']=='resolve':
  resolves.append(body['body']['verification_id'])
  if len(resolves)==1:return dict(component=descriptor(),state='pending')
  return dict(component=descriptor(),state='ready',**body['body'],file_id='fixture-file',
   path='/fixture.mkv',bytes=100,version_key='fixture-version')
 return dict(component=descriptor(),state='unavailable')
sys.modules['xbmcvfs']=types.SimpleNamespace(translatePath=lambda path:str(root/path.split('/')[-1]))
server=runtime.Runtime(dispatch,root/'script.module.bobbi.platform/runtime.json')
server.start()
try:
 data={}
 assert legacy.capture_account(data)==scope and data['_account']==scope
 before=len(calls)
 assert legacy.capture_account(data)==scope and len(calls)==before
 assert legacy.call('status',{},expected_account=scope)['state']=='unavailable'
 data.update(request_id='b'*32,ids={'tmdb_id':'1'},mode='movie',prepared_resource_id='c'*64,prepared_source_info_hash='d'*40)
 entry=dict(key='c'*64,prepared_source_info_hash='d'*40,prepared_file_id='fixture-file',
  path='/fixture.mkv',bytes=100,prepared_version_key='fixture-version')
 before_capture=len(captures)
 assert legacy.resolve_entry(data,dict(generation=1,account='fixture'),entry)==entry
 assert len(captures)==before_capture+1 and len(resolves)==2 and len(set(resolves))==1
 assert legacy.prepare_fonts(data,dict(request_id=data['request_id']))['state']=='unavailable'
 unknown={'_account':None}
 before=len(calls)
 try: legacy.capture_account(unknown)
 except RuntimeError: pass
 else: raise AssertionError('Unknown account was adopted')
 assert len(calls)==before
 assert core.call.__module__=='bobbi_core.preparation_client'
 assert calls.count('preparation')==4
 before=len(calls)
 assert legacy.prepare_fonts({}, {})==dict(state='not_applicable')
 assert legacy.resolve_entry({}, {}, {}) is None
 try:legacy.prepare_fonts(data,{},lambda:True)
 except RuntimeError:pass
 else:raise AssertionError('Cancellation was lost')
 try:legacy.call('not_supported',{})
 except ValueError:pass
 else:raise AssertionError('Invalid command admitted')
 assert len(calls)==before
finally: server.close()
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
        str(ROOT / 'addons/plugin.video.bobbi'), str(ROOT / 'addons/script.module.bobbi.core/lib'),
        str(ROOT / 'addons/script.module.bobbi.platform/lib'), str(tmp_path), order],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
