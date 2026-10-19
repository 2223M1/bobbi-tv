from copy import deepcopy
from uuid import uuid4

import pytest

from test_playback_authority import playing, subtitle_catalog, select


def ready(native):
    from pathlib import Path
    from bobbi_core.runtime_paths import ProfilePath
    return dict(state='ready', native_instance=native.current['native_instance'],
                request_id=native.current['request_id'], subtitle_intent=0,
                file=dict(path=str(Path(ProfilePath('subtitle-browser')) / ('a' * 32 + '.srt')),
                          sha256='a' * 64, bytes=1000))


def setup():
    owner, native, args = playing()
    catalog = subtitle_catalog(native, [dict(index=0, language='eng', stream_key='b' * 64)])
    value = ready(native)
    native.external_subtitle = lambda _: deepcopy(value)
    native.subtitle_file = native.control
    message = dict(args, operation='auto_chinese_subtitle', native_instance=native.current['native_instance'])
    return owner, native, args, catalog, value, message


def test_external_file_once_and_only_confirmed_by_actual_native_receipt():
    owner, native, args, catalog, value, message = setup()
    assert owner.dispatch(message) == {'status': 'QUEUED'}
    command = native.commands[0]
    assert command['path'] == value['file']['path']
    assert command['selection_epoch'] == native.epoch
    assert owner.dispatch(message) == {'status': 'QUEUED'}
    assert len(native.commands) == 1
    catalog['receipt'].update(subtitle_file_applied=True, subtitle_file_sha256='a' * 64)
    assert owner.dispatch(message)['status'] == 'CONTROL_NOT_CONFIRMED'
    catalog['visible'] = True
    assert owner.dispatch(message)['status'] == 'CONFIRMED'
    assert len(native.commands) == 1


@pytest.mark.parametrize('change', ['native', 'request', 'intent', 'path', 'bytes', 'hash'])
def test_unowned_or_invalid_export_never_reaches_native(change):
    owner, native, args, catalog, value, message = setup()
    if change == 'native': value['native_instance'] = str(uuid4())
    elif change == 'request': value['request_id'] = 'f' * 32
    elif change == 'intent': value['subtitle_intent'] = 1
    elif change == 'path': value['file']['path'] = '/storage/videos/CloudDrive/a.srt'
    elif change == 'bytes': value['file']['bytes'] = True
    else: value['file']['sha256'] = 'bad'
    assert owner.dispatch(message)['status'] in ('STALE', 'SUBTITLE_EXPORT_INVALID')
    assert native.commands == []


@pytest.mark.parametrize('change', ['manual', 'new_instance', 'new_selection', 'cancel'])
def test_manual_or_selection_during_local_lookup_wins(change):
    owner, native, args, catalog, value, message = setup()
    def lookup(_):
        if change == 'manual': native.current['subtitle_intent'] = 1
        elif change == 'new_instance': native.current['native_instance'] = str(uuid4())
        elif change == 'new_selection': select(owner, 'release-b')
        else: owner.dispatch(dict(args, operation='cancel'))
        return deepcopy(value)
    native.external_subtitle = lookup
    result = owner.dispatch(message)
    assert result['status'] == 'STALE'
    assert not any('path' in command for command in native.commands)


def test_full_embedded_track_prevents_external_lookup():
    owner, native, args, catalog, value, message = setup()
    catalog['streams'].append(dict(index=1, language='zho', stream_key='c' * 64))
    def forbidden(_): raise AssertionError('External subtitle queried despite full embedded Chinese')
    native.external_subtitle = forbidden
    assert owner.dispatch(message)['status'] == 'QUEUED'
    assert native.commands[0]['index'] == 1


def test_manual_hide_never_opens_external_subtitle():
    owner, native, args, catalog, value, message = setup()
    native.current['subtitle_intent'] = catalog['receipt']['subtitle_intent'] = 1
    assert owner.dispatch(message)['status'] == 'MANUAL_PRESERVED'
    assert native.commands == []


def test_unavailable_provider_does_not_fallback_to_unscoped_kodi():
    owner, native, args, catalog, value, message = setup()
    def unavailable(_): raise TimeoutError('service unavailable')
    native.external_subtitle = unavailable
    assert owner.dispatch(message)['status'] == 'SUBTITLE_SERVICE_UNAVAILABLE'
    assert native.commands == []


