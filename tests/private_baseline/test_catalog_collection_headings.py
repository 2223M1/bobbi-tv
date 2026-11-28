import importlib.util
from pathlib import Path
import json
import sqlite3
from contextlib import closing

from bobbi_catalog.collection_labels import headings, membership
from bobbi_core.library_labels import ref
from lib.domain.torrent import TorrentStream
from lib.utils.general.source_platform import source_libraries


def test_packaged_headings_match_directory_authority_and_never_consume_file_rows():
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('catalog_heading_tool',root/'tools/build_catalog_headings.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    expected=builder.build(builder.ASSETS/'catalog.sqlite3')
    assert expected==headings()
    assert len(expected)==len(set(expected.values()))
    assert '2267部2160p remux FGT' in membership('left-4')[ref('qqdocs','left-4')]
    title=membership('left-45')[ref('qqdocs','left-45')]
    assert '蓝光原盘+蓝光压制+HD高清' in title and '1.62PB' in title
    assert all(not any(x in name for x in (':directory:', 'supp-', '!B', '://')) for name in expected.values())
    assert not builder.heading('[COLOR red]不可信库名[/COLOR]')


def test_a_cell_is_not_a_collection_or_a_movie_filter_identity():
    libs=membership('left-4'); ids=[]
    for pos in ('1!B815','1!B999','user-supplement-test:directory:123456789012'):
        src=TorrentStream(type='Direct',indexer='115 资源目录',guid='qqdocs:test',
                          subindexer=pos+' / 汇总!E4',sourceLibraries=libs)
        ids.append(source_libraries(src))
        assert pos not in str(ids[-1])
    assert ids==[libs]*3
    src.sourceLibraries={}
    assert list(source_libraries(src).values())==['腾讯文档目录']
