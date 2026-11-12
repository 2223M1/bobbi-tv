"""Explicit receipt-bound diagnostic targets; no device or media network I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pickle
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import ce_115_direct_remote as remote
import ce_115_direct_trial as trial
import ce_115_direct_start as start
import ce_115_direct_kodi as kodi
from test_ce_115_direct_start import FakeRuntime, REQUEST


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, 'profile_status', lambda: dict(label='Fixture'))
    row = dict(share=dict(code='sabcdefghi', password='abcd'), fid='123456', size=6142048451,
        name='Legend.of.the.Galactic.Heroes.S01E01.1988.1080i.BluRay.Remux.AVC.TrueHD.5.1-ADE.mkv',
        tmdb=27660, kind='tv', season=1, episode=1, work_year=1988, origins=[])
    row['spec'] = dict(mode='tv', tmdb_id=27660, season=1, episode=1, year=1988,
                       media_key='tv:27660:1:1', years=[1988])
    row['key'] = remote.digest(remote.encoded([row['share']['code'], row['fid'], row['size'], row['name']]))
    locator = 'am6bjuku://' + row['key']
    receipt = dict(operation='select', work='galactic_heroes', attempt=1, regression_attempt=False,
        transport_exit_code=0, result=dict(operation='select', name='galactic_heroes', selected=True,
            record=dict(request_id='a' * 32, selection_identity='transport:' + remote.digest(locator),
                test=dict(title='Legend of the Galactic Heroes', tmdb_id=27660, kind='tv', year=1988,
                          season=1, episode=1, animation=True),
                launch_mode='ordinary_ui', ordinary_ui=True, picker_mode=True,
                selected_card={'Container(1000).ListItem.Label': row['name'],
                    'Container(1000).ListItem.Property(source_key)': 'b' * 64,
                    'Container(1000).ListItem.Property(size)': '5.72 GB'})))
    baseline = tmp_path / 'ordinary-select.json'
    baseline.write_text(json.dumps(receipt), encoding='utf-8')
    target = trial.target_from_baseline(baseline, version=2)
    profile = tmp_path / 'userdata/addon_data/plugin.video.bobbi'
    database = profile / 'source-libraries' / remote.digest('https://example.invalid') / 'catalog.sqlite3'
    database.parent.mkdir(parents=True)
    (tmp_path / 'userdata/profiles.xml').write_text(
        '<profiles><profile><name>Fixture</name><directory>special://masterprofile/</directory></profile></profiles>')
    source_config = profile / 'source-library.json'
    source_config.write_text(json.dumps(dict(schema=1, endpoint='https://example.invalid', generation='1' * 32)))
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE selections (key TEXT, media TEXT, payload TEXT)')
        db.execute('INSERT INTO selections VALUES(?,?,?)', (row['key'], target['media'], json.dumps(row)))
    db.close()
    account = dict(account_id='115:' + 'c' * 64, epoch=7, authenticated=True)
    history = {'jt:lfh': {'test': dict(request_id=target['request_id'], source_title=row['name'],
        mode='tv', tv_data=dict(season=1, episode=1), ids=dict(tmdb_id=27660),
        _share=dict(locator=locator, guid='juku:' + row['key'], title=row['name'], size=row['size'],
                    media=target['media'], account=account))}}
    history_path = profile / 'database.pickle'
    history_path.write_bytes(pickle.dumps(history))
    return dict(root=tmp_path, target=target, row=row, account=account, database=database,
                history=history, history_path=history_path, baseline=baseline, receipt=receipt,
                source_config=source_config)


def inspection(evidence):
    return remote.inspect(evidence['root'], evidence['target'], lambda: evidence['account'])


def test_v2_receipt_pins_hash_not_display_size_and_v1_still_rejects_other_media(evidence):
    target = evidence['target']
    assert target['size'] is None and target['media'] == 'tv:27660:1:1'
    assert target['baseline_sha256'] == hashlib.sha256(evidence['baseline'].read_bytes()).hexdigest()
    with pytest.raises(remote.DiagnosticError, match='TARGET_INVALID'):
        trial.target_from_baseline(evidence['baseline'])
    before = {str(path): path.read_bytes() for path in evidence['root'].rglob('*') if path.is_file()}
    proof = inspection(evidence)
    assert proof['size'] == 6142048451 and proof['size_evidence'] == 'retained_tuple_and_exact_history'
    assert proof['baseline_sha256'] == target['baseline_sha256']
    assert start.checked_inspection(proof, target) == proof
    assert before == {str(path): path.read_bytes() for path in evidence['root'].rglob('*') if path.is_file()}
    assert all(secret not in json.dumps(proof) for secret in ('sabcdefghi', 'abcd', '123456', 'am6bjuku://'))


@pytest.mark.parametrize('field,value', [('season', 2), ('episode', 2), ('tmdb', 42),
                                        ('kind', 'movie'), ('spec', None), ('size', '6142048451')])
def test_v2_catalog_metadata_mismatch_is_not_rescued_by_title(evidence, field, value):
    row = dict(evidence['row'], **{field: value})
    with sqlite3.connect(evidence['database']) as db:
        db.execute('UPDATE selections SET payload=?', (json.dumps(row),))
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        inspection(evidence)


@pytest.mark.parametrize('change', ['request', 'size', 'season', 'episode', 'media', 'tmdb', 'account'])
def test_v2_history_is_independent_exact_request_file_episode_and_epoch_proof(evidence, change):
    history = evidence['history']
    item = history['jt:lfh']['test']
    if change == 'request':
        item['request_id'] = 'd' * 32
    elif change == 'size':
        item['_share']['size'] -= 1  # Same rounded UI size still does not match.
    elif change in ('season', 'episode'):
        item['tv_data'][change] = 2
    elif change == 'media':
        item['_share']['media'] = 'tv:27660:1:2'
    elif change == 'tmdb':
        item['ids']['tmdb_id'] = 42
    elif change == 'account':
        item['_share']['account'] = dict(evidence['account'], epoch=8)
    evidence['history_path'].write_bytes(pickle.dumps(history))
    with pytest.raises(remote.DiagnosticError, match='ACCOUNT_CHANGED' if change == 'account' else 'HISTORY_MISMATCH'):
        inspection(evidence)


@pytest.mark.parametrize('field,value', [('baseline_sha256', 'd' * 64), ('size', None), ('size', True),
    ('size_evidence', 'card'), ('history', {'exact_request': True}), ('schema', 1)])
def test_v2_start_rejects_unbound_or_nonexact_inspection(evidence, field, value):
    proof = dict(inspection(evidence), **{field: value})
    with pytest.raises(remote.DiagnosticError, match='INSPECT_CHANGED'):
        start.checked_inspection(proof, evidence['target'])


def test_any_changed_baseline_bytes_require_fresh_inspection(evidence):
    proof = inspection(evidence)
    evidence['baseline'].write_bytes(evidence['baseline'].read_bytes() + b'\n')
    changed = trial.target_from_baseline(evidence['baseline'], version=2)
    with pytest.raises(remote.DiagnosticError, match='INSPECT_CHANGED'):
        start.checked_inspection(proof, changed)


def test_v2_tv_year_is_bound_to_retained_spec_not_unrelated_release_year(evidence):
    row = dict(evidence['row'], work_year=1989)
    with sqlite3.connect(evidence['database']) as db:
        db.execute('UPDATE selections SET payload=?', (json.dumps(row),))
    assert inspection(evidence)['state'] == 'validated'
    row['spec']['year'] = 1989
    with sqlite3.connect(evidence['database']) as db:
        db.execute('UPDATE selections SET payload=?', (json.dumps(row),))
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        inspection(evidence)


def test_v2_movie_alternative_year_requires_retained_evidenced_years():
    target = dict(schema=2, media='movies:782:0:0', year=1997)
    row = dict(tmdb=782, kind='movie', season=0, episode=0, work_year=1998,
        spec=dict(tmdb_id=782, mode='movies', season=0, episode=0,
                  media_key='movies:782:0:0', year=1997, years=[1997, 1998]))
    remote.retained_context(row, target)
    row['spec']['years'] = [1997]
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        remote.retained_context(row, target)


def test_remote_inspect_rejection_preserves_safe_target_provenance(evidence, monkeypatch):
    def rejected(*args):
        raise remote.DiagnosticError('HISTORY_MISMATCH')
    monkeypatch.setattr(remote, 'inspect', rejected)
    result = remote.remote_entry(dict(operation='inspect', target=evidence['target']))
    assert result['state'] == 'not_validated' and result['error'] == 'HISTORY_MISMATCH'
    assert all(result[key] == value for key, value in remote.target_evidence(evidence['target']).items())


def test_collected_v2_result_cannot_substitute_other_baseline_even_with_same_run_id(evidence):
    receipt = dict(run_id='c' * 32, request_id=REQUEST, route='direct',
                   **remote.target_evidence(dict(evidence['target'], size=evidence['row']['size'])))
    result = dict(receipt, diagnostic_only=True, product_proof=False)
    raw = json.dumps(result).encode()
    descriptor = dict(artifact='/tmp/bobbi-115-direct-' + receipt['run_id'] + '/result.json',
        bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    assert start.decode_result(raw, descriptor, receipt) == result
    result['baseline_sha256'] = 'f' * 64
    raw = json.dumps(result).encode()
    descriptor.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(remote.DiagnosticError, match='DIAGNOSTIC_SCOPE'):
        start.decode_result(raw, descriptor, receipt)


class ExactRuntime(FakeRuntime):
    def __init__(self, evidence):
        super().__init__()
        self.evidence, self.scope = evidence, deepcopy(evidence['account'])
    def inspect(self, target):
        self.calls.append('inspect')
        return remote.inspect(self.evidence['root'], target, self.account)
    def tuple(self, target):
        return remote.retained_tuple(self.evidence['root'], target)
    def require_catalog_scope(self, expected):
        remote.require(remote.catalog_scope(self.evidence['root']) == expected, 'STATE_CHANGED')
    def resolve_sharestream(self, row, account):
        self.calls.append('resolve_sharestream')
        assert row['size'] == self.evidence['row']['size'] and account == self.scope
        return 'http://127.0.0.1:9999/opaque-diagnostic'


@pytest.mark.parametrize('route', ['direct', 'sharestream-open-range',
    'sharestream-open-range-microbatch', 'sharestream-open-range-bound-guard'])
def test_all_comparison_routes_use_same_pinned_file_and_one_opener(evidence, route):
    runtime = ExactRuntime(evidence)
    proof = inspection(evidence)
    target = dict(evidence['target'], size=proof['size'])
    record = dict(request_id=REQUEST, route=route)
    kodi.perform_start(runtime, proof, target, record)
    assert runtime.calls.count('select') == runtime.calls.count('bind') == 1
    assert len([call for call in runtime.calls if isinstance(call, tuple) and call[0] == 'play']) == 1
    assert record['size'] == proof['size'] and record['media'] == target['media']
    assert record['baseline_sha256'] == target['baseline_sha256']
    assert record['tuple_sha256'] == proof['tuple_sha256']
    assert record['baseline_request'] != record['request_id']


def test_v2_kodi_entry_cannot_rediscover_unpinned_size_at_start(evidence):
    runtime = ExactRuntime(evidence)
    with pytest.raises(remote.DiagnosticError, match='INSPECT_CHANGED'):
        kodi.perform_start(runtime, inspection(evidence), evidence['target'], dict(request_id=REQUEST))
    assert not runtime.calls


def test_v2_fresh_history_and_current_epoch_checked_before_resolving(evidence):
    proof = inspection(evidence)
    runtime = ExactRuntime(evidence)
    runtime.scope['epoch'] += 1
    with pytest.raises(remote.DiagnosticError, match='ACCOUNT_CHANGED'):
        kodi.perform_start(runtime, proof, dict(evidence['target'], size=proof['size']), dict(request_id=REQUEST))
    assert runtime.calls == ['inspect']


def test_cli_target_v2_passes_only_inspected_exact_size_to_one_start(evidence, monkeypatch, tmp_path):
    proof_path, output = tmp_path / 'inspect.json', tmp_path / 'start.json'
    proof_path.write_text(json.dumps(inspection(evidence)), encoding='utf-8')
    calls = []
    monkeypatch.setattr(sys, 'argv', ['ce_115_direct_start.py', 'start', '--transport-source', str(tmp_path),
        '--baseline', str(evidence['baseline']), '--target-version', '2', '--inspect', str(proof_path),
        '--output', str(output), '--attended', '--route', 'sharestream-open-range-bound-guard'])
    monkeypatch.setattr(start, 'run_once', lambda source, output, parameters: calls.append(parameters) or dict(state='launched'))
    assert start.main() == 0 and len(calls) == 1
    assert calls[0]['target']['size'] == 6142048451
    assert calls[0]['route'] == 'sharestream-open-range-bound-guard'


def test_current_endpoint_scope_is_pinned_without_names_or_endpoints(evidence):
    proof = inspection(evidence)
    assert proof['catalog_scope']['endpoint_sha256'] == remote.digest('https://example.invalid')
    assert proof['catalog_scope']['source_generation_sha256'] == remote.digest('1' * 32)
    assert 'example.invalid' not in json.dumps(proof) and 'Fixture' not in json.dumps(proof)


@pytest.mark.parametrize('location', ['legacy', 'old_endpoint'])
def test_exact_file_in_noncurrent_cache_is_never_borrowed(evidence, location):
    profile = evidence['source_config'].parent
    destination = (profile / 'juku/catalog.sqlite3' if location == 'legacy'
                   else profile / 'source-libraries' / remote.digest('https://old.invalid') / 'catalog.sqlite3')
    destination.parent.mkdir(parents=True)
    evidence['database'].rename(destination)
    before = {path: path.read_bytes() for path in profile.rglob('*') if path.is_file()}
    with pytest.raises(remote.DiagnosticError, match='CATALOG_NOT_UNIQUE'):
        inspection(evidence)
    assert before == {path: path.read_bytes() for path in profile.rglob('*') if path.is_file()}


def test_no_source_config_cannot_revive_legacy_cache(evidence):
    destination = evidence['source_config'].parent / 'juku/catalog.sqlite3'
    destination.parent.mkdir()
    evidence['database'].rename(destination)
    evidence['source_config'].unlink()
    with pytest.raises(remote.DiagnosticError, match='STATE_CHANGED'):
        inspection(evidence)


def change_source(evidence):
    value = json.loads(evidence['source_config'].read_text())
    value['generation'] = '2' * 32
    evidence['source_config'].write_text(json.dumps(value))


def profile_switcher(evidence, monkeypatch):
    state = {'label': 'Fixture'}
    (evidence['root'] / 'userdata/profiles.xml').write_text('<profiles>'
        '<profile><name>Fixture</name><directory>special://masterprofile/</directory></profile>'
        '<profile><name>Other</name><directory>profiles/other</directory></profile></profiles>')
    monkeypatch.setattr(remote, 'profile_status', lambda: dict(state))
    return lambda: state.update(label='Other')


@pytest.mark.parametrize('change', ['source', 'profile'])
def test_inspect_rejects_source_or_profile_change_during_history(evidence, monkeypatch, change):
    mutate = (lambda: change_source(evidence)) if change == 'source' else profile_switcher(evidence, monkeypatch)
    original = remote.history_proof
    def racing_history(*args):
        result = original(*args)
        mutate()
        return result
    monkeypatch.setattr(remote, 'history_proof', racing_history)
    with pytest.raises(remote.DiagnosticError, match='STATE_CHANGED'):
        inspection(evidence)


@pytest.mark.parametrize('change', ['source', 'profile'])
@pytest.mark.parametrize('stage', ['after_resolve', 'after_select', 'after_bind'])
def test_scope_change_at_admission_stages_never_opens(evidence, monkeypatch, change, stage):
    mutate = (lambda: change_source(evidence)) if change == 'source' else profile_switcher(evidence, monkeypatch)
    proof = inspection(evidence)
    runtime = ExactRuntime(evidence)
    setattr(runtime, stage, mutate)
    with pytest.raises(remote.DiagnosticError, match='STATE_CHANGED'):
        kodi.perform_start(runtime, proof, dict(evidence['target'], size=proof['size']), dict(request_id=REQUEST))
    assert not any(type(call) is tuple and call[0] == 'play' for call in runtime.calls)
    if stage == 'after_resolve':
        assert 'select' not in runtime.calls
    elif stage == 'after_select':
        assert 'bind' not in runtime.calls


def test_changed_generation_with_identical_file_requires_new_inspection(evidence):
    proof = inspection(evidence)
    change_source(evidence)
    runtime = ExactRuntime(evidence)
    with pytest.raises(remote.DiagnosticError, match='INSPECT_CHANGED'):
        kodi.perform_start(runtime, proof, dict(evidence['target'], size=proof['size']), dict(request_id=REQUEST))
    assert runtime.calls == ['inspect']


@pytest.mark.parametrize('missing', [True, False])
def test_start_rejects_unbound_catalog_scope(evidence, missing):
    proof = inspection(evidence)
    if missing:
        proof.pop('catalog_scope')
    else:
        proof['catalog_scope']['endpoint_sha256'] = 'not-a-hash'
    with pytest.raises(remote.DiagnosticError, match='INSPECT_CHANGED'):
        start.checked_inspection(proof, evidence['target'])


@pytest.mark.parametrize('enabled', [0, 1])
def test_qqdocs_share_status_does_not_shadow_profile_callback(evidence, monkeypatch, enabled):
    root, row = evidence['root'], dict(evidence['row'], cell='A1')
    locator = 'am6bqqdocs://A1/' + row['fid']
    target = dict(evidence['target'], selection_identity='transport:' + remote.digest(locator))
    cache = root / 'userdata/addon_data/script.module.bobbi.catalog/cache.sqlite3'
    cache.parent.mkdir(parents=True)
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE selections (key TEXT, media TEXT, payload TEXT)')
        db.execute('INSERT INTO selections VALUES (?,?,?)',
                   ('qqdocs:A1:' + row['fid'] + ':' + target['media'], target['media'], json.dumps(row)))
    db.close()
    catalog = root / 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'
    catalog.parent.mkdir(parents=True)
    with sqlite3.connect(catalog) as db:
        db.execute('CREATE TABLE shares (cell TEXT, code TEXT, password TEXT)')
        db.execute('INSERT INTO shares VALUES (?,?,?)', ('A1', row['share']['code'], row['share']['password']))
        db.execute('CREATE TABLE share_status (cell TEXT, enabled INTEGER)')
        db.execute('INSERT INTO share_status VALUES (?,?)', ('A1', enabled))
    db.close()
    monkeypatch.setattr(remote, 'profile_status', lambda: pytest.fail('Explicit callback must stay bound'))
    callback = lambda: dict(label='Fixture')
    if not enabled:
        with pytest.raises(remote.DiagnosticError, match='SHARE_REVOKED'):
            remote.retained_tuple(root, target, status=callback)
    else:
        selected = remote.retained_tuple(root, target, status=callback)
        assert selected['provider'] == 'qqdocs' and selected['locator'] == locator
