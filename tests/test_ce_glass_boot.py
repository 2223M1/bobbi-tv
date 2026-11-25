import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('glass_boot', ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_glass_boot.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def material(name, seq):
    if seq in guard.BRANDED_SEQUENCES and seq <= guard.APPROVED_CC and name == guard.SOURCE_SELECT:
        import base64, gzip
        return gzip.decompress(base64.b64decode((ROOT/'tests/fixtures/ce2166-2174-source-select.xml.gz.b64').read_bytes()))
    if seq in guard.BRANDED_SEQUENCES and seq < guard.APPROVED_CC and name == 'skin.bobbi.cinema/1080p/Includes_Views.xml':
        import gzip
        return gzip.decompress((ROOT/'tests/fixtures/ce2166-2173-views.xml.gz').read_bytes())
    if seq == guard.OPTICS and name.endswith('/sidebar-classic.png'):
        return (ROOT/'tests/fixtures/ce2169-sidebar-classic.png').read_bytes()
    if seq in guard.BRANDED_SEQUENCES:
        hist_zip = ROOT/'tests/fixtures/ce2174-2185-materials.zip'
        if hist_zip.exists():
            with zipfile.ZipFile(hist_zip) as archived:
                if name in archived.namelist():
                    raw = archived.read(name)
                    if seq < guard.ZIP_OPT_IN and name.endswith('/DialogButtonMenu.xml'):
                        raw = raw.replace(b'!Skin.HasSetting(BobbiLiquidGlassEnabled)', b'Skin.HasSetting(BobbiGlassPrerendered)').replace(b'Skin.HasSetting(BobbiLiquidGlassEnabled)', b'!Skin.HasSetting(BobbiGlassPrerendered)')
                    return raw
        raw = (ROOT/'addons'/name).read_bytes()
        if seq < guard.ZIP_OPT_IN and name.endswith('/DialogButtonMenu.xml'):
            raw = raw.replace(b'!Skin.HasSetting(BobbiLiquidGlassEnabled)', b'Skin.HasSetting(BobbiGlassPrerendered)').replace(b'Skin.HasSetting(BobbiLiquidGlassEnabled)', b'!Skin.HasSetting(BobbiGlassPrerendered)')
        return raw
    with zipfile.ZipFile(ROOT/'tests/fixtures/ce2165-glass-materials.zip') as archived:
        return archived.read(name)


def test_packaged_real_renderer_identity_and_private_snapshot(tmp_path):
    src = ROOT/'addons'/guard.PACKAGED_FILE
    data = src.read_bytes()
    assert data[:6] == b'\x7fELF\x01\x01' and int.from_bytes(data[18:20], 'little') == 40
    assert hashlib.sha256(data).hexdigest() == guard.REFINED_RENDERER
    source = tmp_path/'candidate.so'
    runtime = tmp_path/'private'
    runtime.mkdir()
    source.write_bytes(data)
    dest = guard.runtime_copy(source, runtime)
    source.write_bytes(b'unapproved replacement')
    assert dest.read_bytes() == data
    assert guard.runtime_copy(source, runtime) is None
    dest.chmod(0o600)


@pytest.mark.parametrize('sequence', sorted(guard.PRODUCTS))
@pytest.mark.parametrize('change', ['', 'state', 'unknown', 'mixed', 'string', 'disk', 'binary', 'renderer', 'missing'])
def test_load_only_on_the_reviewed_product(tmp_path, monkeypatch, sequence, change):
    addons, state = tmp_path/'addons', tmp_path/'state.json'
    exe, lib = tmp_path/'kodi.bin', tmp_path/'lib.so'
    if sequence in guard.PACKAGED_SEQUENCES:
        lib = addons / guard.PACKAGED_FILE
        lib.parent.mkdir(parents=True)
    exe.write_bytes(b'core')
    lib.write_bytes(b'glass')
    monkeypatch.setattr(guard, 'KODI', hashlib.sha256(b'core').hexdigest())
    monkeypatch.setattr(guard, 'RENDERER', hashlib.sha256(b'glass').hexdigest())
    monkeypatch.setattr(guard, 'REFINED_RENDERER', hashlib.sha256(b'refined').hexdigest())
    if sequence in (*guard.REFINED_SEQUENCES, *guard.BRANDED_SEQUENCES):
        lib.write_bytes(b'refined')
        for name in guard.material_checks(sequence):
            target = addons / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(material(name, sequence))
    v = dict(guard.PRODUCTS[sequence])
    if change == 'mixed':
        other = 2026102156 if sequence != 2026102156 else 2026102157
        v['script.module.bobbi.platform'] = guard.PRODUCTS[other]['script.module.bobbi.platform']
    for ident, version in v.items():
        folder = addons/ident
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'addon.xml').write_text(f'<addon id="{ident}" version="{version}"/>')
    reported = max(guard.PRODUCTS) + 1 if change == 'unknown' else str(sequence) if change == 'string' else sequence
    state.write_text(json.dumps(dict(sequence=reported, versions=v)))
    if change == 'state': state.write_text('[]')
    if change == 'disk': (addons/'skin.bobbi.cinema/addon.xml').write_text('<bad/>')
    if change == 'binary': exe.write_bytes(b'new')
    if change == 'renderer': lib.write_bytes(b'new')
    if change == 'missing': lib.unlink()
    assert guard.eligible(state, addons, exe, lib) == (not change)


