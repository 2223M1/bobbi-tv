"""On-demand Kodi images; video frames bypass all GUI overlays."""
from ..data_paths import data_path
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import struct
import tempfile
import time
import zlib

MAX_IMAGE = 8 * 1024 * 1024
MAX_PIXELS = 4096 * 2160
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_END = b'\x00\x00\x00\x00IEND\xaeB`\x82'
HIDE_PROPERTY = 'VoiceAssistant.CaptureHidden'
CAPTURE_GROUP = 9900


def png_bgra(pixels, width, height):
    if not 0 < width <= 4096 or not 0 < height <= 2160 or width * height > MAX_PIXELS or len(pixels) != width * height * 4:
        raise ValueError('视频帧尺寸或像素数据不完整。')
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2::4], pixels[1::4], pixels[0::4]
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    rows = b''.join(b'\0' + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 3)) + chunk(b'IEND', b''))


def png_size(data):
    if len(data) < 45 or len(data) > MAX_IMAGE or not data.startswith(PNG_SIGNATURE) or not data.endswith(PNG_END):
        raise ValueError('截图尚未完成或图片格式无效。')
    width, height = struct.unpack('>II', data[16:24])
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise ValueError('截图尺寸不受支持。')
    return width, height


def _check(cancelled):
    if cancelled():
        raise InterruptedError('已取消截图。')


def _result(data, source, note, backend):
    width, height = png_size(data)
    return {'source': source, 'backend': backend, 'width': width, 'height': height,
            'mime_type': 'image/png', 'captured_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
            'note': note, 'data': data}


@contextmanager
def assistant_hidden(cancelled):
    """Hide all assistant XML content without closing modal windows or their tasks."""
    import xbmc
    import xbmcgui
    home = xbmcgui.Window(10000)
    if home.getProperty(HIDE_PROPERTY):
        raise ValueError('另一个截图任务正在进行，请稍后重试。')
    dialog = xbmcgui.getCurrentWindowDialogId()
    group, focus = None, None
    if dialog != 9999:
        window = xbmcgui.Window(dialog)
        try:
            group = window.getControl(CAPTURE_GROUP)
            focus = window.getFocusId()
        except (RuntimeError, TypeError):
            pass
    home.setProperty(HIDE_PROPERTY, 'true')
    try:
        deadline = time.monotonic() + 1
        while group is not None and group.isVisible():
            _check(cancelled)
            if time.monotonic() >= deadline:
                raise ValueError('助手窗口尚未隐藏，未获取截图。')
            xbmc.sleep(20)
        # Allow the display buffer to contain a freshly rendered background.
        xbmc.sleep(120)
        _check(cancelled)
        yield
    finally:
        home.clearProperty(HIDE_PROPERTY)
        if group is not None and focus is not None and xbmcgui.getCurrentWindowDialogId() == dialog:
            xbmc.sleep(60)
            try:window.setFocusId(focus)
            except RuntimeError:pass


def framebuffer(cancelled, device='/dev/fb0', system='/sys/class/graphics/fb0'):
    """Read the active Amlogic OSD page, never write a device or change display mode.

    Some CE builds make TakeScreenshot capture only video even with dialogs open.
    Detect their named OSD framebuffer; other renderers keep Kodi's normal path.
    """
    system = Path(system)
    try:
        if (system / 'name').read_text().strip() != 'OSD FB':
            return None
    except OSError:
        return None
    import fcntl
    _check(cancelled)
    try:
        with open(device, 'rb') as stream:
            info = bytearray(160)
            fcntl.ioctl(stream, 0x4600, info)  # FBIOGET_VSCREENINFO, read-only.
            values = struct.unpack_from('24I', info)
            width, height, virtual_width, virtual_height, xoffset, yoffset, depth = values[:7]
            stride = int((system / 'stride').read_text())
            if (not 0 < width <= 4096 or not 0 < height <= 2160 or width * height > MAX_PIXELS
                    or depth != 32 or tuple(values[8:20]) != (16, 8, 0, 8, 8, 0, 0, 8, 0, 24, 8, 0)
                    or xoffset + width > virtual_width or yoffset + height > virtual_height
                    or not virtual_width * 4 <= stride <= 4096 * 4):
                raise ValueError('当前显示缓冲区尺寸或像素格式不受支持。')
            stream.seek(yoffset * stride + xoffset * 4)
            # Include row padding, but not bytes after the final visible row.
            count = (height - 1) * stride + width * 4
            data = stream.read(count)
            if len(data) != count:
                raise ValueError('未读取到完整界面缓冲区。')
        _check(cancelled)
        pixels = data if stride == width * 4 else b''.join(
            data[y * stride:y * stride + width * 4] for y in range(height))
        return png_bgra(pixels, width, height), width, height
    except (OSError, OverflowError) as error:
        raise ValueError('读取界面显示缓冲区失败：' + str(error)) from None


