from dataclasses import replace
import json
import sqlite3

import pytest

from bobbi_platform.libraries import (LibraryError, Registry, Source, Item,
    MAX_CATALOG_BYTES, MAX_DIRECTORY_ITEMS, import_catalog, vfs_source,
    joined_path, split_location, directory_items, relative_path, validate_source)


def catalog_raw(**updates):
    value = {'schema': 'bobbi-library-v1', 'name': '个人电影', 'items': [
        {'id': 'film-1', 'title': '测试影片', 'url': 'https://media.example/film.mkv', 'year': 2024}]}
    value.update(updates)
    return json.dumps(value, ensure_ascii=False)


def test_registry_create_edit_reopen_remove_only_local_settings(tmp_path):
    media = tmp_path / 'nas' / 'movie.mkv'
    media.parent.mkdir()
    media.write_bytes(b'unchanged-media')
    db = tmp_path / 'profile' / 'libraries.sqlite3'
    source = vfs_source('自己的 NAS', str(media.parent))
    store = Registry(db)
    store.save(source)
    store.save(replace(source, name='重命名'))
    store.close()
    store = Registry(db)
    assert len(store.sources()) == 1
    assert store.get(source.id).name == '重命名'
    store.remove(source.id)
    assert store.sources() == ()
    assert media.read_bytes() == b'unchanged-media'
    store.close()


def test_legacy_migration_is_once_and_removed_source_does_not_resurrect(tmp_path):
    path = tmp_path / 'libraries.sqlite3'
    store = Registry(path)
    assert store.migrate_legacy('smb://nas.example/videos')
    source = store.sources()[0]
    assert not store.migrate_legacy('smb://nas.example/videos')
    store.remove(source.id)
    store.close()
    store = Registry(path)
    assert not store.migrate_legacy('smb://nas.example/videos')
    assert not store.migrate_legacy('nfs://nas.example/new-folder')
    assert store.sources() == ()
    store.close()


def test_legacy_existing_connection_is_not_duplicated(tmp_path):
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(vfs_source('Movies', 'smb://nas.example/videos/'))
    assert not store.migrate_legacy('smb://nas.example/videos')
    assert len(store.sources()) == 1
    store.close()


def test_credential_encoding_and_ipv6_no_secret_in_repr():
    source = vfs_source('NAS', 'davs://[2001:db8::1]:5006/影视/', 'u@域', 'secret:/@%')
    assert source.location == 'davs://[2001:db8::1]:5006/%E5%BD%B1%E8%A7%86/'
    url = joined_path(source, '甲/%2e%2e/video #1.mkv')
    assert 'u%40%E5%9F%9F:secret%3A%2F%40%25@' in url
    assert '%252e%252e' in url and '%20%231.mkv' in url
    assert 'secret' not in repr(source) and source.location not in repr(source)
    root, username, password = split_location('smb://user%40domain:pass%2Fword@nas/Movies')
    assert root == 'smb://nas/Movies/' and username == 'user@domain' and password == 'pass/word'


@pytest.mark.parametrize('root,relative,expected', [
    ('/media', 'movie.mkv', '/media/movie.mkv'),
    ('/', 'movie.mkv', '/movie.mkv'),
    ('D:\\Movies', 'TV/01.mkv', 'D:\\Movies\\TV\\01.mkv'),
    ('E:\\', '01.mkv', 'E:\\01.mkv'),
    ('D:/Movies', '01.mkv', 'D:/Movies/01.mkv'),
    ('nfs://nas/volume1/video', '01.mkv', 'nfs://nas/volume1/video/01.mkv'),
])
def test_supported_location_forms(root, relative, expected):
    assert joined_path(vfs_source('My library', root), relative) == expected


@pytest.mark.parametrize('location', [
    'plugin://run/', 'special://profile/', 'https://nas/dav/', 'relative/folder',
    'smb://', 'smb://nas:wrong/', 'smb://nas:/', 'smb://nas/../private',
    'smb://nas/%2e%2e/', 'smb://nas/%00/', 'smb://nas/%5cprivate/',
    'smb://invalid host/videos', 'smb://nas/films?password=x',
    'smb://nas/films#anything', '/path|Header=value',
])
def test_invalid_locations_rejected(location):
    with pytest.raises(LibraryError):
        vfs_source('NAS', location)


@pytest.mark.parametrize('relative', ['../x.mkv', '/x.mkv', 'a//b', 'a/./b',
    'a/../b', 'smb://else/film.mkv', 'a\\b', 'f.mkv|Header=secret', 'bad\x00name'])
def test_relative_path_cannot_escape_selected_root(relative):
    with pytest.raises(LibraryError):
        relative_path(relative)


