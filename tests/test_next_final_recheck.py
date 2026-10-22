"""Continuation candidates remain provisional until the final owned EOF check."""
from copy import deepcopy
from threading import Event

import pytest

from test_standard_session import actor, begin
from test_standard_product import product, selected, handoff


@pytest.mark.parametrize('transport', ['bt', '115'])
def test_cached_next_is_rechecked_at_eof_and_only_final_result_opens_once(actor, transport):
    data = begin(actor)
    expected = dict(url='https://media.example/verified-115', _next_recheck=True, _next_transport='115')
    actor.owner.observe(data['request_id'], data['url'], 99, 100)
    actor.owner.current['next_data'] = dict(url='magnet:?cached', _next_recheck=True, _next_transport=transport)
    calls = []
    def load(current, cancelled):
        calls.append(deepcopy(current))
        assert current['_continuation_final'] and not cancelled()
        return expected
    actor.owner.next_loader = load
    assert actor.owner.terminal(data['request_id'], 'ENDED')
    actor.clock[0] += .3
    actor.owner.tick(False)
    assert actor.opened == []
    actor.owner.worker.join(1)
    actor.owner.tick(False)
    actor.owner.tick(False)
    assert actor.opened == [expected]
    assert len(calls) == 1


@pytest.mark.parametrize('replacement', ['selection', 'account', 'stop', 'deadline'])
def test_final_recheck_cannot_publish_after_new_intent_account_or_deadline(actor, replacement):
    release = Event()
    data = begin(actor)
    actor.owner.observe(data['request_id'], data['url'], 99, 100)
    actor.owner.current['next_data'] = dict(url='magnet:?cached', _next_recheck=True, _next_transport='bt')
    def load(current, cancelled):
        release.wait(1)
        return dict(url='https://media.example/late', _next_recheck=True, _next_transport='115')
    actor.owner.next_loader = load
    actor.owner.terminal(data['request_id'], 'ENDED')
    actor.clock[0] += .3
    actor.owner.tick(False)
    if replacement == 'selection': begin(actor, 'b' * 32)
    elif replacement == 'account': actor.account['epoch'] += 1
    elif replacement == 'stop': actor.owner.terminal(data['request_id'], 'STOPPED')
    else:
        actor.clock[0] += 20
        actor.owner.tick(False)
    release.set()
    actor.owner.worker.join(1)
    actor.owner.tick(False)
    assert actor.opened == []


def test_optional_subtitle_lookup_never_delays_final_verified_next(product, monkeypatch):
    data = selected(product)
    data['_continuation_final'] = True
    expected = dict(data, url='https://media.example/next', request_id='b' * 32)
    monkeypatch.setattr(product.module, 'next_data', lambda *args: expected)
    monkeypatch.setattr(product.module, 'discover', lambda *args: pytest.fail('optional subtitles must be background'))
    assert product.actor.next_with_subtitle(data, lambda: False) == expected
