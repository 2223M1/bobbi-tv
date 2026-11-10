"""Optional account details. Only implemented actions are offered as actions."""
from pathlib import Path
import base64
import tempfile
from threading import Event, Thread
import time
from uuid import uuid4

from .pan_accounts import NAMES, PanError, scope
from .runtime import call


def _failure(error):
    code = str(error) if isinstance(error, PanError) else ''
    if code in ('PAN_ACCOUNT_CHANGED', 'PAN_CREDENTIALS_CHANGED'):
        return '账号已变更，请重新打开此网盘。'
    if code == 'PAN_LOGIN_REQUIRED':
        return '登录已失效，请在网盘管理重新扫码。'
    if code in ('PAN_QR_EXPIRED', 'PAN_QR_FINISHED', 'PAN_ATTEMPT_EXPIRED'):
        return '二维码已失效，请重新扫码。'
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


def _poll_login(body, window, monitor):
    """Only the UI may commit. A late network reply has no UI authority."""
    done, job = Event(), {}
    def poll():
        try:
            job['result'] = call('pan_login_poll', body, timeout=28)
        except Exception as error:
            job['error'] = error
        finally:
            done.set()
    Thread(target=poll, name='bobbi-pan-login-poll', daemon=True).start()
    started = time.monotonic()
    while not done.wait(.05):
        if window.cancelled or monitor.abortRequested():
            return None
        if time.monotonic() - started >= 29:
            raise PanError('PAN_NETWORK_ERROR')
    if window.cancelled or monitor.abortRequested():
        return None
    if 'error' in job:
        raise job['error']
    return job['result']


def login(row, dialog):
    import xbmc
    import xbmcvfs
    from ._vendor import segno
    from .account_dialog import create
    from .environment import private_path
    from .cloud_ui import _refresh_account_view
    provider = row['provider']
    expected = scope(row['account'], provider)
    attempt = uuid4().hex
    body = dict(provider=provider, attempt=attempt)
    monitor, window, committed, started = xbmc.Monitor(), None, False, False
    root = private_path(xbmcvfs.translatePath, 'pan-accounts-v1.json').parent
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bobbi-pan-qr-', dir=str(root)) as directory:
        try:
            # Mark before IPC. A lost begin reply still has a known cancel ID.
            started = True
            state = call('pan_login_begin', dict(body, expected=expected), timeout=20)
            if state.get('state') != 'waiting':
                raise PanError('PAN_QR_UNAVAILABLE')
            image = Path(directory) / 'login.png'
            if type(state.get('qr')) is str:
                segno.make(state['qr'], micro=False).save(str(image), scale=10, border=4)
            elif type(state.get('qr_png')) is str and len(state['qr_png']) <= 10924:
                raw = base64.b64decode(state['qr_png'], validate=True)
                if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 8192:
                    raise PanError('PAN_QR_IMAGE_INVALID')
                image.write_bytes(raw)
            else:
                raise PanError('PAN_QR_UNAVAILABLE')
            instruction = ('用微信或「123 云盘」App 扫码' if provider == '123'
                           else '用「' + NAMES[provider] + '」App 扫码')
            window = create(image, '登录 ' + NAMES[provider], instruction)
            window.show()
            failures = 0
            while not window.cancelled and not monitor.abortRequested():
                for _ in range(20):
                    if window.cancelled or monitor.waitForAbort(.1):
                        break
                if window.cancelled or monitor.abortRequested():
                    break
                try:
                    state = _poll_login(body, window, monitor)
                    failures = 0
                except (ValueError, OSError, RuntimeError):
                    failures += 1
                    if failures > 2:
                        raise
                    window.set_status('连接暂不可用，正在重试。可按返回取消。')
                    continue
                # The poll may have spent time on HTTP; cancellation wins
                # before a separate commit is ever sent to the account owner.
                if state is None or window.cancelled or monitor.abortRequested():
                    break
                if state.get('state') == 'retry':
                    window.set_status('连接超时，正在重试。可按返回取消。')
                    continue
                if state.get('state') == 'ready':
                    reply = call('pan_login_commit', body)
                    committed = reply.get('state') == 'committed'
                    if not committed:
                        raise PanError('PAN_LOGIN_NOT_COMMITTED')
                    window.close()
                    _refresh_account_view()
                    dialog.ok('已保存 ' + NAMES[provider] + ' 登录',
                              ('可以浏览网盘目录。' if 'list_files' in row.get('capabilities', []) else
                               '目录访问仍需接通该网盘的验证流程。') +
                              ('可在目录中手动打开原文件，尚未实机验证；影视选源与分享接入独立。'
                               if 'personal_play' in row.get('capabilities', []) else
                               '原文件播放尚未接入当前选源流程，不能据此判断播放可用。'))
                    return True
                if state.get('state') not in ('waiting', 'polling', 'starting'):
                    raise PanError('PAN_QR_FINISHED')
                window.set_status('扫码后请在手机确认。可按返回取消。')
        except (ValueError, OSError, RuntimeError) as error:
            if window is not None:
                window.close()
            dialog.ok('未确认登录结果', _failure(error) + '\n请在网盘管理确认当前状态。')
        finally:
            if window is not None:
                window.close()
            if started and not committed:
                try:
                    reply = call('pan_login_cancel', body)
                    if reply.get('state') == 'committed':
                        _refresh_account_view()
                        dialog.ok('登录已保存', '取消前后台已经完成保存，请在网盘管理确认当前账号。')
                except (ValueError, OSError, RuntimeError):
                    # Unknown receipt is not proof of an unchanged account.
                    dialog.ok('未确认取消结果', '请在网盘管理确认状态，当前窗口不会再次提交登录。')
    return False


