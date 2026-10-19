"""Atomic bounded UI projection of qualified bindings, not the whole 115 drive."""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from bobbi_core.preparation import scope_path
from bobbi_core.prepared_qualification import qualification_token
from bobbi_core.video_context import video_identity, checked_video, migrate_entry

MAX_BYTES = 4 * 1024 * 1024
MOUNT_ROOT = '/storage/videos/Clouddrive/CloudDrive'


def document(queue, account):
    if not isinstance(account, str) or not account:
        raise ValueError('Current cloud account scope required')
    titles = {}
    from bobbi_core.subtitle_projection import records, generation as subtitle_generation
    try:
        subtitles = records(queue.db)
        subtitle_revision = subtitle_generation(queue.db)
    except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
        subtitles, subtitle_revision = {}, 0
    rows = queue.db.execute('''SELECT b.resource,b.media_id,b.version_key,b.evidence,t.account,t.source_hash,p.payload
        FROM prepared_bindings b JOIN tasks t ON b.task=t.id
        JOIN preparation_targets p ON p.task=b.task AND p.media_id=b.media_id AND p.version_key=b.version_key
        WHERE t.account=? ORDER BY b.media_id,b.resource''', (account,))
    count = 0
    for row in rows:
        count += 1
        if count > 8192:
            raise ValueError('Prepared projection exceeds source budget')
        item = queue.ledger.get(row['resource'])
        if item['state'] != 'ready' or item['suppressed']:
            continue
        selected = json.loads(row['payload']).get('_selection')
        if not selected:
            continue  # Historical/manual rows are not generic-service proof.
        match = re.fullmatch(r'tmdb:(movie|tv):([1-9]\d*)(?::s(\d+):e([1-9]\d*))?', row['media_id'])
        if not match or (match[1] == 'tv') != bool(match[3]):
            raise ValueError('Invalid bound media identity')
        key = 'tmdb:{}:{}'.format(match[1], match[2])
        if key not in titles:
            if len(titles) >= 1000:
                raise ValueError('Prepared projection exceeds title budget')
            titles[key] = dict(key=key, kind=match[1], tmdb_id=match[2], title=selected['title'],
                               original_title=selected['title'], year=0, anime=selected['anime'], sources=[])
        source = dict(key=row['resource'], title=selected['release_title'], path=item['cloud_path'], bytes=item['bytes'],
                      origin='bt-anime' if selected['anime'] else 'bt-video', subtitles=[],
                      prepared_version_key=row['version_key'], prepared_source_info_hash=row['source_hash'],
                      prepared_account=row['account'], prepared_file_id=item['file_id'], state='qualified')
        source['prepared_qualification'] = qualification_token(queue, item, row['source_hash'])
        if item['qualification'].get('media_profile'):
            from bobbi_core.release_media_profile import checked_profile
            source['prepared_media_profile'] = checked_profile(item['qualification']['media_profile'])
        file = selected['file']
        source['video_context'] = video_identity(row['media_id'], row['version_key'],
            dict(source_info_hash=row['source_hash'], torrent_file_id=file['id'],
                 torrent_path=file['path'], torrent_file_bytes=file['length']))
        subtitle = subtitles.get(source['video_context']['key'])
        if subtitle:
            source['prepared_subtitle'] = subtitle
        if match[1] == 'tv':
            source.update(season=int(match[3]), episode=int(match[4]))
        titles[key]['sources'].append(source)
    return dict(schema_version=1, prepared_schema=2, generation=queue.generation(), account=account,
                subtitle_generation=subtitle_revision,
                mount_root=MOUNT_ROOT, titles=list(titles.values()))


def publish(queue, destination, account, account_scope=None):
    target = Path(destination)
    value = document(queue, account)
    if account_scope is not None:
        from bobbi_platform.account_manager import validate_snapshot
        value['account_scope'] = validate_snapshot(account_scope, authenticated=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('Prepared snapshot exceeds byte budget')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + '.', suffix='.pending', dir=str(target.parent))
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        stamp_fd, stamp_temp = tempfile.mkstemp(prefix=target.name + '.generation.', dir=str(target.parent))
        with os.fdopen(stamp_fd, 'wb') as stream:
            stamp = '{}:{}'.format(account, value['generation'])
            if value['subtitle_generation']:
                stamp += ':sub:{}'.format(value['subtitle_generation'])
            if account_scope is not None:
                stamp += ':epoch:{}'.format(account_scope['epoch'])
            stream.write(stamp.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stamp_temp, str(target) + '.generation')
        if os.name != 'nt':
            directory = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        # Preserve the uniquely named partial for diagnostics. Never replace a
        # last valid snapshot with an empty/error response or truncate in place.
        raise
    return value['generation']


