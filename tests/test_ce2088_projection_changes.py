"""Repeated provider rows change receipts, not already retained source cards."""
from copy import deepcopy

import pytest

from test_ce2062_source_retry import source
from bobbi_core.source_list_session import SourceListSession
from bobbi_core.search_completion import SearchCompletion


def state(epoch=1, observed=1, code=''):
    return dict(epoch=epoch, account=str(epoch)*64, tuple='f'*64,
                observed=observed, code=code)


def session_with(*rows):
    calls = []
    def rank(items):
        calls.append(1)
        return items
    session = SourceListSession({}, rank)
    session.publish(session.epoch, 'first', rows, state='RUNNING')
    return session, session.snapshot(), calls


def test_same_rows_update_receipt_without_rank_or_ui_payload():
    a = source('a')
    session, before, calls = session_with(a)
    session.focus(session.key(a), 0)
    # Legacy merge keeps the first ordinary card, including title/seed count.
    later = deepcopy(a)
    later.title, later.seeders = 'changed provider title', 99
    receipt = SearchCompletion(2, succeeded=1, failed=1)
    session.publish(session.epoch, 'first', [later], state='PARTIAL', completion=receipt)
    after = session.snapshot(after_content_revision=before['content_revision'])
    assert after['entries'] is None
    assert after['content_revision'] == before['content_revision']
    assert after['revision'] > before['revision']
    assert after['providers']['first']['completion']['failed'] == 1
    assert session.entries[session.key(a)].title == 'a'
    assert session.focus_key == session.key(a) and len(calls) == 1


def test_episode_proof_promotes_once():
    a = source('a')
    session, before, calls = session_with(a)
    a.requiresCatalogEpisodeProof = True
    session.publish(session.epoch, 'second', [a], state='RUNNING')
    after = session.snapshot(after_content_revision=before['content_revision'])
    assert after['entries'][0][1].requiresCatalogEpisodeProof is True
    session.publish(session.epoch, 'second', [a])
    assert session.snapshot(after_content_revision=after['content_revision'])['entries'] is None
    assert len(calls) == 2


@pytest.mark.parametrize('ordered', [False, True])
def test_share_failure_changes_retain_required_invalidation(ordered):
    a = source('a')
    a.verifiedShareFile = True
    if ordered:
        a.shareState = state()
    session, before, calls = session_with(a)
    a.shareFailure, a.verifiedShareFile = 'share_revoked', False
    if ordered:
        a.shareState = state(observed=2, code='share_revoked')
    session.publish(session.epoch, 'second', [a], state='RUNNING')
    after = session.snapshot(after_content_revision=before['content_revision'])
    assert after['entries'][0][1].shareFailure == 'share_revoked'
    assert after['entries'][0][1].verifiedShareFile is False
    session.publish(session.epoch, 'second', [a])
    assert session.snapshot(after_content_revision=after['content_revision'])['entries'] is None
    assert len(calls) == 2


def test_new_account_clears_other_cards_and_rejects_late_old_receipt():
    a, b = source('a'), source('b')
    for row in (a, b):
        row.shareState, row.shareFailure, row.verifiedShareFile = state(), 'share_revoked', True
    session, before, calls = session_with(a, b)
    a.shareState, a.shareFailure = state(epoch=2, observed=2), ''
    session.publish(session.epoch, 'second', [a], state='RUNNING')
    after = session.snapshot(after_content_revision=before['content_revision'])
    assert after['entries'] is not None
    assert session.entries[session.key(b)].shareState == {}
    assert session.entries[session.key(b)].verifiedShareFile is False
    # Late old-account state cannot mutate either visible row or invalidate.
    a.shareState, a.shareFailure = state(), 'share_revoked'
    session.publish(session.epoch, 'second', [a])
    assert session.snapshot(after_content_revision=after['content_revision'])['entries'] is None
    assert len(calls) == 2


def test_capacity_failure_still_updates_receipt_and_preserves_existing_card():
    session = SourceListSession({}, lambda rows: rows, limit=1, capacity=1)
    session.publish(session.epoch, 'first', [source('a')], state='RUNNING')
    before = session.snapshot()
    session.publish(session.epoch, 'first', [source('b')])
    after = session.snapshot(after_content_revision=before['content_revision'])
    assert after['entries'] is None
    assert after['providers']['first']['error'] == 'CANDIDATE_CAPACITY_EXCEEDED'
