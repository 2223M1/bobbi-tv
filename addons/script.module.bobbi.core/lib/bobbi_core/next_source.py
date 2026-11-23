"""Read-only adjacent BT proof from service-owned intake/target evidence.

This is not cloud readiness or playback authority. It never fetches metadata,
searches, submits a cloud task or turns a next-purpose target into a current.
"""
import json
from pathlib import PurePosixPath
import re

from .source_intent import checked_body
from .video_context import video_identity


def _target(db, task, media_id, version):
    row = db.execute('''SELECT p.payload,t.source_hash,t.account,t.destination,t.state
        FROM preparation_targets p JOIN tasks t ON t.id=p.task
        WHERE p.task=? AND p.media_id=? AND p.version_key=? AND t.provider='115' ''',
        (task, media_id, version)).fetchone()
    if row is None or row['state'] == 'suppressed':
        return None
    request = json.loads(row['payload'])
    selected = request['_selection']
    file, work = selected['file'], selected['work_identity']
    match = re.fullmatch(r'tmdb:tv:([1-9]\d*):s([1-9]\d*):e([1-9]\d*)', media_id)
    if (not match or request['media_id'] != media_id or request['version_key'] != version
            or request['source_info_hash'] != row['source_hash'] or request['account'] != row['account']
            or request['destination'] != row['destination'] or work.get('provider') != 'tmdb'
            or work.get('id') != int(match[1]) or work.get('kind') != 'tv'
            or not re.fullmatch('[0-9a-f]{64}', selected.get('metadata_sha256', ''))):
        return None
    context = video_identity(media_id, version, dict(source_info_hash=row['source_hash'],
        torrent_file_id=file['id'], torrent_path=file['path'], torrent_file_bytes=file['length']))
    return dict(video_context=context, source_title=selected['release_title'],
                account=row['account'], destination=row['destination'],
                metadata_sha256=selected['metadata_sha256'])


def project(db, body, accepted):
    """At most one next file, bound to this accepted current request/tuple."""
    try:
        media, selected, source_hash = checked_body(body)
        if body['purpose'] != 'current' or media['kind'] != 'tv':
            return None
        current_id = 'tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], media['episode'])
        next_id = 'tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], media['episode'] + 1)
        tasks = accepted.get('tasks', [])
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 3:
            return None
        anchors = [item for item in tasks if item.get('media_id') == current_id]
        if len(anchors) != 1:
            return None
        current = _target(db, anchors[0]['task_id'], current_id, anchors[0]['version_key'])
        if not current or current['video_context']['selected'] != selected:
            return None
        candidates = []
        for target in tasks:
            if target.get('media_id') == next_id and target.get('task_id') == anchors[0]['task_id']:
                candidate = _target(db, target['task_id'], next_id, target['version_key'])
                if candidate and candidate['metadata_sha256'] == current['metadata_sha256']:
                    candidates.append(candidate)
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='next_discovery_jobs'").fetchone():
            rows = db.execute('''SELECT payload,result FROM next_discovery_jobs WHERE account=?
                AND destination=? AND media_id=? AND version_key=? AND state='prepared' LIMIT 2''',
                (current['account'], current['destination'], next_id, current['video_context']['release_key'])).fetchall()
            for row in rows:
                payload, result = json.loads(row['payload']), json.loads(row['result'])
                anchor = payload['anchor']
                offset = payload.get('target_offset', 1)
                if (anchor.get('purpose') != 'current' or type(offset) is not int or offset not in (1, 2)
                        or any(anchor['media'][key] != media[key] for key in ('tmdb_id', 'kind', 'season'))
                        or anchor['media']['episode'] + offset != media['episode'] + 1):
                    continue
                if offset == 1:
                    if anchor['selected'] != selected:
                        continue
                else:
                    # Completed E -> E+2 proof is immutable. When the actual
                    # E+1 is independently accepted under the same strict key,
                    # that already-proved file is now adjacent; no resubmission
                    # or invented intermediate anchor is needed.
                    original_id = 'tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], anchor['media']['episode'])
                    original = _target(db, payload['task'], original_id, current['video_context']['release_key'])
                    if (not original or original['video_context']['selected'] != anchor['selected']
                            or (original['account'], original['destination']) !=
                               (current['account'], current['destination'])):
                        continue
                # Discovery's acceptance receipt identifies the exact queue
                # target; unrelated accepted episodes cannot become a mirror.
                task = result.get('task_id')
                if result.get('state') != 'PREPARATION_REQUESTED_NOT_READY' or not task:
                    continue
                rows = db.execute('SELECT version_key FROM preparation_targets WHERE task=? AND media_id=? LIMIT 2',
                                  (task, next_id)).fetchall()
                if len(rows) == 1:
                    candidate = _target(db, task, next_id, rows[0]['version_key'])
                    if candidate:
                        candidates.append(candidate)
        unique = {}
        for candidate in candidates:
            context = candidate['video_context']
            if (candidate['account'], candidate['destination']) != (current['account'], current['destination']):
                continue
            same = context['release_key'] == current['video_context']['release_key']
            if not same:
                from .episode_revision import compatible_pair
                same = compatible_pair(PurePosixPath(selected['torrent_path']).name,
                    PurePosixPath(context['selected']['torrent_path']).name, media['season'], media['episode'],
                    current['video_context']['release_key'], context['release_key'])
            if same:
                unique[context['key']] = candidate
        proof = dict(request_id=body['request_id'], anchor=current['video_context'], account=current['account'],
                     next=next(iter(unique.values())) if len(unique) == 1 else None)
        # Host IPC currently uses JSON's ASCII escaping. Budget those exact
        # bytes, leaving room for task receipts and the component envelope.
        return proof if len(json.dumps(proof).encode('utf-8')) <= 12288 else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
