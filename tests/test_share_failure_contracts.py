"""Offline exact-share failure contracts; no device, CDN, or playback control."""
from contextlib import closing
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import sys
from threading import Lock, Thread, get_ident
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for ADDON in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT / 'addons' / ADDON / 'lib'))

from bobbi_catalog.api import ShareError
from bobbi_core import juku_catalog as catalog, share_stream
from bobbi_core.share_failure import failure_value, proofs, tuple_hash
from bobbi_core.share_stream import Binding, ShareStream
from bobbi_platform import runtime
from bobbi_platform.account_manager import AccountError, validate_snapshot
from bobbi_platform.host import Host
from test_accounts import credential, logged_in


ADDRESS = 'https://fixture.115cdn.com/video|User-Agent=fixture'
SCOPE = dict(account_id='115:' + 'a' * 64, epoch=2, authenticated=True)
SPEC = catalog._spec(dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Movie']))


def selected(index=1):
    key = '{:064x}'.format(index)
    return dict(locator='am6bjuku://' + key, guid='juku:' + key,
                title='Audit.Movie.2024.Version%d.mkv' % index,
                size=1000 + index, media='movies:101:0:0')


def binding(resolve, manager=None, scope=None, index=1, request='b' * 32):
    return Binding(dict(selected(index), request_id=request), resolve,
                   lambda url: url.startswith('https://fixture.115cdn.com/'),
                   account=manager, scope=scope)


def failed_entry(manager=None, scope=None, category='share_revoked', stamp=None, index=1):
    error = ShareError(category, api_code=4100010)
    if stamp is not None:
        error.checked_proof = dict(checked_at=stamp, checked_account=catalog._account_fingerprint(scope))
    def fail(*args):
        raise error
    entry = binding(fail, manager, scope, index)
    entry.transport_hash = 'c' * 64
    with pytest.raises(ShareError):
        entry.grant()
    return entry


def resident(*entries):
    service = ShareStream.__new__(ShareStream)
    service.lock = Lock()
    service.records = {entry.token: entry for entry in entries}
    return service


@pytest.mark.parametrize('category', ['share_revoked', 'identity_changed'])
def test_permanent_negative_has_fixed_ttl_and_does_not_consume_renewals(monkeypatch, category):
    clock, calls = [100.0], []
    monkeypatch.setattr(share_stream, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000.0, perf_counter_ns=lambda:int(clock[0]*10**9)))
    original = ShareError(category, http_status=403, api_code=4100010)
    def resolve(*args):
        calls.append(clock[0])
        raise original
    entry = binding(resolve)
    with pytest.raises(ShareError):
        entry.grant()
    first = entry.grant_outcome()
    assert first['retry_after'] == 130.0
    for stamp in (101.0, 119.0, 129.999):
        clock[0] = stamp
        with pytest.raises(ShareError) as failure:
            entry.grant()
        assert failure.value is not original
        assert (failure.value.code, failure.value.http_status, failure.value.api_code) == (category, 403, 4100010)
        assert entry.grant_outcome() is first
        assert entry.renewals == [100.0]
    clock[0] = 130.0
    with pytest.raises(ShareError):
        entry.grant()
    assert calls == [100.0, 130.0] and entry.renewals == calls
    assert entry.grant_outcome()['retry_after'] == 160.0


@pytest.mark.parametrize('category', ['network', 'network_timeout', 'http_rejected',
    'login_required', 'deadline', 'cancelled', 'invalid_response', 'share_unavailable'])
def test_transient_or_auth_failures_are_not_negative_cached(category):
    calls = []
    def resolve(*args):
        calls.append(True)
        raise ShareError(category, http_status=429 if category == 'http_rejected' else None)
    entry = binding(resolve)
    for _ in range(2):
        with pytest.raises(ShareError):
            entry.grant()
    assert len(calls) == len(entry.renewals) == 2


def test_later_success_replaces_failure_and_reuses_one_grant(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(share_stream, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000.0, perf_counter_ns=lambda:int(clock[0]*10**9)))
    entry = failed_entry()
    failed = entry.grant_outcome()
    calls = []
    entry.resolve = lambda *args: calls.append(True) or ADDRESS
    clock[0] = failed['retry_after']
    assert entry.grant() == entry.grant() == ADDRESS
    assert calls == [True] and entry.grant_outcome()['state'] == 'ready'
    assert 'failure' not in entry.grant_outcome()


