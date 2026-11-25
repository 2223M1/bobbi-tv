"""Delivery, source-archive, and signed-bundle hygiene contracts.

Only exact manifest-listed notices cross the document-clean boundary.
Retaining conflicting upstream evidence is not distribution clearance; the
vendor-license gate independently keeps unresolved components blocked.
Historical CE2021 one-off repackaging orchestration has been retired after
migrating its SignedBundle, sequence-collision, and atomic-staging negative
controls onto current build_release / ce_release_gate / SignedBundle contracts.
"""
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'addons/script.module.bobbi.platform/lib') not in sys.path:
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))

POLICY = 'pinned-notices-v2'
PUBLIC_CA = 'third_party/addons/script.module.certifi/lib/certifi/cacert.pem'
CURATED_CATALOG = 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'
DEFAULT_EMBEDDED_BUNDLE = 'script.bobbi.start/resources/complete.bobbi-update.zip'

# Match document filenames only. A license directory is not permission to
# discard a .py/.ttf/.wav, and e.g. license_status.py is executable input.
EXCLUDE = re.compile(
    r'(^|/)(?:[^/]*(?:copyright|licen[cs]e|notice|copying|attribution|'
    r'asset-' + r'provenance|third.party)[^/]*\.(?:md|txt|json|rst|html)|'
    r'(?:licen[cs]e|copying|notice|copyright)(?:-[a-z0-9_-]+)?|'
    r'(?:licenses?/)(?:[^/]+/)*[^/]+\.(?:md|txt|json|rst|html))$', re.I)

RETIRED_SKIN_FONTS = frozenset({
    'NetflixSans-Regular.ttf',
    'NetflixSans-Bold.ttf',
    'fzltdhk.ttf',
    'BobbiDisplay.ttf',
})


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


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


def validate_source_paths(names):
    """A Git snapshot, not an unexamined workspace/account backup."""
    folded = set()
    for name in names:
        parts = PurePosixPath(name).parts
        lower = name.lower()
        if (not parts or name.startswith('/') or '\\' in name or ':' in name
                or any(part in ('.', '..') for part in parts)
                or lower in folded):
            raise ValueError('INVALID_SOURCE_PATH')
        folded.add(lower)
        if any(part.lower() in ('.git', '.private', '.venv', '.venv-closure', '__pycache__') for part in parts):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if parts[0].lower() in ('profile', 'profiles', 'userdata', 'dist', 'staging'):
            raise ValueError('LOCAL_STATE_IN_SOURCE')
        if (lower.endswith(('.keystore', '.jks', '/tmdb-project.json'))
                or lower.endswith(('.sqlite', '.sqlite3', '.db')) and name != CURATED_CATALOG
                or lower.endswith('.pem') and name != PUBLIC_CA):
            raise ValueError('LOCAL_SECRET_OR_DATABASE_IN_SOURCE')


def junit_counts(path):
    root = ET.parse(path).getroot()
    rows = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    if not rows:
        raise ValueError('MISSING_JUNIT_SUITE')
    result = {key: sum(int(row.get(key, '0')) for row in rows)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    result['passed'] = result['tests'] - result['failures'] - result['errors'] - result['skipped']
    return result


def inspect_source_archive(path, expected):
    with zipfile.ZipFile(path) as source:
        infos = [row for row in source.infolist() if not row.is_dir()]
        names = [row.filename for row in infos]
        validate_source_paths(names)
        if set(names) != set(expected) or len(names) != len(expected):
            raise ValueError('SOURCE_ARCHIVE_TREE_MISMATCH')
        evidence = []
        for row in infos:
            data = source.read(row.filename)
            if row.filename.startswith('review-evidence/'):
                evidence.append(dict(
                    path=row.filename,
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    acceptance='See the individual receipt and report; this index does not turn it into a pass',
                ))
    return evidence


def require_clean_frozen_checkout(product_commit, git_runner=None, output=None):
    """Reject dirty working trees or post-freeze product diffs before creating output."""
    if output is not None and Path(output).exists():
        raise ValueError('OUTPUT_EXISTS')
    runner = git_runner or git
    if runner('status', '--porcelain').strip():
        raise ValueError('HANDOFF_CHECKOUT_DIRTY')
    if runner('diff', product_commit, 'HEAD', '--', 'addons', 'third_party', 'release').strip():
        raise ValueError('PRODUCT_CHANGED_AFTER_FREEZE')


def safe_members(archive):
    seen = set()
    for item in archive.infolist():
        name = item.filename
        path = PurePosixPath(name)
        if (name in seen or path.is_absolute() or '..' in path.parts or
                '\\' in name or ':' in name or item.flag_bits & 1):
            raise ValueError('Unsafe or duplicate archive member')
        seen.add(name)
        yield item


def checked_sequence(value, registry, minimum_floor=2026102022):
    used = registry.get('allocated') if isinstance(registry, dict) else None
    if (type(value) is not int or not isinstance(used, list) or not used or
            any(type(n) is not int or n < 1 for n in used) or
            value <= max([minimum_floor] + used)):
        raise ValueError('New sequence above verified release registry required')
    return value
