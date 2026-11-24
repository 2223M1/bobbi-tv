"""Real owner/history/display seams with simulated native IO, not device proof."""
from frozen_history import source_bytes
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
from threading import Event, Thread
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_core.playback_start_facts import checked
from bobbi_core.catalog_display import media_facts_text
from bobbi_core.catalog_query import opaque
from test_ce2097_file_history import database, history
from test_playback_start_facts import scene, capture, card, stored_facts, ROOT


VIDEO = dict(codec='hevc', width=1920, height=1080)


def make_chain(scene, accounts=None, account=None):
    """Use real select/bind/claim/refresh, not an asserted available view."""
    calls, controls, publications = [], [], []
    native = SimpleNamespace(current=None, epoch=0)
    def state():
        calls.append('state')
        return dict(protocol=1, selection_epoch=native.epoch, playback=deepcopy(native.current),
                    gui_generation=0, gui_user_intent=0, fullscreen_instance='')
    def intent(command):
        assert command['expected_epoch'] == native.epoch
        native.epoch += 1
        return dict(reserved=True, selection_epoch=native.epoch)
    def subtitles():
        calls.append('subtitles')
        return dict(deepcopy(scene.raw), receipt=deepcopy(native.current), selection_epoch=native.epoch)
    def read_video():
        calls.append('video')
        return dict(currentvideostream=dict(VIDEO, index=0, name='SECRET-2160p-AV1', language='SECRET'))
    native.state, native.intent, native.subtitles, native.video = state, intent, subtitles, read_video
    native.control = lambda command: controls.append(deepcopy(command)) or {'queued': True}
    native.fullscreen = lambda command: controls.append(deepcopy(command)) or {'queued': True}
    native.publish_playback_presentation = lambda *args: publications.append(deepcopy(args))
    owner = PlaybackAuthority(native)
    account = account or scene.data['_account']
    if accounts is None:
        def run(scope, action):
            assert scope == account
            return action()
        accounts = SimpleNamespace(run_if_current=run, is_current=lambda scope: scope == account)
    owner.configure_accounts(accounts)
    initial = owner.dispatch(dict(operation='snapshot'))
    args = dict(boot_id=initial['boot_id'], epoch=initial['epoch'], request_id=scene.data['request_id'])
    args['epoch'] = owner.dispatch(dict(args, operation='select', selection_identity='release-a',
                                       account_scope=account))['epoch']
    identity = scene.owner['file_identity']
    assert owner.dispatch(dict(args, operation='bind_file', selection_identity='release-a',
                               file_identity=identity, url_sha256=scene.row['url_sha256'])) == {'bound': True}
    assert owner.dispatch(dict(args, operation='claim_start', route='resolved_url')) == {'status': 'CLAIMED'}
    native.current = dict(scene.row, open_epoch=native.epoch)
    owner.refresh(reconcile_windows=False)
    scene.owner = dict(args, file_identity=identity)
    scene.data['_account'] = deepcopy(account)
    scene.client.call = lambda message, **kwargs: owner.dispatch(message)
    calls.clear()
    return SimpleNamespace(owner=owner, native=native, calls=calls, controls=controls, publications=publications)


@pytest.fixture
def chain(scene):
    return make_chain(scene)


def read(chain, **kwargs):
    return chain.owner.dispatch(dict(operation='playback_presentation', include_start_facts=True, **kwargs))


def test_video_fence_through_real_start_history_restart_and_readonly_catalog(scene, chain):
    assert capture(scene)
    assert chain.calls == ['state', 'subtitles', 'video', 'state']
    assert scene.files.save(scene.data)
    path = Path(scene.db._database_path)
    before = path.read_bytes()
    reopened = history.FileHistory(scene.storage.PickleDatabase(profile_root=path.parent))
    assert reopened.get(scene.file['id'])['version'] == 1
    assert reopened.media_facts([scene.file])[scene.file['id']]['playback_start']['facts']['video'] == VIDEO
    text = media_facts_text(card(scene))
    assert '启动时视频分辨率：1920 × 1080' in text and '启动时视频编码：hevc' in text
    assert '不代表显示输出、HDR 或直接播放／转码模式' in text and 'HDR：未知' in text
    assert '启动时选中音轨：aac' in text and '启动时选中字幕：zho' in text
    assert b'SECRET' not in before and b'currentvideostream' not in before
    assert path.read_bytes() == before and not chain.controls and not chain.publications


