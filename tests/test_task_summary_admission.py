"""Measured local scheduling only: not a network/decoder/seek speed benchmark."""
from copy import deepcopy
import json
from statistics import median
from threading import Event, Thread
import time
from types import SimpleNamespace

from test_catalog_service import service, file
from bobbi_platform.host import Host
from bobbi_platform.standard_session import StandardSession


def test_slow_scan_leaves_owner_queue_account_guard_and_projection_responsive(tmp_path, record_property):
    entered, release = Event(), Event()
    def listing(*args):
        entered.set()
        assert release.wait(5)
        return dict(items=[file(1)], has_more=False)
    svc, source, expected = service(tmp_path, listing)
    host = Host(tmp_path / 'host')
    accounts = SimpleNamespace(require_current=lambda value, **kw: svc.pans.accounts.require_current(value),
                               is_current=svc.pans.accounts.is_current)
    actor = StandardSession(accounts)
    host.bind_owner(actor.dispatch)
    samples, responses, failures = [], [], []

    def request(body):
        def run():
            began = time.perf_counter()
            try:
                responses.append(host._owner_request(body))
            except Exception as error:
                failures.append(type(error).__name__)
            samples.append(time.perf_counter() - began)
        worker = Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 1
        while host.calls.empty() and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.001)
        host.tick()  # Real bounded resident queue, while provider IO remains blocked.
        worker.join(1)
        assert not worker.is_alive() and not failures

    try:
        for i in range(5):
            request(dict(operation='select', request_id=('%032x' % i), account=expected))
        baseline = list(samples)
        task = svc.start_scan(expected, source)['task_id']
        assert entered.wait(1)
        for i in range(5, 10):
            request(dict(operation='select', request_id=('%032x' % i), account=expected))
            assert not release.is_set()
            started = time.monotonic()
            page = svc.dispatch('catalog_query', dict(expected=expected, query={'view': 'works'}, limit=20))
            assert page['items'] == [] and time.monotonic() - started < .25
            assert svc.pans.accounts.run_if_current(expected, lambda: True)
        during = samples[5:]
        data = dict(request_id='%032x' % 9, _account=deepcopy(expected),
                    url='https://example.invalid/selected.mkv', selection_policy='exact')
        request(dict(operation='register', request_id=data['request_id'], data=data))
        assert actor.observe(data['request_id'], data['url'], 1, 100)
        assert actor.observe(data['request_id'], data['url'], 60, 100)
        assert actor.current['position'] == 60  # Observed seek/progress update remains local.
        pending = svc.dispatch('catalog_cancel', dict(expected=expected, task_id=task))
        assert pending['cancel_requested'] and pending['state'] == 'running'
        release.set()
        svc.worker.join(2)
        final = svc.index.jobs(expected, task=task)['items'][0]
        assert final['state'] == 'canceled' and not final['counts']['discovered']
        measurement = dict(kind='synthetic-local-owner-queue', samples_per_condition=5,
            baseline_median_ms=round(median(baseline)*1000, 3),
            blocked_scan_median_ms=round(median(during)*1000, 3),
            blocked_scan_max_ms=round(max(during)*1000, 3),
            provider_blocked_until_owner_samples_complete=True,
            device_first_frame='not_run', device_seek='not_run', rss='not_measured',
            decision='retain existing bounded scan yielding; no additional scheduler')
        record_property('admission_measurement', json.dumps(measurement))
        print(json.dumps(measurement))
        assert max(during) < .25  # Existing owner request deadline, not a new speed promise.
    finally:
        release.set()
        svc.close()
        actor.close()
