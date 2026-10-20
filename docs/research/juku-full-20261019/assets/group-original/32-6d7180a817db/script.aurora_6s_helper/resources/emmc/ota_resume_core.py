"""Pure parsers for the tested Android 11 persistent Virtual A/B retry case.

Formats: AOSP liblp metadata_format.h, libsnapshot/snapshot.proto and
bootloader_message/bootloader_message.h. No update.zip, install history or I/O.
Unknown states are refused; this is not a generic Android rollback tool.
"""
import hashlib
import re
import struct
import zlib
from android_identity import metadata_geometry

PARTITIONS = ('odm', 'product', 'system', 'system_ext', 'vendor')
RECOVERY = b'recovery\n--prompt_and_wipe_data\n--reason=init_user0_failed\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def protobuf(raw, allowed):
    pos = 0
    result = {}
    def varint():
        nonlocal pos
        value = 0
        for shift in range(0, 70, 7):
            if pos >= len(raw):raise ValueError('截断的 OTA protobuf')
            v = raw[pos];pos += 1;value |= (v & 127) << shift
            if not v & 128:
                if value >= 1 << 64:raise ValueError('OTA protobuf 整数溢出')
                return value
        raise ValueError('无效的 OTA protobuf')
    while pos < len(raw):
        tag = varint();field, wire = tag >> 3, tag & 7
        if field not in allowed or field in result or allowed[field] != wire:
            raise ValueError('不支持的 OTA protobuf 字段')
        if wire == 0:value = varint()
        else:
            size = varint()
            if size > len(raw)-pos:raise ValueError('截断的 OTA protobuf 字符串')
            value = raw[pos:pos+size];pos += size
        result[field] = value
    return result


def snapshot(raw, filename):
    p = protobuf(raw, {1:2, **{i:0 for i in range(2,9)}})
    name = p.get(1,b'').decode('ascii')
    if name != filename or not re.fullmatch(r'(odm|product|system|system_ext|vendor)_[ab]',name):
        raise ValueError('不支持的 OTA 快照名称')
    fields = ('name','state','device_size','snapshot_size','cow_partition_size','cow_file_size','sectors_allocated','metadata_sectors')
    out = {key:p.get(i,0) for i,key in enumerate(fields,1)};out['name'] = name
    if out['state'] != 1 or out['sectors_allocated'] or out['metadata_sectors']:
        raise ValueError('快照已经合并、正在合并或状态未知，不允许重选槽位')
    if not 0 < out['device_size'] <= 16*1024**3 or out['snapshot_size'] != out['device_size']:
        raise ValueError('只支持完整分区快照')
    if any(out[k] % 4096 for k in ('device_size','cow_partition_size','cow_file_size')):
        raise ValueError('快照大小未对齐')
    if not 0 < out['cow_partition_size']+out['cow_file_size'] <= 32*1024**3:
        raise ValueError('无效的 COW 容量')
    return out


def lp_table(raw, capacity, device_name):
    if len(raw)<128:raise ValueError('LP 头截断')
    magic,major,minor,size = struct.unpack_from('<IHHI',raw)
    tables_size = struct.unpack_from('<I',raw,44)[0]
    if magic!=0x414c5030 or major!=10 or minor>2 or size not in (128,256) or size+tables_size>len(raw):
        raise ValueError('不支持的 LP 元数据')
    if hashlib.sha256(raw[:12]+bytes(32)+raw[44:size]).digest()!=raw[12:44]:raise ValueError('LP 头校验失败')
    tables=raw[size:size+tables_size]
    if hashlib.sha256(tables).digest()!=raw[48:80]:raise ValueError('LP 表校验失败')
    ranges=[]
    def entries(pos,stride):
        off,count,actual=struct.unpack_from('<III',raw,pos)
        if actual!=stride or count>8192 or off+count*stride>len(tables):raise ValueError('LP 表越界')
        if count:
            end=off+count*stride
            if any(off<b and a<end for a,b in ranges):raise ValueError('LP 表重叠')
            ranges.append((off,end))
        return [tables[off+i*stride:off+(i+1)*stride] for i in range(count)]
    parts=entries(80,52);extents=entries(92,24);groups=entries(104,48);devices=entries(116,64)
    if len(devices)!=1:raise ValueError('只支持单设备 LP 映射')
    first,_,_,total,name,flags=struct.unpack('<QIIQ36sI',devices[0])
    if name.rstrip(b'\0')!=device_name.encode() or total!=capacity or flags:raise ValueError('LP 底层设备或容量不一致')
    result={};physical=[]
    for part in parts:
        name,attrs,start,count,group=struct.unpack('<36sIIII',part)
        name=name.rstrip(b'\0').decode('ascii')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,36}',name) or name in result or attrs & ~5 or group>=len(groups) or start+count>len(extents):raise ValueError('无效的 LP 分区')
        rows=[]
        for item in extents[start:start+count]:
            sectors,kind,off,source=struct.unpack('<QIQI',item)
            if kind or source or not sectors or off<first or (off+sectors)*512>capacity:raise ValueError('LP 线性映射越界')
            a,b=off*512,(off+sectors)*512
            if any(a<y and x<b for x,y in physical):raise ValueError('LP 分区映射重叠')
            physical.append((a,b));rows.append([a,b-a])
        result[name]={'size':sum(n for _,n in rows),'extents':rows,'attrs':attrs}
    return result


