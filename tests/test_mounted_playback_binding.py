"""Default mounted entries bind once; real loopback RPC and owner, fake Kodi.

Temporary local files and synthetic CD2 mount evidence are not device proof.
"""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import library_ui, runtime
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry, vfs_source
from bobbi_platform.scan_sources import LocalPort, MountedPort
from test_catalog_service import Pans
from test_library_plugin import plugin
from test_media_library_index import scope
from test_scan_source_ports import mounted_ui


@pytest.fixture(params=['mounted_path', 'local_path'])
def reference_kind(request):
    return request.param


@pytest.fixture
def cd2(tmp_path, reference_kind):
    """The existing native/stock fixture also accepts an ordinary local source."""
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'Movie.mkv').write_bytes(b'fixture video')
    source = vfs_source('Fixture mounted source', media.as_posix())
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(source)
    store.close()
    mounts = [dict(path=media.as_posix(), generation='a' * 64)] if reference_kind == 'mounted_path' else []
    service = CatalogService(tmp_path, Pans(scope(), lambda *a: pytest.fail('No native cloud login')))
    service.mounted.port = MountedPort(tmp_path, mounts=lambda: deepcopy(mounts))
    service.mounted.local_port = LocalPort(tmp_path, mounts=lambda: deepcopy(mounts))
    try:
        yield service, source, media, mounts
    finally:
        service.close()


@pytest.fixture
def bound_mount(cd2, mounted_ui, reference_kind, tmp_path, monkeypatch):
    service, source, _, _ = cd2
    prefix = 'catalog_mount_' if reference_kind == 'mounted_path' else 'catalog_local_'
    task = service.dispatch(prefix + 'scan', dict(source_id=source.id))['task_id']
    service.worker.join(5)
    assert not service.worker.is_alive()
    assert service.dispatch(prefix + 'jobs', dict(source_id=source.id, task=task))['items'][0]['state'] == 'completed'
    selected = service.dispatch(prefix + 'query', dict(source_id=source.id,
        query={'view': 'files'}))['items'][0]['entity_id']
    value = SimpleNamespace(ui=mounted_ui, prefix=prefix, bindings=[], captures=[], attempts=[],
        wire=[], dispatched=[], replacement_calls=[], after_dispatch=None, on_close=None,
        profile='A', registries=[], registry_closes=0)

    def dispatch(action, body):
        value.dispatched.append((action, deepcopy(body)))
        result = mounted_ui.dispatch(action, body)
        if value.after_dispatch:
            value.after_dispatch(action, body)
        return result

    first = runtime.Runtime(dispatch, tmp_path / 'runtime.json')
    replacement = runtime.Runtime(lambda action, body:
        value.replacement_calls.append((action, deepcopy(body))) or mounted_ui.dispatch(action, body),
        tmp_path / 'replacement/runtime.json')
    first.start()
    replacement.start()
    value.server, value.replacement = first, replacement
    value.registration = first.path.read_bytes()
    real_bind, real_call = runtime.bind_call, runtime.call
    real_profile_rpc = mounted_ui.catalog._profile_rpc

    def transport(action, body, timeout=3, *, path=None, expected_token=None):
        assert Path(path) == first.path and expected_token == first.server.token
        value.wire.append((action, deepcopy(body), timeout))
        return real_call(action, body, timeout=timeout, path=path, expected_token=expected_token)

    def bind(path):
        value.bindings.append(Path(path))
        bound = real_bind(path)
        def call(action, body, timeout=3):
            value.attempts.append((action, deepcopy(body), timeout))
            return bound(action, body, timeout=timeout)
        return call

    def capture(rpc=None):
        assert rpc is None, 'This suite exercises the actual default entry'
        result = real_profile_rpc(rpc)
        value.captures.append(result)
        return result

    monkeypatch.setattr(runtime, 'call', transport)
    monkeypatch.setattr(runtime, 'bind_call', bind)
    monkeypatch.setattr(runtime, 'profile', lambda **kw: pytest.fail('Dynamic Host discovery is forbidden'))
    monkeypatch.setattr(mounted_ui.playback, 'call',
        lambda *a, **kw: pytest.fail('Mounted entry must not fall back to dynamic RPC'), raising=False)
    monkeypatch.setattr(mounted_ui.catalog, '_profile_rpc', capture)
    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath',
        lambda path: str(tmp_path if value.profile == 'A' else tmp_path / 'profile-B'))
    original_progress = sys.modules['xbmcgui'].DialogProgress
    def progress():
        result = original_progress()
        close = result.close
        def finished():
            close()
            if value.on_close:
                value.on_close()
        result.close = finished
        return result
    monkeypatch.setattr(sys.modules['xbmcgui'], 'DialogProgress', progress)

    class UiRegistry(Registry):
        def source_snapshot(self, source_id):
            pytest.fail('CD2/local binding must not add the network revision contract')
        def close(self):
            value.registry_closes += 1
            super().close()
    def registry(translate):
        value.registries.append(translate('special://profile/addon_data/script.module.bobbi.platform'))
        return UiRegistry(service.root / 'libraries.sqlite3')
    monkeypatch.setattr(library_ui, 'registry', registry)
    params = dict(source=source.id, object_id=selected)
    if reference_kind != 'mounted_path':
        params['reference_kind'] = reference_kind
    value.play = lambda: mounted_ui.playback.mounted(params, handle=17)
    try:
        yield value
    finally:
        first.close()
        replacement.close()


