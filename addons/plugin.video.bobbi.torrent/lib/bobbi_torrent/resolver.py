"""A bounded exact selection pipeline; no fallback release and no player monitor."""
import json
from pathlib import PurePosixPath
import re
import time
from threading import Event, Thread

from .backend import BackendError
from .torrent_identity import magnet_hash, resolve_http

FILE_CHOICE_STATUS_SECONDS = 5.0

# Preserve upstream's ordinary single-file media/elementary-stream formats.
# Disc images/indexes, playlists and scripts need a different resolver contract:
# never treat ISO/BDMV/MPLS/ASX/M3U8/SDP/AVS or generic BIN/DAT as one video here.
VIDEO = (
    '.3g2', '.3gp', '.asf', '.avc', '.avi', '.bivx', '.divx', '.dv', '.dvr-ms',
    '.evo', '.f4v', '.fli', '.flv', '.h264', '.m2t', '.m2ts', '.m2v', '.m4v',
    '.mk3d', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.mts', '.nuv', '.ogm',
    '.ogv', '.pva', '.qt', '.rcv', '.rec', '.rmvb', '.svq3', '.tp', '.trp',
    '.ts', '.ty', '.vc1', '.vdr', '.viv', '.vob', '.vp3', '.webm', '.wmv', '.xvid',
)


def checked_expected_file(raw):
    """Read the service-proved next-file tuple, never a selector override.

    Match video_context's selected-file schema and canonical path rules; this
    adapter additionally requires its native positive, one-based file index.
    """
    from bobbi_core.video_context import digest

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate file tuple field')
            value[key] = item
        return value

    try:
        if not isinstance(raw, str) or not 0 < len(raw.encode('utf-8')) <= 8192:
            raise ValueError('Bounded file tuple required')
        value = json.loads(raw, object_pairs_hook=unique_object)
        keys = {'source_info_hash', 'torrent_file_id', 'torrent_path', 'torrent_file_bytes'}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError('Exact file tuple required')
        digest(value['source_info_hash'], 40)
        path = value['torrent_path']
        if (type(value['torrent_file_id']) is not int or value['torrent_file_id'] <= 0
                or type(value['torrent_file_bytes']) is not int or value['torrent_file_bytes'] <= 0
                or not isinstance(path, str) or not 1 <= len(path) <= 4096
                or '\\' in path or ':' in path or any(ord(char) < 32 for char in path)
                or PurePosixPath(path).is_absolute()
                or any(part in ('', '.', '..') for part in path.split('/'))):
            raise ValueError('Invalid exact file tuple')
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise BackendError('TORRENT_REQUEST_INVALID', 'invalid_request') from None


def metadata_files(info):
    files = info.get('file_stats') if isinstance(info, dict) else None
    if files in (None, []):
        return None
    if not isinstance(files, list) or len(files) > 4096:
        raise BackendError('TORRENT_METADATA_INVALID', 'selected_file_missing')
    found, ids = [], set()
    for file in files:
        if not isinstance(file, dict):
            raise BackendError('TORRENT_METADATA_INVALID', 'selected_file_missing')
        index, path, length = file.get('id'), file.get('path'), file.get('length')
        if (type(index) is not int or index < 1 or index in ids
                or not isinstance(path, str) or not 0 < len(path) <= 4096 or '\x00' in path
                or path.startswith(('/', '\\')) or ':' in path
                or any(ord(char) < 32 for char in path)
                or any(part in ('', '.', '..') for part in re.split(r'[/\\]', path))
                or type(length) is not int or length < 0):
            raise BackendError('TORRENT_METADATA_INVALID', 'selected_file_missing')
        ids.add(index)
        found.append(dict(id=index, path=path, length=length))
    return found


def selected_file_unchanged(info, file):
    files = metadata_files(info)
    if not files or file not in files:
        raise BackendError('TORRENT_SELECTED_FILE_CHANGED', 'selected_file_missing')


