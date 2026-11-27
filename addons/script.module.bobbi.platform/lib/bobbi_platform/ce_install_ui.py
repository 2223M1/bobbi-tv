"""Kodi-native installation UI. No SSH, HTTP control port or developer paths."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
import errno
import os
import re
import shutil
import ssl
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from zipfile import BadZipFile

from .bootstrap_i18n import (
    ZH_CN_ADDON_ID,
    ZH_CN_FILENAME,
    ZH_CN_RELATIVE_DIR,
    active_locale,
    is_cjk_locale,
    normalize_locale,
    tr,
    verify_zh_cn_archive,
)
from .ce_installer import Installer, MANAGED, PlaybackActive, blocked, installed_watermark
from .kodi import rpc
from .offline_updates import SignedBundle
from .paths import profile
from .updates import UpdateError, _atomic, _json, _safe_path, archive_rows, auto_update_enabled
from .upstream_addons import (
    DIRECTORY_CONFLICT,
    DISABLED,
    HOST_COMPONENTS,
    MISSING_HOST,
    MISSING_SEEDABLE,
    NEEDS_UPGRADE,
    SATISFIED,
    STATE_UNKNOWN,
    UPSTREAM_COMPONENTS,
    compare_versions,
    kodi_version,
    plan_dependencies,
)

LANGUAGE_MARKER = 'language-init.json'


def check_host_crypto():
    # Kodi's native provider registers under Crypto (CE) or Cryptodome
    # (official Windows). Import success alone does not prove a working ABI.
    from importlib import import_module
    expected = bytes.fromhex('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    for name in ('Crypto.Hash.SHA256', 'Cryptodome.Hash.SHA256'):
        try:
            if import_module(name).new(b'abc').digest() == expected:
                return
        except (ImportError, OSError, RuntimeError, AttributeError, ValueError, TypeError):
            continue
    raise UpdateError('CRYPTO_DEPENDENCY_UNUSABLE')


class KodiHost:
    def __init__(self, dialog=None, *, unattended=False):
        import xbmc
        self.xbmc = xbmc
        self.monitor = xbmc.Monitor()
        self.dialog = dialog
        self.unattended = bool(unattended)

    @contextmanager
    def _skin_keep_confirmer(self):
        if not self.unattended:
            yield
            return
        stop = threading.Event()

        def _watch():
            while not stop.is_set():
                try:
                    if self.xbmc.getCondVisibility('Window.IsVisible(yesnodialog)'):
                        heading = self.xbmc.getInfoLabel('Control.GetLabel(1)') or ''
                        body = self.xbmc.getInfoLabel('Control.GetLabel(2)') or ''
                        keep_title = self.xbmc.getLocalizedString(13123) or ''
                        if (
                            (keep_title and heading == keep_title)
                            or '保持皮肤' in heading or '保持皮肤' in body
                            or 'keep this change' in body.lower()
                        ):
                            time.sleep(0.2)
                            if self.xbmc.getCondVisibility('Window.IsVisible(yesnodialog)'):
                                self.xbmc.executebuiltin('SendClick(yesnodialog,11)', False)
                except Exception:
                    pass
                stop.wait(0.15)

        worker = threading.Thread(target=_watch, name='BobbiKeepSkinAuto', daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(1.0)

    def skin(self):
        return rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.skin'})['value']

    def locale(self):
        return rpc('Settings.GetSettingValue', {'setting': 'locale.language'}).get('value')

    def details(self, name):
        try:
            value = rpc('Addons.GetAddonDetails', {'addonid': name,
                'properties': ['version', 'enabled']})['addon']
        except (RuntimeError, KeyError, TypeError, ValueError):
            # A failed detail RPC is not evidence of absence. Only a complete
            # installed-addon enumeration can prove the addon does not exist.
            try:
                listing = rpc('Addons.GetAddons', {'enabled': 'all', 'properties': ['enabled', 'version']})
            except (RuntimeError, KeyError, TypeError, ValueError) as error:
                raise UpdateError('ADDON_STATE_UNKNOWN:' + name) from error
            rows = listing.get('addons', []) if isinstance(listing, dict) else None
            if not isinstance(rows, list) or any(not isinstance(r, dict) or 'addonid' not in r for r in rows):
                raise UpdateError('ADDON_STATE_UNKNOWN:' + name)
            matches = [r for r in rows if r['addonid'] == name]
            if not matches:
                return None
            if len(matches) != 1:
                raise UpdateError('ADDON_STATE_UNKNOWN:' + name)
            value = matches[0]
        if (not isinstance(value, dict) or type(value.get('enabled')) is not bool
                or not isinstance(value.get('version'), str)):
            raise UpdateError('ADDON_STATE_UNKNOWN:' + name)
        return value

    def enabled(self):
        return [name for name in sorted(MANAGED) if (self.details(name) or {}).get('enabled')]

    def refresh(self):
        import xbmcgui
        window = xbmcgui.Window(10000)
        key = 'bobbi.install.refresh.' + uuid.uuid4().hex
        deadline = time.monotonic() + 15
        try:
            # Synchronous executebuiltin retains the Python lock on Omega.
            # Queue a FIFO fence and yield via Monitor, never wait in SendMsg.
            self.xbmc.executebuiltin('UpdateLocalAddons', False)
            self.xbmc.executebuiltin('SetProperty(%s,ready,10000)' % key, False)
            while window.getProperty(key) != 'ready':
                if self.monitor.waitForAbort(.05):
                    raise UpdateError('ADDON_REFRESH_CANCELLED')
                if time.monotonic() >= deadline:
                    raise UpdateError('ADDON_REFRESH_NOT_CONFIRMED')
        finally:
            window.clearProperty(key)

    def open_dependency_upgrade(self, addon_id):
        check = getattr(self, 'check_idle', None)
        if callable(check):
            check()
        self.xbmc.executebuiltin('ActivateWindow(AddonBrowser,addons://dependencies/,return)', False)

    def _capture_profile_guard(self):
        try:
            import xbmcvfs
            initial = str(xbmcvfs.translatePath('special://profile/'))
        except Exception:
            xbmcvfs = None
            initial = None

        def ensure_active():
            monitor = getattr(self, 'monitor', None)
            abort = getattr(monitor, 'abortRequested', None) if monitor is not None else None
            if callable(abort) and abort():
                raise UpdateError('DEPENDENCY_PREPARATION_CANCELLED')
            if initial is not None and xbmcvfs is not None:
                try:
                    current = str(xbmcvfs.translatePath('special://profile/'))
                except Exception:
                    raise UpdateError('DEPENDENCY_PREPARATION_CANCELLED') from None
                if current != initial:
                    raise UpdateError('DEPENDENCY_PREPARATION_CANCELLED')
        return ensure_active

    def dependencies(self, staged, dialog=None):
        addons_attr = getattr(self, 'addons', None)
        if addons_attr is not None:
            root = _safe_path(addons_attr)
        else:
            try:
                import xbmcvfs
                root = _safe_path(xbmcvfs.translatePath('special://home/addons'))
            except ImportError:
                root = None
        staged_path = _safe_path(staged)
        active_dialog = dialog if dialog is not None else getattr(self, 'dialog', None)
        ensure_active = self._capture_profile_guard()
        ensure_active()

        plan = plan_dependencies(root, staged_path, managed=MANAGED, details=self.details, strict_roots=True)

        # 1. Fail closed BEFORE any disk write if any required addon's RPC state is unknown.
        for name in plan['order']:
            if plan['items'][name]['state'] == STATE_UNKNOWN:
                raise UpdateError('ADDON_STATE_UNKNOWN:' + name)

        # 2. Bounded single refresh & recheck for residual unregistered directory conflicts.
        # NEVER overwrite or delete a residual user directory!
        if any(plan['items'][name]['state'] == DIRECTORY_CONFLICT for name in plan['order']):
            ensure_active()
            self.refresh()
            plan = plan_dependencies(root, staged_path, managed=MANAGED, details=self.details, strict_roots=True)
            for name in plan['order']:
                if plan['items'][name]['state'] == STATE_UNKNOWN:
                    raise UpdateError('ADDON_STATE_UNKNOWN:' + name)
                if plan['items'][name]['state'] == DIRECTORY_CONFLICT:
                    raise UpdateError('DEPENDENCY_DIRECTORY_CONFLICT:' + name)

        # 3. Handle NEEDS_UPGRADE without ever calling InstallAddon(...) on an installed addon!
        for name in list(plan['order']):
            item = plan['items'][name]
            if item['state'] != NEEDS_UPGRADE:
                continue
            have = item['installed_version'] or '0.0.0'
            need = item['minimum']
            if active_dialog is not None and hasattr(active_dialog, 'yesno'):
                ensure_active()
                if not active_dialog.yesno(
                    tr('dep_upgrade_title', host=self),
                    tr('dep_upgrade_body', host=self, addon=name, have=have, need=need),
                ):
                    raise UpdateError(f'DEPENDENCY_NEEDS_UPGRADE:{name}:{have}->{need}')
                ensure_active()
                self.open_dependency_upgrade(name)
                raise UpdateError(f'DEPENDENCY_HANDOFF_OPENED:{name}:{have}->{need}')
            else:
                raise UpdateError(f'DEPENDENCY_NEEDS_UPGRADE:{name}:{have}->{need}')

        # 4. Execute topological seeding/host-install/enabling with readback verification.
        for name in plan['order']:
            ensure_active()
            item = plan['items'][name]
            minimum = item['minimum']
            state = item['state']
            if state == STATE_UNKNOWN:
                raise UpdateError('ADDON_STATE_UNKNOWN:' + name)
            if state == DIRECTORY_CONFLICT:
                raise UpdateError('DEPENDENCY_DIRECTORY_CONFLICT:' + name)
            if state == NEEDS_UPGRADE:
                have = item['installed_version'] or '0.0.0'
                raise UpdateError(f'DEPENDENCY_NEEDS_UPGRADE:{name}:{have}->{minimum}')

            installed = self.details(name)
            if state == MISSING_SEEDABLE and not installed and name in UPSTREAM_COMPONENTS and root is not None:
                target = _safe_path(root / name)
                if target.exists() or target.is_symlink():
                    raise UpdateError('DEPENDENCY_DIRECTORY_CONFLICT:' + name)
                temporary = _safe_path(root / ('.bobbi-dependency-' + uuid.uuid4().hex))
                try:
                    shutil.copytree(staged_path / name, temporary)
                    ensure_active()
                    os.rename(temporary, target)
                except BaseException:
                    if temporary.exists():
                        shutil.rmtree(temporary, ignore_errors=True)
                    raise
                self.refresh()
                installed = self.details(name)
            elif not installed:
                # Genuinely absent host dependency (e.g. pycryptodome): ask Kodi's installer.
                self.xbmc.executebuiltin('InstallAddon(%s)' % name, False)
                deadline = time.monotonic() + 15
                while True:
                    ensure_active()
                    installed = self.details(name)
                    if installed is not None:
                        break
                    monitor = getattr(self, 'monitor', None)
                    wait_abort = getattr(monitor, 'waitForAbort', None) if monitor is not None else None
                    if callable(wait_abort) and wait_abort(.1):
                        raise UpdateError('DEPENDENCY_PREPARATION_CANCELLED')
                    if time.monotonic() >= deadline:
                        raise UpdateError('DEPENDENCY_UNAVAILABLE:' + name)
                if compare_versions(installed['version'], minimum) < 0:
                    raise UpdateError(f'DEPENDENCY_NEEDS_UPGRADE:{name}:{installed["version"]}->{minimum}')

            if installed and compare_versions(installed['version'], minimum) < 0:
                raise UpdateError(f'DEPENDENCY_NEEDS_UPGRADE:{name}:{installed["version"]}->{minimum}')

            if installed and not installed.get('enabled'):
                ensure_active()
                try:
                    rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
                except RuntimeError as error:
                    raise UpdateError('DEPENDENCY_ENABLE_FAILED:' + name) from error
                installed = self.details(name)

            if (not installed or not installed.get('enabled')
                    or compare_versions(installed['version'], minimum) < 0):
                raise UpdateError('DEPENDENCY_UNAVAILABLE:' + name)

    def check_idle(self):
        """Reject an already active player before opening an install journal."""
        if self.xbmc.Player().isPlaying():
            raise PlaybackActive('PLAYBACK_ACTIVE')

    def prepare_install_skin(self):
        """Wait for Kodi's own timed Keep Skin dialog, not merely its setting."""
        if self.skin() != 'skin.bobbi.cinema':
            return
        self.check_idle()
        target = 'skin.estuary'
        with self._skin_keep_confirmer():
            if rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': target}) is not True:
                raise UpdateError('INSTALL_SKIN_NOT_CONFIRMED')
            deadline = time.monotonic() + 28
            loaded = None
            saw_dialog = False
            while True:
                now = time.monotonic()
                self.check_idle()
                if self.skin() != target:
                    raise UpdateError('INSTALL_SKIN_NOT_CONFIRMED')
                if self.xbmc.getSkinDir() == target:
                    if loaded is None:
                        loaded = now
                    modal = self.xbmc.getCondVisibility('Window.IsVisible(yesnodialog)')
                    if modal and self.xbmc.getInfoLabel('Control.GetLabel(1)') == self.xbmc.getLocalizedString(13123):
                        saw_dialog = True
                    if not modal and (saw_dialog or now - loaded >= 12):
                        if self.skin() == target and self.xbmc.getSkinDir() == target:
                            return
                if now >= deadline or self.monitor.waitForAbort(.1):
                    raise UpdateError('INSTALL_SKIN_NOT_CONFIRMED')

    def restore_skin_after_install(self, previous_skin):
        """Restore skin.bobbi.cinema seamlessly after unattended background updates."""
        if previous_skin != 'skin.bobbi.cinema':
            return
        if not (self.details('skin.bobbi.cinema') or {}).get('enabled'):
            return
        with self._skin_keep_confirmer():
            if self.skin() != 'skin.bobbi.cinema':
                rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.bobbi.cinema'})
            if self.unattended:
                deadline = time.monotonic() + 14
                while time.monotonic() < deadline:
                    if (self.skin() == 'skin.bobbi.cinema'
                            and self.xbmc.getSkinDir() == 'skin.bobbi.cinema'
                            and not self.xbmc.getCondVisibility('Window.IsVisible(yesnodialog)')):
                        break
                    if self.monitor.waitForAbort(0.15):
                        break

    def quiesce(self):
        self.check_idle()
        if self.skin() == 'skin.bobbi.cinema':
            self.prepare_install_skin()
        from .runtime import call
        runtime = profile(name='runtime.json')
        until = time.monotonic() + 15
        legacy = False
        if runtime.is_file():
            try:
                status = call('status', {}, timeout=.3)
            except (OSError, ValueError, RuntimeError):
                status = None
            if isinstance(status, dict) and status.get('quiesce_protocol') == 1:
                try:
                    reply = call('quiesce', {'protocol': 1}, timeout=1)
                except OSError:
                    pass
                else:
                    if reply != {'accepted': True}:
                        raise UpdateError('CINEMA_STOP_NOT_ACCEPTED')
            legacy = (isinstance(status, dict) and 'quiesce_protocol' not in status
                      and status.get('ready') is True and status.get('version') == '0.1.0'
                      and all(type(status.get(key)) is bool for key in
                              ('native_owner', 'preparation', 'shares'))
                      and isinstance(status.get('account'), dict))
        if not legacy:
            self._acquire_runtime_lease(runtime, until)
        for name in ('plugin.video.bobbi', 'plugin.video.bobbi.torrent'):
            if (self.details(name) or {}).get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': False})
        self._acquire_runtime_lease(runtime, until)
        if any((self.details(n) or {}).get('enabled') for n in
               ('plugin.video.bobbi', 'plugin.video.bobbi.torrent')):
            raise UpdateError('CINEMA_DISABLE_NOT_CONFIRMED')
        _safe_path(runtime)
        if runtime.exists():
            runtime.unlink()
        if self.xbmc.Player().isPlaying():
            raise UpdateError('PLAYBACK_STARTED_DURING_INSTALL')

    def _acquire_runtime_lease(self, runtime, until):
        from .instance_lock import InstanceLock
        while getattr(self, '_runtime_lease', None) is None:
            lease = InstanceLock(str(runtime) + '.lock')
            try:
                lease.acquire()
            except OSError:
                pass
            else:
                self._runtime_lease = lease
                break
            if self.monitor.waitForAbort(.1) or time.monotonic() >= until:
                raise UpdateError('CINEMA_SERVICE_NOT_STOPPED')

    def verify(self, versions):
        for name, version in versions.items():
            actual = self.details(name)
            if not actual or actual['version'] != version:
                raise UpdateError('COMPONENT_REGISTRATION_FAILED:' + name)
        check_host_crypto()
        from .capabilities import probe
        capabilities = probe(rpc, 'kodi')
        if not capabilities.get('standard_playback'):
            raise UpdateError('PLAYER_API_UNAVAILABLE:' + ','.join(capabilities.get('errors', [])))

    def activate(self, versions):
        self.close()
        for name in sorted(versions, key=lambda n: n == 'plugin.video.bobbi'):
            if not (self.details(name) or {}).get('enabled'):
                try:
                    rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
                except RuntimeError as error:
                    raise UpdateError('COMPONENT_ENABLE_FAILED:' + name) from error
        if set(versions).issubset(self.enabled()):
            self.ensure_running()

    def restore(self, skin, enabled):
        self.close()
        for name in sorted(MANAGED, key=lambda n: n == 'plugin.video.bobbi'):
            actual = self.details(name)
            desired = name in enabled
            if actual and actual.get('enabled') != desired:
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': desired})
        if skin and skin != self.skin():
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})
        if 'plugin.video.bobbi' in enabled:
            self.ensure_running()

    def close(self):
        lease = getattr(self, '_runtime_lease', None)
        if lease is not None:
            self._runtime_lease = None
            lease.close()

    def ensure_running(self):
        """Confirm a live owner-thread reply, not merely Kodi's enabled flag."""
        from .runtime import call
        from .instance_lock import InstanceLock
        deadline, launched = time.monotonic() + 15, False
        while True:
            try:
                reply = call('playback', {'operation': 'snapshot'}, timeout=.3)
                if isinstance(reply, dict) and (reply.get('adapter') == 'standard'
                        or (isinstance(reply.get('boot_id'), str) and 'desired' in reply)):
                    return
            except (OSError, ValueError, RuntimeError):
                pass
            if not launched:
                lease = InstanceLock(str(profile(name='runtime.json')) + '.lock')
                try:
                    lease.acquire()
                except OSError:
                    pass
                else:
                    try:
                        name = 'plugin.video.bobbi'
                        if not (self.details(name) or {}).get('enabled'):
                            raise UpdateError('CINEMA_PROVIDER_NOT_ENABLED')
                        rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': False})
                        if (self.details(name) or {}).get('enabled'):
                            raise UpdateError('CINEMA_DISABLE_NOT_CONFIRMED')
                    finally:
                        lease.close()
                    rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
                    launched = True
            if self.monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                raise UpdateError('CINEMA_SERVICE_NOT_READY')