@pytest.mark.parametrize('sequence', [2026102158, *guard.REFINED_SEQUENCES])
def test_rollback_selects_old_renderer_and_cannot_mix_materials(tmp_path, monkeypatch, sequence):
    from shutil import copyfile
    addons, state, exe = tmp_path/'addons', tmp_path/'state', tmp_path/'kodi'
    exe.write_bytes(b'kodi')
    monkeypatch.setattr(guard, 'KODI', hashlib.sha256(exe.read_bytes()).hexdigest())
    for name, digest in [('MODULE', 'RENDERER'), ('REFINED_MODULE', 'REFINED_RENDERER')]:
        path = tmp_path/name
        path.write_bytes(name.encode())
        monkeypatch.setattr(guard, name, path)
        monkeypatch.setattr(guard, digest, hashlib.sha256(path.read_bytes()).hexdigest())
    for name in guard.REFINED_FILES:
        target = addons / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(material(name, sequence))
    versions = guard.PRODUCTS[sequence]
    for ident, version in versions.items():
        target = addons/ident/'addon.xml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'<addon id="{ident}" version="{version}"/>')
    state.write_text(json.dumps(dict(sequence=sequence, versions=versions)))
    refined = sequence in guard.REFINED_SEQUENCES
    assert guard.verified_module(state, addons, exe) == (guard.REFINED_MODULE if refined else guard.MODULE)
    assert not guard.eligible(state, addons, exe, guard.MODULE if refined else guard.REFINED_MODULE)
    if refined:
        for name in guard.REFINED_FILES:
            (addons/name).write_bytes(b'stale')
            assert guard.verified_module(state, addons, exe) is None
            (addons/name).write_bytes(material(name, sequence))