def select_file(info, request, info_hash, resolution, protocol):
    from bobbi_core.episode_identity import resolve_episode_binding, check_transport_episode_file
    from bobbi_core.torrent_selection import select_exact_file, ExactSelectionError
    expected = checked_expected_file(request['expected_file']) if 'expected_file' in request else None
    try:
        metadata = metadata_files(info) or []
    except BackendError as error:
        error.diagnostic = dict(stage='metadata_schema')
        raise
    files = [f for f in metadata if f['length'] > 0
             and f['path'].lower().endswith(VIDEO)]
    diagnostic = dict(stage='selector', file_count=len(metadata), candidate_count=len(files),
                      binding_present=bool(request.get('episode_binding')))
    if not files:
        raise BackendError('TORRENT_NO_VIDEO_FILE', 'no_candidate', diagnostic)
    season, episode = request.get('season', ''), request.get('episode', '')
    binding = request.get('episode_binding', '')
    selection = protocol.validate_torrent_resolution(request['request_id'], resolution, info_hash)
    title = ' '.join(str(info.get(k) or '')[:4096] for k in ('name', 'title'))
    title += ' ' + request.get('release_title', '')
    releases = [str(info.get(k) or '')[:4096] for k in ('name', 'title')]
    releases.append(request.get('release_title', ''))
    diagnostic['stage'] = 'binding'
    try:
        checked = resolve_episode_binding(binding, request['request_id'], selection,
            info_hash, season, episode)
        diagnostic['stage'] = 'selector'
        # Bonus/other-season branches in a covering pack cannot compete with
        # the regular target. The same scope check is repeated on the winner.
        try:
            file = select_exact_file(files, season, episode, title, info_hash, checked)
        except ExactSelectionError as selection_error:
            import json
            envelope = json.loads(binding) if binding else {}
            if (selection_error.category == 'target_unresolved' and (season or episode)
                    and isinstance(envelope, dict) and envelope.get('version') in (1, 2)):
                scoped = []
                for candidate in files:
                    try:
                        check_transport_episode_file(binding, candidate['path'], releases, require_work=False)
                        scoped.append(candidate)
                    except ValueError:
                        pass
                if not scoped or scoped == files:
                    raise selection_error
                file = select_exact_file(scoped, season, episode, title, info_hash, checked)
            else:
                raise
        diagnostic['stage'] = 'filename_identity'
        if season or episode:
            check_transport_episode_file(binding, file['path'], releases)
    except ExactSelectionError as error:
        raise BackendError('TORRENT_EXACT_FILE_UNRESOLVED', error.category, diagnostic) from None
    except (ValueError, UnicodeError):
        if diagnostic['stage'] == 'filename_identity':
            # A valid handoff can still name the wrong work. Preserve the old
            # selector's distinction instead of blaming the binding schema.
            raise BackendError('TORRENT_EPISODE_FILE_IDENTITY_UNRESOLVED',
                               'target_unresolved', diagnostic) from None
        raise BackendError('TORRENT_EPISODE_BINDING_INVALID', 'invalid_binding', diagnostic) from None
    if expected is not None and expected != dict(source_info_hash=info_hash,
            torrent_file_id=file['id'], torrent_path=file['path'], torrent_file_bytes=file['length']):
        raise BackendError('TORRENT_EXPECTED_FILE_MISMATCH', 'selected_file_missing', diagnostic)
    if not (season or episode):
        from bobbi_core.movie_identity import load_binding, binding_status, file_identity_status
        raw = request.get('movie_binding', '')
        diagnostic.update(stage='movie_identity', binding_present=bool(raw))
        try:
            binding = load_binding(raw, request['request_id'], selection) if raw else None
            basename = re.split(r'[/\\]', file['path'])[-1]
            status = binding_status(binding, [basename, request.get('release_title', ''),
                                             str(info.get('name') or '')[:4096]])
            if (status['status'] == 'conflict'
                    or file_identity_status(binding, basename)['status'] == 'identity_insufficient'):
                raise BackendError('TORRENT_MOVIE_IDENTITY_UNRESOLVED', 'target_unresolved', diagnostic)
        except (ValueError, UnicodeError):
            raise BackendError('TORRENT_MOVIE_BINDING_INVALID', 'invalid_binding', diagnostic) from None
    return file


