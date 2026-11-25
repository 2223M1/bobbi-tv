"""Optional, TV-approved browser session over the existing local Host APIs.

This owns no sources, cloud credentials, media files, jobs or playback. Only a
short-lived single-browser permission is retained in memory.
"""
import base64
import hmac
from copy import deepcopy
from hashlib import sha256
from http.cookies import SimpleCookie
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from threading import Event, RLock
import time
from urllib.parse import urlsplit

MAX_BODY = 8192
MAX_REPLY = 16384
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_CHUNK = 4096
UPLOAD_IDLE_SECONDS = 60
UPLOAD_TOTAL_SECONDS = 300
SESSION_SECONDS = 900
COOKIE = 'bobbi_management'
SCOPES = frozenset(('catalog_read', 'catalog_review', 'catalog_tasks'))
PLAYBACK_SCOPES = frozenset(('playback_read', 'playback_control'))
STREMIO_SCOPES = frozenset(('stremio_addons',))
SOURCE_IMPORT_SCOPES = frozenset(('source_import',))
SUBTITLE_UPLOAD_SCOPES = frozenset(('subtitle_upload',))
LOCAL_SCOPES = frozenset(('stremio_addons', 'source_import', 'subtitle_upload'))
STREMIO_LIST_BUDGET = MAX_REPLY - 512
ACTION_SCOPE = {
    'catalog_sources': 'catalog_read', 'catalog_items': 'catalog_read', 'catalog_jobs': 'catalog_read',
    'catalog_history': 'catalog_read',
    'catalog_query': 'catalog_read', 'catalog_item': 'catalog_read', 'catalog_receipt': 'catalog_review',
    'catalog_candidates': 'catalog_read', 'catalog_group': 'catalog_read',
    'catalog_preview': 'catalog_review', 'catalog_apply': 'catalog_review',
    'catalog_cancel': 'catalog_tasks', 'catalog_scan': 'catalog_tasks',
    'playback_presentation': 'playback_read', 'playback_receipt': 'playback_read',
    'playback_command': 'playback_control',
    'playback_forget': 'playback_read',
    'stremio_list': 'stremio_addons',
    'stremio_detail': 'stremio_addons',
    'stremio_validate': 'stremio_addons',
    'stremio_add': 'stremio_addons',
    'stremio_toggle': 'stremio_addons',
    'stremio_remove': 'stremio_addons',
    'source_import_status': 'source_import',
    'source_import_begin': 'source_import',
    'source_import_chunk': 'source_import',
    'source_import_commit': 'source_import',
    'source_import_cancel': 'source_import',
    'subtitle_upload_status': 'subtitle_upload',
    'subtitle_upload_begin': 'subtitle_upload',
    'subtitle_upload_chunk': 'subtitle_upload',
    'subtitle_upload_commit': 'subtitle_upload',
    'subtitle_upload_cancel': 'subtitle_upload',
}
PLAYBACK_INSTANCE = ('boot_id', 'epoch', 'request_id', 'native_instance', 'file_sha256', 'selection_epoch')


def same_playback(one, two):
    return all(one.get(key) == two.get(key) for key in PLAYBACK_INSTANCE)


class PhoneError(ValueError):
    def __init__(self, code, status=403):
        super().__init__(code)
        self.status = status


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _id(value, length=32):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}' % length, value):
        raise PhoneError('INVALID_REQUEST', 400)
    return value


def _page(args):
    offset, limit = args.get('offset', 0), args.get('limit', 5)
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 5:
        raise PhoneError('INVALID_REQUEST', 400)
    return offset, limit


