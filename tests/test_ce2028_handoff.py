import importlib.util
from pathlib import Path
import sys
import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('handoff28', TOOLS / 'package_ce2028_handoff.py')
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


@pytest.mark.parametrize('dirty,changed,reason', [
    (True, False, 'HANDOFF_CHECKOUT_DIRTY'),
    (False, True, 'PRODUCT_CHANGED_AFTER_FREEZE'),
])
def test_handoff_rejects_dirty_or_changed_product_before_packaging(tmp_path, monkeypatch, dirty, changed, reason):
    def git(*args):
        if args[0] == 'status':
            return b' M addons/changed.py' if dirty else b''
        assert args == ('diff', handoff.PRODUCT, 'HEAD', '--', 'addons', 'third_party', 'release')
        return b'changed product' if changed else b''
    monkeypatch.setattr(handoff, 'git', git)
    output = tmp_path / 'never-created'
    monkeypatch.setattr(sys, 'argv', ['handoff', '--results', str(tmp_path), '--output', str(output)])
    with pytest.raises(ValueError, match=reason):
        handoff.main()
    assert not output.exists()
