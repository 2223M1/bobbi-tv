"""Presentation-only library metadata; never fetch media or expose credentials."""
from datetime import datetime
import os
from urllib.parse import unquote, urlsplit

from .libraries import LibraryError, MAX_DIRECTORY_ITEMS, directory_items


def source_presentation(source):
    if source.kind == 'catalog':
        return 'catalog', '目录 · %d 项' % len(source.items)
    location = urlsplit(source.location)
    kind = {'smb': 'smb', 'nfs': 'nfs', 'dav': 'webdav', 'davs': 'webdav'}.get(location.scheme)
    if kind:
        # Host only: no username, password, path, query or access token.
        return kind, {'smb': 'SMB', 'nfs': 'NFS', 'webdav': 'WebDAV'}[kind] + ' · ' + location.hostname
    return 'local', '本机目录'


def file_info(size=None, modified=''):
    info = {}
    if type(size) is int and 0 <= size <= 2**63 - 1:
        info['size'] = size
    if isinstance(modified, str) and modified:
        try:
            value = datetime.fromisoformat(modified)
            # Kodi ListItem.setInfo's general "date" uses DD.MM.YYYY.
            info['date'] = value.strftime('%d.%m.%Y')
        except ValueError:
            pass
    return info


def native_listing(response, path):
    """Read one Kodi directory response, preserving the existing file grammar.

    Paths must remain immediate children of the exact authenticated directory.
    Invalid/unsupported metadata permits a plain VFS fallback, never a stat storm.
    """
    result = response.get('result', {})
    rows = result.get('files')
    if not isinstance(rows, list):
        raise ValueError('DIRECTORY_METADATA_UNAVAILABLE')
    total = result.get('limits', {}).get('total', len(rows))
    if type(total) is not int or total > MAX_DIRECTORY_ITEMS or len(rows) > MAX_DIRECTORY_ITEMS:
        raise LibraryError('DIRECTORY_TOO_LARGE')
    if total != len(rows):
        raise ValueError('INCOMPLETE_DIRECTORY')
    dirs, files, metadata = [], [], {}
    prefix = path.rstrip('/') + '/'
    for row in rows:
        if not isinstance(row, dict) or row.get('filetype') not in ('file', 'directory'):
            raise ValueError('INVALID_DIRECTORY_ROW')
        target = row.get('file', '')
        if not isinstance(target, str) or not target.startswith(prefix):
            raise ValueError('DIRECTORY_PATH_CHANGED')
        name = target[len(prefix):].rstrip('/')
        if urlsplit(path).scheme in ('smb', 'nfs', 'dav', 'davs'):
            name = unquote(name)
        if not name or '/' in name or '\\' in name:
            raise ValueError('NOT_IMMEDIATE_CHILD')
        folder = row['filetype'] == 'directory'
        (dirs if folder else files).append(name)
        if not folder:
            metadata[name] = file_info(row.get('size'), row.get('lastmodified'))
    return directory_items(dirs, files), metadata


def local_listing(path):
    """Local sources need not be registered for Kodi's remote-files API."""
    dirs, files, metadata = [], [], {}
    # Embedded CE Python can use an ASCII filesystem codec. Kodi paths and
    # cloud filenames are UTF-8; a bytes scan avoids surrogate-escaped names
    # and also lets users enter a Chinese-named child directory. Windows keeps
    # its native Unicode path API. Do not change the process-wide locale.
    scan_path = os.fspath(path)
    if os.name == 'posix' and isinstance(scan_path, str):
        scan_path = scan_path.encode('utf-8')
    with os.scandir(scan_path) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_DIRECTORY_ITEMS:
                raise LibraryError('DIRECTORY_TOO_LARGE')
            try:
                name = entry.name.decode('utf-8') if isinstance(entry.name, bytes) else entry.name
            except UnicodeDecodeError:
                continue  # Invalid byte names cannot form a Kodi UTF-8 route.
            folder = entry.is_dir()
            (dirs if folder else files).append(name)
            if not folder:
                try:
                    stat = entry.stat()
                    metadata[name] = file_info(stat.st_size, datetime.fromtimestamp(stat.st_mtime).isoformat())
                except OSError:
                    pass
    return directory_items(dirs, files), metadata
