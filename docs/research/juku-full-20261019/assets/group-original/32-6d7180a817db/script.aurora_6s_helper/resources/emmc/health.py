"""Read kernel eMMC health attributes only; no device opens, mounts or ioctls.

Decoding follows mmc-utils pre_eol_info_to_string/life_time_est_to_string:
https://kernel.googlesource.com/pub/scm/utils/mmc/mmc-utils/+/refs/heads/master/mmc_cmds.c
"""
from pathlib import Path
import re


def read_text(path):
    try:
        return path.read_text(encoding='ascii').strip()
    except (OSError, UnicodeError):
        return ''


def byte_value(text):
    if not re.fullmatch(r'(?:0[xX])?[0-9a-fA-F]{1,2}', text):
        return None
    return int(text, 16)


def lifetime(value):
    if value is None:
        return '无法读取（内核未提供或读取失败）'
    if value == 0:
        return '芯片未定义或未提供'
    if 1 <= value <= 10:
        return '估计已使用 %d%%–%d%% 寿命' % ((value - 1) * 10, value * 10)
    if value == 11:
        return '已超过估计设计寿命'
    return '保留值，无法判断'


def pre_eol(value):
    return {None: '无法读取（内核未提供或读取失败）',
            0: '芯片未定义或未提供', 1: '正常',
            2: '预警：备用块消耗已达到预警阈值',
            3: '紧急：备用块消耗已达到紧急阈值'}.get(value, '保留值，无法判断')


def summary(a, b, eol):
    if eol == 3 or 11 in (a, b):
        return '芯片已报告寿命告警，建议尽快备份并考虑更换设备。'
    if eol == 2 or 10 in (a, b):
        return '芯片已报告磨损预警，建议及时备份重要数据。'
    if eol == 1 and all(v is not None and 1 <= v <= 9 for v in (a, b)):
        return '当前已报告指标未见寿命告警。'
    return '健康信息不完整，不能据此确认 eMMC 健康。'


def probe(sys_block=Path('/sys/class/block')):
    devices = []
    for block in sorted(Path(sys_block).glob('mmcblk*')):
        # Exclude SD cards, boot partitions, RPMB and ordinary partitions.
        if not re.fullmatch(r'mmcblk[0-9]+', block.name):
            continue
        card = block / 'device'
        if read_text(card / 'type') != 'MMC':
            continue
        tokens = read_text(card / 'life_time').split()
        a, b = [byte_value(t) for t in tokens] if len(tokens) == 2 else (None, None)
        eol = byte_value(read_text(card / 'pre_eol_info'))
        sectors = read_text(block / 'size')
        devices.append(dict(device='/dev/' + block.name,
                            name=read_text(card / 'name') or '未知',
                            manufacturer_id=read_text(card / 'manfid') or '未知',
                            date=read_text(card / 'date') or '未知',
                            capacity_bytes=int(sectors) * 512 if sectors.isdecimal() else None,
                            lifetime_a=a, lifetime_b=b, pre_eol=eol,
                            summary=summary(a, b, eol)))
    return {'devices': devices, 'text': format_report(devices)}


def format_report(devices):
    if not devices:
        return '未检测到可读取的 eMMC 设备。当前内核可能未提供相关接口。'
    def field(label, value, meaning):
        raw = '0x%02X' % value if value is not None else '不可用'
        return '%s：%s（%s）' % (label, meaning(value), raw)
    sections = []
    for d in devices:
        capacity = '%.2f GiB' % (d['capacity_bytes'] / 1024**3) if d['capacity_bytes'] is not None else '未知'
        sections.append('\n'.join([
            d['summary'],
            '芯片：%s　容量：%s' % (d['name'], capacity),
            '设备：%s　厂商 ID：%s　生产日期：%s' % (d['device'], d['manufacturer_id'], d['date']),
            field('寿命估计 A', d['lifetime_a'], lifetime),
            field('寿命估计 B', d['lifetime_b'], lifetime),
            field('备用块状态', d['pre_eol'], pre_eol)]))
    sections.append('寿命数值按约 10% 分档，表示已使用寿命，并非精确剩余百分比；A/B 对应的存储区域由厂商定义。备用块状态与可用存储空间无关。\n'
                    '这些是芯片经内核提供的估计值，部分内核在启动时缓存，不能预测具体剩余年限，也不能排除其他故障。本功能只读取状态，不执行读写测速。')
    return '\n\n'.join(sections)


if __name__ == '__main__':
    import json
    print(json.dumps(probe(), ensure_ascii=False))
