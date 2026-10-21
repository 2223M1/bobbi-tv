"""Kodi-native installation UI. No SSH, HTTP control port or developer paths."""
from pathlib import Path
import os
import shutil
import sys
import time
import uuid
import xml.etree.ElementTree as ET

from .ce_installer import Installer, MANAGED, blocked
from .kodi import rpc
from .paths import profile
from .updates import UpdateError, _safe_path
from .upstream_addons import UPSTREAM_COMPONENTS, compare_versions


class KodiHost:
    def __init__(self):
        import xbmc
        self.xbmc = xbmc
        self.monitor = xbmc.Monitor()

    def skin(self):
        return rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.skin'})['value']

    def details(self, name):
        try:
            value = rpc('Addons.GetAddonDetails', {'addonid': name,
                'properties': ['version', 'enabled']})['addon']
        except RuntimeError:
            # A failed detail RPC is not evidence of absence. Only a complete
            # installed-addon enumeration can prove the addon does not exist.
            listing = rpc('Addons.GetAddons', {'enabled': 'all', 'properties': ['enabled', 'version']})
            rows = listing.get('addons', [])
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
        self.xbmc.executebuiltin('UpdateLocalAddons', True)

    def dependencies(self, staged):
        minimums = dict.fromkeys(UPSTREAM_COMPONENTS, '0.0.0')
        minimums['script.module.pycryptodome'] = '3.4.3'
        for name in MANAGED | UPSTREAM_COMPONENTS:
            for dep in ET.parse(staged / name / 'addon.xml').findall('./requires/import'):
                key = dep.get('addon')
                if key in minimums and compare_versions(dep.get('version', '0.0.0'), minimums[key]) > 0:
                    minimums[key] = dep.get('version', '0.0.0')
        for name, minimum in sorted(minimums.items()):
            installed = self.details(name)
            if not installed and name in UPSTREAM_COMPONENTS:
                # Signed, unchanged originals are available offline. Seed only
                # absent addons; never overwrite an installed upstream version
                # or edit Kodi's origin database. Subsequent updates stay Kodi's.
                import xbmcvfs
                root = _safe_path(xbmcvfs.translatePath('special://home/addons'))
                target = _safe_path(root / name)
                if not target.exists():
                    temporary = root / ('.bobbi-dependency-' + uuid.uuid4().hex)
                    shutil.copytree(staged / name, temporary)
                    os.rename(temporary, target)
                    self.refresh()
                    installed = self.details(name)
            if not installed or compare_versions(installed['version'], minimum) < 0:
                # Kodi resolves original repository dependencies, prompts as
                # required and picks the actual platform ABI. Never overwrite.
                self.xbmc.executebuiltin('InstallAddon(%s)' % name, True)
                installed = self.details(name)
            if installed and not installed.get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
                installed = self.details(name)
            if (not installed or not installed.get('enabled')
                    or compare_versions(installed['version'], minimum) < 0):
                raise UpdateError('DEPENDENCY_UNAVAILABLE:' + name)

    def quiesce(self):
        if self.xbmc.Player().isPlaying():
            raise UpdateError('PLAYBACK_ACTIVE')
        if self.skin() == 'skin.bobbi.cinema':
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.estuary'})
        for name in ('plugin.video.bobbi', 'plugin.video.bobbi.torrent'):
            if (self.details(name) or {}).get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': False})
        # A registration can survive os._exit. Acquire the stable OS lease,
        # recheck disabled state, then remove only that dead host's marker.
        # Retain the lease through file replacement, until activate/restore.
        from .instance_lock import InstanceLock
        runtime = profile(name='runtime.json')
        until = time.monotonic() + 15
        while getattr(self, '_runtime_lease', None) is None:
            lease = InstanceLock(str(runtime) + '.lock')
            try:
                lease.acquire()
            except OSError:
                pass
            else:
                try:
                    if any((self.details(n) or {}).get('enabled') for n in
                           ('plugin.video.bobbi', 'plugin.video.bobbi.torrent')):
                        raise UpdateError('CINEMA_DISABLE_NOT_CONFIRMED')
                    _safe_path(runtime)
                    if runtime.exists():
                        runtime.unlink()
                    self._runtime_lease = lease
                    break
                except BaseException:
                    lease.close()
                    raise
            if self.monitor.waitForAbort(.1) or time.monotonic() >= until:
                raise UpdateError('CINEMA_SERVICE_NOT_STOPPED')
        if self.xbmc.Player().isPlaying():
            raise UpdateError('PLAYBACK_STARTED_DURING_INSTALL')

    def verify(self, versions):
        for name, version in versions.items():
            actual = self.details(name)
            if not actual or actual['version'] != version:
                raise UpdateError('COMPONENT_REGISTRATION_FAILED:' + name)
        # Registering XML alone is insufficient: check the host's real Python
        # ABI dependency and the standard RPC surface before opening cinema.
        try:
            from Crypto.Hash import SHA256
        except ImportError:
            raise UpdateError('CRYPTO_DEPENDENCY_UNUSABLE') from None
        if len(SHA256.new(b'bobbi').digest()) != 32:
            raise UpdateError('CRYPTO_DEPENDENCY_UNUSABLE')
        from .capabilities import probe
        capabilities = probe(rpc, 'kodi')
        if not capabilities.get('standard_playback'):
            raise UpdateError('PLAYER_API_UNAVAILABLE:' + ','.join(capabilities.get('errors', [])))

    def activate(self, versions):
        self.close()
        # Enable the provider/service last, after all modules have registered.
        for name in sorted(versions, key=lambda n: n == 'plugin.video.bobbi'):
            if not (self.details(name) or {}).get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
        if set(versions).issubset(self.enabled()):
            self.ensure_running()

    def restore(self, skin, enabled):
        self.close()
        # Restore the entire managed enable vector, not just its True entries.
        # Never touch unrelated addons or their origin / user settings.
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
                    pass  # A live owner may still be completing initialization.
                else:
                    lease.close()
                    # Enabled-but-never-running after process loss. The real
                    # service still checks its boot gate and exclusive lease.
                    self.xbmc.executebuiltin('RunScript(special://home/addons/plugin.video.bobbi/service.py)')
                    launched = True
            if self.monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                raise UpdateError('CINEMA_SERVICE_NOT_READY')