def _read_language_marker(work):
    path = _safe_path(Path(work) / LANGUAGE_MARKER)
    if not path.exists():
        return None
    try:
        if not path.is_file() or path.stat().st_size > 16384:
            return None
        data = _json(path.read_bytes())
        if isinstance(data, dict) and data.get('schema') == 1 and data.get('initialized') is True:
            return data
    except (OSError, ValueError, UpdateError):
        pass
    return None


def _write_language_marker(work, decision, locale):
    path = _safe_path(Path(work) / LANGUAGE_MARKER)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic(path, dict(schema=1, initialized=True, decision=decision, locale=locale))


def _guisettings_locale_state(userdata_root):
    """Inspect userdata/guisettings.xml read-only to distinguish default vs explicit en_gb."""
    if userdata_root is None:
        return 'absent'
    try:
        gui = _safe_path(Path(userdata_root) / 'guisettings.xml')
    except UpdateError:
        return 'ambiguous'
    if not gui.exists():
        return 'absent'
    try:
        if not gui.is_file() or gui.stat().st_size > 2 * 1024 * 1024:
            return 'ambiguous'
        raw = gui.read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            return 'ambiguous'
        root = ET.fromstring(raw)
        matches = [n for n in root.findall('./setting') if n.get('id') == 'locale.language']
        if not matches:
            return 'ambiguous'
        node = matches[0]
        if node.get('default') == 'true':
            return 'default'
        return 'explicit'
    except (OSError, ET.ParseError):
        return 'ambiguous'


