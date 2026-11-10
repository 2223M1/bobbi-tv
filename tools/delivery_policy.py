"""Only pinned notices may cross the otherwise document-clean package boundary."""
import re

POLICY = 'pinned-notices-v2'
# Match document filenames only. A license directory is not permission to
# discard a .py/.ttf/.wav, and e.g. license_status.py is executable input.
EXCLUDE = re.compile(
    r'(^|/)(?:[^/]*(?:copyright|licen[cs]e|notice|copying|attribution|'
    r'asset-provenance|third.party)[^/]*\.(?:md|txt|json|rst|html)|'
    r'(?:licen[cs]e|copying|notice|copyright)(?:-[a-z0-9_-]+)?|'
    r'(?:licenses?/)(?:[^/]+/)*[^/]+\.(?:md|txt|json|rst|html))$', re.I)


def require_clean(paths, component=None):
    from vendor_licenses import load_manifest
    allowed = {(row['component'], row['path']) for row in load_manifest().get('deliveries', [])}
    def permitted(path):
        if component is not None:
            return (component, path) in allowed
        prefix, separator, relative = path.partition('/')
        return bool(separator) and (prefix, relative) in allowed
    if any(EXCLUDE.search(path) and not permitted(path) for path in paths):
        raise ValueError('Document policy conflict; review input before refreshing inventory')