def test_directory_filters_scripts_and_strm_and_is_stably_sorted():
    assert directory_items(['folder', 'folder', '..', 'a/b'],
        ['B.mkv', 'a.MP4', 'script.py', 'other.strm', 'name|x.mkv', 'x\x7f.mkv', 'B.mkv']) == (
        (True, 'folder'), (False, 'a.MP4'), (False, 'B.mkv'))
    assert len(directory_items(['d'] * (MAX_DIRECTORY_ITEMS // 2),
                               ['a.mkv'] * (MAX_DIRECTORY_ITEMS // 2))) == 2
    with pytest.raises(LibraryError, match='DIRECTORY_TOO_LARGE'):
        directory_items(['d'] * (MAX_DIRECTORY_ITEMS // 2), ['f'] * (MAX_DIRECTORY_ITEMS // 2 + 1))


def test_catalog_roundtrip_and_invalid_update_preserves_record(tmp_path):
    store = Registry(tmp_path / 'libraries.sqlite3')
    source = import_catalog(catalog_raw())
    store.save(source)
    assert store.get(source.id) == source
    assert 'https://' not in repr(source.items[0])
    with pytest.raises(LibraryError):
        store.save(import_catalog('{broken', source.id))
    assert store.get(source.id) == source
    changed = import_catalog(catalog_raw(name='新名称'), source.id)
    store.save(changed)
    assert store.sources() == (changed,)
    store.close()


@pytest.mark.parametrize('url', ['plugin://execute/', 'file:///x.mkv', 'smb://nas/f.mkv',
    'https://user:pass@media/x.mkv', 'https://@media/x.mkv', 'https://media/x.mkv|Header=x',
    'https://media/x y.mkv', 'https://media:/x.mkv', 'https://media/x.mkv#password=x',
    'https://media/remote.STRM', 'https://media/remote.%73trm', 'https://media/execute.py'])
def test_catalog_only_direct_http_media(url):
    with pytest.raises(LibraryError):
        import_catalog(catalog_raw(items=[{'id': '1', 'title': 'x', 'url': url}]))


@pytest.mark.parametrize('change', [
    {'items': []}, {'items': None}, {'items': [{'id': '1', 'title': 'x'}]},
    {'items': [{'id': '1', 'title': 'x', 'url': 'https://example/x', 'year': True}]},
    {'items': [{'id': '1', 'title': 'x', 'url': 'https://example/x', 'command': 'run'}]},
    {'items': [{'id': '1', 'title': 'x', 'url': 'https://example/x'}] * 2},
    {'schema': 'unknown'}, {'credentials': 'not-allowed'},
])
def test_invalid_catalog_is_not_partially_imported(change):
    with pytest.raises(LibraryError):
        import_catalog(catalog_raw(**change))


def test_duplicate_json_keys_and_size_rejected():
    with pytest.raises(LibraryError):
        import_catalog('{"schema": "bobbi-library-v1", "schema": "other"}')
    with pytest.raises(LibraryError, match='CATALOG_TOO_LARGE'):
        import_catalog(' ' * (MAX_CATALOG_BYTES + 1))


def test_bad_internal_source_and_database_id_mismatch_rejected(tmp_path):
    source = vfs_source('NAS', 'smb://nas/Movies')
    for malformed in (replace(source, id=123), replace(source, items=[]),
            Source('a' * 32, 'x', 'catalog', items=(Item([], 'x', 'https://example/x'),))):
        with pytest.raises(LibraryError):
            validate_source(malformed)
    store = Registry(tmp_path / 'libraries.sqlite3')
    store.save(source)
    store.db.execute('UPDATE sources SET id=?', ('0' * 32,))
    store.db.commit()
    with pytest.raises(LibraryError, match='INVALID_SOURCE'):
        store.sources()
    store.close()


@pytest.mark.parametrize('raw', ['null', '[]', '{}', '{"items": null}'])
def test_invalid_stored_document_is_domain_error(raw):
    with pytest.raises(LibraryError):
        Registry._read(raw)


def test_connection_limit_update_allowed_failed_add_rolled_back(tmp_path):
    store = Registry(tmp_path / 'libraries.sqlite3')
    sources = [vfs_source(str(n), 'smb://nas/Movies') for n in range(32)]
    for source in sources:
        store.save(source)
    with pytest.raises(LibraryError, match='TOO_MANY_SOURCES'):
        store.save(vfs_source('33', 'smb://nas/Movies'))
    store.save(replace(sources[0], name='updated'))
    assert len(store.sources()) == 32 and store.get(sources[0].id).name == 'updated'
    store.close()


def test_unknown_storage_version_is_preserved(tmp_path):
    path = tmp_path / 'libraries.sqlite3'
    with sqlite3.connect(str(path)) as db:
        db.execute('PRAGMA user_version=99')
    before = path.read_bytes()
    with pytest.raises(LibraryError, match='UNKNOWN_STORAGE_VERSION'):
        Registry(path)
    assert path.read_bytes() == before
