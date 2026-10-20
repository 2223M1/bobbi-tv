"""Unified input choices and safe claiming of prepared Bluetooth sessions."""
from contextlib import contextmanager
import time

INPUTS = {
    'ur02': ('Ugoos 遥控（UR01 / UR02）', 'UR02'),
    'nanosic': ('腾讯极光遥控', 'Nanosic'),
    'cmcc': ('移动高清遥控', 'CMCC'),
    'b25': ('Homatics 遥控（B21 / B25）', 'B25'),
    'r22': ('华为 R22 遥控（按住说话）', 'R22'),
    'usb': ('USB 麦克风 / 2.4G 遥控', ''),
}

PROPERTY = 'VoiceInput.'


def pending(home, source):
    prefix = INPUTS[source][1]
    return home.getProperty(PROPERTY + prefix + 'Session') if prefix else ''


@contextmanager
def claim(profile, source, home, monitor, token=None):
    if source == 'usb':
        yield None
        return
    if token is None:
        token = pending(home, source)
        # F5 can precede the service's publication of an ATVV lease.
        if not token and source == 'ur02':
            for unused in range(20):
                if monitor.waitForAbort(.025):
                    yield False
                    return
                token = pending(home, source)
                if token:
                    break
    if not token or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        yield False
        return
    if source == 'ur02':
        from ..ur02_audio import Ur02Client as Client
    elif source == 'nanosic':
        from ..nanosic_audio import NanosicClient as Client
    elif source == 'b25':
        from ..b25_audio import B25Client as Client
    elif source == 'r22':
        from ..r22_audio import R22Client as Client
    else:
        from ..cmcc_audio import CmccClient as Client
    with Client(profile, token) as client:
        yield client.microphone
