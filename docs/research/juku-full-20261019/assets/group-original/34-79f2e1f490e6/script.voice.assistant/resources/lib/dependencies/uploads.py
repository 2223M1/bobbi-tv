"""Bounded streaming uploads of pinned upstream archives, independent of selection."""
import hashlib
from pathlib import Path
import secrets
import shutil
import time
from .catalog import catalog


def cache_path(profile, asset):
    return Path(profile) / 'components/.downloads' / (asset['sha256'] + '.part')


def cached(profile, asset):
    path = cache_path(profile, asset)
    return path.is_file() and path.stat().st_size == asset['bytes']


def file_info(profile, asset):
    return {'filename': asset.get('filename', asset['url'].rsplit('/', 1)[-1]),
            'md5': asset.get('md5', ''), 'bytes': asset['bytes'], 'url': asset['url'],
            'cached': cached(profile, asset)}


def locate(root, filename):
    if not isinstance(filename, str) or not filename or len(filename) > 255 or any(
            char in filename for char in ('/', '\\', '\x00')) or filename in ('.', '..'):
        raise ValueError('依赖文件名无效。')
    for identifier, spec in catalog(str(root))['components'].items():
        for asset in spec['assets']:
            if filename == asset.get('filename', asset['url'].rsplit('/', 1)[-1]):
                if len(asset.get('md5', '')) != 32:
                    raise ValueError('该依赖尚未配置 MD5，无法上传。')
                return identifier, asset
    raise ValueError('不支持的依赖文件名：' + filename)


def receive(root, profile, filename, length, source, cancelled, progress):
    identifier, asset = locate(root, filename)
    if length != asset['bytes']:
        raise ValueError('依赖文件大小不符：' + filename)
    target = cache_path(profile, asset)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(target.parent).free < length + asset['expanded_bytes'] + 32 * 1024 * 1024:
        raise ValueError('剩余空间不足，无法接收和解压该依赖。')
    temporary = target.with_name(asset['sha256'] + '.uploading-' + secrets.token_hex(8))
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    done, began = 0, time.monotonic()
    try:
        with temporary.open('xb') as output:
            temporary.chmod(0o600)
            while done < length:
                if cancelled():
                    raise InterruptedError('上传已取消。')
                block = source.read(min(128 * 1024, length - done))
                if not block:
                    raise ValueError('上传中断，请重新选择文件：' + filename)
                output.write(block)
                md5.update(block)
                sha256.update(block)
                done += len(block)
                progress(done, length, done / max(.01, time.monotonic() - began))
        if cancelled():
            raise InterruptedError('上传已取消。')
        if md5.hexdigest() != asset['md5']:
            raise ValueError('文件 MD5 校验失败：' + filename)
        if sha256.hexdigest() != asset['sha256']:
            raise ValueError('文件 SHA256 校验失败：' + filename)
        temporary.replace(target)
        return identifier, asset
    finally:
        temporary.unlink(missing_ok=True)
