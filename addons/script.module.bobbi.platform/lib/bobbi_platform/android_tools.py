"""Bind optional tools only to the signed APK's installed native directory."""
import hashlib
import json
from pathlib import Path


def font_decoder(tool):
    import xbmcvfs
    from .android_engine import request
    from bobbi_core.android_font_decoder import decoder
    info = request('info')
    root = Path(info['native_directory']).resolve()
    record = json.loads(Path(xbmcvfs.translatePath('special://xbmc/system/bobbi-android-host.json')).read_text())
    if Path(tool).resolve() != root/'libbobbi_7zip.so':
        raise ValueError('ANDROID_FONT_TOOL_PATH')
    for name, field in (('libbobbi_7zip.so', 'font_decoder_sha256'),
                        ('libbobbi_font_limiter.so', 'font_limiter_sha256')):
        path = root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8*1024*1024:
            raise ValueError('ANDROID_FONT_TOOL_INPUT')
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get(field):
            raise ValueError('ANDROID_FONT_TOOL_CHANGED')
    return decoder(root/'libbobbi_7zip.so', root/'libbobbi_font_limiter.so')
