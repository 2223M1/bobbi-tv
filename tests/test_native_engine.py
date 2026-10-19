from pathlib import Path
from types import SimpleNamespace
import pytest
from bobbi_platform import native_engine as native


@pytest.mark.parametrize('release', ['ID="coreelec"\n', 'NAME=CoreELEC\nID=coreelec\n'])
def test_detect_runtime_bitness_not_box_model(monkeypatch, release):
    monkeypatch.setattr(Path, 'read_text', lambda self: release)
    monkeypatch.setattr(native.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(native.platform, 'machine', lambda: 'aarch64')
    monkeypatch.setattr(native.ctypes, 'sizeof', lambda _: 4)
    assert native.architecture() == 'arm7'
    monkeypatch.setattr(native.ctypes, 'sizeof', lambda _: 8)
    assert native.architecture() == 'arm64'


def test_not_installed_means_no_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(native, 'profile', lambda **kw: tmp_path / 'engine')
    monkeypatch.setattr(native.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not start'))
    engine = native.Engine()
    engine.tick()
    engine.close()
    assert engine.attempted is False


def test_close_only_owns_its_process():
    calls = []
    process = SimpleNamespace(poll=lambda: None, terminate=lambda: calls.append('terminate'),
        wait=lambda **kwargs: calls.append('wait'))
    engine = native.Engine()
    engine.process = process
    engine.close()
    assert calls == ['terminate', 'wait']
