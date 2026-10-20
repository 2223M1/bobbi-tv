"""Observed bracketed S/E release through the real Juku cache/next-file chain."""
from contextlib import closing
import time

import pytest

from bobbi_core import juku_catalog as cat


@pytest.mark.parametrize('difference', ['none', 'edition', 'group', 'quality', 'parent', 'share', 'ambiguous', 'cancel'])
def test_bracketed_release_through_juku_next_file(tmp_path, difference):
    spec = cat._spec(dict(tmdb_id=116727, mode='tv', season=1, episode=1,
                         year=2021, aliases=['ODDTAXI']))
    work = dict(tmdbId=116727, typeId=2, year=2021, title='ODDTAXI')
    def row(number, **changes):
        link = dict(url='https://115.com/s/sabcdef', fileId=str(number),
                    fileName='ODD TAXI S01E%02d-[1080p][JP.BD.Remux][lolice-mix].mkv' % number,
                    fileSize=4500000000+number, parentFolderId='8')
        link.update(changes)
        return cat._row(work, link, 'shared:audit')
    anchor, following = row(1), row(2)
    if difference in ('edition', 'group', 'quality'):
        name = following['name']
        name = (name.replace('[1080p]', '[Extended][1080p]') if difference == 'edition' else
                name.replace('lolice-mix', 'Other') if difference == 'group' else name.replace('1080p', '720p'))
        following = row(2, fileName=name)
    elif difference == 'parent':
        following = row(2, parentFolderId='9')
    elif difference == 'share':
        following = row(2, url='https://115.com/s/sghijkl')
    rows = [anchor, following]
    if difference == 'ambiguous':
        rows.append(row(2, fileId='3'))
    with closing(cat.Cache(tmp_path)) as cache:
        cache.replace_library('audit', 1, rows)
        cache.remember([cat._bound(anchor, spec)], spec)
    current = dict(direct_source=dict(locator='am6bjuku://'+anchor['key'],
                   guid='juku:'+anchor['key'], title=anchor['name'], size=anchor['size']))
    result, reason = cat.next_file(current, (116727, 1, 1), lambda: difference == 'cancel',
                                  time.monotonic()+5, state=tmp_path)
    if difference == 'none':
        assert reason == 'INDEXED_DIRECT_SAME_RELEASE'
        assert result['title'] == following['name']
        selected = cat.selected(result['url'], result['guid'], result['title'],
                                result['size'], cat.media_key(116727, 'tv', 1, 2), state=tmp_path)
        assert selected['fid'] == '2'
    else:
        assert result is None
        assert reason != 'INDEXED_DIRECT_SAME_RELEASE'
