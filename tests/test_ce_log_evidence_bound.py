"""Diagnostic transport limits must not erase startup evidence silently."""
import ast
import json
from pathlib import Path


def bounded():
    module = ast.parse((Path(__file__).parents[1] / 'tools/ce_playback_log_probe.py').read_text(encoding='utf-8'))
    remote = next(ast.literal_eval(n.value) for n in module.body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REMOTE' for t in n.targets))
    node = next(n for n in ast.parse(remote).body if isinstance(n, ast.FunctionDef) and n.name == 'bounded_evidence')
    scope = {'json': json}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual-diagnostic-bound>', 'exec'), scope)
    return scope['bounded_evidence']


def test_large_utf8_logs_keep_boundaries_and_report_loss():
    lines = ['START'] + ['字幕' * 300] * 450 + ['END']
    observations = [{'event': 'first'}] + [{'text': 'trace' * 100}] * 250 + [{'event': 'last'}]
    raw = bounded()(dict(lines=lines, share_observations=observations))
    value = json.loads(raw)
    assert len(raw.encode('utf-8')) <= 120 * 1024
    assert value['lines'][0] == 'START' and value['lines'][-1] == 'END'
    assert value['share_observations'][0] == {'event': 'first'}
    assert value['share_observations'][-1] == {'event': 'last'}
    for key in ('lines', 'share_observations'):
        assert value['truncation']['dropped'][key] > 0
        assert len(value[key]) + value['truncation']['dropped'][key] == value['truncation']['original_counts'][key]


def test_small_log_not_truncated():
    value = json.loads(bounded()(dict(lines=['start', 'end'], share_observations=[])))
    assert value['lines'] == ['start', 'end']
    assert value['truncation']['dropped'] == dict(lines=0, share_observations=0)
