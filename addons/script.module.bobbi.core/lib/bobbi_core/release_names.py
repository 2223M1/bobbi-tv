"""Unchanged release-family and filename specification policies."""
import re
from bobbi_core.resolution import resolution_class

def family(name):
    name = str(name or '').casefold()
    # Raw release titles can contain slash-separated aliases. Those aren't
    # paths: dropping the prefix would also drop the release-group identity.
    if name.startswith('/') or re.match(r'^[a-z]:[\\/]', name):
        name = name.replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'\.[a-z0-9]{2,4}$', '', name)
    name = re.sub(r'\[[0-9a-f]{8}\]', '', name)
    name = re.sub(r'(?<!\w)s\d{1,2}[ ._-]*e\d{1,3}(?!\d)', ' EP ', name)
    # Episode numbers vary; release revisions do not. Keep v2/v10 distinct.
    name = re.sub(r'(?<= - )\d{1,3}(v\d+)?(?=\s|\[|$)', r'EP \1', name)
    return re.sub(r'[\W_]+', ' ', name).strip()

def specifications(name):
    text = re.sub(r'[._\[\]()-]+', ' ', str(name or '')).casefold()
    def has(pattern):
        return bool(re.search(r'(?<!\w)(?:' + pattern + r')(?!\w)', text))
    codec = 'hevc' if has(r'hevc|[hx]\s?265') else 'avc' if has(r'avc|[hx]\s?264') else ''
    origin = 'remux' if has('remux|bdremux') else 'bluray' if has(r'blu\s?ray|bdrip') else 'web' if has(r'web\s?dl|webrip|web') else ''
    hdr = 'dv' if has(r'dv|dovi|dolby\s?vision') else 'hdr' if has('hdr10|hdr|pq') else 'sdr-claimed'
    return resolution_class(name), codec, origin, hdr