def _has_historical_kodi_footprint(addons_root, userdata_root):
    """Return True if existing third-party addons or user sources indicate a non-fresh Kodi."""
    from .upstream_addons import OWNED_COMPONENTS
    if userdata_root is not None:
        u = Path(userdata_root)
        if (u / 'sources.xml').is_file() or (u / 'mediasources.xml').is_file():
            return True
    if addons_root is not None and Path(addons_root).is_dir():
        allowed = OWNED_COMPONENTS | {'packages', 'temp'}
        for child in Path(addons_root).iterdir():
            if child.name.startswith('.'):
                continue
            if child.name not in allowed:
                return True
    return False


def classify_language_profile(current_locale, *, work, addons_root=None, userdata_root=None, bobbi_installed=False):
    """Classify host language initialization state without modifying any setting."""
    marker = _read_language_marker(work)
    if marker is not None:
        return 'already_initialized'
    loc = (current_locale or '').strip()
    if loc and loc.lower() not in ('resource.language.en_gb', 'default'):
        return 'explicit_existing'
    if bobbi_installed:
        return 'explicit_existing'
    gui_state = _guisettings_locale_state(userdata_root)
    if gui_state == 'explicit':
        return 'explicit_existing'
    fresh_receipt = _safe_path(Path(work) / 'fresh-profile.json')
    if fresh_receipt.is_file():
        return 'fresh_managed'
    if gui_state in ('absent', 'default') and not _has_historical_kodi_footprint(addons_root, userdata_root):
        return 'fresh_managed'
    return 'ambiguous_historical'


def load_verified_zh_cn_pack(*, addons_root=None, payload=None, trust=None, host_resource_version='1.0.0'):
    """Locate and cryptographically verify official resource.language.zh_cn-11.0.105.zip."""
    candidates = []
    if addons_root is not None:
        pack_dir = Path(addons_root) / 'script.module.bobbi.platform' / ZH_CN_RELATIVE_DIR
        candidates.append(pack_dir)
    here = Path(__file__).resolve().parents[2] / ZH_CN_RELATIVE_DIR
    candidates.append(here)

    for folder in candidates:
        try:
            zip_path = _safe_path(folder / ZH_CN_FILENAME)
            prov_path = _safe_path(folder / 'provenance.json')
            if zip_path.is_file() and prov_path.is_file():
                raw = zip_path.read_bytes()
                prov = _json(prov_path.read_bytes())
                verify_zh_cn_archive(raw, prov, host_resource_version=host_resource_version)
                return raw
        except (OSError, ValueError, UpdateError):
            continue

    if payload is not None and Path(payload).is_file():
        from .offline_updates import load_trust
        active_trust = trust or load_trust()
        with SignedBundle(payload, active_trust, 'coreelec') as signed:
            manifest = signed.check_all()
            plat_row = next((r for r in manifest['components'] if r['id'] == 'script.module.bobbi.platform'), None)
            if plat_row is not None:
                plat_bytes = signed.read(plat_row['file'], plat_row['size'])
                with zipfile.ZipFile(BytesIO(plat_bytes)) as plat_zf:
                    archive_rows(plat_zf, plat_row)
                    z_member = 'script.module.bobbi.platform/' + (ZH_CN_RELATIVE_DIR / ZH_CN_FILENAME).as_posix()
                    p_member = 'script.module.bobbi.platform/' + (ZH_CN_RELATIVE_DIR / 'provenance.json').as_posix()
                    if z_member in plat_zf.namelist() and p_member in plat_zf.namelist():
                        raw = plat_zf.read(z_member)
                        prov = _json(plat_zf.read(p_member))
                        verify_zh_cn_archive(raw, prov, host_resource_version=host_resource_version)
                        return raw
    return None


