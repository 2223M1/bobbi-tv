"""Record traceback and encoding context without changing Kodi's global locale."""
import json
import locale
import os
import sys
import traceback


def exception_details(context):
    info = {
        'python': sys.version,
        'preferred_encoding': locale.getpreferredencoding(False),
        'filesystem_encoding': sys.getfilesystemencoding(),
        'utf8_mode': sys.flags.utf8_mode,
        'locale': {key: os.environ.get(key) for key in
                   ('LANG', 'LC_ALL', 'LC_CTYPE', 'PYTHONUTF8', 'PYTHONIOENCODING')},
    }
    return '[Aurora6S] ' + context + '\n' + json.dumps(info, ensure_ascii=True) + '\n' + traceback.format_exc()


def user_message(error):
    """Render backend errors without exposing Python frames in a Kodi dialog.

    Callers retain the original exception/worker output in logs. Do not change
    validation or infer whether writes occurred from the exception alone.
    """
    import re
    import subprocess
    raw = str(error).strip()
    kind = type(error).__name__ if isinstance(error, BaseException) else ''
    if isinstance(error, subprocess.TimeoutExpired):
        return '操作等待超时，请查看日志确认当前状态后再处理，不要重复启动写入任务。'
    if 'Traceback (most recent call last):' in raw:
        endings = re.findall(r'^([\w.]+(?:Error|Exception)|Exception):\s*(.*)$', raw, re.MULTILINE)
        if not endings:
            return '操作未完成，详细原因请查看日志。'
        kind, raw = endings[-1]
    else:
        match = re.match(r'^([\w.]+(?:Error|Exception)|Exception):\s*(.*)$', raw, re.DOTALL)
        if match:
            kind, raw = match.groups()
    translations = {
        'Nested storage mount requires review: ': '发现 /storage 下的额外挂载：{value}\n请先停止相关挂载服务并卸载该路径，再重试。不要删除文件或目录内容；助手不会自动卸载它。',
        'Nested filesystem encountered: ': '发现 /storage 下的额外挂载：{value}\n请先停止相关挂载服务并卸载该目录，再重试。不要删除目录内容；助手不会自动卸载它。',
        'Nested storage mounts require explicit review: ': '发现 /storage 下的额外挂载：{value}\n请先停止相关挂载服务并卸载该目录，再重试。不要删除目录内容。',
        'Read-only filesystem check failed: ': '残留文件系统未通过只读检查：{value}\n已停止自动修复，请保留日志进一步检查。',
        'Boot payload MD5 mismatch: ': '内置 CE 启动文件校验不一致：{value}\n不能继续自动修复，请保留日志检查文件完整性。',
        'Missing boot file: ': '缺少内置 CE 启动文件：{value}\n不能继续自动修复。',
        'Missing internal MD5: ': '缺少内置 CE 校验文件：{value}\n不能继续自动修复。',
        'Preserved region changed: ': '检测到应保持不变的区域发生变化：{value}\n请停止后续操作并保留日志，先检查设备状态。',
    }
    for prefix, template in translations.items():
        if raw.startswith(prefix):
            return template.format(value=raw[len(prefix):].splitlines()[0][:300])
    known = {
        'Special source files need explicit migration review': '发现套接字、管道或设备节点等特殊文件，不能直接迁移。请先停止相关服务后重试；仍失败时请提供日志。',
        'Source has ACLs but rsync cannot preserve them': '当前复制工具无法保留源文件的访问权限属性，已停止迁移。请提供日志检查系统工具。',
        'Source has extended attributes but rsync cannot preserve them': '当前复制工具无法保留源文件的扩展属性，已停止迁移。请提供日志检查系统工具。',
        'Cannot inspect extended attributes on this Python build': '当前 Python 不支持读取文件扩展属性，无法完成迁移检查。',
        'Unrecognized rsync capability output': '无法识别当前 rsync 的功能，请提供日志检查系统工具。',
        'Requires original 29-partition view; not an already valid dual layout': '当前分区布局不符合 OTA 修复条件；若双系统布局已正常，无需执行此修复。',
        'No helper FAT32 boot volume at original userdata start': '未找到可恢复的 CE 启动区，当前状态不符合自动布局修复条件。',
        'No helper ext4 data volume at expected boot+gap boundary': '未找到可恢复的 CE 数据区，当前状态不符合自动布局修复条件。',
        'Pending bootloader/recovery message in misc': '检测到待处理的引导或恢复请求，已停止自动修复，请提供日志检查。',
        'Virtual A/B merge state is active or unsupported': 'Android OTA 合并尚未结束或状态不受支持，不能自动修复布局。',
    }
    if raw in known:
        return known[raw]
    errno = re.match(r'\[Errno (\d+)\]\s*(.*)', raw, re.DOTALL)
    if errno:
        hints = {28:'存储空间不足，请检查外置盘剩余空间。', 13:'没有访问权限，请检查文件或设备权限。',
                 30:'目标文件系统只读，无法写入。', 5:'发生磁盘读写错误，请检查存储设备并保留日志。',
                 95:'当前文件系统或驱动不支持所需操作，请提供日志进一步检查。',
                 22:'系统拒绝了当前读写参数，请提供日志检查具体操作。',
                 2:'所需文件或设备不存在，请查看日志中的路径。'}
        if int(errno[1]) in hints:
            return hints[int(errno[1])] + '\n错误编号：' + errno[1]
    # Unexpected programming failures get a short message, not source code.
    if kind and kind not in ('ValueError','RuntimeError','OSError','SystemExit'):
        return '操作未完成（%s），详细原因请查看日志。' % kind
    if not raw:
        return '操作未完成，详细原因请查看日志。'
    return raw[:700] + ('\n更多信息请查看日志。' if len(raw)>700 else '')
