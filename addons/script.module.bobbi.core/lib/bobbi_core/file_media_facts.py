"""Display-only evidence from existing file history, never playback authority.

The history row remains v1. Its optional dependent start observation exposes
selected audio/subtitle and optional fenced video metadata, never HDR/output
or probe completeness.
"""
import math
import re

MAX_BATCH = 32
FIELDS = frozenset(('source', 'observation_key', 'duration_seconds', 'recorded_at'))


def checked(value, observation_key):
    """Recompute exact saved-observation matching; never trust an asserted state."""
    if (type(value) is not dict or set(value) not in (
            FIELDS, FIELDS | {'state'}, FIELDS | {'playback_start'}, FIELDS | {'playback_start', 'state'})
            or value.get('source') != 'playback_history'
            or any(type(key) is not str or not re.fullmatch('[0-9a-f]{64}', key)
                   for key in (observation_key, value.get('observation_key')))):
        raise ValueError('FILE_MEDIA_FACTS_INVALID')
    duration, recorded = value['duration_seconds'], value['recorded_at']
    if ((duration is None and 'playback_start' not in value)
            or (duration is not None and (type(duration) not in (int, float)
                or not 0 < duration <= 864000 or not math.isfinite(duration)))
            or type(recorded) not in (int, float) or not 0 <= recorded < 4102444800
            or not math.isfinite(recorded)):
        raise ValueError('FILE_MEDIA_FACTS_INVALID')
    state = 'matched' if value['observation_key'] == observation_key else 'verification_required'
    if 'state' in value and value['state'] != state:
        raise ValueError('FILE_MEDIA_FACTS_INVALID')
    result = dict(source=value['source'], observation_key=value['observation_key'],
        duration_seconds=duration, recorded_at=recorded, state=state)
    if 'playback_start' in value:
        from .playback_start_facts import public
        result['playback_start'] = public(value['playback_start'])
    return result
