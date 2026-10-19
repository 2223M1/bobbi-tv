# SPDX-License-Identifier: GPL-2.0-or-later
"""Files/options for the backed-up RTL8852 NG/NO wake installation."""
import hashlib
import json
from pathlib import Path
import re
import shlex

SOURCE = Path(__file__).resolve().parents[1] / 'wake'
ROOT = '/storage/.config/aurora6s-wake/'
SYSTEMD = '/storage/.config/system.d/'
TRIAL_UNITS = ('aurora-bt-heartbeat-trial','aurora-bt-recovery-trial','aurora-bt-capture-trial',
               'aurora-bt-journal-trial','aurora-bt-native-auto','aurora-bt-native-auto2')

def supported(profile):
    return profile['branch'] in ('ng','no') and profile['board'] in ('6s','4pro') and profile['chip'] == 'rtl8852'

def files(profile=None):
    # None retains the exact 1.9.0 format-6 backup target set.
    if profile is not None and not supported(profile):
        raise ValueError('不支持此设备的蓝牙唤醒修复')
    result={n:ROOT+n for n in ('common.py','runtime.py','aurora_bt_native.ko','rtl8852bs_config.wake')}
    result.update({'aurora6s-wake.service':SYSTEMD+'aurora6s-wake.service',
                   'suspend.conf':SYSTEMD+'systemd-suspend.service.d/90-aurora6s-wake.conf',
                   'dtb.img':'/flash/dtb.img','load-drivers.sh':'/storage/.config/aurora6s-ng/load-drivers.sh'})
    if profile is not None:
        result.pop('aurora_bt_native.ko')
        if profile['branch'] == 'no':
            for name in ('dtb.img','load-drivers.sh'): result.pop(name)
        elif profile['board'] == '4pro':
            for name in ('dtb.img','load-drivers.sh'): result['ng-4pro/'+name]=result.pop(name)
    return result

def extra_targets(profile=None):
    result=files(profile)
    # Preserve the format-7 NG backup schema: snapshot/remove the old module,
    # and restore it when rolling back an upgrade to the previous implementation.
    if profile is not None and profile['branch']=='ng':
        result['aurora_bt_native.ko']=ROOT+'aurora_bt_native.ko'
    result.update({'settings.json':ROOT+'settings.json','config.ini':'/flash/config.ini',
        'enable-link':SYSTEMD+'multi-user.target.wants/aurora6s-wake.service',
        'old-ethernet-hook':SYSTEMD+'systemd-suspend.service.d/91-aurora-ethernet-repeat.conf',
        'old-native-hook':'/run/systemd/system/systemd-suspend.service.d/90-aurora-native-marker.conf',
        'old-heartbeat-hook':'/run/systemd/system/aurora-bt-heartbeat-trial.service.d/90-native-marker.conf'})
    if profile is not None and profile['branch']=='no': result.pop('config.ini')
    return result

def verify():
    expected=json.loads((SOURCE/'hashes.json').read_text())
    all_files=set(files(dict(branch='ng',board='6s',chip='rtl8852'))) | set(files(dict(branch='ng',board='4pro',chip='rtl8852')))
    if set(expected)!=all_files: raise ValueError('待机修复包清单不完整')
    for name,digest in expected.items():
        if hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('待机修复包校验失败：'+name)

def verify_firmware():
    path=Path('/lib/firmware/rtlbt/rtl8852bs_fw')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != '1e27d21231c08010d5dcd4c24d294762f8ea2f608cb533a5955e0df3bd725440':
        raise ValueError('此蓝牙固件尚未通过待机唤醒适配，未改动硬件配置')

def validate(data):
    # Upgrade the initial fixed-list format without retaining stale selections.
    if not isinstance(data, dict) or type(data.get('ethernet_off')) is not bool:
        raise ValueError('唤醒设置格式错误')
    if set(data) == {'peers', 'ethernet_off'}:
        peers = data['peers']
        if (not isinstance(peers, list) or len(peers) > 10
                or any(not isinstance(p, str) or not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', p) for p in peers)
                or len(set(peers)) != len(peers)):
            raise ValueError('旧唤醒名单格式错误')
    elif set(data) != {'remote_mode', 'ethernet_off'} or data['remote_mode'] != 'auto':
        raise ValueError('唤醒设置格式错误')
    return dict(remote_mode='auto', ethernet_off=data['ethernet_off'])

def boot_config(text):
    # Preserve existing boot/disk/rootopt and all unrelated content. Reject dynamic
    # shell expressions rather than evaluating them in this installer.
    begin='# BEGIN Aurora 6S NG suspend\n'; end='# END Aurora 6S NG suspend\n'
    text=re.sub(re.escape(begin)+'.*?'+re.escape(end),'',text,flags=re.S)
    values=[]
    for line in text.splitlines():
        if re.match(r'^\s*coreelec\s*=',line):
            value=line.split('=',1)[1].strip()
            tokens=shlex.split(value,comments=True)
            if len(tokens)!=1 or any(x in tokens[0] for x in ('$', '`','\n')):
                raise ValueError('config.ini 的 coreelec 参数含动态表达式，请先改成固定参数')
            values=tokens[0].split()
    if 'pd_ignore_unused' not in values: values.append('pd_ignore_unused')
    return text.rstrip()+'\n\n'+begin+'coreelec='+shlex.quote(' '.join(values))+'\n'+end

def choose(dialog):
    try: old=validate(json.loads(Path(ROOT+'settings.json').read_text()))
    except (OSError,ValueError): old={'remote_mode':'auto','ethernet_off':False}
    option=dialog.select('待机前是否关闭有线网卡？',[
        '关闭：能缩短约3秒的恢复时间；待机期间有线网络唤醒不可用',
        '保持开启：保留有线网络唤醒条件；恢复可能较慢'],
        preselect=0 if old['ethernet_off'] else 1)
    if option<0:return None
    return dict(remote_mode='auto',ethernet_off=option==0)
