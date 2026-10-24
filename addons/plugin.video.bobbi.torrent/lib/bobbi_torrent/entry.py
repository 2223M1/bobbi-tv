"""Strict plugin entry; one pending Kodi handle, one successful handoff at most."""
import json
import re
import sys
from urllib.parse import parse_qsl, urlsplit

from .backend import Backend, BackendError, load_config
from .owner import Owner
from .resolver import Resolver, checked_expected_file


def failure_log(error, request_id=''):
    """A closed diagnostic schema; input strings never become log details."""
    reason = error.code if isinstance(error, BackendError) else ''
    if not isinstance(reason, str) or not re.fullmatch(r'TORRENT_[A-Z_]{1,80}', reason):
        reason = 'TORRENT_RESOLVER_FAILED'
    detail = {}
    if isinstance(request_id, str) and re.fullmatch('[0-9a-f]{32}', request_id):
        detail['request_id'] = request_id
    diagnostic = error.diagnostic if isinstance(error, BackendError) else {}
    if isinstance(diagnostic, dict):
        stage = diagnostic.get('stage')
        if stage in ('backend', 'download', 'add', 'metadata', 'metadata_schema',
                     'binding', 'selector', 'filename_identity', 'movie_identity',
                     'buffering', 'final_selection'):
            detail['stage'] = stage
        for key, allowed in (('operation', ('echo', 'add', 'upload', 'status', 'preload', 'other')),
                             ('method', ('GET', 'POST')),
                             ('substage', ('manual_recheck', 'manual_wait', 'add_reconcile'))):
            value = diagnostic.get(key)
            if isinstance(value, str) and value in allowed:
                detail[key] = value
        for key in ('http_status', 'initial_http_status'):
            value = diagnostic.get(key)
            if type(value) is int and 100 <= value <= 599:
                detail[key] = value
        for key in ('file_count', 'candidate_count', 'metadata_polls'):
            value = diagnostic.get(key)
            if type(value) is int and 0 <= value <= 4096:
                detail[key] = value
        if type(diagnostic.get('binding_present')) is bool:
            detail['binding_present'] = diagnostic['binding_present']
        for key in ('elapsed_ms', 'torrent_preloaded', 'torrent_preload_target',
                    'selected_file_bytes', 'peers', 'download_bps'):
            value = diagnostic.get(key)
            if type(value) is int and 0 <= value <= 512*1024**3:
                detail[key] = value
        timings = diagnostic.get('stage_ms')
        if isinstance(timings, dict):
            detail['stage_ms'] = {k: v for k, v in timings.items()
                if k in ('backend', 'download', 'add', 'metadata', 'selector', 'buffering', 'final_selection')
                and type(v) is int and 0 <= v <= 1200000}
    return '[BOBBI-TORRENT] reason=' + reason + ' detail=' + json.dumps(
        detail, sort_keys=True, separators=(',', ':'))


def parse_request(argv):
    if len(argv) < 3 or not isinstance(argv[2], str) or len(argv[2]) > 32768:
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    pairs = parse_qsl(argv[2].lstrip('?'), keep_blank_values=True, max_num_fields=24)
    if len({key for key, _ in pairs}) != len(pairs):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    request = dict(pairs)
    action = urlsplit(argv[0]).path.strip('/')
    if action not in ('play_magnet', 'play_url'):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    fields = {'magnet', 'url', 'title', 'description', 'poster', 'category',
              'season', 'episode', 'release_title', 'selection_policy', 'request_id',
              'episode_binding', 'movie_binding', 'original_audio_hint', 'expected_file', 'ready_context'}
    if (set(request) - fields or request.get('selection_policy') != 'exact'
            or not re.fullmatch('[0-9a-f]{32}', request.get('request_id', ''))):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    locator = 'magnet' if action == 'play_magnet' else 'url'
    if not request.get(locator) or len(request[locator]) > 16384:
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    if action == 'play_magnet' and not request[locator].startswith('magnet:?'):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    if action == 'play_url' and urlsplit(request[locator]).scheme not in ('http', 'https'):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    for key in ('episode_binding', 'movie_binding'):
        if len(request.get(key, '').encode('utf-8')) > 2048:
            raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    for key in fields - {'magnet', 'url', 'expected_file'}:
        if len(request.get(key, '')) > 4096:
            raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request')
    if 'expected_file' in request:
        checked_expected_file(request['expected_file'])
    if 'ready_context' in request:
        try:
            from bobbi_core.prepared_retry import decode_context
            decode_context(request['ready_context'], request['request_id'])
        except (ValueError, RuntimeError, TypeError):
            raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request') from None
    request['action'] = action
    return request


