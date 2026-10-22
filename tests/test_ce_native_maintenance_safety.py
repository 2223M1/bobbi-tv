"""Failure injection executes the maintainer's real remote body without a device."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_ce_native_handoff_profile import artifacts
from test_ce_native_reapply import harness, tool


def remote_body(h):
    original_path = h.ns['pathlib'].Path
    h.ns['pathlib'] = SimpleNamespace(Path=lambda value:
        h.conf if str(value) == '/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf'
        else original_path(value))
    h.ns.update(BASE=str(h.base), REQUIRED_SEQUENCE=2026102035, PROFILE_TAG='2035')
    h.generation.write_text(json.dumps(dict(sequence=2026102035)))
    tree = ast.parse(tool.REMOTE)
    body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
            and not (isinstance(node, ast.FunctionDef) and node.name in ('command', 'rpc', 'native_sha', 'ready'))]
    return lambda: exec(compile(ast.Module(body=body, type_ignores=[]), '<real-native-remote>', 'exec'), h.ns)


@pytest.mark.parametrize('new_configuration', [b'concurrent-owner-configuration', b'old conf'])
def test_rollback_rechecks_exact_observed_configuration_after_stopping_service(tmp_path, monkeypatch,
                                                                           new_configuration):
    h = harness(tmp_path, monkeypatch)
    h.ns['MODE'] = 'rollback'
    record = json.loads(h.receipt.read_text())
    record['state'] = 'applied'
    h.receipt.write_text(json.dumps(record))
    h.conf.write_bytes(h.new_conf)
    original = h.ns['command']
    def command(*args):
        if args[:2] == ('systemctl', 'stop'):
            h.conf.write_bytes(new_configuration)
        return original(*args)
    h.ns['command'] = command
    with pytest.raises(AssertionError, match='CONCURRENT_CONFIGURATION_CHANGE'):
        h.run()
    assert h.conf.read_bytes() == new_configuration
    assert h.calls == [('systemctl', 'stop', 'kodi.service')]
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'rollback_blocked' and record['recovered'] is False


@pytest.mark.parametrize('damage', ['corrupt', 'missing'])
@pytest.mark.parametrize('mode', ['status', 'rollback'])
def test_damaged_new_candidate_does_not_disable_status_or_old_overlay_rollback(tmp_path, monkeypatch,
                                                                           damage, mode):
    h = harness(tmp_path, monkeypatch)
    h.ns['MODE'] = mode
    record = json.loads(h.receipt.read_text())
    record['state'] = 'applied'
    h.receipt.write_text(json.dumps(record))
    h.conf.write_bytes(h.new_conf)
    candidate = h.base/'kodi.bin'
    if damage == 'corrupt': candidate.write_bytes(b'corrupt candidate')
    else: candidate.unlink()
    remote_body(h)()
    if mode == 'status':
        assert h.ns['out']['staged_valid'] is False
        assert h.ns['out']['staged']['kodi.bin']['valid'] is False
        assert h.ns['out']['candidate_ready'] is False
        assert not h.calls
    else:
        assert h.ns['out']['staged_valid'] is None and h.ns['out']['staged'] == {}
        assert h.ns['out']['staged_check'] == 'not_required_for_rollback'
        assert h.conf.read_bytes() == h.old_conf
        record = json.loads(h.receipt.read_text())
        assert record['state'] == 'rolled_back' and record['recovered'] is True


@pytest.mark.parametrize('mode', ['apply', 'reapply'])
def test_damaged_candidate_still_prevents_apply_before_service_mutation(tmp_path, monkeypatch, mode):
    h = harness(tmp_path, monkeypatch)
    h.ns['MODE'] = mode
    (h.base/'kodi.bin').write_bytes(b'corrupt candidate')
    before = h.receipt.read_bytes()
    with pytest.raises(AssertionError, match='STAGED_HASH_MISMATCH'):
        remote_body(h)()
    assert not h.calls and h.receipt.read_bytes() == before


@pytest.mark.parametrize('failure', ['timeout', 'remote_exit', 'close_after_timeout',
                                     'close_after_success', 'connect', 'stage_sftp',
                                     'rc0_structured_failure', 'rc0_error_type'])
def test_remote_failure_always_emits_sanitized_unconfirmed_local_report(artifacts, monkeypatch,
                                                                      tmp_path, capsys, failure):
    a = artifacts
    monkeypatch.setitem(tool.PROFILES, 'handoff2035', a.profile)
    closed = []
    marker = 'redaction_probe_only'
    def close():
        closed.append(True)
        if failure.startswith('close_'): raise OSError(marker)
    def sftp(): raise OSError(marker)
    client = SimpleNamespace(close=close, open_sftp=sftp)
    def readonly(*args, **kwargs):
        if failure in ('timeout', 'close_after_timeout'): raise TimeoutError(marker)
        if failure == 'remote_exit': return 1, None, marker
        if failure == 'rc0_structured_failure':
            return 0, {'outcome': 'unconfirmed', 'stage': 'generation',
                       'code': 'ENTRY_INSTALLATION_INCOMPLETE', 'error_type': 'AssertionError'}, ''
        if failure == 'rc0_error_type': return 0, {'error_type': 'AssertionError'}, ''
        return 0, {'receipt': {'state': 'applied'}}, ''
    wire = SimpleNamespace(readonly=readonly)
    def connect():
        if failure == 'connect': raise ConnectionError(marker)
        return client, wire
    def execute(module): module.connect = connect
    monkeypatch.setattr(tool.importlib.util, 'spec_from_file_location',
                        lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=execute)))
    monkeypatch.setattr(tool.importlib.util, 'module_from_spec', lambda spec: SimpleNamespace())
    reports = tmp_path/'reports'
    mode = 'stage' if failure == 'stage_sftp' else 'apply'
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'argv', ['ce_native_update.py', '--profile', 'handoff2035',
        '--transport-source', str(tmp_path), '--mode', mode, '--build-result', str(a.result_path),
        '--baseline-layout', str(a.layout_path), '--report-dir', str(reports)])
    with pytest.raises(RuntimeError, match='NATIVE_TRANSITION_UNCONFIRMED_READ_STATUS'):
        tool.main()
    assert closed == ([] if failure == 'connect' else [True])
    paths = list(reports.glob('ce-native2035-'+mode+'-*.json'))
    assert len(paths) == 1
    text = paths[0].read_text()
    report = json.loads(text)
    assert report['outcome'] == 'unconfirmed' and report['next_action'] == 'status'
    assert marker not in text and marker not in capsys.readouterr().out
    if failure in ('timeout', 'close_after_timeout'): assert report['error_type'] == 'TimeoutError'
    if failure.startswith('close_'): assert report['close_error_type'] == 'OSError'
    if failure == 'connect': assert report['error_type'] == 'ConnectionError'
    if failure == 'stage_sftp': assert report['error_type'] == 'OSError' and report['phase'] == 'stage'
    if failure == 'rc0_structured_failure':
        assert report['result']['code'] == 'ENTRY_INSTALLATION_INCOMPLETE'