@pytest.mark.parametrize('category', ['share_revoked', 'identity_changed'])
def test_permanent_renewal_failure_cannot_return_old_cached_address(monkeypatch, category):
    clock, calls = [100.0], []
    monkeypatch.setattr(share_stream, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000.0, perf_counter_ns=lambda:int(clock[0]*10**9)))
    entry = binding(lambda *args: ADDRESS)
    assert entry.grant() == ADDRESS
    def fail(*args):
        calls.append(True)
        raise ShareError(category)
    entry.resolve = fail
    with pytest.raises(ShareError):
        entry.grant(rejected=ADDRESS)
    assert entry.address is None and entry.expires_at is None
    for _ in range(2):
        with pytest.raises(ShareError):
            entry.grant()
    assert len(calls) == 1
    clock[0] = 130.0
    with pytest.raises(ShareError):
        entry.grant()
    assert len(calls) == 2


def test_late_old_account_failure_cannot_poison_current_binding(tmp_path):
    manager, scope = logged_in(tmp_path)
    def changed(*args):
        manager.install(credential('456'), scope)
        raise ShareError('share_revoked')
    old = binding(changed, manager, scope)
    with pytest.raises(ShareError):
        old.grant()
    assert old.grant_outcome()['state'] == 'pending'
    assert resident(old).failure_record(scope, selected(), old.transport_hash) is None
    current = binding(lambda *args: ADDRESS, manager, manager.snapshot())
    assert current.grant() == ADDRESS and current.grant_outcome()['state'] == 'ready'
    with pytest.raises(OSError, match='SHARE_STOPPED'):
        old.grant()


def test_negative_does_not_spread_to_new_registration():
    old = failed_entry()
    new = binding(lambda *args: ADDRESS, request='d' * 32)
    assert new.grant() == ADDRESS and old.grant_outcome()['state'] == 'failed'


def test_only_actual_typed_safe_failure_values_are_kept():
    assert failure_value(RuntimeError('share_revoked https://private.example/token')) is None
    error = ShareError('share_revoked')
    error.http_status, error.api_code = True, 'private-response'
    error.invalidation_failed = 'true'
    error.checked_proof = dict(checked_at=float('nan'), checked_account='a' * 64)
    assert failure_value(error) == dict(code='share_revoked', http_status=None,
                                       api_code=None, invalidation_failed=False)


def test_failure_lookup_is_readonly_does_not_take_grant_lock_or_hold_records_lock(tmp_path, monkeypatch):
    manager, scope = logged_in(tmp_path)
    entry = failed_entry(manager, scope)
    service = resident(entry)
    previous, renewals = entry.grant_outcome(), list(entry.renewals)
    original = manager.is_current
    def current(value):
        assert service.lock.acquire(blocking=False), 'Records lock held while checking account'
        service.lock.release()
        return original(value)
    monkeypatch.setattr(manager, 'is_current', current)
    with entry.lock:
        assert service.failure_record(scope, selected(), entry.transport_hash) == (entry, previous)
    assert entry.grant_outcome() is previous and entry.renewals == renewals


@pytest.mark.parametrize('change', [dict(locator='am6bjuku://' + 'f' * 64),
    dict(guid='juku:' + 'f' * 64), dict(title='Other.mkv'), dict(size=999), dict(media='movies:102:0:0')])
def test_failure_lookup_requires_all_exact_tuple_fields(change):
    entry = failed_entry(scope=SCOPE)
    service = resident(entry)
    assert service.failure_record(SCOPE, dict(selected(), **change), entry.transport_hash) is None
    assert service.failure_record(dict(SCOPE, epoch=3), selected(), entry.transport_hash) is None
    assert service.failure_record(SCOPE, selected(), 'e' * 64) is None


def host_fixture(tmp_path):
    manager, scope = logged_in(tmp_path)
    entry = failed_entry(manager, scope, stamp=2000.0)
    host = Host(tmp_path)
    host.runtime.close()  # Direct-dispatch tests never start a listener or leave a bound socket.
    host.accounts, host.streams = manager, resident(entry)
    owner = dict(boot_id='d' * 32, epoch=4, request_id='e' * 32,
                 file_identity='transport:' + 'f' * 64,
                 native_instance='11111111-2222-3333-4444-555555555555',
                 url_sha256=entry.transport_hash)
    message = dict(account=scope, owner=owner, selected=selected())
    return host, entry, message