def manual_candidates(info, request, info_hash, resolution, protocol):
    """Real metadata only. Unknown is selectable; a known contradiction is not.

    This path never manufactures title/episode verification. Its result can only
    be opened with USER_CONFIRMED_FILE and cannot seed automatic preparation.
    """
    from bobbi_core.episode_identity import resolve_episode_binding
    from bobbi_core.torrent_selection import load_episode_binding, movie_candidates
    from bobbi_core.torrent_episode_matching import _path_season_contexts, _release_season_contexts
    from bobbi_core.filename_semantics import parse_filename
    from bobbi_core.movie_identity import load_binding, binding_status
    selection = protocol.validate_torrent_resolution(request['request_id'], resolution, info_hash)
    files = [f for f in (metadata_files(info) or []) if f['length'] > 0
             and f['path'].lower().endswith(VIDEO)]
    season, episode = request.get('season', ''), request.get('episode', '')
    try:
        if not (season or episode):
            binding = load_binding(request.get('movie_binding', ''), request['request_id'], selection)
            names = [request.get('release_title', ''), str(info.get('name') or '')[:4096]]
            if binding_status(binding, names)['status'] == 'conflict':
                return []
            return [f for f in movie_candidates(files)
                    if binding_status(binding, [f['path']])['status'] != 'conflict']
        checked = resolve_episode_binding(request.get('episode_binding', ''), request['request_id'],
                                          selection, info_hash, season, episode)
        binding = load_episode_binding(checked, info_hash, season, episode)
        import json
        from bobbi_core.episode_identity import check_transport_episode_file
        transport = json.loads(request['episode_binding']) if request.get('episode_binding') else {}
        season, episode = int(season), int(episode)
        if not 0 <= season <= 100000 or not 0 < episode <= 100000:
            return []
        allowed = {episode}
        if binding:
            allowed.add(binding['absolute_episode'])
        candidates = []
        for file in files:
            parsed = parse_filename(file['path'])
            if isinstance(transport, dict) and transport.get('version') in (1, 2):
                try:
                    check_transport_episode_file(request['episode_binding'], file['path'],
                        [request.get('release_title', ''), str(info.get('name') or '')[:4096],
                         str(info.get('title') or '')[:4096]], require_work=False)
                except ValueError:
                    continue
            release_contexts = set()
            for title in (request.get('release_title', ''), str(info.get('name') or '')[:4096],
                          str(info.get('title') or '')[:4096]):
                release_contexts.update(_release_season_contexts(title, season))
            if (_path_season_contexts(file['path'], season) | release_contexts) - {season}:
                continue
            if parsed.strong:
                pairs = parsed.episode_pairs()
                if any(s != season for s, _ in pairs) or (season, episode) not in pairs:
                    continue
            elif parsed.markers and not {int(m['episode']) for m in parsed.markers}.issubset(allowed):
                continue
            candidates.append(file)
        return candidates
    except (ValueError, UnicodeError):
        raise BackendError('TORRENT_BINDING_INVALID', 'invalid_binding') from None