def ensure_zh_cn_ready_and_selected(host, addons_root, dialog, *, payload=None, trust=None, rpc_fn=None):
    """Ensure resource.language.zh_cn is installed/enabled and locale.language readback matches."""
    call_rpc = rpc_fn or rpc
    addons_path = _safe_path(addons_root)

    # Check host kodi.resource version if reported by Kodi
    host_res_ver = '1.0.0'
    try:
        kr = host.details('kodi.resource')
        if isinstance(kr, dict) and isinstance(kr.get('version'), str):
            kodi_version(kr['version'])
            host_res_ver = kr['version']
    except UpdateError as err:
        if str(err).startswith('ADDON_STATE_UNKNOWN:'):
            return dict(ok=False, reason='addon_state_unknown')
        return dict(ok=False, reason='host_resource_invalid')

    try:
        installed = host.details(ZH_CN_ADDON_ID)
    except UpdateError:
        return dict(ok=False, reason='addon_state_unknown')

    if installed is not None:
        # Compatible existing pack (including newer versions): reuse without downgrading!
        try:
            kodi_version(installed['version'])
            live_xml = addons_path / ZH_CN_ADDON_ID / 'addon.xml'
            if live_xml.exists():
                _safe_path(live_xml)
                root = ET.fromstring(live_xml.read_bytes())
                if root.get('id') != ZH_CN_ADDON_ID or root.find('./extension[@point="kodi.resource.language"]') is None:
                    return dict(ok=False, reason='installed_pack_invalid')
        except (OSError, ET.ParseError, UpdateError):
            return dict(ok=False, reason='installed_pack_invalid')
    else:
        target = _safe_path(addons_path / ZH_CN_ADDON_ID)
        if target.exists() or target.is_symlink():
            # Unregistered residual directory: try one bounded refresh, never overwrite/delete!
            host.refresh()
            installed = host.details(ZH_CN_ADDON_ID)
            if installed is None:
                return dict(ok=False, reason='directory_conflict')
        else:
            raw_pack = None
            try:
                raw_pack = load_verified_zh_cn_pack(
                    addons_root=addons_path,
                    payload=payload,
                    trust=trust,
                    host_resource_version=host_res_ver,
                )
            except UpdateError as err:
                return dict(ok=False, reason=str(err))

            if raw_pack is not None:
                temp_dir = _safe_path(addons_path / ('.bobbi-lang-' + uuid.uuid4().hex))
                try:
                    with zipfile.ZipFile(BytesIO(raw_pack)) as zf:
                        rows = archive_rows(zf, {'id': ZH_CN_ADDON_ID})
                        for row in rows:
                            rel_parts = PurePosixPath(row.filename).parts[1:]
                            if not rel_parts:
                                continue
                            dest = temp_dir.joinpath(*rel_parts)
                            if row.is_dir():
                                dest.mkdir(parents=True, exist_ok=True)
                            else:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                dest.write_bytes(zf.read(row))
                    os.rename(temp_dir, target)
                except BaseException:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    raise
                host.refresh()
                installed = host.details(ZH_CN_ADDON_ID)
            elif hasattr(host, 'xbmc') and hasattr(host.xbmc, 'executebuiltin'):
                host.xbmc.executebuiltin('InstallAddon(%s)' % ZH_CN_ADDON_ID, False)
                deadline = time.monotonic() + 15
                while True:
                    installed = host.details(ZH_CN_ADDON_ID)
                    if installed is not None:
                        break
                    if host.monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                        return dict(ok=False, reason='pack_unavailable')

    if not installed:
        return dict(ok=False, reason='pack_not_registered')

    if not installed.get('enabled'):
        try:
            call_rpc('Addons.SetAddonEnabled', {'addonid': ZH_CN_ADDON_ID, 'enabled': True})
        except RuntimeError:
            return dict(ok=False, reason='pack_enable_failed')
        installed = host.details(ZH_CN_ADDON_ID)
        if not installed or not installed.get('enabled'):
            return dict(ok=False, reason='pack_enable_unconfirmed')

    # Verify CJK font readability BEFORE switching UI to Chinese
    if not readable_text(host, dialog, locale=ZH_CN_ADDON_ID, cjk_needed=True, rpc_fn=call_rpc):
        return dict(ok=False, reason='cjk_font_declined_or_unconfirmed')

    check = getattr(host, 'check_idle', None)
    if callable(check):
        check()

    changed = call_rpc('Settings.SetSettingValue', {'setting': 'locale.language', 'value': ZH_CN_ADDON_ID})
    actual_locale = (call_rpc('Settings.GetSettingValue', {'setting': 'locale.language'}) or {}).get('value')
    actual_addon = host.details(ZH_CN_ADDON_ID)
    if changed is not True or actual_locale != ZH_CN_ADDON_ID or not actual_addon or not actual_addon.get('enabled'):
        return dict(ok=False, reason='locale_readback_failed')

    return dict(ok=True, locale=actual_locale, version=actual_addon['version'])


def ensure_host_language(host, installer, dialog, *, payload=None, rpc_fn=None):
    """Apply first-use / upgrade host language policy without unsolicited resets."""
    if (
        not callable(getattr(host, 'locale', None))
        or not callable(getattr(host, 'details', None))
        or not hasattr(installer, 'addons')
        or not hasattr(installer, 'work')
        or not callable(getattr(installer, '_read', None))
    ):
        return dict(action='skipped_unmanaged_host')

    call_rpc = rpc_fn or rpc
    try:
        current_locale = host.locale()
    except Exception:
        return dict(action='skipped_locale_unreadable')

    state = installer._read()
    try:
        bobbi_installed = state is not None or host.details('plugin.video.bobbi') is not None
    except UpdateError:
        return dict(action='skipped_addon_state_unknown')

    category = classify_language_profile(
        current_locale,
        work=installer.work,
        addons_root=installer.addons,
        userdata_root=getattr(installer, 'userdata', None),
        bobbi_installed=bobbi_installed,
    )
    if category in ('already_initialized', 'explicit_existing'):
        if normalize_locale(current_locale) == 'zh_cn':
            try:
                zh_installed = host.details(ZH_CN_ADDON_ID)
            except UpdateError:
                return dict(action='skipped_addon_state_unknown')
            if not zh_installed or not zh_installed.get('enabled'):
                result = ensure_zh_cn_ready_and_selected(
                    host,
                    installer.addons,
                    dialog,
                    payload=payload,
                    trust=getattr(installer, 'trust', None),
                    rpc_fn=call_rpc,
                )
                if result['ok']:
                    _write_language_marker(installer.work, 'repaired_existing_zh_cn', ZH_CN_ADDON_ID)
                    return dict(action=category, locale=ZH_CN_ADDON_ID, version=result['version'], repaired=True)
                return dict(action='pack_unavailable', locale=current_locale, reason=result['reason'])
        if category == 'already_initialized':
            return dict(action='already_initialized', locale=current_locale)
        _write_language_marker(installer.work, 'preserved_existing', current_locale or 'resource.language.en_gb')
        return dict(action='preserved_existing', locale=current_locale)

    if category == 'fresh_managed':
        result = ensure_zh_cn_ready_and_selected(
            host, installer.addons, dialog, payload=payload, trust=installer.trust, rpc_fn=call_rpc
        )
        if result['ok']:
            _write_language_marker(installer.work, 'default_zh_cn', ZH_CN_ADDON_ID)
            return dict(action='default_zh_cn', locale=ZH_CN_ADDON_ID, version=result['version'])
        # Missing/corrupt pack: keep current language and NEVER write a fake completion marker!
        if hasattr(dialog, 'ok'):
            dialog.ok(
                tr('lang_pack_unavailable_title', locale=current_locale),
                tr('lang_pack_unavailable_body', locale=current_locale),
            )
        return dict(action='pack_unavailable', locale=current_locale, reason=result['reason'])

    # category == 'ambiguous_historical': highlight Chinese as default (preselect=0), allow keeping English.
    # Ensure prompt is readable even if Default font lacks CJK (bilingual EN/ZH options).
    choice = dialog.select(
        tr('lang_prompt_title', locale='en_gb'),
        [tr('lang_opt_zh', locale='en_gb'), tr('lang_opt_keep_en', locale='en_gb')],
        preselect=0,
    )
    if choice < 0:
        # Cancelled: keep current language and NEVER write a fake completion marker!
        return dict(action='cancelled', locale=current_locale)
    if choice == 1:
        _write_language_marker(installer.work, 'kept_current', current_locale or 'resource.language.en_gb')
        return dict(action='kept_current', locale=current_locale)

    result = ensure_zh_cn_ready_and_selected(
        host, installer.addons, dialog, payload=payload, trust=installer.trust, rpc_fn=call_rpc
    )
    if result['ok']:
        _write_language_marker(installer.work, 'selected_zh_cn', ZH_CN_ADDON_ID)
        return dict(action='selected_zh_cn', locale=ZH_CN_ADDON_ID, version=result['version'])
    if hasattr(dialog, 'ok'):
        dialog.ok(
            tr('lang_pack_unavailable_title', locale=current_locale),
            tr('lang_pack_unavailable_body', locale=current_locale),
        )
    return dict(action='pack_unavailable', locale=current_locale, reason=result['reason'])


def recover_interactive(installer, dialog, report=None, *, host=None):
    """Persistent host failure must never hide rollback/exit behind recover."""
    while True:
        try:
            installer.recover()
            return True
        except (OSError, ValueError, RuntimeError) as error:
            if report:
                report('recover', error)
            try:
                state = installer._read()
            except (OSError, ValueError, RuntimeError):
                state = None
            rollback = bool(state and state['phase'] in ('activation_pending', 'complete'))
            actions = (
                [tr('recover_retry', host=host)]
                + ([tr('recover_prev', host=host)] if rollback else [])
                + [tr('recover_exit', host=host)]
            )
            choice = dialog.select(tr('recover_title', host=host), actions, preselect=len(actions)-1)
            if choice == 0:
                continue
            if rollback and choice == 1:
                try:
                    installer.rollback()
                    return True
                except (OSError, ValueError, RuntimeError) as error:
                    if report:
                        report('rollback', error)
                    continue
            return False


def choose_package(dialog, payload, first, *, host=None):
    embedded = str(payload) if payload and Path(payload).is_file() else None
    if embedded and first:
        return embedded
    if embedded:
        choice = dialog.select(
            tr('source_title', host=host),
            [tr('source_browse', host=host), tr('source_embedded', host=host)],
        )
        if choice < 0:
            return None
        if choice == 1:
            return embedded
    return dialog.browse(1, tr('source_browse_heading', host=host), 'files', mask='.zip')


