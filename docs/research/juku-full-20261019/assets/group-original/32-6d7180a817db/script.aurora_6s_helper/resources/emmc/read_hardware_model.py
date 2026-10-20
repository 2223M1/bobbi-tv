"""Read original Android identity only; no install policy or environment writes."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from aurora_emmc import MIB, parse_mpt
from repair_identity import read_models_for_environment


def read_models():
    disk = Path('/sys/block/mmcblk0')
    dev = os.stat('/dev/mmcblk0')
    if not stat.S_ISBLK(dev.st_mode):
        raise ValueError('eMMC is not a block device')
    if (disk / 'dev').read_text().strip() != '%d:%d' % (os.major(dev.st_rdev), os.minor(dev.st_rdev)):
        raise ValueError('eMMC device identity mismatch')
    capacity = int((disk / 'size').read_text()) * 512
    with open('/dev/mmcblk0', 'rb', buffering=0) as source:
        source.seek(36 * MIB)
        table = parse_mpt(source.read(4096), capacity)
    rows = [row for row in table['partitions'] if row['name'] == 'super']
    if len(rows) != 1:
        raise ValueError('Cannot identify original super partition')
    # This reader checks the live super device against the MPT, validates LP
    # checksums/extents and mounts only vendor as ro,noload, then cleans up.
    environment = subprocess.run(['fw_printenv', 'active_slot'], capture_output=True,
                                 encoding='utf-8', timeout=30)
    if environment.returncode:
        raise ValueError('Android 启动环境读取失败：' + environment.stderr.strip())
    models, _ = read_models_for_environment(rows[0], environment.stdout)
    return models


if __name__ == '__main__':
    try:
        print(json.dumps(read_models()))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
