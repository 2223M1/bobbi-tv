"""Real prepared readers never discover a new profile/account/Host on retry."""
import builtins
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from threading import Lock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi'))

from bobbi_core import prepared_index, prepared_retry, preparation_client
from bobbi_core.capabilities import descriptor
from bobbi_platform import prepared_sessions, runtime
from bobbi_platform.paths import ProfileBinding


ACCOUNT = dict(account_id='115:' + 'a' * 64, epoch=3, authenticated=True)


def projection(path):
    value = dict(schema_version=1, prepared_schema=2, generation=2, account='fixture',
        account_scope=ACCOUNT, mount_root=prepared_index.MOUNT_ROOT,
        titles=[dict(kind='movie', tmdb_id='1', sources=[])])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return value


def test_real_core_import_and_read_do_not_import_platform_or_kodi(tmp_path, monkeypatch):
    path = tmp_path / 'prepared.json'
    expected = projection(path)
    original = builtins.__import__
    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Core read discovered its environment: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', imported)
    importlib.reload(prepared_index)
    importlib.reload(prepared_retry)
    assert prepared_index.load(path, account_current=lambda scope: scope == ACCOUNT) == expected
    assert prepared_index.load(path)['titles'] == []
    assert prepared_retry.verified_entry({}, None, {}) is None
    probe = prepared_retry.ReadyProbe({'info_hash': 'a' * 40})
    assert not probe.poll('a' * 40, {}, lambda: False, float('inf'))
    assert probe.nonce is None
    data = {}
    with pytest.raises(RuntimeError):
        preparation_client.capture_account(data, allow_capture=False)
    assert data == {'_account': None}


def test_profile_a_b_a_revokes_reader_and_never_reads_other_root(tmp_path):
    current, calls = ['a'], []
    binding = ProfileBinding(lambda addon: tmp_path / current[0] / addon)
    root = binding.root('plugin.video.bobbi')
    expected = projection(root / 'bobi-prepared.json')
    projection(tmp_path / 'b' / 'plugin.video.bobbi' / 'bobi-prepared.json')
    def call(action, body, timeout):
        calls.append(action)
        return ACCOUNT
    session = prepared_sessions.PreparedSession(root, call, ACCOUNT, binding.is_current)
    assert session.load_index() == expected
    current[0] = 'b'
    with pytest.raises(RuntimeError):
        session.load_index()
    count = len(calls)
    current[0] = 'a'
    with pytest.raises(RuntimeError):
        session.load_index()
    assert len(calls) == count


@pytest.mark.parametrize('change', ['epoch', 'logout', 'unknown'])
def test_account_change_and_unknown_are_irrevocable(tmp_path, change):
    live, calls = [dict(ACCOUNT)], []
    def call(action, body, timeout):
        calls.append(action)
        if live[0] is None:
            raise OSError('unknown')
        return live[0]
    session = prepared_sessions.PreparedSession(tmp_path, call, ACCOUNT, lambda: True)
    assert session.account_current(ACCOUNT)
    live[0] = (None if change == 'unknown' else
               dict(account_id='', epoch=4, authenticated=False) if change == 'logout' else
               dict(ACCOUNT, epoch=4))
    assert not session.account_current(ACCOUNT)
    count = len(calls)
    live[0] = dict(ACCOUNT)
    assert not session.account_current(ACCOUNT)
    assert len(calls) == count
    with pytest.raises(RuntimeError):
        session.call('prepare', {})
    assert len(calls) == count


def test_capture_failure_remains_none_after_service_recovers(tmp_path, monkeypatch):
    binding = ProfileBinding(lambda addon: tmp_path / addon)
    calls, online = [], [False]
    def call(action, body, timeout):
        calls.append(action)
        if not online[0]:
            raise OSError('not ready')
        return ACCOUNT
    monkeypatch.setattr(runtime, 'bind_call', lambda path: call)
    data = {}
    assert prepared_sessions.capture(data, binding=binding) is None
    assert data == {'_account': None}
    online[0] = True
    assert prepared_sessions.capture(data, binding=binding) is None
    assert calls == ['account_status']


