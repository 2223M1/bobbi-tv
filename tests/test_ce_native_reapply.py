"""Execute the native maintainer's real branch locally; no SSH/systemctl."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ce_native_tool', ROOT / 'tools/ce_native_update.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def harness(tmp_path, monkeypatch):
    base = tmp_path / 'native'
    base.mkdir()
    old_conf, new_conf, old_binary, new_binary, old_launcher = b'old conf', b'new conf', b'old binary', b'new binary', b'old launcher'
    def digest(data):
        return hashlib.sha256(data).hexdigest()
    for name, value in {'previous.conf': old_conf, 'next.conf': new_conf, 'kodi.bin': new_binary}.items():
        (base / name).write_bytes(value)
    conf = tmp_path / 'kodi.conf'
    conf.write_bytes(old_conf)
    oldbin, oldlaunch, generation = tmp_path / 'old.bin', tmp_path / 'old.py', tmp_path / 'state.json'
    oldbin.write_bytes(old_binary)
    oldlaunch.write_bytes(old_launcher)
    generation.write_text(json.dumps({'sequence': 2026101909}))
    pins = dict(old_conf_sha256=digest(old_conf), new_conf_sha256=digest(new_conf),
                old_sha256=digest(old_binary), new_sha256=digest(new_binary))
    receipt = base / 'receipt.json'
    receipt.write_text(json.dumps(dict(pins, state='rolled_back', recovered=True,
        history=[dict(pins, state='applied', recorded_at=1)])))
    aliases = {'/storage/.am6b-repair284/native/kodi.bin': oldbin,
               '/storage/.am6b-repair284/native/launch.py': oldlaunch,
               '/storage/.local/share/bobbi-private-updates/state.json': generation}
    tree = ast.parse(tool.REMOTE)
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name in ('sha', 'atomic', 'checked_record', 'transition')]
    branch = next(node for node in tree.body if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "MODE == 'status'")
    namespace = dict(hashlib=hashlib, json=json, os=os, tempfile=tempfile, time=time,
                     pathlib=SimpleNamespace(Path=lambda path: aliases.get(str(path), Path(path))),
                     base=base, conf=conf, receipt=receipt, MODE='reapply',
                     OLD=pins['old_sha256'], OLD_CONF=pins['old_conf_sha256'], OLD_LAUNCH=digest(old_launcher),
                     HASHES={'next.conf': pins['new_conf_sha256'], 'kodi.bin': pins['new_sha256']}, out={})
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<native-functions>', 'exec'), namespace)
    calls, state = [], {'players': [], 'fail_start_once': False, 'pin_known': True}
    def command(*args):
        calls.append(args)
        if args[:2] == ('systemctl', 'start') and state['fail_start_once']:
            state['fail_start_once'] = False
            raise RuntimeError('injected restart failure')
        return ''
    def rpc(*args):
        if state['players'] is None:
            raise OSError('offline')
        return state['players']
    namespace.update(command=command, rpc=rpc, native_sha=lambda: pins['old_sha256'],
                     ready=lambda expected: True)
    parent, runtime = ModuleType('bobbi_core'), ModuleType('bobbi_core.runtime_paths')
    runtime.known_ce_native = lambda value: state['pin_known'] and value == pins['new_sha256']
    monkeypatch.setitem(sys.modules, 'bobbi_core', parent)
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', runtime)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    code = compile(ast.Module(body=[branch], type_ignores=[]), '<native-branch>', 'exec')
    return SimpleNamespace(ns=namespace, run=lambda: exec(code, namespace), calls=calls, state=state,
                           receipt=receipt, conf=conf, generation=generation, base=base, oldbin=oldbin,
                           pins=pins, old_conf=old_conf, new_conf=new_conf)


def test_reapply_after_confirmed_rollback_preserves_history_and_old_overlay(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    original_generation = h.generation.read_bytes()
    original_backup = (h.base / 'previous.conf').read_bytes()
    h.run()
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'applied' and record['action'] == 'reapply'
    assert [row['state'] for row in record['history']] == ['applied', 'rolled_back', 'prepared']
    assert h.conf.read_bytes() == h.new_conf
    assert h.generation.read_bytes() == original_generation
    assert (h.base / 'previous.conf').read_bytes() == original_backup
    assert h.calls == [('systemctl', 'stop', 'kodi.service'), ('systemctl', 'daemon-reload'),
                       ('systemctl', 'start', 'kodi.service')]


@pytest.mark.parametrize('case', ['not_rolled_back', 'unconfirmed', 'receipt_pin', 'current_conf',
                                  'old_binary', 'backup', 'unknown_candidate', 'old_generation', 'active_playback'])
def test_invalid_reapply_fails_before_service_mutation(tmp_path, monkeypatch, case):
    h = harness(tmp_path, monkeypatch)
    record = json.loads(h.receipt.read_text())
    if case == 'not_rolled_back':
        record['state'] = 'applied'
    elif case == 'unconfirmed':
        record['recovered'] = False
    elif case == 'receipt_pin':
        record['new_sha256'] = 'wrong'
    elif case == 'current_conf':
        h.conf.write_bytes(b'foreign')
    elif case == 'old_binary':
        h.oldbin.write_bytes(b'foreign')
    elif case == 'backup':
        (h.base / 'previous.conf').write_bytes(b'foreign')
    elif case == 'unknown_candidate':
        h.state['pin_known'] = False
    elif case == 'old_generation':
        h.generation.write_text(json.dumps({'sequence': 2026101907}))
    else:
        h.state['players'] = [{'playerid': 1}]
    h.receipt.write_text(json.dumps(record))
    before_receipt, before_conf = h.receipt.read_bytes(), h.conf.read_bytes()
    with pytest.raises(AssertionError):
        h.run()
    assert h.calls == []
    assert h.receipt.read_bytes() == before_receipt and h.conf.read_bytes() == before_conf


def test_reapply_restart_failure_restores_old_and_retains_failed_transition(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    h.state['fail_start_once'] = True
    with pytest.raises(RuntimeError, match='injected'):
        h.run()
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'recovered_after_failure' and record['recovered'] is True
    assert record['action'] == 'reapply' and record['error'] == 'RuntimeError'
    assert [entry['state'] for entry in record['history']] == ['applied', 'rolled_back', 'prepared']
    assert h.conf.read_bytes() == h.old_conf
    assert h.calls.count(('systemctl', 'start', 'kodi.service')) == 2


def test_interrupted_reapply_can_roll_back_without_a_running_kodi(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    record = json.loads(h.receipt.read_text())
    h.ns['transition'](record, 'prepared', action='reapply')
    h.conf.write_bytes(h.new_conf)
    h.ns['MODE'] = 'rollback'
    h.state['players'] = None
    h.run()
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'rolled_back' and record['recovered'] is True
    assert any(entry.get('action') == 'reapply' and entry['state'] == 'prepared' for entry in record['history'])
    assert h.conf.read_bytes() == h.old_conf


def test_initial_apply_never_reuses_an_existing_receipt(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    h.ns['MODE'] = 'apply'
    with pytest.raises(AssertionError, match='TRANSITION_ALREADY_STARTED'):
        h.run()
    assert h.calls == []
