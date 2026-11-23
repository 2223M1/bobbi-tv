"""Experimental read-only personal 115 adapter; existing QR/account owner only.

Protocol evidence: ChenyangGao/p115client revision
856e4f8f09ce034534bd458f06d3dee4474a1698 client.py fs_files/fs_file/
download_url_app, tool/attr.py normalize_attr_web. Independent local ShareLib
0.81 ARM64 ListUserFiles/Get115FilePickCodeByFID/ResolveUserPlay corroborate
the directory -> file ID -> pick code -> chrome original-download sequence.
This is protocol attribution, not a verified MIT license claim; the adapted
wire codec's conflicting pinned license evidence remains unresolved.
No share fallback, transcoding, transfer, new worker or credential store.
"""
import json
import re

from . import pan_115_cipher as cipher
from .pan_accounts import PanError
from .pan_http import (Session, credentials, PERSONAL115_DOWNLOAD as DOWNLOAD,
                       PERSONAL115_DOWNLOAD_USER_AGENT as USER_AGENT)
from .pan_tokens import decimal, identifier, listing, number, original_url, page_number, text

WEB = 'https://webapi.115.com'
CDN = ('115.com', '115cdn.com', '115cdn.net')


def _reply(value):
    if type(value) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    if value.get('state') is not True:
        raise PanError('PAN_API_REJECTED')
    return value


def _integer(value):
    return number(int(decimal(value)))


def _sha(value):
    if type(value) is not str or not re.fullmatch('[a-fA-F0-9]{40}', value):
        raise PanError('PAN_REPLY_INVALID')
    return value.lower()


def _entry(row, parent):
    if type(row) is not dict:
        raise PanError('PAN_REPLY_INVALID')
    directory = 'fid' not in row
    fid = decimal(row.get('cid') if directory else row.get('fid'))
    actual_parent = decimal(row.get('pid') if directory else row.get('cid'))
    if fid == '0' or actual_parent != parent or directory and fid == parent:
        raise PanError('PAN_DIRECTORY_UNAVAILABLE')
    result = dict(file_id=fid, name=text(row.get('n') or row.get('fn') or row.get('file_name')),
                  size=0 if directory else _integer(row.get('s', row.get('fs'))), directory=directory)
    if not directory:
        result.update(sha1=_sha(row.get('sha') or row.get('sha1')), parent=parent)
    return result


class Client:
    def __init__(self, value, session=None):
        self.subject = credentials('115', value)[0]
        self.session = session if session is not None else Session('115', value)

    def __repr__(self):
        return '<115 personal drive: credentials hidden>'

    def list_files(self, parent='0', page=1, size=10):
        parent = decimal(parent)
        page_number(page, size)
        offset = (page - 1) * size
        value = _reply(self.session.request(WEB + '/files', query=dict(
            aid=1, cid=parent, offset=offset, limit=size, show_dir=1,
            count_folders=1, record_open_time=0, cur=1)))
        # The web API can silently return root for an invalid cid. A path is
        # authoritative even for an empty folder; row parent checks alone are
        # insufficient. Never index that fallback under the requested source.
        path = value.get('path')
        if (type(path) is not list or not path or len(path) > 256
                or any(type(row) is not dict for row in path)
                or decimal(path[-1].get('cid')) != parent):
            raise PanError('PAN_DIRECTORY_UNAVAILABLE')
        if _integer(value.get('offset')) != offset:
            raise PanError('PAN_REPLY_INVALID')
        total, rows = _integer(value.get('count')), value.get('data')
        if (type(rows) is not list or offset > total or len(rows) != min(size, total - offset)):
            raise PanError('PAN_REPLY_INVALID')
        result = listing(rows, total, page, size, lambda row: _entry(row, parent))
        operation = getattr(self.session, 'operation', None)
        if operation is not None and operation.kind == 'scan':
            # Clients are short-lived per page. Keep bounded pagination proof
            # on the existing scan operation, not a provider worker/cache.
            # A changing total or repeated file cannot close a full scan.
            progress = getattr(operation, '_115_directories', None)
            if progress is None:
                progress = operation._115_directories = {}
            previous = progress.get(parent)
            ids = {item['file_id'] for item in result['items']}
            if previous is not None:
                count, following, seen = previous
                if total != count or offset != following or seen.intersection(ids):
                    raise PanError('PAN_REPLY_INVALID')
                ids.update(seen)
            if len(progress) >= 1024 and parent not in progress or len(ids) > 12000:
                raise PanError('PAN_BUDGET_EXHAUSTED')
            progress[parent] = total, offset + len(rows), ids
        return result

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'name', 'size', 'directory', 'sha1', 'parent'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        fid, parent = decimal(selected['file_id']), decimal(selected['parent'])
        number(selected['size'], 1)
        _sha(selected['sha1'])
        value = _reply(self.session.request(WEB + '/files/get_info', query={'file_id': fid}))
        rows = value.get('data')
        if type(rows) is not list or len(rows) != 1:
            raise PanError('PAN_FILE_CHANGED')
        current = _entry(rows[0], parent)
        # get_info also knows some permanently deleted files. Only the
        # normal personal-drive area is supported; no deleted/instant area.
        if _integer(rows[0].get('aid')) != 1:
            raise PanError('PAN_DIRECTORY_UNAVAILABLE')
        if current != selected:
            raise PanError('PAN_FILE_CHANGED')
        pickcode = identifier(rows[0].get('pc'))
        payload = json.dumps(dict(pickcode=pickcode, user_id=int(self.subject)), separators=(',', ':'))
        value = _reply(self.session.request(DOWNLOAD, form={'data': cipher.encrypt(payload)}))
        try:
            files = json.loads(cipher.decrypt(value.get('data')))
        except (ValueError, UnicodeError):
            raise PanError('PAN_REPLY_INVALID') from None
        if type(files) is not dict or set(files) != {fid} or type(files[fid]) is not dict:
            raise PanError('PAN_FILE_CHANGED')
        item = files[fid]
        if (item.get('pick_code') != pickcode or item.get('file_name') != selected['name']
                or _integer(item.get('file_size')) != selected['size']
                or _sha(item.get('sha1')) != selected['sha1']):
            raise PanError('PAN_FILE_CHANGED')
        address = item.get('url')
        if type(address) is not dict:
            raise PanError('PAN_FILE_CHANGED')
        url = original_url(address.get('url'), CDN)
        if re.search(r'[\x00-\x20\x7f|]', url):
            raise PanError('PAN_DOWNLOAD_ORIGIN_REJECTED')
        # The exact request UA is required by the signed download URL. Account
        # cookies remain in the API CookieJar; never forward them to a CDN.
        return dict(url=url, size=selected['size'], original=True, headers={'User-Agent': USER_AGENT})
