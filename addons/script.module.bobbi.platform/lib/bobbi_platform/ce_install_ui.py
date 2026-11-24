"""Kodi-native installation UI. No SSH, HTTP control port or developer paths."""
from pathlib import Path
import errno
import os
import re
import shutil
import ssl
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from zipfile import BadZipFile

from .ce_installer import Installer, MANAGED, PlaybackActive, blocked, installed_watermark
from .kodi import rpc
from .paths import profile
from .updates import UpdateError, _safe_path
from .upstream_addons import UPSTREAM_COMPONENTS, compare_versions


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
        needs = {name: set() for name in minimums}
        for name in MANAGED | UPSTREAM_COMPONENTS:
            for dep in ET.parse(staged / name / 'addon.xml').findall('./requires/import'):
                key = dep.get('addon')
                if dep.get('optional') == 'true':
                    continue
                if key in minimums and compare_versions(dep.get('version', '0.0.0'), minimums[key]) > 0:
                    minimums[key] = dep.get('version', '0.0.0')
                if name in needs and key in needs:
                    needs[name].add(key)
        # On an empty Kodi profile a module may be auto-disabled (or fail to
        # enable) until its own imports are installed. Alphabetical order
        # attempts requests before urllib3. Validate the signed graph BEFORE
        # any copying, and leave existing repository origins/versions alone.
        order = []
        while needs:
            ready = sorted(name for name, parents in needs.items() if not parents)
            if not ready:
                raise UpdateError('DEPENDENCY_GRAPH_INVALID')
            for name in ready:
                del needs[name]
            for parents in needs.values():
                parents.difference_update(ready)
            order.extend(ready)
        for name in order:
            minimum = minimums[name]
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
        if rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': target}) is not True:
            raise UpdateError('INSTALL_SKIN_NOT_CONFIRMED')
        # On Omega SetSettingValue posts ReloadSkin(confirm). The setting changes
        # BEFORE the GUI loads; declining or timing out reverts it ten seconds
        # later. Never press Yes on behalf of the user (or on another dialog).
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

    def quiesce(self):
        # Recheck after staging: a preflight is not an exclusive playback lease.
        self.check_idle()
        if self.skin() == 'skin.bobbi.cinema':
            self.prepare_install_skin()  # Also covers recovery of older journals.
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
                try:
                    reply = call('quiesce', {'protocol': 1}, timeout=1)
                except OSError:
                    # A lost reply can follow a real drain. Reconcile through
                    # the same exclusive OS lease below; never send it again.
                    pass
                else:
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
        check_host_crypto()
        from .capabilities import probe
        capabilities = probe(rpc, 'kodi')
        if not capabilities.get('standard_playback'):
            raise UpdateError('PLAYER_API_UNAVAILABLE:' + ','.join(capabilities.get('errors', [])))

    def activate(self, versions):
        self.close()
        # Enable the provider/service last, after all modules have registered.
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


def recover_interactive(installer, dialog, report=None):
    """Persistent host failure must never hide rollback/exit behind recover."""
    while True:
        try:
            installer.recover()
            return True
        except (OSError, ValueError, RuntimeError) as error:
            if report:
                report('recover', error)
            # Invalid journals still cannot be bypassed by a UI choice.
            try:
                state = installer._read()
            except (OSError, ValueError, RuntimeError):
                state = None
            rollback = bool(state and state['phase'] in ('activation_pending', 'complete'))
            actions = ['重试恢复'] + (['恢复上一版本（保留个人数据）'] if rollback else []) + ['退出，稍后处理']
            choice = dialog.select('安装未完成', actions, preselect=len(actions)-1)
            if choice == 0:
                continue
            if rollback and choice == 1:
                try:
                    installer.rollback()
                    return True
                except (OSError, ValueError, RuntimeError) as error:
                    if report:
                        report('rollback', error)
                    continue  # The next recovery menu remains reachable.
            return False


def choose_package(dialog, payload, first):
    embedded = str(payload) if payload and Path(payload).is_file() else None
    if embedded and first:
        return embedded
    if embedded:
        choice = dialog.select('安装来源', ['选择完整安装包', '使用内附版本'])
        if choice < 0:
            return None
        if choice == 1:
            return embedded
    return dialog.browse(1, '选择波比 TV 完整安装包', 'files', mask='.zip')


