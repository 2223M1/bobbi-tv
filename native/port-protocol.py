"""One-time reviewed import of generic protocol sections, never CE hardware patches.

The release input is the final patches/ patch, not this development utility.
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

ALLOWED = {
    'xbmc/application/Application.cpp', 'xbmc/application/ApplicationPlayer.cpp',
    'xbmc/application/ApplicationPlayer.h', 'xbmc/cores/BobiGuiGate.h',
    'xbmc/cores/BobiOpenGate.h', 'xbmc/cores/BobiReadStatus.h', 'xbmc/cores/IPlayer.h',
    'xbmc/cores/VideoPlayer/DVDMessage.h', 'xbmc/cores/VideoPlayer/VideoPlayer.cpp',
    'xbmc/cores/VideoPlayer/VideoPlayer.h', 'xbmc/guilib/GUIWindow.cpp',
    'xbmc/interfaces/json-rpc/JSONServiceDescription.cpp',
    'xbmc/interfaces/json-rpc/PlayerOperations.cpp',
    'xbmc/interfaces/json-rpc/PlayerOperations.h',
    'xbmc/interfaces/json-rpc/schema/methods.json',
    'xbmc/interfaces/json-rpc/schema/notifications.json',
    'xbmc/messaging/ApplicationMessenger.h',
    'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemux.h',
    'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp',
    'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.h',
    'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStream.h',
    'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp',
    'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp',
    'xbmc/cores/VideoPlayer/VideoPlayerVideo.h',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('checkout', type=Path)
    args = parser.parse_args()
    raw = args.baseline.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '96f2cf3ba90f2e9286795ea3f1df6573ce8837d0d02083dc35882cc4e144c648':
        raise ValueError('Unrecognized baseline patch')
    chunks = re.split(r'(?=^diff --git )', raw.decode().replace('\r\n', '\n'), flags=re.M)
    selected = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        path = chunk.splitlines()[0].split(' b/', 1)[1]
        if path in ALLOWED:
            selected.append(chunk)
    output = args.checkout.parent / 'generic-import.patch'
    output.write_text(''.join(selected), encoding='utf-8', newline='\n')
    subprocess.run(['git', 'apply', '--reject', str(output.resolve())], cwd=args.checkout, check=True)


if __name__ == '__main__':
    main()
