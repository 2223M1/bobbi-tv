"""Kodi-native installation UI. No SSH, HTTP control port or developer paths."""
from pathlib import Path
import errno
import os
import shutil
import ssl
import sys
import time
import uuid
import xml.etree.ElementTree as ET

from .ce_installer import Installer, MANAGED, PlaybackActive, blocked
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
        import xbmcgui
        window = xbmcgui.Window(10000)
        key = 'bobbi.install.refresh.' + uuid.uuid4().hex
        deadline = time.monotonic() + 15
        try:
            # Synchronous executebuiltin retains the Python lock on Omega.
            # An addon-stop job needs that lock while holding the invocation
            # manager lock; the GUI then cannot dispatch the waiting builtin.
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
                self.xbmc.executebuiltin('InstallAddon(%s)' % name, False)
                deadline = time.monotonic() + 15
                while True:
                    installed = self.details(name)
                    if installed and compare_versions(installed['version'], minimum) >= 0:
                        break
                    if self.monitor.waitForAbort(.1) or time.monotonic() >= deadline:
                        raise UpdateError('DEPENDENCY_UNAVAILABLE:' + name)
            if installed and not installed.get('enabled'):
                rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
                installed = self.details(name)
            if (not installed or not installed.get('enabled')
                    or compare_versions(installed['version'], minimum) < 0):
                raise UpdateError('DEPENDENCY_UNAVAILABLE:' + name)

    def check_idle(self):
        """Reject an already active player before opening an install journal."""
        if self.xbmc.Player().isPlaying():
            raise PlaybackActive('PLAYBACK_ACTIVE')

    def quiesce(self):
        # Recheck after staging: a preflight is not an exclusive playback lease.
        self.check_idle()
        if self.skin() == 'skin.bobbi.cinema':
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': 'skin.estuary'})
        from .runtime import call
        runtime = profile(name='runtime.json')
        until = time.monotonic() + 15
        # Ask an upgraded host to drain BEFORE Kodi holds its addon/service
        # locks and starts a five-second forced Python abort. Acknowledgement
        # is only acceptance; the OS lease remains the replacement barrier.
        legacy = False
        if runtime.is_file():
            try:
                status = call('status', {}, timeout=.3)
            except (OSError, ValueError, RuntimeError):
                status = None
            if isinstance(status, dict) and status.get('quiesce_protocol') == 1:
                reply = call('quiesce', {'protocol': 1}, timeout=.5)
                if reply != {'accepted': True}:
                    raise UpdateError('CINEMA_STOP_NOT_ACCEPTED')
            # Only a complete live pre-protocol reply authorizes the old Kodi
            # stop path. Missing IPC/marker can mean a modern owner is STILL
            # draining after a failed close, including across installer objects.
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
        # A registration can survive os._exit. Acquire the stable OS lease,
        # recheck disabled state, then remove only that dead host's marker.
        # Retain the lease through file replacement, until activate/restore.
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
                    try:
                        # A path RunScript has neither addon context nor a
                        # ServiceAddonManager handle. Restart only this enabled
                        # provider via a real managed state transition. Keep
                        # the lease until disabled is confirmed; an initializing
                        # old invocation cannot acquire replacement ownership.
                        name = 'plugin.video.bobbi'
                        if not (self.details(name) or {}).get('enabled'):
                            raise UpdateError('CINEMA_PROVIDER_NOT_ENABLED')
                        rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': False})
                        if (self.details(name) or {}).get('enabled'):
                            raise UpdateError('CINEMA_DISABLE_NOT_CONFIRMED')
                    finally:
                        lease.close()
                    # The transaction remains pending if enabling or readiness
                    # fails. Retrying restores its complete desired vector.
                    rpc('Addons.SetAddonEnabled', {'addonid': name, 'enabled': True})
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


