"""The attended transport tool must prepare local receipts before device work."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('mode', ('status', 'block'))
def test_first_run_prepares_receipt_directory_before_connect(monkeypatch, tmp_path, mode):
    path = Path(__file__).resolve().parents[1] / 'tools/ce_transport_mode.py'
    spec = importlib.util.spec_from_file_location('transport_mode_receipt_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', [str(path), mode, '--transport-source', str(tmp_path/'wire')])
    closed = []

    def connect():
        assert (tmp_path/'review-evidence/ce-20261020').is_dir()
        return SimpleNamespace(close=lambda: closed.append(True)), SimpleNamespace(
            readonly=lambda *a, **k: (0, {'mode': mode, 'account_preserved': True}, False))

    loader = SimpleNamespace(exec_module=lambda target: setattr(target, 'connect', connect))
    monkeypatch.setattr(module.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=loader))
    monkeypatch.setattr(module.importlib.util, 'module_from_spec', lambda *a: SimpleNamespace())
    module.main()
    receipts = list((tmp_path/'review-evidence/ce-20261020').glob('transport-'+mode+'-*.json'))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt['exit_code'] == 0
    assert receipt['result']['mode'] == mode
    assert closed == [True]


def test_invalid_run_rejected_before_connection(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / 'tools/ce_transport_mode.py'
    spec = importlib.util.spec_from_file_location('transport_mode_bad_run', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, 'argv', [str(path), 'progressive', '--transport-source', str(tmp_path),
                                    '--run-id', '../not-a-run'])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


def test_custom_run_uses_own_device_baseline_and_local_receipts(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / 'tools/ce_transport_mode.py'
    spec = importlib.util.spec_from_file_location('transport_mode_custom_run', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path/'new-evidence'
    monkeypatch.setattr(sys, 'argv', [str(path), 'progressive', '--transport-source', str(tmp_path),
        '--run-id', 'review-new-run', '--output-dir', str(output)])
    seen = []
    def readonly(client, code, **kwargs):
        assert output.is_dir()
        seen.append(code.decode())
        return 0, {'configured': 'progressive'}, False
    loader = SimpleNamespace(exec_module=lambda target: setattr(target, 'connect', lambda: (
        SimpleNamespace(close=lambda: None), SimpleNamespace(readonly=readonly))))
    monkeypatch.setattr(module.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=loader))
    monkeypatch.setattr(module.importlib.util, 'module_from_spec', lambda *a: SimpleNamespace())
    module.main()
    assert "TRIAL_RUN='review-new-run'" in seen[0]
    assert "/TRIAL_RUN/'transport-original.json'" in seen[0]
    assert len(list(output.glob('transport-progressive-*.json'))) == 1
