"""Independent playback regression expectations against an explicit repository.

Run in an isolated process with BOBBI_REVIEW_REPO=/absolute/candidate/repository.
Loads the candidate's real StandardSession and StandardPlayback source files.
Only account, history/player-command and provider IO are doubles; the fake
clock is deterministic. This is not a Kodi/device certification.
"""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def product(monkeypatch):
    value = os.environ.get('BOBBI_REVIEW_REPO')
    if not value:
        raise pytest.UsageError('Set BOBBI_REVIEW_REPO to the candidate repository root')
    repo = Path(value).resolve()
    platform = repo / 'addons/script.module.bobbi.platform/lib/bobbi_platform'
    service = repo / 'addons/plugin.video.bobbi/lib/services/standard_playback.py'
    assert platform.is_dir() and service.is_file(), 'Candidate source tree is incomplete'
    package = ModuleType('bobbi_platform')
    package.__path__ = [str(platform)]
    monkeypatch.setitem(sys.modules, 'bobbi_platform', package)
    for name in ('bobbi_platform.playback', 'bobbi_platform.standard_session'):
        monkeypatch.delitem(sys.modules, name, raising=False)
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module
    session_module = load('bobbi_platform.standard_session', platform / 'standard_session.py')
    service_module = load('independent_review_standard_playback', service)
    clock = [100.0]
    account = {'account_id': '', 'authenticated': False, 'epoch': 0}
    def require(value, authenticated=False):
        if value != account:
            raise ValueError('STALE_ACCOUNT')
    accounts = SimpleNamespace(is_current=lambda value: value == account, require_current=require)
    saved, opened = [], []
    owner = session_module.StandardSession(accounts, history=saved.append,
        open_next=opened.append, clock=lambda: clock[0])
    adapter = object.__new__(service_module.StandardPlayback)
    adapter.host = SimpleNamespace(accounts=accounts)
    adapter.session = owner
    # Replace this module's clock dependency without changing global time or
    # the production state machine. Network IO stubs honor their deadline.
    monkeypatch.setattr(service_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    current = dict(request_id='a'*32, _account=deepcopy(account),
        url='https://media.example/S01E01.mkv', mode='tv',
        tv_data={'season': 1, 'episode': 1}, selection_policy='exact')
    successor = dict(current, request_id='b'*32,
        url='https://media.example/S01E02.mkv', tv_data={'season': 1, 'episode': 2})
    owner.select(current['request_id'], account)
    assert owner.register(current['request_id'], current)['accepted']
    yield SimpleNamespace(owner=owner, module=service_module, adapter=adapter,
        clock=clock, saved=saved, opened=opened, current=current, successor=successor)
    owner.close()


def sample(product, position=99.0, duration=100.0):
    data = product.current
    return product.owner.observe(data['request_id'], data['url'], position, duration)


def join_worker(product):
    worker = product.owner.worker
    if worker is not None:
        worker.join(timeout=1.0)
        assert not worker.is_alive(), 'Test IO must not leave a blocked worker'


def test_invalid_progress_sample_cannot_refresh_eof_evidence(product):
    """A missing duration must not make a 40-second-old end position fresh."""
    assert sample(product)
    product.owner.current['next_data'] = deepcopy(product.successor)
    product.clock[0] += 40.0
    sample(product, 0.0, 0.0)
    natural = product.owner.terminal(product.current['request_id'], 'ENDED')
    product.clock[0] += .3
    product.owner.tick()
    assert not natural, 'Invalid 0/0 refreshed stale end-position evidence'
    assert not product.saved[-1]['completed']
    assert product.opened == []


def test_ready_next_media_is_not_discarded_by_optional_subtitle_delay(product, monkeypatch):
    """EOF-only media discovery succeeds; absent subtitles must not consume it."""
    calls = []
    def ready_media(current, cancelled):
        assert not cancelled()
        calls.append(('media_ready', product.clock[0]))
        return deepcopy(product.successor)
    def slow_absent_subtitle(data, host, deadline, cancelled):
        # The provider needs 25 seconds to find no subtitle. Honor a shorter
        # passed deadline so a repair can bound optional IO inside EOF budget.
        start = product.clock[0]
        product.clock[0] = min(start + 25.0, deadline)
        calls.append(('subtitle_finished', product.clock[0]))
        if cancelled() or product.clock[0] >= deadline:
            raise RuntimeError('SUBTITLE_DEADLINE')
        return None
    monkeypatch.setattr(product.module, 'next_data', ready_media)
    monkeypatch.setattr(product.module, 'discover', slow_absent_subtitle)
    product.owner.next_loader = product.adapter.next_with_subtitle
    assert sample(product)
    assert product.owner.terminal(product.current['request_id'], 'ENDED')
    eof_at = product.clock[0]
    product.owner.tick()
    join_worker(product)
    product.clock[0] = max(product.clock[0], eof_at + .3)
    product.owner.tick()
    assert calls[0] == ('media_ready', eof_at)
    assert len(product.opened) == 1, 'Playable next media was lost behind subtitle IO'
    assert product.opened[0]['url'] == product.successor['url']
    assert product.clock[0] - eof_at < 20, 'Do not repair by extending the absolute EOF window'


def test_fresh_valid_eof_continues_exact_candidate_once(product, monkeypatch):
    """Positive control: disabling continuation cannot satisfy this review."""
    monkeypatch.setattr(product.module, 'next_data',
                        lambda current, cancelled: deepcopy(product.successor))
    monkeypatch.setattr(product.module, 'discover', lambda *args: None)
    product.owner.next_loader = product.adapter.next_with_subtitle
    assert sample(product)
    product.owner.tick(playing=True)
    join_worker(product)
    product.owner.tick(playing=True)
    assert product.owner.terminal(product.current['request_id'], 'ENDED')
    product.clock[0] += .3
    product.owner.tick()
    product.owner.tick()
    assert len(product.opened) == 1
    assert product.opened[0]['url'] == product.successor['url']
    assert product.opened[0]['tv_data'] == product.successor['tv_data']
    assert product.opened[0]['_account'] == product.successor['_account']
    assert product.saved[-1]['completed']


def test_genuinely_missing_candidate_never_fabricates_continuation(product, monkeypatch):
    """Negative control: a subtitle fix must not invent a next-media candidate."""
    monkeypatch.setattr(product.module, 'next_data', lambda current, cancelled: None)
    def unexpected_subtitle(*args):
        pytest.fail('No media candidate means there is no subtitle authority')
    monkeypatch.setattr(product.module, 'discover', unexpected_subtitle)
    product.owner.next_loader = product.adapter.next_with_subtitle
    assert sample(product)
    product.owner.tick(playing=True)
    join_worker(product)
    product.owner.tick(playing=True)
    assert product.owner.terminal(product.current['request_id'], 'ENDED')
    product.owner.tick()
    join_worker(product)
    product.clock[0] += .3
    product.owner.tick()
    product.clock[0] += 20.0
    product.owner.tick()
    assert product.opened == []
    assert product.owner.current['cancel'].is_set()