def install_online(installer, host, dialog):
    """A manual online action downloads first, then reuses the offline transaction."""
    import xbmcgui
    from .online_updates import latest, Cancelled
    from .online_components import download
    host.check_idle()
    progress = xbmcgui.DialogProgress()
    selected = None
    try:
        progress.create('波比 TV · 在线更新', '正在查询最新正式版本，可取消。')
        cancelled = lambda: host.monitor.abortRequested() or progress.iscanceled()
        offer = latest(cancelled)
        state = installer._read() or {}
        watermark = max(state.get('high_watermark', 0), state.get('sequence', 0))
        progress.close()
        if offer['sequence'] <= watermark:
            dialog.ok('无需更新', '当前已安装此版本或更新的版本。需要恢复旧程序时，请使用回退入口。')
            return False
        if not dialog.yesno('安装 ' + offer['tag'].upper(),
                '整套程序约 %d MB；可复用的组件不会重复下载。保留账号与观看记录，不自动切换皮肤；播放中不会安装。继续？'
                % ((offer['size'] + 1024 * 1024 - 1) // (1024 * 1024))):
            return False
        host.check_idle()
        progress.create('波比 TV · 在线更新', '正在准备完整版本；优先复用组件，不支持时下载整包。可随时取消。')
        selected = download(offer, installer.work / 'downloads', installer.trust,
                            cancelled, lambda percent: progress.update(percent))
        if cancelled():
            return False
        host.check_idle()  # Playback may have started during the download.
        progress.close()
        installer.apply(selected)
        return True
    except Cancelled:
        return False
    finally:
        progress.close()
        if selected is not None:
            # Remove only this invocation's downloaded package, never backups.
            selected.unlink(missing_ok=True)


def failure_message(error):
    """Explain existing failures without echoing URLs, paths or server bodies."""
    code = str(error)
    if code == 'PLAYBACK_ACTIVE':
        return '请先停止播放再更新或切换界面。当前影片与已安装程序保持不变。'
    if code == 'INSTALLATION_SPACE_REQUIRED' or getattr(error, 'errno', None) == errno.ENOSPC:
        plan = getattr(error, 'space', None)
        sizes = ('需新增至少 {:.1f} MiB，当前可用 {:.1f} MiB。'.format(
            plan['required_bytes']/1024**2, plan['free_bytes']/1024**2) if plan else '')
        return sizes + '可用空间不足，可在“存储空间与更新缓存”预览并清理可重建缓存后重试。未删除程序备份、账号或媒体。'
    if isinstance(error, PermissionError) or getattr(error, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
        return '本机目录没有写入权限或处于只读状态。请检查存储设备，不要删除账号或程序备份。'
    if isinstance(getattr(error, 'reason', error), ssl.SSLError):
        return 'HTTPS 证书或安全连接检查未通过。请检查设备日期、时间和网络；也可使用完整离线包。'
    messages = {
        'STORAGE_PLAN_CHANGED': '缓存内容已变化，本次清理已停止。请重新预览再确认；程序和备份不受影响。',
        'Another update is active': '另一个安装或下载操作正在进行，请等待完成后重试。',
        'ONLINE_CANCELLED': '已取消操作。程序、备份和账号保持不变。',
        'ONLINE_TIMEOUT': '查询或下载超时。支持续传的同版断点会保留，可稍后重新检查更新，也可使用完整离线包。',
        'ONLINE_SHORT_READ': '下载不完整，未安装这个包。支持续传的同版断点会保留，可重试或使用完整离线包。',
        'ONLINE_LENGTH_INVALID': '下载长度与发布信息不匹配，未安装这个包。请重新检查更新或下载完整离线包。',
        'ONLINE_CONTENT_INVALID': '下载内容不匹配，未安装这个包。请重新检查更新或下载完整离线包。',
        'ONLINE_GENERATION_MISMATCH': '下载包与更新索引的版本不一致，未安装。请稍后重新检查更新。',
        'ONLINE_PACKAGE_INVALID': '安装包格式不完整，未安装。请重新下载完整安装包。',
        'ONLINE_RANGE_INVALID': '服务返回的续传范围或版本标记不一致，已放弃本次下载。可重新检查更新，现有程序没有改变。',
        'ONLINE_DOWNLOAD_BUSY': '另一个更新入口正在下载，请先关闭它或等待完成；本次没有重复下载或安装。',
        'ONLINE_CACHE_PATH_INVALID': '更新临时目录不是普通文件，未改动该目录。可使用完整离线包安装。',
        'ONLINE_OFFER_INVALID': '更新信息暂不可用。请稍后重试，也可从国内下载页获取完整离线包。',
        'ONLINE_RESPONSE_INVALID': '下载服务没有返回正常的安装内容。请稍后重试或使用完整离线包。',
        'ONLINE_REDIRECT_REJECTED': '下载地址不在当前支持的发布通道中。请使用项目下载页的完整离线包。',
        'GENERATION_NOT_NEWER': '所选完整包不是更新版本。需要恢复旧程序时，请使用回退入口。',
        'NO_PREVIOUS_PROGRAM_GENERATION': '本机没有可回退的上一程序版本。已有账号与观看记录未改变。',
    }
    if code in messages:
        return messages[code]
    if isinstance(error, UpdateError) and ('signature' in code or code.startswith('Offline ')):
        return '完整安装包校验未通过。请从项目下载页重新下载，不要修改或混装包内组件。'
    return ('网络连接或下载未完成；支持续传的同版断点会保留，可稍后重试，也可使用完整离线包。'
            if isinstance(error, OSError) or code.startswith('ONLINE_') else
            '程序安装或启用尚未完成。可重新打开“波比开始使用”恢复或重试。')


def main(payload=None, online=False, storage=False):
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
        actions = ['进入影院设置 / 登录自己的115', '安装本地完整包',
                   '回退上一次程序安装', '返回原 Kodi 界面', '在线检查并安装最新正式版', '存储空间与更新缓存']
        first = state is None and not host.details('plugin.video.bobbi')
        choice = 5 if storage else (4 if online or (first and not (payload and Path(payload).is_file())) else (
            1 if first else dialog.select('波比 TV', actions)))
        if choice == 5:
            from .ce_storage import show
            show(installer, host, dialog)
            return
        if choice == 4:
            if not install_online(installer, host, dialog):
                return
            dialog.ok('安装完成', '即将进入影院设置。账号和观看记录保持不变；更新后请重启 Kodi。')
            choice = 0
        if choice == 1:
            selected = choose_package(dialog, payload, first)
            if not selected:
                return
            from .ce_storage import plan_text, require_space
            selected = xbmcvfs.translatePath(selected)
            plan = installer.plan_space(selected)
            require_space(plan)
            if not dialog.yesno('安装波比影院', plan_text(plan) + '\n只安装程序和必要依赖，不改账号与音画设置。继续？'):
                return
            installer.apply(selected)
            dialog.ok('安装完成', '账号、片库与观看记录保留；更新后请重启 Kodi。\n'
                      '即将进入设置；115 可扫码登录，本地与 NAS 不需要网盘账号。')
            choice = 0
        elif choice == 2:
            if dialog.yesno('回退程序', '只恢复上一次波比程序，不覆盖账号、片库和观看记录。继续？'):
                installer.rollback()
                dialog.ok('已回退程序', '账号和观看记录保持不变。请重启 Kodi 后再开始观影。')
            return
        elif choice == 3:
            host.check_idle()
            skin = (state or {}).get('previous_skin') or 'skin.estuary'
            if skin == 'skin.bobbi.cinema':
                skin = 'skin.estuary'
            rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin})
            return
        if choice == 0:
            xbmc.executebuiltin('RunScript(script.bobbi.setup)')
    except (OSError, ValueError, RuntimeError) as error:
        xbmc.log('[bobbi-install] ' + type(error).__name__, xbmc.LOGERROR)
        if str(error) in ('PREVIOUS_PROGRAM_INCOMPLETE', 'PREVIOUS_PROGRAM_SPECIAL_FILE', 'PREVIOUS_PROGRAM_RECEIPT_REQUIRED'):
            dialog.ok('暂不能回退', '旧程序备份不完整，或来自没有完整性记录的旧安装器。已拒绝不完整回退并保留现场，请保留备份并使用完整安装包恢复。')
        else:
            dialog.ok('操作未完成', failure_message(error))
    finally:
        close = getattr(host, 'close', None)
        if close:
            close()
