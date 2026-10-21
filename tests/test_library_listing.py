from dataclasses import replace
import json
import pytest
from bobbi_platform.libraries import import_catalog, vfs_source, LibraryError
from bobbi_platform.library_listing import source_presentation, file_info, native_listing


@pytest.mark.parametrize('scheme,kind,label', [('smb','smb','SMB'), ('nfs','nfs','NFS'),
    ('dav','webdav','WebDAV'), ('davs','webdav','WebDAV')])
def test_source_protocol_and_host_only(scheme,kind,label):
    source = vfs_source('Name', scheme + '://nas.local/Private/Path')
    source = replace(source, location=scheme + '://ignored:secret@nas.local/Private?secret=1')
    assert source_presentation(source) == (kind, label + ' · nas.local')


def test_local_not_misrepresented_as_network():
    assert source_presentation(vfs_source('Disk','/storage/media')) == ('local', '本机目录')


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
