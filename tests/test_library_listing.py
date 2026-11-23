from dataclasses import replace
from contextlib import contextmanager
import json
import os
from types import SimpleNamespace
import pytest
from bobbi_platform.libraries import import_catalog, vfs_source, LibraryError
from bobbi_platform.library_listing import source_presentation, file_info, native_listing, local_listing


@pytest.mark.parametrize('scheme,kind,label', [('smb','smb','SMB'), ('nfs','nfs','NFS'),
    ('dav','webdav','WebDAV'), ('davs','webdav','WebDAV')])
def test_source_protocol_and_host_only(scheme,kind,label):
    source = vfs_source('Name', scheme + '://nas.local/Private/Path')
    source = replace(source, location=scheme + '://ignored:secret@nas.local/Private?secret=1')
    assert source_presentation(source) == (kind, label + ' · nas.local')


def test_local_not_misrepresented_as_network():
    assert source_presentation(vfs_source('Disk','/storage/media')) == ('local', '本机目录')


def test_local_metadata_does_not_require_remote_api_permission(tmp_path):
    (tmp_path/'film.mkv').write_bytes(b'video fixture')
    (tmp_path/'nested').mkdir()
    (tmp_path/'ignored.strm').write_text('never execute')
    listing,metadata=local_listing(tmp_path)
    assert listing==((True,'nested'),(False,'film.mkv'))
    assert metadata['film.mkv']['size']==13
    assert len(metadata['film.mkv']['date'])==10


@pytest.mark.parametrize('path', ['/mnt/115open/', '/mnt/115open/动画/'])
def test_ce_ascii_filesystem_codec_preserves_utf8_names_and_paths(monkeypatch, path):
    from bobbi_platform import library_listing
    seen=[]
    @contextmanager
    def scandir(value):
        seen.append(value)
        if isinstance(value,str):
            value.encode('ascii')  # Embedded CE Python's filesystem codec.
        names=[('动画'.encode(),True),('第一集.mkv'.encode(),False),(b'bad\xff.mkv',False)]
        yield iter(SimpleNamespace(
            name=raw if isinstance(value,bytes) else raw.decode('ascii','surrogateescape'),
            is_dir=lambda folder=folder:folder,
            stat=lambda:SimpleNamespace(st_size=123,st_mtime=1700000000)) for raw,folder in names)
    monkeypatch.setattr(library_listing,'os',SimpleNamespace(name='posix',scandir=scandir,fspath=os.fspath))
    listing,metadata=local_listing(path)
    assert seen==[path.encode('utf-8')]
    assert listing==((True,'动画'),(False,'第一集.mkv'))
    assert metadata['第一集.mkv']['size']==123


@pytest.mark.parametrize('size,date,expected', [(0,'',{'size':0}), (-1,'oops',{}),
    (True,None,{}), (2**64,'2026-10-21',{'date':'21.10.2026'})])
def test_unknown_metadata_is_not_fabricated(size,date,expected):
    assert file_info(size,date) == expected


def test_incomplete_or_outside_listing_falls_back():
    with pytest.raises(ValueError):
        native_listing({'result':{'files':[],'limits':{'total':1}}}, 'smb://nas/a/')
    with pytest.raises(ValueError):
        native_listing({'result':{'files':[{'file':'smb://other/a.mkv','filetype':'file'}]}}, 'smb://nas/a/')
    with pytest.raises(LibraryError):
        native_listing({'result':{'files':[],'limits':{'total':10001}}}, 'smb://nas/a/')


@pytest.mark.parametrize('fields', [{'size':-1},{'size':True},{'modified':'bad'},{'modified':7}])
def test_catalog_rejects_invalid_optional_metadata(fields):
    row = dict(id='1',title='Film',url='https://example.org/video.mkv',**fields)
    with pytest.raises(LibraryError):
        import_catalog(json.dumps(dict(schema='bobbi-library-v1',name='Films',items=[row])))
