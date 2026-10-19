"""Read vendor build.prop from a temporary read-only super mapping on NG.

LP format: AOSP liblp metadata_format.h (Apache-2.0), also distributed at
https://github.com/tchebb/parse-android-dynparts/tree/master/liblp/include/liblp
No userdata decryption or persistent Android mounts are involved.
"""
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import uuid


def metadata_geometry(raw):
    valid=[];errors=[]
    for offset in (4096,8192):
        geom=raw[offset:offset+52]
        if len(geom)!=52 or struct.unpack_from('<II',geom)!=(0x616c4467,52):
            errors.append('Unsupported super geometry');continue
        if hashlib.sha256(geom[:8]+bytes(32)+geom[40:]).digest()!=geom[8:40]:
            errors.append('Super geometry checksum mismatch');continue
        maximum,slots,blocksize=struct.unpack_from('<III',geom,40)
        if not 4096<=maximum<=1024**2 or maximum%512 or not 1<=slots<=4 or blocksize!=4096:
            errors.append('Unsupported super metadata limits');continue
        valid.append((maximum,slots,blocksize))
    if not valid:raise ValueError('; '.join(errors))
    if len(set(valid))!=1:raise ValueError('Conflicting super geometry copies')
    return valid[0]


def vendor_extents(raw, capacity, slot=0, backup=False):
    maximum,slots,_=metadata_geometry(raw)
    if slot not in (0,1) or slot>=slots:raise ValueError('Unsupported Android metadata slot')
    start=12288+(slot+(slots if backup else 0))*maximum
    header=raw[start:start+maximum]
    if len(header)<128:raise ValueError('Short super metadata')
    magic,major,minor,size=struct.unpack_from('<IHHI',header)
    if magic!=0x414c5030 or major!=10 or minor>2 or size not in (128,256):
        raise ValueError('Unsupported super metadata version')
    tables_size=struct.unpack_from('<I',header,44)[0]
    if size+tables_size>maximum or len(header)<size+tables_size:raise ValueError('Short super tables')
    if hashlib.sha256(header[:12]+bytes(32)+header[44:size]).digest()!=header[12:44]:
        raise ValueError('Super header checksum mismatch')
    tables=header[size:size+tables_size]
    if hashlib.sha256(tables).digest()!=header[48:80]:raise ValueError('Super table checksum mismatch')
    def entries(offset,expected):
        start,count,stride=struct.unpack_from('<III',header,offset)
        if stride!=expected or start+count*stride>len(tables):raise ValueError('Invalid super table bounds')
        return [tables[start+i*stride:start+(i+1)*stride] for i in range(count)]
    parts=entries(80,52);extents=entries(92,24);groups=entries(104,48);devices=entries(116,64)
    if len(devices)!=1:raise ValueError('Only single-device super supported')
    first,_,_,device_size,name,flags=struct.unpack('<QIIQ36sI',devices[0])
    if name.rstrip(b'\0')!=b'super' or device_size!=capacity or flags:
        raise ValueError('Super backing device mismatch')
    candidates=[]
    for part in parts:
        name,attrs,start,count,group=struct.unpack('<36sIIII',part)
        expected=b'vendor_a' if slot==0 else b'vendor_b'
        if name.rstrip(b'\0') not in (b'vendor',expected) or not count:continue
        if attrs & ~5 or group>=len(groups) or start+count>len(extents):raise ValueError('Unsupported vendor partition')
        rows=[]
        for item in extents[start:start+count]:
            sectors,kind,offset,source=struct.unpack('<QIQI',item)
            if kind!=0 or source!=0 or sectors==0 or offset<first or (offset+sectors)*512>capacity:
                raise ValueError('Invalid vendor extent')
            if any(offset<oldoff+oldsize and oldoff<offset+sectors for oldsize,oldoff in rows):
                raise ValueError('Overlapping vendor extents')
            rows.append((sectors,offset))
        candidates.append(rows)
    if len(candidates)!=1:raise ValueError('Cannot unambiguously select original Android vendor')
    return candidates[0]


def parse_active_slot(output):
    match=re.fullmatch(r'active_slot=(_[ab])',output.strip())
    if not match:raise ValueError('无法确认 Android active_slot，拒绝猜测 A/B 槽位')
    return 0 if match.group(1)=='_a' else 1


