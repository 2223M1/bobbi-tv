import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('release_version_preflight', ROOT / 'tools/check_release_versions.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def offer():
    return {'tag': 'ce2184', 'sequence': 2026102184, 'versions': {
        'script.bobbi.start': '0.2.123', 'script.module.bobbi.platform': '0.1.98',
        'plugin.video.bobbi': '0.1.97'}}


def test_changed_bootstrap_cannot_reuse_published_launcher_filename():
    versions = dict(offer()['versions'], **{'script.module.bobbi.platform': '0.1.99'})
    with pytest.raises(ValueError, match='script.bobbi.start.*0.2.123'):
        gate.check_versions(offer(), versions, [
            'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py'])


def test_changed_plugin_requires_new_component_version():
    with pytest.raises(ValueError, match='plugin.video.bobbi'):
        gate.check_versions(offer(), offer()['versions'], ['addons/plugin.video.bobbi/lib/router.py'])


def test_new_component_and_launcher_versions_pass_without_allocating_release():
    versions = {'script.bobbi.start': '0.2.124', 'script.module.bobbi.platform': '0.1.99',
                'plugin.video.bobbi': '0.1.98'}
    result = gate.check_versions(offer(), versions, [
        'addons/plugin.video.bobbi/lib/router.py',
        'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py'])
    assert set(result['changed_owned_components']) == set(versions)
    assert result['sequence_allocated'] is False
    assert result['publication_verified'] is False


def test_unrelated_docs_do_not_force_component_versions():
    result = gate.check_versions(offer(), offer()['versions'], ['docs/architecture.md'])
    assert result['changed_owned_components'] == []


def test_removed_owned_component_fails_closed():
    with pytest.raises(ValueError, match='component missing'):
        gate.check_versions(offer(), {}, ['addons/plugin.video.bobbi/addon.xml'])
