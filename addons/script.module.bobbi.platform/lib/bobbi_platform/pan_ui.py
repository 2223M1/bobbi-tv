"""Optional account details. Only implemented actions are offered as actions."""
from pathlib import Path
import json
import re
import tempfile
from threading import Event, Thread
import time
from uuid import uuid4

from .pan_accounts import NAMES, PanError, scope
from .runtime import call
from .pan_providers import descriptor
from . import cd2_mounts


def _navigation_path(provider):
    import xbmcvfs
    from .environment import private_path
    return private_path(xbmcvfs.translatePath, 'pan-navigation-' + provider + '.json').with_name(
        'pan-navigation-' + provider + '.json')


def _navigation_frame(row):
    """Navigation hints are never a saved selected-file/play capability."""
    if type(row) is not dict or set(row) != {'parent', 'title', 'position', 'focus'}:
        raise ValueError('PAN_NAVIGATION_INVALID')
    for key, maximum in (('parent', 4096), ('title', 1024)):
        if (type(row[key]) is not str or not 0 < len(row[key]) <= maximum
                or '://' in row[key] or re.search(r'[\x00-\x1f\x7f]', row[key])):
            raise ValueError('PAN_NAVIGATION_INVALID')
    position = row['position']
    if (type(position) is not dict or not {'page', 'cursor'} <= set(position) <= {'page', 'cursor', 'continuation'}
            or type(position['page']) is not int or not 1 <= position['page'] <= 10000
            or type(position['cursor']) is not str or len(position['cursor']) > 2048
            or '://' in position['cursor'] or re.search(r'[\x00-\x1f\x7f]', position['cursor'])
            or 'continuation' in position and (type(position['continuation']) is not str
                or not re.fullmatch(r'[0-9a-f]{32}\.[0-9]{1,5}', position['continuation']))
            or type(row['focus']) is not int or not 0 <= row['focus'] <= 24):
        raise ValueError('PAN_NAVIGATION_INVALID')
    return dict(parent=row['parent'], title=row['title'], page=1, positions={1: dict(position)},
                refresh=False, focus=row['focus'])


def _load_navigation(expected):
    try:
        path = _navigation_path(expected['provider'])
        if (path.is_symlink() or not path.is_file() or path.stat().st_size > 65536
                or any(p.is_symlink() for p in path.parents)):
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if (type(data) is not dict or set(data) != {'version', 'expected', 'frames'}
                or type(data['version']) is not int or data['version'] != 1
                or data['expected'] != expected or type(data['frames']) is not list or not 1 <= len(data['frames']) <= 8):
            return None
        return [_navigation_frame(frame) for frame in data['frames']]
    except (ValueError, OSError, KeyError, TypeError, ImportError):
        return None


def _save_navigation(expected, stack):
    try:
        from .account_manager import _write
        frames = [dict(parent=f['parent'], title=f['title'], position=f['positions'][f['page']],
                       focus=f['focus']) for f in stack[-8:]]
        for frame in frames:
            _navigation_frame(frame)
        value = dict(version=1, expected=expected, frames=frames)
        if len(json.dumps(value, separators=(',', ':')).encode('utf-8')) <= 65536:
            _write(_navigation_path(expected['provider']), value)
    except (ValueError, OSError, KeyError, TypeError, ImportError):
        pass  # Optional navigation hints must not prevent cloud browsing.


