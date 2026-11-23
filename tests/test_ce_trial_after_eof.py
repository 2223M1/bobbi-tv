"""A test driver may proceed after proven EOF, never an unfinished selection."""
import ast
from copy import deepcopy
from pathlib import Path
import pytest

tree = ast.parse((Path(__file__).parents[1] / 'tools/ce_trial_remote.py').read_text(encoding='utf-8'))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'can_start_trial')
scope = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), '<real-trial-start-guard>', 'exec'), scope)
can_start = scope['can_start_trial']


def ended():
    return dict(epoch=3, observed=None,
        desired=dict(request_id='a'*32, epoch=3, file_identity='exact-a', file_bound=True,
                     start_claimed=True, cancelled=False),
        terminal=dict(reason='NATURAL_EOF', consumed=False, av_started=True, error=False,
                      request_id='a'*32, epoch=3, native_instance='one', file_identity='exact-a'))


def test_proven_unconsumed_natural_eof_allows_a_new_manual_trial():
    row = ended()
    before = deepcopy(row)
    assert can_start(row)
    assert row == before


@pytest.mark.parametrize('key,value', [('consumed',True),('av_started',False),('error',True),
    ('reason','STOP'),('reason','ERROR'),('request_id','b'*32),('epoch',2),
    ('file_identity','other'),('native_instance','')])
def test_terminal_must_still_prove_the_exact_finished_selection(key,value):
    row = ended()
    row['terminal'][key] = value
    assert not can_start(row)


def test_no_terminal_or_new_pending_selection_is_not_idle():
    row = ended()
    row['terminal'] = None
    assert not can_start(row)
    row = ended()
    row['desired']['request_id'] = 'b'*32
    assert not can_start(row)
    row = ended()
    row['observed'] = {'request_id':'other'}
    assert not can_start(row)


def test_existing_empty_or_cancelled_states_remain_valid():
    assert can_start({'desired':None})
    assert can_start({'desired':{'cancelled':True}})


def test_real_picker_guard_reuses_the_same_terminal_proof():
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'assert_picker_idle')
    state = ended()
    calls = []
    env = dict(can_start_trial=can_start, snapshot=lambda: deepcopy(state),
               rpc=lambda method: calls.append(method) or [])
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<real-picker-idle>', 'exec'), env)
    env['assert_picker_idle']({'prior_request':'a'*32})
    assert calls == ['Player.GetActivePlayers']
    with pytest.raises(AssertionError, match='USER_CHANGED_SELECTION'):
        env['assert_picker_idle']({'prior_request':'b'*32})
    state['terminal']['consumed'] = True
    with pytest.raises(AssertionError, match='UNEXPECTED_SELECTION'):
        env['assert_picker_idle']({'prior_request':'a'*32})