def selected_vendor_extents(raw,capacity,slot):
    errors=[]
    # Same-slot primary then backup, as in AOSP liblp ReadMetadata.
    for backup in (False,True):
        try:return vendor_extents(raw,capacity,slot,backup)
        except ValueError as exc:errors.append(str(exc))
    raise ValueError('Android 槽位 %s 的主备元数据均不可用：%s'%('AB'[slot] if slot in (0,1) else slot,'; '.join(errors)))


def validate_vendor_filesystem(source,extents):
    # Read the ext4 superblock via the selected extents before asking the kernel
    # to mount anything. Never expand a mapping to match a filesystem header.
    skip=1024;remaining=1024;chunks=[]
    for sectors,offset in extents:
        size=sectors*512
        if skip>=size:skip-=size;continue
        count=min(remaining,size-skip)
        source.seek(offset*512+skip);data=source.read(count)
        if len(data)!=count:raise ValueError('Short vendor superblock read')
        chunks.append(data);remaining-=count;skip=0
        if remaining==0:break
    sb=b''.join(chunks)
    if len(sb)!=1024 or struct.unpack_from('<H',sb,56)[0]!=0xef53:
        raise ValueError('所选 vendor 映射没有有效的 ext4 超级块')
    log=struct.unpack_from('<I',sb,24)[0]
    if log>6:raise ValueError('Unsupported vendor filesystem block size')
    blocks=struct.unpack_from('<I',sb,4)[0]
    if struct.unpack_from('<I',sb,96)[0]&0x80:
        blocks|=struct.unpack_from('<I',sb,336)[0]<<32
    expected=blocks*(1024<<log);actual=sum(size*512 for size,_ in extents)
    if not expected or expected>actual:
        raise ValueError('vendor 文件系统需要 %d 字节，所选槽位映射只有 %d 字节；拒绝扩大映射'%(expected,actual))
    return expected


def read_vendor_models(super_row, *, slot=None):
    dev=Path('/dev/super')
    import os,stat
    if not stat.S_ISBLK(dev.stat().st_mode):raise ValueError('super is not a block device')
    block=Path('/sys/dev/block/%d:%d'%(os.major(dev.stat().st_rdev),os.minor(dev.stat().st_rdev)))
    if block.resolve().parent.name!='mmcblk0' or int((block/'start').read_text(encoding='utf-8'))*512!=super_row['offset'] or int((block/'size').read_text(encoding='utf-8'))*512!=super_row['size']:
        raise ValueError('super device does not match verified MPT')
    def run(args):
        p=subprocess.run(args,capture_output=True,encoding='utf-8',timeout=30)
        if p.returncode:raise ValueError('Android 机型读取失败：'+p.stderr.strip())
        return p.stdout.strip()
    if slot is None:
        slot=parse_active_slot(run(['fw_printenv','active_slot']))
    elif slot not in (0,1):
        raise ValueError('Invalid identity-only vendor slot')
    with dev.open('rb',buffering=0) as f:
        prefix=f.read(12288)
        maximum,slots,_=metadata_geometry(prefix)
        raw=prefix+f.read(2*maximum*slots)
        extents=selected_vendor_extents(raw,super_row['size'],slot)
        validate_vendor_filesystem(f,extents)
    name='aurora-id-'+uuid.uuid4().hex[:12]
    cursor=0;table=[]
    for size,offset in extents:
        table.append('%d %d linear %s %d'%(cursor,size,dev,offset));cursor+=size
    with tempfile.TemporaryDirectory(prefix='aurora-android-') as tmp:
        created=mounted=False
        try:
            run(['dmsetup','create',name,'--readonly','--table','\n'.join(table)]);created=True
            run(['mount','-t','ext4','-o','ro,noload','/dev/mapper/'+name,tmp]);mounted=True
            text=(Path(tmp)/'build.prop').read_text(encoding='utf-8')
            return sorted({line.split('=',1)[1].strip() for line in text.splitlines()
                           if re.match(r'^ro\.product\.(?:[\w]+\.)?model=',line)})
        finally:
            try:
                if mounted:run(['umount',tmp])
                if created:run(['dmsetup','remove','--retry',name])
            except Exception as exc:
                # A repair identity probe must never swallow failed cleanup and
                # continue to another mapping or a write operation.
                raise RuntimeError('Android identity mapping cleanup failed') from exc
