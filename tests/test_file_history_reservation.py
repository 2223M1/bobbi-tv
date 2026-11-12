"""The real ticket claim must reserve a writer without relabelling old progress."""
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
import sys

import pytest

from test_ce2097_file_history import database, service, history, playback, FILE, ACCOUNT
from bobbi_core.file_ref import from_selected, same_file
from bobbi_platform.host import Host
from bobbi_platform.pan_history import prepare_history_play
from bobbi_platform.pan_accounts import PanError


def test_claiming_changed_file_preserves_old_resume_evidence_until_new_report(database, service, monkeypatch):
    storage, _ = database
    owner, expected, state = service
    files = history.FileHistory(storage.PickleDatabase())
    original = from_selected(expected, FILE, '0')
    old = files.begin(original)
    assert files.save(playback(old, position=42))
    before = files.get(original['id'])

    selected = dict(FILE, size=201, name='replacement.mkv')
    state.items = [selected]
    owner.list_files(expected, '0', 1, refresh=True)
    ticket = owner.prepare_play(expected, selected)['ticket']
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(FileHistory=lambda: files))
    host = SimpleNamespace(stopping=Event(), accounts=owner.accounts, _pans=lambda: owner)
    claimed = Host.dispatch(host, 'pan_claim_play', {'ticket': ticket})
    assert claimed['file_ref']['size'] == 201
    reserved = history.FileHistory(storage.PickleDatabase()).get(original['id'])
    # The next resume must still reject replacement content, even after a claim.
    with pytest.raises(PanError, match='PAN_FILE_CHANGED'):
        prepare_history_play(owner, reserved, 'd' * 32)
    # Failure/cancellation before AV must not attach old 42 seconds to this replacement.
    assert reserved['file_ref'] == original
    assert all(reserved[key] == before[key] for key in ('position', 'duration', 'completion_reason', 'updated_at'))
    assert reserved['generation'] == old['generation'] + 1
    assert not same_file(reserved['file_ref'], claimed['file_ref'])

    # The reservation still fences out late reports from the superseded writer.
    assert files.save(playback(old, sequence=99, position=98))
    assert files.get(original['id'])['position'] == 42
    context = dict(claimed['history'], file_ref=claimed['file_ref'])
    assert files.save(playback(context, position=2))
    restarted = history.FileHistory(storage.PickleDatabase()).get(original['id'])
    assert restarted['file_ref'] == claimed['file_ref'] and restarted['position'] == 2


@pytest.mark.parametrize('change', ['size', 'fingerprint', 'rename'])
def test_reservation_keeps_last_observation_and_returns_current_writer_ref(database, change):
    storage, _ = database
    expected = dict(ACCOUNT, provider='aliyun', account_id='aliyun:' + 'a' * 64)
    selected = dict(FILE, file_id='drive:f1', content_hash='original-hash')
    original = from_selected(expected, selected, 'drive:root')
    files = history.FileHistory(storage.PickleDatabase())
    old = files.begin(original)
    assert files.save(playback(old, position=42))
    replacement = deepcopy(selected)
    replacement.update({'size': 201} if change == 'size' else
                       {'content_hash': 'replacement-hash'} if change == 'fingerprint' else
                       {'name': 'renamed.mkv'})
    current = from_selected(expected, replacement, 'drive:root')
    new = files.begin(current)
    assert new['file_ref'] == current
    assert files.get(original['id'])['file_ref'] == original
    assert files.get(original['id'])['position'] == 42
    assert files.save(playback(new, position=3))
    assert files.get(original['id'])['file_ref'] == current
    assert files.get(original['id'])['position'] == 3
