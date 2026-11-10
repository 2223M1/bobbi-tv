"""Independent review of catalog response bounds and source membership."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.file_ref import from_selected
from bobbi_core.media_library_index import MediaIndex
from bobbi_platform.runtime import encode_message, MAX_MESSAGE_BYTES


def test_emoji_metadata_default_catalog_page_fits_real_ipc_budget(tmp_path):
    index = MediaIndex(tmp_path / 'catalog.sqlite3')
    expected = dict(provider='baidu', account_id='baidu:' + 'a' * 64, epoch=1, authenticated=True)
    try:
        refs = [from_selected(expected, dict(file_id=str(number), name='🎬' * 240 + '.mkv',
            size=100, directory=False), '/' + '🎬' * 240) for number in range(1, 6)]
        task = index.start('b' * 32, expected)
        index.begin(task)
        index.batch(task, refs, {'page': 1}, 5)
        index.finish(task, 'completed')
        mapping = dict(kind='movie', title='🎬' * 240, tmdb_id=1, season=None, episode=None, version='🎬' * 80)
        commands = [dict(file_id=ref['id'], expected_revision=0, action='confirm', mapping=mapping) for ref in refs]
        result = index.apply(expected, 'c' * 32, commands)
        assert all(row['status'] == 'applied' for row in result['items'])
        result = index.items(expected)
        assert len(encode_message(dict(ok=True, result=result))) <= MAX_MESSAGE_BYTES
    finally:
        index.close()
