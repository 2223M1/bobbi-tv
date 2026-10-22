"""Fetch the pinned icon font."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'af620534bfc3c2d4cbefcfeec29603bbe7809e64'  # Font Awesome Free 6.7.2
INPUTS = {
    'webfonts/fa-solid-900.ttf': ('assets/fonts/fa-solid-900.ttf', 426112,
                                'a0414182dca34041fdd585c0c4b4bd7a3a2753e2'),
}


def verify(raw, size, git_blob):
    framed = b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw
    if len(raw) != size or hashlib.sha1(framed).hexdigest() != git_blob:
        raise ValueError('Pinned font asset verification failed')


def fetch():
    result = {}
    for source, (output, size, git_blob) in INPUTS.items():
        dest = ROOT / output
        if dest.is_file():
            raw = dest.read_bytes()
        else:
            reply = subprocess.run(['gh', 'api', 'repos/FortAwesome/Font-Awesome/contents/'
                                    + source + '?ref=' + COMMIT], capture_output=True, check=True, timeout=30)
            data = json.loads(reply.stdout)
            if data.get('sha') != git_blob or data.get('encoding') != 'base64':
                raise ValueError('Pinned font API response mismatch')
            raw = base64.b64decode(''.join(data['content'].split()), validate=True)
            verify(raw, size, git_blob)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(raw)
        verify(raw, size, git_blob)
        result[output] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'git_blob': git_blob}
    return result


if __name__ == '__main__':
    print(json.dumps(fetch(), indent=2))
