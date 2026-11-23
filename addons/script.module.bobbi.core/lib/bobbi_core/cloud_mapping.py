"""Exact provider-task to torrent-file mapping, without filename search heuristics."""
from pathlib import PurePosixPath

from bobbi_core.preparation import scope_path


def map_torrent_file(provider, destination, observation, torrent_file):
    scope_path(destination)
    if (observation.get('status') != 2 or not observation.get('file_id')
            or not observation.get('parent_id')):
        raise ValueError('Completed task with stable cloud identities required')
    if (set(torrent_file) != {'id', 'path', 'length'} or type(torrent_file['id']) is not int
            or torrent_file['id'] < 0 or type(torrent_file['length']) is not int or torrent_file['length'] <= 0):
        raise ValueError('Verified TorrServer file tuple required')
    relative = torrent_file['path']
    if (not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative
            or PurePosixPath(relative).is_absolute() or any(p in ('', '.', '..') for p in relative.split('/'))):
        raise ValueError('Canonical torrent path required')
    parent = destination.rsplit('/', 1)[0]
    destinations = [item for item in provider.identified_files(parent)
                    if item['path'] == destination and item['file_id'] == observation['parent_id']]
    if len(destinations) != 1 or not destinations[0]['directory'] or destinations[0].get('forbidden'):
        raise ValueError('Cloud task parent identity does not match destination')
    root = [item for item in provider.identified_files(destination) if item['file_id'] == observation['file_id']]
    if len(root) != 1 or root[0].get('forbidden'):
        raise ValueError('Cloud task root missing, ambiguous or forbidden')
    root = root[0]
    if root['path'] != destination + '/' + root['name']:
        raise ValueError('Cloud root escaped destination')
    parts = relative.split('/')
    if not root['directory']:
        if parts != [root['name']]:
            raise ValueError('Single-file cloud task is not the selected torrent file')
        selected = root
    else:
        # TorrServer may retain the torrent top-level directory in file_stats.
        # Strip exactly that directory only, never fuzzy/casefold match names.
        # A provider can wrap one file in a directory with that same filename.
        # Strip a torrent root only if a leaf remains. Otherwise require the
        # exact named child below that task-owned directory, including size/ID.
        if len(parts) > 1 and parts[0] == root['name']:
            parts = parts[1:]
        if not parts or len(parts) > 8:
            raise ValueError('Bounded exact cloud path required')
        selected = root
        for position, name in enumerate(parts):
            if not selected['directory']:
                raise ValueError('Expected a directory in the exact cloud path')
            parent = selected['path']
            rows = provider.identified_files(parent)
            matches = [item for item in rows if item['name'] == name and item['path'] == parent + '/' + name]
            if len(matches) != 1 or matches[0].get('forbidden'):
                raise ValueError('Exact cloud file path missing or ambiguous')
            selected = matches[0]
    if selected['directory'] or not selected['file_id'] or selected['bytes'] != torrent_file['length']:
        raise ValueError('Cloud/torrent file size or identity mismatch')
    return dict(selected, task_root_id=root['file_id'], task_root_path=root['path'],
                torrent_file_id=torrent_file['id'], torrent_path=relative)
