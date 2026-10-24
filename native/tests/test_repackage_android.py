"""The approved thin torrent adapter must not open arbitrary inventory migration."""
import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'repackage_android', Path(__file__).resolve().parents[1] / 'repackage-android.py')
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)
TORRENT = 'plugin.video.bobbi.torrent'


def manifest(ids):
    return {'components': [{'id': value} for value in ids]}


BASE = ['component.' + str(index) for index in range(21)]


def test_current_display_version_preserves_sequence_and_signing_template():
    source = 'android {\n versionCode Integer.parseInt(System.getenv("BOBBI_ANDROID_VERSION_CODE"))\n versionName "0.2.0-private.1 (Kodi 21.3)"\n}\n'
    updated = PACKAGE.versioned_gradle(source, '2072 (Kodi 21.3)')
    assert 'versionName "2072 (Kodi 21.3)"' in updated
    assert source.replace('0.2.0-private.1 (Kodi 21.3)', '2072 (Kodi 21.3)') == updated


@pytest.mark.parametrize('value', ['', 'x";exec()', 'x\nversionCode 1', 'x'*81])
def test_version_name_rejects_gradle_injection(value):
    with pytest.raises(ValueError):
        PACKAGE.versioned_gradle('versionName "old"\n//BOBBI_ANDROID_VERSION_CODE', value)


def test_unknown_version_template_rejected():
    with pytest.raises(ValueError):
        PACKAGE.versioned_gradle('versionName "old"', '2072')


@pytest.mark.parametrize('ids', [BASE, BASE + [TORRENT]])
def test_unchanged_inventory_remains_valid_without_approval(ids):
    result = PACKAGE.validate_component_inventory(manifest(ids), manifest(ids))
    assert result == {'previous_count': len(ids), 'current_count': len(ids),
                      'added_components': [], 'removed_components': []}


def test_exact_reviewed_migration_requires_explicit_approval():
    with pytest.raises(ValueError, match='explicit review'):
        PACKAGE.validate_component_inventory(manifest(BASE), manifest(BASE + [TORRENT]))
    result = PACKAGE.validate_component_inventory(manifest(BASE), manifest(BASE + [TORRENT]), TORRENT)
    assert result == {'previous_count': 21, 'current_count': 22,
                      'added_components': [TORRENT], 'removed_components': []}


@pytest.mark.parametrize('before,after', [
    (BASE, BASE + ['plugin.video.unreviewed']),
    (BASE, BASE + [TORRENT, 'plugin.video.unreviewed']),
    (BASE, BASE[:-1] + [TORRENT]),
    (BASE, BASE[:-1] + [TORRENT, 'plugin.video.unreviewed']),
    (BASE + [TORRENT], BASE),
    (BASE[:-1], BASE[:-1] + [TORRENT]),
    (BASE + ['extra.component'], BASE + ['extra.component', TORRENT]),
])
def test_approval_never_allows_removals_replacements_or_another_delta(before, after):
    with pytest.raises(ValueError, match='explicit review'):
        PACKAGE.validate_component_inventory(manifest(before), manifest(after), TORRENT)


@pytest.mark.parametrize('approval', ['*', 'plugin.video.unreviewed', 'PLUGIN.VIDEO.BOBBI.TORRENT'])
def test_unreviewed_approval_is_rejected_even_with_unchanged_inventory(approval):
    with pytest.raises(ValueError, match='not been reviewed'):
        PACKAGE.validate_component_inventory(manifest(BASE), manifest(BASE), approval)


def test_stale_approval_is_not_silently_ignored():
    with pytest.raises(ValueError, match='not present'):
        PACKAGE.validate_component_inventory(manifest(BASE + [TORRENT]), manifest(BASE + [TORRENT]), TORRENT)


@pytest.mark.parametrize('invalid', [[], [None], [''], BASE + ['COMPONENT.0'], BASE + [BASE[0]]])
@pytest.mark.parametrize('side', ['previous', 'frozen'])
def test_malformed_or_duplicate_component_inventory_fails_closed(invalid, side):
    inputs = {'previous': manifest(BASE), 'frozen': manifest(BASE)}
    inputs[side] = manifest(invalid)
    with pytest.raises(ValueError):
        PACKAGE.validate_component_inventory(**inputs)