def parameters(action, args):
    if type(args) is not dict or len(encode(args)) > MAX_BODY:
        raise PhoneError('INVALID_REQUEST', 400)
    if action in ('stremio_list', 'stremio_detail', 'stremio_validate', 'stremio_add', 'stremio_toggle', 'stremio_remove'):
        if action == 'stremio_list':
            if not set(args) <= {'offset', 'limit'}:
                raise PhoneError('INVALID_REQUEST', 400)
            off = args.get('offset', 0)
            lim = args.get('limit', 64)
            if type(off) is not int or not 0 <= off <= 100000 or type(lim) is not int or not 1 <= lim <= 64:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'offset': off, 'limit': lim}
        if action == 'stremio_detail':
            addon_id = args.get('id')
            if set(args) != {'id'} or type(addon_id) is not str or not 0 < len(addon_id) <= 512 or '\x00' in addon_id:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'id': addon_id}
        if action in ('stremio_validate', 'stremio_add'):
            url = args.get('url')
            if (set(args) != {'url'} or type(url) is not str or not 0 < len(url.strip()) <= 2048
                    or re.search(r'[\x00-\x1f\x7f]', url)):
                raise PhoneError('INVALID_REQUEST', 400)
            return {'url': url.strip()}
        if action == 'stremio_toggle':
            addon_id, category, enabled = args.get('id'), args.get('category'), args.get('enabled')
            if (set(args) != {'id', 'category', 'enabled'} or type(addon_id) is not str
                    or not 0 < len(addon_id) <= 512 or '\x00' in addon_id
                    or category not in ('stream', 'catalog', 'tv') or type(enabled) is not bool):
                raise PhoneError('INVALID_REQUEST', 400)
            return dict(id=addon_id, category=category, enabled=enabled)
        addon_id = args.get('id')
        if set(args) != {'id'} or type(addon_id) is not str or not 0 < len(addon_id) <= 512 or '\x00' in addon_id:
            raise PhoneError('INVALID_REQUEST', 400)
        return dict(id=addon_id)
    if action.startswith('source_import_'):
        if action == 'source_import_status':
            if args:
                raise PhoneError('INVALID_REQUEST', 400)
            return {}
        if action == 'source_import_begin':
            if not ({'upload_id', 'file_name', 'total_bytes', 'sha256'} <= set(args) <= {
                'upload_id', 'file_name', 'total_bytes', 'sha256', 'base_url'
            }):
                raise PhoneError('INVALID_REQUEST', 400)
            uid = _id(args['upload_id'], 32)
            fname = args.get('file_name')
            total = args.get('total_bytes')
            digest = _id(args.get('sha256'), 64)
            base_url = args.get('base_url', '')
            if (
                type(fname) is not str or not 1 <= len(fname.strip()) <= 128
                or any(ord(c) < 32 or c in '/\\' for c in fname)
                or type(total) is not int or type(total) is bool
                or not 1 <= total <= MAX_IMPORT_BYTES
                or type(base_url) is not str or len(base_url) > 2048
                or any(ord(c) < 32 for c in base_url)
            ):
                raise PhoneError('INVALID_REQUEST', 400)
            return {
                'upload_id': uid,
                'file_name': fname.strip(),
                'total_bytes': total,
                'sha256': digest,
                'base_url': base_url.strip(),
            }
        if action == 'source_import_chunk':
            if set(args) != {'upload_id', 'offset', 'data_b64'}:
                raise PhoneError('INVALID_REQUEST', 400)
            uid = _id(args['upload_id'], 32)
            off = args.get('offset')
            b64 = args.get('data_b64')
            if (
                type(off) is not int or type(off) is bool or not 0 <= off < MAX_IMPORT_BYTES
                or type(b64) is not str or not 1 <= len(b64) <= 6000 or not b64.isascii()
            ):
                raise PhoneError('INVALID_REQUEST', 400)
            try:
                raw_chunk = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError):
                raise PhoneError('INVALID_REQUEST', 400) from None
            if not 1 <= len(raw_chunk) <= MAX_IMPORT_CHUNK:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'upload_id': uid, 'offset': off, 'chunk': raw_chunk}
        if action in ('source_import_commit', 'source_import_cancel'):
            if set(args) != {'upload_id'}:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'upload_id': _id(args['upload_id'], 32)}
        raise PhoneError('ACTION_FORBIDDEN')
    if action.startswith('subtitle_upload_'):
        from lib.services.subtitle_server import MAX_SUBTITLE_BYTES, sanitize_subtitle_filename
        if action == 'subtitle_upload_status':
            if args:
                raise PhoneError('INVALID_REQUEST', 400)
            return {}
        if action == 'subtitle_upload_begin':
            if not ({'upload_id', 'file_name', 'total_bytes', 'sha256'} <= set(args) <= {
                'upload_id', 'file_name', 'total_bytes', 'sha256', 'target_id',
            }):
                raise PhoneError('INVALID_REQUEST', 400)
            uid = _id(args['upload_id'], 32)
            total = args.get('total_bytes')
            digest = _id(args.get('sha256'), 64)
            target_id = args.get('target_id')
            if target_id is not None:
                target_id = _id(target_id, 32)
            try:
                clean_name = sanitize_subtitle_filename(args.get('file_name'))
            except ValueError as exc:
                raise PhoneError(str(exc), 400) from None
            if type(total) is not int or type(total) is bool or not 1 <= total <= MAX_SUBTITLE_BYTES:
                raise PhoneError('INVALID_REQUEST', 400)
            return {
                'upload_id': uid,
                'file_name': clean_name,
                'total_bytes': total,
                'sha256': digest,
                'target_id': target_id,
            }
        if action == 'subtitle_upload_chunk':
            if set(args) != {'upload_id', 'offset', 'data_b64'}:
                raise PhoneError('INVALID_REQUEST', 400)
            uid = _id(args['upload_id'], 32)
            off = args.get('offset')
            b64 = args.get('data_b64')
            if (
                type(off) is not int or type(off) is bool or not 0 <= off < MAX_SUBTITLE_BYTES
                or type(b64) is not str or not 1 <= len(b64) <= 6000 or not b64.isascii()
            ):
                raise PhoneError('INVALID_REQUEST', 400)
            try:
                raw_chunk = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError):
                raise PhoneError('INVALID_REQUEST', 400) from None
            if not 1 <= len(raw_chunk) <= MAX_IMPORT_CHUNK:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'upload_id': uid, 'offset': off, 'chunk': raw_chunk}
        if action in ('subtitle_upload_commit', 'subtitle_upload_cancel'):
            if set(args) != {'upload_id'}:
                raise PhoneError('INVALID_REQUEST', 400)
            return {'upload_id': _id(args['upload_id'], 32)}
        raise PhoneError('ACTION_FORBIDDEN')
    if action in ('playback_presentation', 'playback_receipt', 'playback_command', 'playback_forget'):
        from bobbi_core.playback_presentation import command, expected
        try:
            if action == 'playback_presentation' and not args:
                return {}
            if action == 'playback_command':
                return command(args)
            if action in ('playback_receipt', 'playback_forget') and set(args) == {'expected', 'command_id'}:
                return dict(expected=expected(args['expected']), command_id=_id(args['command_id']))
        except (ValueError, TypeError, KeyError):
            pass
        raise PhoneError('INVALID_REQUEST', 400)
    allowed = {
        'catalog_sources': {'offset', 'limit'}, 'catalog_items': {'source', 'state', 'offset', 'limit'},
        'catalog_jobs': {'task', 'offset', 'limit'}, 'catalog_preview': {'commands'},
        'catalog_history': {'offset', 'limit'},
        'catalog_query': {'query', 'cursor', 'limit'}, 'catalog_item': {'file_id'}, 'catalog_receipt': {'request_id'},
        'catalog_candidates': {'query', 'media_kind', 'year'},
        'catalog_group': {'file_id', 'source_id', 'offset', 'limit', 'projection_revision'},
        'catalog_apply': {'commands', 'request_id'}, 'catalog_cancel': {'task_id'}, 'catalog_scan': {'source_id'},
    }
    if action not in allowed or not set(args) <= allowed[action]:
        raise PhoneError('ACTION_FORBIDDEN')
    args = dict(args)
    if action in ('catalog_sources', 'catalog_items', 'catalog_jobs', 'catalog_history'):
        args['offset'], args['limit'] = _page(args)
        for key in ('source', 'task'):
            if args.get(key) is not None:
                _id(args[key])
        if args.get('state') not in (None, 'unmatched', 'ambiguous', 'proposed', 'confirmed', 'ignored'):
            raise PhoneError('INVALID_REQUEST', 400)
    elif action == 'catalog_candidates':
        from lib.clients.tmdb.catalog_candidates import parameters as candidate_parameters
        try:
            args = candidate_parameters(args)
        except (ValueError, TypeError):
            raise PhoneError('INVALID_REQUEST', 400) from None
    elif action == 'catalog_group':
        _id(args.get('file_id'), 64)
        args['offset'], args['limit'] = _page(args)
        if args.get('source_id') is not None:
            _id(args['source_id'])
        if args.get('projection_revision') is not None and (type(args['projection_revision']) is not int or args['projection_revision'] < 0):
            raise PhoneError('INVALID_REQUEST', 400)
    elif action == 'catalog_query':
        from bobbi_core.catalog_query import parameters as query_parameters
        try:
            args['query'] = query_parameters(args.get('query', {}))
        except (ValueError, TypeError):
            raise PhoneError('INVALID_REQUEST', 400) from None
        args['limit'] = args.get('limit', 20)
        if type(args['limit']) is not int or not 1 <= args['limit'] <= 32:
            raise PhoneError('INVALID_REQUEST', 400)
        if args.get('cursor') is not None:
            _id(args['cursor'])
    elif action in ('catalog_preview', 'catalog_apply'):
        if (set(args) != allowed[action] or type(args['commands']) is not list
                or not 1 <= len(args['commands']) <= 5):
            raise PhoneError('INVALID_REQUEST', 400)
        from bobbi_core.catalog_review import command
        try:
            args['commands'] = [command(value) for value in args['commands']]
        except (ValueError, TypeError, KeyError):
            raise PhoneError('INVALID_REQUEST', 400) from None
        if action == 'catalog_apply':
            _id(args['request_id'])
    else:
        if set(args) != allowed[action]:
            raise PhoneError('INVALID_REQUEST', 400)
        _id(next(iter(args.values())), 64 if action == 'catalog_item' else 32)
    return args