def operations(rows):
    return [body['operation'] for action, body in rows if action == 'playback']


def assert_single_binding(case):
    assert case.bindings == [case.server.path]
    assert len(case.captures) == 1
    assert case.replacement_calls == []


def test_default_cd2_and_local_capture_once_and_keep_existing_two_second_owner_budget(bound_mount):
    case = bound_mount
    case.play()
    assert_single_binding(case)
    assert [row[1] for row in case.ui.plugin.resolved] == [True]
    item = case.ui.plugin.resolved[0][2]
    assert item.properties['StartOffset'] == '0'
    assert operations(case.dispatched).count('select') == 1
    assert not {'bind_file', 'claim_start', 'cancel'} & set(operations(case.dispatched))
    assert all(timeout == 2 for action, body, timeout in case.attempts if action == 'playback')
    assert any(action == case.prefix + 'prepare' and timeout == 28 for action, body, timeout in case.attempts)
    assert any(action == case.prefix + 'verify' and timeout == 8 for action, body, timeout in case.attempts)
    assert len(case.registries) == case.registry_closes == 1
    assert not any(action.startswith('pan_') for action, body in case.dispatched)


def test_lost_select_reply_cancels_same_binding_once_without_reselection(bound_mount):
    case = bound_mount
    def lose_reply(action, body):
        if action == 'playback' and body['operation'] == 'select':
            raise OSError('Accepted select, lost reply')
    case.after_dispatch = lose_reply
    case.play()
    assert_single_binding(case)
    assert [row[1] for row in case.ui.plugin.resolved] == [False]
    assert operations(case.dispatched) == ['snapshot', 'select', 'snapshot', 'cancel']
    assert [action for action, body in case.dispatched].count(case.prefix + 'cancel_play') == 1
    assert all(timeout == 2 for action, body, timeout in case.attempts
        if action == 'playback' or action == case.prefix + 'cancel_play')
    assert not any(action == case.prefix + 'prepare' for action, body in case.dispatched)
    assert case.ui.dispatch('playback', {'operation': 'snapshot'})['desired']['cancelled']


@pytest.mark.parametrize('aba', [False, True])
def test_host_replacement_is_rejected_and_finally_never_recaptures_even_after_aba(bound_mount, aba):
    case = bound_mount
    def replace_host(action, body):
        if action == case.prefix + 'prepare':
            case.server.path.write_bytes(case.replacement.path.read_bytes())
    case.after_dispatch = replace_host
    if aba:
        case.on_close = lambda: case.server.path.write_bytes(case.registration)
    case.play()
    assert_single_binding(case)
    assert [row[1] for row in case.ui.plugin.resolved] == [False]
    assert operations(case.dispatched) == ['snapshot', 'select']
    assert not any(action.endswith(('_claim', '_verify', '_cancel_play')) for action, body in case.dispatched)
    assert [(action, body.get('operation'), timeout) for action, body, timeout in case.attempts[-2:]] == [
        (case.prefix + 'cancel_play', None, 2), ('playback', 'snapshot', 2)]
    case.server.path.write_bytes(case.registration)
    with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
        case.captures[0][1]('playback', {'operation': 'snapshot'}, timeout=2)
    assert_single_binding(case)


def test_profile_a_b_a_cannot_revive_entry_or_finally_cleanup(bound_mount):
    case = bound_mount
    def change_profile(action, body):
        if action == case.prefix + 'prepare':
            case.profile = 'B'
    case.after_dispatch = change_profile
    case.on_close = lambda: setattr(case, 'profile', 'A')
    case.play()
    assert_single_binding(case)
    assert case.profile == 'A'
    assert [row[1] for row in case.ui.plugin.resolved] == [False]
    assert operations(case.dispatched) == ['snapshot', 'select']
    assert not any(action.endswith(('_claim', '_verify', '_cancel_play')) for action, body in case.dispatched)
    # Profile revocation blocks before transport, including both cleanup calls.
    assert case.attempts[-1][0] == case.prefix + 'prepare'
    binding, rpc = case.captures[0]
    assert binding.is_current() is False
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        rpc('playback', {'operation': 'snapshot'}, timeout=2)
    assert_single_binding(case)


def test_missing_default_registration_is_not_recaptured_when_host_returns(bound_mount):
    case = bound_mount
    case.server.path.unlink()
    case.on_close = lambda: case.server.path.write_bytes(case.registration)
    case.play()
    assert case.bindings == [case.server.path] and case.captures == []
    assert case.attempts == case.dispatched == case.replacement_calls == []
    assert [row[1] for row in case.ui.plugin.resolved] == [False]
    assert case.server.path.read_bytes() == case.registration