def test_only_explicit_start_read_adds_video_io_and_does_not_mutate_owner(scene, chain):
    before = deepcopy((chain.owner.owner.snapshot(), chain.owner.history.items, chain.owner.last_native,
                       chain.owner.playback_commands, chain.owner.native_windows))
    view = chain.owner.dispatch(dict(operation='playback_presentation'))
    assert view['available'] and 'video' not in view['start_facts']
    assert chain.calls == ['state', 'subtitles']
    chain.calls.clear()
    assert read(chain)['start_facts']['video'] == VIDEO
    assert before == (chain.owner.owner.snapshot(), chain.owner.history.items, chain.owner.last_native,
                      chain.owner.playback_commands, chain.owner.native_windows)
    assert not chain.controls and not chain.publications


def test_optional_video_never_overflows_existing_presentation_wire_budget(scene, chain):
    for key in ('audio_streams', 'streams'):
        original = scene.raw[key][0]
        scene.raw[key] = [dict(original, index=i, stream_key='%064x' % (i + 1),
                               name='n' * 128, language='l' * 32) for i in range(32)]
    for size in range(257):
        chain.native.subtitle_status = lambda row: 's' * size
        base = chain.owner.dispatch(dict(operation='playback_presentation'))
        expanded = dict(base, start_facts=dict(base['start_facts'], video=VIDEO))
        if len(json.dumps(expanded, ensure_ascii=False).encode('utf-8')) > 12288:
            break
    else:
        pytest.fail('Fixture did not reach the actual projection budget')
    result = read(chain)
    assert len(json.dumps(result, ensure_ascii=False).encode('utf-8')) <= 12288
    assert 'video' not in result['start_facts'] and result['start_facts']['audio']['codec'] == 'aac'


@pytest.mark.parametrize('value', [1, 'true', None, [], {}])
def test_truthy_or_non_boolean_start_request_never_enables_io(chain, value):
    with pytest.raises(ValueError):
        chain.owner.dispatch(dict(operation='playback_presentation', include_start_facts=value))
    assert not chain.calls


@pytest.mark.parametrize('failure', [OSError, RuntimeError, ValueError, TypeError, AttributeError, TimeoutError])
@pytest.mark.parametrize('stage', ['video', 'after'])
def test_optional_native_error_preserves_prior_audio_subtitle_observation(scene, chain, failure, stage):
    original = chain.native.state
    def fail():
        raise failure('fixture')
    if stage == 'video':
        chain.native.video = fail
    else:
        chain.native.state = lambda: fail() if chain.calls else original()
    assert capture(scene)
    facts = scene.data['_file_start_observation']['facts']
    assert 'video' not in facts and facts['audio']['codec'] == 'aac' and facts['subtitle']['language'] == 'zho'
    assert not chain.controls and not chain.publications


def test_older_adapter_without_video_still_captures_audio_and_subtitles(scene, chain):
    del chain.native.video
    assert capture(scene)
    assert set(scene.data['_file_start_observation']['facts']) == {
        'audio_count', 'subtitle_count', 'audio', 'subtitle', 'subtitle_visible'}


def test_unfenced_video_in_scoped_catalog_is_not_implicitly_trusted(scene, chain):
    scene.raw['video'] = VIDEO
    scene.raw['currentvideostream'] = dict(VIDEO, index=0)
    del chain.native.video
    assert capture(scene) and 'video' not in scene.data['_file_start_observation']['facts']


