"""Run actual retired clients from the maintainer's archive without redistributing them."""
import hashlib
import os
from pathlib import Path

import pytest


def launcher(relative, sha256):
    root = Path(os.environ.get('BOBBI_ARCHIVED_FEED', Path(__file__).resolve().parents[1] / 'repository'))
    path = root / relative
    if not path.is_file() and 'BOBBI_ARCHIVED_FEED' not in os.environ:
        pytest.skip('Historical launcher not distributed; set BOBBI_ARCHIVED_FEED to run archived-client evidence')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
    return path
