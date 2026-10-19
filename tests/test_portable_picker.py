"""Synthetic portable UI/stock-Kodi tests; no device/playback certification."""
import builtins
import importlib.util
from pathlib import Path
import sys
from threading import Event
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_platform.playback import Handoff, selected_identity

ROOT = Path(__file__).resolve().parents[1]


def source(**values):
    defaults = dict(type='Direct', guid='provider:chosen', url='https://media.example/chosen.mkv',
                    infoHash='', debridType='', requiresCatalogEpisodeProof=False,
                    preparedResourceId='', directCloudKey='', isPack=False)
    defaults.update(values)
    return SimpleNamespace(**defaults)


@pytest.fixture
def picker(monkeypatch):
    state = SimpleNamespace(aborted=False, calls=[], resolutions=[], dialogs=[], opened=[],
                            handles=[], identities=[], sources=[], native_imports=[], window_props={})
    xbmc = ModuleType('xbmc')
    xbmc.Monitor = lambda: SimpleNamespace(abortRequested=lambda: state.aborted)
    gui = ModuleType('xbmcgui')
    state.file_choice, state.file_prompts, state.progress_cancelled = 0, [], False
    gui.Dialog = lambda: SimpleNamespace(ok=lambda *args: state.dialogs.append(args),
        select=lambda title, names: (state.file_prompts.append(names) or state.file_choice))
    gui.DialogProgress = lambda: SimpleNamespace(create=lambda *args: None,
        close=lambda: None, iscanceled=lambda: state.progress_cancelled)
    global_window = SimpleNamespace(getProperty=lambda key: state.window_props.get(key, ''),
        setProperty=lambda key, value: state.window_props.update({key: value}),
        clearProperty=lambda key: state.window_props.pop(key, None))
    gui.Window = lambda _id: global_window
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc)
    monkeypatch.setitem(sys.modules, 'xbmcgui', gui)
    utils = ModuleType('lib.utils.kodi.utils')
    utils.ADDON_HANDLE = 17
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', utils)
    spec = importlib.util.spec_from_file_location('_bobbi_portable_picker_test',
        ROOT / 'addons/plugin.video.bobbi/lib/portable.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def handoff(identity, handle, **kwargs):
        state.handles.append(handle)
        state.identities.append(identity)
        def resolve(actual_handle, succeeded, item):
            state.opened.append(('resolve', actual_handle, succeeded, item))
        def play(url, item):
            state.opened.append(('play', url, item))
        return Handoff(identity, handle, resolve, play, lambda url, data: (url, dict(data)), **kwargs)
    monkeypatch.setattr(module, 'standard_handoff', handoff)
    state.module, state.utils = module, utils

    def window(choices, resolver=None, progressive=False):
        pending = list(choices)
        result = SimpleNamespace(_selection_locked=False, _pending_selection=None,
            _auto_select_pending=True, item_information={}, last_error='', position=4,
            resolved=False, props={}, closed=0)
        result.setProperty = lambda key, value: result.props.update({key: value})
        def close():
            result.closed += 1
        result.close = close
        def ensure(chosen):
            state.sources.append(chosen)
            if resolver:
                return resolver(chosen)
            return {'url': chosen.url, 'is_torrent': False, 'is_pack': chosen.isPack}
        result._ensure_playback_info = ensure
        def modal():
            state.calls.append('modal')
            choice = pending.pop(0) if pending else None
            if choice is not None:
                module.queue_selected(result, choice)
        result.base_modal = modal
        result._run_progressive_window = modal
        if progressive:
            result.source_session = SimpleNamespace(reopen=lambda: state.calls.append('reopen'),
                cancel=lambda: state.calls.append('session_cancel'))
            result.source_pump = SimpleNamespace(cancel=lambda: state.calls.append('pump_cancel'))
        else:
            result.source_session = None
            result.source_pump = None
        return result
    state.window = window
    return state


@pytest.mark.parametrize('handle', [17, -1])
def test_one_stock_handoff_preserves_exact_chosen_object_identity(picker, handle, monkeypatch):
    chosen = source()
    picker.utils.ADDON_HANDLE = handle
    window = picker.window([chosen])
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.startswith(('lib.cinema.playback', 'bobbi_core.playback', 'am6b_core.playback')):
            picker.native_imports.append(name)
            raise AssertionError('Portable picker imported native ownership')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    assert picker.module.manual_modal(window, window.base_modal) is True
    assert picker.sources == [chosen] and picker.sources[0] is chosen
    assert picker.identities == [selected_identity(chosen.guid)]
    assert len(picker.opened) == 1
    assert picker.opened[0][0] == ('resolve' if handle >= 0 else 'play')
    assert not picker.native_imports
    assert window.item_information['selection_policy'] == 'portable_manual'
    assert not window._auto_select_pending


def test_ui_direct_flag_does_not_reuse_positive_plugin_handle(picker):
    window = picker.window([source()])
    window.item_information['direct_playback_handoff'] = True
    assert picker.module.manual_modal(window, window.base_modal) is True
    assert picker.handles == [-1]
    assert picker.opened[0][0] == 'play'


def test_failure_before_submission_reopens_without_switching_source(picker):
    chosen = source()
    def failed(_):
        raise OSError('provider unavailable')
    window = picker.window([chosen, None], failed, progressive=True)
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.sources == [chosen]
    assert picker.opened == []
    assert picker.calls == ['modal', 'reopen', 'modal', 'pump_cancel', 'session_cancel']
    assert window._restore_position == 4
    assert len(picker.dialogs) == 1


def test_explicit_second_choice_after_resolution_failure_only(picker):
    bad, good = source(guid='bad'), source(guid='good', url='https://media.example/good.mkv')
    def resolve(chosen):
        if chosen is bad:
            raise ValueError('not ready')
        return {'url': chosen.url}
    window = picker.window([bad, good], resolve)
    assert picker.module.manual_modal(window, window.base_modal) is True
    assert picker.sources == [bad, good]
    assert len(picker.opened) == 1
    assert picker.identities == [selected_identity(good.guid)]


@pytest.mark.parametrize('values', [{'type': 'Torrent'}, {'requiresCatalogEpisodeProof': True},
    {'preparedResourceId': 'private-cloud-id'}, {'directCloudKey': 'cloud-binding'},
    {'debridType': 'RealDebrid'}])
def test_unimplemented_backend_rejected_before_legacy_resolver(picker, values):
    chosen = source(**values)
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.sources == picker.opened == []
    assert len(picker.dialogs) == 1


def test_actual_stremio_enum_is_supported_as_direct_candidate(picker):
    # Authoritative IndexerType.STREMIO_DEBRID is 'Stremio', NOT 'Stremio Debrid'.
    chosen = source(type='Stremio')
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is True
    assert picker.sources == [chosen]
    assert len(picker.opened) == 1


def test_paired_bt_uses_exact_returned_file_and_no_legacy_resolver(picker, monkeypatch):
    from bobbi_platform.torrserver import VideoFile
    digest = 'a' * 40
    chosen = source(type='Torrent', infoHash=digest, url='magnet:?xt=urn:btih:' + digest, isPack=True)
    picker.file_choice = 1
    calls = []
    def select(expected, **kwargs):
        calls.append((expected, kwargs['magnet']))
        assert not kwargs['cancelled']()
        file = kwargs['choose_file']((VideoFile(1, 'S01E01.mkv', 100), VideoFile(2, 'S01E02.mkv', 200)))
        assert file.id == 2
        return {'url': 'http://127.0.0.1:8090/stream?link=' + expected + '&index=2&play',
                'info_hash': expected, 'file_id': file.id, 'file_path': file.path}
    monkeypatch.setattr(picker.module, 'local_client', lambda: SimpleNamespace(select_source=select))
    window = picker.window([chosen])
    assert picker.module.manual_modal(window, window.base_modal) is True
    assert picker.sources == []
    assert calls == [(digest, chosen.url)]
    assert picker.identities == [selected_identity('bt:' + digest + ':2')]
    assert len(picker.opened) == 1
    assert picker.file_prompts == [['S01E01.mkv', 'S01E02.mkv']]


def test_bt_file_cancel_returns_to_sources_without_playback(picker, monkeypatch):
    from bobbi_platform.torrserver import VideoFile, Cancelled
    chosen = source(type='Torrent', infoHash='a' * 40)
    picker.file_choice = -1
    def select(expected, **kwargs):
        assert kwargs['choose_file']((VideoFile(1, 'single.mkv', 100),)) is None
        raise Cancelled('USER_CANCELLED_FILE_CHOICE')
    monkeypatch.setattr(picker.module, 'local_client', lambda: SimpleNamespace(select_source=select))
    window = picker.window([chosen, None], progressive=True)
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.sources == picker.opened == picker.dialogs == []
    assert picker.calls == ['modal', 'reopen', 'modal', 'pump_cancel', 'session_cancel']


def test_restricted_catalogue_episode_never_bypasses_proof_via_bt(picker, monkeypatch):
    chosen = source(type='Torrent', infoHash='a' * 40, requiresCatalogEpisodeProof=True)
    def forbidden():
        pytest.fail('Restricted unproven source reached BT backend')
    monkeypatch.setattr(picker.module, 'local_client', forbidden)
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.sources == picker.opened == []


def test_bt_bad_supplied_magnet_cannot_be_discarded_for_hash(picker, monkeypatch):
    chosen = source(type='Torrent', infoHash='a' * 40, url='magnet:?xt=urn:btih:' + 'b' * 40)
    def forbidden():
        pytest.fail('Mismatched magnet reached backend')
    monkeypatch.setattr(picker.module, 'local_client', forbidden)
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.opened == []


def test_unresolved_pack_is_rejected_before_any_backend_work(picker):
    chosen = source(isPack=True)
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.sources == []
    assert picker.opened == []


def test_malformed_empty_identity_reports_failure_and_reopens(picker):
    chosen = source(guid='', url='', infoHash='')
    window = picker.window([chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert len(picker.dialogs) == 1
    assert picker.calls == ['modal', 'modal']
    assert picker.opened == []


def test_abort_during_resolution_must_not_open_stale_work(picker):
    chosen = source()
    def resolve(_):
        picker.aborted = True
        return {'url': chosen.url}
    window = picker.window([chosen], resolve)
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.opened == []


def test_replaced_local_request_must_not_open_stale_work(picker):
    chosen = source()
    def resolve(_):
        window.item_information['request_id'] = 'f' * 32
        return {'url': chosen.url}
    window = picker.window([chosen], resolve)
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.opened == []


def test_newer_picker_global_token_supersedes_slow_old_resolution(picker):
    chosen = source()
    def resolve(_):
        picker.window_props[picker.module.SELECTION] = 'b' * 32
        return {'url': chosen.url}
    window = picker.window([chosen], resolve)
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.opened == []


def test_superseded_during_item_creation_does_not_submit(picker, monkeypatch):
    chosen = source()
    def factory(identity, handle, **kwargs):
        def make_item(url, data):
            picker.window_props[picker.module.SELECTION] = 'c' * 32
            return url
        return Handoff(identity, handle, lambda *args: picker.opened.append(args),
                       lambda *args: picker.opened.append(args), make_item, **kwargs)
    monkeypatch.setattr(picker.module, 'standard_handoff', factory)
    window = picker.window([chosen])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert picker.opened == []


def test_uncertain_submission_is_not_reopened_as_unused_resolver_handle(picker, monkeypatch):
    chosen = source()
    def uncertain(identity, handle, **kwargs):
        def resolve(*args):
            picker.opened.append(args)
            raise OSError('reply lost after possible acceptance')
        return Handoff(identity, handle, resolve, lambda *_: None, lambda url, data: url, **kwargs)
    monkeypatch.setattr(picker.module, 'standard_handoff', uncertain)
    window = picker.window([chosen, chosen, None])
    assert picker.module.manual_modal(window, window.base_modal) is False
    assert len(picker.opened) == 1
    assert picker.calls == ['modal']


def test_advanced_action_does_not_queue_or_resolve(picker):
    window = picker.window([])
    picker.module.queue_selected(window, source(), pack_select=True)
    assert window._pending_selection is None
    assert not window._selection_locked
    assert window.closed == 0
    assert window.props['playback_error']


def load_player():
    spec = importlib.util.spec_from_file_location('_bobbi_portable_player_test',
        ROOT / 'overlays/plugin.video.bobbi/lib/player.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_player_compatibility_entry_uses_direct_flag_without_startup_claim(picker, monkeypatch):
    module = load_player()
    monkeypatch.setattr(module, 'standard_handoff', picker.module.standard_handoff)
    callbacks = []
    player = module.JacktookPLayer(on_started=lambda: callbacks.append('started'),
        on_handoff=lambda: callbacks.append('handoff'))
    player.run({'selection_policy': 'portable_manual', 'direct_playback_handoff': True,
                'url': 'https://media.example/file.mkv'})
    assert picker.opened[0][0] == 'play'
    assert picker.handles == [-1]
    assert callbacks == []
    assert not player._handoff_confirmed


def test_player_cancel_during_item_creation_does_not_submit(picker, monkeypatch):
    module = load_player()
    cancel = Event()
    def factory(identity, handle, **kwargs):
        def make_item(url, data):
            cancel.set()
            return url
        return Handoff(identity, handle, lambda *args: picker.opened.append(args),
                       lambda *args: picker.opened.append(args), make_item, **kwargs)
    monkeypatch.setattr(module, 'standard_handoff', factory)
    player = module.JacktookPLayer(cancel_event=cancel)
    player.run({'selection_policy': 'portable_manual', 'url': 'https://media.example/file.mkv'})
    assert picker.opened == []
    assert not player._resolution_answered
