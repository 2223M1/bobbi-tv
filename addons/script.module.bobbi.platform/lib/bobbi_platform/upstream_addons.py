"""Fixed upstream ownership boundary and authoritative dependency closure planner.

Version ordering follows Kodi 21.3 CAddonVersion / CompareComponent (Team Kodi,
GPL-2.0-or-later), not PEP440/SemVer. Invalid or overflowing forms fail closed.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET


UPSTREAM_COMPONENTS = frozenset((
    'script.module.certifi',
    'script.module.chardet',
    'script.module.idna',
    'script.module.infotagger',
    'script.module.jurialmunkey',
    'script.module.requests',
    'script.module.routing',
    'script.module.urllib3',
    'script.skinvariables',
))
OWNED_COMPONENTS = frozenset((
    'plugin.video.bobbi',
    'plugin.video.bobbi.library',
    'plugin.video.bobbi.torrent',
    'repository.bobbi',
    'resource.uisounds.bobbi-modern',
    'script.bobbi.opensubtitles',
    'script.bobbi.setup',
    'script.bobbi.start',
    'script.module.bobbi.catalog',
    'script.module.bobbi.core',
    'script.module.bobbi.mdsub',
    'script.module.bobbi.platform',
    'skin.bobbi.cinema',
))
FULL_COMPONENTS = OWNED_COMPONENTS | UPSTREAM_COMPONENTS
HOST_COMPONENTS = frozenset(('script.module.pycryptodome',))
VIRTUAL_ADDONS = frozenset((
    'xbmc.python',
    'xbmc.gui',
    'xbmc.addon',
    'xbmc.core',
    'xbmc.json',
    'xbmc.metadata',
    'xbmc.webinterface',
    'kodi.resource',
    'kodi.audioengine',
))

# Explicit dependency closure states
NOT_REQUIRED = 'NOT_REQUIRED'
SATISFIED = 'SATISFIED'
DISABLED = 'DISABLED'
MISSING_SEEDABLE = 'MISSING_SEEDABLE'
MISSING_HOST = 'MISSING_HOST'
NEEDS_UPGRADE = 'NEEDS_UPGRADE'
DIRECTORY_CONFLICT = 'DIRECTORY_CONFLICT'
STATE_UNKNOWN = 'STATE_UNKNOWN'
CANCELLED = 'CANCELLED'
DEPENDENCY_STATES = (
    NOT_REQUIRED,
    SATISFIED,
    DISABLED,
    MISSING_SEEDABLE,
    MISSING_HOST,
    NEEDS_UPGRADE,
    DIRECTORY_CONFLICT,
    STATE_UNKNOWN,
    CANCELLED,
)

# Tested installed Kodi HTTP floors (release/http-runtime-policy.json).
DECLARED_HTTP_RUNTIME_FLOORS = {
    'script.module.requests': '2.31.0',
    'script.module.urllib3': '2.2.3',
}

_ADDON_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def valid_addon_id(value):
    return (isinstance(value, str)
            and bool(_ADDON_ID_RE.fullmatch(value))
            and '..' not in value)


def managed_components(expected):
    """Only the reviewed complete inventory opts into external preservation."""
    expected = frozenset(expected)
    return OWNED_COMPONENTS if expected == FULL_COMPONENTS else expected


def project_state(state, managed=OWNED_COMPONENTS):
    """Project already-validated generation metadata, without touching disk."""
    return dict(
        sequence=state['sequence'],
        versions={name: version for name, version in state['versions'].items() if name in managed},
    )


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


def _parse_manifest_bytes(raw, name):
    from .updates import UpdateError
    if not isinstance(raw, (bytes, bytearray)) or not 0 < len(raw) <= 1024 * 1024:
        raise UpdateError('Kodi dependency missing or invalid: ' + name + '; install/update it in Kodi')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise UpdateError('Kodi dependency XML declarations rejected: ' + name)
    try:
        node = ET.fromstring(raw)
    except ET.ParseError:
        raise UpdateError('Kodi dependency XML invalid: ' + name) from None
    if node.tag != 'addon' or node.get('id') != name or not valid_addon_id(name):
        raise UpdateError('Kodi dependency identity mismatch: ' + name)
    try:
        kodi_version(node.get('version'))
    except UpdateError:
        raise UpdateError('Kodi dependency version invalid: ' + name
                          + '; install/update it in Kodi') from None
    seen_imports = set()
    for dep in node.findall('./requires/import'):
        dep_id = dep.get('addon')
        if not valid_addon_id(dep_id):
            raise UpdateError('DEPENDENCY_GRAPH_INVALID:invalid_import_id:' + name)
        opt = dep.get('optional')
        if opt not in (None, 'false', 'true'):
            raise UpdateError('DEPENDENCY_GRAPH_INVALID:invalid_optional:' + name)
        if dep_id == name and opt != 'true':
            raise UpdateError('DEPENDENCY_GRAPH_INVALID:cycle:' + name)
        seen_imports.add(dep_id)
    return node


def _addon(root, name):
    from .updates import UpdateError, _safe_path
    if not valid_addon_id(name):
        raise UpdateError('DEPENDENCY_GRAPH_INVALID:invalid_addon_id')
    path = _safe_path(Path(root) / name / 'addon.xml')
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise UpdateError('Kodi dependency missing or invalid: ' + name + '; install/update it in Kodi')
    return _parse_manifest_bytes(path.read_bytes(), name)


def _has_residual_entry(root, name):
    from .updates import _safe_path
    base = _safe_path(Path(root))
    target = base / name
    if target.is_symlink():
        return True
    return target.exists()


def plan_dependencies(
    addons_root,
    candidate_root=None,
    managed=OWNED_COMPONENTS,
    *,
    details=None,
    candidate_manifests=None,
    strict_roots=False,
    require_installed_upstream=False,
):
    """Single authoritative dependency closure planner across Owned -> Upstream/Host.

    - Roots: candidate's owned managed addons (`managed`).
    - Optional `<import optional="true">` edges are ignored.
    - Rejects cycles, malformed/illegal addon IDs/versions, path traversal, or
      conflicting manifest identities BEFORE any disk write.
    - Retained installed upstream addons read their OWN installed `addon.xml` so
      unreachable/unused staged manifests never impose ghost floor requirements.
    """
    from .updates import UpdateError, _safe_path

    managed_set = frozenset(managed)
    if not managed_set or any(not valid_addon_id(n) for n in managed_set) or not managed_set <= OWNED_COMPONENTS:
        raise UpdateError('Unreviewed upstream ownership boundary')

    addons_path = _safe_path(addons_root) if addons_root is not None else None
    cand_path = _safe_path(candidate_root) if candidate_root is not None else None
    if cand_path is None and candidate_manifests is None:
        raise UpdateError('DEPENDENCY_GRAPH_INVALID:missing_candidate')

    def load_candidate_node(name):
        if candidate_manifests is not None:
            if name not in candidate_manifests:
                return None
            return _parse_manifest_bytes(candidate_manifests[name], name)
        entry = cand_path / name
        if entry.is_symlink():
            raise UpdateError('Symlink update path')
        if not entry.exists():
            return None
        return _addon(cand_path, name)

    # Pre-validate all root manifests in candidate
    owned_nodes = {}
    for name in sorted(managed_set):
        node = load_candidate_node(name)
        if node is None:
            if strict_roots:
                raise UpdateError('Kodi dependency missing or invalid: ' + name + '; install/update it in Kodi')
            continue
        owned_nodes[name] = node

    # If staged upstream manifests exist on disk/memory, validate their identity/XML
    # only when needed for seeding, UNLESS strict_roots is requested (e.g. full stage),
    # in which case we still ensure no corrupt/conflicting manifest identity hides in stage.
    staged_upstream_cache = {}

    def get_staged_seed(name):
        if name not in staged_upstream_cache:
            staged_upstream_cache[name] = load_candidate_node(name)
        return staged_upstream_cache[name]

    floors = {}
    edges = {}
    resolved_info = {}
    rpc_cache = {}

    def query_details(name):
        if details is None:
            return None, False
        if name not in rpc_cache:
            try:
                info = details(name)
            except UpdateError as err:
                if str(err).startswith('ADDON_STATE_UNKNOWN:'):
                    rpc_cache[name] = (None, True)
                else:
                    raise
            else:
                if info is not None:
                    if (not isinstance(info, dict)
                            or type(info.get('enabled')) is not bool
                            or not isinstance(info.get('version'), str)):
                        rpc_cache[name] = (None, True)
                    else:
                        kodi_version(info['version'])
                        rpc_cache[name] = (dict(info), False)
                else:
                    rpc_cache[name] = (None, False)
        return rpc_cache[name]

    def select_upstream(name):
        """Select authoritative manifest & initial state for a reachable upstream/host addon."""
        if name in resolved_info:
            return resolved_info[name]

        if name in HOST_COMPONENTS:
            info, unknown = query_details(name)
            if unknown:
                res = dict(id=name, node=None, manifest_source=None, installed=None, base_state=STATE_UNKNOWN)
            elif info is None:
                res = dict(id=name, node=None, manifest_source=None, installed=None, base_state=MISSING_HOST)
            else:
                res = dict(id=name, node=None, manifest_source='host_rpc', installed=info,
                           base_state=SATISFIED if info['enabled'] else DISABLED)
            resolved_info[name] = res
            return res

        # name in UPSTREAM_COMPONENTS
        if details is not None:
            info, unknown = query_details(name)
            if unknown:
                res = dict(id=name, node=None, manifest_source=None, installed=None, base_state=STATE_UNKNOWN)
                resolved_info[name] = res
                return res
            has_dir = _has_residual_entry(addons_path, name) if addons_path is not None else False
            if info is not None:
                if has_dir:
                    try:
                        live_node = _addon(addons_path, name)
                    except UpdateError:
                        res = dict(id=name, node=None, manifest_source='conflict', installed=info,
                                   base_state=DIRECTORY_CONFLICT)
                        resolved_info[name] = res
                        return res
                    if live_node.get('version') != info['version']:
                        res = dict(id=name, node=None, manifest_source='conflict', installed=info,
                                   base_state=DIRECTORY_CONFLICT)
                        resolved_info[name] = res
                        return res
                    res = dict(id=name, node=live_node, manifest_source='installed', installed=info,
                               base_state=SATISFIED if info['enabled'] else DISABLED)
                else:
                    res = dict(id=name, node=None, manifest_source='host_rpc', installed=info,
                               base_state=SATISFIED if info['enabled'] else DISABLED)
                resolved_info[name] = res
                return res
            # info is None (not registered in Kodi)
            if has_dir:
                res = dict(id=name, node=None, manifest_source='conflict', installed=None,
                           base_state=DIRECTORY_CONFLICT)
                resolved_info[name] = res
                return res
            seed_node = get_staged_seed(name)
            if seed_node is not None:
                res = dict(id=name, node=seed_node, manifest_source='staged_seed', installed=None,
                           base_state=MISSING_SEEDABLE)
            else:
                res = dict(id=name, node=None, manifest_source=None, installed=None,
                           base_state=MISSING_HOST)
            resolved_info[name] = res
            return res

        # Filesystem-only mode (check_dependencies or ce_storage.install_plan)
        if require_installed_upstream:
            live_node = _addon(addons_path, name)
            info = {'version': live_node.get('version'), 'enabled': True}
            res = dict(id=name, node=live_node, manifest_source='installed', installed=info,
                       base_state=SATISFIED)
            resolved_info[name] = res
            return res

        # Space-budget read-only estimation mode
        has_dir = _has_residual_entry(addons_path, name) if addons_path is not None else False
        if has_dir:
            xml_file = addons_path / name / 'addon.xml'
            if not xml_file.is_symlink() and xml_file.is_file():
                live_node = _addon(addons_path, name)
                info = {'version': live_node.get('version'), 'enabled': True}
                res = dict(id=name, node=live_node, manifest_source='installed', installed=info,
                           base_state=SATISFIED)
            else:
                # Directory already exists on disk (e.g. origin-only fixture); never seed over it.
                seed_node = get_staged_seed(name)
                res = dict(id=name, node=seed_node, manifest_source='existing_dir', installed=None,
                           base_state=DIRECTORY_CONFLICT)
            resolved_info[name] = res
            return res

        seed_node = get_staged_seed(name)
        if seed_node is not None:
            res = dict(id=name, node=seed_node, manifest_source='staged_seed', installed=None,
                       base_state=MISSING_SEEDABLE)
        else:
            res = dict(id=name, node=None, manifest_source=None, installed=None,
                       base_state=MISSING_HOST)
        resolved_info[name] = res
        return res

    # 3-color DFS from candidate roots to extract reachable closure & reject any cycle
    UNVISITED, VISITING, VISITED = 0, 1, 2
    color = {}

    def visit(node_id, xml_node):
        color[node_id] = VISITING
        edges.setdefault(node_id, set())
        if xml_node is not None:
            for dep in xml_node.findall('./requires/import'):
                target = dep.get('addon')
                if dep.get('optional') == 'true':
                    continue
                required = dep.get('version', '0.0.0')
                if target in VIRTUAL_ADDONS:
                    try:
                        kodi_version(required)
                    except UpdateError:
                        raise UpdateError('Kodi dependency requirement invalid: ' + target
                                          + '; install/update ' + node_id + ' in Kodi') from None
                    continue
                if target in OWNED_COMPONENTS:
                    try:
                        kodi_version(required)
                    except UpdateError:
                        raise UpdateError('Kodi dependency requirement invalid: ' + target
                                          + '; install/update ' + node_id + ' in Kodi') from None
                    edges[node_id].add(target)
                    state_color = color.get(target, UNVISITED)
                    if state_color == VISITING:
                        raise UpdateError('DEPENDENCY_GRAPH_INVALID:cycle:' + target)
                    cand_target = owned_nodes.get(target)
                    if cand_target is None and target != 'script.bobbi.start':
                        cand_target = load_candidate_node(target)
                        if cand_target is not None:
                            owned_nodes[target] = cand_target
                    if cand_target is not None:
                        if compare_versions(cand_target.get('version'), required) < 0:
                            raise UpdateError('DEPENDENCY_GRAPH_INVALID:owned_floor:' + target)
                        if state_color == UNVISITED:
                            visit(target, cand_target)
                    continue
                if target in UPSTREAM_COMPONENTS | HOST_COMPONENTS:
                    try:
                        kodi_version(required)
                    except UpdateError:
                        raise UpdateError('Kodi dependency requirement invalid: ' + target
                                          + '; install/update ' + node_id + ' in Kodi') from None
                    edges[node_id].add(target)
                    if compare_versions(required, floors.get(target, '0.0.0')) > 0:
                        floors[target] = required
                    state_color = color.get(target, UNVISITED)
                    if state_color == VISITING:
                        raise UpdateError('DEPENDENCY_GRAPH_INVALID:cycle:' + target)
                    selected = select_upstream(target)
                    if state_color == UNVISITED:
                        visit(target, selected['node'])
                    continue
                # Out-of-scope virtuals: check_dependencies ignores unexamined virtuals;
                # strict host preparation rejects unknown non-virtual addon requirements.
                if details is not None:
                    try:
                        kodi_version(required)
                    except UpdateError:
                        raise UpdateError('Kodi dependency requirement invalid: ' + target
                                          + '; install/update ' + node_id + ' in Kodi') from None
                    raise UpdateError('DEPENDENCY_GRAPH_INVALID:unknown_dependency:' + target)
        color[node_id] = VISITED

    for root_id in sorted(owned_nodes):
        if color.get(root_id, UNVISITED) == UNVISITED:
            visit(root_id, owned_nodes[root_id])

    # Topological sort over required external dependencies (UPSTREAM_COMPONENTS | HOST_COMPONENTS)
    required_ext = sorted(floors)
    dep_needs = {
        name: {child for child in edges.get(name, set()) if child in floors}
        for name in required_ext
    }
    order = []
    remaining = dict(dep_needs)
    while remaining:
        ready = sorted(name for name, parents in remaining.items() if not parents)
        if not ready:
            raise UpdateError('DEPENDENCY_GRAPH_INVALID:cycle')
        for name in ready:
            del remaining[name]
        for parents in remaining.values():
            parents.difference_update(ready)
        order.extend(ready)

    items = {}
    seedable = []
    blocking = []
    for name in sorted(UPSTREAM_COMPONENTS | HOST_COMPONENTS):
        if name not in floors:
            items[name] = dict(
                id=name,
                required=False,
                minimum=None,
                installed_version=None,
                enabled=None,
                state=NOT_REQUIRED,
                manifest_source=None,
            )
            continue
        minimum = floors[name]
        selected = resolved_info[name]
        installed = selected['installed']
        state = selected['base_state']
        installed_ver = installed['version'] if installed else None
        enabled_flag = installed['enabled'] if installed else None

        if state in (SATISFIED, DISABLED):
            if compare_versions(installed_ver, minimum) < 0:
                state = NEEDS_UPGRADE
        elif state == MISSING_SEEDABLE:
            seed_ver = selected['node'].get('version')
            if compare_versions(seed_ver, minimum) < 0:
                state = MISSING_HOST
            else:
                seedable.append(name)

        if require_installed_upstream and name in UPSTREAM_COMPONENTS and state == NEEDS_UPGRADE:
            raise UpdateError('Kodi dependency too old: ' + name + ' requires ' + minimum
                              + '; install/update it in Kodi')

        if state in (STATE_UNKNOWN, DIRECTORY_CONFLICT, NEEDS_UPGRADE, MISSING_HOST):
            blocking.append(name)

        items[name] = dict(
            id=name,
            required=True,
            minimum=minimum,
            installed_version=installed_ver,
            enabled=enabled_flag,
            state=state,
            manifest_source=selected['manifest_source'],
        )

    upstream_minimums = {name: floors[name] for name in sorted(floors) if name in UPSTREAM_COMPONENTS}
    return dict(
        minimums=dict(sorted(floors.items())),
        upstream_minimums=upstream_minimums,
        order=order,
        items=items,
        seedable=sorted(seedable),
        blocking=blocking,
    )


def check_dependencies(addons_root, candidate_root, managed=OWNED_COMPONENTS):
    """Return reachable required upstream minimums; Kodi/native virtuals are out of scope.

    Only reachable non-optional upstream dependencies are required; unused legacy
    helpers (such as removed Skin Variables edges) are not demanded or seeded.
    Retained upstream modules use their installed manifests, never staged seeds.
    """
    from .updates import UpdateError
    if frozenset(managed) != OWNED_COMPONENTS:
        raise UpdateError('Unreviewed upstream ownership boundary')
    plan = plan_dependencies(
        addons_root,
        candidate_root,
        managed=managed,
        details=None,
        require_installed_upstream=True,
    )
    return plan['upstream_minimums']


def inspect_http_runtime():
    """Record actual loaded requests/urllib3 versions, file paths, and Python runtime."""
    import sys
    import requests
    import urllib3
    from .updates import UpdateError

    req_ver = getattr(requests, '__version__', '')
    u3_ver = getattr(urllib3, '__version__', '')
    if compare_versions(req_ver, DECLARED_HTTP_RUNTIME_FLOORS['script.module.requests']) < 0:
        raise UpdateError(
            'Loaded requests runtime too old: ' + str(req_ver)
            + ' < ' + DECLARED_HTTP_RUNTIME_FLOORS['script.module.requests']
        )
    if compare_versions(u3_ver, DECLARED_HTTP_RUNTIME_FLOORS['script.module.urllib3']) < 0:
        raise UpdateError(
            'Loaded urllib3 runtime too old: ' + str(u3_ver)
            + ' < ' + DECLARED_HTTP_RUNTIME_FLOORS['script.module.urllib3']
        )
    return {
        'python_version': sys.version,
        'python_version_info': list(sys.version_info[:3]),
        'requests': {
            'version': req_ver,
            'file': Path(requests.__file__).resolve().as_posix(),
        },
        'urllib3': {
            'version': u3_ver,
            'file': Path(urllib3.__file__).resolve().as_posix(),
        },
    }
