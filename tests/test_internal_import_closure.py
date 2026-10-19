"""Catch inherited namespace moves without requiring optional Kodi services."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_static_internal_module_imports_resolve_to_actual_source():
    roots = dict(lib=ROOT / 'addons/plugin.video.bobbi/lib',
        bobbi_core=ROOT / 'addons/script.module.bobbi.core/lib/bobbi_core',
        bobbi_platform=ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform',
        bobbi_catalog=ROOT / 'addons/script.module.bobbi.catalog/lib/bobbi_catalog')
    missing = []
    for path in (ROOT / 'addons').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names = ([node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                     else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                prefix, _, suffix = name.partition('.')
                if prefix not in roots or not suffix:
                    continue
                target = roots[prefix].joinpath(*suffix.split('.'))
                # Kodi permits namespace-package directories without __init__.
                if not target.is_dir() and not target.with_suffix('.py').is_file():
                    missing.append((path.relative_to(ROOT).as_posix(), name))
    assert not missing


def test_authored_candidate_source_parses_under_kodi_python38_grammar():
    for path in (ROOT / 'addons').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path), feature_version=(3, 8))