def test_host_routes_failure_proof_through_existing_native_owner_queue(tmp_path):
    host, entry, message = host_fixture(tmp_path)
    threads, requests, replies, errors = [], [], [], []
    def owner(request):
        requests.append(request)
        threads.append(get_ident())
        return dict(failed=True, receipt=message['owner'])
    host.bind_owner(owner)
    def query():
        try:
            replies.append(host.dispatch('share_failure', message))
        except Exception as error:
            errors.append(error)
    worker = Thread(target=query)
    worker.start()
    job = host.calls.get(timeout=1)
    host.calls.put_nowait(job)
    host.tick()
    worker.join(1)
    assert not worker.is_alive() and not errors
    assert threads == [get_ident()]
    assert requests == [dict({key: message['owner'][key] for key in
                        ('boot_id', 'epoch', 'request_id', 'file_identity')}, operation='startup_failure')]
    assert entry.body['request_id'] != message['owner']['request_id']
    assert replies == [dict(matched=True, account=message['account'], owner=message['owner'],
        tuple_sha256=tuple_hash(message['selected']), failure=dict(code='share_revoked',
        http_status=None, api_code=4100010, invalidation_failed=False,
        share_state=entry.grant_outcome()['failure']['share_state']))]
    state = replies[0]['failure']['share_state']
    from bobbi_core.share_failure import valid_card_state, _scope_key
    assert valid_card_state(state) and state['tuple'] == tuple_hash(message['selected'])
    assert state['epoch'] == message['account']['epoch'] and state['account'] == _scope_key(message['account'])


@pytest.mark.parametrize('field,value', [('boot_id', '0' * 32), ('epoch', 5),
    ('request_id', '0' * 32), ('file_identity', 'transport:' + '0' * 64),
    ('native_instance', '22222222-2222-3333-4444-555555555555'), ('url_sha256', '0' * 64)])
def test_host_rejects_every_mismatched_native_receipt_field(tmp_path, monkeypatch, field, value):
    host, entry, message = host_fixture(tmp_path)
    receipt = dict(message['owner'], **{field: value})
    monkeypatch.setattr(host, '_owner_request', lambda request: dict(failed=True, receipt=receipt))
    assert host.dispatch('share_failure', message) == {'matched': False}


def test_host_rechecks_outcome_and_account_after_owner_receipt(tmp_path, monkeypatch):
    host, entry, message = host_fixture(tmp_path)
    def fresh_success(request):
        entry._publish_outcome(dict(started=time.monotonic(), started_at=time.time(), state='ready'))
        return dict(failed=True, receipt=message['owner'])
    monkeypatch.setattr(host, '_owner_request', fresh_success)
    assert host.dispatch('share_failure', message) == {'matched': False}
    entry._publish_outcome(dict(state='failed', started=1, started_at=1,
        failure=dict(code='share_revoked', http_status=None, api_code=None, invalidation_failed=False)))
    def switched_account(request):
        host.accounts.install(credential('456'), message['account'])
        return dict(failed=True, receipt=message['owner'])
    monkeypatch.setattr(host, '_owner_request', switched_account)
    with pytest.raises(AccountError):
        host.dispatch('share_failure', message)


def test_readonly_host_queries_never_create_missing_share_service(tmp_path, monkeypatch):
    host, _, message = host_fixture(tmp_path)
    host.streams = None
    monkeypatch.setattr(host, '_shares', lambda: pytest.fail('Read-only lookup constructed ShareStream'))
    monkeypatch.setattr(host, '_owner_request', lambda request: pytest.fail('No Binding requires no owner call'))
    assert host.dispatch('share_failure', message) == {'matched': False}
    batch = [dict(tuple_sha256=tuple_hash(selected()), checked_at=2000.0)]
    assert host.dispatch('share_known_failures', dict(account=message['account'], proofs=batch)) == dict(
        account=message['account'], denied=[])


@pytest.mark.parametrize('stamp,scope_change,category,expected', [
    (2000.0, False, 'share_revoked', True), (2000.0, False, 'identity_changed', True),
    (2001.0, False, 'share_revoked', False), (2000.0, True, 'share_revoked', False),
    (2000.0, False, 'network', False)])
