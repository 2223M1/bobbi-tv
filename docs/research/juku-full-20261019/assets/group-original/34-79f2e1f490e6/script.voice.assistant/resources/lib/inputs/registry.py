"""Unified input choices and safe claiming of prepared Bluetooth sessions."""
from contextlib import contextmanager
import time

INPUTS = {
    'ur02': ('Ugoos 遥控（UR01 / UR02）', 'UR02'),
    'nanosic': ('腾讯极光遥控', 'Nanosic'),
    'cmcc': ('移动高清遥控', 'CMCC'),
    'r22': ('华为 R22 遥控（按住说话）', 'R22'),
    'b25': ('Homatics 遥控（B21 / B25）', 'B25'),
    'usb': ('USB 麦克风 / 2.4G 遥控', ''),
}


def pending(home, source):
    prefix = INPUTS[source][1]
    return home.getProperty('VoiceAssistant.' + prefix + 'Session') if prefix else ''


def resolve_token(home, source, monitor, token=None):
    """Ignore stale launches before opening a window or importing the client."""
    if token is None:
        token = pending(home, source)
        # A physical key can precede the service's publication of its lease.
        if not token and source in ('ur02', 'r22', 'b25'):
            for unused in range(20):
                if monitor.waitForAbort(.025):
                    return None
                token = pending(home, source)
                if token:
                    break
    if not token or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        return None
    return token


@contextmanager
def claim(profile, source, home, monitor, token=None):
    if source == 'usb':
        yield None
        return
    token = resolve_token(home, source, monitor, token)
    if token is None:
        yield False
        return
    from .pcm import Client
    with Client(profile, token, socket_name=source + '.sock') as client:
        yield client.microphone
