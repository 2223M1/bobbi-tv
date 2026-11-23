"""Use CE's system curl for one admitted origin response, never as a resolver.

Only raw HTTP/1.1 bytes cross a private socket pair. The core still parses the
response, checks the exact range and account, owns retries and serves Kodi.
No media URL, UA or credentials are passed on the process command line.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

SYSTEM_CURL = '/usr/bin/curl'


def installed_reader():
    if sys.platform != 'linux' or not os.access(SYSTEM_CURL, os.X_OK):
        return None
    try:
        release = Path('/etc/os-release').read_text(encoding='ascii')
    except (OSError, UnicodeError):
        return None
    if not re.search(r'^id=(?:"coreelec"|coreelec)$', release.lower(), re.MULTILINE):
        return None
    from bobbi_core.share_origin import RangeOrigin
    return lambda: RangeOrigin(wire=wire_socket)


def _quoted(value):
    if (not isinstance(value, str) or len(value) > 8192 or
            any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('SHARE_TRANSPORT_INVALID')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


@contextmanager
def wire_socket(parts, target, headers, timeout, *, ca_file=None):
    if ca_file is None:
        import certifi
        ca_file = certifi.where()
    address = parts.scheme + '://' + parts.netloc + target
    # curl's config is private stdin, not a file, shell, inherited proxy or
    # environment. Limit both vocabulary and size before starting a process.
    if (parts.scheme not in ('https', 'http') or
            set(headers) != {'User-Agent', 'Range', 'Accept-Encoding', 'Connection'} or
            not re.fullmatch(r'bytes=[0-9]+-[0-9]*', headers['Range']) or
            headers['Accept-Encoding'] != 'identity' or headers['Connection'] != 'close'):
        raise ValueError('SHARE_TRANSPORT_INVALID')
    config = ('url = ' + _quoted(address) + '\n' + ''.join(
        'header = ' + _quoted(k + ': ' + v) + '\n' for k, v in headers.items())).encode('utf-8')
    if len(config) > 12288:
        raise ValueError('SHARE_TRANSPORT_INVALID')
    # The dedicated header callback flushes even when a rejected response
    # sends no body. --include can buffer these headers until a body arrives.
    command = [SYSTEM_CURL, '-q', '--silent', '--dump-header', '-', '--raw', '--no-buffer',
               '--http1.1', '--globoff', '--path-as-is', '--noproxy', '*', '--proto', '=http,https',
               '--max-redirs', '0', '--retry', '0', '--cacert', str(ca_file),
               '--connect-timeout', str(timeout[0]), '--speed-time', str(int(timeout[1])),
               '--speed-limit', '1', '--config', '-']
    parent, child = socket.socketpair()
    with parent, child:
        child.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024)
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=child.fileno(),
                                   stderr=subprocess.DEVNULL, close_fds=True, env={})
        child.close()  # An exited reader must be visible as EOF immediately.
        try:
            with process.stdin:
                process.stdin.write(config)
            yield parent
        finally:
            # A seek, pause backpressure or account revocation can end the
            # request before upstream EOF. Do not leave a helper holding it.
            parent.close()
            if process.poll() is None:
                process.kill()
            process.wait()
