from pathlib import Path
import sys
import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import delivery_policy as policy

PRODUCT_FIXTURE = '0b4dad0454632d5d2eb31792444dd1456ab34a42'


@pytest.mark.parametrize('dirty,changed,reason', [
    (True, False, 'HANDOFF_CHECKOUT_DIRTY'),
    (False, True, 'PRODUCT_CHANGED_AFTER_FREEZE'),
])
def test_handoff_rejects_dirty_or_changed_product_before_packaging(tmp_path, dirty, changed, reason):
    def git(*args):
        if args[0] == 'status':
            return b' M addons/changed.py' if dirty else b''
        assert args == ('diff', PRODUCT_FIXTURE, 'HEAD', '--', 'addons', 'third_party', 'release')
        return b'changed product' if changed else b''

    output = tmp_path / 'never-created'
    with pytest.raises(ValueError, match=reason):
        policy.require_clean_frozen_checkout(PRODUCT_FIXTURE, git_runner=git, output=output)
    assert not output.exists()