@pytest.mark.parametrize('stage', ['before', 'inflight'])
def test_capture_profile_revocation_discards_even_a_successful_video_reply(scene, chain, stage):
    assert capture(scene)
    original = chain.native.video
    def revoked():
        scene.current[0] = 'B'
        return original()
    if stage == 'before':
        scene.current[0] = 'B'
    else:
        chain.native.video = revoked
    assert not capture(scene) and '_file_start_observation' not in scene.data
    scene.current[0] = 'A'
    assert not capture(scene) and '_file_start_observation' not in scene.data


@pytest.mark.parametrize('field,value', [
    ('request_id', 'f' * 32), ('native_instance', 'ffffffff-ffff-4fff-8fff-ffffffffffff'), ('file_identity', 'replacement'),
    ('url_sha256', 'f' * 64), ('open_epoch', 3), ('sequence', 3), ('phase', 'OPEN'),
    ('user_intent', 1), ('subtitle_intent', 1), ('subtitle_auto_intent', 1), ('audio_intent', 1),
    ('sequence', 2.0), ('user_intent', False), ('audio_intent', None), ('open_epoch', True),
])
def test_video_late_across_receipt_change_is_discarded_without_rebinding_audio(scene, chain, field, value):
    old_scope = deepcopy(chain.native.current)
    original = chain.native.video
    def late():
        result = original()
        chain.native.current[field] = value
        return result
    chain.native.video = late
    assert capture(scene)
    observed = scene.data['_file_start_observation']
    assert 'video' not in observed['facts'] and observed['facts']['audio']['codec'] == 'aac'
    assert observed['expected']['expected_sequence'] == old_scope['sequence']
    assert not chain.controls and not chain.publications


@pytest.mark.parametrize('change', ['epoch', 'epoch_bool', 'protocol', 'protocol_bool', 'no_playback', 'missing_intent'])
def test_after_fence_requires_typed_selection_and_complete_native_receipt(scene, chain, change):
    original = chain.native.state
    def state():
        value = original()
        if 'video' in chain.calls:
            if change == 'epoch': value['selection_epoch'] += 1
            if change == 'epoch_bool': value['selection_epoch'] = True
            if change == 'protocol': value['protocol'] = 2
            if change == 'protocol_bool': value['protocol'] = True
            if change == 'no_playback': value['playback'] = None
            if change == 'missing_intent': value['playback'].pop('audio_intent')
        return value
    chain.native.state = state
    assert capture(scene) and 'video' not in scene.data['_file_start_observation']['facts']


@pytest.mark.parametrize('properties', [None, [], {}, {'currentvideostream': None},
    {'currentvideostream': {}}, {'currentvideostream': {'index': -1}},
    {'currentvideostream': {'index': True}}, {'currentvideostream': {'index': 256}},
    {'currentvideostream': {'index': 0, 'codec': 'https://secret'}},
    {'currentvideostream': {'index': 0, 'codec': 'a' * 33}},
    {'currentvideostream': {'index': 0, 'codec': 'hevc\nSECRET'}},
    {'currentvideostream': {'index': 0, 'width': True}},
    {'currentvideostream': {'index': 0, 'height': 1080.0}},
    {'currentvideostream': {'index': 0, 'height': -1}},
    {'currentvideostream': {'index': 0, 'width': 65536}},
])
def test_empty_invalid_and_sensitive_video_properties_do_not_poison_audio(scene, chain, properties):
    chain.native.video = lambda: properties
    assert capture(scene)
    facts = scene.data['_file_start_observation']['facts']
    assert 'video' not in facts and facts['audio']['codec'] == 'aac'


