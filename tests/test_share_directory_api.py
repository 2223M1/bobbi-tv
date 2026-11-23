from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_catalog.api import Client, ShareError


def client(data):
    value = object.__new__(Client)
    value.get = lambda *args, **kwargs: data
    return value


def test_directory_preserves_file_and_directory_identity_and_provider_total():
    value = client(dict(count='3', list=[{'fid': '100', 'n': 'Film.mkv', 's': '1234'},
        {'cid': '200', 'n': 'Subs', 's': 0}, {'fid': '300', 'n': 'Film.zh.ass', 's': 32}]))
    result = value.list_directory({}, '0', 0, 100, time.monotonic() + 1)
    assert result == dict(total=3, rows=[dict(fid='100', name='Film.mkv', size=1234, is_dir=False),
        dict(fid='200', name='Subs', size=0, is_dir=True),
        dict(fid='300', name='Film.zh.ass', size=32, is_dir=False)])


@pytest.mark.parametrize('parent,offset,limit', [('bad', 0, 100), ('1', -1, 100),
    ('1', True, 100), ('1', 0, 101), ('1', 0, True), ('1', 0, 0)])
def test_directory_request_bounds(parent, offset, limit):
    with pytest.raises(ShareError):
        client({}).list_directory({}, parent, offset, limit, time.monotonic() + 1)


def test_directory_overlong_page_rejected_instead_of_silent_truncation():
    value = client(dict(list=[{'fid': '1', 'n': 'a.srt', 's': 2}] * 2))
    with pytest.raises(ShareError):
        value.list_directory({}, '0', 0, 1, time.monotonic() + 1)


def test_malformed_rows_do_not_fabricate_identity_or_complete_total():
    value = client(dict(list=[{}, None, {'fid': 'bad', 'n': 'bad', 's': 3},
                              {'fid': '1', 'n': 'bad\x00.srt', 's': 5}]))
    assert value.list_directory({}, '0', 0, 100, time.monotonic() + 1) == {'rows': [], 'total': None}