# Recursive field projection is a second, browser-specific egress boundary.
# Never pass a future Host result field through merely because the RPC is local.
PUBLIC_FIELDS = frozenset(('items', 'next_offset', 'id', 'name', 'parent', 'truncated', 'file',
    'state', 'reason', 'candidates', 'revision', 'mapping', 'provenance', 'origin', 'season',
    'episode', 'year', 'kind', 'title', 'tmdb_id', 'version', 'status', 'before', 'after', 'action',
    'schema', 'task_id', 'stage', 'counts', 'pages', 'scanned', 'discovered', 'updated_at',
    'cancel_requested', 'result_summary', 'available', 'after_state', 'position', 'duration', 'completion_reason', 'index',
    'observation', 'coverage', 'availability', 'recheck_required', 'indexed_count', 'latest_state',
    'work_title', 'version_label', 'description', 'navigation', 'view', 'parent_entity_id',
    'supplement', 'before_supplement', 'after_supplement', 'metadata_key', 'parent_file_id',
    'parent_revision', 'parent_evidence', 'observation_key', 'needs_review'))

# Query summaries have their own read budget; this never enlarges review batches.
QUERY_FIELDS = frozenset(('schema', 'items', 'next_cursor', 'projection_revision', 'truncated',
    'entity_id', 'entity_kind', 'display_title', 'media_kind', 'season', 'episode', 'review_state',
    'availability', 'variant_count', 'available_count', 'source_count', 'metadata_key', 'year', 'art', 'poster', 'thumb', 'fanart',
    'file_name', 'file_size', 'version_label', 'sources', 'source_total', 'id', 'name',
    'review_revision', 'observation_key', 'supplement', 'kind', 'title', 'parent_file_id',
    'parent_revision', 'parent_evidence', 'state'))
CANDIDATE_FIELDS = frozenset(('items', 'media_kind', 'tmdb_id', 'title', 'original_title',
                            'year', 'poster_path', 'basis', 'mismatch'))
GROUP_FIELDS = PUBLIC_FIELDS | frozenset(('group_id', 'anchor_id', 'source_id', 'projection_revision'))
PLAYBACK_FIELDS = frozenset(('available', 'reason', 'expected', 'boot_id', 'epoch', 'request_id',
    'native_instance', 'file_sha256', 'selection_epoch', 'expected_sequence', 'user_intent',
    'subtitle_intent', 'audio_intent', 'position_ms', 'duration_ms', 'can_seek', 'subtitle_visible',
    'transport_protocol', 'transport_state', 'can_pause', 'can_resume', 'can_stop',
    'subtitle_status', 'audio_status', 'audio', 'subtitles', 'chapters', 'name', 'language', 'index',
    'stream_key', 'selected', 'audio_truncated', 'subtitles_truncated', 'chapters_truncated', 'command_id', 'status'))


STREMIO_FIELDS = frozenset(('items', 'next_offset', 'total', 'addon', 'manifest', 'valid', 'success', 'id', 'name',
    'description', 'description_truncated', 'version', 'host', 'logo', 'logo_rejected', 'types', 'capabilities',
    'selected', 'stream', 'catalog', 'tv'))
SUBTITLE_UPLOAD_FIELDS = frozenset((
    'state', 'target_id', 'title', 'upload_id', 'offset', 'total_bytes',
    'cancelled', 'committed', 'file_name', 'byte_length', 'sha256',
))


def public_subtitle_upload(value, depth=0):
    if depth > 4:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {k: public_subtitle_upload(v, depth + 1) for k, v in value.items() if k in SUBTITLE_UPLOAD_FIELDS}
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 512 and '://' not in value and '\x00' not in value:
        return value
    raise PhoneError('INVALID_REPLY', 502)
SOURCE_IMPORT_FIELDS = frozenset((
    'state', 'upload_id', 'offset', 'total_bytes', 'cancelled', 'committed', 'awaiting_tv_confirm',
    'diagnosis', 'ok', 'error_code', 'sha256', 'byte_length', 'can_save_t4', 'counts',
    'type4', 'type3', 'unsupported_type', 'unsupported_headers', 'invalid', 'lives',
    'summary_zh', 'type4_names', 'type3_names', 'lives_names', 'unsupported_top_fields',
))


def public_source_import(value, depth=0):
    if depth > 6:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {k: public_source_import(v, depth + 1) for k, v in value.items() if k in SOURCE_IMPORT_FIELDS}
    if type(value) is list:
        if len(value) > 64:
            raise PhoneError('INVALID_REPLY', 502)
        return [public_source_import(v, depth + 1) for v in value]
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 1024 and '://' not in value and '\x00' not in value:
        return value
    raise PhoneError('INVALID_REPLY', 502)


def public_stremio(value, depth=0, key=None):
    if depth > 6:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {k: public_stremio(v, depth + 1, k) for k, v in value.items() if k in STREMIO_FIELDS}
    if type(value) is list:
        limit = 64 if key == 'items' else 8
        if len(value) > limit:
            raise PhoneError('INVALID_REPLY', 502)
        return [public_stremio(v, depth + 1, key) for v in value]
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 1024 and '\x00' not in value:
        if key == 'logo':
            if value == '' or re.fullmatch(r'https://image\.tmdb\.org/[A-Za-z0-9/_.-]{1,240}\.(?:jpg|jpeg|png|webp)', value, re.IGNORECASE):
                return value
            raise PhoneError('INVALID_REPLY', 502)
        if key in ('host', 'version') and '://' in value:
            raise PhoneError('INVALID_REPLY', 502)
        return value
    raise PhoneError('INVALID_REPLY', 502)


def public(value, depth=0, fields=PUBLIC_FIELDS, max_items=5):
    if depth > 6:
        raise PhoneError('INVALID_REPLY', 502)
    if type(value) is dict:
        return {key: public(item, depth + 1, fields, max_items) for key, item in value.items() if key in fields}
    if type(value) is list:
        if len(value) > max_items:
            raise PhoneError('INVALID_REPLY', 502)
        return [public(item, depth + 1, fields, max_items) for item in value]
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is str and len(value) <= 1024 and '://' not in value:
        return value
    raise PhoneError('INVALID_REPLY', 502)


