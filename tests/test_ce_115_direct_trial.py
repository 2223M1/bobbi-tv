import importlib.util
import json
from pathlib import Path
import pickle
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ce_115_direct_remote as remote
import ce_115_direct_trial as driver


@pytest.fixture(autouse=True)
def restore_baseline(monkeypatch):
    monkeypatch.setattr(remote, 'BASELINE', dict(remote.BASELINE))


def fixture(tmp_path):
    row = dict(share=dict(code='sabcdefghi', password='abcd'), fid='123456', size=55082330412,
        name='Gattaca.1997.2160p.BluRay.REMUX.HEVC.DTS-HD.MA.TrueHD.7.1.Atmos-FGT.mkv',
        tmdb=782, kind='movie', season=0, episode=0, work_year=1997, origins=[])
    key = remote.digest(remote.encoded([row['share']['code'], row['fid'], row['size'], row['name']]))
    row['key'] = key
    target = dict(request_id='a' * 32, selection_identity='transport:' + remote.digest('am6bjuku://' + key),
                  source_key='b' * 64, title=row['name'], size=row['size'], media='movies:782:0:0', year=1997)
    remote.BASELINE.update({key: target[key] for key in remote.BASELINE})
    path = tmp_path / 'userdata/addon_data/plugin.video.bobbi/juku/catalog.sqlite3'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE selections (key TEXT, media TEXT, payload TEXT)')
    db.execute('INSERT INTO selections VALUES (?,?,?)', (key, target['media'], json.dumps(row)))
    db.commit()
    db.close()
    account = dict(account_id='115:' + 'c' * 64, epoch=7, authenticated=True)
    history = {'jt:lfh': {'test': dict(request_id=target['request_id'], source_title=row['name'],
        mode='movies', ids={'tmdb_id': 782}, _share=dict(locator='am6bjuku://' + key, guid='juku:' + key,
        title=row['name'], size=row['size'], media=target['media'], account=account))}}
    (path.parent.parent / 'database.pickle').write_bytes(pickle.dumps(history))
    return target, row, account, path


def test_inspect_exact_retained_file_and_account_without_writes(tmp_path):
    target, row, account, path = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = remote.inspect(tmp_path, target, lambda: account)
    assert result['state'] == 'validated' and result['size'] == 55082330412
    assert result['fid_sha256'] == remote.digest(row['fid'])
    assert result['history']['exact_request'] and not result['playback_performed']
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    output = json.dumps(result)
    assert row['fid'] not in output and row['share']['code'] not in output and 'abcd' not in output


@pytest.mark.parametrize('field,value', [('fid','999'), ('size',55082330411), ('name','other.mkv'),
    ('tmdb',1782), ('work_year',1998)])
def test_same_title_cannot_rescue_tuple_mismatch(tmp_path, field, value):
    target, row, account, path = fixture(tmp_path)
    row[field] = value
    with sqlite3.connect(path) as db:
        db.execute('UPDATE selections SET payload=?', (json.dumps(row),))
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        remote.inspect(tmp_path, target, lambda: account)


def test_history_request_is_required_not_any_same_title(tmp_path):
    target, row, account, path = fixture(tmp_path)
    target['request_id'] = 'f' * 32
    remote.BASELINE['request_id'] = target['request_id']
    with pytest.raises(remote.DiagnosticError, match='HISTORY_MISMATCH'):
        remote.inspect(tmp_path, target, lambda: account)


def test_account_replacement_invalidates_inspection(tmp_path):
    target, row, account, path = fixture(tmp_path)
    replies = iter([account, dict(account, epoch=8)])
    with pytest.raises(remote.DiagnosticError, match='ACCOUNT_CHANGED'):
        remote.inspect(tmp_path, target, lambda: next(replies))


def test_restricted_history_never_executes_globals():
    class Dangerous:
        def __reduce__(self):
            return (eval, ('1+1',))
    with pytest.raises(remote.DiagnosticError, match='HISTORY_INVALID'):
        remote.primitive_history(pickle.dumps({'jt:lfh': Dangerous()}))
    value = []
    value.append(value)
    with pytest.raises(remote.DiagnosticError, match='HISTORY_INVALID'):
        remote.primitive_history(pickle.dumps({'jt:lfh': {'cycle': value}}))


def test_timeout_has_exclusive_unconfirmed_receipt_and_no_dispatch_retry(tmp_path):
    target, _, _, _ = fixture(tmp_path)
    output, calls = tmp_path / 'receipt.json', []
    def sender(source, code):
        calls.append(code)
        assert json.loads(output.read_text())['state'] == 'unconfirmed'
        raise TimeoutError('https://secret.example/?Cookie=private')
    result = driver.execute_inspect(tmp_path, output, target, sender)
    assert len(calls) == 1 and result['state'] == 'unconfirmed'
    assert 'secret' not in output.read_text() and not result['retry_allowed']
    with pytest.raises(FileExistsError):
        driver.execute_inspect(tmp_path, output, target, sender)
    assert len(calls) == 1


def test_baseline_is_actual_retained_attempt_three():
    target = driver.target_from_baseline(ROOT / 'tests/fixtures/playback/selection_initial.json')
    assert target['request_id'] == '0ed3043bc7424b159264ad87fe64504d'
    assert target['selection_identity'].endswith('939b30906b7f9f8490cf3509ded1d4fe28c4659e9ff707ebd8dfa6decef8042e')


def test_unreviewed_baseline_identity_is_rejected(tmp_path):
    target, _, _, _ = fixture(tmp_path)
    for field in remote.BASELINE:
        with pytest.raises(remote.DiagnosticError, match='TARGET_INVALID'):
            remote.checked_target(dict(target, **{field: 'f' * 64}))


def test_wal_database_refused_without_creating_sidecars(tmp_path):
    path = tmp_path / 'wal.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE example (x)')
    db.close()
    before = {p.name for p in tmp_path.iterdir()}
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        remote.readonly(path)
    assert {p.name for p in tmp_path.iterdir()} == before


def test_wal_switch_between_precheck_and_connect_fails_without_sidecars(tmp_path, monkeypatch):
    path = tmp_path / 'race.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE example (x)')
    db.close()
    connect = sqlite3.connect
    def racing_connect(*args, **kwargs):
        with connect(path) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
        writer.close()
        return connect(*args, **kwargs)
    monkeypatch.setattr(remote.sqlite3, 'connect', racing_connect)
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        remote.readonly(path)
    assert {p.name for p in tmp_path.iterdir()} == {'race.sqlite3'}


def test_database_change_during_query_rejected_at_close(tmp_path):
    path = tmp_path / 'changed.sqlite3'
    with sqlite3.connect(path) as writer:
        writer.execute('CREATE TABLE example (x)')
    writer.close()
    reader = remote.readonly(path)
    assert reader.execute('SELECT * FROM example').fetchall() == []
    with sqlite3.connect(path) as writer:
        writer.execute('INSERT INTO example VALUES (1)')
    writer.close()
    with pytest.raises(remote.DiagnosticError, match='TUPLE_MISMATCH'):
        reader.close()
    with pytest.raises(sqlite3.ProgrammingError):
        reader.execute('SELECT * FROM example')