def test_known_negative_requires_exact_checked_proof_and_account(stamp, scope_change, category, expected):
    entry = failed_entry(scope=SCOPE, stamp=2000.0, category=category)
    scope = dict(SCOPE, epoch=3) if scope_change else SCOPE
    key = tuple_hash(selected())
    assert resident(entry).denied_proofs(scope, {key: stamp}) == ([key] if expected else [])


@pytest.mark.parametrize('state', ['ready', 'pending'])
@pytest.mark.parametrize('same_started', [False, True])
@pytest.mark.parametrize('reversed_records', [False, True])
def test_newer_success_or_pending_binding_suppresses_older_negative(
        monkeypatch, state, same_started, reversed_records):
    clock = [100.0]
    monkeypatch.setattr(share_stream, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000.0, perf_counter_ns=lambda:int(clock[0]*10**9)))
    old = failed_entry(scope=SCOPE, stamp=2000.0)
    clock[0] = 100.0 if same_started else 101.0
    new = binding(lambda *args: ADDRESS, scope=SCOPE, request='d' * 32)
    assert new.grant() == ADDRESS
    if state == 'pending':
        new._publish_outcome(dict(state='pending', started=clock[0]))
    key = tuple_hash(selected())
    service = resident(new, old) if reversed_records else resident(old, new)
    assert service.denied_proofs(SCOPE, {key: 2000.0}) == []
    assert resident().denied_proofs(SCOPE, {key: 2000.0}) == []


@pytest.mark.parametrize('bad', [None, [], [{}],
    [dict(tuple_sha256='a' * 64, checked_at=value) for value in (1, 1)],
    [dict(tuple_sha256='a' * 64, checked_at=float('nan'))],
    [dict(tuple_sha256='a' * 64, checked_at=float('inf'))],
    [dict(tuple_sha256='a' * 64, checked_at=True)],
    [dict(tuple_sha256='a' * 64, checked_at=-1)],
    [dict(tuple_sha256='A' * 64, checked_at=1)],
    [dict(tuple_sha256='{:064x}'.format(i), checked_at=1) for i in range(129)]])
def test_batch_proof_protocol_is_closed_finite_unique_and_bounded(bad):
    with pytest.raises(ValueError, match='SHARE_PROOFS_INVALID'):
        proofs(bad)


def test_maximum_batch_fits_actual_runtime_request_and_reply_wrappers(tmp_path, monkeypatch):
    host, _, message = host_fixture(tmp_path)
    scope = validate_snapshot(dict(message['account'], epoch=2**63-1), authenticated=True)
    host.accounts._scope = scope
    host.streams = SimpleNamespace(denied_proofs=lambda expected, submitted: sorted(submitted))
    batch = [dict(tuple_sha256='{:064x}'.format(index), checked_at=sys.float_info.max)
             for index in range(128)]
    assert len(proofs(batch)) == 128
    config = dict(port=12345, token='a' * 64)
    monkeypatch.setattr(runtime, 'profile', lambda **kwargs: SimpleNamespace(
        is_file=lambda: True, is_symlink=lambda: False,
        stat=lambda: SimpleNamespace(st_size=128),
        read_text=lambda **kwargs: json.dumps(config)))
    wires = {}
    def open_request(request, timeout):
        # Execute the actual server handler and both runtime serializers without a socket.
        wires['request'] = request.data
        handler = runtime.Handler.__new__(runtime.Handler)
        handler.path = '/control'
        handler.headers = {'Authorization': 'Bearer ' + config['token'],
                           'Content-Length': str(len(request.data))}
        handler.server = SimpleNamespace(token=config['token'], dispatch=host.dispatch)
        handler.rfile, handler.wfile = io.BytesIO(request.data), io.BytesIO()
        handler.send_response = lambda *args: None
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        handler.do_POST()
        wires['reply'] = handler.wfile.getvalue()
        return io.BytesIO(wires['reply'])
    monkeypatch.setattr(runtime, 'build_opener', lambda *args: SimpleNamespace(open=open_request))
    result = runtime.call('share_known_failures', dict(account=scope, proofs=batch), timeout=.2)
    assert result == dict(account=scope, denied=batch)
    assert len(wires['request']) <= 16384 and len(wires['reply']) <= 16384
    assert json.loads(wires['request']) == dict(action='share_known_failures',
        body=dict(account=scope, proofs=batch))
    assert json.loads(wires['reply']) == dict(ok=True, result=result)


