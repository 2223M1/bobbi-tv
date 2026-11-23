"""Prepared subtitle reuse after migration is exact-account/epoch and optional."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from threading import Event
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import subtitle_candidates as subtitles
from test_ce_state_migration import fixture as migration_fixture, migrate, SCOPE

CONTEXT = dict(title='Scope Example', mode='movie', year=2001, tmdb=1000001,
               duration=300, release='Scope.Example.2001.BluRay.NEW')


class Accounts:
    def __init__(self):
        self.scope = dict(SCOPE)
    def snapshot(self):
        return dict(self.scope)
    def is_current(self, expected):
        return expected == self.scope


def subtitle_text():
    return '\n'.join('{}\n00:{:02d}:{:02d},000 --> 00:{:02d}:{:02d},000\n中文完整对白第{}句\nEnglish dialogue {}\n'.format(
        i + 1, i * 10 // 60, i * 10 % 60, (i * 10 + 4) // 60, (i * 10 + 4) % 60, i + 1, i + 1)
        for i in range(30)).encode('utf-8')


def setup(tmp_path, monkeypatch):
    source, target = migration_fixture(tmp_path)
    raw = subtitle_text()
    digest = hashlib.sha256(raw).hexdigest()
    record = dict(forced=False, full_dialogue=True, language='zho', extension='.srt', subtitle_sha256=digest,
                  video=dict(media_id='tmdb:movie:1000001', selected=dict(torrent_path='Scope.Example.2001.BluRay.OLD.mkv')))
    (source / 'subtitles/objects' / (digest + '.srt')).write_bytes(raw)
    with sqlite3.connect(source / 'resources.sqlite') as db:
        db.execute('INSERT INTO subtitle_objects VALUES(?,?,?)', (digest, len(raw), '.srt'))
        db.execute('INSERT INTO subtitle_revisions VALUES(?,?,?,?,?,?)', (1, 'fixture', 'old-release', digest, json.dumps(record), 0))
        db.execute('INSERT INTO subtitle_current VALUES(?,?,?)', ('fixture', 'old-release', 1))
    migrate(source, target)
    accounts = Accounts()
    provider = subtitles.AssrtCandidates(None, tmp_path / 'public-cache', accounts=accounts,
                                        preparation_root=target.parent, clock=lambda: 0)
    native = tmp_path / 'native-cache'
    monkeypatch.setattr(provider, 'remote_candidates', Mock(side_effect=subtitles.LookupStopped('ASSRT_HTTP_493')))
    return provider, accounts, target, native, raw


def test_migrated_other_release_subtitle_reused_without_scanning_or_cloud(tmp_path, monkeypatch):
    provider, accounts, target, native, raw = setup(tmp_path, monkeypatch)
    assert not (target.parent / 'resources.sqlite').exists()
    monkeypatch.setattr(Path, 'glob', lambda *a: pytest.fail('Do not scan account/epoch directories'))
    result = provider.candidates(CONTEXT, 30, lambda: False, root=native)
    assert result['origin'].startswith('local:') and result['account_scope'] == SCOPE
    assert Path(result['file']['path']).read_bytes() == raw and result['bilingual'] is True
    assert result['source']['videoname'].endswith('OLD.mkv')
    assert provider.remote_candidates.call_count == 1  # Failed optional improvement retains valid text.


@pytest.mark.parametrize('change', ['account', 'epoch', 'logout'])
def test_cached_local_candidate_is_rejected_after_account_or_epoch_change(tmp_path, monkeypatch, change):
    provider, accounts, target, native, raw = setup(tmp_path, monkeypatch)
    old = provider.candidates(CONTEXT, 30, lambda: False, root=native)
    if change == 'account':
        accounts.scope = dict(SCOPE, account_id='115:' + 'b' * 64, epoch=2)
    elif change == 'epoch':
        accounts.scope = dict(SCOPE, epoch=2)
    else:
        accounts.scope = dict(account_id='', authenticated=False, epoch=2)
    current = subtitles.AssrtCandidates(None, provider.directory, accounts=accounts,
        preparation_root=target.parent, clock=lambda: 0)
    assert current.local_candidates(CONTEXT, 30, lambda: False, native) == []
    assert current.candidate_current(old) is False
    current.remote_candidates = Mock(return_value=dict(origin='assrt:fixture', state='candidate'))
    result = current.candidates(CONTEXT, 30, lambda: False, root=native)
    assert result['origin'] == 'assrt:fixture'
    assert current.remote_candidates.call_args.args[-1] == []


def test_account_change_during_byte_read_discards_local_candidate(tmp_path, monkeypatch):
    provider, accounts, target, native, raw = setup(tmp_path, monkeypatch)
    original = Path.read_bytes
    def read(path):
        value = original(path)
        if path.parent == target / 'subtitles/objects':
            accounts.scope = dict(SCOPE, epoch=2)
        return value
    monkeypatch.setattr(Path, 'read_bytes', read)
    assert provider.local_candidates(CONTEXT, 30, lambda: False, native) == []
    assert not native.exists()


@pytest.mark.parametrize('kind', ['missing', 'corrupt', 'no_accounts', 'unauthenticated', 'legacy_unscoped'])
def test_optional_prepared_cache_absence_does_not_interrupt_assrt(tmp_path, monkeypatch, kind):
    accounts = Accounts()
    root = tmp_path / 'preparation'
    if kind == 'unauthenticated':
        accounts.scope = dict(account_id='', epoch=0, authenticated=False)
    elif kind in ('corrupt', 'legacy_unscoped'):
        directory = root if kind == 'legacy_unscoped' else root / (SCOPE['account_id'][4:] + '-1')
        directory.mkdir(parents=True)
        (directory / 'resources.sqlite').write_bytes(b'not a sqlite database')
    provider = subtitles.AssrtCandidates(None, tmp_path / 'cache',
        accounts=None if kind == 'no_accounts' else accounts, preparation_root=root, clock=lambda: 0)
    provider.remote_candidates = Mock(return_value=dict(origin='assrt:fixture'))
    assert provider.candidates(CONTEXT, 30, lambda: False, root=tmp_path / 'native')['origin'] == 'assrt:fixture'
    assert provider.remote_candidates.call_count == 1


def test_unscoped_old_local_cache_receipt_has_no_legacy_authority(tmp_path):
    provider = subtitles.AssrtCandidates(None, tmp_path / 'cache', accounts=Accounts())
    assert provider.candidate_current(dict(origin='local:old')) is False
    assert provider.candidate_current(dict(origin='assrt:public')) is True


def fallback():
    spec = importlib.util.spec_from_file_location('prepared_scope_fallback',
        ROOT / 'addons/plugin.video.bobbi/lib/services/subtitle_fallback.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.SubtitleFallback(clock=lambda: 0)


def test_late_account_change_is_checked_again_when_owner_requests_candidate():
    module, worker = fallback()
    accounts = worker.accounts = Accounts()
    row = dict(native_instance='native', request_id='request', file_identity='file', url_sha256='url',
               subtitle_intent=0, subtitle_auto_intent=0)
    worker.key, worker.deadline = module.receipt_key(row), 30
    worker.result = dict(state='candidate', account_scope=dict(SCOPE), file={'path': 'immutable'})
    assert worker.request(row)['state'] == 'candidate'
    accounts.scope = dict(SCOPE, epoch=2)
    assert worker.request(row) == dict(state='unavailable', reason='SUBTITLE_ACCOUNT_CHANGED')
    # Even an already computed cache result cannot supersede a user's choice.
    assert worker.request(dict(row, subtitle_intent=1)) == dict(state='unavailable', reason='MANUAL_PRESERVED')
    assert worker.cancel.is_set()


def test_manual_cancel_during_local_lookup_never_publishes_fallback_result(monkeypatch):
    module, worker = fallback()
    worker.accounts = Accounts()
    row = dict(native_instance='native', request_id='request', file_identity='file', url_sha256='url',
               subtitle_intent=0, subtitle_auto_intent=0)
    key = worker.key = module.receipt_key(row)
    cancelled = worker.cancel = Event()
    def candidate(*args):
        assert worker.request(dict(row, subtitle_intent=1))['reason'] == 'MANUAL_PRESERVED'
        return dict(file={}, origin='local:fixture', account_scope=dict(SCOPE))
    worker.factory = lambda: type('Provider', (), {'candidates': staticmethod(candidate)})()
    worker._run(key, row, dict(mode='series'), cancelled, 30)
    assert worker.result is None and cancelled.is_set()