def execute(request, owner, backend, download_session, list_item, resolve_url,
            resolver_factory=Resolver):
    """Injectable workflow; an uncertain Kodi response is never retried."""
    answered = False
    try:
        result = resolver_factory(backend, owner, download_session).resolve(request)
        owner.active()
        item = list_item(label=request.get('title') or result['file']['path'], path=result['url'])
        item.setProperty('IsPlayable', 'true')
        item.setProperty('no-ext-subs-scan', 'true')
        tag = item.getVideoInfoTag()
        tag.setTitle(request.get('title') or result['file']['path'])
        if request.get('description'):
            tag.setPlot(request['description'])
        if request.get('poster'):
            item.setArt({'poster': request['poster']})
        owner.progress('starting', 100)
        owner.bind(item, result['info_hash'], result['file'], result['url'],
            result['resolution'], request.get('original_audio_hint', ''),
            result.get('file_evidence', 'AUTO_VERIFIED_FILE'))
        owner.selected(result['info_hash'], result['file'], final_url=result['url'])
        owner.active()
        answered = True  # Kodi may accept a throwing call; never answer it twice.
        resolve_url(True, item)
        return True
    except Exception as error:
        category = error.category if isinstance(error, BackendError) else 'playback_failed'
        if category != 'prepared_ready':
            owner.failure(category)
        if not answered:
            answered = True
            resolve_url(False, list_item())
            if category == 'prepared_ready':
                # No receipt if Kodi's answer throws or has an unknown outcome.
                # main publishes only after both owned IO sessions have closed.
                owner.prepared_ready_answered = True
        raise


def main(argv=None):
    import xbmc
    import xbmcgui
    import xbmcplugin
    import requests
    argv = sys.argv if argv is None else argv
    owner = backend = session = None
    entered = False
    try:
        request = parse_request(argv)
        owner = Owner(request['request_id'])
        owner.active()
        def cancelled():
            owner.active()
            return xbmc.Monitor().abortRequested()
        try:
            config = load_config()
        except BackendError as error:
            if error.code != 'TORRENT_BACKEND_NOT_CONFIGURED':
                raise
            from .backend import playback_config
            config = playback_config(cancelled=cancelled)
        backend = Backend(config)
        session = requests.Session()
        entered = True
        execute(request, owner, backend, session, xbmcgui.ListItem,
            lambda success, item: xbmcplugin.setResolvedUrl(int(argv[1]), success, item))
    except Exception as error:
        if owner is not None and not entered:
            owner.failure(error.category if isinstance(error, BackendError) else 'playback_failed')
        if not entered:
            try:
                xbmcplugin.setResolvedUrl(int(argv[1]), False, xbmcgui.ListItem())
            except Exception:
                pass
        level = xbmc.LOGINFO if isinstance(error, BackendError) and error.category == 'prepared_ready' else xbmc.LOGWARNING
        xbmc.log(failure_log(error, owner.request_id if owner is not None else ''), level)
    finally:
        try:
            if backend is not None:
                backend.close()
        finally:
            if session is not None:
                session.close()
        if owner is not None and getattr(owner, 'prepared_ready_answered', False):
            owner.failure('prepared_ready')
