import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.project_metadata import tmdb_key, ATTRIBUTION


def document():
    return dict(schema=1, application='Bobbi TV', api_key='a' * 32,
                use='personal-noncommercial', attribution=ATTRIBUTION)


def test_project_key_is_application_configuration(tmp_path):
    path = tmp_path / 'application.json'
    path.write_text(json.dumps(document()), encoding='utf-8')
    assert tmdb_key(path) == 'a' * 32
    assert tmdb_key(tmp_path / 'missing') == ''


@pytest.mark.parametrize('field,value', [('schema', True), ('schema', 2),
    ('api_key', 'token'), ('api_key', None), ('application', 'unrelated'),
    ('use', 'commercial'), ('attribution', ''), ('session', 'not-allowed')])
def test_project_configuration_is_strict(tmp_path, field, value):
    path = tmp_path / 'application.json'
    row = document()
    row[field] = value
    path.write_text(json.dumps(row), encoding='utf-8')
    assert tmdb_key(path) == ''


def test_oversized_or_invalid_config_does_not_block_startup(tmp_path):
    path = tmp_path / 'application.json'
    for value in ('x' * 2049, 'not-json', '[]', 'null'):
        path.write_text(value, encoding='utf-8')
        assert tmdb_key(path) == ''


def test_warmup_uses_same_initialization_as_catalogue():
    source = (ROOT / 'addons/plugin.video.bobbi/lib/services/preloader.py').read_text(encoding='utf-8')
    assert 'ensure_tmdb_init()' in source
    assert 'tmdb.api_key =' not in source
