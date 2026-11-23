"""Fixed upstream ownership boundary; validation never installs or enables addons.

Version ordering follows Kodi 21.3 CAddonVersion / CompareComponent (Team Kodi,
GPL-2.0-or-later), not PEP440/SemVer. Invalid or overflowing forms fail closed.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET


UPSTREAM_COMPONENTS = frozenset(('script.module.certifi', 'script.module.chardet',
    'script.module.idna', 'script.module.infotagger', 'script.module.jurialmunkey',
    'script.module.requests', 'script.module.routing', 'script.module.urllib3',
    'script.skinvariables'))
OWNED_COMPONENTS = frozenset(('plugin.video.bobbi', 'plugin.video.bobbi.library',
    'plugin.video.bobbi.torrent', 'repository.bobbi', 'resource.uisounds.bobbi-modern',
    'script.bobbi.opensubtitles', 'script.bobbi.setup', 'script.bobbi.start',
    'script.module.bobbi.catalog', 'script.module.bobbi.core', 'script.module.bobbi.mdsub',
    'script.module.bobbi.platform', 'skin.bobbi.cinema'))
FULL_COMPONENTS = OWNED_COMPONENTS | UPSTREAM_COMPONENTS


def managed_components(expected):
    """Only the reviewed complete inventory opts into external preservation."""
    expected = frozenset(expected)
    return OWNED_COMPONENTS if expected == FULL_COMPONENTS else expected


def project_state(state, managed=OWNED_COMPONENTS):
    """Project already-validated generation metadata, without touching disk."""
    return dict(sequence=state['sequence'],
                versions={name: version for name, version in state['versions'].items() if name in managed})


def kodi_version(value):
    from .updates import UpdateError
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise UpdateError('Unsupported Kodi addon version')
    match = re.fullmatch(r'(?:([0-9]{1,10}):)?([A-Za-z0-9.+_@~]+)(?:-([A-Za-z0-9.+_@~]+))?', value)
    if not match or any(len(n) > 10 or int(n) > 2147483647 for n in re.findall(r'\d+', value)):
        raise UpdateError('Unsupported Kodi addon version')
    return int(match[1] or 0), match[2].lower(), (match[3] or '').lower()


def _compare_component(a, b):
    while a and b:
        while a and b and not a[0].isdigit() and not b[0].isdigit():
            if a[0] != b[0]:
                if a[0] == '~':
                    return -1
                if b[0] == '~':
                    return 1
                return -1 if a[0] < b[0] else 1
            a, b = a[1:], b[1:]
        if a and b and (not a[0].isdigit() or not b[0].isdigit()):
            if a[0] == '~':
                return -1
            if b[0] == '~':
                return 1
            return -1 if a[0].isdigit() else 1
        # Kodi uses strtol here, including an optional leading plus if one
        # side ended in the non-digit loop (e.g. "1." == "1.+0").
        left, right = re.match(r'(?:\+?\d+)?', a)[0], re.match(r'(?:\+?\d+)?', b)[0]
        first, second = int(left or 0), int(right or 0)
        if first != second:
            return -1 if first < second else 1
        a, b = a[len(left):], b[len(right):]
    if not a and not b:
        return 0
    return (-1 if a[0] == '~' else 1) if a else (1 if b[0] == '~' else -1)


def compare_versions(left, right):
    a, b = kodi_version(left), kodi_version(right)
    if a[0] != b[0]:
        return -1 if a[0] < b[0] else 1
    return _compare_component(a[1], b[1]) or _compare_component(a[2], b[2])


def _addon(root, name):
    from .updates import UpdateError, _safe_path
    path = _safe_path(Path(root) / name / 'addon.xml')
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise UpdateError('Kodi dependency missing or invalid: ' + name + '; install/update it in Kodi')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise UpdateError('Kodi dependency XML declarations rejected: ' + name)
    try:
        node = ET.fromstring(raw)
    except ET.ParseError:
        raise UpdateError('Kodi dependency XML invalid: ' + name) from None
    if node.tag != 'addon' or node.get('id') != name:
        raise UpdateError('Kodi dependency identity mismatch: ' + name)
    try:
        kodi_version(node.get('version'))
    except UpdateError:
        raise UpdateError('Kodi dependency version invalid: ' + name
                          + '; install/update it in Kodi') from None
    return node


def check_dependencies(addons_root, candidate_root, managed=OWNED_COMPONENTS):
    """Return required upstream minimums; Kodi/native virtuals are out of scope.

    All nine originals must already exist. Only this fixed set is traversed;
    candidate-owned files are read from staging, never substituted from live.
    Kodi's enabled/origin state is checked by the caller, never changed here.
    """
    from .updates import UpdateError
    if frozenset(managed) != OWNED_COMPONENTS:
        raise UpdateError('Unreviewed upstream ownership boundary')
    installed = {name: _addon(addons_root, name) for name in sorted(UPSTREAM_COMPONENTS)}
    minimums = dict.fromkeys(UPSTREAM_COMPONENTS, '0.0.0')
    nodes = list(installed.values())
    for name in sorted(OWNED_COMPONENTS):
        # A rollback may remove a component absent from the previous generation.
        if (Path(candidate_root) / name).exists():
            nodes.append(_addon(candidate_root, name))
    for node in nodes:
        for dependency in node.findall('./requires/import'):
            name = dependency.get('addon')
            if name not in UPSTREAM_COMPONENTS or dependency.get('optional') == 'true':
                continue
            required = dependency.get('version', '0.0.0')
            try:
                kodi_version(required)
            except UpdateError:
                raise UpdateError('Kodi dependency requirement invalid: ' + name
                                  + '; install/update ' + node.get('id') + ' in Kodi') from None
            if compare_versions(required, minimums[name]) > 0:
                minimums[name] = required
    for name, required in minimums.items():
        if compare_versions(installed[name].get('version'), required) < 0:
            raise UpdateError('Kodi dependency too old: ' + name + ' requires ' + required
                              + '; install/update it in Kodi')
    return dict(sorted(minimums.items()))
