"""Verified, cancellable installs. Nothing executes until the receipt is committed."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PROXY = 'https://v6.gh-proxy.org/'


def digest(path, cancelled=lambda: False):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        while True:
            if cancelled():
                raise InterruptedError('下载已取消。')
            block = source.read(1024 * 1024)
            if not block:
                return value.hexdigest()
            value.update(block)


def safe_name(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not value or '..' in path.parts or '\\' in value:
        raise ValueError('组件文件路径无效。')
    return value


def fetch(asset, directory, cancelled, progress, opener=urlopen):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (asset['sha256'] + '.part')
    expected = asset['bytes']
    size = target.stat().st_size if target.exists() else 0
    if size > expected:
        target.unlink(); size = 0
    if size == expected:
        if digest(target, cancelled) == asset['sha256']:
            progress(expected, expected, 0)
            return target
        target.unlink(); size = 0
    url = asset['url']
    if url.startswith('https://github.com/'):
        url = PROXY + url
    if not url.startswith('https://'):
        raise ValueError('组件必须通过 HTTPS 下载。')
    headers = {'User-Agent': 'CoreELEC-VoiceAssistant/2', 'Accept-Encoding': 'identity'}
    if size:
        headers['Range'] = 'bytes=' + str(size) + '-'
    try:
        response = opener(Request(url, headers=headers), timeout=10)
    except HTTPError as error:
        if error.code == 416 and size:
            target.unlink(missing_ok=True)
        raise ValueError('下载服务返回 HTTP ' + str(error.code) + '，请重试。') from None
    with response:
        if cancelled():
            raise InterruptedError('下载已取消。')
        if size and response.status == 206:
            content_range = response.headers.get('Content-Range', '')
            if not content_range.startswith('bytes ' + str(size) + '-') or content_range.rsplit('/', 1)[-1] != str(expected):
                raise ValueError('下载服务返回了错误的续传范围。')
        elif response.status == 200:
            size = 0  # Proxy may ignore Range; replace rather than append.
        else:
            raise ValueError('下载服务返回了无效的响应。')
        began, base = time.monotonic(), size
        with target.open('ab' if size else 'wb') as output:
            target.chmod(0o600)
            progress(size, expected, 0)
            while True:
                if cancelled():
                    raise InterruptedError('下载已取消。')
                block = response.read(128 * 1024)
                if not block:
                    break
                size += len(block)
                if size > expected:
                    raise ValueError('下载文件超过预期大小。')
                output.write(block)
                progress(size, expected, (size - base) / max(.01, time.monotonic() - began))
        if size != expected:
            raise ValueError('下载连接中断，可重试继续下载。')
    progress(size, expected, 0, phase='verifying')
    if digest(target, cancelled) != asset['sha256']:
        target.unlink(missing_ok=True)
        raise ValueError('下载文件 SHA256 校验失败，请重试。')
    return target


def unpack(asset, source, target, cancelled):
    """Only explicitly named regular files/trees; never tar.extractall or links."""
    files, trees = asset.get('files', {}), asset.get('trees', {})
    expected = set(files)
    def copy(stream, name, size):
        safe_name(name)
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('wb') as output:
            remaining = size
            while remaining:
                if cancelled():
                    raise InterruptedError('下载已取消。')
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError('组件压缩包不完整。')
                output.write(block); remaining -= len(block)
        destination.chmod(0o755 if name in asset.get('executables', []) else 0o600)
    if asset.get('format') == 'raw':
        with source.open('rb') as stream:
            copy(stream, asset['target'], source.stat().st_size)
        return
    with tarfile.open(source, 'r:*') as archive:
        total = 0
        for member in archive:
            name = member.name.removeprefix('./')
            destination = files.get(name)
            if destination is None:
                for prefix, mapped in trees.items():
                    if name.startswith(prefix) and len(name) > len(prefix):
                        destination = mapped + name[len(prefix):]
                        break
            if destination is None or member.isdir():
                continue
            if not member.isfile() or member.size < 0:
                raise ValueError('组件压缩包含有无效的文件类型。')
            safe_name(name)
            total += member.size
            if total > asset['expanded_bytes']:
                raise ValueError('组件解压大小超过预期。')
            with archive.extractfile(member) as stream:
                copy(stream, destination, member.size)
            expected.discard(name)
            if not expected and not trees:
                break  # Skip unrelated chunk sizes, example audio and other model variants.
    if expected:
        raise ValueError('组件压缩包缺少所需文件。')


def install(root, profile, identifier, cancelled, progress, opener=urlopen):
    from .catalog import specification, component_path, revision
    spec = specification(root, identifier)
    target = component_path(root, profile, identifier)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_name(target.name + '.installing')
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(mode=0o700)
    downloads = Path(profile) / 'components/.downloads'
    archives = []
    total_bytes = sum(asset['bytes'] for asset in spec['assets'])
    completed_bytes = 0
    try:
        for asset in spec['assets']:
            reserve = asset['bytes'] + asset['expanded_bytes'] + 32 * 1024 * 1024
            if shutil.disk_usage(target.parent).free < reserve:
                raise ValueError('剩余空间不足，需要容纳下载文件及解压后的组件。')
            def report(done, total, speed, phase='downloading'):
                progress(completed_bytes + done, total_bytes, speed, phase=phase)
            source = fetch(asset, downloads, cancelled, report, opener)
            archives.append(source)
            report(asset['bytes'], asset['bytes'], 0, phase='extracting')
            unpack(asset, source, temporary, cancelled)
            completed_bytes += asset['bytes']
        receipt = {}
        for path in temporary.rglob('*'):
            if path.is_file():
                receipt[path.relative_to(temporary).as_posix()] = {'size': path.stat().st_size,
                    'sha256': digest(path, cancelled)}
        for name in spec.get('required', []):
            if name not in receipt:
                raise ValueError('组件安装不完整。')
        if cancelled():
            raise InterruptedError('下载已取消。')
        (temporary / 'installed.json').write_text(json.dumps({'revision': revision(spec), 'files': receipt}), encoding='utf-8')
        (temporary / 'installed.json').chmod(0o600)
        # Existing versions have different paths; an incomplete same-version install is unused.
        if target.exists():
            shutil.rmtree(target)
        temporary.replace(target)
        for path in set(archives):
            path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
