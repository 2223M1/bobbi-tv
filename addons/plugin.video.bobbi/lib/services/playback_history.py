"""One native history submission boundary, reusing the existing writer lane.

Personal files need session sequencing and must never fall back to synchronous
disk IO when that lane is busy. Legacy title history keeps its prior policy.
No playback owner, network operation or global player observer lives here.
"""
from copy import deepcopy


def snapshot(data, reason=None):
    if data.get('_pan_file'):
        data['_file_history_sequence'] = data.get('_file_history_sequence', 0) + 1
    value = deepcopy(data)
    if reason is not None:
        value['terminal_reason'] = reason
        value['completed'] = reason == 'NATURAL_EOF'
    return value


def submit_native(data, deferred=False, reason=None, save=None):
    if save is None:
        from lib.utils.general.utils import set_watched_file
        save = set_watched_file
    value = snapshot(data, reason)
    if deferred or data.get('_pan_file'):
        from lib.db.deferred_history import defer_watched_file
        if defer_watched_file(value):
            return True
        if data.get('_pan_file'):
            from lib.jacktook.utils import kodilog
            kodilog('[FILE-HISTORY] HISTORY_QUEUE_FULL')
            return False
    return save(value)
