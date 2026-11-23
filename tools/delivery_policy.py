"""Only exact manifest-listed notices cross the document-clean boundary.

Retaining conflicting upstream evidence is not distribution clearance; the
vendor-license gate independently keeps unresolved components blocked.
"""
import re

POLICY = 'pinned-notices-v2'
# Match document filenames only. A license directory is not permission to
# discard a .py/.ttf/.wav, and e.g. license_status.py is executable input.
EXCLUDE = re.compile(
    r'(^|/)(?:[^/]*(?:copyright|licen[cs]e|notice|copying|attribution|'
    r'asset-' + 'provenance|third.party)[^/]*\.(?:md|txt|json|rst|html)|'
    r'(?:licen[cs]e|copying|notice|copyright)(?:-[a-z0-9_-]+)?|'
    r'(?:licenses?/)(?:[^/]+/)*[^/]+\.(?:md|txt|json|rst|html))$', re.I)


RETIRED_SKIN_FONTS = frozenset({'NetflixSans-Regular.ttf', 'NetflixSans-Bold.ttf', 'fzltdhk.ttf', 'BobbiDisplay.ttf'})


def require_clean(paths, component=None):
    paths = tuple(paths)
    if any(path.rsplit('/', 1)[-1].casefold() in {n.casefold() for n in RETIRED_SKIN_FONTS} for path in paths):
        raise ValueError('Retired skin font in package')
    from vendor_licenses import load_manifest
    allowed = {(row['component'], row['path']) for row in load_manifest().get('deliveries', [])}
    def permitted(path):
        if component is not None:
            return (component, path) in allowed
        prefix, separator, relative = path.partition('/')
        return bool(separator) and (prefix, relative) in allowed
    if any(EXCLUDE.search(path) and not permitted(path) for path in paths):
        raise ValueError('Document policy conflict; review input before refreshing inventory')
