"""Keep one preparation transport and avoid owner IPC for local no-op retries.

The native method bodies and Host/Session account admission are production code.
Only the transport and worker scheduling are substituted by the shared fixture.
No real device, network account, or native player is controlled by these tests.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import sys
from threading import Event, Thread
import time

import pytest

from test_ce2029_lifecycle_audit import native_prepare
from test_accounts import credential
from bobbi_core import preparation_client, subtitle_lookup, subtitle_lookup_portable
import bobbi_platform.runtime as runtime


def configure_kind(p, kind):
    if kind == 'mdsub':
        p.player.data.update(is_torrent=False, direct_source=dict(provider='mdsub',
            guid='mdsub:' + 'c' * 64, locator='https://pan.mdsub.top/api/raw?fixture',
            title='Fixture.2025.mkv', size=16384))
    return '_direct_prepare_' if kind == 'mdsub' else '_cinema_prepare_'


def count_owner_reads(p):
    original = p.player._owns_playback_session
    calls = []
    def owned():
        calls.append(True)
        return original()
    p.player._owns_playback_session = owned
    return calls


@pytest.mark.parametrize('kind', ['bt', 'mdsub'])
@pytest.mark.parametrize('gate', ['exhausted', 'deferred'])
def test_hundred_noop_ticks_do_not_query_native_owner(native_prepare, kind, gate):
    p = native_prepare
    prefix = configure_kind(p, kind)
    if gate == 'exhausted':
        setattr(p.player, prefix + 'attempts', 6)
    else:
        setattr(p.player, prefix + 'due', p.clock[0] + 30)
    owner_reads = count_owner_reads(p)
    for _ in range(100):
        p.player.start_cinema_preparation()
    assert not p.calls
    assert len(owner_reads) == 0, {'ticks': 100, 'owner_reads': len(owner_reads), 'kind': kind, 'gate': gate}


@pytest.mark.parametrize('kind', ['bt', 'mdsub'])
@pytest.mark.parametrize('state', ['current', 'superseded', 'cancelled', 'switched'])
def test_due_work_still_requires_owner_and_original_account(native_prepare, kind, state):
    p = native_prepare
    prefix = configure_kind(p, kind)
    p.player.data['_account'] = deepcopy(p.initial)
    setattr(p.player, prefix + 'due', p.clock[0])
    if state == 'superseded':
        p.player._owns_playback_session = lambda: False
    elif state == 'cancelled':
        p.player._cinema_cancel.set()
    elif state == 'switched':
        p.accounts.install(credential('456'), p.initial)
    owner_reads = count_owner_reads(p)
    p.player.start_cinema_preparation()
    if state == 'current':
        assert p.calls == [('catalog_prepare' if kind == 'mdsub' else 'prepare', p.initial)]
        assert owner_reads
    else:
        assert not p.calls
        assert owner_reads if state != 'cancelled' else not owner_reads
    assert not getattr(p.player, prefix + 'sent', False)  # fixture deliberately loses the first intake reply


@pytest.mark.parametrize('kind', ['bt', 'mdsub'])
@pytest.mark.parametrize('late', ['cancel', 'superseded', 'switched'])
def test_status_absent_is_not_authority_to_submit_after_late_change(native_prepare, monkeypatch, kind, late):
    p = native_prepare
    prefix = configure_kind(p, kind)
    p.player.data['_account'] = deepcopy(p.initial)
    setattr(p.player, prefix + 'attempts', 1)
    setattr(p.player, prefix + 'due', p.clock[0])
    status_method = 'catalog_status' if kind == 'mdsub' else 'status'
    original = runtime.call
    def transport(action, body, **kwargs):
        result = original(action, body, **kwargs)
        if action == 'preparation' and body['method'] == status_method:
            assert result['state'] == 'absent'
            if late == 'cancel':
                p.player._cinema_cancel.set()
            elif late == 'superseded':
                p.player._owns_playback_session = lambda: False
            else:
                p.accounts.install(credential('456'), p.initial)
        return result
    monkeypatch.setattr(runtime, 'call', transport)
    p.player.start_cinema_preparation()
    assert p.calls == [(status_method, p.initial)]
    assert not getattr(p.player, prefix + 'sent', False)


def test_legacy_subtitle_import_is_exactly_the_portable_class():
    assert subtitle_lookup.SubtitleLookup is subtitle_lookup_portable.SubtitleLookup


def test_plugin_compatibility_import_keeps_the_same_portable_class(native_prepare, monkeypatch):
    # Bootstrap is supplied by the normal plugin before its compatibility
    # imports. Exercise the actual alias file, not a duplicated import string.
    monkeypatch.setattr(sys.modules['lib.cinema'], '_shared', object(), raising=False)
    path = Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi/lib/cinema/subtitle_lookup.py'
    name = '_test_legacy_subtitle_lookup_import'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    assert sys.modules[name].SubtitleLookup is subtitle_lookup_portable.SubtitleLookup


@pytest.mark.parametrize('entry', ['legacy', 'portable'])
def test_both_subtitle_imports_drain_worker_and_discard_late_success(entry):
    began, release, closed = Event(), Event(), Event()
    def call(method, body, timeout):
        began.set()
        assert release.wait(2)
        return {'state': 'ready', 'request_id': body['request_id']}
    cls = (subtitle_lookup.SubtitleLookup if entry == 'legacy'
           else subtitle_lookup_portable.SubtitleLookup)
    lookup = cls(call=call)
    closer = Thread(target=lambda: (lookup.close(), closed.set()), daemon=True)
    try:
        assert lookup.request({'request_id': 'A'}) == {'state': 'pending'}
        assert began.wait(1)
        closer.start()
        deadline = time.monotonic() + 1
        while not lookup.stopped and time.monotonic() < deadline:
            time.sleep(.001)
        assert lookup.stopped
        assert not closed.wait(.03)
        assert lookup.request({'request_id': 'B'})['reason'] == 'SUBTITLE_LOOKUP_STOPPED'
        release.set()
        assert closed.wait(1)
        assert not lookup.worker.is_alive()
        lookup.tick()
        assert lookup.result is None
    finally:
        release.set()
        if closer.ident is not None:
            closer.join(2)
        lookup.close()


@pytest.mark.parametrize('scoped', [False, True])
def test_explicit_unix_path_is_rejected_without_any_transport(native_prepare, monkeypatch, scoped):
    def forbidden(*args, **kwargs):
        pytest.fail('legacy request must not open a socket or silently use current host')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(runtime, 'call', forbidden)
    kwargs = {'expected_account': native_prepare.initial} if scoped else {}
    with pytest.raises(ValueError, match='host transport'):
        preparation_client.call('status', {}, socket_path='fixture-unused.sock', **kwargs)


def test_preparation_transport_has_no_unix_socket_implementation():
    assert 'socket' not in vars(preparation_client)