def super_table(raw,capacity,slot):
    maximum,slots,_=metadata_geometry(raw)
    if slot not in (0,1) or slots<=slot or len(raw)!=12288+2*maximum*slots:raise ValueError('super 元数据长度不一致')
    copies=[]
    for backup in (0,1):
        start=12288+(slot+backup*slots)*maximum
        try:copies.append(lp_table(raw[start:start+maximum],capacity,'super'))
        except ValueError:continue
    if not copies:raise ValueError('目标槽 super 主备 LP 元数据均不可用')
    if any(v!=copies[0] for v in copies):raise ValueError('目标槽 super 主备元数据冲突')
    return copies[0]


def image_table(raw,capacity):
    if len(raw)<4096+128 or len(raw)>2*1024**2:raise ValueError('GSI 映射文件长度异常')
    g=raw[:52]
    if struct.unpack_from('<II',g)!=(0x616c4467,52) or hashlib.sha256(g[:8]+bytes(32)+g[40:]).digest()!=g[8:40]:raise ValueError('GSI geometry 校验失败')
    maximum,slots,block=struct.unpack_from('<III',g,40)
    if slots!=1 or block!=512 or maximum<4096 or maximum>1024**2 or len(raw)-4096>maximum:raise ValueError('不支持的 GSI geometry')
    return lp_table(raw[4096:],capacity,'userdata')


def boot_control(raw,source):
    if len(raw)<65536 or source not in ('_a','_b'):raise ValueError('misc 或来源槽无效')
    b=raw[2048:2080];v=raw[32768:32832];s='ab'.index(source[1]);t=1-s
    if b[:4] not in (b'_a\0\0',b'_b\0\0') or struct.unpack_from('<I',b,4)[0]!=0x42414342 or b[8:12]!=b'\x01\x02\0\0' or any(b[16:28]):raise ValueError('A/B 头或记录的来源槽不一致')
    if zlib.crc32(b[:28])!=struct.unpack_from('<I',b,28)[0]:raise ValueError('A/B CRC 校验失败')
    if v[:7]!=bytes.fromhex('02b00a745602')+bytes([s]) or any(v[7:]):raise ValueError('Virtual A/B 状态或来源槽不一致')
    target=b[12+t*2:14+t*2]
    # Android may mark the OTA target successful before user0 initialization
    # fails. In this observed state only BCB/layout may change, never A/B.
    if (b[:4]==('_'+chr(97+t)).encode()+b'\0\0' and
            b[12+s*2:14+s*2]==b'\x77\0' and target==b'\xf7\0'):
        return 'target-confirmed'
    if b[:4]!=source.encode()+b'\0\0':raise ValueError('记录槽位与 OTA 来源不一致')
    if b[12+s*2:14+s*2]!=b'\xf7\0':raise ValueError('来源槽不是已验证的成功启动状态')
    if target==b'\x6f\0':return 'already-selected'
    if target!=b'\x77\0':raise ValueError('目标槽已有其他尝试或失败状态，拒绝重置重试次数')
    return 'ready'


def recovery_command(raw):
    if raw[:32] not in (bytes(32),b'boot-recovery'.ljust(32,b'\0')):raise ValueError('未知的 BCB 命令或填充内容')
    command=raw[:32].split(b'\0',1)[0]
    args=raw[64:832].split(b'\0',1)[0]
    if any(raw[32:64]) or any(raw[832:2048]):raise ValueError('misc 包含其他启动请求，拒绝覆盖')
    if command not in (b'',b'boot-recovery') or args not in (b'',RECOVERY):raise ValueError('未知 Recovery 请求，拒绝清除')
    if command and args!=RECOVERY:raise ValueError('Recovery 原因不是已验证的 init_user0_failed')
    return bool(command)


def misc_candidate(raw,source,activate):
    if len(raw)!=2*1024**2:raise ValueError('需要完整 2 MiB misc')
    status=boot_control(raw,source)
    if status not in ('ready','target-confirmed') or (status=='target-confirmed' and activate):
        raise ValueError('目标槽已经选中，不重复写入')
    recovery_command(raw)
    out=bytearray(raw);out[:32]=bytes(32)
    if activate:
        target=1-'ab'.index(source[1]);out[2060+target*2]=0x6f
        struct.pack_into('<I',out,2076,zlib.crc32(out[2048:2076]))
    return bytes(out)
