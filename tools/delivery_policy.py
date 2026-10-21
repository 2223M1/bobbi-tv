"""Owner-approved document-only cleanup; never exclude executable or asset bytes.

This is a private packaging choice, not a grant of redistribution rights.
Exact source inventories, upstream IDs and inline code credits remain intact.
"""
import re

POLICY = 'private-document-clean-v1'
# Match document filenames only. A license directory is not permission to
# discard a .py/.ttf/.wav, and e.g. license_status.py is executable input.
EXCLUDE = re.compile(
    r'(^|/)(?:[^/]*(?:copyright|licen[cs]e|notice|copying|attribution|'
    r'asset-provenance|third.party)[^/]*\.(?:md|txt|json|rst|html)|'
    r'(?:licen[cs]e|copying|notice|copyright)(?:-[a-z0-9_-]+)?|'
    r'(?:licenses?/)(?:[^/]+/)*[^/]+\.(?:md|txt|json|rst|html))$', re.I)


def require_clean(paths):
    if any(EXCLUDE.search(path) for path in paths):
        raise ValueError('Document policy conflict; review input before refreshing inventory')
