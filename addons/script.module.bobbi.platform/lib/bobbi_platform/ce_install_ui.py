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
            return rpc('Addons.GetAddonDetails', {'addonid': name,
                'properties': ['version', 'enabled']})['addon']
        except RuntimeError:
            return None

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
        # Kodi disables/stops the service. Its registration is removed only in
        # host.close(). No pid guesses and no unrelated script/player stop.
        runtime = profile(name='runtime.json')
        until = time.monotonic() + 15
        while runtime.exists():
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
        # Enable the provider/service last, after all modules have registered.
        for name in sorted(versions, key=lambda n: n == 'plugin.video.bobbi'):
            if not (self.details(name) or {}).get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})

    def restore(self, skin, enabled):
        for name in enabled:
            if name in MANAGED and self.details(name):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
        if skin and skin != self.skin():
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})


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
        if blocked(installer.work):
            installer.recover()
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
        dialog.ok('安装未完成', '未切换到新影院。可重新打开“波比开始使用”恢复或重试。\n' + str(error))