def catalog_row(index=1):
    movie = dict(tmdbId=101, typeId=1, year=2024, title='Audit Movie', id=1, vodId=1)
    link = dict(url='https://115.com/s/sabcdef', fileId=str(index),
                fileName='Audit.Movie.2024.Version%d.mkv' % index,
                fileSize=1000 + index, parentFolderId='8')
    return catalog._bound(catalog._row(movie, link, 'shared:fixture-library'), SPEC)


def seed(cache, count=1, stamp=None, scope=SCOPE):
    stamp = time.time() if stamp is None else stamp
    rows = [catalog_row(index + 1) for index in range(count)]
    cache.replace_library('fixture-library', 1, rows)
    cache.remember(rows, SPEC)
    with cache.db:
        cache.db.execute('UPDATE selections SET checked_at=?,checked_account=?',
                         (stamp, catalog._account_fingerprint(scope)))
    return rows


@pytest.mark.parametrize('category', ['share_revoked', 'identity_changed'])
def test_juku_permanent_failure_clears_only_exact_old_proof(tmp_path, category):
    with closing(catalog.Cache(tmp_path)) as cache:
        row = seed(cache, 2)[0]
    def fail(*args):
        raise ShareError(category)
    client = SimpleNamespace(account_scope=SCOPE, resolve=fail)
    with pytest.raises(ShareError) as raised:
        catalog.resolve('am6bjuku://' + row['key'], 'juku:' + row['key'], row['name'], row['size'],
                        SPEC['media_key'], state=tmp_path, client=client)
    assert raised.value.checked_proof['checked_account'] == catalog._account_fingerprint(SCOPE)
    with closing(catalog.Cache(tmp_path)) as cache:
        assert cache.select(row['key'], SPEC['media_key'])['_checked_at'] == 0
        assert cache.db.execute('SELECT COUNT(*) FROM selections WHERE checked_at>0').fetchone()[0] == 1
        assert cache.db.execute('SELECT COUNT(*) FROM selections').fetchone()[0] == 2
        assert cache.db.execute('SELECT COUNT(*) FROM shared_rows').fetchone()[0] == 2
        assert cache.db.execute('SELECT COUNT(*) FROM libraries').fetchone()[0] == 1
        assert cache.db.execute('SELECT COUNT(*) FROM library_visibility').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['newer_success', 'changed_tuple', 'changed_account'])
def test_juku_proof_cas_preserves_newer_or_different_evidence(tmp_path, change):
    with closing(catalog.Cache(tmp_path)) as cache:
        row = seed(cache, stamp=2000.0)[0]
        original = cache.select(row['key'], SPEC['media_key'])
        with cache.db:
            if change == 'newer_success':
                cache.db.execute('UPDATE selections SET checked_at=2001')
            elif change == 'changed_account':
                cache.db.execute('UPDATE selections SET checked_account=?', ('f' * 64,))
            else:
                cache.remember([dict(row, name='Changed.mkv')], SPEC)
        before = dict(cache.db.execute('SELECT * FROM selections').fetchone())
        cache.invalidate_proof(original, SPEC['media_key'])
        assert dict(cache.db.execute('SELECT * FROM selections').fetchone()) == before


def test_busy_juku_invalidation_preserves_typed_failure_and_sets_maintenance_flag(tmp_path):
    with closing(catalog.Cache(tmp_path)) as cache:
        row = seed(cache)[0]
    writer = sqlite3.connect(str(tmp_path / 'catalog.sqlite3'), timeout=0)
    writer.execute('BEGIN IMMEDIATE')
    def fail(*args):
        raise ShareError('share_revoked')
    try:
        with pytest.raises(ShareError) as raised:
            catalog.resolve('am6bjuku://' + row['key'], 'juku:' + row['key'], row['name'], row['size'],
                SPEC['media_key'], state=tmp_path, client=SimpleNamespace(account_scope=SCOPE, resolve=fail))
        assert raised.value.code == 'share_revoked' and raised.value.invalidation_failed is True
        assert raised.value.checked_proof['checked_at'] > 0
    finally:
        writer.rollback()
        writer.close()
    with closing(catalog.Cache(tmp_path)) as cache:
        assert cache.select(row['key'], SPEC['media_key'])['_checked_at'] > 0


def batch_reply(body, denied=()):
    return dict(account=body['account'], denied=[deepcopy(proof) for proof in body['proofs']
                                               if proof['tuple_sha256'] in denied])


