"""Read-only workload admission: idle, or this exact playing source's next.

No Kodi imports or controls. Samples are collected on the preparation IO lane;
they never confer resource readiness or identify a torrent from its label.
"""
import base64
import hashlib
import json
import re
import socket
import time

from bobbi_core.source_intent import checked_target_offset

STARTED = 'Window(10000).Property(bobbi_cinema_started)'
SELECTED = 'Window(10000).Property(bobbi_cinema_selection)'
OWNER = 'Window(10000).Property(bobbi_active_player_session)'
MESSAGES = (
    ('Player.GetActivePlayers', None),
    ('XBMC.GetInfoLabels', {'labels': [STARTED, SELECTED, OWNER]}),
    ('Player.GetItem', {'playerid': 1, 'properties': ['file']}),
    ('XBMC.GetInfoBooleans', {'booleans': ['Player.Caching', 'Player.Paused']}),
    ('Player.GetActivePlayers', None),
)


def _source_hash(value):
    """Compare equivalent BTIH encodings without changing provider identity."""
    if not isinstance(value, str):
        return None
    if re.fullmatch('[0-9a-fA-F]{40}', value):
        return value.lower()
    if re.fullmatch('[A-Za-z2-7]{32}', value):
        return base64.b32decode(value.upper()).hex()
    return None


def admitted(job, replies):
    try:
        before, after = replies[1], replies[5]
        if before != after or not isinstance(before, list): return False
        if before == []: return True
        if len(before) != 1 or not isinstance(before[0], dict): return False
        player = before[0]
        if (set(player) - {'playerid', 'type', 'playertype'}
                or type(player.get('playerid')) is not int or player['playerid'] != 1
                or player.get('type') != 'video'
                or player.get('playertype', 'internal') != 'internal'): return False
        labels, file, flags = replies[2], replies[3]['item']['file'], replies[4]
        if flags.get('Player.Caching') is not False or flags.get('Player.Paused') is not False: return False
        proof = json.loads(labels[STARTED])
        request = proof['request_id']
        if (not isinstance(request, str) or not re.fullmatch('[a-f0-9]{32}', request)
                or labels[SELECTED] != request or labels[OWNER] != request): return False
        if (not isinstance(file, str) or not file
                or hashlib.sha256(file.split('|', 1)[0].encode()).hexdigest() != proof['url_sha256']): return False
        anchor = job['payload']['anchor']
        media, episode = anchor['media'], proof['tv_data']
        source_hash = _source_hash(proof['source_info_hash'])
        if (str(proof['ids']['tmdb_id']) != str(media['tmdb_id'])
                or type(episode['season']) is not int or type(episode['episode']) is not int
                or (episode['season'], episode['episode']) != (media['season'], media['episode'])
                or source_hash is None
                or source_hash != anchor['selected']['source_info_hash']): return False
        offset = checked_target_offset(job['payload'].get('target_offset', 1))
        expected = 'tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], media['episode'] + offset)
        return job['media_id'] == expected
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def may_discover(job):
    """At most 1 s total, fixed loopback, fixed read-only RPC, bounded replies."""
    deadline = time.monotonic() + 1.0
    try:
        with socket.create_connection(('127.0.0.1', 9090), timeout=0.3) as connection:
            for index, (method, params) in enumerate(MESSAGES, 1):
                left = deadline - time.monotonic()
                if left <= 0: return False
                connection.settimeout(min(0.3, left))
                message = dict(jsonrpc='2.0', id=index, method=method)
                if params is not None: message['params'] = params
                connection.sendall(json.dumps(message).encode() + b'\n')
            raw, replies, count = '', {}, 0
            decoder = json.JSONDecoder()
            import codecs
            utf8 = codecs.getincrementaldecoder('utf-8')()
            while time.monotonic() < deadline and len(replies) < len(MESSAGES):
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                chunk = connection.recv(4096)
                if not chunk: return False
                count += len(chunk)
                if count > 16384: return False
                raw += utf8.decode(chunk)
                while raw.strip():
                    raw = raw.lstrip()
                    try: message, end = decoder.raw_decode(raw)
                    except ValueError: break
                    raw = raw[end:]
                    if not isinstance(message, dict): return False
                    identity = message.get('id')
                    if type(identity) is int and 1 <= identity <= len(MESSAGES):
                        if identity in replies: return False
                        replies[identity] = message.get('result')
            return len(replies) == len(MESSAGES) and time.monotonic() <= deadline and admitted(job, replies)
    except (OSError, UnicodeError, ValueError):
        return False
