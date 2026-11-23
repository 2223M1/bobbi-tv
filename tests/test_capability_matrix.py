"""One evidence matrix; historical device results cannot certify new source."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_matrix_uses_six_nonexclusive_classes_and_resolvable_evidence():
    value = json.loads((ROOT / 'release/capability-matrix.json').read_text(encoding='utf-8'))
    assert value['schema'] == 2
    classes = {'implemented', 'partial', 'entry_missing', 'reliability_missing', 'absent', 'duplicated'}
    assert set(value['classification_values']) == classes == set(value['classification_labels'])
    rows = value['product_capabilities']
    assert len({row['id'] for row in rows}) == len(rows)
    assert {name for row in rows for name in row['references']} >= {'Infuse', 'Jellyfin', 'Plex', 'Kodi', 'ShareLib', 'LiquidTiles'}
    for row in rows:
        assert row['classification'] and set(row['classification']) <= classes
        assert row['device'] and type(row['stage']) is int and 0 <= row['stage'] <= 6
        for group in ('entries', 'implementation', 'tests'):
            assert type(row[group]) is list
            for path in row[group]:
                target = (ROOT / path).resolve()
                assert ROOT in target.parents and target.is_file(), (row['id'], group, path)
        if 'implemented' in row['classification']:
            assert row['entries'] and row['implementation'] and row['tests'], row['id']
        if any(state in row['classification'] for state in classes - {'implemented'}):
            assert row['remaining'], row['id']


def test_unfrozen_worktree_does_not_inherit_historical_device_certification():
    value = json.loads((ROOT / 'release/capability-matrix.json').read_text(encoding='utf-8'))
    identity = value['source_identity']
    assert identity['catalog_schema'] >= 4
    assert len(identity['baseline_commit']) == len(identity['baseline_tree']) == 40
    assert value['historical_rows'] and value['historical_scope']
    assert 'rows' not in value  # No ambiguous mixed-generation list.
    if identity['state'] == 'working_tree_not_frozen':
        assert identity['commit'] is identity['tree'] is None
        assert value['device_acceptance']['current_source'] == 'not_deployed'
        assert all(row['device'] == 'not_tested_current_source' for row in value['product_capabilities'])
    else:
        assert identity['state'] == 'frozen'
        assert len(identity['commit']) == len(identity['tree']) == 40