@pytest.mark.parametrize('raw,expected', [
    ({'index': 0}, dict(codec=None, width=None, height=None)),
    ({'index': 0, 'codec': '', 'width': 0, 'height': 0}, dict(codec=None, width=None, height=None)),
    ({'index': 0, 'codec': 'av1', 'height': 1080}, dict(codec='av1', width=None, height=1080)),
    ({'index': 0, 'width': 1920, 'height': 1080}, dict(codec=None, width=1920, height=1080)),
])
def test_missing_metadata_never_inherits_previous_snapshot_or_guesses_filename(scene, chain, raw, expected):
    assert capture(scene) and scene.files.save(scene.data)
    scene.data['_file_history'] = scene.files.begin(scene.file)
    chain.native.video = lambda: {'currentvideostream': dict(raw, name='8K-DolbyVision-HEVC.mkv')}
    assert capture(scene) and scene.files.save(scene.data)
    assert stored_facts(scene)['observation']['facts']['video'] == expected
    text = media_facts_text(card(scene))
    if expected['width'] is None or expected['height'] is None:
        assert '分辨率：未知' in text
    if expected['codec'] is None:
        assert '视频编码：未知' in text
    assert '8K' not in text and 'HDR：未知' in text


@pytest.mark.parametrize('video', [None, {}, {'codec': 'hevc'}, dict(VIDEO, extra='SECRET'),
                                  dict(VIDEO, width=0), dict(VIDEO, height=True), dict(VIDEO, codec='')])
def test_new_optional_saved_shape_is_strict_without_changing_history_v1(scene, chain, video):
    assert capture(scene)
    scene.data['_file_start_observation']['facts']['video'] = video
    with pytest.raises(ValueError):
        checked(scene.data['_file_start_observation']['facts'])
    assert scene.files.save(scene.data)
    assert scene.files.get(scene.file['id'])['version'] == 1
    assert 'playback_start' not in card(scene)['media_facts']


@pytest.mark.parametrize('field,value', [('size', 99999), ('name', 'Replaced-8K-AV1.mkv'), ('parent', 'other')])
def test_replaced_same_file_id_never_displays_old_video_as_current(scene, chain, field, value):
    assert capture(scene) and scene.files.save(scene.data)
    replacement = dict(scene.file, **{field: value})
    facts = scene.files.media_facts([replacement])[replacement['id']]
    text = media_facts_text(dict(media_facts=facts, observation_key=opaque(replacement)))
    assert '分辨率：未知' in text and '视频编码：未知' in text and '待重新核验' in text
    assert '启动时视频分辨率：1920' not in text and '启动时视频编码：hevc' not in text


def test_late_old_generation_and_sequence_cannot_replace_new_file_video(scene, chain):
    assert capture(scene) and scene.files.save(scene.data)
    old = deepcopy(scene.data)
    scene.data['_file_history'] = scene.files.begin(scene.file)
    scene.data['_file_history_sequence'] = 2
    chain.native.video = lambda: {'currentvideostream': dict(index=0, codec='av1', width=3840, height=2160)}
    assert capture(scene) and scene.files.save(scene.data)
    accepted = stored_facts(scene)
    old['_file_history_sequence'] = 999
    assert scene.files.save(old)
    late = deepcopy(scene.data)
    late['_file_history_sequence'] = 1
    late['_file_start_observation']['facts']['video'] = VIDEO
    assert scene.files.save(late)
    assert stored_facts(scene) == accepted


def test_later_sound_change_with_missing_video_never_inherits_old_video(scene, chain):
    assert capture(scene) and scene.files.save(scene.data)
    scene.data['_file_history'] = scene.files.begin(scene.file)
    scene.raw['audio_streams'][0]['codec'] = 'flac'
    scene.raw['streams'][0]['language'] = 'eng'
    chain.native.video = lambda: {'currentvideostream': None}
    assert capture(scene) and scene.files.save(scene.data)
    value = card(scene)
    facts = value['media_facts']['playback_start']['facts']
    assert 'video' not in facts and facts['audio']['codec'] == 'flac' and facts['subtitle']['language'] == 'eng'
    text = media_facts_text(value)
    assert '分辨率：未知' in text and '视频编码：未知' in text