def _failure(error):
    code = str(error) if isinstance(error, PanError) else ''
    if code in ('PAN_ACCOUNT_CHANGED', 'PAN_CREDENTIALS_CHANGED'):
        return '账号已变更，请重新打开此网盘。'
    if code == 'PAN_LOGIN_REQUIRED':
        return '登录已失效，请在网盘管理重新扫码。'
    if code in ('PAN_QR_EXPIRED', 'PAN_ATTEMPT_EXPIRED'):
        return '二维码已失效，请重新扫码。'
    if code == 'PAN_QR_FINISHED':
        return '本次扫码已结束，请重新打开登录。'
    if code == 'PAN_LOGIN_FAILED':
        return '本次登录未完成，已停止等待。请稍后重试。'
    if code == 'PAN_QR_EXCHANGE_FAILED':
        return '网盘未完成本次扫码授权，请重新扫码。'
    if code in ('PAN_CREDENTIALS_INVALID', 'PAN_ACCOUNT_ID_INVALID'):
        return '网盘返回的登录信息不完整，本次未替换已保存的账号。'
    if code == 'PAN_API_REJECTED':
        return '网盘未接受本次请求，请稍后重试。'
    if code == 'PAN_HTTP_REJECTED':
        return '网盘服务暂不接受连接，请稍后重试。'
    if code == 'PAN_REPLY_INVALID':
        return '网盘返回的信息无法安全识别，本次操作已停止。'
    if code == 'PAN_CHALLENGE_REQUIRED':
        return '网盘要求额外验证，请先在官方 App 完成验证，再重新扫码。'
    if code == 'PAN_CRYPTO_UNAVAILABLE':
        return '缺少登录组件，请通过影院安装入口修复组件后重试。'
    if code == 'PAN_ROUTE_REJECTED':
        return '此账号的网盘分区尚未适配，未向未知地址发送登录信息。'
    if code == 'PAN_LOGIN_BUSY':
        return '已有扫码任务，请先关闭原来的扫码窗口。'
    if code == 'PAN_FILE_CHANGED':
        return '文件已变化，请刷新目录后重新选择。'
    if code in ('PAN_PLAY_EXPIRED', 'PAN_SELECTION_CANCELLED'):
        return '本次选择已失效，请回到目录重新选择文件。'
    if code == 'PAN_PAGE_EXPIRED':
        return '此目录分页已失效，请刷新目录后重试。'
    if code == 'PAN_ITEM_TOO_LARGE':
        return '此文件信息超出本地消息上限，无法安全显示；文件未被删除。'
    if code == 'PAN_RATE_LIMITED':
        return '网盘暂时限流，请稍后重试当前位置。'
    if code == 'PAN_BUDGET_EXHAUSTED':
        return '本次读取已达到时间或调用上限，请重试当前位置。'
    return '连接或接口暂不可用，已保存的登录不会被清除。'


def _status():
    value = call('pan_status', {}, timeout=1)
    if type(value) is not dict or type(value.get('providers')) is not list:
        raise PanError('PAN_STATUS_INVALID')
    rows = value['providers']
    if (len(rows) != len(NAMES) or {r.get('provider') for r in rows if type(r) is dict} != set(NAMES)):
        raise PanError('PAN_STATUS_INVALID')
    for row in rows:
        if row['provider'] == '115':
            from .account_manager import validate_snapshot
            validate_snapshot(row['account'])
        else:
            scope(row['account'], row['provider'])
        if type(row.get('capabilities')) is not list:
            raise PanError('PAN_STATUS_INVALID')
    return rows


class _NativeLogin:
    """Thin Host IPC adapter; account authority and credentials stay in Host."""
    def __init__(self, body, expected):
        self.body, self.expected, self.phase = body, expected, 'prepare'

    def _call(self, action, body, timeout=28):
        try:
            return call(action, body, timeout=timeout)
        except PanError as error:
            phase = getattr(error, 'login_phase', None)
            if phase in ('confirm', 'exchange', 'identity'):
                self.phase = phase
            raise

    def begin(self):
        value = self._call('pan_login_begin', dict(self.body, expected=self.expected), timeout=20)
        self.phase = 'confirm'
        return value

    def poll(self):
        value = self._call('pan_login_poll', self.body)
        if value.get('phase') in ('confirm', 'exchange', 'identity'):
            self.phase = value['phase']
        if value.get('state') in ('failed', 'account_changed', 'cancelled'):
            raise PanError({'failed': 'PAN_LOGIN_FAILED', 'account_changed': 'PAN_ACCOUNT_CHANGED',
                            'cancelled': 'PAN_QR_FINISHED'}[value['state']])
        return value

    def commit(self):
        return call('pan_login_commit', self.body)


def _cancel_async(action, body):
    """Close UI first; receipt processing has a strict local 50ms budget.

    A late worker may finish the IPC but never touches windows or temporary QR
    files. Management re-reads Host status, so no stale receipt revives a UI.
    """
    done, job = Event(), {}
    def cancel():
        try:
            job['result'] = call(action, body, timeout=3)
        except Exception:
            # Cancellation is best-effort; never print an unknown worker error
            # that could contain transport URLs or credentials.
            pass
        finally:
            done.set()
    Thread(target=cancel, name='bobbi-pan-cancel', daemon=True).start()
    done.wait(.05)
    return job.get('result')


