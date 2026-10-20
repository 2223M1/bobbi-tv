"""Offline checks for recovering the Aurora dual layout; no device I/O."""
import copy,hashlib,struct,zlib
import policy
from aurora_emmc import parse_mpt
from layout_trial import fdt

sha=lambda data:hashlib.sha256(data).hexdigest()
FIELDS=('index','name','offset','size','flags')
def geometry(rows):return [[p[k] for k in FIELDS] for p in rows]
def android_state(raw):
    """Describe opaque state for preservation, never select or repair a slot."""
    if len(raw)!=65536:raise ValueError('Short misc read')
    b=raw[2048:2080]
    valid=(struct.unpack_from('<I',b,4)[0]==0x42414342 and b[8]==1 and
           b[9]&7==2 and zlib.crc32(b[:28])==struct.unpack_from('<I',b,28)[0])
    suffix=b[:4].rstrip(b'\0')
    recorded=suffix.decode('ascii') if valid and suffix in (b'_a',b'_b') else None
    v=raw[32768:32832]
    vab=(v[5] if v[0]==2 and struct.unpack_from('<I',v,1)[0]==0x56740ab0 else
         0 if not any(v) else None)
    warnings=[]
    if any(raw[:2048]):warnings.append('Android 存在待处理的 Recovery/启动请求，修复会原样保留；若启动后提示清空数据，请先不要确认。')
    if vab!=0:warnings.append('Android OTA 状态尚未确认空闲，修复不处理升级、合并或回滚。')
    if not recorded:warnings.append('Android A/B 元数据不能明确解析；仅保留，不指定启动槽位。')
    return {'misc_sha256':sha(raw),'ab_metadata_valid':valid,
            'recorded_suffix':recorded,'virtual_ab_status':vab,
            'pending_boot_message':bool(any(raw[:2048])), 'warnings':warnings,
            'policy':'preserve-only; no boot slot selected'}

def select_slot(raw):
    if len(raw)!=65536:raise ValueError('Short misc read')
    # Do not silently override pending recovery / update requests.
    if any(raw[:2048]):raise ValueError('Pending bootloader/recovery message in misc')
    b=raw[2048:2080]
    if struct.unpack_from('<I',b,4)[0]!=0x42414342 or b[8]!=1 or b[9]&7!=2:
        raise ValueError('Unsupported A/B control format')
    if zlib.crc32(b[:28])!=struct.unpack_from('<I',b,28)[0]:raise ValueError('A/B control CRC mismatch')
    slots=[]
    for i in range(2):
        v=b[12+2*i]
        slots.append(dict(slot='_'+chr(97+i),priority=v&15,tries=(v>>4)&7,successful=bool(v&128),corrupt=bool(b[13+2*i]&1)))
    suffix=b[:4].rstrip(b'\0').decode('ascii')
    if suffix not in ('_a','_b'):raise ValueError('Invalid misc suffix')
    # Require agreement between metadata suffix, known Amlogic selector and success.
    a,c=slots
    selected=0 if a['priority']>c['priority'] or (a['priority']==c['priority'] and a['successful']) else 1
    s=slots[selected]
    if s['slot']!=suffix or s['priority']==0 or not s['tries'] or not s['successful'] or s['corrupt']:
        raise ValueError('No unambiguous previously successful boot slot; needs manual review')
    # Both the legacy field and Android Virtual A/B message must be idle.
    if b[10]&7 or b[11]:raise ValueError('A/B merge/rollback state requires manual review')
    v=raw[32768:32832]
    if any(v):
        if v[0]!=2 or struct.unpack_from('<I',v,1)[0]!=0x56740ab0 or v[5]!=0:
            raise ValueError('Virtual A/B merge state is active or unsupported')
    return {'selected':suffix,'slots':slots,'misc_sha256':sha(raw)}

def check_environment(env, allow_short=False):
    """Check supported boot scripts without deriving any environment writes."""
    if env.get('active_slot') not in ('normal','_a','_b'):
        raise ValueError('Unrecognized persisted active_slot')
    # Validate the actual persisted value; normal is supported without guessing.
    policy.environment_change(env,'install')
    count,_=policy.scanner(env['cfgloademmc'])
    if count<29 and not allow_short:
        raise ValueError('Existing cfgloademmc does not cover CE partition 29; layout-only repair cannot change it')