def test_real_host_registration_replacement_cannot_rebind(tmp_path):
    path = tmp_path / 'runtime.json'
    first_calls, second_calls = [], []
    def first(action, body):
        first_calls.append(action)
        return ACCOUNT
    def second(action, body):
        second_calls.append(action)
        return ACCOUNT
    first_host = runtime.Runtime(first, path)
    second_host = None
    try:
        first_host.start()
        initial = path.read_text()
        session = prepared_sessions.PreparedSession(tmp_path, runtime.bind_call(path), ACCOUNT, lambda: True)
        assert session.account_current(ACCOUNT)
        first_host.close()
        second_host = runtime.Runtime(second, path)
        second_host.start()
        assert not session.account_current(ACCOUNT)
        replacement = path.read_text()
        path.write_text(initial)
        assert not session.account_current(ACCOUNT)
        path.write_text(replacement)
        assert first_calls == ['account_status'] and second_calls == []
    finally:
        first_host.close()
        if second_host is not None:
            second_host.close()


def test_unknown_prepare_reply_is_not_retried_and_account_probe_has_no_owner_lock(tmp_path):
    owner_lock, calls = Lock(), []
    def call(action, body, timeout):
        assert 0 < timeout <= .3
        calls.append(action)
        if action == 'account_status':
            assert owner_lock.acquire(blocking=False)
            owner_lock.release()
            return ACCOUNT
        with owner_lock:
            raise OSError('reply unknown')
    session = prepared_sessions.PreparedSession(tmp_path, call, ACCOUNT, lambda: True)
    with pytest.raises(OSError):
        session.call('prepare', {'request_id': 'a' * 32})
    assert calls.count('preparation') == 1
    assert session.account_current(ACCOUNT)
    assert calls.count('preparation') == 1  # A read cannot replay a mutation.


def test_missing_or_false_account_checker_cannot_advertise_prepared_rows(tmp_path):
    path = tmp_path / 'prepared.json'
    projection(path)
    for checker in (None, lambda scope: False, lambda scope: None):
        assert prepared_index.load(path, account_current=checker)['titles'] == []


def test_explicit_unknown_account_never_uses_bound_account(tmp_path):
    session = prepared_sessions.PreparedSession(tmp_path,
        lambda *a, **kw: pytest.fail('Unknown account must fail before transport'), ACCOUNT, lambda: True)
    with pytest.raises(RuntimeError):
        session.call('prepare', {}, expected_account=None)


def test_font_preflight_uses_bound_transport_and_unknown_account_stays_unavailable(tmp_path, monkeypatch):
    calls = []
    def call(action, body, timeout):
        calls.append(action)
        return ACCOUNT if action == 'account_status' else dict(component=descriptor(), state='unavailable')
    session = prepared_sessions.PreparedSession(tmp_path, call, ACCOUNT, lambda: True)
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: pytest.fail('Fonts must not discover current Host'))
    data = dict(prepared_resource_id='a' * 64, prepared_source_info_hash='b' * 40, _account=None)
    assert session.prepare_fonts(data, dict(request_id='c' * 32))['state'] == 'unavailable'
    assert calls == [] and data['_account'] is None
    data['_account'] = dict(ACCOUNT)
    assert session.prepare_fonts(data, dict(request_id='c' * 32))['state'] == 'unavailable'
    assert calls == ['account_status', 'preparation']


def test_explicit_failed_reader_never_uses_plugin_capture(tmp_path, monkeypatch):
    from lib.clients import bobbi_library
    monkeypatch.setattr(prepared_sessions, 'capture', lambda *a, **k: pytest.fail('late capture'))
    assert bobbi_library.load_prepared_index(session=None)['titles'] == []
    assert bobbi_library.load_ready_index(session=None)['titles'] == []
    assert bobbi_library.prepared_generation(session=None) is None
    assert bobbi_library.load_index(session=None)['titles'] == []


def test_real_core_resolver_uses_only_injected_host_and_copied_account(monkeypatch):
    seen = []
    def call(action, body, timeout):
        seen.append((action, deepcopy(body)))
        if action == 'account_status':
            return ACCOUNT
        return dict(component=descriptor(), state='unavailable')
    original = builtins.__import__
    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Explicit preparation transport fell back to environment')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', imported)
    data = dict(request_id='b' * 32, ids={'tmdb_id': '1'}, mode='movie')
    entry = dict(key='c' * 64, prepared_source_info_hash='d' * 40)
    assert preparation_client.resolve_entry(data, dict(generation=2, account='fixture'), entry,
                                             host_call=call) is None
    assert data['_account'] == ACCOUNT
    data['_account']['epoch'] = 99
    assert seen[-1][1]['account'] == ACCOUNT
