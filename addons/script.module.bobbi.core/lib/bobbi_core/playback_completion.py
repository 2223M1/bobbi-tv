"""Position corroboration only; never creates EOF or player-control authority."""
import math


def completion_observation(value):
    """Validate the optional native media-ms snapshot, never player authority.

    An explicit unavailable observation is different from an old host without
    this capability. Invalid/new-host evidence must not fall back to polling.
    """
    if (type(value) is not dict
            or set(value) != {'schema', 'position_ms', 'duration_ms', 'age_us', 'valid'}
            or type(value.get('schema')) is not int or value['schema'] != 1
            or type(value.get('valid')) is not bool
            or any(type(value.get(key)) is not int or not 0 <= value[key] <= 2**53 - 1
                   for key in ('position_ms', 'duration_ms', 'age_us'))):
        return None
    if not value['valid']:
        return dict(value) if all(value[key] == 0 for key in
                                 ('position_ms', 'duration_ms', 'age_us')) else None
    if value['duration_ms'] <= 0 or value['position_ms'] > value['duration_ms'] + 3000:
        return None
    return dict(value)


def terminal_end(terminal, position, duration, observed_at, now):
    """One result feeds both history and next; only a matched EOF can complete."""
    if not isinstance(terminal, dict) or terminal.get('reason') != 'NATURAL_EOF':
        return False
    if 'completion_observation' in terminal:
        observed = completion_observation(terminal['completion_observation'])
        return bool(observed and observed['valid'] and observed['age_us'] <= 5_000_000
                    and observed['duration_ms'] - observed['position_ms'] <= 3000)
    # Compatibility for older native hosts only. Never OR this with a new-host
    # observation: an unavailable/stale/incomplete native result fails closed.
    return observed_end(position, duration, observed_at, now, max_age=5)


def observed_end(position, duration, observed_at, now, max_age=3):
    values = (position, duration, observed_at, now, max_age)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return False
    return (duration > 0 and 0 <= position <= duration + 3
            and duration - position <= 3 and 0 <= now - observed_at <= max_age)