@pytest.mark.parametrize('case,allowed', [
    ('user-only', True), ('older-maintenance', True), ('equal', True),
    ('tie-differs', False), ('newer-unknown', False), ('rollback', False),
    ('pending', False), ('activation', False), ('host-pending', False), ('no-proof', False),
    ('wrong-proof', False), ('wrong-tx', False), ('bad-tree', False), ('bad-vector', False),
    ('low-watermark', False), ('boolean-schema', False), ('mixed-files', False),
    ('changed-material', False), ('wrong-kodi', False), ('wrong-renderer', False),
    ('changes-during-hash', False),
    ('stock-zip', True), ('stock-without-journal', False), ('stock-rollback', False),
])
@pytest.mark.parametrize('seq', [guard.BRANDED_LABEL, guard.OPTICS, guard.SLATE, guard.SURFACES, guard.CONTROL_CENTER, guard.CONTROL_CENTER_TYPE, guard.APPROVED_CC, guard.ZIP_CRYPTO, *guard.STOCK_SEQUENCES])
def test_normal_zip_has_its_own_completed_generation(tmp_path, monkeypatch, case, allowed, seq):
    tx = '1' * 32
    versions = dict(guard.PRODUCTS[seq])
    state, journal = tmp_path/'maintenance.json', tmp_path/'user/installation.json'
    txdir = journal.parent/tx
    txdir.mkdir(parents=True)
    proof = txdir/'complete.json'
    completion = dict(schema=1, tx=tx, sequence=seq, trees={'stage': 'a' * 64})
    user = dict(schema=1, sequence=seq, high_watermark=seq, tx=tx, phase='complete',
                items=[dict(id=k, had_old=True) for k in versions], versions=versions)
    if case != 'user-only':
        previous = seq if case in ('equal', 'tie-differs') else seq + 1 if case == 'newer-unknown' else guard.REFINED_PICKER
        stored = dict(guard.PRODUCTS.get(previous, versions))
        if case == 'tie-differs': stored['skin.bobbi.cinema'] = '99'
        state.write_text(json.dumps(dict(sequence=previous, versions=stored)))
    if case == 'rollback': user['phase'] = 'restored'
    if case == 'stock-rollback': user['phase'] = 'restored'
    if case == 'pending': user['phase'] = 'switching'
    if case == 'activation': user['phase'] = 'activation_pending'
    if case == 'host-pending': user['host_pending'] = 'restore'
    if case == 'wrong-proof': completion['sequence'] -= 1
    if case == 'wrong-tx': completion['tx'] = '2' * 32
    if case == 'bad-tree': completion['trees'] = {'../other': 'x'}
    if case == 'bad-vector': user['items'] *= 2
    if case == 'low-watermark': user['high_watermark'] -= 1
    if case == 'boolean-schema': user['schema'] = True
    journal.write_text(json.dumps(user))
    if case != 'no-proof': proof.write_text(json.dumps(completion))
    addons, exe, lib = tmp_path/'addons', tmp_path/'kodi', tmp_path/'renderer'
    if seq in guard.PACKAGED_SEQUENCES:
        lib = addons / guard.PACKAGED_FILE
        lib.parent.mkdir(parents=True)
    for ident, ver in versions.items():
        x = addons/ident/'addon.xml'
        x.parent.mkdir(parents=True, exist_ok=True)
        x.write_text(f'<addon id="{ident}" version="{ver}"/>')
    for rel in guard.material_checks(seq):
        target = addons/rel
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(material(rel, seq))
    exe.write_bytes(b'kodi')
    lib.write_bytes(b'glass')
    monkeypatch.setattr(guard, 'KODI', guard.sha(exe))
    monkeypatch.setattr(guard, 'REFINED_RENDERER', guard.sha(lib))
    if case == 'mixed-files': (addons/'skin.bobbi.cinema/addon.xml').write_text('<bad/>')
    if case == 'changed-material': target.write_bytes(b'other')
    if case == 'wrong-kodi': exe.write_bytes(b'unknown')
    if case.startswith('stock-'):
        exe.write_bytes(b'qualified-stock')
        monkeypatch.setattr(guard, 'STOCK_CE213_AMLOGIC_NG', guard.sha(exe))
        if case == 'stock-without-journal':
            journal.unlink()
            state.write_text(json.dumps(dict(sequence=seq, versions=versions)))
        allowed = allowed and seq in guard.STOCK_SEQUENCES
    if case == 'wrong-renderer': lib.write_bytes(b'unknown')
    if case == 'changes-during-hash':
        digest = guard.sha
        def change(path):
            if path == exe:
                journal.write_text(json.dumps(dict(user, phase='restoring')))
            return digest(path)
        monkeypatch.setattr(guard, 'sha', change)
    assert (guard.verified_module(state, addons, exe, lib, installation=journal) == lib) is allowed
