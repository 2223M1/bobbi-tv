import os
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core.android_font_decoder import collect


def test_cancelled_font_decode_never_starts_child(monkeypatch):
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('cancelled child started'))
    with pytest.raises(InterruptedError):
        collect(['unused'], 16, time.monotonic()+1, lambda: False)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX pipe/child boundaries run under WSL')
@pytest.mark.parametrize('code,limit,error', [
    ('import sys;sys.stdout.write("x"*8192)', 64, ValueError),
    ('import time;time.sleep(3)', 64, TimeoutError),
    ('raise SystemExit(1)', 64, ValueError)])
def test_child_output_deadline_and_failure_are_bounded(code, limit, error):
    started = time.monotonic()
    with pytest.raises(error):
        collect([sys.executable, '-c', code], limit, started+.5, lambda: True)
    assert time.monotonic()-started < 2


@pytest.mark.skipif(os.name != 'posix', reason='POSIX pipe/child boundaries run under WSL')
def test_child_exact_output():
    assert collect([sys.executable, '-c', 'print("hello",end="")'], 5,
                   time.monotonic()+2, lambda: True) == b'hello'
