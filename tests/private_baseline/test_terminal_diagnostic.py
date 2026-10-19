"""Bounded terminal evidence only: never authorizes or infers a continuation."""
from uuid import uuid4

import pytest

from test_playback_authority import playing, select
from lib.services.playback_control import KodiNative


@pytest.mark.parametrize('reason', ['NATURAL_EOF', 'STOP', 'ERROR', 'SUPERSEDED'])
def test_actual_terminal_logged_before_cancellation_and_deduplicated(reason):
    authority, native, args = playing()
    seen = []
    def diagnostic(request_id, instance, received_reason):
        assert authority.owner.desired['cancelled'] is False
        seen.append((request_id, instance, received_reason))
    native.terminal_diagnostic = diagnostic
    terminal = dict(native.current, phase='TERMINAL', sequence=2, reason=reason)
    assert authority.event('xbmc', 'Player.OnBobiState', terminal) is True
    assert seen == [(args['request_id'], terminal['native_instance'], reason)]
    assert authority.owner.terminal['reason'] == reason
    assert authority.owner.desired['cancelled'] is (reason != 'NATURAL_EOF')
    for seq in (2, 3, 999):
        assert authority.event('xbmc', 'Player.OnBobiState', dict(terminal, sequence=seq)) is False
    assert len(seen) == 1 and native.commands == [] and native.gui_commands == []


@pytest.mark.parametrize('mutation', ['sender', 'method', 'invalid_reason', 'invalid_instance', 'request_changed', 'nonterminal'])
def test_rejected_or_nonterminal_receipts_emit_no_terminal_evidence(mutation):
    authority, native, args = playing()
    seen = []
    native.terminal_diagnostic = lambda *values: seen.append(values)
    terminal = dict(native.current, phase='TERMINAL', sequence=2, reason='NATURAL_EOF')
    sender, method = 'xbmc', 'Player.OnBobiState'
    if mutation == 'sender': sender = 'other.addon'
    elif mutation == 'method': method = 'Player.OnStop'
    elif mutation == 'invalid_reason': terminal['reason'] = 'NEAR_END_OR_IDLE'
    elif mutation == 'invalid_instance': terminal['native_instance'] = 'not-a-native-instance'
    elif mutation == 'request_changed': terminal['request_id'] = 'f' * 32
    else: terminal.update(phase='AV_STARTED', reason='')
    authority.event(sender, method, terminal)
    assert seen == [] and authority.owner.terminal is None


def test_idle_or_generic_stopped_callback_never_logs_inferred_natural_eof():
    authority, native, args = playing()
    seen = []
    native.terminal_diagnostic = lambda *values: seen.append(values)
    native.current = None
    authority.refresh()
    authority.event('xbmc', 'Player.OnStop', dict(end=True))
    assert seen == []


def test_live_poll_and_notification_share_the_existing_terminal_deduplication():
    authority, native, args = playing()
    seen = []
    native.terminal_diagnostic = lambda *values: seen.append(values)
    native.current.update(phase='TERMINAL', sequence=2, reason='NATURAL_EOF')
    authority.refresh()
    authority.refresh()
    assert authority.event('xbmc', 'Player.OnBobiState', dict(native.current)) is False
    assert seen == [(args['request_id'], native.current['native_instance'], 'NATURAL_EOF')]


def test_late_old_terminal_is_diagnostic_only_and_cannot_cancel_new_selection():
    authority, native, args = playing()
    seen = []
    native.terminal_diagnostic = lambda *values: seen.append(values)
    terminal = dict(native.current, phase='TERMINAL', sequence=2, reason='ERROR')
    selected = select(authority, 'release-b')
    authority.event('xbmc', 'Player.OnBobiState', terminal)
    assert seen == [(args['request_id'], terminal['native_instance'], 'ERROR')]
    assert authority.owner.desired['request_id'] == selected['request_id']
    assert authority.owner.desired['cancelled'] is False
    assert native.commands == []


def test_diagnostic_failure_does_not_skip_terminal_cancellation():
    authority, native, args = playing()
    def fail(*values):
        raise OSError('diagnostic backend unavailable')
    native.terminal_diagnostic = fail
    assert authority.event('xbmc', 'Player.OnBobiState', dict(native.current,
        phase='TERMINAL', sequence=2, reason='ERROR')) is True
    assert authority.owner.terminal['reason'] == 'ERROR'
    assert authority.owner.desired['cancelled'] is True
    assert native.commands == []


def test_terminal_evidence_never_forwards_raw_receipt_locators_or_extra_fields(monkeypatch):
    import xbmc
    authority, native, args = playing()
    messages = []
    monkeypatch.setattr(xbmc, 'log', lambda message, level: messages.append((message, level)))
    native.terminal_diagnostic = KodiNative.terminal_diagnostic
    terminal = dict(native.current, phase='TERMINAL', sequence=2, reason='ERROR',
                    arbitrary_secret='secret-fixture', locator='https://example.invalid/private?token=secret-fixture')
    authority.event('xbmc', 'Player.OnBobiState', terminal)
    expected = '[BOBBI-TERMINAL] request={} instance={} reason=ERROR'.format(
        args['request_id'], native.current['native_instance'])
    assert messages == [(expected, xbmc.LOGINFO)]
    assert len(expected) < 160 and 'secret' not in expected


@pytest.mark.parametrize('request_id,instance,reason', [
    ('x' * 33, str(uuid4()), 'ERROR'),
    ('a' * 32 + '\n', str(uuid4()), 'STOP'),
    ('https://example.invalid', str(uuid4()), 'STOP'),
    ('a' * 32, 'bad-instance', 'ERROR'),
    ('a' * 32, str(uuid4()), 'NATURAL_EOF\nsecret'),
    ('a' * 32, str(uuid4()), {'reason': 'ERROR'}),
    (None, str(uuid4()), 'ERROR'),
])
def test_diagnostic_sink_rejects_non_allowlisted_fields(monkeypatch, request_id, instance, reason):
    import xbmc
    monkeypatch.setattr(xbmc, 'log', lambda *a: pytest.fail('Unbounded evidence must not be logged'))
    assert KodiNative.terminal_diagnostic(request_id, instance, reason) is False


def test_unbound_native_receipt_uses_empty_request_without_inventing_identity(monkeypatch):
    import xbmc
    messages = []
    monkeypatch.setattr(xbmc, 'log', lambda message, level: messages.append(message))
    instance = str(uuid4())
    assert KodiNative.terminal_diagnostic('', instance, 'STOP') is True
    assert messages == ['[BOBBI-TERMINAL] request= instance={} reason=STOP'.format(instance)]
