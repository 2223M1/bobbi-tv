"""Position corroboration only; never creates EOF or player-control authority."""
import math


class FileProgressCheckpoint:
    """Rate-limit an existing file writer; a clock sample is never an EOF.

    Each playback owner keeps one in memory. Time is monotonic wall time,
    not media time. Entering pause can checkpoint early, staying paused does
    not repeat it. A backward seek is valid. No timer, threads or persistence.
    """
    def __init__(self):
        self.last_at = self.position = None
        self.paused = False

    def due(self, now, position, duration, *, paused=False):
        if (any(type(v) not in (int, float) or not math.isfinite(v)
                for v in (now, position, duration)) or not 0 <= position <= duration
                or not 0 < duration <= 864000):
            return False
        entering_pause = paused and not self.paused
        self.paused = paused
        if self.last_at is None:
            self.last_at, self.position = now, position
            return entering_pause and position >= 1
        if abs(position - self.position) < 1 or (not entering_pause and now - self.last_at < 30):
            return False
        self.last_at, self.position = now, position
        return True


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
