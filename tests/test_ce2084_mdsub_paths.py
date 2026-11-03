"""The faster catalog scanner must accept exactly the same public paths."""
import importlib.util
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mdsub_path_fixture',
    ROOT/'addons/script.module.bobbi.mdsub/lib/bobbi_mdsub/catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def original(path):
    if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
            or len(path) > 2048 or len(path.split('/')) < 3
            or any(part in ('', '.', '..') or part.startswith('._') for part in path.split('/')[1:])
            or any(ord(char) < 32 or ord(char) == 127 for char in path) or '\\' in path
            or Path(path).suffix.casefold() not in catalog.VIDEO_EXTENSIONS):
        raise ValueError('INVALID_MDSUB_PATH')
    return path


def accepted(function, path):
    try:
        return function(path)
    except ValueError:
        return None


def test_catalog_path_rules_unchanged_for_all_ascii_and_unicode_edges():
    paths = [None, 1, '', '/', '//work/video.mkv', '/work/.mkv', '/work/._video.mkv',
             '/work/../video.mkv', '/work/./video.mkv', '/work/影片.MKV', '/work/影片.mkv ']
    paths += ['/work/a'+chr(code)+'b.mkv' for code in range(256)]
    paths += ['/work/'+('片'*length)+'.mkv' for length in (1, 100, 2038, 2040, 2048)]
    rng = random.Random(2084)
    alphabet = '/.\\\x00\x1f\x7f中文Ａa🦊é xyz012_-'
    paths += ['/work/'+''.join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))+'.mkv'
              for _ in range(2000)]
    for path in paths:
        assert accepted(catalog.checked_path, path) == accepted(original, path), repr(path)


def test_every_shipped_catalog_path_still_validates():
    data = json.loads(catalog.DEFAULT_INDEX.read_text(encoding='utf-8'))
    for row in data['files']:
        assert catalog.checked_path(row['path']) == original(row['path'])
    assert catalog.validate(data) is data
