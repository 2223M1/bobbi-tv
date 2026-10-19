"""One bounded startup budget shared by the BT worker and its parent."""
DOWNLOAD_SECONDS = 30
CONTROL_SECONDS = 30
HANDOFF_SECONDS = 45


def bounded_seconds(value, default, maximum):
    try:
        parsed = int(value) if not isinstance(value, bool) else 0
    except (ValueError, TypeError, OverflowError):
        parsed = 0
    return min(parsed, maximum) if parsed > 0 else default


def budgets(metadata=30, buffering=90):
    metadata = bounded_seconds(metadata, 30, 120)
    buffering = bounded_seconds(buffering, 90, 300)
    # Metadata may need refreshing once at the file-buffer boundary. Control
    # covers upload/poll overshoot; handoff covers sidecars and native AV startup.
    return dict(metadata=metadata, buffering=buffering,
                total=DOWNLOAD_SECONDS + CONTROL_SECONDS + 2 * metadata + buffering + HANDOFF_SECONDS)
