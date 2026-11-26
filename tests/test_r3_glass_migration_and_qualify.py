"""R3 N3-06 Liquid Glass ELF qualification, 85/60 migration, post-2185 asset decoupling, and 7-state status tests."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'addons/script.module.bobbi.platform/lib') not in sys.path:
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))

from bobbi_platform import ce_glass_boot as boot
from bobbi_platform import ce_glass_host as glass_host
from bobbi_platform import glass_settings as gs
import update_glass_assets

RAW_BOX_DIR = Path(r'D:\AM6B-Project\AM6B-B-FULL-execution\AM6B\handoffs\n3-integrated-closure\device-before\raw-box-files')


def _uleb128(val: int) -> bytes:
    out = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def build_arm_attributes(*, cpu_arch: int = 14, simd_arch: int = 3, vfp_args: int = 1) -> bytes:
    body = bytearray()
    body.extend(_uleb128(5) + b'8-A\x00')
    body.extend(_uleb128(6) + _uleb128(cpu_arch))
    body.extend(_uleb128(12) + _uleb128(simd_arch))
    body.extend(_uleb128(28) + _uleb128(vfp_args))
    file_sub = b'\x01' + struct.pack('<I', 5 + len(body)) + bytes(body)
    vendor = b'aeabi\x00' + file_sub
    return b'A' + struct.pack('<I', 4 + len(vendor)) + vendor


def build_synthetic_elf32(
    *,
    ei_class: int = 1,
    e_type: int = 3,
    e_machine: int = 40,
    e_flags: int = 0x05000400,
    arm_attrs: bytes | None = None,
    exported_symbols: tuple[str, ...] = (),
    verdefs: tuple[str, ...] = (),
    dt_needed: tuple[str, ...] = (),
    salt: bytes = b'',
) -> bytes:
    """Build a compact, spec-compliant ELF32 LE binary with optional .ARM.attributes, .dynsym, .dynamic, .gnu.version_d."""
    if ei_class != 1:
        hdr = bytearray(64)
        hdr[:4] = b'\x7fELF'
        hdr[4] = ei_class
        hdr[5] = 1
        hdr[6] = 1
        return bytes(hdr) + salt

    strtab = bytearray(b'\x00')
    offsets: dict[str, int] = {}

    def intern(s: str) -> int:
        if s not in offsets:
            offsets[s] = len(strtab)
            strtab.extend(s.encode('ascii') + b'\x00')
        return offsets[s]

    for s in (*exported_symbols, *verdefs, *dt_needed):
        intern(s)

    dynsym = bytearray(16)  # STN_UNDEF
    for sym in exported_symbols:
        st_name = intern(sym)
        st_info = (1 << 4) | 2  # STB_GLOBAL, STT_FUNC
        dynsym.extend(struct.pack('<IIIBBH', st_name, 0x1000, 4, st_info, 0, 1))

    dyn_sec = bytearray()
    for soname in dt_needed:
        dyn_sec.extend(struct.pack('<iI', 1, intern(soname)))
    dyn_sec.extend(struct.pack('<iI', 0, 0))

    verdef_sec = bytearray()
    for idx, vname in enumerate(verdefs, start=1):
        is_last = idx == len(verdefs)
        vd_next = 0 if is_last else 28
        verdef_sec.extend(struct.pack('<HHHHIII', 1, 0, idx, 1, 0, 20, vd_next))
        verdef_sec.extend(struct.pack('<II', intern(vname), 0))

    # Section layout:
    # 0: NULL, 1: .dynstr, 2: .dynsym, 3: .dynamic, [4: .gnu.version_d], [last: .ARM.attributes]
    blobs: list[tuple[int, int, bytes]] = [
        (3, 0, bytes(strtab)),       # SHT_STRTAB (index 1)
        (11, 1, bytes(dynsym)),      # SHT_DYNSYM (link=1)
        (6, 1, bytes(dyn_sec)),      # SHT_DYNAMIC (link=1)
    ]
    if verdefs:
        blobs.append((0x6FFFFFFD, 1, bytes(verdef_sec)))
    if arm_attrs is not None:
        blobs.append((0x70000003, 0, arm_attrs))
    if salt:
        blobs.append((1, 0, salt))   # SHT_PROGBITS

    cur_off = 52
    payload = bytearray()
    shdrs = [struct.pack('<10I', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for sh_type, sh_link, data in blobs:
        pad = (4 - (cur_off % 4)) % 4
        if pad:
            payload.extend(b'\x00' * pad)
            cur_off += pad
        entsize = 16 if sh_type == 11 else 8 if sh_type == 6 else 0
        shdrs.append(struct.pack('<10I', 0, sh_type, 0, 0, cur_off, len(data), sh_link, 0, 4, entsize))
        payload.extend(data)
        cur_off += len(data)

    pad = (4 - (cur_off % 4)) % 4
    if pad:
        payload.extend(b'\x00' * pad)
        cur_off += pad
    e_shoff = cur_off
    sh_table = b''.join(shdrs)

    ehdr = bytearray(52)
    ehdr[:4] = b'\x7fELF'
    ehdr[4] = 1  # ELFCLASS32
    ehdr[5] = 1  # ELFDATA2LSB
    ehdr[6] = 1  # EV_CURRENT
    struct.pack_into(
        '<HHIIIIIHHHHHH',
        ehdr,
        16,
        e_type,
        e_machine,
        1,
        0x1000,
        0,
        e_shoff,
        e_flags,
        52,
        0,
        0,
        40,
        len(shdrs),
        0,
    )
    return bytes(ehdr) + bytes(payload) + sh_table


def populate_qualified_lib_dir(
    lib_dir: Path,
    *,
    include_gles_symlink: bool = True,
    include_ubo_symbol: bool = True,
    missing_gles_symbol: str | None = None,
    missing_egl_symbol: str | None = None,
    glibc_versions: tuple[str, ...] = ('GLIBC_2.4', 'GLIBC_2.17', 'GLIBC_2.34'),
) -> Path:
    lib_dir.mkdir(parents=True, exist_ok=True)
    gles_syms = [s for s in boot.REQUIRED_GLES2_SYMBOLS if s != missing_gles_symbol]
    if include_ubo_symbol:
        gles_syms.append(boot.OPTIONAL_GLES3_UBO_SYMBOL)
    egl_syms = [s for s in boot.REQUIRED_EGL_SYMBOLS if s != missing_egl_symbol]

    mali_bytes = build_synthetic_elf32(
        arm_attrs=build_arm_attributes(),
        exported_symbols=tuple(sorted(set(gles_syms) | set(egl_syms))),
    )
    mali_file = lib_dir / 'libMali.so'
    mali_file.write_bytes(mali_bytes)
    (lib_dir / 'libGLESv2.so.2').write_bytes(mali_bytes)
    if include_gles_symlink:
        (lib_dir / 'libGLESv2.so').write_bytes(mali_bytes)
    (lib_dir / 'libEGL.so').write_bytes(mali_bytes)

    (lib_dir / 'libc.so.6').write_bytes(build_synthetic_elf32(
        arm_attrs=build_arm_attributes(),
        verdefs=glibc_versions,
        exported_symbols=('dlopen', 'dlsym', 'fopen', 'rename'),
    ))
    (lib_dir / 'libm.so.6').write_bytes(build_synthetic_elf32(
        arm_attrs=build_arm_attributes(),
        verdefs=('GLIBC_2.4',),
        exported_symbols=('cosf', 'sinf'),
    ))
    (lib_dir / 'ld-linux-armhf.so.3').write_bytes(build_synthetic_elf32(
        arm_attrs=build_arm_attributes(),
        verdefs=('GLIBC_2.4',),
        exported_symbols=('__tls_get_addr',),
    ))
    return lib_dir


def populate_qualified_proc(
    proc_dir: Path,
    *,
    cpu_arch: str = '8',
    features: str = 'fp asimd evtstrm aes pmull sha1 sha2 crc32 neon',
) -> Path:
    proc_dir.mkdir(parents=True, exist_ok=True)
    lines = ['Processor\t: AArch64 Processor rev 4 (aarch64)' if cpu_arch == '8' else 'Processor\t: ARMv7 Processor rev 5 (v7l)']
    if cpu_arch is not None:
        lines.append(f'CPU architecture: {cpu_arch}')
    if features is not None:
        lines.append(f'Features\t: {features}')
    (proc_dir / 'cpuinfo').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return proc_dir


def stage_post_2185_install(storage: Path, *, sequence: int = 2026102186) -> tuple[Path, Path, Path]:
    addons = storage / '.kodi/addons'
    userdata = storage / '.kodi/userdata'
    journal = userdata / 'addon_data/script.bobbi.start/installation.json'
    state = storage / '.local/share/bobbi-private-updates/state.json'
    tx = 'a' * 32
    tx_dir = journal.parent / tx
    tx_dir.mkdir(parents=True, exist_ok=True)
    state.parent.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((ROOT / 'addons' / boot.GLASS_ASSETS_FILE).read_text(encoding='utf-8'))
    for rel in [boot.PACKAGED_FILE.as_posix(), boot.GLASS_ASSETS_FILE.as_posix(), *manifest['materials'].keys()]:
        dst = addons / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / 'addons' / rel).read_bytes())

    versions = {
        'skin.bobbi.cinema': '0.2.1',
        'plugin.video.bobbi': '0.2.5',
        'script.module.bobbi.platform': '0.2.3',
        'script.module.bobbi.core': '0.2.2',
    }
    for ident, ver in versions.items():
        xml_path = addons / ident / 'addon.xml'
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_text(f'<addon id="{ident}" version="{ver}"/>', encoding='utf-8')

    record = {
        'schema': 1,
        'sequence': sequence,
        'high_watermark': sequence,
        'tx': tx,
        'phase': 'complete',
        'host_pending': None,
        'items': [{'id': k, 'had_old': True} for k in sorted(versions)],
        'versions': versions,
    }
    proof = {'schema': 1, 'sequence': sequence, 'tx': tx, 'trees': {'stage': 'b' * 64}}
    journal.write_text(json.dumps(record), encoding='utf-8')
    (tx_dir / 'complete.json').write_text(json.dumps(proof), encoding='utf-8')

    skin_settings = userdata / 'addon_data/skin.bobbi.cinema/settings.xml'
    skin_settings.parent.mkdir(parents=True, exist_ok=True)
    skin_settings.write_text('<settings><setting id="BobbiLiquidGlassEnabled">true</setting></settings>', encoding='utf-8')
    return addons, state, journal


def test_guard_hash_and_glass_assets_manifest_are_exact():
    boot_bytes = (ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/ce_glass_boot.py').read_bytes()
    assert hashlib.sha256(boot_bytes).hexdigest() == gs.GUARD_HASH
    assert gs.N3R1_HASH in gs.OLD_UNITS
    assert b'--opt-in\n' in gs.OLD_UNITS[gs.N3R1_HASH]
    assert gs.CE2185_HASH in gs.OLD_UNITS
    assert update_glass_assets.main(['--check']) == 0


def test_post_2185_generation_decoupled_from_products_with_strict_asset_and_elf_checks(tmp_path):
    """R3-GLASS-ARTIFACT-C01: sequence > 2026102185 works without PRODUCTS entry, fails on tampered asset."""
    storage = tmp_path / 'storage'
    addons, state, journal = stage_post_2185_install(storage, sequence=2026102299)
    assert 2026102299 not in boot.PRODUCTS

    lib_dir = populate_qualified_lib_dir(tmp_path / 'usr_lib', include_ubo_symbol=False)
    proc_dir = populate_qualified_proc(tmp_path / 'proc')
    exe = tmp_path / 'kodi.bin'
    exe.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(), salt=b'other-ce-firmware'))
    assert boot.sha(exe) not in (boot.KODI, boot.STOCK_CE213_AMLOGIC_NG)

    resolved = boot.verified_module(state, addons, exe, installation=journal, lib_dirs=(lib_dir,), proc_root=proc_dir)
    assert resolved == addons / boot.PACKAGED_FILE

    # Tampering with any material listed in glass_assets.json must immediately reject
    target_xml = addons / 'skin.bobbi.cinema/1080p/DialogButtonMenu.xml'
    orig_bytes = target_xml.read_bytes()
    target_xml.write_bytes(orig_bytes + b'<!-- drift -->')
    assert boot.verified_module(state, addons, exe, installation=journal, lib_dirs=(lib_dir,), proc_root=proc_dir) is None
    target_xml.write_bytes(orig_bytes)
    assert boot.verified_module(state, addons, exe, installation=journal, lib_dirs=(lib_dir,), proc_root=proc_dir) == addons / boot.PACKAGED_FILE


def test_cpu_abi_separation_and_host_cpu_qualification_matrix(tmp_path):
    """N3-GL-ABI-01: Qualify real ARMv8+NEON CPU independently of 32-bit kodi.bin .ARM.attributes."""
    glass_host.clear_qualification_cache()
    renderer = ROOT / 'addons' / boot.PACKAGED_FILE
    lib_dir = populate_qualified_lib_dir(tmp_path / 'libs')
    proc_v8 = populate_qualified_proc(tmp_path / 'proc_v8')

    # 1) ARMv8+NEON host + ARMv7 hard-float kodi.bin (cpu_arch=10) -> QUALIFIED!
    exe_v7 = tmp_path / 'kodi_v7.bin'
    exe_v7.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(cpu_arch=10), salt=b'ce-armv7-target'))
    r1 = glass_host.qualify_host_cached(exe_v7, renderer, lib_dirs=(lib_dir,), proc_root=proc_v8)
    assert r1['ok'] is True
    assert r1['reason'] == 'QUALIFIED'
    assert r1['cpu_arch'] == 8
    assert r1['exe_cpu_arch'] == 10

    # 2) ARMv8+NEON host + stripped kodi.bin WITHOUT .ARM.attributes (non-allowlisted SHA) -> QUALIFIED!
    exe_stripped = tmp_path / 'kodi_stripped.bin'
    exe_stripped.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=None, salt=b'arbitrary-ce-build'))
    assert boot.sha(exe_stripped) not in (boot.KODI, boot.STOCK_CE213_AMLOGIC_NG)
    r2 = glass_host.qualify_host_cached(exe_stripped, renderer, lib_dirs=(lib_dir,), proc_root=proc_v8)
    assert r2['ok'] is True
    assert r2['reason'] == 'QUALIFIED'
    assert r2['cpu_arch'] == 8
    assert r2['exe_cpu_arch'] is None

    # 3) Missing or empty /proc/cpuinfo -> fail closed HOST_CPU_CAPABILITY_UNKNOWN!
    proc_missing = tmp_path / 'proc_missing'
    proc_missing.mkdir()
    r3_missing = glass_host.qualify_host_cached(exe_stripped, renderer, lib_dirs=(lib_dir,), proc_root=proc_missing)
    assert r3_missing['ok'] is False and r3_missing['reason'] == 'HOST_CPU_CAPABILITY_UNKNOWN'

    (proc_missing / 'cpuinfo').write_text('', encoding='utf-8')
    r3_empty = glass_host.qualify_host_cached(exe_stripped, renderer, lib_dirs=(lib_dir,), proc_root=proc_missing)
    assert r3_empty['ok'] is False and r3_empty['reason'] == 'HOST_CPU_CAPABILITY_UNKNOWN'

    # 4) ARMv7 /proc/cpuinfo (CPU architecture: 7) even if kodi.bin lacks attributes -> HOST_CPU_ARCH_UNSUPPORTED!
    proc_v7 = populate_qualified_proc(tmp_path / 'proc_v7', cpu_arch='7', features='half thumb fastmult vfp edsp neon vfpv3')
    r4 = glass_host.qualify_host_cached(exe_stripped, renderer, lib_dirs=(lib_dir,), proc_root=proc_v7)
    assert r4['ok'] is False and r4['reason'] == 'HOST_CPU_ARCH_UNSUPPORTED'

    # 5) ARMv8 /proc/cpuinfo missing neon/asimd -> HOST_SIMD_MISSING!
    proc_no_simd = populate_qualified_proc(tmp_path / 'proc_no_simd', cpu_arch='8', features='fp evtstrm aes sha2 crc32')
    r5 = glass_host.qualify_host_cached(exe_stripped, renderer, lib_dirs=(lib_dir,), proc_root=proc_no_simd)
    assert r5['ok'] is False and r5['reason'] == 'HOST_SIMD_MISSING'

    # 6) 64-bit kodi.bin (ELFCLASS64) on ARMv8+NEON host -> ELF_NOT_32BIT!
    exe_64 = tmp_path / 'kodi_aarch64.bin'
    exe_64.write_bytes(build_synthetic_elf32(ei_class=2, salt=b'aarch64-kodi'))
    r6 = glass_host.qualify_host_cached(exe_64, renderer, lib_dirs=(lib_dir,), proc_root=proc_v8)
    assert r6['ok'] is False and r6['reason'] == 'ELF_NOT_32BIT'


@pytest.mark.parametrize('failure_case,expected_prefix', [
    ('elf64', 'ELF_NOT_32BIT'),
    ('host_armv7', 'HOST_CPU_ARCH_UNSUPPORTED'),
    ('host_no_simd', 'HOST_SIMD_MISSING'),
    ('vfp_args_mismatch', 'ELF_VFP_ARGS_MISMATCH'),
    ('soft_float', 'ELF_NOT_HARD_FLOAT'),
    ('only_so2', 'MISSING_DT_NEEDED:libGLESv2.so'),
    ('old_glibc', 'MISSING_VERSION:libc.so.6:GLIBC_2.34'),
    ('missing_gl_sym', 'MISSING_GLES_SYMBOL:glUniformMatrix4fv'),
    ('missing_egl_sym', 'MISSING_EGL_SYMBOL:eglSwapBuffers'),
])
def test_elf_abi_soname_glibc_and_symbol_negative_controls_and_cache_invalidation(tmp_path, failure_case, expected_prefix):
    """R3-GLASS-QUALIFY-C01..C03 & R3-GLASS-BOUNDARY-C01."""
    glass_host.clear_qualification_cache()
    renderer = ROOT / 'addons' / boot.PACKAGED_FILE
    lib_dir = populate_qualified_lib_dir(
        tmp_path / 'libs',
        include_gles_symlink=(failure_case != 'only_so2'),
        missing_gles_symbol=('glUniformMatrix4fv' if failure_case == 'missing_gl_sym' else None),
        missing_egl_symbol=('eglSwapBuffers' if failure_case == 'missing_egl_sym' else None),
        glibc_versions=(('GLIBC_2.4', 'GLIBC_2.17', 'GLIBC_2.33') if failure_case == 'old_glibc'
                        else ('GLIBC_2.4', 'GLIBC_2.17', 'GLIBC_2.34')),
    )
    proc_dir = populate_qualified_proc(
        tmp_path / 'proc',
        cpu_arch=('7' if failure_case == 'host_armv7' else '8'),
        features=('fp evtstrm crc32' if failure_case == 'host_no_simd' else 'fp asimd evtstrm aes pmull sha1 sha2 crc32 neon'),
    )

    exe = tmp_path / 'kodi.bin'
    if failure_case == 'elf64':
        exe.write_bytes(build_synthetic_elf32(ei_class=2))
    elif failure_case == 'vfp_args_mismatch':
        exe.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(vfp_args=0)))
    elif failure_case == 'soft_float':
        exe.write_bytes(build_synthetic_elf32(e_type=2, e_flags=0x05000200, arm_attrs=build_arm_attributes()))
    else:
        exe.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(cpu_arch=10)))

    res = glass_host.qualify_host_cached(exe, renderer, lib_dirs=(lib_dir,), proc_root=proc_dir)
    assert res['ok'] is False
    assert str(res['reason']).startswith(expected_prefix)
    if failure_case == 'only_so2':
        assert not (lib_dir / 'libGLESv2.so').exists()  # Must NEVER create symlinks!

    # Fix the host in-place -> cached entry must auto-invalidate because SHA changed!
    lib_dir_fixed = populate_qualified_lib_dir(tmp_path / 'libs_fixed')
    proc_fixed = populate_qualified_proc(tmp_path / 'proc_fixed')
    exe.write_bytes(build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(cpu_arch=10), salt=b'upgraded'))
    res_ok = glass_host.qualify_host_cached(exe, renderer, lib_dirs=(lib_dir_fixed,), proc_root=proc_fixed)
    assert res_ok['ok'] is True and res_ok['ubo_supported'] is True

    # Mutating libc.so.6 to drop GLIBC_2.34 invalidates cache immediately
    (lib_dir_fixed / 'libc.so.6').write_bytes(build_synthetic_elf32(
        arm_attrs=build_arm_attributes(),
        verdefs=('GLIBC_2.4', 'GLIBC_2.17'),
    ))
    res_invalidated = glass_host.qualify_host_cached(exe, renderer, lib_dirs=(lib_dir_fixed,), proc_root=proc_fixed)
    assert res_invalidated['ok'] is False
    assert res_invalidated['reason'] == 'MISSING_VERSION:libc.so.6:GLIBC_2.34'


def test_verified_60_coexistence_and_85_quarantine_with_real_box_evidence_and_crash_recovery(tmp_path, monkeypatch):
    """R3-GLASS-MIGRATE-C01..C04: Real box 60 + 85 migration, crash recovery, foreign zero-touch, and boot preload."""
    storage = tmp_path / 'storage'
    addons, _state, _journal = stage_post_2185_install(storage, sequence=2026102186)
    lib_dir = populate_qualified_lib_dir(tmp_path / 'usr_lib')
    proc_dir = populate_qualified_proc(tmp_path / 'proc')

    drop_dir = storage / '.config/system.d/kodi.service.d'
    drop_dir.mkdir(parents=True, exist_ok=True)
    native_dir = storage / '.local/share/bobbi-native/2026102154-life'
    native_dir.mkdir(parents=True, exist_ok=True)
    legacy_glass_dir = storage / '.local/share/bobbi-glass/2026102168'
    legacy_glass_dir.mkdir(parents=True, exist_ok=True)

    native_kodi_bytes = build_synthetic_elf32(e_type=2, arm_attrs=build_arm_attributes(), salt=b'native-b0b6')
    native_kodi_sha = hashlib.sha256(native_kodi_bytes).hexdigest()
    monkeypatch.setattr(boot, 'KODI', native_kodi_sha)
    (native_dir / 'kodi.bin').write_bytes(native_kodi_bytes)

    box_60 = RAW_BOX_DIR / '60-am6b-subtitle284.conf'
    box_launch = RAW_BOX_DIR / 'native__storage__.local__share__bobbi-native__2026102154-life__launch.py'
    box_receipt = RAW_BOX_DIR / 'native__storage__.local__share__bobbi-native__2026102154-life__receipt.json'
    box_85 = RAW_BOX_DIR / '85-bobbi-r19-glass.conf'
    box_svc = RAW_BOX_DIR / 'glass__storage__.local__share__bobbi-glass__2026102168__ce_service.py'
    if all(p.is_file() for p in (box_60, box_launch, box_receipt, box_85, box_svc)):
        conf_60_bytes = box_60.read_bytes()
        launch_bytes = box_launch.read_bytes()
        receipt_obj = json.loads(box_receipt.read_text(encoding='utf-8'))
        conf_85_bytes = box_85.read_bytes()
        svc_2168_bytes = box_svc.read_bytes()
    else:
        conf_60_bytes = (
            b'[Service]\n'
            b'BindReadOnlyPaths=/storage/.local/share/bobbi-native/2026102154-life/kodi.bin:/usr/lib/kodi/kodi.bin\n'
            b'ExecStart=\n'
            b'ExecStart=/usr/bin/python3 /storage/.local/share/bobbi-native/2026102154-life/launch.py --standalone -fs $KODI_ARGS $KODI_DEBUG\n'
        )
        launch_bytes = b"import os, sys\nos.execv('/usr/lib/kodi/kodi.sh', ['/usr/lib/kodi/kodi.sh', *sys.argv[1:]])\n"
        monkeypatch.setattr(boot, 'KNOWN_NATIVE_LAUNCH_SHAS', boot.KNOWN_NATIVE_LAUNCH_SHAS | {hashlib.sha256(launch_bytes).hexdigest()})
        receipt_obj = {'state': 'applied', 'new_conf_sha256': hashlib.sha256(conf_60_bytes).hexdigest()}
        conf_85_bytes = glass_host.legacy_85_unit_bytes(2026102168, '/storage')
        svc_2168_bytes = b'# ce_service 2168\n'
        monkeypatch.setattr(glass_host, 'KNOWN_CE_SERVICE_SHAS', glass_host.KNOWN_CE_SERVICE_SHAS | {hashlib.sha256(svc_2168_bytes).hexdigest()})

    receipt_obj['new_sha256'] = native_kodi_sha
    (drop_dir / '60-am6b-subtitle284.conf').write_bytes(conf_60_bytes)
    (native_dir / 'launch.py').write_bytes(launch_bytes)
    (native_dir / 'receipt.json').write_text(json.dumps(receipt_obj), encoding='utf-8')
    (drop_dir / '85-bobbi-r19-glass.conf').write_bytes(conf_85_bytes)
    (legacy_glass_dir / 'ce_service.py').write_bytes(svc_2168_bytes)

    exe_path = native_dir / 'kodi.bin'
    daemon_reloads = []
    monkeypatch.setattr(gs, 'coreelec', lambda: True)
    monkeypatch.setattr(gs.HostOptics, 'storage', storage)
    monkeypatch.setattr(gs.HostOptics, 'exe', exe_path)
    monkeypatch.setattr(gs.HostOptics, 'running', exe_path)
    monkeypatch.setattr(gs.HostOptics, 'lib_dirs', (lib_dir,))
    monkeypatch.setattr(gs.HostOptics, 'proc_root', proc_dir)
    monkeypatch.setattr(gs.HostOptics, 'systemctl_runner', staticmethod(lambda argv: (daemon_reloads.append(argv) or True)))

    host = gs.HostOptics(True)
    assert host.available() is True

    # Inject ENOSPC interruption right after quarantine_85, then recover idempotently!
    def fail_once(stage_name, _rec):
        if stage_name == 'after_quarantine_85':
            raise OSError(errno.ENOSPC, 'Simulated disk full after quarantine_85')

    with pytest.raises(OSError, match='Simulated disk full'):
        host.enable(fault_hook=fail_once)

    mid_receipt = json.loads((storage / glass_host.RECEIPT_REL).read_text(encoding='utf-8'))
    assert mid_receipt['stage'] == 'quarantine_85'
    assert not (drop_dir / '85-bobbi-r19-glass.conf').exists()
    assert (storage / glass_host.QUARANTINE_REL).read_bytes() == conf_85_bytes

    final_receipt = host.enable()
    assert final_receipt['stage'] == 'confirmed'
    assert final_receipt['daemon_reloaded'] is True
    assert daemon_reloads == [['systemctl', 'daemon-reload']]
    assert (drop_dir / '86-bobbi-opt-in-glass.conf').read_bytes() == gs.UNIT
    assert (drop_dir / '60-am6b-subtitle284.conf').read_bytes() == conf_60_bytes
    assert (native_dir / 'launch.py').read_bytes() == launch_bytes
    assert (native_dir / 'kodi.bin').read_bytes() == native_kodi_bytes

    # Boot time ExecStartPre (--opt-in and --stock-opt-in alias) loads renderer into runtime tmpfs!
    runtime_dir = tmp_path / 'run_bobbi_glass'
    runtime_dir.mkdir()
    monkeypatch.delenv('LD_PRELOAD', raising=False)
    boot.main(opt_in=True, storage=storage, exe=exe_path, runtime=runtime_dir, lib_dirs=(lib_dir,), proc_root=proc_dir)
    loader_env = (runtime_dir / 'loader.env').read_text(encoding='ascii')
    assert loader_env == f'LD_PRELOAD={runtime_dir / "libbobbi_liquid_glass.so"}\n'
    assert boot.sha(runtime_dir / 'libbobbi_liquid_glass.so') == boot.REFINED_RENDERER

    # Disable removes owned 86 and NEVER reactivates quarantined 85 or touches 60
    host.disable()
    assert not (drop_dir / '86-bobbi-opt-in-glass.conf').exists()
    assert not (drop_dir / '85-bobbi-r19-glass.conf').exists()
    assert (storage / glass_host.QUARANTINE_REL).read_bytes() == conf_85_bytes
    assert (drop_dir / '60-am6b-subtitle284.conf').read_bytes() == conf_60_bytes

    # Foreign/modified 60 or 85 or 90-custom.conf must be FOREIGN_CONFLICT with zero file changes!
    (drop_dir / '85-bobbi-r19-glass.conf').write_bytes(conf_85_bytes + b'# user edit\n')
    assert host.available() is False
    with pytest.raises(ValueError):
        host.enable()
    assert (drop_dir / '85-bobbi-r19-glass.conf').read_bytes() == conf_85_bytes + b'# user edit\n'


def test_show_window_guard_and_all_seven_runtime_status_states(tmp_path, monkeypatch):
    """GM12 + 7-state runtime status inspection (off, static_material, pending_restart, loaded_unverified, live_active, fallback_unavailable, status_unconfirmed)."""
    # 1. Window guard allows both skinsettings and settings, blocks other windows
    conds_queried = []
    applied = []
    monkeypatch.setattr(gs, 'ProfileBinding', lambda: SimpleNamespace(is_current=lambda: True))
    monkeypatch.setattr('bobbi_platform.paths.profile_root', lambda: Path('/non-master-test'))
    monkeypatch.setattr(gs, 'coreelec', lambda: False)

    for active_win, should_run in [('skinsettings', True), ('settings', True), ('home', False)]:
        applied.clear()
        monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
            getSkinDir=lambda: 'skin.bobbi.cinema',
            getCondVisibility=lambda expr: (
                conds_queried.append(expr) or (
                    active_win in expr if 'Window.IsActive' in expr else False
                )
            ),
            executebuiltin=lambda cmd, wait=False: applied.append(cmd),
        ))
        gs.show(SimpleNamespace(yesno=lambda *a: True))
        assert bool(applied) is should_run

    # 2. Verify all 7 runtime states + stale/prior-PID stats rejection + ZH/EN labels
    storage = tmp_path / 'st'
    proc_root = tmp_path / 'proc'
    runtime_dir = tmp_path / 'run'
    runtime_dir.mkdir(parents=True)
    lib_copy = runtime_dir / 'libbobbi_liquid_glass.so'
    lib_copy.write_bytes((ROOT / 'addons' / boot.PACKAGED_FILE).read_bytes())

    pid = 4242
    pid_dir = proc_root / str(pid)
    pid_dir.mkdir(parents=True)
    (proc_root / 'stat').write_text('btime 1700000000\n', encoding='ascii')
    # Process started at btime + 10000 ticks / 100 Hz = 1700000100.0 (field 22 = after[19])
    (pid_dir / 'stat').write_text(f'{pid} (kodi.bin) S ' + ' '.join(['0'] * 18 + ['10000', '0']), encoding='ascii')

    # State 1: off
    s1 = glass_host.inspect_runtime_status(
        opted_in=False, is_coreelec=True, host_available=True, owned_86_present=False,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s1['state'], s1['label'], s1['label_en']) == ('off', '已关闭', 'Off')

    # State 7a: status_unconfirmed when /proc maps is unreadable
    s7a = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=False,
    )
    assert (s7a['state'], s7a['label']) == ('status_unconfirmed', 'Status not confirmed')

    # Unmapped /proc/<pid>/maps
    (pid_dir / 'maps').write_text('00400000-00410000 r-xp 00000000 00:01 1 /usr/lib/kodi/kodi.bin\n', encoding='utf-8')

    # State 2: static_material
    s2 = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=False,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s2['state'], s2['label']) == ('static_material', '静态玻璃材质')

    # State 3: pending_restart
    s3 = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s3['state'], s3['label']) == ('pending_restart', '已配置，重启后验证')

    # State 6: fallback_unavailable (host unqualified/conflict)
    s6 = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=False, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s6['state'], s6['label']) == ('fallback_unavailable', '实时玻璃暂不可用，已使用静态材质')

    # Mapped renderer in /proc/<pid>/maps
    (pid_dir / 'maps').write_text(f'b6f00000-b6f10000 r-xp 00000000 00:01 2 {lib_copy}\n', encoding='utf-8')

    # State 4: loaded_unverified (missing stats.json, or stats.json from prior PID / before proc start)
    s4_missing = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s4_missing['state'], s4_missing['label']) == ('loaded_unverified', '已加载，等待绘制验证')

    stats_file = runtime_dir / 'stats.json'
    stats_file.write_text(json.dumps({
        'enabled': 1, 'tags_registered': 24, 'blur_runs': 12, 'glass_quads_last_frame': 5,
    }), encoding='utf-8')
    os.utime(stats_file, (1700000090.0, 1700000090.0))  # Older than process start 1700000100.0!
    s4_prior = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert s4_prior['state'] == 'loaded_unverified' and s4_prior['detail'] == 'STATS_OLDER_THAN_PROC_START'

    # State 7b: status_unconfirmed when stats.json is expired (> max_stats_age_sec)
    os.utime(stats_file, (1700000102.0, 1700000102.0))
    s7b = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000130.0, cjk=True,
    )
    assert s7b['state'] == 'status_unconfirmed' and s7b['detail'] == 'STATS_EXPIRED'

    # blur_runs > 0 with quads == 0 MUST stay loaded_unverified (AWAITING_GLASS_DRAW), NOT live_active!
    stats_file.write_text(json.dumps({
        'enabled': 1, 'tags_registered': 24, 'blur_runs': 5, 'glass_quads_last_frame': 0,
    }), encoding='utf-8')
    os.utime(stats_file, (1700000103.0, 1700000103.0))
    s4_no_quads = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s4_no_quads['state'], s4_no_quads['detail']) == ('loaded_unverified', 'AWAITING_GLASS_DRAW')

    # State 5: live_active requires enabled == 1, tags > 0, AND quads > 0
    stats_file.write_text(json.dumps({
        'enabled': 1, 'tags_registered': 24, 'blur_runs': 5, 'glass_quads_last_frame': 2,
    }), encoding='utf-8')
    os.utime(stats_file, (1700000104.0, 1700000104.0))
    s5 = glass_host.inspect_runtime_status(
        opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
        storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0, cjk=True,
    )
    assert (s5['state'], s5['label'], s5['label_en']) == ('live_active', '实时玻璃已生效', 'Live glass active')

    # 3. Verify sync_runtime_property(), runtime_summary_line(), and skin XML consumers (N3-GL-STATE-01)
    home_props = {}
    active_lang = {'val': 'resource.language.zh_cn'}
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        getInfoLabel=lambda k: active_lang['val'] if k == 'System.Language' else '',
        getSkinDir=lambda: 'skin.bobbi.cinema',
        getCondVisibility=lambda expr: False,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Window=lambda wid: SimpleNamespace(
            setProperty=lambda k, v: home_props.__setitem__((wid, k), v),
            getProperty=lambda k: home_props.get((wid, k), ''),
        ),
    ))

    stub_host = SimpleNamespace(
        runtime_status=lambda **kw: glass_host.inspect_runtime_status(
            opted_in=True, is_coreelec=True, host_available=True, owned_86_present=True,
            storage=storage, runtime_dir=runtime_dir, proc_root=proc_root, pid=pid, now=1700000105.0,
            cjk=kw.get('cjk'),
        ),
    )
    st_zh = gs.sync_runtime_property(stub_host)
    assert st_zh['state'] == 'live_active'
    assert home_props[(10000, 'Bobbi.Glass.State')] == 'live_active'
    assert home_props[(10000, 'Bobbi.Glass.StateLabel')] == '实时玻璃已生效'
    assert gs.runtime_summary_line(stub_host) == '液态玻璃 · 实时玻璃已生效'

    active_lang['val'] = 'resource.language.en_gb'
    st_en = gs.sync_runtime_property(stub_host)
    assert st_en['state'] == 'live_active'
    assert home_props[(10000, 'Bobbi.Glass.StateLabel')] == 'Live glass active'
    assert gs.runtime_summary_line(stub_host) == 'Liquid Glass · Live glass active'

    vars_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/Variables.xml').getroot()
    short_var = vars_xml.find("./variable[@name='BobbiGlassShortState']")
    assert short_var is not None
    values = [(v.get('condition'), v.text) for v in short_var.findall('value')]
    assert values[0] == (
        '!String.IsEmpty(Window(Home).Property(Bobbi.Glass.StateLabel))',
        '$INFO[Window(Home).Property(Bobbi.Glass.StateLabel)]',
    )
    for win_name in ('Settings.xml', 'SkinSettings.xml'):
        win_root = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p' / win_name).getroot()
        onloads = [n.text for n in win_root.findall('onload')]
        assert 'RunScript(script.bobbi.setup,liquid_glass_status)' in onloads
