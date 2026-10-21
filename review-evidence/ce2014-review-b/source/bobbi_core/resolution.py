"""Conservative filename resolution *classes*, not probed media dimensions.

Used by both quality badges and Cinema ranking. Cropped landscape encodes retain
their standard width class; conflicting claims remain unknown. Pure local work.
"""
import re


_TAG = re.compile(r"(?<![a-z0-9])(4320p|8k|2160p?|4k|1080[pi]|720p|576p|480p)(?![a-z0-9])", re.I)
_DIMENSIONS = re.compile(r"(?<![a-z0-9])(\d{3,5})\s*[x×]\s*(\d{3,5})(?![a-z0-9])", re.I)


def resolution_class(title):
    """Return 480/720/1080/2160/4320, or 0 for absent/ambiguous claims.

    Small encoder padding (1922x1080) and common cinema crops (3840x1600)
    are recognized. Portrait, episode numbers and arbitrary dimensions are not
    promoted to HD/4K. An 8K dimension claim must not be silently labelled 4K.
    """
    text = str(title or "")
    claims = set()
    for tag in _TAG.findall(text):
        tag = tag.lower()
        claims.add(4320 if tag in {"4320p", "8k"} else
                   2160 if tag in {"2160", "2160p", "4k"} else
                   1080 if tag.startswith("1080") else 720 if tag == "720p" else 480)
    for width, height in _DIMENSIONS.findall(text):
        width, height = int(width), int(height)
        # Standard 4:3 HD releases are not low-resolution crops of widescreen
        # video. Keep exact standard pairs; arbitrary/portrait dimensions and
        # conflicting tags must still remain unknown.
        found = {(1440, 1080): 1080, (960, 720): 720}.get((width, height), 0)
        for resolution, min_w, max_w, min_h, max_h in (
            (4320, 7648, 8192, 2880, 4320),
            (2160, 3824, 4096, 1440, 2160),
            (1080, 1904, 2048, 720, 1088),
            (720, 1264, 1280, 480, 720),
            (480, 640, 854, 360, 576),
        ):
            if min_w <= width <= max_w and min_h <= height <= max_h:
                found = resolution
                break
        claims.add(found)
    return next(iter(claims)) if len(claims) == 1 else 0