def login(row, dialog):
    import xbmc
    import xbmcvfs
    from .account_dialog import create, render_qr, failure_details, safe_close
    from .login_flow import LoginRunner, LoginFlowError
    from .environment import private_path
    from .cloud_ui import _refresh_account_view
    provider = row['provider']
    expected = scope(row['account'], provider)
    attempt = uuid4().hex
    body = dict(provider=provider, attempt=attempt)
    monitor, window, committed, started, runner = xbmc.Monitor(), None, False, False, None
    adapter = _NativeLogin(body, expected)
    root = private_path(xbmcvfs.translatePath, 'pan-accounts-v1.json').parent
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bobbi-pan-qr-', dir=str(root)) as directory:
        try:
            instruction = ('用微信或「123 云盘」App 扫码' if provider == '123'
                           else '用「' + NAMES[provider] + '」App 扫码')
            image = Path(directory) / 'login.png'
            window = create('', '登录 ' + NAMES[provider], instruction)
            window.message = '正在准备二维码，可按返回取消。'
            window.show()
            # Mark before IPC. A lost begin reply still has a known cancel ID.
            started = True
            runner = LoginRunner(window, monitor)
            committed = runner.run(adapter, lambda state: render_qr(window, image, state))
            if committed:
                safe_close(window)
                _refresh_account_view()
                dialog.ok('已保存 ' + NAMES[provider] + ' 登录',
                          ('登录信息已保存，可打开“我的文件”。目录和播放会在使用时分别验证。'
                           if 'list_files' in row.get('capabilities', []) else
                           '目录访问仍需接通该网盘的验证流程。') +
                          ('' if 'personal_play' in row.get('capabilities', []) else
                           '原文件播放尚未接入当前选源流程，不能据此判断播放可用。'))
                return True
        except Exception as error:
            safe_close(window)
            # A UI boundary, not an error dump: unknown failures get only the
            # fixed fallback, never exception messages or upstream bodies.
            message = ('二维码已失效，请重新扫码。' if isinstance(error, LoginFlowError) and error.code == 'EXPIRED'
                       else _failure(error))
            detail = '\n' + failure_details(runner, error, provider) if runner is not None else ''
            dialog.ok('未确认登录结果', message + detail + '\n请在网盘管理确认当前状态。')
        finally:
            try:
                safe_close(window)
            finally:
                if started and not committed:
                    reply = _cancel_async('pan_login_cancel', body)
                    if reply is not None and reply.get('state') == 'committed':
                        _refresh_account_view()
                        dialog.ok('登录已保存', '取消前后台已经完成保存，请在网盘管理确认当前账号。')
    return False


def _read_directory(body, title, monitor):
    """Cancellable UI wait. Worker only returns data; late replies cannot navigate."""
    import xbmcgui
    done, job = Event(), {}
    body = dict(body, operation_id=uuid4().hex)
    def read():
        try:
            job['result'] = call('pan_list_files', body, timeout=28)
        except Exception as error:
            job['error'] = error
        finally:
            done.set()
    worker = Thread(target=read, name='bobbi-pan-directory', daemon=True)
    worker.start()
    started, progress = time.monotonic(), None
    try:
        while not done.wait(.05):
            if monitor.abortRequested() or progress is not None and progress.iscanceled():
                return None
            elapsed = time.monotonic() - started
            if elapsed >= 29:
                raise PanError('PAN_NETWORK_ERROR')
            if elapsed >= .15 and progress is None:
                progress = xbmcgui.DialogProgress()
                progress.create('正在读取 · ' + title, '可按返回取消，不影响已保存的登录。')
        if monitor.abortRequested() or progress is not None and progress.iscanceled():
            return None
        if 'error' in job:
            raise job['error']
        return job['result']
    finally:
        if progress is not None:
            progress.close()
        if not done.is_set():
            _cancel_async('pan_cancel_operation', dict(expected=body['expected'], operation_id=body['operation_id']))