def recover_interactive(installer, dialog):
    """Persistent host failure must never hide rollback/exit behind recover."""
    while True:
        try:
            installer.recover()
            return True
        except (OSError, ValueError, RuntimeError):
            # Invalid journals still cannot be bypassed by a UI choice.
            try:
                state = installer._read()
            except (OSError, ValueError, RuntimeError):
                state = None
            rollback = bool(state and state['phase'] in ('activation_pending', 'complete'))
            actions = ['重试恢复'] + (['回到上一程序版本（不改账号与观看记录）'] if rollback else []) + ['退出，保留现场']
            choice = dialog.select('安装恢复尚未完成', actions, preselect=len(actions)-1)
            if choice == 0:
                continue
            if rollback and choice == 1:
                try:
                    installer.rollback()
                    return True
                except (OSError, ValueError, RuntimeError):
                    continue  # The next recovery menu remains reachable.
            return False


def choose_package(dialog, payload, first):
    embedded = str(payload) if payload and Path(payload).is_file() else None
    if embedded and first:
        return embedded
    if embedded:
        choice = dialog.select('安装来源', ['选择新的完整签名包', '使用入口内附版本'])
        if choice < 0:
            return None
        if choice == 1:
            return embedded
    return dialog.browse(1, '选择波比 CE 完整签名包', 'files', mask='.zip')


def main(payload=None):
    import xbmc
    import xbmcgui
    import xbmcvfs
    dialog = xbmcgui.Dialog()
    host = KodiHost()
    installer = Installer(xbmcvfs.translatePath('special://home/addons'),
                          profile('script.bobbi.start'), host)
    try:
        # Pending activation is runnable but still needs recovery/readback.
        if not recover_interactive(installer, dialog):
            return
        state = installer._read()
        actions = ['进入影院设置 / 登录自己的115', '安装完整签名包',
                   '回退上一次程序安装', '返回原 Kodi 界面']
        first = state is None and not host.details('plugin.video.bobbi')
        choice = 1 if first else dialog.select('波比 TV', actions)
        if choice == 1:
            selected = choose_package(dialog, payload, first)
            if not selected:
                return
            if not dialog.yesno('安装波比影院', '只安装波比程序和必要依赖，不读取旧影院账号、不改音画设置。安装完成后可用自己的手机登录115。继续？'):
                return
            installer.apply(xbmcvfs.translatePath(selected))
            dialog.ok('安装完成', '即将进入影院设置；登录115后可浏览和手动选源。原Kodi界面可从“波比开始使用”返回。')
            choice = 0
        elif choice == 2:
            if dialog.yesno('回退程序', '只恢复上一次波比程序，不覆盖账号、片库和观看记录。继续？'):
                installer.rollback()
                dialog.ok('已回退程序', '账号和观看记录保持不变。')
            return
        elif choice == 3:
            skin = (state or {}).get('previous_skin') or 'skin.estuary'
            if skin == 'skin.bobbi.cinema':
                skin = 'skin.estuary'
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})
            return
        if choice == 0:
            xbmc.executebuiltin('RunScript(script.bobbi.setup)')
    except (OSError, ValueError, RuntimeError) as error:
        xbmc.log('[bobbi-install] ' + type(error).__name__, xbmc.LOGERROR)
        dialog.ok('安装未完成', '程序安装或启用尚未完成。可重新打开“波比开始使用”恢复或重试。\n' + str(error))
    finally:
        close = getattr(host, 'close', None)
        if close:
            close()
