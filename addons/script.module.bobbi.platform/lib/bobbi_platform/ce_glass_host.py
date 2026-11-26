"""CoreELEC Liquid Glass qualification cache, legacy 85/60 migration, and 7-state runtime status."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

from . import ce_glass_boot as boot
from .bootstrap_i18n import is_cjk_locale

KNOWN_CE_SERVICE_SHAS = frozenset({
    # All 10 box-captured historical /storage/.local/share/bobbi-glass/<seq>/ce_service.py digests (2026102156..2026102168)
    'b7ddc499416aa8de6772627126492ea246b1b7fa2eb3d60bbbeec4e06526ab92',  # 2026102156
    '21145bffef154d914f85dcf571b31eb626c66f9f7c95d186789398372d2fc6b6',  # 2026102157
    '1d6e7567e381d2592b440d015408a2231a9bc141a681fb667e40d760a89b643f',  # 2026102158
    'f53550c812d6ff69dde31a7657c04d532aa6135689b0e66b270d6541d3e7be1c',  # 2026102159
    '4448c73dce9f6434b35b71fe88c734a6370b5b7ba4b6edac462d8b56daacff3a',  # 2026102160
    'fa8be5223cd463bf26a00a387e4ed40813a2be71c1e730629975e65f79edbea3',  # 2026102161
    'f534ce23eaddc976fd9f86dbf9db700dd91b64fc992b6b9eb0d632d5979dd83f',  # 2026102162
    '5ca301d83645072a683147b684d5c1398fb77708943f472da9477737373ecd69',  # 2026102165
    '9fce0f1f7fa59c0b30e10f9b277176fa1e86d9ef6cd7f3a149cc7a5b43911763',  # 2026102166
    '52638ed1cb447fd6b0b4382a3449b5a349ea4b1f2390912048920004ee904ab5',  # 2026102168
    # Known historical shipped ce_glass_boot.py digests if referenced as ce_service.py up to 2026102179
    'b6ea905c6f5d96731f37bc474f08c423d89d7d35fa0821aaa456d71ee2f376d2',
    '08576e40aae95c1bc37fc7c5b43ce115a6bd34b42e74ff4e6bee9930a074ee38',
    '51cc4c15f7e7d4a99f63181e26ec3f5c79e31d63186d71a0ee8dabff10c4dbd7',
    '810db4ef0e4ad787cc450e651d068c0926141050bc9fdb2055cfa99f0caedff6',
    '58eb1babf11a506fde4fb7e6bfc7acfaa6c43b3e8bc607deefb0197cdb3af0b3',
})

LEGACY_85_NAME = '85-bobbi-r19-glass.conf'
NATIVE_60_NAME = '60-am6b-subtitle284.conf'
OWNED_86_NAME = '86-bobbi-opt-in-glass.conf'
LEGACY_85_SEQUENCES = tuple(range(2026102156, 2026102180))

MIGRATION_DIR_REL = Path('.local/share/bobbi-glass-optin')
QUARANTINE_REL = MIGRATION_DIR_REL / 'quarantine' / LEGACY_85_NAME
RECEIPT_REL = MIGRATION_DIR_REL / 'migration-receipt.json'
MIGRATION_STAGES = ('prepare', 'quarantine_85', 'publish_86', 'confirmed')

RUNTIME_STATES = (
    'off',
    'static_material',
    'pending_restart',
    'loaded_unverified',
    'live_active',
    'fallback_unavailable',
    'status_unconfirmed',
)

RUNTIME_LABELS = {
    'off': ('已关闭', 'Off'),
    'static_material': ('静态玻璃材质', 'Static glass material'),
    'pending_restart': ('已配置，重启后验证', 'Configured — verify after restart'),
    'loaded_unverified': ('已加载，等待绘制验证', 'Loaded — awaiting rendering verification'),
    'live_active': ('实时玻璃已生效', 'Live glass active'),
    'fallback_unavailable': ('实时玻璃暂不可用，已使用静态材质', 'Live glass unavailable — using static material'),
    'status_unconfirmed': ('状态待确认', 'Status not confirmed'),
}

TOGGLE_PROMPTS_ZH = {
    'stock': '这台 CoreELEC 支持实时折射。将为 Kodi 添加可撤销的启动项，不更换内核、不自动重启。重启盒子后生效；关闭此开关会移除该启动项。',
    'live': '本机已加载实时渲染器。现在启用液态玻璃？不会修改系统启动项。',
    'material': '当前环境没有可启用的实时渲染器。仅开启皮肤自带的玻璃材质，不修改系统启动项。',
}

TOGGLE_PROMPTS_EN = {
    'stock': 'This CoreELEC host supports live refraction. A revocable Kodi startup drop-in will be configured without replacing the kernel or restarting automatically. Restart to activate; turning this off removes the drop-in.',
    'live': 'Live renderer is already loaded in this process. Enable Liquid Glass now without modifying startup drop-ins?',
    'material': 'No live renderer is available for this host. Enable static skin glass materials only without modifying startup drop-ins?',
}


def toggle_dialog_copy(mode: str, *, cjk: bool | None = None) -> tuple[str, str]:
    zh = is_cjk_locale() if cjk is None else bool(cjk)
    return ('开启液态玻璃？', TOGGLE_PROMPTS_ZH[mode]) if zh else ('Enable Liquid Glass?', TOGGLE_PROMPTS_EN[mode])

_QUAL_CACHE: dict[tuple[str, ...], dict[str, object]] = {}


def clear_qualification_cache() -> None:
    _QUAL_CACHE.clear()


def _ordinary(path: Path) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('GLASS_PATH_CHANGED')
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('GLASS_FILE_CHANGED')


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    _ordinary(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _ordinary(path)
    raw = (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_receipt(path: Path) -> dict[str, object] | None:
    _ordinary(path)
    if not path.exists():
        return None
    info = path.stat()
    if info.st_size <= 0 or info.st_size > 65536:
        raise ValueError('GLASS_RECEIPT_INVALID')
    data = json.loads(path.read_bytes().decode('utf-8'))
    if not isinstance(data, dict) or data.get('stage') not in MIGRATION_STAGES:
        raise ValueError('GLASS_RECEIPT_INVALID')
    return data


def legacy_85_unit_bytes(seq: int, prefix: str = '/storage') -> bytes:
    base = prefix.rstrip('/')
    return (
        '[Service]\n'
        'RuntimeDirectory=bobbi-glass\n'
        'RuntimeDirectoryMode=0700\n'
        f'ExecStartPre=/usr/bin/python3 -IB {base}/.local/share/bobbi-glass/{seq}/ce_service.py\n'
        'EnvironmentFile=-/run/bobbi-glass/loader.env\n'
    ).encode('ascii')


def verify_legacy_85_dropin(conf_path: Path, storage: Path = Path('/storage')) -> dict[str, object] | None:
    """Verify exact historical 85-bobbi-r19-glass.conf bytes AND known ce_service.py digest."""
    conf_path = Path(conf_path)
    storage = Path(storage)
    if boot._ordinary_file(conf_path, limit=4096) is None:
        return None
    info = conf_path.stat()
    raw = conf_path.read_bytes()
    storage_posix = storage.as_posix().rstrip('/')
    matched_seq = None
    for seq in LEGACY_85_SEQUENCES:
        if raw == legacy_85_unit_bytes(seq, '/storage') or raw == legacy_85_unit_bytes(seq, storage_posix):
            matched_seq = seq
            break
    if matched_seq is None:
        return None
    service_path = storage / '.local/share/bobbi-glass' / str(matched_seq) / 'ce_service.py'
    if boot._ordinary_file(service_path, limit=256 * 1024) is None:
        return None
    service_sha = boot.sha(service_path)
    if service_sha not in KNOWN_CE_SERVICE_SHAS:
        return None
    return {
        'sequence': matched_seq,
        'conf_sha256': hashlib.sha256(raw).hexdigest(),
        'size': info.st_size,
        'mode': stat.S_IMODE(info.st_mode),
        'mtime_ns': info.st_mtime_ns,
        'service_path': str(service_path),
        'service_sha256': service_sha,
    }


def qualify_host_cached(executable: Path, renderer: Path, *,
                        addons: Path | None = None, lib_dirs=None,
                        proc_root: Path = Path('/proc')) -> dict[str, object]:
    """Run ELF/ABI/SONAME/GLIBC/GLES qualification with digest-keyed cache invalidation."""
    exe_path = Path(executable)
    ren_path = Path(renderer)
    proc_path = Path(proc_root)
    search_dirs = tuple(Path(d) for d in (lib_dirs if lib_dirs is not None else boot.DEFAULT_LIB_DIRS))

    def _safe_sha(p: Path) -> str:
        try:
            st = p.stat()
            if stat.S_ISREG(st.st_mode) and st.st_size > 0:
                return boot.sha(p)
        except OSError:
            pass
        return 'MISSING'

    def _lib_sha(soname: str) -> str:
        for folder in search_dirs:
            cand = folder / soname
            digest = _safe_sha(cand)
            if digest != 'MISSING':
                return f'{cand}:{digest}'
        return f'MISSING:{soname}'

    assets_sha = 'NO_ADDONS'
    if addons is not None:
        assets_path = Path(addons) / boot.GLASS_ASSETS_FILE
        assets_sha = _safe_sha(assets_path)

    raw_cpuinfo = boot._read_proc_bytes(proc_path / 'cpuinfo')
    cpuinfo_sha = hashlib.sha256(raw_cpuinfo).hexdigest() if raw_cpuinfo else 'MISSING_CPUINFO'

    cache_key = (
        _safe_sha(exe_path),
        _safe_sha(ren_path),
        _lib_sha('libGLESv2.so'),
        _lib_sha('libEGL.so'),
        _lib_sha('libc.so.6'),
        _lib_sha('libm.so.6'),
        _lib_sha('ld-linux-armhf.so.3'),
        assets_sha,
        cpuinfo_sha,
    )
    cached = _QUAL_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    result = boot.qualify_host(exe_path, ren_path, lib_dirs=search_dirs, proc_root=proc_path)
    result['cache_key'] = cache_key
    if 'MISSING' not in cache_key[:2]:
        _QUAL_CACHE[cache_key] = dict(result)
    return result


def inspect_dropins(storage: Path, current_unit: bytes, old_units: dict[str, bytes]) -> dict[str, object]:
    """Classify systemd drop-ins under <storage>/.config/system.d/kodi.service.d."""
    storage = Path(storage)
    drop_dir = storage / '.config/system.d/kodi.service.d'
    drop_86 = drop_dir / OWNED_86_NAME
    _ordinary(drop_86)
    if not drop_dir.exists():
        return {
            'status': 'CLEAN',
            'available': True,
            'owned_86': None,
            'legacy_85': None,
            'native_60': None,
            'conflicts': [],
        }
    if drop_dir.is_symlink() or any(p.is_symlink() for p in drop_dir.parents):
        raise ValueError('GLASS_PATH_CHANGED')

    owned_86 = None
    legacy_85 = None
    native_60 = None
    conflicts: list[str] = []

    for conf in sorted(drop_dir.glob('*.conf')):
        _ordinary(conf)
        if conf.stat().st_size > 32768:
            conflicts.append(f'{conf.name}:OVERSIZE')
            continue
        raw = conf.read_bytes()
        if conf.name == OWNED_86_NAME:
            if raw == current_unit:
                owned_86 = 'current'
            elif any(raw == old_bytes for old_bytes in old_units.values()):
                owned_86 = 'previous'
            else:
                conflicts.append(f'{OWNED_86_NAME}:FOREIGN_86')
        elif conf.name == LEGACY_85_NAME:
            verified_85 = verify_legacy_85_dropin(conf, storage)
            if verified_85 is None:
                conflicts.append(f'{LEGACY_85_NAME}:UNVERIFIED_85')
            else:
                legacy_85 = verified_85
        elif conf.name == NATIVE_60_NAME:
            verified_60 = boot.verify_native_60_dropin(conf, storage)
            if verified_60 is None:
                conflicts.append(f'{NATIVE_60_NAME}:UNVERIFIED_60')
            else:
                native_60 = verified_60
        else:
            if any(tok in raw for tok in (b'LD_PRELOAD', b'bobbi-glass', b'EnvironmentFile', b'ExecStart', b'ExecStartPre')):
                conflicts.append(f'{conf.name}:FOREIGN_DROPIN')

    if conflicts:
        status = 'FOREIGN_CONFLICT'
    elif legacy_85 is not None:
        status = 'MIGRATABLE_85'
    elif owned_86 is not None:
        status = 'OWNED_86'
    elif native_60 is not None:
        status = 'VERIFIED_60'
    else:
        status = 'CLEAN'

    return {
        'status': status,
        'available': not conflicts,
        'owned_86': owned_86,
        'legacy_85': legacy_85,
        'native_60': native_60,
        'conflicts': conflicts,
    }


def _bounded_daemon_reload(runner=None) -> bool:
    if runner is not None:
        return bool(runner(['systemctl', 'daemon-reload']))
    systemctl = shutil.which('systemctl')
    if not systemctl:
        return False
    try:
        proc = subprocess.run(
            [systemctl, 'daemon-reload'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def execute_migration(
    *,
    storage: Path,
    snapshot_path: Path,
    guard_bytes: bytes,
    guard_hash: str,
    drop_86_path: Path,
    unit_bytes: bytes,
    old_units: dict[str, bytes],
    place_fn,
    systemctl_runner=None,
    fault_hook=None,
) -> dict[str, object]:
    """Run or resume the 4-stage crash-safe migration (prepare -> quarantine_85 -> publish_86 -> confirmed)."""
    storage = Path(storage)
    drop_dir = drop_86_path.parent
    drop_85_path = drop_dir / LEGACY_85_NAME
    quarantine_path = storage / QUARANTINE_REL
    receipt_path = storage / RECEIPT_REL

    existing_receipt = _read_receipt(receipt_path)
    inspection = inspect_dropins(storage, unit_bytes, old_units)
    if not inspection['available']:
        raise ValueError('GLASS_FOREIGN_CONFLICT:' + ','.join(inspection['conflicts']))

    legacy_85 = inspection['legacy_85']
    if legacy_85 is None and existing_receipt and existing_receipt.get('legacy_85'):
        recorded_85 = existing_receipt['legacy_85']
        if isinstance(recorded_85, dict):
            if drop_85_path.exists():
                raise ValueError('GLASS_85_CHANGED_DURING_RECOVERY')
            if quarantine_path.exists():
                _ordinary(quarantine_path)
                if boot.sha(quarantine_path) != recorded_85.get('conf_sha256'):
                    raise ValueError('GLASS_QUARANTINE_TAMPERED')
                legacy_85 = recorded_85

    if hashlib.sha256(guard_bytes).hexdigest() != guard_hash:
        raise ValueError('GLASS_GUARD_CHANGED')

    # Stage 1: prepare
    place_fn(snapshot_path, guard_bytes)
    receipt: dict[str, object] = {
        'schema': 1,
        'stage': 'prepare',
        'guard_hash': guard_hash,
        'unit_sha256': hashlib.sha256(unit_bytes).hexdigest(),
        'legacy_85': legacy_85,
        'native_60': inspection['native_60'],
        'daemon_reloaded': False,
    }
    _atomic_write_json(receipt_path, receipt)
    if fault_hook is not None:
        fault_hook('after_prepare', receipt)

    # Stage 2: quarantine_85 (only when verified 85 is active or already quarantined for this receipt)
    if legacy_85 is not None:
        expected_85_sha = str(legacy_85['conf_sha256'])
        service_path = Path(str(legacy_85['service_path']))
        expected_svc_sha = str(legacy_85['service_sha256'])
        if boot._ordinary_file(service_path, limit=256 * 1024) is None or boot.sha(service_path) != expected_svc_sha:
            raise ValueError('GLASS_85_SERVICE_CHANGED')

        if drop_85_path.exists():
            _ordinary(drop_85_path)
            raw_85 = drop_85_path.read_bytes()
            if hashlib.sha256(raw_85).hexdigest() != expected_85_sha:
                raise ValueError('GLASS_85_CHANGED')
            if quarantine_path.exists():
                _ordinary(quarantine_path)
                if boot.sha(quarantine_path) != expected_85_sha:
                    raise ValueError('GLASS_QUARANTINE_CONFLICT')
            else:
                place_fn(quarantine_path, raw_85)
            if boot.sha(quarantine_path) != expected_85_sha:
                raise ValueError('GLASS_QUARANTINE_VERIFY_FAILED')
            if boot.sha(drop_85_path) != expected_85_sha:
                raise ValueError('GLASS_85_CHANGED')
            drop_85_path.unlink()
        elif not quarantine_path.exists() or boot.sha(quarantine_path) != expected_85_sha:
            raise ValueError('GLASS_QUARANTINE_MISSING')

    receipt['stage'] = 'quarantine_85'
    _atomic_write_json(receipt_path, receipt)
    if fault_hook is not None:
        fault_hook('after_quarantine_85', receipt)

    # Stage 3: publish_86
    _ordinary(drop_86_path)
    if drop_86_path.exists():
        current_86 = drop_86_path.read_bytes()
        if current_86 != unit_bytes:
            if any(current_86 == old_u for old_u in old_units.values()):
                drop_86_path.unlink()
            else:
                raise ValueError('GLASS_FILE_CHANGED')
    place_fn(drop_86_path, unit_bytes)
    receipt['stage'] = 'publish_86'
    _atomic_write_json(receipt_path, receipt)
    if fault_hook is not None:
        fault_hook('after_publish_86', receipt)

    # Stage 4: confirmed (+ bounded daemon-reload; never restarts Kodi or stops playback)
    reloaded = _bounded_daemon_reload(systemctl_runner)
    receipt['stage'] = 'confirmed'
    receipt['daemon_reloaded'] = reloaded
    _atomic_write_json(receipt_path, receipt)
    if fault_hook is not None:
        fault_hook('after_confirmed', receipt)
    return receipt


def _proc_start_ticks(proc_stat_path: Path) -> int | None:
    try:
        raw = proc_stat_path.read_text(encoding='ascii', errors='replace').strip()
    except OSError:
        return None
    rparen = raw.rfind(')')
    if rparen < 0:
        return None
    after = raw[rparen + 2:].split()
    # Field 22 (1-indexed) in /proc/<pid>/stat is index 19 after "(comm) "
    if len(after) <= 19:
        return None
    try:
        return int(after[19])
    except ValueError:
        return None


def _proc_start_epoch(proc_root: Path, pid: int, start_ticks: int) -> float | None:
    try:
        clk_tck = int(os.sysconf('SC_CLK_TCK'))
    except (AttributeError, ValueError, OSError):
        clk_tck = 100
    if clk_tck <= 0:
        clk_tck = 100
    try:
        for line in (proc_root / 'stat').read_text(encoding='ascii', errors='replace').splitlines():
            if line.startswith('btime '):
                btime = int(line.split()[1])
                return float(btime) + (float(start_ticks) / float(clk_tck))
    except (OSError, ValueError, IndexError):
        pass
    try:
        return (proc_root / str(pid)).stat().st_mtime
    except OSError:
        try:
            return (proc_root / 'self').stat().st_mtime
        except OSError:
            return None


def _is_renderer_mapped(maps_path: Path, runtime_dir: Path, storage: Path) -> bool | None:
    try:
        lines = maps_path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return None
    local_share = storage / '.local/share'
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or 'x' not in fields[1]:
            continue
        mapped_path = Path(fields[-1])
        if mapped_path.name != 'libbobbi_liquid_glass.so':
            continue
        if mapped_path.parent == runtime_dir or local_share in mapped_path.parents:
            try:
                if boot.sha(mapped_path) == boot.REFINED_RENDERER:
                    return True
            except OSError:
                continue
    return False


def inspect_runtime_status(
    *,
    opted_in: bool,
    is_coreelec: bool,
    host_available: bool,
    owned_86_present: bool,
    storage: Path = Path('/storage'),
    runtime_dir: Path = boot.RUNTIME,
    proc_root: Path = Path('/proc'),
    pid: int | None = None,
    now: float | None = None,
    max_stats_age_sec: float = 15.0,
    cjk: bool | None = None,
) -> dict[str, object]:
    """Evaluate the 7-state Liquid Glass runtime status without inventing persisted state."""
    use_cjk = is_cjk_locale() if cjk is None else bool(cjk)

    def _pack(state: str, detail: str, extra: dict[str, object] | None = None) -> dict[str, object]:
        zh_label, en_label = RUNTIME_LABELS[state]
        out: dict[str, object] = {
            'state': state,
            'label': zh_label if use_cjk else en_label,
            'label_zh': zh_label,
            'label_en': en_label,
            'detail': detail,
        }
        if extra:
            out.update(extra)
        return out

    if not opted_in:
        return _pack('off', 'USER_PREFERENCE_OFF')

    if not is_coreelec:
        return _pack('static_material', 'NON_COREELEC_STATIC_ONLY')

    cur_pid = os.getpid() if pid is None else int(pid)
    cur_now = time.time() if now is None else float(now)

    pid_dir = proc_root / str(cur_pid)
    if not pid_dir.exists():
        pid_dir = proc_root / 'self'
    stat_path = pid_dir / 'stat'
    maps_path = pid_dir / 'maps'

    start_ticks = _proc_start_ticks(stat_path)
    mapped = _is_renderer_mapped(maps_path, Path(runtime_dir), Path(storage))
    if start_ticks is None or mapped is None:
        return _pack('status_unconfirmed', 'PROC_UNREADABLE', {'pid': cur_pid})

    if not mapped:
        if owned_86_present and host_available:
            return _pack('pending_restart', 'OWNED_86_ARMED_AWAITING_RESTART', {'pid': cur_pid, 'starttime_ticks': start_ticks})
        if not host_available:
            return _pack('fallback_unavailable', 'HOST_UNQUALIFIED_OR_CONFLICT', {'pid': cur_pid, 'starttime_ticks': start_ticks})
        return _pack('static_material', 'STATIC_MATERIAL_ONLY', {'pid': cur_pid, 'starttime_ticks': start_ticks})

    stats_path = Path(runtime_dir) / 'stats.json'
    if not stats_path.exists():
        return _pack('loaded_unverified', 'STATS_MISSING', {'pid': cur_pid, 'starttime_ticks': start_ticks})
    if stats_path.is_symlink():
        return _pack('status_unconfirmed', 'STATS_SYMLINK', {'pid': cur_pid, 'starttime_ticks': start_ticks})

    try:
        st_info = stats_path.stat()
        if not stat.S_ISREG(st_info.st_mode) or st_info.st_size <= 0 or st_info.st_size > 262144:
            return _pack('status_unconfirmed', 'STATS_INVALID_FILE', {'pid': cur_pid})
        stats_data = json.loads(stats_path.read_bytes().decode('utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _pack('status_unconfirmed', 'STATS_CORRUPT', {'pid': cur_pid, 'starttime_ticks': start_ticks})

    if not isinstance(stats_data, dict):
        return _pack('status_unconfirmed', 'STATS_NOT_OBJECT', {'pid': cur_pid})

    if stats_data.get('pid') not in (None, cur_pid):
        return _pack('loaded_unverified', 'STATS_PRIOR_PID', {'pid': cur_pid, 'stats_pid': stats_data.get('pid')})
    if stats_data.get('starttime_ticks') not in (None, start_ticks):
        return _pack('loaded_unverified', 'STATS_PRIOR_STARTTIME', {'pid': cur_pid})

    start_epoch = _proc_start_epoch(proc_root, cur_pid, start_ticks)
    if start_epoch is not None and st_info.st_mtime + 0.001 < start_epoch:
        return _pack('loaded_unverified', 'STATS_OLDER_THAN_PROC_START', {'pid': cur_pid, 'starttime_ticks': start_ticks})

    age = cur_now - st_info.st_mtime
    if age > max_stats_age_sec:
        return _pack('status_unconfirmed', 'STATS_EXPIRED', {'pid': cur_pid, 'age_sec': round(age, 3)})

    if stats_data.get('enabled') == 0:
        return _pack('fallback_unavailable', 'RENDERER_RUNTIME_DISABLED', {'pid': cur_pid})

    tags = stats_data.get('tags_registered', 0)
    blur_runs = stats_data.get('blur_runs', 0)
    quads = stats_data.get('glass_quads_last_frame', 0)
    if (stats_data.get('enabled') == 1
            and isinstance(tags, int) and not isinstance(tags, bool) and tags > 0
            and isinstance(quads, int) and not isinstance(quads, bool) and quads > 0):
        return _pack(
            'live_active',
            'LIVE_RENDERING_CONFIRMED',
            {
                'pid': cur_pid,
                'starttime_ticks': start_ticks,
                'tags_registered': tags,
                'blur_runs': blur_runs,
                'glass_quads_last_frame': quads,
            },
        )

    return _pack('loaded_unverified', 'AWAITING_GLASS_DRAW', {'pid': cur_pid, 'starttime_ticks': start_ticks})