def discover_layout(live,read_at):
    """Infer the helper's CE-first layout. No job files, fixed CID or data size."""
    policy.identity(live)
    kind,_,_=policy.layouts(live)
    if kind!='stock':raise ValueError('Requires original 29-partition view; not an already valid dual layout')
    mib=1024**2;gib=1024**3;start=live['mpt']['partitions'][-1]['offset']
    # Published helper format: 1GiB FAT + 8MiB gap + ext4 + 8MiB gap + Android.
    # This constant is a format constraint, NOT a guessed per-device capacity.
    fat=read_at(start,4096)
    if len(fat)!=4096 or fat[510:512]!=b'\x55\xaa' or fat[82:90]!=b'FAT32   ' or fat[71:82].rstrip()!=b'CE_AURORA':
        raise ValueError('No helper FAT32 boot volume at original userdata start')
    sector=struct.unpack_from('<H',fat,11)[0];count=struct.unpack_from('<I',fat,32)[0]
    if sector!=512 or not 0<=gib-sector*count<4096:
        # mkfs.fat may round to 1KiB alignment; known image is 4096B short.
        if sector!=512 or gib-sector*count!=4096:raise ValueError('FAT volume does not match helper 1GiB boot format')
    data_start=start+gib+8*mib
    sb=read_at(data_start+1024,1024)
    if len(sb)!=1024 or sb[56:58]!=b'\x53\xef' or sb[120:136].rstrip(b'\0')!=b'CE_AURORA_DATA':
        raise ValueError('No helper ext4 data volume at expected boot+gap boundary')
    log=struct.unpack_from('<I',sb,24)[0]
    if log!=2:raise ValueError('Only helper 4KiB ext4 block format supported')
    blocks=struct.unpack_from('<I',sb,4)[0]
    if struct.unpack_from('<I',sb,96)[0]&0x80:blocks|=struct.unpack_from('<I',sb,336)[0]<<32
    size=blocks*4096
    if size<4*gib or size%mib or live['emmc_bytes']%mib:
        raise ValueError('Cannot uniquely infer MiB-aligned helper partition from filesystem size')
    from aurora_emmc import plan
    target=plan(live,20,1024,'reset-data',8,ce_bytes=size)['partitions']
    fake=copy.deepcopy(live);fake['mpt']['partitions']=[dict(p,sysfs_matches=True) for p in target]
    if policy.layouts(fake)[0]!='dual':raise ValueError('Inferred geometry not supported')
    if target[29]['offset']!=data_start or target[-1]['size']<8*gib:raise ValueError('Insufficient Android tail')
    return target,{'method':'helper-format-from-filesystems','fat_volume_bytes':sector*count,'ce_data_filesystem_bytes':size,
                   'gap_bytes':8*mib,'alignment_bytes':mib,
                   'android_tail':'inferred from supported layout, encrypted data integrity not verified'}

def bump_dtb(current,candidate):
    from extract_recovery_metadata import validate_dtb_slots
    validate_dtb_slots(current);validate_dtb_slots(candidate)
    stamp=max(struct.unpack_from('<I',data,off+262136)[0] for data in (current,candidate) for off in (0,262144))+1
    if stamp>0xffffffff:raise ValueError('DTB generation overflow')
    new=bytearray(candidate)
    for off in (0,262144):
        struct.pack_into('<I',new,off+262136,stamp)
        struct.pack_into('<I',new,off+262140,sum(struct.unpack_from('<65535I',new,off))&0xffffffff)
    validate_dtb_slots(new);return bytes(new)


def validate_kernel_header(header, size):
    """CE NO ships an Android v0 boot wrapper; also recognize raw arm64 Image."""
    if len(header) < 64:
        raise ValueError('Truncated kernel header')
    if header[:8] == b'ANDROID!':
        kernel, _, ramdisk, _, second, _, _, page, version = struct.unpack_from('<9I', header, 8)
        if version != 0 or page not in (2048, 4096, 8192, 16384) or not kernel:
            raise ValueError('Unsupported Android kernel wrapper')
        aligned = lambda n: ((n + page - 1) // page) * page
        if page + aligned(kernel) + aligned(ramdisk) + aligned(second) > size:
            raise ValueError('Truncated Android kernel payload')
    elif header[56:60] == b'ARM\x64':
        image_size = struct.unpack_from('<Q', header, 16)[0]
        if image_size and image_size > size:
            raise ValueError('Truncated arm64 kernel payload')
    else:
        raise ValueError('Unrecognized CE kernel header')


def validate_env_config(text):
    """Select the reviewed eMMC entry; CE also lists a NAND fallback."""
    entries=[line.split('#',1)[0].split() for line in text.splitlines()]
    emmc=[line for line in entries if line and line[0]=='/dev/env']
    if len(emmc)!=1:
        raise ValueError('Expected exactly one /dev/env entry in fw_env.config')
    try:
        valid=len(emmc[0])==4 and [int(x,0) for x in emmc[0][1:]]==[0,65536,65536]
    except ValueError:
        valid=False
    if not valid:
        raise ValueError('Unsupported /dev/env offset/size in fw_env.config: '+' '.join(emmc[0]))
    return '/dev/env 0x0 0x10000 0x10000\n'
