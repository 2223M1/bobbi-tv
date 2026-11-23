from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from bobbi_core.resolve_lane import ResolveLane


class Resolver:
    def __init__(self):
        self.owner = threading.get_ident()
        self.calls = 0
        self.valid = True
        self.threads = []

    def plan(self, body):
        assert threading.get_ident() == self.owner
        return {'body': dict(body)}

    def perform(self, plan):
        assert threading.get_ident() != self.owner
        self.threads.append(threading.get_ident())
        self.calls += 1
        return True

    def finish(self, plan, valid):
        assert threading.get_ident() == self.owner
        return dict(state='ready' if valid and self.valid else 'unavailable', **plan['body'])


def body(nonce='a' * 32):
    return dict(request_id='b' * 32, verification_id=nonce)


def complete(lane, request):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        lane.tick()
        result = lane.request(request)
        if result['state'] != 'pending':
            return result
        time.sleep(0.005)
    pytest.fail('lightweight resolver exceeded one-second test budget')


def test_four_second_background_probe_cannot_block_resolve():
    resolver = Resolver()
    lane = ResolveLane(resolver)
    started = threading.Event()
    def qualify():
        started.set()
        time.sleep(4.1)
    try:
        with ThreadPoolExecutor(max_workers=1) as background:
            job = background.submit(qualify)
            assert started.wait(1)
            assert lane.request(body())['state'] == 'pending'
            assert complete(lane, body())['state'] == 'ready'
            assert not job.done()
    finally:
        lane.close()


def test_each_consumption_stage_requires_new_network_check():
    resolver = Resolver()
    lane = ResolveLane(resolver)
    try:
        lane.request(body())
        assert complete(lane, body())['state'] == 'ready'
        assert lane.request(body())['state'] == 'ready'
        assert resolver.calls == 1
        second = body('c' * 32)
        assert lane.request(second)['state'] == 'pending'
        assert complete(lane, second)['state'] == 'ready'
        assert resolver.calls == 2
        assert len(set(resolver.threads)) == 1
    finally:
        lane.close()


def test_expired_hit_does_not_return_ready_and_revalidates():
    resolver, now = Resolver(), [0.0]
    lane = ResolveLane(resolver, lambda: now[0])
    try:
        lane.request(body())
        assert complete(lane, body())['state'] == 'ready'
        now[0] = 2.1
        assert lane.request(body())['state'] == 'pending'
        assert complete(lane, body())['state'] == 'ready'
        assert resolver.calls == 2
    finally:
        lane.close()


def test_generation_or_resource_drift_invalidates_unexpired_ready():
    resolver = Resolver()
    lane = ResolveLane(resolver)
    try:
        lane.request(body())
        assert complete(lane, body())['state'] == 'ready'
        resolver.valid = False
        assert lane.request(body())['state'] == 'unavailable'
    finally:
        lane.close()


def test_same_nonce_cannot_retarget_request():
    lane = ResolveLane(Resolver())
    try:
        lane.request(body())
        with pytest.raises(ValueError, match='retargeted'):
            lane.request(dict(body(), request_id='d' * 32))
    finally:
        lane.close()


def test_dependency_loss_drains_completed_io_but_never_submits_queued_reads():
    resolver, now = Resolver(), [0.0]
    lane = ResolveLane(resolver, lambda: now[0])
    try:
        lane.request(body())
        lane.tick(allow_submit=False)
        assert resolver.calls == 0 and lane.future is None
        lane.tick()
        lane.future.result(timeout=1)
        lane.request(body('c' * 32))
        lane.tick(allow_submit=False)
        assert lane.future is None and resolver.calls == 1
        assert lane.request(body())['state'] == 'unavailable'
        now[0] = 4
        lane.tick(allow_submit=False)
        assert not lane.records and resolver.calls == 1
    finally:
        lane.close()


@pytest.mark.parametrize('at_poll', [False, True])
def test_rejected_finish_is_request_failure_not_service_loop_failure(at_poll):
    resolver = Resolver()
    original_finish = resolver.finish
    reject = [not at_poll]
    def finish(plan, valid):
        if valid and reject[0]:
            raise ValueError('Injected changed protection binding')
        return original_finish(plan, valid)
    resolver.finish = finish
    lane = ResolveLane(resolver)
    try:
        lane.request(body())
        if at_poll:
            assert complete(lane, body())['state'] == 'ready'
            reject[0] = True
        result = complete(lane, body())
        assert result == {'state': 'unavailable', 'reason': 'resolve_finish_rejected', 'error_type': 'ValueError'}
        reject[0] = False
        second = body('c' * 32)
        lane.request(second)
        assert complete(lane, second)['state'] == 'ready'
    finally:
        lane.close()


