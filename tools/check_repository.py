"""Compare all public repository bytes, including ZIPs and change checksums."""
import hashlib
from pathlib import Path
import sys


def snapshot(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def compare(first, second):
    a, b = snapshot(first), snapshot(second)
    if a != b:
        changed = sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key))
        raise ValueError('Repository build differs: ' + ', '.join(changed[:20]))
    return len(a)


if __name__ == '__main__':
    print('Reproducible files:', compare(*sys.argv[1:3]))
