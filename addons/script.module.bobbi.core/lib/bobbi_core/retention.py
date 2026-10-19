"""Pure retention decisions. This module cannot remove a local or cloud file."""
import math
from datetime import datetime, timedelta, timezone

DAY = 86400
BJT = timezone(timedelta(hours=8))


def nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def protected_reason(resource, now):
    """Unknown metadata/history and active dependencies fail closed."""
    if not nonnegative(now):
        return "clock_unavailable"
    if not resource.get("identity_verified") or not resource.get("file_id"):
        return "identity_unverified"
    if not resource.get("cloud_path") or not nonnegative(resource.get("bytes")):
        return "file_unverified"
    if resource.get("state") not in {"ready", "unavailable", "observed"}:
        return "resource_in_transition"
    for flag in ("favorite", "keep", "playing", "pending_next", "incomplete", "active_lease", "retained_dependency"):
        if resource.get(flag):
            return flag
    if resource.get("user_started") and not resource.get("completed_at"):
        return "unfinished"
    if not resource.get("managed") and not resource.get("observation_at") and not resource.get("completed_at"):
        return "unknown_original_history"
    for key in ("observation_at", "completed_at", "left_recommendation_at", "last_access_at"):
        stamp = resource.get(key)
        if stamp is not None and (not nonnegative(stamp) or stamp > now):
            return "clock_or_history_uncertain"
    return ""


def cleanup_candidate(resource, now, emergency=False):
    reason = protected_reason(resource, now)
    if reason:
        return {"eligible": False, "reason": reason}
    completed = resource.get("completed_at")
    departed = resource.get("left_recommendation_at")
    accessed = resource.get("last_access_at") or 0
    if completed:
        due = completed + 14 * DAY
        group, label = 1, "completed"
    elif not resource.get("user_started") and departed and not resource.get("recommended"):
        due = max(departed, accessed) + 30 * DAY
        group, label = 2, "unwatched_left_recommendation"
    else:
        return {"eligible": False, "reason": "no_retention_evidence"}
    expired = now >= due
    return {"eligible": bool(expired or emergency), "reason": label,
            "due_at": due, "priority": 0 if expired else group,
            "last_access_at": accessed or resource.get("observation_at") or completed or departed,
            "bytes": resource["bytes"], "resource_id": resource["resource_id"]}


def required_free_bytes(total, in_flight, proposed):
    if any(type(value) is not int or value < 0 for value in (total, in_flight, proposed)) or not total:
        raise ValueError("Fresh nonnegative capacity and task sizes required")
    # Integer ceiling: preserve two percent without floating-point rounding.
    return (total + 49) // 50 + in_flight + proposed


def select_cleanup(resources, now, total, free, in_flight=0, proposed=0, emergency=False, limit=20):
    """Advisory exact IDs only; executor refreshes capacity after each small batch."""
    if type(free) is not int or not 0 <= free <= total or not 1 <= limit <= 20:
        raise ValueError("Invalid capacity or batch limit")
    required = required_free_bytes(total, in_flight, proposed)
    shortage = max(0, required - free)
    if emergency and not shortage:
        return {"status": "ENOUGH_SPACE", "files": [], "required_free": required}
    candidates = [cleanup_candidate(resource, now, emergency) for resource in resources]
    candidates = sorted((row for row in candidates if row["eligible"]),
                        key=lambda row: (row["priority"], row["last_access_at"], -row["bytes"], row["resource_id"]))
    chosen, nominal = [], 0
    for candidate in candidates[:limit]:
        chosen.append(candidate)
        nominal += candidate["bytes"]
        if emergency and nominal >= shortage:
            break
    return {"status": "CANDIDATES_REQUIRE_FRESH_VALIDATION" if chosen else "PAUSE_PREPARATION_PROTECTED_ONLY",
            "files": chosen, "required_free": required, "shortage": shortage,
            "nominal_reclaimable": nominal}


def weekly_cleanup_due(now, last_completed, idle_seconds, playing):
    if playing or not nonnegative(idle_seconds) or idle_seconds < 600 or not nonnegative(now):
        return False
    local = datetime.fromtimestamp(now, BJT)
    slot = (local - timedelta(days=local.weekday())).replace(hour=5, minute=0, second=0, microsecond=0)
    if local < slot:
        slot -= timedelta(days=7)
    return last_completed is None or (nonnegative(last_completed) and last_completed < slot.timestamp())


class PlaybackCoverage:
    """Watch evidence, not max position. Test/probe/seek cannot finish a work."""
    def __init__(self, duration, purpose="user", intervals=None):
        if not nonnegative(duration) or duration <= 0 or purpose not in {"user", "test", "probe", "preload"}:
            raise ValueError("Invalid playback evidence")
        self.duration, self.purpose = float(duration), purpose
        self.intervals = []
        self.previous = None
        for start, end in intervals or []:
            self._merge(start, end)

    def _merge(self, start, end):
        if not all(nonnegative(value) for value in (start, end)) or not 0 <= start < end <= self.duration:
            raise ValueError("Invalid coverage interval")
        merged = []
        for a, b in sorted(self.intervals + [[float(start), float(end)]]):
            if merged and a <= merged[-1][1] + .05:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        # Pathologically fragmented evidence is not sufficient for completion.
        if len(merged) > 4096:
            raise ValueError("Playback coverage budget exceeded")
        self.intervals = merged

    def sample(self, position, monotonic_time, speed=1):
        if not all(nonnegative(value) for value in (position, monotonic_time)) or position > self.duration:
            self.previous = None
            return
        previous, self.previous = self.previous, (float(position), float(monotonic_time), speed)
        if self.purpose != "user" or previous is None or speed != 1 or previous[2] != 1:
            return
        delta, elapsed = position - previous[0], monotonic_time - previous[1]
        # Short gaps only. Jumps, reverse/fast play, sleep and restart do not
        # accrue unseen content. A seek boundary resets even if later resumed.
        if 0 < elapsed <= 10 and 0 < delta <= elapsed + .75:
            self._merge(previous[0], position)

    def seek(self):
        self.previous = None

    @property
    def fraction(self):
        return min(1.0, sum(end - start for start, end in self.intervals) / self.duration)

    def completed(self, natural_end):
        return self.purpose == "user" and natural_end is True and self.fraction >= .9
