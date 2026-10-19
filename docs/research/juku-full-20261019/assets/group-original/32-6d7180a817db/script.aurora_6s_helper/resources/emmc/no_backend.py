"""NO 22.x device access: verified loop mappings and native CE environment tools."""
import contextlib
import os
from pathlib import Path
import re
import struct
import fcntl


@contextlib.contextmanager
def region(op,off,size,readonly=False):
    args=['losetup','--find','--show','--offset',str(off),'--sizelimit',str(size)]
    if readonly:args+=['--read-only']
    loop=op.run(args+[op.DISK])
    if not re.fullmatch('/dev/loop[0-9]+',loop):raise ValueError('无效的 loop 设备名')
    try:
        with open(loop,'rb',buffering=0) as f:
            status=fcntl.ioctl(f.fileno(),0x4c05,b'\0'*232) # LOOP_GET_STATUS64
            # lo_rdevice is the backing block device; offset/limit, not its stale partitions.
            _,_,rdev,actual_off,limit=struct.unpack_from('=5Q',status)
            actual_size=struct.unpack('Q',fcntl.ioctl(f.fileno(),op.BLKGETSIZE64,b'\0'*8))[0]
            if (rdev,actual_off,limit,actual_size)!=(os.stat(op.DISK).st_rdev,off,size,size):
                raise ValueError('loop 后端、偏移或长度核对失败')
        yield Path(loop)
    finally:op.run(['losetup','--detach',loop])



def checkpoint(op,report):
    op.same_device(report,op.probe())


@contextlib.contextmanager
def environment_options(op,report):
    yield []
