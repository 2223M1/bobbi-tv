# -*- coding: utf-8 -*-
"""Unified file access for local paths and Kodi VFS (smb://, nfs://, ...)."""

from __future__ import annotations

import os
import stat as stat_mod
import xml.etree.ElementTree as ET
from typing import Optional

import xbmcvfs

VFS_PREFIXES = (
    'special://', 'smb://', 'nfs://', 'ftp://', 'sftps://', 'ssh://',
    'dav://', 'davs://', 'upnp://', 'sources://',
)


def is_vfs_path(path: str) -> bool:
    lowered = (path or '').lower()
    return lowered.startswith(VFS_PREFIXES)


def normalize(path: str) -> str:
    path = (path or '').strip()
    if is_vfs_path(path):
        return path.replace('\\', '/')
    return path


def join(base: str, *parts: str) -> str:
    result = normalize(base)
    for part in parts:
        if not part:
            continue
        piece = normalize(part).strip('/\\')
        if is_vfs_path(result):
            result = result.rstrip('/') + '/' + piece
        else:
            result = os.path.join(result, piece)
    return result


def dirname(path: str) -> str:
    path = normalize(path)
    if is_vfs_path(path):
        if '/' not in path.rstrip('/'):
            return path
        return path.rstrip('/').rsplit('/', 1)[0]
    return os.path.dirname(path)


def basename(path: str) -> str:
    path = normalize(path)
    if is_vfs_path(path):
        return path.rstrip('/').rsplit('/', 1)[-1]
    return os.path.basename(path)


def exists(path: str) -> bool:
    path = normalize(path)
    if not path:
        return False
    return xbmcvfs.exists(path)


def _stat_mode(path: str) -> Optional[int]:
    try:
        return xbmcvfs.Stat(path).st_mode()
    except Exception:
        return None


def isdir(path: str) -> bool:
    path = normalize(path)
    if not path or not xbmcvfs.exists(path):
        return False
    if hasattr(xbmcvfs, 'isdir'):
        return bool(xbmcvfs.isdir(path))
    mode = _stat_mode(path)
    return bool(mode is not None and stat_mod.S_ISDIR(mode))


def isfile(path: str) -> bool:
    path = normalize(path)
    if not path or not xbmcvfs.exists(path):
        return False
    if hasattr(xbmcvfs, 'isfile'):
        return bool(xbmcvfs.isfile(path))
    mode = _stat_mode(path)
    if mode is not None:
        return stat_mod.S_ISREG(mode)
    handle = xbmcvfs.File(path, 'rb')
    try:
        handle.read(1)
        return True
    except Exception:
        return False
    finally:
        handle.close()


def makedirs(path: str) -> None:
    path = normalize(path)
    if not path or isdir(path):
        return
    if hasattr(xbmcvfs, 'mkdirs'):
        xbmcvfs.mkdirs(path)
        return
    parent = dirname(path)
    if parent and not exists(parent):
        makedirs(parent)
    if hasattr(xbmcvfs, 'mkdir'):
        xbmcvfs.mkdir(path)


def _read_raw(path: str):
    handle = xbmcvfs.File(path, 'rb')
    try:
        return handle.read()
    finally:
        handle.close()


def read_bytes(path: str) -> Optional[bytes]:
    path = normalize(path)
    if not isfile(path):
        return None
    try:
        data = _read_raw(path)
        if data is None:
            return None
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            try:
                return data.encode('latin-1')
            except UnicodeEncodeError:
                return data.encode('utf-8')
        return None
    except Exception:
        return None


def write_bytes(path: str, data: bytes) -> bool:
    path = normalize(path)
    parent = dirname(path)
    if parent:
        makedirs(parent)
    handle = xbmcvfs.File(path, 'wb')
    try:
        try:
            handle.write(data)
        except TypeError:
            handle.write(data.decode('latin-1'))
        return True
    except Exception:
        return False
    finally:
        handle.close()


def read_text(path: str, encoding: str = 'utf-8') -> Optional[str]:
    path = normalize(path)
    if not isfile(path):
        return None
    try:
        data = _read_raw(path)
        if data is None:
            return None
        if isinstance(data, str):
            return data
        return data.decode(encoding)
    except (UnicodeDecodeError, Exception):
        return None


def remove(path: str) -> bool:
    path = normalize(path)
    if not path or not xbmcvfs.exists(path):
        return False
    return xbmcvfs.delete(path)


def write_text(path: str, text: str, encoding: str = 'utf-8') -> bool:
    return write_bytes(path, text.encode(encoding))


def parse_xml(path: str) -> Optional[ET.Element]:
    content = read_text(path)
    if content is None:
        return None
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


def write_xml(path: str, root: ET.Element) -> bool:
    if hasattr(ET, 'indent'):
        ET.indent(ET.ElementTree(root), space='  ')
    body = ET.tostring(root, encoding='utf-8')
    header = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    return write_bytes(path, header + body)
