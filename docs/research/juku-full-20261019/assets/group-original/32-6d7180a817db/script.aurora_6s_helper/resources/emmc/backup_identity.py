"""Read acquisition identity or a separately audited legacy identity supplement.

The supplement preserves original records. It is not created automatically from
whatever device happens to be connected, nor a replacement for image hashing.
"""
import json
from pathlib import Path
import re
from check_backup import safe_file, sha

RECORDS = ('manifest.json', 'probe-before.json', 'probe-after.json')
BINDING = 'legacy-identity.json'
EVIDENCE = 'legacy-layout-ticket.json'


def read_identity(folder):
    folder = Path(folder)
    saved = json.loads(safe_file(folder, 'probe-before.json').read_text())
    if saved.get('cid') or not (folder / BINDING).exists():
        return saved
    binding = json.loads(safe_file(folder, BINDING).read_text())
    if binding.get('schema') != 1 or binding.get('kind') != 'audited-legacy-layout-ticket':
        raise ValueError('旧备份身份补充格式不支持')
    cid = binding.get('cid', '')
    if not isinstance(cid, str) or not re.fullmatch(r'[0-9a-f]{32}', cid):
        raise ValueError('旧备份身份补充的 CID 无效')
    hashes = binding.get('record_sha256', {})
    if set(hashes) != set(RECORDS):
        raise ValueError('旧备份身份补充缺少原始记录校验')
    for name in RECORDS:
        if sha(safe_file(folder, name)) != hashes[name]:
            raise ValueError('旧备份原始记录已改变：' + name)
    ticket_path = safe_file(folder, EVIDENCE)
    if sha(ticket_path) != binding.get('evidence_sha256'):
        raise ValueError('旧备份历史身份依据已改变')
    ticket = json.loads(ticket_path.read_text())
    if (ticket.get('kind') != 'metadata-only-reset-layout-trial'
            or ticket.get('cid') != cid
            or Path(ticket.get('backup', '')).name != binding.get('original_backup_name')
            or ticket.get('emmc_bytes') != saved['emmc_bytes']
            or ticket.get('hashes', {}).get('original', {}).get('mpt') != saved['mpt_sha256']):
        raise ValueError('旧备份与历史安装身份记录不匹配')
    for key in ('emmc_bytes', 'android_models', 'boot_areas'):
        if binding.get(key) != saved.get(key):
            raise ValueError('旧备份身份补充不匹配：' + key)
    return dict(saved, cid=cid, cid_source='audited-legacy-layout-ticket')