def browse(row, dialog):
    import xbmc
    expected = scope(row['account'], row['provider'], authenticated=True)
    monitor = xbmc.Monitor()
    layout = descriptor(row['provider'])
    def frame(parent, title):
        return dict(parent=parent, title=title, page=1,
                    positions={1: dict(page=1, cursor='')}, refresh=False, focus=0)
    stack = _load_navigation(expected) or [frame(row.get('root', layout.root), NAMES[row['provider']])]
    while stack and not monitor.abortRequested():
        current = stack[-1]
        parent, title, page = current['parent'], current['title'], current['page']
        try:
            position = current['positions'][page]
            body = dict(expected=expected, parent=parent, page=position['page'])
            if row.get('pagination', layout.pagination) == 'cursor':
                body['cursor'] = position['cursor']
            if position.get('continuation'):
                body['continuation'] = position['continuation']
            if current['refresh']:
                body['refresh'] = True
            result = _read_directory(body, title, monitor)
            if result is None:
                return  # User cancelled; an in-flight read has no UI authority.
            current['refresh'] = False
            items = result['items']
            labels = [('文件夹 · ' if item['directory'] else '') + item['name'] for item in items]
            actions = []
            if result['has_more']:
                labels.append('下一页')
                actions.append('next')
            if page > 1:
                labels.append('上一页')
                actions.append('previous')
            labels.append('刷新当前目录')
            actions.append('refresh')
            labels.append('将此目录加入片库')
            actions.append('catalog')
            choice = dialog.select(title + (' · 目录为空' if not items else ' · 第 %d 页' % page),
                                   labels, preselect=current['focus'])
            if choice >= 0:
                current['focus'] = choice
            _save_navigation(expected, stack)
            if choice < 0 or choice >= len(labels):
                stack.pop()
                if stack:
                    _save_navigation(expected, stack)
            elif choice < len(items):
                item = items[choice]
                if item['directory']:
                    stack.append(frame(item[row.get('parent_field', layout.parent_field)], item['name']))
                else:
                    from .pan_stream import EXTENSIONS
                    if ('personal_play' in row.get('capabilities', [])
                            and item['name'].rsplit('.', 1)[-1].lower() in EXTENSIONS):
                        action = dialog.select(item['name'], ['播放原文件', '查看文件信息'])
                        if action == 0:
                            result = call('pan_prepare_play', dict(expected=expected, selected=item))
                            ticket = result.get('ticket')
                            if type(ticket) is not str or len(ticket) != 32 or any(c not in '0123456789abcdef' for c in ticket):
                                raise PanError('PAN_REPLY_INVALID')
                            xbmc.executebuiltin('RunPlugin(plugin://plugin.video.bobbi/?action=pan_play&ticket=' + ticket + ')')
                            return True
                        if action != 1:
                            continue
                    detail = ('手选原文件播放，不自动匹配作品、转存或切换其他源。'
                              if 'personal_play' in row.get('capabilities', []) else
                              '当前仅开放浏览，播放接入尚未完成。')
                    dialog.ok('文件信息', item['name'] + '\n大小 %d 字节\n' % item['size'] + detail)
            else:
                action = actions[choice - len(items)]
                if action == 'next':
                    current['positions'][page + 1] = (
                        dict(position, continuation=result['continuation']) if result.get('continuation') else
                        dict(page=position['page'] + 1, cursor=result.get('next_cursor', '')))
                    current['page'] += 1
                    current['focus'] = 0
                elif action == 'previous':
                    current['page'] -= 1
                    current['focus'] = 0
                elif action == 'catalog':
                    from .catalog_ui import add_directory
                    add_directory(expected, parent)
                else:
                    # A refreshed marker sequence starts at page one; old
                    # cursors must never skip/duplicate a modified directory.
                    current.update(page=1, positions={1: dict(page=1, cursor='')}, refresh=True, focus=0)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
            if monitor.abortRequested():
                return
            code = str(error) if isinstance(error, PanError) else ''
            if code == 'PAN_PAGE_EXPIRED':
                if dialog.select('目录分页已失效 · ' + title, ['刷新目录', '返回网盘管理']) == 0:
                    current.update(page=1, positions={1: dict(page=1, cursor='')}, refresh=True, focus=0)
                    continue
                return
            if isinstance(error, OSError) or code in ('PAN_NETWORK_ERROR', 'PAN_OPERATION_BUSY', 'PAN_RATE_LIMITED', 'PAN_BUDGET_EXHAUSTED'):
                choice = dialog.select('连接暂不可用 · ' + title,
                    ['重试当前位置', '返回上级目录', '返回网盘管理'])
                if choice == 0:
                    continue  # Preserve folder, page, cursor and focused item.
                if choice == 1:
                    stack.pop()
                    continue
                return
            dialog.ok('目录暂不可用', _failure(error))
            return