class PhoneManagement:
    def __init__(
        self,
        expected,
        origin,
        rpc=None,
        clock=time.monotonic,
        scopes=SCOPES,
        profile_binding=None,
        target_current=None,
    ):
        from bobbi_platform.pan_accounts import scope
        from bobbi_platform.paths import ProfileBinding
        from bobbi_platform.runtime import bind_call
        self._target_current = target_current
        self.local_scope = (
            expected.get('local_scope')
            if type(expected) is dict and expected.get('local_scope') in LOCAL_SCOPES
            else None
        )
        if self.local_scope is not None:
            if self.local_scope == 'subtitle_upload':
                allowed_local = SUBTITLE_UPLOAD_SCOPES
                if not ({'local_scope', 'target_id'} <= set(expected) <= {
                    'local_scope', 'target_id', 'source_key', 'title',
                }):
                    raise PhoneError('INVALID_REQUEST', 400)
                target_id = _id(expected.get('target_id'), 32)
                source_key = str(expected.get('source_key') or '')[:512]
                title = str(expected.get('title') or '')[:240]
                if '\x00' in source_key or '\x00' in title:
                    raise PhoneError('INVALID_REQUEST', 400)
                local_expected = {
                    'local_scope': 'subtitle_upload',
                    'target_id': target_id,
                    'source_key': source_key,
                    'title': title,
                }
            else:
                if set(expected) != {'local_scope'}:
                    raise PhoneError('INVALID_REQUEST', 400)
                allowed_local = STREMIO_SCOPES if self.local_scope == 'stremio_addons' else SOURCE_IMPORT_SCOPES
                local_expected = dict(local_scope=self.local_scope)
            if not set(scopes) <= allowed_local:
                raise PhoneError('ACTION_FORBIDDEN')
            self.profile_binding = profile_binding or (ProfileBinding() if rpc is None else None)
            if self.profile_binding is not None:
                self.profile_binding.require_current()
            self.reference_kind = None
            self.path_source = False
            self.catalog_prefix = None
            self.expected = local_expected
        else:
            # An injected transport may supply its own binding in fixtures. The
            # production path always captures both Kodi roots and this exact Host.
            self.profile_binding = profile_binding or (ProfileBinding() if rpc is None else None)
            if rpc is None:
                rpc = bind_call(self.profile_binding.root('script.module.bobbi.platform') / 'runtime.json')
                self.profile_binding.require_current()
            self.reference_kind = expected.get('reference_kind') if type(expected) is dict else None
            from bobbi_core.typed_ref import KINDS, action_prefix
            self.path_source = self.reference_kind in KINDS
            self.catalog_prefix = action_prefix(self.reference_kind) if self.path_source else None
            if self.path_source and set(scopes) & PLAYBACK_SCOPES:
                raise PhoneError('ACTION_FORBIDDEN')
            if self.path_source:
                if set(expected) - {'reference_kind', 'source_id', 'namespace', 'generation'}:
                    raise PhoneError('INVALID_REQUEST', 400)
                self.expected = dict(reference_kind=self.reference_kind, source_id=_id(expected.get('source_id')),
                                     namespace=_id(expected.get('namespace'), 64), generation='')
                if self.reference_kind == 'network_path':
                    self.expected['generation'] = _id(expected.get('generation'), 64)
            else:
                self.expected = scope(expected, authenticated=True)
        parts = urlsplit(origin)
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            raise PhoneError('ORIGIN_FORBIDDEN') from None
        if (parts.scheme != 'http' or not (address.is_private or address.is_loopback)
                or parts.path or parts.query or parts.fragment or parts.username or parts.password
                or not parts.port or not 1 <= parts.port <= 65535
                or not set(scopes) <= SCOPES | PLAYBACK_SCOPES | STREMIO_SCOPES | SOURCE_IMPORT_SCOPES | SUBTITLE_UPLOAD_SCOPES
                or ('playback_control' in scopes and 'playback_read' not in scopes)):
            raise PhoneError('ORIGIN_FORBIDDEN')
        self.origin, self.host, self.rpc, self.clock = origin, parts.netloc, rpc, clock
        self.scopes, self.lock = frozenset(scopes), RLock()
        self.revoked = Event()
        self.previews = {}
        self._staged_import = None
        self._committed_import = None
        self._staged_subtitle = None
        self.committed_subtitle = None
        self._staging_dir = (
            Path(self.profile_binding.root('script.module.bobbi.platform')) / 'source-import-staging'
            if self.profile_binding is not None
            else None
        )
        if self.local_scope == 'source_import':
            self._sweep_orphan_import_parts()
        self._subtitle_dir = (
            Path(self.profile_binding.root('plugin.video.bobbi')) / 'Subtitles' / 'uploads'
            if self.profile_binding is not None
            else None
        )
        # Session-only correlation hints survive page reload and another tab.
        # They never execute/retry a command or replace the owner's receipts.
        self.playback_operations = {}
        self._challenge, self._session, self._csrf = secrets.token_urlsafe(32), None, None
        self.expires, self.closed = clock() + SESSION_SECONDS, False

    def __repr__(self):
        return '<Phone management: session hidden>'

    @property
    def pairing_url(self):
        with self.lock:
            if self.closed or self._challenge is None:
                raise PhoneError('SESSION_EXPIRED', 401)
            return self.origin + '/manage#' + self._challenge

    def check_origin(self, headers, write=True):
        if headers.get('Host') != self.host or write and headers.get('Origin') != self.origin:
            raise PhoneError('ORIGIN_FORBIDDEN')
        if headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            raise PhoneError('ORIGIN_FORBIDDEN')

    def _live(self):
        self._profile()
        if self.revoked.is_set() or self.closed or self.clock() >= self.expires:
            self.revoke()
            raise PhoneError('SESSION_EXPIRED', 401)

    def _profile(self):
        try:
            if self.profile_binding is not None:
                self.profile_binding.require_current()
        except (OSError, ValueError, RuntimeError):
            self._committed_import = None
            self.revoke()
            raise PhoneError('ACCOUNT_OR_SERVICE_CHANGED', 401) from None

    def _rpc(self, action, args, timeout):
        self._profile()
        result = self.rpc(action, args, timeout=timeout)
        self._profile()
        return result

    def _account(self):
        if self.local_scope is not None:
            self._profile()
            if self.local_scope == 'subtitle_upload' and self._target_current is not None:
                try:
                    still_current = bool(self._target_current())
                except Exception:
                    still_current = False
                if not still_current:
                    self.discard_committed_subtitle()
                    self.revoke()
                    raise PhoneError('SUBTITLE_TARGET_CHANGED', 409)
            return
        try:
            if self.path_source:
                current = self._rpc(self.catalog_prefix + 'scope', {'source_id': self.expected['source_id']}, timeout=2)
                if type(current) is not dict:
                    raise ValueError
                current = current.get('scope', current)
                if type(current) is not dict:
                    raise ValueError
                if any(current.get(key) != self.expected[key] for key in ('reference_kind', 'source_id', 'namespace')):
                    raise ValueError
                if self.reference_kind == 'network_path' and current.get('generation') != self.expected['generation']:
                    raise ValueError
            else:
                rows = self._rpc('pan_status', {}, timeout=2)['providers']
                current = next(row['account'] for row in rows if row['provider'] == self.expected['provider'])
                if current != self.expected:
                    raise ValueError
        except (ValueError, OSError, KeyError, TypeError, StopIteration, RuntimeError):
            self.revoke()
            raise PhoneError('ACCOUNT_OR_SERVICE_CHANGED', 401) from None

    def _host(self, action, args):
        self._profile()
        if action in ('playback_presentation', 'playback_command', 'playback_receipt'):
            body = dict(operation=action, account_scope=self.expected)
            if action == 'playback_command':
                body['command'] = args
            else:
                body.update(args)
            return self._rpc('playback', body, timeout=3)
        if not self.path_source:
            return self._rpc(action, dict(args, expected=self.expected), timeout=3)
        if action == 'catalog_history':
            raise PhoneError('ACTION_FORBIDDEN')
        for value in (args.get('source'), args.get('source_id'), (args.get('query') or {}).get('source_id')):
            if value is not None and value != self.expected['source_id']:
                raise PhoneError('ACTION_FORBIDDEN')
        if action == 'catalog_sources':
            listed = self._rpc(self.catalog_prefix + 'sources', {}, timeout=3)
            # The browser grant covers exactly one registered namespace. Keep
            # other source names and observations out of its public response.
            return dict(items=[row for row in listed['items'] if row['id'] == self.expected['source_id']])
        params = dict(args, source_id=self.expected['source_id'], namespace=self.expected['namespace'])
        if self.reference_kind == 'network_path':
            params['generation'] = self.expected['generation']
        return self._rpc(action.replace('catalog_', self.catalog_prefix, 1), params, timeout=3)

    def _session_description(self):
        return dict(csrf=self._csrf, expires_in=int(self.expires - self.clock()),
                    scopes=sorted(self.scopes),
                    playback_operations=deepcopy(list(self.playback_operations.values())),
                    catalog_kind=('stremio' if self.local_scope == 'stremio_addons' else
                                  'source_import' if self.local_scope == 'source_import' else
                                  'subtitle_upload' if self.local_scope == 'subtitle_upload' else
                                  'local' if self.reference_kind == 'local_path' else
                                  'network' if self.reference_kind == 'network_path' else
                                  'mounted' if self.path_source else 'native'),
                    source_id=self.expected['source_id'] if self.path_source else None, **_phone_locale_payload(self.scopes))

    def _remember_playback(self, args):
        prior = self.playback_operations.get(args['command_id'])
        if prior is not None:
            if prior['command'] != args:
                raise PhoneError('PLAYBACK_COMMAND_CONFLICT', 409)
            return False  # Duplicate POST is converted to a receipt read.
        for record in self.playback_operations.values():
            if record['status'] in ('queued', 'unknown') and same_playback(record['command']['expected'], args['expected']):
                raise PhoneError('PLAYBACK_PENDING', 409)
        if len(self.playback_operations) >= 8:
            settled = next((key for key, row in self.playback_operations.items()
                            if row['status'] in ('applied', 'rejected', 'failed')), None)
            if settled is None:
                raise PhoneError('PLAYBACK_JOURNAL_FULL', 409)
            del self.playback_operations[settled]
        self.playback_operations[args['command_id']] = dict(command=deepcopy(args), status='unknown')
        return True

    def _observe_playback(self, args, result):
        record = self.playback_operations.get(args['command_id'])
        if (record is not None and record['command']['expected'] == args['expected']
                and record['status'] not in ('applied', 'rejected', 'failed')
                and result.get('command_id') == args['command_id']
                and result.get('status') in ('queued', 'applied', 'rejected', 'failed', 'unknown')):
            record['status'] = result['status']

    def _forget_playback(self, args):
        record = self.playback_operations.get(args['command_id'])
        if record is not None:
            if record['command']['expected'] != args['expected']:
                raise PhoneError('PLAYBACK_COMMAND_CONFLICT', 409)
            # Both UI and server recheck: a stale browser cannot discard the
            # only recovery hint for the current instance.
            from bobbi_core.playback_presentation import expected
            try:
                fresh = self._host('playback_presentation', {})
                distinct = (type(fresh) is dict and fresh.get('available') is True and
                            not same_playback(expected(fresh.get('expected')), args['expected']))
            except (ValueError, OSError, RuntimeError):
                distinct = False
            if not distinct:
                raise PhoneError('PLAYBACK_PENDING', 409)
            self._account()
            self._live()
            self.playback_operations.pop(args['command_id'], None)
        return dict(command_id=args['command_id'], status='forgotten')

    def _authorize(self, headers, csrf=True):
        self._live()
        try:
            cookie = SimpleCookie()
            cookie.load(headers.get('Cookie', ''))
            token = cookie[COOKIE].value
        except (KeyError, TypeError, ValueError):
            raise PhoneError('PAIRING_REQUIRED', 401) from None
        if (self._session is None or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token)
                or not hmac.compare_digest(token, self._session)):
            raise PhoneError('PAIRING_REQUIRED', 401)
        receipt = headers.get('X-Bobbi-CSRF', '')
        if csrf and (not re.fullmatch(r'[A-Za-z0-9_-]{43}', receipt)
                     or not hmac.compare_digest(receipt, self._csrf)):
            raise PhoneError('CSRF_REJECTED')

    def handle(self, path, headers, raw):
        """Return result + optional cookie; all writes happen after this gate."""
        with self.lock:
            self.check_origin(headers)
            self._live()
            if len(raw) > MAX_BODY:
                raise PhoneError('REQUEST_TOO_LARGE', 413)
            try:
                body = json.loads(raw)
                if type(body) is not dict:
                    raise ValueError
            except (ValueError, TypeError):
                raise PhoneError('INVALID_REQUEST', 400) from None
            if path == '/manage/api/pair':
                code = body.get('code')
                if (set(body) != {'code'} or type(code) is not str or len(code) != 43
                        or self._challenge is None or not hmac.compare_digest(code, self._challenge)):
                    raise PhoneError('PAIRING_REJECTED', 401)
                self._account()
                self._challenge = None
                self._session, self._csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                return self._session_description(), (
                    COOKIE + '=' + self._session + '; HttpOnly; SameSite=Strict; Path=/manage/api; Max-Age=900')
            self._authorize(headers, csrf=path != '/manage/api/session')
            self._account()
            if path == '/manage/api/session' and not body:
                return self._session_description(), None
            if path == '/manage/api/revoke' and not body:
                self.revoke()
                return dict(revoked=True), COOKIE + '=; HttpOnly; SameSite=Strict; Path=/manage/api; Max-Age=0'
            if path != '/manage/api' or set(body) != {'action', 'params'}:
                raise PhoneError('ACTION_FORBIDDEN')
            action = body['action']
            if type(action) is not str or ACTION_SCOPE.get(action) not in self.scopes:
                raise PhoneError('ACTION_FORBIDDEN')
            args = parameters(action, body['params'])
            if action.startswith('stremio_'):
                return self._handle_stremio(action, args)
            if action.startswith('source_import_'):
                return self._handle_source_import(action, args)
            if action.startswith('subtitle_upload_'):
                return self._handle_subtitle_upload(action, args)
            if action == 'playback_forget':
                return self._forget_playback(args), None
            if action == 'playback_command' and not self._remember_playback(args):
                action = 'playback_receipt'
                args = {key: args[key] for key in ('expected', 'command_id')}
            digest = sha256(encode(args.get('commands', []))).hexdigest()
            if action == 'catalog_apply' and self.clock() - self.previews.get(digest, float('-inf')) > 120:
                raise PhoneError('PREVIEW_REQUIRED', 409)
            self._live()
            host_args = {} if action == 'catalog_sources' else args
            try:
                if action == 'catalog_candidates':
                    from lib.clients.tmdb.catalog_candidates import search
                    try:
                        result = search(**args, cancelled=self.revoked.is_set)
                    except (ValueError, OSError, RuntimeError):
                        self._live()
                        raise PhoneError('CATALOG_CANDIDATE_UNAVAILABLE', 502) from None
                else:
                    result = self._host(action, host_args)
            except PhoneError:
                raise
            except (ValueError, OSError, RuntimeError) as error:
                if action in ('playback_command', 'playback_receipt'):
                    # The owner may have accepted before the response was lost.
                    # Keep the original ID only while its grant is still live.
                    self._account()
                    self._live()
                    return dict(command_id=args['command_id'], status='unknown'), None
                from bobbi_platform.runtime import CATALOG_ERRORS
                code = str(error)
                if code in CATALOG_ERRORS and code not in ('CATALOG_ACCOUNT_MISMATCH', 'CATALOG_SERVICE_CLOSED',
                        'CATALOG_SCHEMA_UNSUPPORTED', 'CATALOG_STORAGE_UNSAFE', 'CATALOG_PROFILE_CHANGED'):
                    raise PhoneError(code, 409 if code == 'CATALOG_SCAN_BUSY' else 400) from None
                self.revoke()
                raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
            self._account()
            self._live()
            if action == 'catalog_sources':
                rows, offset, limit = result['items'], args['offset'], args['limit']
                result = dict(items=rows[offset:offset+limit], next_offset=(offset+limit if len(rows) > offset+limit else None))
            if action in ('playback_presentation', 'playback_command', 'playback_receipt'):
                result = public(result, fields=PLAYBACK_FIELDS, max_items=32)
            elif action == 'catalog_query':
                result = public(result, fields=QUERY_FIELDS, max_items=32)
            else:
                fields = CANDIDATE_FIELDS if action == 'catalog_candidates' else GROUP_FIELDS if action == 'catalog_group' else PUBLIC_FIELDS
                result = public(result, fields=fields)
            if len(encode(result)) > MAX_REPLY:
                raise PhoneError('REPLY_TOO_LARGE', 502)
            if action in ('playback_command', 'playback_receipt'):
                self._observe_playback(args, result)
            if action == 'catalog_preview':
                self.previews[digest] = self.clock()
                while len(self.previews) > 8:
                    del self.previews[next(iter(self.previews))]
            return result, None

    def _handle_stremio(self, action, args):
        from lib.services.webserver import (
            commit_stremio_addon,
            format_stremio_addon,
            get_stremio_addon,
            list_stremio_addons,
            prepare_stremio_addon,
            remove_stremio_addon,
            toggle_stremio_addon,
        )
        self._live()
        self._account()
        if action == 'stremio_list':
            all_items = list_stremio_addons(summary=True)
            total = len(all_items)
            offset = args.get('offset', 0)
            limit = args.get('limit', 64)
            sliced = all_items[offset : offset + limit] if offset < total else []
            page_items = []
            for row in sliced:
                candidate = {
                    'items': [*page_items, row],
                    'total': total,
                    'next_offset': (offset + len(page_items) + 1) if (offset + len(page_items) + 1 < total) else None,
                }
                if page_items and len(encode(public_stremio(candidate))) > STREMIO_LIST_BUDGET:
                    break
                page_items.append(row)
            next_offset = (offset + len(page_items)) if (offset + len(page_items) < total and page_items) else None
            result = dict(items=page_items, total=total, next_offset=next_offset)
        elif action == 'stremio_detail':
            detail = get_stremio_addon(args['id'])
            if detail is None:
                raise PhoneError('STREMIO_ADDON_NOT_FOUND', 404)
            result = dict(addon=detail)
        elif action in ('stremio_validate', 'stremio_add'):
            self.lock.release()
            try:
                resolved_url, manifest, error = prepare_stremio_addon(args['url'])
            finally:
                self.lock.acquire()
            self._account()
            self._live()
            if error is not None:
                raise PhoneError(error, 409 if error == 'STREMIO_ADDON_EXISTS' else 400)
            if action == 'stremio_validate':
                summary = format_stremio_addon(dict(manifest=manifest, transportUrl=resolved_url))
                result = dict(valid=True, manifest=summary)
            else:
                addon, commit_error = commit_stremio_addon(resolved_url, manifest)
                if commit_error is not None or addon is None:
                    raise PhoneError(commit_error or 'STREMIO_ADDON_UNAVAILABLE',
                                     409 if commit_error == 'STREMIO_ADDON_EXISTS' else 400)
                result = dict(success=True, addon=format_stremio_addon(addon))
        elif action == 'stremio_toggle':
            if not toggle_stremio_addon(args['id'], args['category'], args['enabled']):
                raise PhoneError('STREMIO_ADDON_NOT_FOUND', 404)
            result = dict(success=True)
        else:
            if not remove_stremio_addon(args['id']):
                raise PhoneError('STREMIO_ADDON_NOT_FOUND', 404)
            result = dict(success=True)
        self._account()
        self._live()
        projected = public_stremio(result)
        if len(encode(projected)) > MAX_REPLY:
            raise PhoneError('REPLY_TOO_LARGE', 502)
        return projected, None

    @property
    def committed_import(self):
        with self.lock:
            ci = getattr(self, '_committed_import', None)
            if ci is None:
                return None
            if self.profile_binding is not None:
                try:
                    if not self.profile_binding.is_current():
                        self._committed_import = None
                        return None
                except Exception:
                    self._committed_import = None
                    return None
            return ci

    @committed_import.setter
    def committed_import(self, value):
        with self.lock:
            self._committed_import = value

    def consume_committed_import(self) -> dict | None:
        """Atomically hand off and clear the verified committed import for the current profile."""
        with self.lock:
            ci = self.committed_import
            self._committed_import = None
            return ci

    def reject_committed_import(self) -> None:
        """Destroy a pending committed import handoff when TV confirmation is declined."""
        with self.lock:
            self._committed_import = None

    def _sweep_orphan_import_parts(self):
        sdir = getattr(self, '_staging_dir', None)
        if sdir is None or not sdir.is_dir():
            return
        try:
            for child in list(sdir.iterdir()):
                if child.is_file() and child.name.endswith('.part'):
                    try:
                        child.unlink(missing_ok=True)
                    except OSError:
                        pass
            if not any(sdir.iterdir()):
                sdir.rmdir()
        except OSError:
            pass

    def _check_staged_import_timeouts(self):
        staged = getattr(self, '_staged_import', None)
        if staged is None:
            return
        now = self.clock()
        if (
            now - staged['updated_at'] > UPLOAD_IDLE_SECONDS
            or now - staged['started_at'] > UPLOAD_TOTAL_SECONDS
        ):
            self._cleanup_staged_import()
            raise PhoneError('UPLOAD_TIMEOUT', 408)

    def _cleanup_staged_import(self):
        staged = getattr(self, '_staged_import', None)
        self._staged_import = None
        if staged and staged.get('path') is not None:
            try:
                Path(staged['path']).unlink(missing_ok=True)
            except OSError:
                pass
        sdir = getattr(self, '_staging_dir', None)
        if sdir is not None and sdir.is_dir():
            try:
                if not any(sdir.iterdir()):
                    sdir.rmdir()
            except OSError:
                pass

    @staticmethod
    def _project_diagnosis(diag: dict) -> dict:
        return {
            'ok': bool(diag.get('ok')),
            'error_code': diag.get('error_code'),
            'sha256': diag.get('sha256', ''),
            'byte_length': int(diag.get('byte_length') or 0),
            'can_save_t4': bool(diag.get('can_save_t4')),
            'counts': dict(diag.get('counts') or {}),
            'summary_zh': str(diag.get('summary_zh') or '')[:900],
            'type4_names': [str(s.get('name') or s.get('key') or '')[:80] for s in (diag.get('type4_sites') or [])[:24]],
            'type3_names': [str(s.get('name') or s.get('key') or '')[:80] for s in (diag.get('type3_spiders') or [])[:24]],
            'lives_names': [str(s.get('name') or '')[:80] for s in (diag.get('lives_subscriptions') or [])[:16]],
            'unsupported_top_fields': [str(k)[:40] for k in (diag.get('unsupported_top_fields') or [])[:16]],
        }

    def _handle_source_import(self, action, args):
        from bobbi_core import t4
        self._live()
        self._account()
        if self._staging_dir is None:
            raise PhoneError('MANAGEMENT_UNAVAILABLE', 503)

        if action in ('source_import_status', 'source_import_chunk', 'source_import_commit'):
            self._check_staged_import_timeouts()

        if action == 'source_import_status':
            if self._staged_import is not None:
                st = self._staged_import
                res = {
                    'state': 'receiving',
                    'upload_id': st['upload_id'],
                    'offset': st['offset'],
                    'total_bytes': st['total_bytes'],
                }
            elif self.committed_import is not None:
                ci = self.committed_import
                res = {
                    'state': 'committed',
                    'committed': True,
                    'awaiting_tv_confirm': bool(ci['diagnosis'].get('can_save_t4')),
                    'diagnosis': self._project_diagnosis(ci['diagnosis']),
                }
            else:
                res = {'state': 'idle'}
            return public_source_import(res), None

        if action == 'source_import_begin':
            self._cleanup_staged_import()
            self.committed_import = None
            self._staging_dir.mkdir(parents=True, exist_ok=True)
            part_path = self._staging_dir / (args['upload_id'] + '.part')
            try:
                part_path.unlink(missing_ok=True)
                fd = os.open(str(part_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except OSError:
                raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
            now_ts = self.clock()
            self._staged_import = {
                'upload_id': args['upload_id'],
                'file_name': args['file_name'],
                'total_bytes': args['total_bytes'],
                'sha256': args['sha256'],
                'base_url': args['base_url'],
                'offset': 0,
                'path': part_path,
                'started_at': now_ts,
                'updated_at': now_ts,
            }
            res = {
                'state': 'receiving',
                'upload_id': args['upload_id'],
                'offset': 0,
                'total_bytes': args['total_bytes'],
            }
            return public_source_import(res), None

        if action == 'source_import_cancel':
            if self._staged_import and self._staged_import['upload_id'] == args['upload_id']:
                self._cleanup_staged_import()
            return public_source_import({'state': 'idle', 'cancelled': True}), None

        staged = self._staged_import
        if staged is None or staged['upload_id'] != args['upload_id']:
            raise PhoneError('UPLOAD_NOT_FOUND', 404)

        if action == 'source_import_chunk':
            off = args['offset']
            chunk = args['chunk']
            cur_off = staged['offset']
            if off == cur_off:
                if cur_off + len(chunk) > staged['total_bytes']:
                    self._cleanup_staged_import()
                    raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
                try:
                    with open(staged['path'], 'ab') as fh:
                        fh.write(chunk)
                except OSError:
                    self._cleanup_staged_import()
                    raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
                staged['offset'] = cur_off + len(chunk)
            elif off < cur_off and off + len(chunk) <= cur_off:
                # Idempotent retry verification: exact byte match at previously written offset!
                try:
                    with open(staged['path'], 'rb') as fh:
                        fh.seek(off)
                        existing = fh.read(len(chunk))
                except OSError:
                    self._cleanup_staged_import()
                    raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
                if not hmac.compare_digest(existing, chunk):
                    self._cleanup_staged_import()
                    raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
            else:
                self._cleanup_staged_import()
                raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
            staged['updated_at'] = self.clock()
            res = {
                'state': 'receiving',
                'upload_id': staged['upload_id'],
                'offset': staged['offset'],
                'total_bytes': staged['total_bytes'],
            }
            return public_source_import(res), None

        # source_import_commit
        if staged['offset'] != staged['total_bytes']:
            raise PhoneError('UPLOAD_INCOMPLETE', 409)
        try:
            raw_bytes = Path(staged['path']).read_bytes()
        except OSError:
            self._cleanup_staged_import()
            raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
        self._cleanup_staged_import()
        actual_sha = sha256(raw_bytes).hexdigest()
        if not hmac.compare_digest(actual_sha, staged['sha256']) or len(raw_bytes) != staged['total_bytes']:
            raise PhoneError('UPLOAD_HASH_MISMATCH', 400)
        diag = t4.diagnose_config(raw_bytes, base_url=staged['base_url'])
        can_save = bool(diag.get('can_save_t4'))
        self.committed_import = {
            'file_name': staged['file_name'],
            'base_url': staged['base_url'],
            'raw_bytes': raw_bytes if can_save else None,
            'diagnosis': diag,
        }
        res = {
            'state': 'committed',
            'committed': True,
            'awaiting_tv_confirm': can_save,
            'diagnosis': self._project_diagnosis(diag),
        }
        projected = public_source_import(res)
        if len(encode(projected)) > MAX_REPLY:
            raise PhoneError('REPLY_TOO_LARGE', 502)
        return projected, None

    def _cleanup_staged_subtitle(self):
        staged = getattr(self, '_staged_subtitle', None)
        self._staged_subtitle = None
        if staged and staged.get('path') is not None:
            try:
                Path(staged['path']).unlink(missing_ok=True)
            except OSError:
                pass

    def discard_committed_subtitle(self):
        with self.lock:
            self._cleanup_staged_subtitle()
            committed = self.committed_subtitle
            self.committed_subtitle = None
        if committed and committed.get('path'):
            try:
                Path(committed['path']).unlink(missing_ok=True)
            except OSError:
                pass

    def consume_committed_subtitle(self, expected_target_id: str, expected_source_key: str | None = None) -> dict | None:
        """Atomically consume an uploaded subtitle strictly bound to profile, target_id, and source_key."""
        with self.lock:
            committed = self.committed_subtitle
            self.committed_subtitle = None
        if not committed:
            return None
        ok = True
        try:
            if self.profile_binding is not None and not self.profile_binding.is_current():
                ok = False
            if self._target_current is not None and not self._target_current():
                ok = False
        except Exception:
            ok = False
        if (
            not ok
            or committed.get('target_id') != expected_target_id
            or (expected_source_key is not None and committed.get('source_key') != expected_source_key)
        ):
            try:
                Path(committed['path']).unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return committed

    def _handle_subtitle_upload(self, action, args):
        from lib.services.subtitle_server import store_validated_subtitle
        self._live()
        self._account()
        if self._subtitle_dir is None:
            raise PhoneError('MANAGEMENT_UNAVAILABLE', 503)
        target_id = self.expected['target_id']
        title = self.expected.get('title', '')

        if action == 'subtitle_upload_status':
            if self._staged_subtitle is not None:
                st = self._staged_subtitle
                res = {
                    'state': 'receiving',
                    'target_id': target_id,
                    'title': title,
                    'upload_id': st['upload_id'],
                    'offset': st['offset'],
                    'total_bytes': st['total_bytes'],
                }
            elif self.committed_subtitle is not None:
                cs = self.committed_subtitle
                res = {
                    'state': 'committed',
                    'target_id': target_id,
                    'title': title,
                    'committed': True,
                    'file_name': cs['file_name'],
                    'byte_length': cs['byte_length'],
                    'sha256': cs['sha256'],
                }
            else:
                res = {'state': 'idle', 'target_id': target_id, 'title': title}
            return public_subtitle_upload(res), None

        if action == 'subtitle_upload_begin':
            if args.get('target_id') is not None and args['target_id'] != target_id:
                raise PhoneError('SUBTITLE_TARGET_CHANGED', 409)
            self.discard_committed_subtitle()
            self._subtitle_dir.mkdir(parents=True, exist_ok=True)
            part_path = self._subtitle_dir / ('.part-' + args['upload_id'])
            try:
                part_path.unlink(missing_ok=True)
                fd = os.open(str(part_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except OSError:
                raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
            self._staged_subtitle = {
                'upload_id': args['upload_id'],
                'file_name': args['file_name'],
                'total_bytes': args['total_bytes'],
                'sha256': args['sha256'],
                'offset': 0,
                'path': part_path,
            }
            return public_subtitle_upload({
                'state': 'receiving',
                'target_id': target_id,
                'upload_id': args['upload_id'],
                'offset': 0,
                'total_bytes': args['total_bytes'],
            }), None

        if action == 'subtitle_upload_cancel':
            if self._staged_subtitle and self._staged_subtitle['upload_id'] == args['upload_id']:
                self._cleanup_staged_subtitle()
            self.discard_committed_subtitle()
            return public_subtitle_upload({'state': 'idle', 'target_id': target_id, 'cancelled': True}), None

        staged = self._staged_subtitle
        if staged is None or staged['upload_id'] != args['upload_id']:
            raise PhoneError('UPLOAD_NOT_FOUND', 404)

        if action == 'subtitle_upload_chunk':
            off = args['offset']
            chunk = args['chunk']
            cur_off = staged['offset']
            if off == cur_off:
                if cur_off + len(chunk) > staged['total_bytes']:
                    self._cleanup_staged_subtitle()
                    raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
                try:
                    with open(staged['path'], 'ab') as fh:
                        fh.write(chunk)
                except OSError:
                    self._cleanup_staged_subtitle()
                    raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
                staged['offset'] = cur_off + len(chunk)
            elif off < cur_off and off + len(chunk) <= cur_off:
                try:
                    with open(staged['path'], 'rb') as fh:
                        fh.seek(off)
                        existing = fh.read(len(chunk))
                except OSError:
                    self._cleanup_staged_subtitle()
                    raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
                if not hmac.compare_digest(existing, chunk):
                    self._cleanup_staged_subtitle()
                    raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
            else:
                self._cleanup_staged_subtitle()
                raise PhoneError('CHUNK_OFFSET_MISMATCH', 409)
            return public_subtitle_upload({
                'state': 'receiving',
                'target_id': target_id,
                'upload_id': staged['upload_id'],
                'offset': staged['offset'],
                'total_bytes': staged['total_bytes'],
            }), None

        # subtitle_upload_commit
        if staged['offset'] != staged['total_bytes']:
            raise PhoneError('UPLOAD_INCOMPLETE', 409)
        try:
            raw_bytes = Path(staged['path']).read_bytes()
        except OSError:
            self._cleanup_staged_subtitle()
            raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
        self._cleanup_staged_subtitle()
        actual_sha = sha256(raw_bytes).hexdigest()
        if not hmac.compare_digest(actual_sha, staged['sha256']) or len(raw_bytes) != staged['total_bytes']:
            raise PhoneError('UPLOAD_HASH_MISMATCH', 400)
        self._account()
        self._live()
        try:
            stored = store_validated_subtitle(self._subtitle_dir, staged['file_name'], raw_bytes)
        except ValueError as exc:
            raise PhoneError(str(exc), 400) from None
        except OSError:
            raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
        self.committed_subtitle = {
            **stored,
            'target_id': target_id,
            'source_key': self.expected.get('source_key', ''),
        }
        return public_subtitle_upload({
            'state': 'committed',
            'target_id': target_id,
            'committed': True,
            'file_name': stored['file_name'],
            'byte_length': stored['byte_length'],
            'sha256': stored['sha256'],
        }), None

    def handle_subtitle_multipart(self, headers, rfile):
        """Bounded paired multipart subtitle upload endpoint requiring session Cookie + Origin + CSRF."""
        from lib.services.subtitle_server import parse_bounded_multipart, store_validated_subtitle
        with self.lock:
            self.check_origin(headers)
            self._authorize(headers, csrf=True)
            self._account()
            if 'subtitle_upload' not in self.scopes or self._subtitle_dir is None:
                raise PhoneError('ACTION_FORBIDDEN')
            target_id = self.expected['target_id']
        filename, content_or_err = parse_bounded_multipart(headers, rfile)
        if filename is None:
            raise PhoneError('INVALID_SUBTITLE_MULTIPART', 400)
        with self.lock:
            self._live()
            self._account()
            self.discard_committed_subtitle()
            try:
                stored = store_validated_subtitle(self._subtitle_dir, filename, content_or_err)
            except ValueError as exc:
                raise PhoneError(str(exc), 400) from None
            except OSError:
                raise PhoneError('MANAGEMENT_UNAVAILABLE', 503) from None
            self.committed_subtitle = {
                **stored,
                'target_id': target_id,
                'source_key': self.expected.get('source_key', ''),
            }
            return public_subtitle_upload({
                'state': 'committed',
                'target_id': target_id,
                'committed': True,
                'file_name': stored['file_name'],
                'byte_length': stored['byte_length'],
                'sha256': stored['sha256'],
            }), None

    def revoke(self):
        # Immediate logical revocation, even while an already-admitted domain
        # call is in flight. This does not undo a committed mapping mutation.
        self.revoked.set()
        self.closed = True
        self._session = self._csrf = self._challenge = None
        self.playback_operations.clear()
        self._cleanup_staged_import()
        self._cleanup_staged_subtitle()


def _phone_locale_payload(scopes):
    try:
        from lib.services.phone_l10n import session_locale_payload
    except ImportError:
        import importlib.util
        import sys
        mod = sys.modules.get('bobbi_phone_l10n')
        if mod is None:
            spec = importlib.util.spec_from_file_location(
                'bobbi_phone_l10n', Path(__file__).with_name('phone_l10n.py'))
            mod = importlib.util.module_from_spec(spec)
            sys.modules['bobbi_phone_l10n'] = mod
            spec.loader.exec_module(mod)
        session_locale_payload = mod.session_locale_payload
    return session_locale_payload(scopes)