def amvideocap(width, height, cancelled, device='/dev/amvideocap0', system='/sys/class/video'):
    """Read Amlogic's current linear video copy, including a paused frame.

    The 4.9 ioctl setters take integer values, not pointers. They configure this
    capture handle only; playback, decoder mode and global config stay intact.
    ABI: CoreELEC linux-amlogic include/linux/amlogic/media/video_sink/amvideocap.h.
    Kodi's ScreenshotAML.cpp documents that S24_RGB actually returns BGR bytes.
    """
    if not Path(device).is_char_device():
        return None
    import fcntl
    import os
    _check(cancelled)
    try:
        with (Path(system) / 'frame_addr').open() as source:
            addresses = source.read(256).strip().split('-')
    except OSError:
        return None  # Other kernels/renderers keep the normal Kodi path.
    try:
        linear = len(addresses) == 3 and all(value.startswith('0x') for value in addresses)
        linear = linear and int(addresses[0], 16) != 0
    except ValueError:
        linear = False
    if not linear:
        raise ValueError('当前视频没有可读取的线性画面副本。请启用驱动双写后重新打开视频，再获取画面。')
    capture_width = (width + 31) & ~31
    if not 0 < width <= 3840 or not 0 < height <= 2160 or capture_width * height > MAX_PIXELS:
        raise ValueError('视频帧尺寸不受支持。')
    descriptor = None
    capture_started = False
    try:
        descriptor = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        pixel_format = 0x1000200  # GE2D_FORMAT_S24_RGB (memory order BGR).
        for command, value in ((0x40045601, pixel_format), (0x40045602, capture_width),
                               (0x40045603, height), (0x40085605, 500), (0x40045606, 0)):
            fcntl.ioctl(descriptor, command, value)
        _check(cancelled)
        # This legacy driver queues a nonblocking GE2D conversion, then copies
        # its destination immediately. Its first read can contain unwritten
        # pixels. Warm the same buffer, allow conversion to finish, then read
        # again (which also performs the driver's DMA cache invalidation).
        capture_started = True
        first = os.pread(descriptor, capture_width * height * 3, 0)
        if len(first) != capture_width * height * 3:
            raise ValueError('视频驱动返回的像素数据不完整。')
        time.sleep(.05)
        _check(cancelled)
        pixels = os.pread(descriptor, capture_width * height * 3, 0)
        _check(cancelled)
        for command, expected in ((0x80045631, 300), (0x80045610, pixel_format),
                                   (0x80045611, capture_width), (0x80045612, height)):
            actual = bytearray(4)
            fcntl.ioctl(descriptor, command, actual)
            if struct.unpack('I', actual)[0] != expected:
                raise ValueError('视频驱动未返回完整的当前画面。')
        if len(pixels) != capture_width * height * 3:
            raise ValueError('视频驱动返回的像素数据不完整。')
    except InterruptedError:
        raise
    except OSError as error:
        raise ValueError('视频驱动取帧失败：' + str(error)) from None
    finally:
        if descriptor is not None:
            try:
                # Keep the destination alive while the last queued conversion
                # completes, including cancellation/error cleanup.
                if capture_started:time.sleep(.05)
            finally:
                os.close(descriptor)
    # The driver aligns capture width to 32 pixels. Crop padding per row.
    if capture_width != width:
        pixels = b''.join(pixels[y * capture_width * 3:y * capture_width * 3 + width * 3]
                          for y in range(height))
    bgra = bytearray(width * height * 4)
    bgra[0::4], bgra[1::4], bgra[2::4] = pixels[0::3], pixels[1::3], pixels[2::3]
    bgra[3::4] = b'\xff' * (width * height)
    _check(cancelled)
    return png_bgra(bgra, width, height)