def choose_files(dialog):
    """Direct personal files, separate from account setup."""
    try:
        mounted = bool(cd2_mounts.discover())
        rows = [r for r in _status() if 'list_files' in r['capabilities'] and r['account']['authenticated']]
        if mounted:
            labels = ['使用已有 CD2 网盘 · 无需扫码'] + [NAMES[r['provider']] + ' · 原生登录' for r in rows]
            labels.append('原生网盘登录 / 管理')
            choice = dialog.select('我的网盘文件', labels)
            if not 0 <= choice < len(labels):
                return
            if choice == 0:
                from .library_ui import open_existing_cd2
                return open_existing_cd2(dialog)
            if choice == len(labels) - 1:
                return manage(dialog)
            return browse(rows[choice - 1], dialog)
        if not rows:
            return manage(dialog)
        choice = 0 if len(rows) == 1 else dialog.select('我的网盘文件', [NAMES[r['provider']] for r in rows])
        if 0 <= choice < len(rows):
            return browse(rows[choice], dialog)
    except (ValueError, OSError, RuntimeError) as error:
        dialog.ok('网盘暂不可用', _failure(error))
        if cd2_mounts.discover():
            from .library_ui import open_existing_cd2
            if dialog.select('原生连接不可用，已有挂载不受影响',
                    ['使用已有 CD2 网盘 · 无需扫码', '返回']) == 0:
                return open_existing_cd2(dialog)


def manage(dialog):
    import xbmc
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        mounted = bool(cd2_mounts.discover())
        try:
            all_rows = _status()
        except (ValueError, OSError, RuntimeError, KeyError, TypeError):
            dialog.ok('原生网盘后台暂不可用', '原有 115 和 CD2 入口保持不变，请稍后再试。')
            if mounted:
                from .library_ui import open_existing_cd2
                if dialog.select('已有挂载不受原生登录影响',
                        ['使用已有 CD2 网盘 · 无需扫码', '返回']) == 0:
                    return open_existing_cd2(dialog)
            return
        rows = [row for row in all_rows if row['capabilities']]
        labels = [NAMES[row['provider']] + ' · ' + ('原生登录已保存' if row['account']['authenticated'] else '原生未登录')
                  + (' · 待实机验证' if row['provider'] != '115' else '') for row in rows]
        labels.append('全部 10 类网盘的接入状态')
        if mounted:
            labels.append('使用已有 CD2 网盘 · 无需扫码')
        choice = dialog.select('原生网盘账号', labels)
        if choice < 0 or choice >= len(labels):
            return
        if mounted and choice == len(rows) + 1:
            from .library_ui import open_existing_cd2
            if open_existing_cd2(dialog):
                return True
            continue
        if choice == len(rows):
            dialog.textviewer('接入状态', '\n'.join(NAMES[r['provider']] + ' · ' +
                ('现有 115 分享播放' if r['provider'] == '115' else
                 '扫码、个人目录和手选原文件播放已接线，待实测；影视分享尚未接通' if 'personal_play' in r['capabilities'] else
                 '扫码与目录浏览已接入，待实测；播放尚未接通' if 'list_files' in r['capabilities'] else
                 '扫码已接入，待实测；目录验证与播放尚未接通' if 'qr_login' in r['capabilities'] else
                 '尚未实现') for r in all_rows) +
                '\n\n已保存登录不等于持续有效。未接入的网盘不会显示可登录或可播放按钮。'
                '\n原生登录与 CD2 / WebDAV 挂载相互独立。已有挂载可直接浏览和播放，无需在这里再次扫码；挂载存在不代表账号已验证或文件可读。'
                '\n不会自动转存或删除网盘文件。CD2 / WebDAV 挂载不计作原生支持。')
            continue
        row = rows[choice]
        if row['provider'] == '115':
            from .cloud_ui import login as existing_login
            existing_login()
            continue
        actions = [('login', '扫码登录 / 切换账号')]
        if row['account']['authenticated']:
            if 'list_files' in row['capabilities']:
                actions.append(('browse', '浏览我的文件'))
            actions.append(('logout', '退出此网盘'))
        action = dialog.select(NAMES[row['provider']], [label for _, label in actions])
        if not 0 <= action < len(actions):
            continue
        selected = actions[action][0]
        if selected == 'login':
            login(row, dialog)
        elif selected == 'browse':
            if browse(row, dialog):
                return True
        elif dialog.yesno('退出 ' + NAMES[row['provider']] + '？',
                          '仅移除此网盘在本机保存的登录，取消待登录任务；其他网盘和云端文件保留。'):
            try:
                call('pan_logout', {'expected': row['account']})
            except (ValueError, OSError, RuntimeError):
                dialog.ok('未确认退出结果', '请重新打开网盘管理查看状态。')