def install_online(installer, host, dialog):
    """A manual online action downloads first, then reuses the offline transaction."""
    import xbmcgui
    from .online_updates import latest, Cancelled, selected_track
    from .online_components import download
    host.check_idle()
    progress = xbmcgui.DialogProgress()
    selected = None
    try:
        progress.create(tr('online_title', host=host), tr('online_checking', host=host))
        cancelled = lambda: host.monitor.abortRequested() or progress.iscanceled()
        track, mirrors = selected_track(installer.work), {}
        offer = latest(cancelled, track=track, report=mirrors)
        state = installer._read() or {}
        watermark = installed_watermark(state)
        progress.close()
        if offer['sequence'] <= watermark:
            prefix = (
                tr('online_stable_behind', host=host)
                if track == 'stable' and offer['sequence'] < watermark
                else ''
            )
            dialog.ok(tr('online_up_to_date_title', host=host), prefix + tr('online_up_to_date_body', host=host))
            return False
        mirror_lbl = {
            'synchronized': tr('mirror_sync', host=host),
            'out-of-sync': tr('mirror_out_of_sync', host=host),
            'unavailable': tr('mirror_unavailable', host=host),
        }.get(mirrors.get('mirrors'), tr('mirror_unreported', host=host))
        dialog.textviewer(
            tr('online_offer_title', host=host),
            tr(
                'online_offer_body',
                host=host,
                track=tr('track_stable' if track == 'stable' else 'track_preview', host=host),
                installed=state.get('sequence', tr('not_installed', host=host)),
                tag=offer['tag'].upper(),
                mirror=mirror_lbl,
            ),
        )
        if not dialog.yesno(
            tr('online_confirm_title', host=host, tag=offer['tag'].upper()),
            tr('online_confirm_body', host=host, mb=(offer['size'] + 1024 * 1024 - 1) // (1024 * 1024)),
        ):
            return False
        host.check_idle()
        progress.create(tr('online_title', host=host), tr('online_downloading', host=host))
        selected = download(offer, installer.work / 'downloads', installer.trust,
                            cancelled, lambda percent: progress.update(percent))
        if cancelled():
            return False
        host.check_idle()
        progress.close()
        installer.apply(selected)
        sync_entry_from_bundle(selected, getattr(installer, 'addons', None), getattr(installer, 'trust', None), host=host)
        ensure_host_language(host, installer, dialog, payload=selected)
        return True
    except Cancelled:
        return False
    finally:
        progress.close()
        if selected is not None:
            selected.unlink(missing_ok=True)


_ENTRY_BOOTSTRAP_FILES = (
    '__init__.py', 'bootstrap_i18n.py', 'ce_installer.py', 'ce_install_ui.py', 'android_ui.py',
    'ce_storage.py', 'ce_recovery.py', 'offline_updates.py', 'catalog_compatibility.py',
    'optimization.py', 'updates.py', 'upstream_addons.py', 'signatures.py', 'release_trust.json',
    'paths.py', 'kodi.py', 'playback.py', 'capabilities.py', 'runtime.py', 'instance_lock.py',
    'online_updates.py', 'online_transport.py', 'online_partial.py', 'online_components.py',
)


def sync_entry_from_bundle(bundle, addons_root, trust=None, *, host=None):
    """Keep script.bobbi.start & its bootstrap synchronized from the verified signed bundle."""
    if bundle is None or addons_root is None:
        return False
    bundle_path = Path(bundle)
    if not bundle_path.is_file():
        return False
    try:
        root = _safe_path(addons_root)
        if not root.is_dir():
            return False
        from .offline_updates import load_trust
        active_trust = trust or load_trust()
        with SignedBundle(bundle_path, active_trust, 'coreelec') as signed:
            manifest = signed.check_all()
            entry_row = next((r for r in manifest['components'] if r['id'] == 'script.bobbi.start'), None)
            plat_row = next((r for r in manifest['components'] if r['id'] == 'script.module.bobbi.platform'), None)
            if entry_row is None or plat_row is None:
                return False
            live_entry = root / 'script.bobbi.start'
            live_xml = live_entry / 'addon.xml'
            if live_xml.is_file():
                try:
                    if ET.fromstring(live_xml.read_bytes()).get('version') == entry_row['version']:
                        return False
                except ET.ParseError:
                    pass
            entry_bytes = signed.read(entry_row['file'], entry_row['size'])
            plat_bytes = signed.read(plat_row['file'], plat_row['size'])
        temp_wrap = _safe_path(root / ('.bobbi-entry-' + uuid.uuid4().hex))
        stage_entry = temp_wrap / 'script.bobbi.start'
        try:
            with zipfile.ZipFile(BytesIO(entry_bytes)) as ezf:
                rows = archive_rows(ezf, entry_row)
                for row in rows:
                    rel_parts = PurePosixPath(row.filename).parts[1:]
                    if not rel_parts:
                        continue
                    dest = stage_entry.joinpath(*rel_parts)
                    if row.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(ezf.read(row))
            with zipfile.ZipFile(BytesIO(plat_bytes)) as pzf:
                archive_rows(pzf, plat_row)
                boot_dir = stage_entry / 'bootstrap' / 'bobbi_platform'
                boot_dir.mkdir(parents=True, exist_ok=True)
                for fname in _ENTRY_BOOTSTRAP_FILES:
                    member = 'script.module.bobbi.platform/lib/bobbi_platform/' + fname
                    if member in pzf.namelist():
                        (boot_dir / fname).write_bytes(pzf.read(member))
            if live_entry.exists():
                os.replace(live_entry, temp_wrap / 'previous')
            os.replace(stage_entry, live_entry)
        finally:
            if temp_wrap.exists():
                shutil.rmtree(temp_wrap, ignore_errors=True)
        if host is not None and callable(getattr(host, 'refresh', None)):
            host.refresh()
        return True
    except (OSError, ValueError, UpdateError, BadZipFile):
        return False


def install_auto_online(installer, host):
    """Unattended background online update when idle and auto_update_enabled is True."""
    import xbmc as _xbmc
    import xbmcgui
    from .online_updates import latest, Cancelled, selected_track
    from .online_components import download
    if not auto_update_enabled(installer.work):
        return False
    xbmc_mod = getattr(host, 'xbmc', _xbmc)
    monitor = getattr(host, 'monitor', None)
    abort_fn = getattr(monitor, 'abortRequested', lambda: False) if monitor is not None else (lambda: False)
    cond_fn = getattr(xbmc_mod, 'getCondVisibility', lambda _c: False)
    player_fn = getattr(xbmc_mod, 'Player', None)
    selected = None
    try:
        host.check_idle()
        if cond_fn('System.HasModalDialog'):
            return False
        cancelled = lambda: (
            abort_fn()
            or (callable(player_fn) and player_fn().isPlaying())
            or not auto_update_enabled(installer.work)
        )
        track = selected_track(installer.work)
        offer = latest(cancelled, track=track)
        state = installer._read() or {}
        watermark = installed_watermark(state)
        if offer['sequence'] <= watermark:
            return False
        previous_skin = host.skin() if callable(getattr(host, 'skin', None)) else None
        selected = download(offer, installer.work / 'downloads', installer.trust, cancelled)
        if cancelled() or cond_fn('System.HasModalDialog'):
            return False
        host.check_idle()
        installer.apply(selected)
        sync_entry_from_bundle(selected, getattr(installer, 'addons', None), getattr(installer, 'trust', None), host=host)
        ensure_host_language(host, installer, None, payload=selected)
        restore_skin = getattr(host, 'restore_skin_after_install', None)
        if callable(restore_skin):
            restore_skin(previous_skin)
        en = normalize_locale(active_locale(host=host, rpc_fn=rpc)) == 'en_gb'
        notify_fn = getattr(xbmcgui.Dialog(), 'notification', None)
        if callable(notify_fn):
            notify_fn(
                'Bobbi TV Updated' if en else '波比 TV 已自动更新',
                (f"Updated to {offer['tag'].upper()}" if en else f"已自动升级至 {offer['tag'].upper()}"),
                sound=False,
            )
        return True
    except (Cancelled, PlaybackActive):
        return False
    finally:
        if selected is not None:
            selected.unlink(missing_ok=True)


def failure_message(error, stage=None, *, locale=None, host=None):
    """Explain existing failures without echoing URLs, paths or server bodies."""
    lang = normalize_locale(locale) if locale is not None else active_locale(host=host, rpc_fn=rpc)
    en = (lang == 'en_gb')
    code = str(error)
    if code.startswith(('DEPENDENCY_NEEDS_UPGRADE:', 'DEPENDENCY_HANDOFF_OPENED:')):
        parts = code.split(':', 2)
        comp = parts[1] if len(parts) > 1 and parts[1] in UPSTREAM_COMPONENTS | HOST_COMPONENTS else ''
        ver_spec = parts[2] if len(parts) > 2 and re.fullmatch(r'[A-Za-z0-9.+_@~:-]+->[A-Za-z0-9.+_@~:-]+', parts[2]) else ''
        have_ver, _, need_ver = ver_spec.partition('->') if ver_spec else ('', '', '')
        if code.startswith('DEPENDENCY_HANDOFF_OPENED:'):
            detail_en = f' for {comp} ({have_ver} -> {need_ver})' if comp and have_ver and need_ver else (f' for {comp}' if comp else '')
            detail_zh = f' {comp}（已装 {have_ver}，需 {need_ver}）' if comp and have_ver and need_ver else (f' {comp}' if comp else '')
            return (
                f'Opened Kodi Dependencies (addons://dependencies/){detail_en}. Select it and click "Update", then reopen "Bobbi TV · Get Started" to continue.'
                if en else
                f'已打开 Kodi“依赖项”列表（addons://dependencies/）以更新{detail_zh}。请在列表中点选该组件并点击“更新”，完成后重新打开“波比 TV · 开始使用”继续。'
            )
        detail_en = f' ({comp}: installed {have_ver}, required {need_ver})' if comp and have_ver and need_ver else (f' ({comp})' if comp else '')
        detail_zh = f'（{comp} 当前 {have_ver}，需至少 {need_ver}）' if comp and have_ver and need_ver else (f'（{comp}）' if comp else '')
        return (
            f'Installed Kodi dependency{detail_en} is older than required (existing files are never overwritten). Open Kodi Dependencies (addons://dependencies/), select {comp or "the add-on"} -> Update, then reopen "Bobbi TV · Get Started".'
            if en else
            f'Kodi 已安装的依赖{detail_zh}版本低于所需下限（不会私自覆盖现有目录）。请在 Kodi“依赖项”列表（addons://dependencies/）中点选该组件并点击“更新”，完成后再打开“波比 TV · 开始使用”。'
        )
    if code.startswith('DEPENDENCY_DIRECTORY_CONFLICT:'):
        return (
            'An unregistered residual add-on folder conflicts with a required dependency (existing files were kept untouched). Check your Kodi addons folder or restart Kodi, then retry.'
            if en else
            '检测到未注册的同名插件残留目录（原目录保留未动，不会覆盖或删除）。请重启 Kodi 或在插件管理核对后再试。'
        )
    if code == 'DEPENDENCY_PREPARATION_CANCELLED':
        return (
            'Dependency preparation was cancelled or the active profile changed. Existing files and accounts remain untouched.'
            if en else
            '已取消依赖准备或当前配置已切换。原有组件、账号与数据保持不变。'
        )
    if code.startswith(('DEPENDENCY_UNAVAILABLE:', 'DEPENDENCY_ENABLE_FAILED:')):
        return (
            'Kodi could not install or enable a required dependency (existing Kodi components are never overwritten). Update or enable the add-on below in Kodi, then reopen Start.'
            if en else
            'Kodi 未能启用或满足所需依赖版本（不会私自覆盖 Kodi 组件）。请在 Kodi 插件管理中更新下方组件后，再打开“开始使用”。'
        )
    if code.startswith(('Kodi dependency too old:', 'Kodi dependency missing or invalid:')):
        return (
            'An upstream Kodi dependency is missing or older than required (existing Kodi components are never overwritten). Update it in Kodi Add-ons, then reopen Start.'
            if en else
            'Kodi 已安装的上游依赖版本过低或缺失（不会私自覆盖 Kodi 组件）。请在 Kodi 插件管理中更新对应依赖后，再打开“开始使用”。'
        )
    if code.startswith('COMPONENT_ENABLE_FAILED:') or code == 'HOST_ACTIVATION_NOT_CONFIRMED':
        return (
            'Cinema components are not enabled yet. Reopen Start to recover without deleting data.'
            if en else
            '影院组件尚未启用。请重新打开“开始使用”恢复，不用删除数据。'
        )
    if code.startswith(('ADDON_STATE_UNKNOWN:', 'COMPONENT_REGISTRATION_FAILED:')) or code == 'ADDON_REFRESH_NOT_CONFIRMED':
        return (
            'Kodi has not confirmed add-on registration. Restart Kodi and reopen Start to recover; personal data is kept.'
            if en else
            'Kodi 未确认组件已登记。请重启 Kodi，再打开“开始使用”恢复；不用删除个人数据。'
        )
    if code == 'CRYPTO_DEPENDENCY_UNUSABLE':
        return (
            'Kodi PyCryptodome is unavailable. Install/repair PyCryptodome from your Kodi repository and retry.'
            if en else
            'Kodi 的 PyCryptodome 模块不可用。请用本机 Kodi 仓库修复对应架构的依赖，再重试。'
        )
    if code.startswith('PLAYER_API_UNAVAILABLE:'):
        return (
            'Required Kodi playback RPC interfaces are unavailable; check your CoreELEC / Kodi version.'
            if en else
            '当前 Kodi 未提供所需播放接口，请核对 CoreELEC 和 Kodi 版本。'
        )
    if code == 'CINEMA_SERVICE_NOT_READY':
        return (
            'Cinema service is not ready yet. Restart Kodi and reopen Start; no re-login required.'
            if en else
            '影院服务未就绪。请重启 Kodi 后打开“开始使用”恢复，无需重新登录。'
        )
    if code == 'INSTALL_SKIN_NOT_CONFIRMED':
        return (
            'Temporary skin switch was not confirmed. Restart installation and choose "Yes" on Kodi\'s "Keep skin?" prompt.'
            if en else
            'Kodi 未保留临时界面。重新开始安装，在 Kodi 的“保持皮肤？”弹窗中选“是”。'
        )
    if code == 'CINEMA_SERVICE_NOT_STOPPED':
        return (
            'Previous playback service is still draining. Stop playback, restart Kodi, and reopen Start.'
            if en else
            '旧播放服务尚未退出，未取得替换许可。请停止播放，重启 Kodi 后从“开始使用”恢复。'
        )
    if isinstance(error, BadZipFile):
        return (
            'ZIP file is incomplete; re-download the full package starting with script.bobbi.start-.'
            if en else
            'ZIP 文件不完整，请重新下载文件名以 script.bobbi.start- 开头的完整安装包。'
        )
    if code == 'PLAYBACK_ACTIVE':
        return (
            'Please stop video playback before updating or switching the interface.'
            if en else
            '请先停止播放，再更新程序或切换界面。'
        )
    if code == 'INSTALLATION_SPACE_REQUIRED' or getattr(error, 'errno', None) == errno.ENOSPC:
        plan = getattr(error, 'space', None)
        if en:
            sizes = ('Need at least {:.1f} MiB, {:.1f} MiB free. '.format(
                plan['required_bytes']/1024**2, plan['free_bytes']/1024**2) if plan else '')
            return sizes + 'Insufficient storage; open "Storage and cleanup" to inspect reclaimable cache.'
        sizes = ('需新增至少 {:.1f} MiB，当前可用 {:.1f} MiB。'.format(
            plan['required_bytes']/1024**2, plan['free_bytes']/1024**2) if plan else '')
        return sizes + '空间不足，请到“存储空间与清理”查看可清理内容。'
    if isinstance(error, PermissionError) or getattr(error, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
        return (
            'Storage is not writable; check disk space and permissions without deleting accounts or backups.'
            if en else
            '无法写入存储设备，请检查空间和写入权限，勿删除账号或程序备份。'
        )
    if isinstance(getattr(error, 'reason', error), ssl.SSLError):
        return (
            'Secure TLS connection failed; check device clock and network, or use the full offline ZIP.'
            if en else
            '无法建立安全连接，请检查设备时间和网络，或使用完整离线包。'
        )
    messages_zh = {
        'STORAGE_PLAN_CHANGED': '可清理内容已变化，本次已停止。请重新预览后再清理。',
        'Another update is active': '另一个安装或下载操作正在进行，请等待完成后重试。',
        'ONLINE_CANCELLED': '已取消操作。程序、备份和账号保持不变。',
        'ONLINE_TIMEOUT': '下载或查询超时，请重试。可续传的进度已保留，也可使用完整离线包。',
        'ONLINE_SHORT_READ': '安装包未下载完整，请重试。可续传的进度已保留，现有程序未更改。',
        'ONLINE_LENGTH_INVALID': '安装包大小不符，未安装。请重新下载完整包。',
        'ONLINE_CONTENT_INVALID': '安装包内容不符，未安装。请重新下载完整包。',
        'ONLINE_GENERATION_MISMATCH': '安装包与线上版本不一致，未安装。请稍后重新检查更新。',
        'ONLINE_PACKAGE_INVALID': '安装包不完整，未安装。请重新下载完整包。',
        'ONLINE_RANGE_INVALID': '无法续传这个安装包，请重新检查更新。现有程序未更改。',
        'ONLINE_DOWNLOAD_BUSY': '另一个更新窗口正在下载，请等待完成或关闭它。',
        'ONLINE_CACHE_PATH_INVALID': '下载缓存目录不可用，请改用完整离线包安装。',
        'ONLINE_OFFER_INVALID': '暂时查不到更新，请稍后重试，或从国内下载页获取完整包。',
        'ONLINE_TRACK_MISMATCH': '发行轨道与安装包不匹配，未安装。请等待正确的同轨道版本。',
        'ONLINE_LEGACY_UNVERIFIED': '旧更新入口的稳定版身份尚未核实，未安装。请等待轨道入口同步或使用已核实的离线包。',
        'ONLINE_MIRROR_CONFLICT': '镜像同版本内容冲突，未安装。请等待发布者核对后再试。',
        'ONLINE_RESPONSE_INVALID': '下载服务暂不可用，请重试或使用完整离线包。',
        'ONLINE_REDIRECT_REJECTED': '此下载地址不受支持，请从项目下载页获取完整包。',
        'GENERATION_NOT_NEWER': '所选安装包版本较旧或相同，请通过版本恢复入口使用旧版。',
        'NO_PREVIOUS_PROGRAM_GENERATION': '本机没有上一版本备份，账号与观看记录保留。',
        'CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE': '目标版本无法确认能读取当前片库来源。已保留程序和资料；如需回退，请显式选择与旧版本配套的数据备份。',
        'RECOVERY_POINT_INVALID': '恢复包不完整或已变化，未恢复。请改用上一版本备份或重新下载完整包。',
        'RECOVERY_STORE_LIMIT': '恢复目录需要检查，请保留文件并联系维护者。仍可尝试“恢复上一版本”。',
    }
    messages_en = {
        'STORAGE_PLAN_CHANGED': 'Reclaimable files changed during confirmation; preview again before cleaning.',
        'Another update is active': 'Another installation or download is currently active; please wait and retry.',
        'ONLINE_CANCELLED': 'Operation cancelled. Programs, backups and accounts remain unchanged.',
        'ONLINE_TIMEOUT': 'Network request timed out; retry to resume or use the full offline package.',
        'ONLINE_SHORT_READ': 'Download incomplete; retry to resume. Installed programs were not changed.',
        'ONLINE_LENGTH_INVALID': 'Package size mismatch; nothing was installed. Re-download the full package.',
        'ONLINE_CONTENT_INVALID': 'Package digest mismatch; nothing was installed. Re-download the full package.',
        'ONLINE_GENERATION_MISMATCH': 'Package generation differs from the published feed; re-check for updates.',
        'ONLINE_PACKAGE_INVALID': 'Package archive is invalid; nothing was installed.',
        'ONLINE_RANGE_INVALID': 'Resume range was rejected; re-check for updates. Installed programs are unchanged.',
        'ONLINE_DOWNLOAD_BUSY': 'Another update window is downloading; wait for it to finish.',
        'ONLINE_CACHE_PATH_INVALID': 'Download cache directory is unusable; install from a full offline package.',
        'ONLINE_OFFER_INVALID': 'Update metadata is currently unavailable; retry later or use a full offline ZIP.',
        'ONLINE_TRACK_MISMATCH': 'Update track does not match the package; wait for a matching release.',
        'ONLINE_LEGACY_UNVERIFIED': 'Legacy feed offer could not be verified against the stable track.',
        'ONLINE_MIRROR_CONFLICT': 'Update mirrors reported conflicting metadata for the same sequence.',
        'ONLINE_RESPONSE_INVALID': 'Download service returned an invalid response; retry or use offline ZIP.',
        'ONLINE_REDIRECT_REJECTED': 'Unsupported download redirect rejected.',
        'GENERATION_NOT_NEWER': 'Selected package is older or already installed; use recovery to roll back.',
        'NO_PREVIOUS_PROGRAM_GENERATION': 'No previous version backup is stored on this device; accounts are kept.',
        'CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE': 'Target version cannot read the current source registry format; data and programs were kept.',
        'RECOVERY_POINT_INVALID': 'Recovery package is incomplete or modified; use one-step rollback or re-download.',
        'RECOVERY_STORE_LIMIT': 'Recovery directory exceeded inspection bounds; files were preserved.',
    }
    table = messages_en if en else messages_zh
    if code in table:
        return table[code]
    if isinstance(error, UpdateError) and ('signature' in code or code.startswith('Offline ')):
        return (
            'Package signature verification failed; re-download the official full ZIP.'
            if en else
            '安装包校验失败，请从项目下载页重新下载完整包。'
        )
    if (isinstance(error, OSError) and stage in (None, 'online')) or code.startswith('ONLINE_'):
        return (
            'Download incomplete; check network and retry (resumable progress was kept), or use the offline ZIP.'
            if en else
            '下载未完成，请检查网络后重试，或使用完整离线包。可续传的进度已保留。'
        )
    return (
        'Installation incomplete; reopen "Bobbi TV · Start" to recover or retry.'
        if en else
        '安装未完成，请重新打开“波比 TV · 开始使用”恢复或重试。'
    )


def diagnosis(stage, error):
    """One line shared by the television and Kodi log. Never echo an exception."""
    where = {'init': '初始化', 'font': '界面字体', 'lang': '界面语言', 'recover': '恢复安装', 'menu': '读取状态',
             'storage': '存储预检', 'online': '在线更新', 'apply': '安装组件', 'rollback': '恢复程序',
             'settings': '进入设置', 'validate': '校验安装包'}.get(stage, '安装')
    reason, _, detail = str(error).partition(':')
    known = {'DEPENDENCY_UNAVAILABLE', 'DEPENDENCY_ENABLE_FAILED', 'DEPENDENCY_GRAPH_INVALID',
             'DEPENDENCY_NEEDS_UPGRADE', 'DEPENDENCY_HANDOFF_OPENED', 'DEPENDENCY_DIRECTORY_CONFLICT', 'DEPENDENCY_PREPARATION_CANCELLED',
             'COMPONENT_REGISTRATION_FAILED', 'COMPONENT_ENABLE_FAILED', 'HOST_ACTIVATION_NOT_CONFIRMED',
             'CRYPTO_DEPENDENCY_UNUSABLE', 'PLAYER_API_UNAVAILABLE',
             'ADDON_STATE_UNKNOWN', 'CINEMA_SERVICE_NOT_READY', 'CINEMA_SERVICE_NOT_STOPPED', 'INSTALL_SKIN_NOT_CONFIRMED',
             'CINEMA_DISABLE_NOT_CONFIRMED', 'CINEMA_STOP_NOT_ACCEPTED', 'ADDON_REFRESH_CANCELLED',
             'ADDON_REFRESH_NOT_CONFIRMED', 'INSTALLATION_PATHS_INVALID', 'INSTALLATION_JOURNAL_INVALID',
             'INSTALLATION_SPACE_REQUIRED', 'INSTALLATION_RECOVERY_REQUIRED', 'PLAYBACK_ACTIVE',
             'GENERATION_NOT_NEWER', 'PREVIOUS_PROGRAM_INCOMPLETE', 'PREVIOUS_PROGRAM_SPECIAL_FILE',
             'PREVIOUS_PROGRAM_RECEIPT_REQUIRED', 'CE_CATALOG_SCHEMA_UNREADABLE', 'CE_CATALOG_SCHEMA_UNINITIALIZED_OR_UNKNOWN',
             'CE_CATALOG_PROGRAM_SCHEMA_UNPROVEN', 'CE_CATALOG_OTHER_PROFILES_REQUIRE_EXPLICIT_REVIEW',
             'CE_CATALOG_SCHEMA_INCOMPATIBLE_REQUIRES_EXPLICIT_OFFLINE_RESTORE',
             'CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE', 'HOST_RESTORE_NOT_CONFIRMED'}
    allowed_addons = MANAGED | UPSTREAM_COMPONENTS | HOST_COMPONENTS | {ZH_CN_ADDON_ID}
    extra_version = ''
    if reason in ('DEPENDENCY_NEEDS_UPGRADE', 'DEPENDENCY_HANDOFF_OPENED'):
        code = reason
        comp_part, _, ver_part = detail.partition(':')
        detail = comp_part if comp_part in allowed_addons else ''
        if detail and re.fullmatch(r'[A-Za-z0-9.+_@~:-]+->[A-Za-z0-9.+_@~:-]+', ver_part):
            extra_version = ver_part
    elif reason in known:
        code = reason
        first_part = detail.partition(':')[0]
        detail = first_part if first_part in allowed_addons else ''
    elif reason in ('Kodi dependency too old', 'Kodi dependency missing or invalid'):
        code = 'DEPENDENCY_TOO_OLD' if reason == 'Kodi dependency too old' else 'DEPENDENCY_MISSING'
        candidate_comp = detail.strip().split(';', 1)[0].split()[0] if detail.strip() else ''
        if candidate_comp in allowed_addons:
            detail = candidate_comp
            reason = 'DEPENDENCY_UNAVAILABLE'
        else:
            detail = ''
    elif isinstance(error, BadZipFile):
        code = 'ZIP_INVALID'
    elif isinstance(error, OSError):
        code = 'IO_' + errno.errorcode.get(getattr(error, 'errno', None), 'UNAVAILABLE')
    elif isinstance(error, ImportError):
        code = 'MODULE_UNAVAILABLE'
    elif reason == 'Kodi RPC failed' and detail.strip() in {'Addons.GetAddons','Addons.GetAddonDetails',
            'Addons.SetAddonEnabled','Settings.GetSettingValue','Settings.SetSettingValue','JSONRPC.Introspect'}:
        code = 'KODI_RPC ' + detail.strip()
    elif type(error) in (KeyError, TypeError, AttributeError, IndexError, TimeoutError, ValueError):
        code = type(error).__name__
    else:
        code = 'PACKAGE_CHECK' if isinstance(error, UpdateError) else 'INSTALL_ERROR'
    component = detail if reason in known and detail in allowed_addons else ''
    tb = error.__traceback__
    frame = ''
    while tb:
        source = Path(tb.tb_frame.f_code.co_filename).stem
        if source in {'ce_installer','ce_install_ui','ce_recovery','ce_storage','kodi','updates',
                      'offline_updates','catalog_compatibility','online_updates','upstream_addons','bootstrap_i18n'}:
            frame = f'{source}:{tb.tb_lineno}'
        tb = tb.tb_next
    return ' · '.join(v for v in (where, code, component, extra_version, frame) if v)


def readable_text(host, dialog, *, locale=None, cjk_needed=None, rpc_fn=None):
    """Offer Kodi's built-in Unicode Arial font only when CJK text is actually needed on Estuary Default."""
    if host.skin() != 'skin.estuary':
        return True
    if cjk_needed is False:
        return True
    resolved_locale = locale
    if resolved_locale is None and cjk_needed is None and callable(getattr(host, 'locale', None)):
        try:
            resolved_locale = host.locale()
        except Exception:
            resolved_locale = None
    if cjk_needed is None and resolved_locale is not None and not is_cjk_locale(resolved_locale):
        # English / non-CJK UI renders English bootstrap strings cleanly on Estuary Default font.
        return True
    call_rpc = rpc_fn or rpc
    if call_rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.font'}).get('value') != 'Default':
        return True
    host.check_idle()
    if not dialog.yesno('Display Chinese text',
            'Bobbi TV uses Chinese menus. Enable the built-in Arial font so they are readable? '
            'This changes only the interface font, not video subtitles. Choose No to exit.'):
        return False
    host.check_idle()
    changed = call_rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.font', 'value': 'Arial'})
    actual = call_rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.font'}).get('value')
    if changed is not True or actual != 'Arial':
        dialog.ok('Font not changed', 'Open Settings > Interface > Skin > Fonts, select Arial, then open Bobbi TV again.')
        return False
    return True


def main(payload=None, online=False, storage=False, auto=False):
    import xbmc
    from .android_ui import bundled_host, start
    if bundled_host():
        return None if auto else start(online=online, storage=storage)
    import xbmcgui
    import xbmcvfs
    dialog = None if auto else xbmcgui.Dialog()
    host = None
    from .optimization import observe
    from .paths import profile_root
    diagnostic_root = None
    started = time.monotonic()
    stage = 'init'
    def report(step, error):
        if diagnostic_root is not None:
            observe(diagnostic_root, {'online':'update','auto':'update','rollback':'rollback'}.get(step,'install'),
                    'space' if str(error).partition(':')[0] == 'INSTALLATION_SPACE_REQUIRED' else 'failed', started)
        line = diagnosis(step, error)
        try:
            import xbmcaddon
            version = xbmcaddon.Addon('script.bobbi.start').getAddonInfo('version')
            kodi_version_match = re.match(r'^[0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]{1,2})?', xbmc.getInfoLabel('System.BuildVersion'))
            if isinstance(version, str) and re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}', version) and kodi_version_match:
                line += ' · ZIP ' + version + ' / Kodi ' + kodi_version_match[0]
        except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
            pass
        if hasattr(xbmc, 'log'):
            xbmc.log('[bobbi-install] ' + line, getattr(xbmc, 'LOGWARNING', xbmc.LOGERROR) if auto else xbmc.LOGERROR)
        if not auto and dialog is not None and hasattr(dialog, 'ok'):
            old = str(error) in ('PREVIOUS_PROGRAM_INCOMPLETE', 'PREVIOUS_PROGRAM_SPECIAL_FILE', 'PREVIOUS_PROGRAM_RECEIPT_REQUIRED')
            message = (tr('report_old_backup_body', host=host) if old
                       else failure_message(error, step, host=host))
            title = tr('report_old_backup_title' if old else 'report_failed_title', host=host)
            dialog.ok(title, message + tr('report_diag_prefix', host=host) + line)
    try:
        try:
            host = KodiHost(dialog=dialog, unattended=auto)
        except TypeError:
            host = KodiHost()
        try:
            diagnostic_root = profile_root()
        except (ValueError, OSError, RuntimeError, AttributeError, ImportError):
            pass
        installer = Installer(xbmcvfs.translatePath('special://home/addons'),
                              profile('script.bobbi.start'), host)
        if auto:
            stage = 'auto'
            state_now = installer._read()
            if not state_now or state_now.get('host_pending') or state_now.get('phase') not in ('complete', 'restored'):
                return False
            updated = install_auto_online(installer, host)
            if updated and diagnostic_root is not None:
                observe(diagnostic_root, 'update', 'ok', started)
            return updated
        if not storage and callable(getattr(installer, '_read', None)):
            try:
                pending_state = installer._read()
            except (OSError, ValueError, RuntimeError):
                pending_state = 'invalid'
            if pending_state is None or (isinstance(pending_state, dict)
                    and not pending_state.get('host_pending')
                    and pending_state.get('phase') in ('complete', 'restored')):
                stage = 'lang'
                ensure_host_language(host, installer, dialog, payload=payload)
        stage = 'font'
        if not readable_text(host, dialog):
            return
        stage = 'recover'
        if not recover_interactive(installer, dialog, report, host=host):
            return
        stage = 'menu'
        state = installer._read()
        actions = [
            tr('menu_settings', host=host),
            tr('menu_install_local', host=host),
            tr('menu_rollback', host=host),
            tr('menu_return_kodi', host=host),
            tr('menu_online', host=host),
            tr('menu_storage', host=host),
            tr('menu_recovery', host=host),
            tr('menu_track', host=host),
        ]
        first = state is None and not host.details('plugin.video.bobbi')
        choice = 5 if storage else (4 if online or (first and not (payload and Path(payload).is_file())) else (
            1 if first else dialog.select(tr('menu_title', host=host), actions)))
        if choice == 7:
            from .online_updates import selected_track, TRACKS
            current = selected_track(installer.work)
            selected = dialog.select(
                tr('track_title', host=host),
                [tr('track_opt_stable', host=host), tr('track_opt_preview', host=host)],
                preselect=TRACKS.index(current),
            )
            if selected in (0, 1) and (selected == 0 or dialog.yesno(
                    tr('track_preview_confirm_title', host=host),
                    tr('track_preview_confirm_body', host=host))):
                selected_track(installer.work, TRACKS[selected])
            return
        if choice == 6:
            stage = 'rollback'
            from .ce_recovery import show
            if show(installer, host, dialog):
                dialog.ok(tr('restored_title', host=host), tr('restored_body', host=host))
            return
        if choice == 5:
            stage = 'storage'
            from .ce_storage import show
            show(installer, host, dialog)
            return
        if choice == 4:
            stage = 'online'
            if not install_online(installer, host, dialog):
                return
            if diagnostic_root is not None:
                observe(diagnostic_root, 'update', 'ok', started)
            dialog.ok(tr('installed_title', host=host), tr('installed_online_body', host=host))
            choice = 0
        if choice == 1:
            stage = 'validate'
            selected = choose_package(dialog, payload, first, host=host)
            if not selected:
                return
            from .ce_storage import plan_text, require_space
            selected = xbmcvfs.translatePath(selected)
            plan = installer.plan_space(selected)
            require_space(plan)
            dialog.textviewer(tr('space_title', host=host), plan_text(plan, host=host))
            host.check_idle()
            if not dialog.yesno(
                tr('install_confirm_title', host=host),
                tr('install_confirm_body', host=host,
                   required=plan['required_bytes']/1024**2, free=plan['free_bytes']/1024**2),
            ):
                return
            stage = 'apply'
            installer.apply(selected)
            ensure_host_language(host, installer, dialog, payload=selected)
            if diagnostic_root is not None:
                observe(diagnostic_root, 'install', 'ok', started)
            dialog.ok(tr('installed_title', host=host), tr('installed_offline_body', host=host))
            choice = 0
        elif choice == 2:
            stage = 'rollback'
            if dialog.yesno(tr('rollback_confirm_title', host=host), tr('rollback_confirm_body', host=host)):
                installer.rollback()
                dialog.ok(tr('restored_title', host=host), tr('restored_body', host=host))
            return
        elif choice == 3:
            host.check_idle()
            skin = (state or {}).get('previous_skin') or 'skin.estuary'
            if skin == 'skin.bobbi.cinema':
                skin = 'skin.estuary'
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})
            return
        if choice == 0:
            stage = 'settings'
            xbmc.executebuiltin('RunScript(script.bobbi.setup)')
    except Exception as error:
        if str(error).startswith('DEPENDENCY_HANDOFF_OPENED:'):
            if hasattr(xbmc, 'log'):
                xbmc.log('[bobbi-install] ' + diagnosis(stage, error), getattr(xbmc, 'LOGINFO', 1))
            return
        report(stage, error)
    finally:
        close = getattr(host, 'close', None)
        if close:
            close()