def test_batch_is_once_per_cache_at_most_128_and_missing_resident_keeps_cards(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(catalog, '_account_scope', lambda **kwargs: SCOPE)
    def call(action, body, timeout):
        calls.append((action, deepcopy(body), timeout))
        return batch_reply(body)
    monkeypatch.setattr(runtime, 'call', call)
    with closing(catalog.Cache(tmp_path, deadline=time.monotonic() + 10)) as cache:
        rows = seed(cache, 130)
        first = catalog._finish(cache, rows[:129], SPEC)
        final = catalog._finish(cache, rows, SPEC)
        assert len(first) == 129 and len(final) == 130
        assert all(row['_verified'] for row in final)
        assert len(calls) == 1 and calls[0][0] == 'share_known_failures'
        assert len(calls[0][1]['proofs']) == 128 and 0 < calls[0][2] <= .2


def test_batch_denial_affects_only_exact_submitted_old_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, '_account_scope', lambda **kwargs: SCOPE)
    calls = []
    def call(action, body, timeout):
        calls.append(body)
        return batch_reply(body, [body['proofs'][0]['tuple_sha256']])
    monkeypatch.setattr(runtime, 'call', call)
    with closing(catalog.Cache(tmp_path)) as cache:
        rows = seed(cache, 2)
        first = catalog._finish(cache, rows[:1], SPEC)
        assert first[0]['_verified'] is False
        with cache.db:
            cache.db.execute('UPDATE selections SET checked_at=checked_at+1 WHERE key=?', (rows[0]['key'],))
        final = catalog._finish(cache, rows, SPEC)
        assert len(calls) == 1 and len(final) == 2 and all(row['_verified'] for row in final)


@pytest.mark.parametrize('case', ['missing', 'extra', 'duplicate', 'bad_account', 'bad_stamp', 'network'])
def test_invalid_or_unavailable_batch_is_not_negative_evidence(tmp_path, monkeypatch, case):
    monkeypatch.setattr(catalog, '_account_scope', lambda **kwargs: SCOPE)
    def call(action, body, timeout):
        result = batch_reply(body, [body['proofs'][0]['tuple_sha256']])
        if case == 'missing':
            del result['denied'][0]['checked_at']
        elif case == 'extra':
            result['denied'].append(dict(tuple_sha256='f' * 64, checked_at=1))
        elif case == 'duplicate':
            result['denied'] *= 2
        elif case == 'bad_account':
            result['account'] = dict(SCOPE, epoch=3)
        elif case == 'bad_stamp':
            result['denied'][0]['checked_at'] = float('nan')
        else:
            raise OSError('offline fixture')
        return result
    monkeypatch.setattr(runtime, 'call', call)
    with closing(catalog.Cache(tmp_path)) as cache:
        rows = seed(cache)
        result = catalog._finish(cache, rows, SPEC)
        assert len(result) == 1 and result[0]['_verified'] is True
        assert cache.proof_check_done and cache.denied_proofs == {}


def test_batch_timeout_never_exceeds_remaining_search_budget_and_no_retry(tmp_path, monkeypatch):
    calls = []
    def call(action, body, timeout):
        calls.append(timeout)
        raise TimeoutError('offline fixture')
    monkeypatch.setattr(runtime, 'call', call)
    with closing(catalog.Cache(tmp_path)) as cache:
        rows = seed(cache)
        rows[0]['_verified'] = True
        cache.deadline = time.monotonic() + .05
        catalog._known_failures(cache, rows, SPEC, SCOPE)
        catalog._known_failures(cache, rows, SPEC, SCOPE)
        # Binary addition/subtraction at a large monotonic uptime can round
        # 50 ms upward by a few picoseconds; this is not a larger IO budget.
        assert len(calls) == 1 and 0 < calls[0] <= .05 + 1e-9


def test_account_switch_cannot_reuse_old_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, '_account_scope', lambda **kwargs: dict(SCOPE, epoch=3))
    monkeypatch.setattr(runtime, 'call', lambda *args, **kwargs: pytest.fail('No current proof needs a batch'))
    with closing(catalog.Cache(tmp_path)) as cache:
        rows = seed(cache)
        result = catalog._finish(cache, rows, SPEC)
        assert len(result) == 1 and result[0]['_verified'] is False