def test_old_audio_only_facts_and_frozen_ed645ee_reader_fallback(scene, chain, monkeypatch):
    # Current reader accepts the exact prior schema unchanged.
    old_view = chain.owner.dispatch(dict(operation='playback_presentation'))
    assert checked(old_view['start_facts']) == old_view['start_facts']
    assert capture(scene) and scene.files.save(scene.data)
    path = Path(scene.db._database_path)
    before = path.read_bytes()
    source = source_bytes('ed645eece1dc340e52f1377731d5f1ff9d0804c8', 'addons/script.module.bobbi.core/lib/bobbi_core/playback_start_facts.py')
    legacy = ModuleType('bobbi_core.playback_start_facts')
    legacy.__package__ = 'bobbi_core'
    exec(compile(source, '<frozen-ed645ee-start-facts>', 'exec'), legacy.__dict__)
    monkeypatch.setitem(sys.modules, 'bobbi_core.playback_start_facts', legacy)
    # The real unchanged history reader rejects only the unknown dependent
    # observation; the original v1 history and duration survive without writes.
    reopened = history.FileHistory(scene.storage.PickleDatabase(profile_root=path.parent))
    facts = reopened.media_facts([scene.file])[scene.file['id']]
    assert facts['duration_seconds'] == 100 and 'playback_start' not in facts
    assert reopened.get(scene.file['id'])['version'] == 1 and path.read_bytes() == before


def test_exact_production_kodi_adapter_requests_only_currentvideostream():
    source = ROOT / 'addons/plugin.video.bobbi/lib/services/playback_control.py'
    cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'KodiNative')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'video')
    env, calls = {}, []
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), env)
    actor = SimpleNamespace(rpc=lambda *args: calls.append(args) or {'currentvideostream': VIDEO})
    assert env['video'](actor) == {'currentvideostream': VIDEO}
    assert calls == [('Player.GetProperties', {'playerid': 1, 'properties': ['currentvideostream']})]


@pytest.mark.parametrize('change', ['unchanged', 'switch', 'aba', 'logout', 'renew'])
def test_slow_video_io_never_holds_account_lock_or_publishes_revoked_scope(scene, change):
    from bobbi_platform.account_manager import AccountError, AccountManager
    manager = AccountManager(scene.root / 'account.json')
    def credential(user='123', suffix='A1_fixture'):
        return dict(app='os_linux', cookies=dict(UID=user + '_' + suffix, CID='fixture', SEID='fixture'))
    account = manager.install(credential(), manager.snapshot())
    entered, release, changed = Event(), Event(), Event()
    results = {}
    def run():
        chain = make_chain(scene, accounts=manager, account=account)
        original = chain.native.video
        def blocked():
            entered.set()
            assert release.wait(5)
            return original()
        chain.native.video = blocked
        try:
            results['view'] = read(chain, account_scope=account)
        except AccountError:
            results['revoked'] = True
        finally:
            results['controls'] = chain.controls
            results['publications'] = chain.publications
    worker = Thread(target=run)
    worker.start()
    assert entered.wait(3)
    def update():
        if change == 'unchanged':
            results['current'] = manager.is_current(account)
        elif change == 'logout':
            manager.logout(manager.snapshot())
        else:
            manager.install(credential('456' if change in ('switch', 'aba') else '123', 'B1_fixture'), manager.snapshot())
            if change == 'aba':
                manager.install(credential(), manager.snapshot())
        changed.set()
    mutation = Thread(target=update)
    mutation.start()
    try:
        assert changed.wait(2), 'Video IO retained the account lock'
    finally:
        release.set()
        worker.join(3)
        mutation.join(3)
    assert not worker.is_alive() and not mutation.is_alive()
    assert not results['controls'] and not results['publications']
    if change in ('unchanged', 'renew'):
        assert manager.is_current(account) and results['view']['start_facts']['video'] == VIDEO
    else:
        assert results.get('revoked') is True and 'view' not in results
