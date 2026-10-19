"""Bounded AML_RES v2 codec and the Aurora RGB565 boot image format."""
import gzip
import hashlib
import io
import struct
import warnings
import zlib

PARTITION_SIZE = 8 * 1024**2
STOCK_SHA256 = '77499f3c323e5697207efd26d612e8ad1821cbb4bb232d00fd6b8ed7d12127dd'
MAX_IMAGE = 32 * 1024**2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gunzip(data, limit):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        result = f.read(limit + 1)
    if len(result) > limit:
        raise ValueError('压缩素材解压后超出大小限制')
    return result


def stock(path):
    raw = gunzip(path.read_bytes(), PARTITION_SIZE)
    if len(raw) != PARTITION_SIZE or digest(raw) != STOCK_SHA256:
        raise ValueError('内置原厂 Logo 素材校验失败')
    unpack(raw)
    return raw


def unpack(raw):
    if len(raw) != PARTITION_SIZE:
        raise ValueError('Logo 分区容量不受支持')
    crc, version, magic, size, count, align = struct.unpack_from('<II8sIII', raw)
    if version != 2 or magic != b'AML_RES!' or align != 16 or not 1 <= count <= 64:
        raise ValueError('Logo 不是支持的 AML_RES v2 资源包；可选择恢复内置原厂素材')
    if not 64 + count*64 <= size <= len(raw) or size % 16:
        raise ValueError('Logo 资源包长度不正确')
    if zlib.crc32(raw[4:size]) ^ 0xffffffff != crc:
        raise ValueError('Logo 资源包 CRC 校验失败；可选择恢复内置原厂素材')
    entries = []; end = 64 + count*64
    for i in range(count):
        h = raw[64+i*64:128+i*64]
        marker, reserved, length, start, r2, nxt, r3, index = struct.unpack_from('<8I', h)
        name = h[32:64].split(b'\0')[0].decode('ascii')
        if (marker != 0x27051956 or reserved or r2 or r3 or index != i | count << 8
                or nxt != (128+i*64 if i+1 < count else 0)
                or not name or name in [e[0] for e in entries]
                or start % 16 or start < end or not length or start+length > size):
            raise ValueError('Logo 资源项结构不受支持')
        entries.append((name, raw[start:start+length])); end = (start+length+15)//16*16
    if sum(name == 'bootup' for name, _ in entries) != 1:
        raise ValueError('Logo 资源包没有唯一的 bootup 图片')
    return entries


def pack(entries):
    count = len(entries); body = bytearray(64+count*64)
    struct.pack_into('<II8sIII', body, 0, 0, 2, b'AML_RES!', 0, count, 16)
    for i, (name, payload) in enumerate(entries):
        off = 64+i*64; start = len(body)
        name_bytes = name.encode('ascii')
        if len(name_bytes) > 31:raise ValueError('Logo 资源名称过长')
        struct.pack_into('<8I', body, off, 0x27051956, 0, len(payload), start, 0,
                         off+64 if i+1<count else 0, 0, i | count << 8)
        body[off+32:off+64] = name_bytes.ljust(32,b'\0')
        body.extend(payload); body.extend(bytes((-len(body))%16))
    if len(body) > PARTITION_SIZE:raise ValueError('生成的 Logo 超出分区容量')
    struct.pack_into('<I', body, 16, len(body))
    struct.pack_into('<I', body, 0, zlib.crc32(body[4:]) ^ 0xffffffff)
    result = bytes(body).ljust(PARTITION_SIZE,b'\0')
    unpack(result)
    return result


def boot_image(raw):
    payload = dict(unpack(raw))['bootup']
    if payload.startswith(b'\x1f\x8b'):payload = gunzip(payload, MAX_IMAGE)
    return decode(payload)


def pillow_bytes(data):
    """Promote a 56-byte BMP DIB to V4 for older Pillow, in memory only."""
    if len(data) < 18 or data[:2] != b'BM' or struct.unpack_from('<I', data, 14)[0] != 56:
        return data
    if len(data) < 70:
        raise ValueError('BMP 图片头不完整')
    offset = struct.unpack_from('<I', data, 10)[0]
    if not 70 <= offset <= len(data):
        raise ValueError('BMP 像素数据位置无效')
    # V3 already contains all four channel masks. V4 appends color-space
    # fields; pixel encoding, row padding and orientation remain unchanged.
    header = bytearray(data[:70] + bytes(52))
    struct.pack_into('<I', header, 2, len(data) + 52)
    struct.pack_into('<I', header, 10, offset + 52)
    struct.pack_into('<I', header, 14, 108)
    struct.pack_into('<I', header, 70, 0x73524742)  # LCS_sRGB
    return bytes(header) + data[70:]


def decode(data):
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ValueError('当前系统缺少 Pillow 图片库，无法转换或预览第一屏') from exc
    if len(data) > MAX_IMAGE:raise ValueError('图片文件不能超过 32 MiB')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(pillow_bytes(data))) as source:
            if source.format not in ('PNG','JPEG','BMP'):
                raise ValueError('只支持 PNG、JPEG 和 BMP 图片')
            if source.width * source.height > 24_000_000:
                raise ValueError('图片不能超过 2400 万像素')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGBA')
        canvas = Image.new('RGB',(1920,1080),'black')
    image = ImageOps.contain(image,(1920,1080), getattr(Image,'Resampling',Image).LANCZOS)
    canvas.paste(image,((1920-image.width)//2,(1080-image.height)//2),image)
    return canvas


def rgb565(image):
    if image.size != (1920,1080):raise ValueError('启动图像尺寸必须为 1920×1080')
    # Match the stock 56-byte DIB, BI_BITFIELDS and bottom-up RGB565 rows.
    width,height=image.size; pixels=bytearray(width*height*2); rgb=image.convert('RGB').tobytes()
    for y in range(height):
        dst=(height-1-y)*width*2; src=y*width*3
        for x in range(width):
            r,g,b=rgb[src+x*3:src+x*3+3]
            struct.pack_into('<H',pixels,dst+x*2,((r>>3)<<11)|((g>>2)<<5)|(b>>3))
    header=bytearray(70)
    struct.pack_into('<2sIHHI',header,0,b'BM',70+len(pixels),0,0,70)
    struct.pack_into('<IiiHHIIiiII',header,14,56,width,height,1,16,3,len(pixels),0,0,0,0)
    struct.pack_into('<4I',header,54,0xf800,0x07e0,0x001f,0)
    return bytes(header+pixels)


def replace_boot(raw, data):
    entries=unpack(raw); bmp=rgb565(decode(data))
    candidate=pack([(name,gzip.compress(bmp,mtime=0) if name=='bootup' else content)
                    for name,content in entries])
    return candidate
