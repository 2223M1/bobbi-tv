"""Foreground CE copy; the user stops playback/library activity before starting."""
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
from file_attributes import rsync_xattr_filters


def rsync_copy(args, update=None, step=None, total=0, timeout=7200):
    if update:update('copying','复制文件',progress_step=step,progress_done=0,progress_total=total)
    process=subprocess.Popen(args+['--info=progress2','--outbuf=L'],stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,env={**os.environ,'LC_ALL':'C'})
    pending=b'';tail='';start=time.monotonic();done=0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            eof=False
            while not eof:
                if time.monotonic()-start>timeout:raise TimeoutError('复制文件超时')
                if update:update('copying','复制文件',progress_step=step,progress_done=done,progress_total=total)
                for key,_ in selector.select(1):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data:eof=True;break
                    pending+=data
                    lines=re.split(b'[\r\n]',pending);pending=lines.pop()
                    for line in lines:
                        text=line.decode('utf-8','replace');tail=(tail+'\n'+text)[-3000:]
                        match=re.match(r'^\s*([\d,]+)\s+\d+%',text)
                        if match:done=min(total,int(match[1].replace(',','')))
            if process.wait()!=0:raise RuntimeError('文件复制失败：'+tail)
        if update:update('copying','文件复制完成',progress_step=step,progress_done=total,progress_total=total)
    finally:
        if process.poll() is None:process.terminate();process.wait()
        process.stdout.close()


def copy_live_storage(source,dest,flags,excludes,run,update=None):
    source=Path(source);dest=Path(dest);total=0
    for base,dirs,files in os.walk(source,followlinks=False):
        dirs[:]=[n for n in dirs if not (Path(base)/n).is_symlink()
                 and '/'+str((Path(base)/n).relative_to(source))+'/' not in excludes]
        for name in files:
            path=Path(base)/name
            if path.is_file() and not path.is_symlink():total+=path.stat().st_size
    args=['rsync',flags,'--numeric-ids',*rsync_xattr_filters(flags),*['--exclude='+p for p in excludes],str(source)+'/',str(dest)+'/']
    rsync_copy(args,update,'snapshot-copy',total)
