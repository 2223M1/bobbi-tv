"""Live audio counters must not starve subtitles or weaken event admission."""
import pytest

from bobbi_core.native_receipt import ReceiptHistory, receipt, subtitle_snapshot_follows
from test_playback_authority import row


def snapshot():
    return row('a' * 32, 'file-a', audio_intent=2, open_epoch=4)


def test_live_audio_update_does_not_become_a_new_immutable_event():
    previous = snapshot()
    current = dict(previous, audio_intent=3)
    assert subtitle_snapshot_follows(current, previous)
    history = ReceiptHistory()
    assert history.accept(previous)
    assert history.accept(current) is None


@pytest.mark.parametrize('value', [True, False, -1, 1.0, '3', None, [], {}])
def test_optional_audio_counter_has_exact_type(value):
    invalid = dict(snapshot(), audio_intent=value)
    assert receipt(invalid) is None
    assert not subtitle_snapshot_follows(invalid, None)


@pytest.mark.parametrize('sequence', [1, 2])
def test_audio_counter_and_abi_do_not_regress(sequence):
    previous = snapshot()
    assert not subtitle_snapshot_follows(dict(previous, audio_intent=1, sequence=sequence), previous)
    old_f9 = dict(previous)
    old_f9.pop('audio_intent')
    assert not subtitle_snapshot_follows(dict(old_f9, sequence=sequence), previous)
    assert not subtitle_snapshot_follows(dict(previous, sequence=sequence), old_f9)
    assert subtitle_snapshot_follows(dict(old_f9, subtitle_intent=1, sequence=sequence), old_f9)


def test_audio_live_counter_does_not_allow_unrelated_field_changes():
    previous = snapshot()
    assert not subtitle_snapshot_follows(dict(previous, audio_intent=3, paused=True), previous)


def test_real_native_poll_keeps_subtitle_observer_live_after_manual_audio():
    from types import SimpleNamespace
    from lib.services.playback_control import KodiNative

    previous = snapshot()
    current = dict(previous, audio_intent=3)
    observed = []
    native = object.__new__(KodiNative)
    native.subtitle_lookup = SimpleNamespace(tick=lambda: None)
    native.subtitle_fallback = SimpleNamespace(key='pending', observe=observed.append)
    native.subtitle_receipt = previous
    native.subtitle_poll = 0
    native.state = lambda: dict(protocol=1, selection_epoch=4, playback=current)
    native.poll_io()
    assert observed == [current]
    assert native.subtitle_receipt == current
