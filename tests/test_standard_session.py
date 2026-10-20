"""Product standard lifecycle tests; no native receipt mocks or hardware claims."""
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
import time

import pytest

from bobbi_platform.standard_session import StandardSession


@pytest.fixture
def actor():
    clock = [100.]
    account = {'account_id': '', 'authenticated': False, 'epoch': 0}
    def require(value, authenticated=False):
        if value != account:
            raise ValueError('account changed')
    accounts = SimpleNamespace(require_current=require, is_current=lambda value: value == account)
    saved, opened = [], []
    owner = StandardSession(accounts, history=lambda row: saved.append(row),
        open_next=lambda data: opened.append(data), clock=lambda: clock[0])
    return SimpleNamespace(owner=owner, clock=clock, account=account, saved=saved, opened=opened)


def begin(actor, request='a' * 32, url='https://media.example/a.mkv'):
    actor.owner.select(request, actor.account)
    data = dict(request_id=request, _account=deepcopy(actor.account), url=url,
                selection_policy='exact', subtitles_path=['/profile/中文.ass'])
    assert actor.owner.register(request, data)['accepted']
    return data


def test_submission_is_not_av_start_and_wrong_file_cannot_attach(actor):
    data = begin(actor)
    assert actor.saved == []
    assert not actor.owner.observe(data['request_id'], 'https://media.example/wrong', 0, 100)
    assert not actor.owner.observe('b' * 32, data['url'], 0, 100)
    assert actor.owner.observe(data['request_id'], data['url'], 0, 100)
    assert actor.saved[-1]['terminal_reason'] == 'STARTED'
    assert not actor.saved[-1]['completed']
    assert 'native_instance' not in actor.saved[-1]


def test_selection_b_retires_late_a_and_cancel_cannot_reopen(actor):
    a = begin(actor)
    b = begin(actor, 'b' * 32, 'https://media.example/b')
    assert not actor.owner.register(a['request_id'], a)['accepted']
    assert not actor.owner.observe(a['request_id'], a['url'], 100, 100)
    assert not actor.owner.terminal(a['request_id'], 'ENDED')
    actor.owner.dispatch(dict(operation='cancel', request_id=b['request_id']))
    assert not actor.owner.observe(b['request_id'], b['url'], 0, 100)
    assert actor.opened == []


@pytest.mark.parametrize('kind,position', [('STOPPED', 99), ('ERROR', 99), ('ENDED', 45)])
def test_stop_error_or_short_read_never_becomes_completed_or_next(actor, kind, position):
    data = begin(actor)
    actor.owner.observe(data['request_id'], data['url'], position, 100)
    actor.owner.current['next_data'] = {'url': 'https://media.example/next'}
    assert not actor.owner.terminal(data['request_id'], kind)
    actor.clock[0] += 1
    actor.owner.tick()
    assert not actor.saved[-1]['completed']
    assert actor.saved[-1]['current_time'] == position
    assert actor.opened == []


def test_natural_eof_continues_exact_worker_result_once(actor):
    data = begin(actor)
    expected = {'request_id': 'b' * 32, 'url': 'https://media.example/exact-next'}
    actor.owner.next_loader = lambda current, cancelled: expected
    actor.owner.observe(data['request_id'], data['url'], 99, 100)
    actor.owner.tick()
    actor.owner.worker.join(1)
    assert actor.owner.terminal(data['request_id'], 'ENDED')
    actor.clock[0] += .3
    actor.owner.tick()
    actor.owner.tick()
    assert actor.opened == [expected]
    assert actor.saved[-1]['completed']


@pytest.mark.parametrize('replacement', ['selection', 'account', 'stop'])
def test_late_next_result_loses_to_new_user_action(actor, replacement):
    release = Event()
    data = begin(actor)
    def load(current, cancelled):
        release.wait(1)
        return {'url': 'https://media.example/late'}
    actor.owner.next_loader = load
    actor.owner.observe(data['request_id'], data['url'], 99, 100)
    actor.owner.tick()
    actor.owner.terminal(data['request_id'], 'ENDED')
    if replacement == 'selection':
        begin(actor, 'b' * 32)
    elif replacement == 'account':
        actor.account['epoch'] += 1
    else:
        actor.owner.terminal(data['request_id'], 'STOPPED')
    release.set()
    actor.owner.worker.join(1)
    actor.clock[0] += 1
    actor.owner.tick()
    assert actor.opened == []


def test_unassociated_terminal_while_new_video_is_playing_is_ignored(actor):
    data = begin(actor)
    actor.owner.observe(data['request_id'], data['url'], 99, 100)
    assert not actor.owner.terminal(data['request_id'], 'ENDED', playing=True)
    assert actor.owner.current['state'] == 'playing'


def test_same_account_refresh_is_not_retirement(actor):
    data = begin(actor)
    actor.owner.observe(data['request_id'], data['url'], 2, 100)
    actor.owner.tick()
    assert actor.owner.current_request(data['request_id'])