def _read_directory(body, title, monitor):
    """Cancellable UI wait. Worker only returns data; late replies cannot navigate."""
    import xbmcgui
    done, job = Event(), {}
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


def browse(row, dialog):
    import xbmc
    expected = scope(row['account'], row['provider'], authenticated=True)
    monitor = xbmc.Monitor()
    def frame(parent, title):
        return dict(parent=parent, title=title, page=1, cursors={1: ''}, refresh=False, focus=0)
    stack = [frame('/' if row['provider'] == 'baidu' else '0', NAMES[row['provider']])]
    while stack and not monitor.abortRequested():
        current = stack[-1]
        parent, title, page = current['parent'], current['title'], current['page']
        try:
            body = dict(expected=expected, parent=parent, page=page)
            if row['provider'] in ('aliyun', '139', 'xunlei'):
                body['cursor'] = current['cursors'][page]
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
            choice = dialog.select(title + ' · 第 %d 页' % page, labels, preselect=current['focus'])
            if choice >= 0:
                current['focus'] = choice
            if choice < 0 or choice >= len(labels):
                stack.pop()
            elif choice < len(items):
                item = items[choice]
                if item['directory']:
                    stack.append(frame(item['path'] if row['provider'] == 'baidu' else item['file_id'], item['name']))
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
                    current['cursors'][page + 1] = result.get('next_cursor', '')
                    current['page'] += 1
                    current['focus'] = 0
                elif action == 'previous':
                    current['page'] -= 1
                    current['focus'] = 0
                else:
                    # A refreshed marker sequence starts at page one; old
                    # cursors must never skip/duplicate a modified directory.
                    current.update(page=1, cursors={1: ''}, refresh=True, focus=0)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
            if monitor.abortRequested():
                return
            code = str(error) if isinstance(error, PanError) else ''
            if isinstance(error, OSError) or code in ('PAN_NETWORK_ERROR', 'PAN_OPERATION_BUSY'):
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


def manage(dialog):
    import xbmc
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        try:
            all_rows = _status()
        except (ValueError, OSError, RuntimeError, KeyError, TypeError):
            dialog.ok('原生网盘后台暂不可用', '原有 115 和 CD2 入口保持不变，请稍后再试。')
            return
        rows = [row for row in all_rows if row['capabilities']]
        labels = [NAMES[row['provider']] + ' · ' + ('已保存登录' if row['account']['authenticated'] else '未登录')
                  + (' · 待实机验证' if row['provider'] != '115' else '') for row in rows]
        labels.append('全部 10 类网盘的接入状态')
        choice = dialog.select('原生网盘账号', labels)
        if choice < 0 or choice >= len(labels):
            return
        if choice == len(rows):
            dialog.textviewer('接入状态', '\n'.join(NAMES[r['provider']] + ' · ' +
                ('现有 115 分享播放' if r['provider'] == '115' else
                 '扫码、个人目录和手选原文件播放已接线，待实测；影视分享尚未接通' if 'personal_play' in r['capabilities'] else
                 '扫码与目录浏览已接入，待实测；播放尚未接通' if 'list_files' in r['capabilities'] else
                 '扫码已接入，待实测；目录验证与播放尚未接通' if 'qr_login' in r['capabilities'] else
                 '尚未实现') for r in all_rows) +
                '\n\n已保存登录不等于持续有效。未接入的网盘不会显示可登录或可播放按钮。'
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
