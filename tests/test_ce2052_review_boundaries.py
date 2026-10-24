"""CE2051 independent repros plus negative/recall and scoped-retry controls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT/'addons'/addon/'lib'))
from bobbi_core import share_failure as failure
from bobbi_core.candidate_titles import matches
from bobbi_core.source_list_session import SourceListSession


@pytest.mark.parametrize('script,extra', [
    ('review1/probe_tls_handshake_cancel.py', []),
    ('review1/probe_tls_connect_deadline.py', []),
    ('review1/probe_publisher_title_admission.py', []),
    ('review1/probe_initial_unknown_scope.py', []),
    ('review2/probe_juku_optional_write.py', ['--expect', 'fixed', '--include-default-budget']),
    ('review2/repro_retry_scope.py', ['--expect', 'fixed']),
    ('review2/repro_movie_alias_noise.py', ['--expect', 'fixed']),
])
def test_independent_contracts(tmp_path, script, extra):
    output = tmp_path/'result.json'
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'tests/repros/ce2052'/script),
        '--repo', str(ROOT), '--output', str(output), *extra], cwd=ROOT,
        env=dict(os.environ, PYTHONUTF8='1'), capture_output=True, text=True, encoding='utf-8', timeout=45)
    if output.exists() and json.loads(output.read_text(encoding='utf-8')).get('status') == 'INCONCLUSIVE':
        pytest.skip('Real dual-stack accept-queue fixture unavailable: '+run.stdout)
    assert run.returncode == 0, run.stdout+run.stderr


def test_tls_exception_cancel_supersede_deadline_and_reuse():
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'tests/ce2052_tls_lifecycle_probe.py')],
        capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert run.returncode == 0, run.stdout+run.stderr
    assert len(json.loads(run.stdout)['cases']) == 6


@pytest.mark.parametrize('title,aliases,accepted', [
    ('[Group] Orchid (兰花) 2024 1080p', ['Orchid', '兰花'], True),
    ('[Group] 兰花 / Orchid / ラン 10-bit 1080p HEVC', ['兰花', 'Orchid', 'ラン'], True),
    ('Orchid (Director Cut) 2024 1080p', ['Orchid'], True),
    ('Orchid', ['Orchid'], True),  # No year, category or codec required.
    ('1917.2019.1080p.BluRay', ['1917'], True),
    ('2001.A.Space.Odyssey.1968.1080p', ['2001: A Space Odyssey'], True),
    ('Evangelion (1.0) You Are (Not) Alone.2007.1080p', ['Evangelion (1.0) You Are (Not) Alone'], True),
    ('Other Film 2024 1080p (Orchid)', ['Orchid'], False),
    ('Other Film (Orchid) 2024 1080p', ['Orchid'], False),
    ('Other Film / Orchid 2024 1080p', ['Orchid'], False),
    ('Orchid.2024 [Manga EN] (Publisher+)', ['Orchid'], False),
    ('[Manga FR] Orchid.2024 (Publisher+)', ['Orchid'], False),
    ('[Orchid] Other Film.2024.1080p', ['Orchid'], False),
    ('Manga.2024.1080p', ['Manga'], True),
])
def test_movie_prefix_and_explicit_nonvideo(title, aliases, accepted):
    assert matches(title, aliases, 'movies') is accepted


def fixture():
    media = dict(ids=dict(tmdb_id=101), mode='movies', season=1, episode=1)
    identity = dict(locator='am6bqqdocs://A1/1', guid='qqdocs:A1:1',
                    title='Fixture.2024.mkv', size=1000, media='movies:101:0:0')
    source = SimpleNamespace(url=identity['locator'], guid=identity['guid'], title=identity['title'],
        size=1000, indexer='115', type='Direct', shareState={}, shareFailure='', verifiedShareFile=False)
    scope = dict(account_id='fixture-a', epoch=1, authenticated=True)
    session = SourceListSession(media, lambda rows:rows)
    session.publish(session.epoch, '115', [source])
    key = session.key(source)
    session.focus(key, 0)
    selected = session.capture(session.epoch, key)
    return session, selected, identity, scope, key


@pytest.mark.parametrize('transition', ['same', 'renew', 'unavailable', 'switch', 'logout', 'return_a'])
def test_initial_unknown_scoped_failure_and_repeat_transitions(monkeypatch, transition):
    session, source, identity, scope, key = fixture()
    state = failure.resolution_state(identity, scope, 'share_revoked', time.perf_counter_ns())
    assert session.invalidate_share(session.epoch, source, 'share_revoked', state=state)
    session.reopen()
    current = dict(scope)
    if transition == 'unavailable': current = None
    elif transition == 'switch': current.update(account_id='fixture-b', epoch=2)
    elif transition == 'logout': current.update(account_id='', epoch=2, authenticated=False)
    elif transition == 'return_a': current.update(epoch=3)
    calls = []
    def status(**kw):
        assert kw == dict(include_signed_out=True, timeout=.1)
        calls.append(True)
        return current
    monkeypatch.setattr(failure, 'account_scope', status)
    session.status()
    cleared = transition in ('switch', 'logout', 'return_a')
    assert session.inspect(session.epoch, key).shareFailure == ('' if cleared else 'share_revoked')
    assert session.focus_key == key and len(session.entries) == 1
    for _ in range(4): session.status()
    assert len(calls) == 1


def test_foreign_tuple_and_unscoped_string_have_no_new_account_authority():
    session, source, identity, scope, key = fixture()
    assert not session.invalidate_share(session.epoch, source, 'share_revoked')
    foreign = failure.resolution_state(dict(identity, guid='qqdocs:A1:2'), scope,
                                       'share_revoked', time.perf_counter_ns())
    assert not session.invalidate_share(session.epoch, source, 'share_revoked', state=foreign)
    assert session.entries[key].shareFailure == ''


def test_late_old_generation_or_observation_cannot_override_new_state(monkeypatch):
    session, source, identity, scope, key = fixture()
    old = failure.resolution_state(identity, scope, 'share_revoked', time.perf_counter_ns())
    session.invalidate_share(session.epoch, source, 'share_revoked', state=old)
    session.reopen()
    newer_scope = dict(scope, account_id='fixture-b', epoch=2)
    monkeypatch.setattr(failure, 'account_scope', lambda **kw:newer_scope)
    session.status()
    captured = session.capture(session.epoch, key)
    session.invalidate_share(session.epoch, captured, 'share_revoked', state=old)
    assert session.entries[key].shareFailure == ''
    session.reopen()
    fresh = failure.resolution_state(identity, newer_scope, 'identity_changed', time.perf_counter_ns())
    captured = session.capture(session.epoch, key)
    session.invalidate_share(session.epoch, captured, 'identity_changed', state=fresh)
    session.invalidate_share(session.epoch, captured, 'share_revoked', state=dict(fresh, observed=fresh['observed']-1, code='share_revoked'))
    assert session.entries[key].shareFailure == 'identity_changed'
    assert session.focus_key == key


def test_scoped_failure_survives_negative_binding_cache(tmp_path):
    from bobbi_catalog.api import ShareError
    from bobbi_core.share_stream import Binding
    from test_accounts import logged_in
    manager, scope = logged_in(tmp_path/'account')
    _, _, identity, _, _ = fixture()
    calls = []
    def resolve(body, actual_scope):
        assert actual_scope == scope
        calls.append(True)
        raise ShareError('share_revoked', http_status=403, api_code=4100010)
    binding = Binding(dict(identity, request_id='a'*32), resolve, lambda url:True, account=manager, scope=scope)
    receipts = []
    for _ in range(2):
        with pytest.raises(ShareError) as caught: binding.grant()
        receipts.append(failure.failure_value(caught.value))
    assert receipts[0] == receipts[1]
    assert failure.valid_card_state(receipts[0]['share_state'])
    assert receipts[0]['share_state']['tuple'] == failure.tuple_hash(identity)
    assert binding.address is None and calls == [True]


def test_trace_is_opt_in_expiring_bounded_and_omits_secrets(tmp_path, monkeypatch):
    from bobbi_core import search_trace as trace
    monkeypatch.setattr(trace, '_sink', None)
    trace.configure(tmp_path, 'a'*32)
    assert trace._sink is None
    marker = tmp_path/'search-trace.json'
    marker.write_text(json.dumps(dict(expires=time.time()+60, hashes=['f'*40])))
    trace.configure(tmp_path, 'a'*32)
    row = SimpleNamespace(infoHash='f'*40, title='PRIVATE_TITLE', url='https://secret.invalid/?token=secret', type='Torrent')
    trace.observe('rss_parsed', [row])
    trace.observe('rss_parsed', [row])
    text = trace._sink.path.read_text()
    assert len(text.splitlines()) == 1 and 'PRIVATE_TITLE' not in text and 'secret' not in text
    value = json.loads(text)
    assert value['selected'][0]['info_hash'] == 'f'*40 and value['count'] == 1
    trace._sink.expires = time.time()-1
    trace.observe('visible', [row])
    assert trace._sink.path.read_text() == text
