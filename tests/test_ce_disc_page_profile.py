"""CE-only cache changes may not enter the generic Kodi patch series or change the ABI gate."""
import hashlib
import json
from pathlib import Path

from test_ce_native_reapply import tool

ROOT = Path(__file__).resolve().parents[1]


def test_ce_disc_patch_is_pinned_and_not_an_android_patch():
    root = ROOT/'native/patches'
    generic = json.loads((root/'series.json').read_text())['patches']
    ce, = json.loads((root/'ce-downstream-series.json').read_text())['patches']
    assert ce not in generic and ce['file'] not in {r['file'] for r in generic}
    patch = (root/ce['file']).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == ce['sha256'] == tool.PROFILES['discpages2141']['canonical_patch_sha256']
    assert all(b'/DVDInputStreams/BlurayIsoCache.' in line for line in patch.splitlines() if line.startswith(b'diff --git'))
    assert b'forwardPrefetchPages' not in patch


def test_only_reviewed_binary_uses_old_subtitle_abi():
    from bobbi_core.runtime_paths import known_ce_native
    p = tool.PROFILES['discpages2141']
    assert known_ce_native(p['candidate']) and known_ce_native(p['predecessor']['binary'])
    assert not known_ce_native(('1' if p['candidate'][0]=='0' else '0')+p['candidate'][1:])
    assert p['minimum_versions']['script.module.bobbi.core'] == '0.1.76'


def test_audible_tempo_is_an_exact_ce_successor_not_an_android_capability():
    from bobbi_core.runtime_paths import known_ce_native
    p = tool.PROFILES['pcmtempo2148']
    root = ROOT/'native/patches'
    declaration = json.loads((root/'ce-audible-tempo-series.json').read_text())
    patch, = declaration['patches']
    assert declaration['predecessor_sha256'] == p['predecessor']['binary'] == tool.PROFILES['discpages2141']['candidate']
    assert patch['sha256'] == hashlib.sha256((root/patch['file']).read_bytes()).hexdigest() == p['canonical_patch_sha256']
    assert not any(row['file']==patch['file'] for row in json.loads((root/'series.json').read_text())['patches'])
    assert known_ce_native(p['candidate']) and not known_ce_native('0'+p['candidate'][1:])
