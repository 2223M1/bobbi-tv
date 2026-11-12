"""Position corroboration only; never creates EOF or player-control authority."""
import math


def observed_end(position, duration, observed_at, now, max_age=3):
    values = (position, duration, observed_at, now, max_age)
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return False
    return (duration > 0 and 0 <= position <= duration + 3
            and duration - position <= 3 and 0 <= now - observed_at <= max_age)
