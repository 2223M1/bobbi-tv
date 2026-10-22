"""Validate immutable native receipts; generic Player.OnPlay carries no authority."""
from copy import deepcopy
import re

SHA = re.compile('[0-9a-f]{64}')
UUID = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
TERMINALS = {'NATURAL_EOF', 'STOP', 'ERROR', 'SUPERSEDED'}


def receipt(value):
    if not isinstance(value, dict) or type(value.get('protocol')) is not int or value['protocol'] != 1:
        return None
    if not UUID.fullmatch(str(value.get('native_instance', ''))):
        return None
    if not SHA.fullmatch(str(value.get('url_sha256', ''))):
        return None
    request, identity = value.get('request_id'), value.get('file_identity')
    if not isinstance(request, str) or (request and not re.fullmatch('[0-9a-f]{32}', request)):
        return None
    if not isinstance(identity, str) or len(identity) > 1024:
        return None
    if value.get('phase') not in ('OPEN', 'AV_STARTED', 'TERMINAL'):
        return None
    if value['phase'] == 'TERMINAL' and value.get('reason') not in TERMINALS:
        return None
    if any(type(value.get(key)) is not int or value[key] < 0 for key in ('sequence', 'user_intent')):
        return None
    if 'audio_intent' in value and (type(value['audio_intent']) is not int or value['audio_intent'] < 0):
        return None
    if type(value.get('paused')) is not bool:
        return None
    return deepcopy(value)


def _same_typed_value(left, right):
    """JSON structural equality without bool/int/float value aliasing."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (len(left) == len(right)
                and all(type(key) is str and key in right
                        and _same_typed_value(value, right[key]) for key, value in left.items()))
    if type(left) is list:
        return len(left) == len(right) and all(_same_typed_value(a, b) for a, b in zip(left, right))
    return type(left) in (type(None), bool, int, float, str) and left == right


def subtitle_snapshot_follows(current, previous):
    """Presentation-only live snapshot order, not an event/control admission.

    Native user/subtitle/audio intent and successful automatic file application
    update live fields without BobiEvent/sequence. The audio counter is optional
    for older F9 players, but cannot appear/disappear within one instance. Everything
    else at the same event sequence must remain byte-for-byte equivalent as
    structured data. ReceiptHistory deliberately keeps its immutable events.
    """
    current = receipt(current)
    if (not current or current['phase'] != 'AV_STARTED'
            or any(type(current.get(key)) is not int or current[key] < 0
                   for key in ('subtitle_intent', 'subtitle_auto_intent'))):
        return False
    applied = current.get('subtitle_file_applied', False)
    if (type(applied) is not bool
            or (applied and (not isinstance(current.get('subtitle_file_sha256'), str)
                            or not SHA.fullmatch(current['subtitle_file_sha256'])))
            or (not applied and 'subtitle_file_sha256' in current)):
        return False
    if previous is None:
        return True
    previous = receipt(previous)
    if (not previous or previous['phase'] != 'AV_STARTED'
            or any(not _same_typed_value(current.get(key), previous.get(key)) for key in
                   ('native_instance', 'request_id', 'file_identity', 'url_sha256', 'open_epoch'))
            or current['sequence'] < previous['sequence']
            or any(type(previous.get(key)) is not int or previous[key] < 0
                   for key in ('subtitle_intent', 'subtitle_auto_intent'))
            or current['subtitle_auto_intent'] != previous['subtitle_auto_intent']
            or ('audio_intent' in current) != ('audio_intent' in previous)
            or ('audio_intent' in current and current['audio_intent'] < previous['audio_intent'])
            or any(current[key] < previous[key] for key in ('user_intent', 'subtitle_intent'))):
        return False
    live = {'user_intent', 'subtitle_intent', 'audio_intent', 'subtitle_file_applied', 'subtitle_file_sha256'}
    if (current['sequence'] == previous['sequence']
            and not _same_typed_value(
                {key: value for key, value in current.items() if key not in live},
                {key: value for key, value in previous.items() if key not in live})):
        return False
    was_applied = previous.get('subtitle_file_applied', False)
    if (type(was_applied) is not bool
            or (not was_applied and 'subtitle_file_sha256' in previous)
            or (was_applied and (not applied
                    or current['subtitle_file_sha256'] != previous.get('subtitle_file_sha256')))):
        return False
    return True


class ReceiptHistory:
    """Small current-process cache; terminal is sticky, never inferred from time."""
    def __init__(self):
        self.items = {}

    def accept(self, value):
        row = receipt(value)
        if row is None:
            return None
        ident = row['native_instance']
        previous = self.items.get(ident)
        if previous:
            if any(previous[key] != row[key] for key in ('request_id', 'file_identity', 'url_sha256')):
                return None
            if previous['phase'] == 'TERMINAL' or row['sequence'] <= previous['sequence']:
                return None
        if len(self.items) >= 16 and ident not in self.items:
            self.items.pop(next(iter(self.items)))
        self.items[ident] = deepcopy(row)
        return row