class Resolver:
    def __init__(self, backend, owner, session, clock=time.monotonic):
        self.backend, self.owner, self.session, self.clock = backend, owner, session, clock
        self.session.trust_env = False

    def resolve(self, request):
        self.stage = 'backend'
        self.substage = None
        self.metadata_polls = 0
        self.started = self.stage_started = self.clock()
        self.stages, self.buffer_snapshot = {}, {}
        try:
            return self._resolve(request)
        except BackendError as error:
            # Fixed enums/counts only. Do not retain metadata, file paths,
            # transport URLs, backend credentials or exception messages.
            error.diagnostic.setdefault('stage', self.stage)
            if self.substage is not None:
                error.diagnostic.setdefault('substage', self.substage)
            error.diagnostic['metadata_polls'] = self.metadata_polls
            error.diagnostic.update(self.buffer_snapshot)
            error.diagnostic['elapsed_ms'] = int((self.clock()-self.started)*1000)
            error.diagnostic['stage_ms'] = dict(self.stages,
                **{self.stage: int((self.clock()-self.stage_started)*1000)})
            raise

    def phase(self, stage):
        self.substage = None
        now = self.clock()
        self.stages[self.stage] = int((now-self.stage_started)*1000)
        self.stage, self.stage_started = stage, now

    def wait_more(self):
        callback = getattr(self.owner, 'wait_for_buffer', None)
        return bool(callback and callback(dict(self.buffer_snapshot)))

    def choose_with_status(self, choose, candidates, info_hash):
        """Keep only this already-added torrent alive while the human chooses.

        MatriX get renews its idle lease; the blocking Kodi dialog otherwise
        outlasts that lease. No add, save, preload or media open is repeated.
        The worker is joined before the mandatory post-choice identity read.
        """
        from bobbi_core.torrent_startup import FILE_CHOICE_SECONDS
        done, errors = Event(), []
        deadline = self.clock() + FILE_CHOICE_SECONDS
        def refresh():
            while not done.wait(FILE_CHOICE_STATUS_SECONDS):
                try:
                    def active():
                        if done.is_set():
                            raise BackendError('TORRENT_CANCELLED', 'cancelled')
                        self.owner.active()
                    active()
                    if self.clock() >= deadline:
                        return
                    self.backend.status(info_hash, min(deadline, self.clock() + 2), active)
                except BackendError as error:
                    if not done.is_set():
                        error.diagnostic.setdefault('substage', 'manual_wait')
                        errors.append(error)
                    return
                except Exception:
                    if not done.is_set():
                        errors.append(BackendError('TORRENT_CONTROL_UNAVAILABLE',
                            diagnostic={'substage': 'manual_wait'}))
                    return
        worker = Thread(target=refresh, name='bobbi-file-choice-status')
        worker.start()
        try:
            choice = choose(candidates)
        finally:
            done.set()
            # Request-local socket shutdown interrupts even trickling headers
            # or bodies. No worker may outlive Back, confirmation or an error.
            worker.join()
        self.owner.active()  # Cancel/replacement wins over old HTTP diagnostics.
        if choice is None:
            return None
        if errors:
            raise errors[0]
        return choice

    def _resolve(self, request):
        from bobbi_core.torrent_startup import DOWNLOAD_SECONDS, CONTROL_SECONDS
        expected = checked_expected_file(request['expected_file']) if 'expected_file' in request else None
        owner, backend = self.owner, self.backend
        owner.active()
        backend.ready(owner.active)  # Fail before fetching a torrent or submitting an add.
        self.phase('download')
        owner.progress('download')
        locator = request['magnet'] if request['action'] == 'play_magnet' else request['url']
        raw, magnet = None, ''
        try:
            if request['action'] == 'play_magnet':
                info_hash, magnet = magnet_hash(locator), locator
            else:
                raw, info_hash, magnet = resolve_http(locator, self.session.get, owner.active,
                    self.clock, self.clock() + DOWNLOAD_SECONDS)
        except BackendError:
            raise
        except TimeoutError:
            raise BackendError('TORRENT_DOWNLOAD_TIMEOUT', 'torrent_download_timeout') from None
        except Exception:
            raise BackendError('TORRENT_DOWNLOAD_FAILED', 'torrent_download_failed') from None
        if expected is not None and info_hash != expected['source_info_hash']:
            raise BackendError('TORRENT_EXPECTED_FILE_MISMATCH', 'source_identity_mismatch')
        owner.active()
        try:
            resolution = owner.protocol.resolve_torrent(owner.request_id, locator, info_hash, info_hash)
        except (ValueError, RuntimeError):
            raise BackendError('TORRENT_SOURCE_IDENTITY_MISMATCH', 'source_identity_mismatch') from None
        self.phase('add')
        backend.add(info_hash, magnet, raw, self.clock() + CONTROL_SECONDS, owner.active)
        owner.active()
        # Poll status, not /stream?stat, which can reset MatriX.144.1 preload state.
        owner.progress('metadata')
        self.phase('metadata')
        deadline = self.clock() + backend.config['metadata_seconds']
        for _ in range(241):
            owner.active()
            if self.clock() >= deadline:
                raise BackendError('TORRENT_METADATA_TIMEOUT', 'metadata_timeout')
            self.metadata_polls += 1
            try:
                info = backend.status(info_hash, deadline, owner.active)
            except BackendError as error:
                owner.active()
                if (error.code in ('TORRENT_CONTROL_DEADLINE', 'TORRENT_HTTP_TIMEOUT')
                        and self.clock() >= deadline):
                    raise BackendError('TORRENT_METADATA_TIMEOUT', 'metadata_timeout') from None
                raise
            if metadata_files(info):
                break
            owner.wait(min(.5, max(0, deadline - self.clock())))
        else:
            raise BackendError('TORRENT_METADATA_TIMEOUT', 'metadata_timeout')
        owner.active()
        self.phase('selector')
        evidence = 'AUTO_VERIFIED_FILE'
        try:
            file = select_file(info, request, info_hash, resolution, owner.protocol)
        except BackendError as error:
            choose = getattr(owner, 'choose_file', None)
            if expected is not None or error.category != 'target_unresolved' or choose is None:
                raise
            candidates = manual_candidates(info, request, info_hash, resolution, owner.protocol)
            if not candidates:
                raise
            file = self.choose_with_status(choose, candidates, info_hash)
            owner.active()
            if file is None:
                raise BackendError('TORRENT_CANCELLED', 'cancelled') from None
            if file not in candidates:
                raise BackendError('TORRENT_SELECTED_FILE_CHANGED', 'selected_file_missing') from None
            # Re-read after the human dialog, not just the old in-memory rows.
            self.substage = 'manual_recheck'
            info = backend.status(info_hash, self.clock() + CONTROL_SECONDS, owner.active)
            selected_file_unchanged(info, file)
            if file not in manual_candidates(info, request, info_hash, resolution, owner.protocol):
                raise BackendError('TORRENT_SELECTED_FILE_CHANGED', 'selected_file_missing') from None
            evidence = 'USER_CONFIRMED_FILE'
        if evidence == 'AUTO_VERIFIED_FILE':
            owner.selected(info_hash, file)  # Only automatic identity can seed cloud preparation.
        owner.progress('buffering')
        self.phase('buffering')
        deadline = self.clock() + backend.config['buffering_seconds']
        def prefer_ready():
            callback = getattr(owner, 'prepared_source_ready', None)
            if (evidence == 'AUTO_VERIFIED_FILE' and callback
                    and callback(request, info_hash, file, deadline)):
                raise BackendError('TORRENT_PREPARED_READY', 'prepared_ready')
        prefer_ready()
        backend.preload(info_hash, file['id'], deadline, owner.active)
        extended = False
        poll_timeouts = 0
        for _ in range(1202):
            owner.active()
            prefer_ready()
            if self.clock() >= deadline:
                if not extended and self.wait_more():
                    extended = True
                    owner.active()
                    deadline = self.clock() + backend.config['buffering_seconds']
                    poll_timeouts = 0
                else:
                    raise BackendError('TORRENT_BUFFER_TIMEOUT', 'buffer_timeout')
            try:
                info = backend.status(info_hash, deadline, owner.active)
            except BackendError as error:
                owner.active()  # Cancellation/new selection always wins.
                if (error.code in ('TORRENT_CONTROL_DEADLINE', 'TORRENT_HTTP_TIMEOUT')
                        and self.clock() >= deadline):
                    # A read started inside the budget can finish outside it.
                    # Re-enter the same stage timeout/one manual-extension path,
                    # never mislabel this as an engine failure or preload twice.
                    continue
                if error.code == 'TORRENT_HTTP_TIMEOUT' and poll_timeouts < 1:
                    poll_timeouts += 1
                    owner.wait(min(.5, max(0, deadline - self.clock())))
                    continue  # One read-only status retry within the same budget.
                raise
            selected_file_unchanged(info, file)
            done, total = info.get('preloaded_bytes', 0), info.get('preload_size', 0)
            # Both supported MatriX versions publish the configured preload
            # before capping their actual work to this file's length. Their
            # Filled counter is torrent-wide: this is an advisory startup gate,
            # never proof that this file (or a subsequent native AV) is ready.
            threshold = min(total, file['length']) if type(total) is int and total > 0 else 0
            self.buffer_snapshot = {k: v for k, v in dict(
                torrent_preloaded=done, torrent_preload_target=threshold,
                selected_file_bytes=file['length'],
                peers=info.get('active_peers'), download_bps=info.get('download_speed')).items()
                if type(v) is int and 0 <= v <= 512*1024**3}
            if (type(done) is int and threshold > 0 and done >= threshold):
                break
            owner.progress('buffering', 100 * done / threshold if
                type(done) is int and done >= 0 and threshold > 0 else 0)
            owner.wait(min(.5, max(0, deadline - self.clock())))
        else:
            raise BackendError('TORRENT_BUFFER_TIMEOUT', 'buffer_timeout')
        owner.active()
        self.phase('final_selection')
        owner.protocol.validate_torrent_resolution(owner.request_id, resolution, info_hash)
        # Re-evaluate year/episode and exact file after all slow operations.
        if (evidence == 'AUTO_VERIFIED_FILE' and
                select_file(info, request, info_hash, resolution, owner.protocol) != file):
            raise BackendError('TORRENT_SELECTED_FILE_CHANGED', 'selected_file_missing')
        if (evidence == 'USER_CONFIRMED_FILE' and
                file not in manual_candidates(info, request, info_hash, resolution, owner.protocol)):
            raise BackendError('TORRENT_SELECTED_FILE_CHANGED', 'selected_file_missing')
        report = getattr(owner, 'diagnostic', None)
        if report:
            report(dict(stage='final_selection', stage_ms=self.stages,
                elapsed_ms=int((self.clock()-self.started)*1000), **self.buffer_snapshot))
        return dict(info_hash=info_hash, file=file, resolution=resolution, file_evidence=evidence,
                    url=backend.stream_url(info_hash, file))
