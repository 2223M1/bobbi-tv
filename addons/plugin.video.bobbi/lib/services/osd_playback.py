"""OSD client of the resident playback projection, not another player owner.

Window properties carry presentation/captured commands only. The resident actor
validates every expected scope. Missing capability is never native permission.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import re
import time
from uuid import uuid4

from bobbi_core.playback_presentation import command, expected

PENDING = 'Bobbi.OSD.Pending'
STREAM_PANEL = 'Bobbi.OSD.StreamPanel'
NATIVE_MODES = ('external', 'standard')
FINAL = ('applied', 'rejected', 'failed')


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode()


def decode(value):
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError('OSD_CAPTURE_INVALID')
    result = json.loads(base64.b64decode(value, altchars=b'-_', validate=True))
    if type(result) is not dict:
        raise ValueError('OSD_CAPTURE_INVALID')
    return result


class Client:
    def __init__(self, call, window, pending_key=PENDING, lock_path=None):
        self.call, self.window = call, window
        self.pending_key, self.lock_path = pending_key, lock_path

    def read(self):
        try:
            view = self.call(dict(operation='playback_presentation', include_owner=True))
            if type(view) is dict:
                if view.get('mode') in NATIVE_MODES and view.get('available') is False:
                    return view
                if view.get('mode') == 'managed' and view.get('available') is True:
                    expected(view.get('expected'))
                    if (any(type(view.get(key)) is not bool for key in ('can_seek', 'subtitle_visible'))
                            or any(type(view.get(key)) is not int or not 0 <= view[key] <= 864000000
                                   for key in ('position_ms', 'duration_ms'))
                            or any(type(view.get(key)) is not list for key in ('audio', 'subtitles', 'chapters'))):
                        raise ValueError('OSD_PROJECTION_INVALID')
                    return view
        except (OSError, RuntimeError, ValueError, TypeError):
            pass
        return dict(available=False, mode='unavailable')

    @staticmethod
    def capture(view, action, params):
        return command(dict(expected=deepcopy(view['expected']), command_id=uuid4().hex,
                            action=action, params=deepcopy(params)))

    def receipt(self, original):
        try:
            reply = self.call(dict(operation='playback_receipt',
                expected=original['expected'], command_id=original['command_id']))
            if (type(reply) is dict and reply.get('command_id') == original['command_id']
                    and reply.get('status') in FINAL + ('queued', 'unknown')):
                return reply
        except (OSError, RuntimeError, ValueError, TypeError):
            pass
        return dict(command_id=original['command_id'], status='unknown')

    def reconcile_pending(self):
        """Under the OSD lock, query the original even after its player exits."""
        pending = self.window.getProperty(self.pending_key)
        if not pending:
            return
        try:
            original = command(decode(pending))
        except (ValueError, TypeError, KeyError):
            return dict(status='unknown')
        reply = self.receipt(original)
        if (reply['status'] in FINAL
                and self.window.getProperty(self.pending_key) == pending):
            self.window.clearProperty(self.pending_key)
        return reply

    def submit(self, captured):
        """Called under the OSD lock. Persist before IPC; never replay a send."""
        captured = command(captured)
        pending = self.window.getProperty(self.pending_key)
        if pending:
            try:
                previous = command(decode(pending))
            except (ValueError, TypeError, KeyError):
                return dict(status='unknown')  # Corruption is not permission to retry.
            reply = self.receipt(previous)
            if reply['status'] not in FINAL:
                # A command bound to a retired native instance cannot affect a
                # different instance. Verify this, never substitute fresh scope
                # into either command. Same-instance uncertainty stays blocked.
                fresh = self.read() if previous['expected']['native_instance'] != captured['expected']['native_instance'] else {}
                if fresh.get('available') is not True or fresh.get('expected') != captured['expected']:
                    return reply
                self.window.setProperty(self.pending_key + '.PreviousUnknown', pending)
            self.window.clearProperty(self.pending_key)
            if previous['command_id'] == captured['command_id']:
                return reply
        self.window.setProperty(self.pending_key, encode(captured))
        try:
            reply = self.call(dict(operation='playback_command', command=captured))
            if (type(reply) is not dict or reply.get('command_id') != captured['command_id']
                    or reply.get('status') not in FINAL + ('queued', 'unknown')):
                raise ValueError('OSD_REPLY_INVALID')
        except (OSError, RuntimeError, ValueError, TypeError):
            return dict(command_id=captured['command_id'], status='unknown')
        if reply['status'] in FINAL:
            self.window.clearProperty(self.pending_key)
        return reply


def client():
    from bobbi_platform.paths import profile_root
    from bobbi_platform.runtime import bind_call
    from xbmcgui import Window
    root = profile_root()
    key = PENDING + '.' + sha256(str(root).encode()).hexdigest()[:24]
    try:
        bound = bind_call(root / 'runtime.json')
        call = lambda message: bound('playback', message, timeout=.3)
    except (OSError, ValueError, TypeError):
        def call(message):
            raise OSError('OSD_RUNTIME_UNAVAILABLE')
    return Client(call, Window(10000), key, root / 'osd.lock')


def publish(view, window):
    """UI hints only; no control decision reads these mode/status properties."""
    # The skin consumes this one-use display nonce on opening. It contains no
    # playback scope or command. Seed the following visit on an existing read,
    # so Kodi need not serialise two additional Python starts for each picker.
    if not window.getProperty('Bobbi.OSD.NextStreamPanel'):
        window.setProperty('Bobbi.OSD.NextStreamPanel', uuid4().hex)
    window.setProperty('Bobbi.OSD.Mode', view['mode'])
    if view.get('available'):
        window.setProperty('AM6B.SubtitleState', view.get('subtitle_status', ''))
        window.setProperty('AM6B.AudioState', view.get('audio_status', ''))
        window.setProperty('Bobbi.OSD.Truncated', _tr(91200, '列表已截短') if any(
            view.get(key + '_truncated') for key in ('audio', 'subtitles', 'chapters')) else '')
    else:
        window.clearProperty('Bobbi.OSD.Truncated')
        window.clearProperty('AM6B.SubtitleState')
        window.clearProperty('AM6B.AudioState')


def begin_stream_panel(window, kind, visible):
    """Mint a display generation only. No player read, command or replay."""
    if kind not in ('audio', 'subtitle') or window.getProperty(STREAM_PANEL) not in ('opening', 'opening-' + kind) or not visible():
        return
    window.setProperty(STREAM_PANEL, uuid4().hex)


def stream_directory(handle, stream_type, panel=None):
    """Render captured controls without executing them or loading vendor code."""
    import xbmcplugin
    from xbmcgui import ListItem
    from bobbi_platform.kodi import rpc
    from urllib.parse import urlencode

    owner = client()
    def current_panel():
        return panel is None or (isinstance(panel, str) and re.fullmatch('[a-f0-9]{32}', panel)
                                 and owner.window.getProperty(STREAM_PANEL) == panel)
    items = []
    definitions = {'audio': ('audiostreams', 'currentaudiostream'),
                   'subtitle': ('subtitles', 'currentsubtitle')}
    definition = definitions.get(stream_type)
    try:
        if not current_panel():
            raise ValueError('OSD_PANEL_RETIRED')
        view = owner.read()
        if panel is not None:
            # Opening over AV startup can briefly have no projection. Only
            # re-read this still-open panel; never submit a player command.
            for delay in (.10, .22, .40):
                if view.get('mode') != 'unavailable' or not current_panel():
                    break
                time.sleep(delay)
                if current_panel():
                    view = owner.read()
        if not current_panel():
            raise ValueError('OSD_PANEL_RETIRED')
        publish(view, owner.window)
        rows, current = [], None
        if definition is not None:
            if view['mode'] == 'managed':
                rows = view['audio' if stream_type == 'audio' else 'subtitles']
            elif view['mode'] in NATIVE_MODES:
                from lib.services.native_streams import snapshot
                seen = snapshot(rpc, stream_type, view['mode'])
                rows, current = seen['rows'], seen['current']
            if type(rows) is not list:
                raise ValueError('OSD_PROJECTION_INVALID')
            toggle = (encode(owner.capture(view, 'subtitle_visible',
                          dict(visible=not view['subtitle_visible'])))
                      if view['mode'] == 'managed' else encode(dict(native_toggle=not seen['visible'], proof=seen['proof']))
                      if view['mode'] in NATIVE_MODES and stream_type == 'subtitle' else '')
            for row in rows:
                if type(row) is not dict or type(row.get('index')) is not int or not 0 <= row['index'] <= 255:
                    raise ValueError('OSD_PROJECTION_INVALID')
                captured = (owner.capture(view,
                    'audio_stream' if stream_type == 'audio' else 'manual_subtitle_stream',
                    dict(index=row['index'], stream_key=row['stream_key'])) if view['mode'] == 'managed'
                    else dict(native_stream=stream_type, index=row['index'], proof=seen['proof']))
                token = encode(captured)
                path = 'plugin://plugin.video.bobbi/?' + urlencode(dict(action='osd_apply', token=token))
                caption = row.get('name', '')
                if stream_type == 'subtitle':
                    purposes = []
                    if row.get('isforced') is True:
                        purposes.append(_tr(91657, '强制字幕'))
                    if row.get('isimpaired') is True:
                        purposes.append(_tr(91658, '听障字幕 (SDH)'))
                    caption = ' · '.join(dict.fromkeys(x for x in [*purposes, caption] if x))
                item = ListItem(label=row.get('language') or 'UND', label2=caption,
                                path=path, offscreen=True)
                properties = {str(key): str(value) for key, value in row.items() if value is not None}
                properties.update(bobbi_command=token, bobbi_toggle=toggle, isfolder='false')
                if panel is not None:
                    properties['bobbi_panel'] = panel
                if row.get('selected', current == row['index']):
                    properties['iscurrent'] = 'true'
                item.setProperties(properties)
                items.append((path, item, False))
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        # Reading is not permission for a control or a global fallback. Never
        # retain a partial list whose captured rows failed validation.
        items = []
    if panel is not None and current_panel():
        owner.window.setProperty('Bobbi.OSD.StreamPanelRead', panel)
        reconcile_display(owner)
    xbmcplugin.addDirectoryItems(handle, items if current_panel() else [])
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def _notice(status):
    if status in ("applied", "queued"):
        return  # Routine foreground controls already have visible player feedback.
    from xbmcgui import Dialog
    text = {'applied': _tr(91202, '操作已生效'), 'queued': _tr(91203, '操作已提交，等待播放器确认'),
            'unknown': _tr(91204, '操作结果待确认，请稍后重新打开面板；不会重复发送'),
            'rejected': _tr(91205, '播放状态已变化，请重新打开面板'), 'failed': _tr(91206, '播放器未完成操作'),
            'unavailable': _tr(91207, '当前无法安全控制此播放，请稍后重试')}.get(status, _tr(91208, '当前操作不可用'))
    Dialog().notification(_tr(91201, '播放控制'), text)


def _locked(owner, operation):
    from bobbi_platform.instance_lock import InstanceLock
    from bobbi_platform.paths import profile
    lock = InstanceLock(str(owner.lock_path or profile(name='osd.lock')))
    try:
        lock.acquire()
    except (OSError, ValueError, RuntimeError):
        _notice('unknown')
        return
    try:
        return operation()
    finally:
        lock.close()


def _submit(owner, value):
    reply = _locked(owner, lambda: owner.submit(value))
    if reply is not None:
        _notice(reply['status'])
    return reply


def apply(owner, token):
    value = decode(token)
    if 'native_toggle' in value or 'native_stream' in value:
        from bobbi_platform.kodi import rpc
        from lib.services.native_streams import snapshot
        try:
            toggle = 'native_toggle' in value
            kind = 'subtitle' if toggle else value['native_stream']
            keys = {'native_toggle', 'proof'} if toggle else {'native_stream', 'index', 'proof'}
            mode = owner.read()['mode']
            if set(value) != keys or mode not in NATIVE_MODES or kind not in ('audio','subtitle'):
                raise ValueError('OSD_CAPTURE_INVALID')
            seen = snapshot(rpc, kind, mode)
            if value['proof'] != seen['proof'] or owner.read()['mode'] != mode:
                raise ValueError('OSD_CAPTURE_STALE')
            if toggle:
                visible = value['native_toggle']
                if type(visible) is not bool or visible == seen['visible']:
                    raise ValueError('OSD_CAPTURE_INVALID')
                return rpc('Player.SetSubtitle', dict(playerid=seen['player'], subtitle='on' if visible else 'off'))
            index = value['index']
            if type(index) is not int or not any(r['index'] == index for r in seen['rows']):
                raise ValueError('OSD_CAPTURE_INVALID')
            if kind == 'audio':
                return rpc('Player.SetAudioStream', dict(playerid=seen['player'], stream=index))
            return rpc('Player.SetSubtitle', dict(playerid=seen['player'], subtitle=index, enable=True))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
            _notice('rejected')
            return
    return _submit(owner, command(value))


def transport(owner, view, action):
    """Capture once before confirmation; the actor owns the eventual CAS.

    Pause chooses between explicit commands, never a player toggle. A missing
    extension on an older binary is not permission for global control.
    """
    from xbmcgui import Dialog
    import xbmc
    if view['mode'] in NATIVE_MODES:
        # These adapters explicitly retain Kodi's non-atomic native controls.
        # Never fall back here after a managed command was rejected/unknown.
        if action == 'confirm_stop':
            if not xbmc.getCondVisibility('Skin.HasSetting(backstopplay)') and not Dialog().yesno(
                    _tr(91201, '播放控制'), _tr(91209, '确定关闭播放吗？')):
                return
            if owner.read()['mode'] not in NATIVE_MODES:
                _notice('rejected')
                return
        if action == 'resume' and not xbmc.getCondVisibility(
                'Player.Paused | Player.Forwarding | Player.Rewinding'):
            return
        return xbmc.executebuiltin('PlayerControl(Stop)' if action in ('stop', 'confirm_stop')
                                  else 'PlayerControl(Play)')
    target = {'stop': 'stop', 'confirm_stop': 'stop', 'resume': 'resume'}.get(action)
    if action == 'toggle_pause':
        target = 'pause' if view.get('transport_state') == 'playing' else 'resume'
    if (view.get('available') is not True or type(view.get('transport_protocol')) is not int
            or view['transport_protocol'] != 1 or view.get('can_' + str(target)) is not True
            or view.get('transport_state') not in ('paused', 'playing', 'other')):
        _notice('unavailable')
        return
    captured = Client.capture(view, 'user_' + target, {})
    if action == 'confirm_stop' and not xbmc.getCondVisibility('Skin.HasSetting(backstopplay)'):
        if not Dialog().yesno(_tr(91201, '播放控制'), _tr(91209, '确定关闭播放吗？')):
            return
    return _submit(owner, captured)


def reconcile_display(owner):
    """Only query the existing receipt, if any. No player command on paint."""
    if owner.window.getProperty(owner.pending_key):
        reply = _locked(owner, owner.reconcile_pending)
        if reply is not None:
            _notice(reply['status'])


def run(bobbi_osd, token=None, **kwargs):
    import xbmc
    from xbmcgui import Dialog
    if bobbi_osd in ('open_audio_panel', 'open_subtitle_panel'):
        from xbmcgui import Window
        kind, menu = ('audio', '1145') if bobbi_osd == 'open_audio_panel' else ('subtitle', '1144')
        begin_stream_panel(Window(10000), kind, lambda: xbmc.getCondVisibility('Window.IsActive(' + menu + ')'))
        return
    owner = client()
    if bobbi_osd in ('apply', 'subtitle_toggle'):
        try:
            return apply(owner, token)
        except (ValueError, TypeError, KeyError):
            _notice('rejected')
            return
    return _run_view(bobbi_osd, owner, owner.read())


def _run_view(bobbi_osd, owner, view):
    import xbmc
    from xbmcgui import Dialog
    publish(view, owner.window)
    if bobbi_osd == 'refresh':
        reconcile_display(owner)
        return view
    if bobbi_osd == 'confirm_stop':
        # Saved remote keymaps keep 1126. It cannot turn into a skin-reset
        # dialog when A ends while confirmation waits.
        xbmc.executebuiltin('Dialog.Close(1126)')
        # Music's saved remote keymap also uses 1126. It has no managed video
        # instance; retain its native interaction without a global video Stop.
        music = 'Player.HasAudio + !Player.HasVideo'
        if xbmc.getCondVisibility(music):
            if (xbmc.getCondVisibility('Skin.HasSetting(backstopplay)')
                    or Dialog().yesno(_tr(91201, '播放控制'), _tr(91209, '确定关闭播放吗？'))):
                if xbmc.getCondVisibility(music):
                    from bobbi_platform.kodi import rpc
                    return rpc('Player.Stop', dict(playerid=0))
            return
    if bobbi_osd in ('toggle_pause', 'resume', 'stop', 'confirm_stop'):
        return transport(owner, view, bobbi_osd)
    if view['mode'] in NATIVE_MODES:
        native = {'seek_back': 'Seek(-10)', 'seek_forward': 'Seek(30)',
            'chapter_previous': 'PlayerControl(Previous)', 'chapter_next': 'PlayerControl(Next)',
            'chapters': 'ActivateWindow(videobookmarks)',
            'audio_settings': 'ActivateWindow(OSDAudioSettings)',
            'subtitle_settings': 'ActivateWindow(OSDSubtitleSettings)'}
        if bobbi_osd in native:
            xbmc.executebuiltin(native[bobbi_osd])
        elif bobbi_osd == 'seek':
            seconds = Dialog().numeric(0, _tr(91210, '跳转到第几秒'))
            if seconds and seconds.isdigit() and owner.read()['mode'] in NATIVE_MODES:
                from bobbi_platform.kodi import rpc
                value = int(seconds)
                rpc('Player.Seek', dict(playerid=1, value=dict(
                    hours=value // 3600, minutes=(value // 60) % 60,
                    seconds=value % 60, milliseconds=0)))
        return
    if view['mode'] != 'managed':
        _notice('unavailable')
        return
    if not view['can_seek'] or bobbi_osd.endswith('_settings'):
        _notice('unavailable')
        return
    target = None
    if bobbi_osd in ('seek_back', 'seek_forward'):
        target = view['position_ms'] + (-10000 if bobbi_osd == 'seek_back' else 30000)
        target = max(0, min(target, view['duration_ms'] - 1))
    elif bobbi_osd == 'seek':
        seconds = Dialog().numeric(0, _tr(91211, '跳转到第几秒（当前 %d 秒）') % (view['position_ms'] // 1000))
        if not seconds:
            return
        try:
            target = int(seconds) * 1000
        except ValueError:
            _notice('rejected')
            return
    elif bobbi_osd == 'chapters':
        rows = view['chapters']
        chapter_word = _tr(91212, '章节')
        selected = Dialog().select(chapter_word + (_tr(91213, '（列表已截短）') if view.get('chapters_truncated') else ''),
            [_tr(91214, '%s  ·  %d 秒') % (row['name'] or chapter_word, row['position_ms'] // 1000) for row in rows])
        if selected < 0 or selected >= len(rows):
            return
        target = rows[selected]['position_ms']
    elif bobbi_osd in ('chapter_previous', 'chapter_next'):
        positions = sorted(row['position_ms'] for row in view['chapters'])
        choices = ([p for p in positions if p < view['position_ms'] - 1000]
                   if bobbi_osd == 'chapter_previous' else [p for p in positions if p > view['position_ms']])
        if choices:
            target = choices[-1] if bobbi_osd == 'chapter_previous' else choices[0]
    if type(target) is not int or not 0 <= target < view['duration_ms']:
        _notice('unavailable')
        return
    # view was captured BEFORE the numeric/chapter dialog. No re-read/rebase.
    return _submit(owner, Client.capture(view, 'seek', dict(position_ms=target)))



TAP_SCOPE = 'Bobbi.OSD.TapScope'
TAPS = ('toggle_pause', 'seek_forward', 'seek_back', 'stop', 'chapter_next', 'chapter_previous')


def tap_scope(view):
    # Presentation token pins the open OSD to one player/selection. The real
    # command still captures the fresh sequence and is checked by the actor.
    if view.get('mode') != 'managed' or view.get('available') is not True:
        return ''
    row = view['expected']
    return sha256(encode([row[k] for k in ('boot_id', 'epoch', 'request_id',
        'native_instance', 'file_sha256', 'selection_epoch')]).encode()).hexdigest()[:32]


def resident_tap(owner, method):
    import xbmc
    if not xbmc.getCondVisibility('Window.IsActive(videoosd)'):
        return
    if method == 'Other.BobbiRefresh':
        view = owner.read()
        _run_view('refresh', owner, view)
        owner.window.setProperty(TAP_SCOPE, tap_scope(view))
        return
    action, _, captured = method.removeprefix('Other.BobbiTap.').partition('.')
    if action not in TAPS or not re.fullmatch('[0-9a-f]{32}', captured):
        return
    view = owner.read()
    if captured == owner.window.getProperty(TAP_SCOPE) and captured == tap_scope(view):
        return _run_view(action, owner, view)
    _notice('rejected')

def _tr(po_id, zh_text):
    try:
        from bobbi_platform.i18n import tr
        return tr(po_id, zh_text, '', addon_id='plugin.video.bobbi')
    except Exception:
        return zh_text