def read_generation(path):
    try:
        with open(str(path) + '.generation', 'rb') as stream:
            raw = stream.read(129)
        return raw.decode('utf-8') if 1 <= len(raw) <= 128 else None
    except (OSError, UnicodeError, TypeError):
        return None


def load(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Prepared snapshot exceeds byte budget')
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('prepared_schema') not in (1, 2) or value.get('schema_version') != 1
            or value.get('mount_root') != MOUNT_ROOT or type(value.get('generation')) is not int
            or not isinstance(value.get('account'), str) or not value['account']
            or value['generation'] < 0 or not isinstance(value.get('titles'), list) or len(value['titles']) > 1000
            or type(value.get('subtitle_generation', 0)) is not int or value.get('subtitle_generation', 0) < 0):
        raise ValueError('Invalid prepared snapshot')
    count = 0
    for title in value['titles']:
        if title.get('kind') not in {'movie', 'tv'} or not isinstance(title.get('sources'), list):
            raise ValueError('Invalid prepared title')
        for item in title['sources']:
            migrate_entry(item)
            count += 1
            if 'prepared_media_profile' in item:
                from bobbi_core.release_media_profile import checked_profile
                checked_profile(item['prepared_media_profile'])
            if (count > 8192 or item.get('state') != 'qualified' or type(item.get('bytes')) is not int
                    or item['bytes'] <= 0 or not item.get('prepared_file_id') or not item.get('prepared_account')
                    or item['prepared_account'] != value['account']
                    or not re.fullmatch('[0-9a-f]{64}', item.get('prepared_version_key', ''))
                    or not re.fullmatch('[0-9a-f]{40}', item.get('prepared_source_info_hash', ''))):
                raise ValueError('Unqualified prepared source')
            scope_path(item['path'])
            if ('prepared_qualification' in item and
                    (not isinstance(item['prepared_qualification'], str) or
                     not re.fullmatch('[0-9a-f]{64}', item['prepared_qualification']))):
                raise ValueError('Invalid per-resource qualification')
            if 'video_context' in item:
                context = checked_video(item['video_context'])
                media = ('tmdb:tv:{}:s{}:e{}'.format(title['tmdb_id'], item.get('season'), item.get('episode'))
                         if title['kind'] == 'tv' else 'tmdb:movie:{}'.format(title['tmdb_id']))
                if (context['media_id'] != media or context['release_key'] != item['prepared_version_key']
                        or context['selected']['source_info_hash'] != item['prepared_source_info_hash']
                        or context['selected']['torrent_file_bytes'] != item['bytes']):
                    raise ValueError('Video context does not belong to the prepared file')
            if 'prepared_subtitle' in item:
                from bobbi_core.subtitle_projection import checked
                try:
                    checked(item['prepared_subtitle'], checked_video(item.get('video_context')))
                except (ValueError, TypeError, KeyError):
                    # Optional subtitle metadata cannot revoke a qualified video.
                    item.pop('prepared_subtitle', None)
    value['prepared_schema'] = 2
    if 'account_scope' in value and not scope_is_current(value['account_scope']):
        return dict(value, titles=[])
    return value


def scope_is_current(scope):
    """Old projection bytes never advertise another generation as ready."""
    from bobbi_platform.account_manager import validate_snapshot, AccountError
    try:
        from bobbi_platform.runtime import call
        return (validate_snapshot(scope, authenticated=True) ==
                call('account_status', {}, timeout=.2))
    except (AccountError, OSError, RuntimeError, ValueError, ImportError):
        return False


def selected_cloud(data, snapshot):
    """Reuse only the exact already-qualified source hash and episode identity."""
    info_hash = str(data.get('info_hash') or '').lower()
    if not re.fullmatch('[0-9a-f]{40}', info_hash):
        return None
    wanted_kind = 'tv' if data.get('mode') in {'tv', 'anime', 'episode'} else 'movie'
    tmdb = str((data.get('ids') or {}).get('tmdb_id') or '')
    television = data.get('tv_data') or {}
    found = []
    for title in snapshot.get('titles', []):
        if title.get('kind') != wanted_kind or str(title.get('tmdb_id')) != tmdb:
            continue
        for item in title['sources']:
            if item.get('prepared_source_info_hash') != info_hash or item.get('state') != 'qualified':
                continue
            if wanted_kind == 'tv' and any(str(item.get(k)) != str(television.get(k)) for k in ('season', 'episode')):
                continue
            found.append(item)
    if len(found) != 1:
        return None
    return found[0]