def _screen(cancelled):
    import xbmc
    shot = framebuffer(cancelled)
    if shot is not None:
        data, width, height = shot
        note = '当前界面显示缓冲区，已隐藏助手自身弹窗；独立硬件视频层未必在图中，视频内容请用video。未改变播放状态。'
        _check(cancelled)
        return _result(data, 'screen', note, 'framebuffer')
    import xbmcaddon
    import xbmcvfs
    profile = Path(xbmcvfs.translatePath(xbmcaddon.Addon('script.voice.assistant').getAddonInfo('profile')))
    directory = data_path(profile, 'captures');directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='screen-', dir=directory) as temporary:
        path = Path(temporary) / 'screen.png'
        # The optional sync flag was removed in newer Kodi. Poll the complete PNG.
        xbmc.executebuiltin('TakeScreenshot(' + str(path) + ')')
        deadline = time.monotonic() + 5
        while True:
            _check(cancelled)
            try:
                if path.stat().st_size > MAX_IMAGE:
                    raise ValueError('屏幕截图超过 8MiB，未发送图片。')
                with path.open('rb') as stream:
                    data = stream.read(MAX_IMAGE + 1)
                png_size(data)
                break
            except (OSError, ValueError) as error:
                if path.is_file() and path.stat().st_size > MAX_IMAGE:
                    raise ValueError('屏幕截图超过 8MiB，未发送图片。') from None
                if time.monotonic() >= deadline:
                    raise ValueError('Kodi 未生成完整屏幕截图，请检查当前渲染方式。') from error
            xbmc.sleep(20)
    note = '当前屏幕，已隐藏助手自身弹窗，保留其他 Kodi 界面和字幕；未改变播放状态。'
    return _result(data, 'screen', note, 'kodi')


def capture(source='auto', cancelled=lambda: False):
    import xbmc
    _check(cancelled)
    if source not in ('auto', 'video', 'screen'):
        raise ValueError('不支持的截图来源。')
    if source == 'auto':
        source = 'video' if xbmc.Player().isPlayingVideo() else 'screen'
    if source == 'video':
        if not xbmc.Player().isPlayingVideo():
            raise ValueError('当前没有正在播放的视频，无法获取视频帧。')
        render = xbmc.RenderCapture()
        aspect = render.getAspectRatio()
        width, height = (960, max(1, round(960 / aspect))) if .75 <= aspect <= 5 else (960, 540)
        render.capture(width, height)
        # Kodi returns immediately on a failed hardware capture. Do not busy-loop
        # or send a corrupt native screenshot as a replacement video frame.
        pixels = render.getImage(1000)
        if len(pixels) != width * height * 4:
            data = amvideocap(width, height, cancelled)
            if data is not None:
                note = ('驱动当前线性视频帧，不含 Kodi 界面和助手弹窗；双写副本可能低于原片分辨率。'
                        '独立渲染的字幕可能不在图中。未改变播放或暂停状态。')
                _check(cancelled)
                return _result(data, 'video', note, 'amvideocap')
            raise ValueError('播放器未返回完整视频帧。字幕和界面可用 screen 查询；独立视频层当前无法获取。')
        _check(cancelled)
        if render.getImageFormat() != 'BGRA':
            raise ValueError('播放器返回的像素格式不受支持。')
        data = png_bgra(pixels, width, height)
        note = '播放器当前视频帧，不含 Kodi 界面和弹窗；独立渲染的外挂字幕可能不在图中。未改变播放或暂停状态。'
    else:
        with assistant_hidden(cancelled):
            result = _screen(cancelled)
            _check(cancelled)
            return result
    _check(cancelled)
    return _result(data, source, note, 'render_capture' if source == 'video' else 'kodi')