def install_online(installer, host, dialog):
    """A manual online action downloads first, then reuses the offline transaction."""
    import xbmcgui
    from .online_updates import latest, Cancelled, selected_track
    from .online_components import download
    host.check_idle()
    progress = xbmcgui.DialogProgress()
    selected = None
    try:
        progress.create('波比 TV 更新', '正在检查更新，可取消。')
        cancelled = lambda: host.monitor.abortRequested() or progress.iscanceled()
        track, mirrors = selected_track(installer.work), {}
        offer = latest(cancelled, track=track, report=mirrors)
        state = installer._read() or {}
        watermark = installed_watermark(state)
        progress.close()
        if offer['sequence'] <= watermark:
            dialog.ok('无需重复更新', ('稳定版尚未追上已安装版本，等待同轨道后续更新；不会自动降级。\n'
                if track == 'stable' and offer['sequence'] < watermark else '') +
                '此版本或更新版本已安装过。需要恢复时，请选择“恢复上一版本”或“选择恢复版本”。')
            return False
        dialog.textviewer('更新版本', '轨道 {}\n已装 {}\n候选 {}\n镜像 {}'.format(
            '稳定版' if track == 'stable' else '预览版', state.get('sequence', '未安装'), offer['tag'].upper(),
            {'synchronized': '已同步', 'out-of-sync': '尚未同步，使用较新版本',
             'unavailable': '部分不可用，使用已核实镜像'}.get(mirrors.get('mirrors'), '未报告')))
        if not dialog.yesno('安装 ' + offer['tag'].upper(),
                '完整安装包约 %d MB，已有组件可复用。若 Kodi 询问是否保持临时皮肤，请选“是”。账号与观看记录保留。继续安装？'
                % ((offer['size'] + 1024 * 1024 - 1) // (1024 * 1024))):
            return False
        host.check_idle()
        progress.create('波比 TV 更新', '正在下载更新，已有组件会复用。可随时取消。')
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


def failure_message(error, stage=None):
    """Explain existing failures without echoing URLs, paths or server bodies."""
    code = str(error)
    if code.startswith(('DEPENDENCY_UNAVAILABLE:', 'DEPENDENCY_ENABLE_FAILED:')):
        return 'Kodi 未能启用所需依赖。请检查下方组件，再打开“开始使用”。'
    if code.startswith('COMPONENT_ENABLE_FAILED:') or code == 'HOST_ACTIVATION_NOT_CONFIRMED':
        return '影院组件尚未启用。请重新打开“开始使用”恢复，不用删除数据。'
    if code.startswith(('ADDON_STATE_UNKNOWN:', 'COMPONENT_REGISTRATION_FAILED:')) or code == 'ADDON_REFRESH_NOT_CONFIRMED':
        return 'Kodi 未确认组件已登记。请重启 Kodi，再打开“开始使用”恢复；不用删除个人数据。'
    if code == 'CRYPTO_DEPENDENCY_UNUSABLE':
        return 'Kodi 的 PyCryptodome 模块不可用。请用本机 Kodi 仓库修复对应架构的依赖，再重试。'
    if code.startswith('PLAYER_API_UNAVAILABLE:'):
        return '当前 Kodi 未提供所需播放接口，请核对 CoreELEC 和 Kodi 版本。'
    if code == 'CINEMA_SERVICE_NOT_READY':
        return '影院服务未就绪。请重启 Kodi 后打开“开始使用”恢复，无需重新登录。'
    if code == 'INSTALL_SKIN_NOT_CONFIRMED':
        return 'Kodi 未保留临时界面。重新开始安装，在 Kodi 的“保持皮肤？”弹窗中选“是”。'
    if code == 'CINEMA_SERVICE_NOT_STOPPED':
        return '旧播放服务尚未退出，未取得替换许可。请停止播放，重启 Kodi 后从“开始使用”恢复。'
    if isinstance(error, BadZipFile):
        return 'ZIP 文件不完整，请重新下载文件名以 script.bobbi.start- 开头的完整安装包。'
    if code == 'PLAYBACK_ACTIVE':
        return '请先停止播放，再更新程序或切换界面。'
    if code == 'INSTALLATION_SPACE_REQUIRED' or getattr(error, 'errno', None) == errno.ENOSPC:
        plan = getattr(error, 'space', None)
        sizes = ('需新增至少 {:.1f} MiB，当前可用 {:.1f} MiB。'.format(
            plan['required_bytes']/1024**2, plan['free_bytes']/1024**2) if plan else '')
        return sizes + '空间不足，请到“存储空间与清理”查看可清理内容。'
    if isinstance(error, PermissionError) or getattr(error, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
        return '无法写入存储设备，请检查空间和写入权限，勿删除账号或程序备份。'
    if isinstance(getattr(error, 'reason', error), ssl.SSLError):
        return '无法建立安全连接，请检查设备时间和网络，或使用完整离线包。'
    messages = {
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
    if code in messages:
        return messages[code]
    if isinstance(error, UpdateError) and ('signature' in code or code.startswith('Offline ')):
        return '安装包校验失败，请从项目下载页重新下载完整包。'
    return ('下载未完成，请检查网络后重试，或使用完整离线包。可续传的进度已保留。'
            if (isinstance(error, OSError) and stage in (None, 'online')) or code.startswith('ONLINE_') else
            '安装未完成，请重新打开“波比 TV · 开始使用”恢复或重试。')


def diagnosis(stage, error):
    """One line shared by the television and Kodi log. Never echo an exception."""
    where = {'init': '初始化', 'font': '界面字体', 'recover': '恢复安装', 'menu': '读取状态',
             'storage': '存储预检', 'online': '在线更新', 'apply': '安装组件', 'rollback': '恢复程序',
             'settings': '进入设置', 'validate': '校验安装包'}.get(stage, '安装')
    reason, _, detail = str(error).partition(':')
    # An exception string can contain URLs, account details or paths. Only
    # product-owned codes, reviewed addon IDs and our own frame names get out.
    known = {'DEPENDENCY_UNAVAILABLE', 'DEPENDENCY_ENABLE_FAILED', 'DEPENDENCY_GRAPH_INVALID',
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
    if reason in known:
        code = reason
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
    component = detail if reason in known and detail in MANAGED | UPSTREAM_COMPONENTS | {'script.module.pycryptodome'} else ''
    tb = error.__traceback__
    frame = ''
    while tb:
        source = Path(tb.tb_frame.f_code.co_filename).stem
        if source in {'ce_installer','ce_install_ui','ce_recovery','ce_storage','kodi','updates',
                      'offline_updates','catalog_compatibility','online_updates','upstream_addons'}:
            frame = f'{source}:{tb.tb_lineno}'
        tb = tb.tb_next
    return ' · '.join(v for v in (where, code, component, frame) if v)


def readable_text(host, dialog):
    """Offer Kodi's existing Unicode font before Chinese-only stock dialogs."""
    if host.skin() != 'skin.estuary':
        return True
    if rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.font'}).get('value') != 'Default':
        return True
    host.check_idle()
    if not dialog.yesno('Display Chinese text',
            'Bobbi TV uses Chinese menus. Enable the built-in Arial font so they are readable? '
            'This changes only the interface font, not video subtitles. Choose No to exit.'):
        return False
    host.check_idle()
    changed = rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.font', 'value': 'Arial'})
    actual = rpc('Settings.GetSettingValue', {'setting': 'lookandfeel.font'}).get('value')
    if changed is not True or actual != 'Arial':
        dialog.ok('Font not changed', 'Open Settings > Interface > Skin > Fonts, select Arial, then open Bobbi TV again.')
        return False
    return True


def main(payload=None, online=False, storage=False):
    import xbmc
    from .android_ui import bundled_host, start
    if bundled_host():
        return start(online=online, storage=storage)
    import xbmcgui
    import xbmcvfs
    dialog = xbmcgui.Dialog()
    host = None
    from .optimization import observe
    from .paths import profile_root
    diagnostic_root = None
    started = time.monotonic()
    stage = 'init'
    def report(step, error):
        if diagnostic_root is not None:
            observe(diagnostic_root, {'online':'update','rollback':'rollback'}.get(step,'install'),
                    'space' if str(error).partition(':')[0] == 'INSTALLATION_SPACE_REQUIRED' else 'failed', started)
        line = diagnosis(step, error)
        try:
            import xbmcaddon
            version = xbmcaddon.Addon('script.bobbi.start').getAddonInfo('version')
            kodi_version = re.match(r'^[0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]{1,2})?', xbmc.getInfoLabel('System.BuildVersion'))
            if isinstance(version, str) and re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}', version) and kodi_version:
                line += ' · ZIP ' + version + ' / Kodi ' + kodi_version[0]
        except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
            pass  # A failed version lookup cannot hide the original fault.
        if hasattr(xbmc, 'log'):
            xbmc.log('[bobbi-install] ' + line, xbmc.LOGERROR)
        if hasattr(dialog, 'ok'):
            old = str(error) in ('PREVIOUS_PROGRAM_INCOMPLETE', 'PREVIOUS_PROGRAM_SPECIAL_FILE', 'PREVIOUS_PROGRAM_RECEIPT_REQUIRED')
            message = ('旧备份不完整或缺少核对记录。请保留备份，改用完整安装包恢复。' if old
                       else failure_message(error, step))
            dialog.ok('无法恢复旧版' if old else '操作未完成', message + '\n诊断（可拍照） ' + line)
    try:
        host = KodiHost()
        try:
            diagnostic_root = profile_root()
        except (ValueError, OSError, RuntimeError, AttributeError, ImportError):
            pass
        installer = Installer(xbmcvfs.translatePath('special://home/addons'),
                              profile('script.bobbi.start'), host)
        stage = 'font'
        if not readable_text(host, dialog):
            return
        # Pending activation is runnable but still needs recovery/readback.
        stage = 'recover'
        if not recover_interactive(installer, dialog, report):
            return
        stage = 'menu'
        state = installer._read()
        actions = ['影院设置', '安装本地完整包',
                   '恢复上一版本', '返回 Kodi 界面', '检查在线更新', '存储空间与清理',
                   '选择恢复版本', '更新轨道（稳定版 / 预览版）']
        first = state is None and not host.details('plugin.video.bobbi')
        choice = 5 if storage else (4 if online or (first and not (payload and Path(payload).is_file())) else (
            1 if first else dialog.select('波比 TV', actions)))
        if choice == 7:
            from .online_updates import selected_track, TRACKS
            current = selected_track(installer.work)
            selected = dialog.select('更新轨道', ['稳定版（默认）', '预览版（测试）'], preselect=TRACKS.index(current))
            if selected in (0, 1) and (selected == 0 or dialog.yesno('使用预览版？',
                    '预览版可能有未验证功能。切回稳定版不会自动降级。继续？')):
                selected_track(installer.work, TRACKS[selected])
            return
        if choice == 6:
            stage = 'rollback'
            from .ce_recovery import show
            if show(installer, host, dialog):
                dialog.ok('版本已恢复', '请重启 Kodi 后再观看，账号与观看记录保留。')
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
            dialog.ok('安装完成', '账号与观看记录保留。即将进入设置，观看前请重启 Kodi。')
            choice = 0
        if choice == 1:
            stage = 'validate'
            selected = choose_package(dialog, payload, first)
            if not selected:
                return
            from .ce_storage import plan_text, require_space
            selected = xbmcvfs.translatePath(selected)
            plan = installer.plan_space(selected)
            require_space(plan)
            dialog.textviewer('安装所需空间', plan_text(plan))
            host.check_idle()
            if not dialog.yesno('安装波比影院',
                    '预计需新增至少 {:.1f} MiB，当前可用 {:.1f} MiB。\n'
                    '账号与音画设置保留。若 Kodi 询问是否保持临时皮肤，请选“是”。继续安装？'.format(
                        plan['required_bytes']/1024**2, plan['free_bytes']/1024**2)):
                return
            stage = 'apply'
            installer.apply(selected)
            if diagnostic_root is not None:
                observe(diagnostic_root, 'install', 'ok', started)
            dialog.ok('安装完成', '账号、片库与观看记录保留。即将进入设置，观看前请重启 Kodi。')
            choice = 0
        elif choice == 2:
            stage = 'rollback'
            if dialog.yesno('恢复上一版本？', '仅恢复程序，账号、片库与观看记录保留。完成后需重启 Kodi。'):
                installer.rollback()
                dialog.ok('版本已恢复', '请重启 Kodi 后再观看，账号与观看记录保留。')
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
        # Last presentation boundary: the transaction owns recovery. Unexpected
        # exceptions must be photographable too, never hide a shutdown/exit.
        report(stage, error)
    finally:
        close = getattr(host, 'close', None)
        if close:
            close()
