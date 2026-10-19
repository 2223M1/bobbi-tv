"""ctypes libraries follow Python's ABI; independent speech workers use ARM64."""
import ctypes.util
from pathlib import Path
import re
import struct


def decoder_path(root, group, stem, dependency='avcodec'):
    architecture = 'linux_aarch64' if struct.calcsize('P') == 8 else 'linux_armv7l'
    name = ctypes.util.find_library(dependency) or ''
    match = re.search(r'\.so\.(\d+)', name)
    if match:
        major = int(match[1])
    else:
        found = []
        for base in ('/usr/lib', '/lib'):
            for path in Path(base).glob('lib' + dependency + '.so.*'):
                version = re.search(r'\.so\.(\d+)', path.name)
                if version: found.append(int(version[1]))
        major = max(found) if found else (60 if dependency == 'avutil' else 62)
    return Path(root) / 'resources/native' / architecture / group / (stem + str(major) + '.so')
