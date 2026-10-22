"""Explicit later UI receipts retain the release and exact history/account gates."""
from copy import deepcopy
import json
from pathlib import Path
import pickle
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ce_115_direct_remote as remote
import ce_115_direct_trial as driver
from test_ce_115_direct_trial import fixture as retained_fixture


LATER_BASELINE = ROOT / 'review-evidence/ce-new-work-gattaca-select-1792613222684877200.json'
LATER_REQUEST = '9c83ef02df784463a97b03f7f4b2f946'


@pytest.fixture(autouse=True)
def preserve_release_pins(monkeypatch):
    monkeypatch.setattr(remote, 'BASELINE', dict(remote.BASELINE))


def receipt():
    """Only selection evidence is needed; no playback trace or URLs are copied."""
    value = json.loads(LATER_BASELINE.read_text(encoding='utf-8'))
    result = value['result']
    record = result['record']
    return dict(operation=value['operation'], work=value['work'], attempt=value['attempt'],
        regression_attempt=value['regression_attempt'], transport_exit_code=value['transport_exit_code'],
        result=dict(operation=result['operation'], name=result['name'], selected=result['selected'],
            record={key: record[key] for key in ('request_id', 'selection_identity', 'selected_card',
                                              'test', 'launch_mode', 'ordinary_ui', 'picker_mode')}))


def target_from(tmp_path, value):
    path = tmp_path / 'explicit-baseline.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return driver.target_from_baseline(path)


def test_actual_attempt_six_uses_its_explicit_request_and_same_release_pins():
    target = driver.target_from_baseline(LATER_BASELINE)
    assert target['request_id'] == LATER_REQUEST != remote.BASELINE['request_id']
    assert target['selection_identity'] == remote.BASELINE['selection_identity']
    assert target['source_key'] == remote.BASELINE['source_key']
    assert target['size'] == 55082330412 and target['media'] == 'movies:782:0:0'
    assert target['year'] == 1997


@pytest.mark.parametrize('attempt', [3, 4, 6, 9])
def test_explicit_ordinary_attempt_at_or_after_three_is_accepted(tmp_path, attempt):
    value = receipt()
    value['attempt'] = attempt
    assert target_from(tmp_path, value)['request_id'] == LATER_REQUEST


@pytest.mark.parametrize('attempt', [None, True, False, 0, 1, 2, -1, 3.0, '6'])
def test_attempt_must_be_an_integer_at_or_after_three(tmp_path, attempt):
    value = receipt()
    value['attempt'] = attempt
    with pytest.raises(remote.DiagnosticError, match='TARGET_INVALID'):
        target_from(tmp_path, value)


@pytest.mark.parametrize('field,value', [
    ('request_id', 'f' * 31), ('request_id', 'F' * 32), ('request_id', int('1' * 32)),
    ('selection_identity', 'transport:' + 'f' * 64), ('source_key', 'f' * 64),
    ('title', 'Gattaca.1997.other.mkv'), ('size', 55082330411), ('size', 55082330412.0),
    ('media', 'movies:783:0:0'), ('year', 1998),
])
def test_later_request_does_not_relax_target_shape_or_release_pins(field, value):
    target = driver.target_from_baseline(LATER_BASELINE)
    target[field] = value
    with pytest.raises(remote.DiagnosticError, match='TARGET_INVALID'):
        remote.checked_target(target)


@pytest.mark.parametrize('field,value', [
    ('launch_mode', 'diagnostic'), ('ordinary_ui', False), ('picker_mode', False),
    ('selection_identity', 'transport:' + 'f' * 64),
])
def test_later_baseline_still_requires_ordinary_selection_evidence(tmp_path, field, value):
    evidence = receipt()
    evidence['result']['record'][field] = value
    with pytest.raises(remote.DiagnosticError, match='TARGET_INVALID'):
        target_from(tmp_path, evidence)


def history_file(catalog):
    return catalog.parent.parent / 'database.pickle'


def test_new_request_rejects_old_history_and_accepts_only_matching_history(tmp_path):
    target, _, account, catalog = retained_fixture(tmp_path)
    target['request_id'] = LATER_REQUEST
    assert remote.checked_target(target) == target
    path = history_file(catalog)
    original = path.read_bytes()
    with pytest.raises(remote.DiagnosticError, match='HISTORY_MISMATCH'):
        remote.inspect(tmp_path, target, lambda: account)
    assert path.read_bytes() == original
    history = pickle.loads(original)
    history['jt:lfh']['test']['request_id'] = LATER_REQUEST
    path.write_bytes(pickle.dumps(history))
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = remote.inspect(tmp_path, target, lambda: account)
    assert result['baseline_request'] == LATER_REQUEST and result['state'] == 'validated'
    assert result['history'] == dict(exact_request=True, exact_pointer=True, same_account_epoch=True)
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('mismatch', ['locator', 'guid', 'title', 'size', 'media', 'account', 'duplicate'])
def test_matching_later_request_still_rejects_history_tuple_account_or_ambiguity(tmp_path, mismatch):
    target, _, account, catalog = retained_fixture(tmp_path)
    target['request_id'] = LATER_REQUEST
    path = history_file(catalog)
    history = pickle.loads(path.read_bytes())
    item = history['jt:lfh']['test']
    item['request_id'] = LATER_REQUEST
    if mismatch == 'duplicate':
        history['jt:lfh']['duplicate'] = deepcopy(item)
    elif mismatch == 'account':
        item['_share']['account'] = dict(account, epoch=account['epoch'] + 1)
    elif mismatch == 'size':
        item['_share']['size'] -= 1
    else:
        item['_share'][mismatch] = 'different'
    path.write_bytes(pickle.dumps(history))
    expected = 'ACCOUNT_CHANGED' if mismatch == 'account' else 'HISTORY_MISMATCH'
    with pytest.raises(remote.DiagnosticError, match=expected):
        remote.inspect(tmp_path, target, lambda: account)
