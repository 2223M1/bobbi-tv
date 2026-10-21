"""Canonical notices retain original bytes and are extracted into build outputs."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import provenance_document as provenance
import build_release


def test_all_originals_have_one_canonical_source_and_valid_hashes():
    entries = provenance.records(ROOT)
    assert len(entries) == 22
    for name in entries:
        assert not (ROOT / name).exists(), name
    private = json.loads(entries['release/private-assets.json'])
    for row in private['files']:
        if row['target'] in entries:
            assert hashlib.sha256(entries[row['target']]).hexdigest() == row['sha256']
    assert not (ROOT / 'docs/THIRD_PARTY_AUDIT.md').exists()
    assert not (ROOT / 'docs/research/juku-full-20261019/README.md').exists()


@pytest.mark.parametrize('raw', [b'Copyright\nTerms\n', b'Copyright\r\nTerms\r\n', b'No final newline'])
def test_exact_byte_roundtrip_and_canonical_updates(tmp_path, raw):
    doc = tmp_path / provenance.DOCUMENT
    doc.parent.mkdir(parents=True)
    doc.write_text(provenance.render('notices/a.txt', raw), encoding='utf-8')
    assert provenance.read_source(tmp_path, 'notices/a.txt') == raw
    changed = raw + b'\n'
    if b'\r\n' in raw:
        changed = raw + b'\r\n'
    provenance.write_source(tmp_path, 'notices/a.txt', changed)
    assert provenance.read_source(tmp_path, 'notices/a.txt') == changed
    assert not (tmp_path / 'notices/a.txt').exists()


def test_tamper_and_duplicates_are_rejected(tmp_path):
    doc = tmp_path / provenance.DOCUMENT
    doc.parent.mkdir(parents=True)
    block = provenance.render('notices/a.txt', b'Copyright\n')
    doc.write_text(block.replace('Copyright', 'Wrong'), encoding='utf-8')
    with pytest.raises(ValueError, match='digest'):
        provenance.records(tmp_path)
    doc.write_text(block + '\n' + block, encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate'):
        provenance.records(tmp_path)


def test_unrelated_component_does_not_inherit_notices_by_basename(tmp_path):
    assert provenance.component_records(ROOT, tmp_path / 'skin.bobbi.cinema') == {}


def test_generated_components_keep_full_original_licenses(tmp_path):
    for addon in ('skin.bobbi.cinema', 'resource.uisounds.bobbi-modern', 'script.module.bobbi.core'):
        root = ROOT / 'addons' / addon
        notices = provenance.component_records(ROOT, root)
        assert notices
        output = tmp_path / (addon + '.zip')
        names = build_release.files(root)
        build_release.archive(root, names, output)
        with zipfile.ZipFile(output) as package:
            for name, raw in notices.items():
                assert package.read(addon + '/' + name) == raw
            if addon == 'skin.bobbi.cinema':
                assert addon + '/COPYRIGHT.zh-CN.md' in package.namelist()
                assert addon + '/ASSET-PROVENANCE.md' not in package.namelist()