@pytest.mark.parametrize('reason,status', [
    ('NO_MATCHED_CHINESE_TEXT', 'NO_QUALIFIED_CHINESE_SUBTITLE'),
    ('ASSRT_TOKEN_NOT_CONFIGURED', 'SUBTITLE_PROVIDER_AUTH_REQUIRED'),
    ('ASSRT_HTTP_401', 'SUBTITLE_PROVIDER_AUTH_REQUIRED'),
    ('ASSRT_HTTP_403', 'SUBTITLE_PROVIDER_AUTH_REQUIRED'),
    ('ASSRT_RATE_LIMIT', 'SUBTITLE_PROVIDER_RATE_LIMITED'),
    ('ASSRT_HTTP_429', 'SUBTITLE_PROVIDER_RATE_LIMITED'),
    ('SUBTITLE_DEADLINE', 'SUBTITLE_LOOKUP_TIMEOUT'),
    ('SUBTITLE_IO_DEADLINE', 'SUBTITLE_LOOKUP_TIMEOUT'),
    ('CANCELLED_OR_DEADLINE', 'SUBTITLE_LOOKUP_STOPPED'),
    ('ASSRT_HTTP_503', 'SUBTITLE_PROVIDER_UNAVAILABLE'),
    ('ASSRT_HTTP_418', 'SUBTITLE_PROVIDER_UNAVAILABLE'),
    ('ASSRT_HTTP_451', 'SUBTITLE_PROVIDER_UNAVAILABLE'),
    ('ASSRT_HTTP_493', 'SUBTITLE_PROVIDER_UNAVAILABLE'),
    ('ASSRT_HTTP_599', 'SUBTITLE_PROVIDER_UNAVAILABLE'),
    ('MATCHED_SUBTITLE_UNAVAILABLE', 'SUBTITLE_CANDIDATE_UNAVAILABLE'),
    ('SUBTITLE_TIMELINE_MISMATCH', 'SUBTITLE_TIMELINE_REJECTED'),
    ('SUBTITLE_CHINESE_PARTIAL', 'SUBTITLE_TEXT_REJECTED'),
    ('TORRENT_PLAYING_FILE_CHANGED', 'SUBTITLE_IDENTITY_REJECTED'),
    ('MEDIA_CONTEXT_MISSING', 'SUBTITLE_CONTEXT_UNAVAILABLE'),
    ('SUBTITLE_IPC_UNAVAILABLE', 'SUBTITLE_SERVICE_UNAVAILABLE'),
    ('MANUAL_PRESERVED', 'MANUAL_PRESERVED'),
])
def test_external_failure_keeps_bounded_observed_reason(reason, status):
    owner, native, args, catalog, value, message = setup()
    native.external_subtitle = lambda _: dict(state='unavailable', reason=reason)
    assert owner.dispatch(message) == dict(status=status, reason=reason)
    assert native.commands == []


@pytest.mark.parametrize('reason', [None, '', {}, [], 'UNKNOWN_CODE', 'ASSRT_API_9999',
                                    'ASSRT_HTTP_200', 'ASSRT_HTTP_600', 'ASSRT_HTTP_0493',
                                    'ASSRT_HTTP_493_private', 'ASSRT_HTTP_493\n',
                                    'https://example.invalid/private?token=secret', 'X' * 10000])
def test_unknown_subtitle_failure_is_not_empty_search_or_arbitrary_detail(reason):
    owner, native, args, catalog, value, message = setup()
    native.external_subtitle = lambda _: dict(state='unavailable', reason=reason)
    assert owner.dispatch(message) == dict(status='SUBTITLE_LOOKUP_UNAVAILABLE', reason='SUBTITLE_REASON_UNKNOWN')
    assert native.commands == []


def test_pending_subtitle_lookup_is_not_a_failure():
    owner, native, args, catalog, value, message = setup()
    native.external_subtitle = lambda _: dict(state='pending', reason='ASSRT_HTTP_401')
    assert owner.dispatch(message) == {'status': 'SUBTITLE_PREPARING'}
    assert native.commands == []


@pytest.mark.parametrize('current', [True, False, None])
def test_account_scoped_export_requires_final_current_account_check(current):
    owner, native, args, catalog, value, message = setup()
    scope = value['account_scope'] = dict(account_id='115:'+'a'*64, epoch=1, authenticated=True)
    checked = []
    if current is not None:
        native.subtitle_candidate_current = lambda candidate: checked.append(candidate['account_scope']) or current
    result = owner.dispatch(message)
    assert result == {'status': 'QUEUED' if current is True else 'STALE'}
    assert len(native.commands) == (1 if current is True else 0)
    assert checked == ([scope] if current is not None else [])


def test_account_change_after_lookup_before_native_apply_rejects_late_export():
    owner, native, args, catalog, value, message = setup()
    scope = value['account_scope'] = dict(account_id='115:'+'a'*64, epoch=1, authenticated=True)
    current = [scope]
    original = native.state
    looked_up = [False]
    def lookup(_):
        looked_up[0] = True
        return deepcopy(value)
    def state():
        if looked_up[0]:
            current[0] = dict(scope, epoch=2)
        return original()
    native.external_subtitle = lookup
    native.state = state
    native.subtitle_candidate_current = lambda candidate: candidate['account_scope'] == current[0]
    assert owner.dispatch(message) == {'status': 'STALE'}
    assert not native.commands


def test_prepared_ready_cached_before_logout_never_reaches_native(tmp_path):
    from types import SimpleNamespace
    from bobbi_core.preparation_host import Session, Lease
    from bobbi_core.subtitle_lookup_portable import SubtitleLookup
    from bobbi_platform.account_manager import AccountManager
    from lib.services.playback_control import KodiNative
    from lib.services.subtitle_fallback import SubtitleFallback
    owner, native, args, catalog, value, message = setup()
    accounts = AccountManager(tmp_path/'account.json')
    scope = accounts.install(dict(app='os_linux', cookies=dict(UID='123_fixture', CID='fixture', SEID='fixture')),
                             accounts.snapshot())
    session = object.__new__(Session)
    session.lease = Lease(accounts, scope)
    session.subtitles = SimpleNamespace(for_playback=lambda body: deepcopy(value))
    native.subtitle_lookup = SubtitleLookup(call=lambda method, body, **kw: session.dispatch(method, body))
    native.subtitle_fallback = SubtitleFallback()
    native.subtitle_fallback.accounts = accounts
    native.external_subtitle = lambda receipt: KodiNative.external_subtitle(native, receipt)
    native.subtitle_candidate_current = lambda candidate: KodiNative.subtitle_candidate_current(native, candidate)
    try:
        assert native.subtitle_lookup.request(native.current)['state'] == 'pending'
        native.subtitle_lookup.worker.join(1)
        native.subtitle_lookup.tick()
        assert native.subtitle_lookup.result['account_scope'] == scope
        accounts.logout(scope)
        assert owner.dispatch(message) == {'status': 'STALE'}
        assert not native.commands
    finally:
        native.subtitle_lookup.close()
        native.subtitle_fallback.close()
