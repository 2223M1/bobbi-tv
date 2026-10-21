"""Transactional preview of skin.bobbi.cinema + plugin.video.bobbi dialog assets.

Explicit --source-root selects the UI worktree, including its uncommitted files.
No business Python, addon.xml, settings, accounts or installer journal is replaced.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile

from ce_ui_preview_remote import allowed

REMOTE = Path(__file__).with_name('ce_ui_preview_remote.py')
COMPONENTS = {'skin': 'addons/skin.bobbi.cinema', 'dialogs': 'addons/plugin.video.bobbi/resources/skins'}


def package(source_root, destination, installed, scopes):
    files = {}
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as zipped:
        for component in scopes:
            root = source_root / COMPONENTS[component]
            if not root.is_dir() or root.is_symlink():
                raise ValueError('Invalid source component: ' + component)
            for path in sorted(root.rglob('*')):
                if path.is_symlink():
                    raise ValueError('Source contains symlink')
                name = component + '/' + path.relative_to(root).as_posix()
                if not path.is_file() or not allowed(name):
                    continue
                raw = path.read_bytes()
                sha = hashlib.sha256(raw).hexdigest()
                if installed[component].get(path.relative_to(root).as_posix()) == sha:
                    continue
                if path.suffix == '.xml':
                    ET.fromstring(raw)
                elif path.suffix == '.py':
                    compile(raw, name, 'exec')
                if len(raw) > 64 * 1024 * 1024:
                    raise ValueError('Preview file too large')
                zipped.writestr(name, raw)
                files[name] = sha
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('status', 'deploy', 'rollback', 'screenshot'))
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--transport-source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--scope', choices=('skin', 'dialogs', 'both'), default='both')
    parser.add_argument('--transaction')
    args = parser.parse_args()
    if args.mode == 'deploy' and not args.source_root:
        parser.error('deploy requires --source-root')
    if args.mode in ('rollback', 'screenshot') and not args.transaction:
        parser.error(args.mode + ' requires --transaction')
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.transport_source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('preview_wire', args.transport_source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    record = dict(mode=args.mode, transaction=args.transaction, operations=[])
    def remote(mode, params):
        script = 'MODE=' + repr(mode) + '\nPARAMS=' + repr(params) + '\n' + REMOTE.read_text(encoding='utf-8')
        rc, result, diag = wire.readonly(client, script.encode('utf-8'), deadline_seconds=55)
        record['operations'].append(dict(mode=mode, exit_code=rc, result=result, diagnostic_present=bool(diag)))
        if rc or diag or result.get('error'):
            raise RuntimeError(result.get('code', 'REMOTE_PREVIEW_FAILED'))
        return result
    try:
        if args.mode == 'deploy':
            status = remote('status', {})
            transaction = 'preview-' + stamp
            record['transaction'] = transaction
            record['source_root'] = str(args.source_root.resolve())
            directory = args.output / transaction
            directory.mkdir()
            archive = directory / 'candidate.zip'
            scopes = list(COMPONENTS) if args.scope == 'both' else [args.scope]
            files = package(args.source_root, archive, status['manifest'], scopes)
            record['files'] = files
            if not files:
                record['state'] = 'unchanged'
            else:
                components = {name.split('/')[0] for name in files}
                prepared = remote('prepare', dict(transaction=transaction, files=files,
                    before={key: status['manifest'][key] for key in components}))
                with client.open_sftp() as sftp:
                    sftp.put(str(archive), prepared['remote_path'])
                record['result'] = remote('deploy', dict(transaction=transaction,
                    sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
        else:
            record['result'] = remote(args.mode, dict(transaction=args.transaction))
        screenshot = record.get('result', {}).get('screenshot')
        if screenshot:
            local = args.output / (args.mode + '-' + stamp + '.png')
            with client.open_sftp() as sftp:
                sftp.get(screenshot['remote_path'], str(local))
            if hashlib.sha256(local.read_bytes()).hexdigest() != screenshot['sha256']:
                raise RuntimeError('SCREENSHOT_CHANGED')
            screenshot['local_path'] = str(local)
    except Exception as error:
        record['error'] = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
    finally:
        client.close()
        output = args.output / (args.mode + '-' + stamp + '.json')
        output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(evidence=str(output), transaction=record['transaction'],
        changed_files=len(record.get('files', {})), state=record.get('state', record.get('result', {}).get('state')),
        screenshot=record.get('result', {}).get('screenshot', {}).get('local_path'), error=record.get('error')), ensure_ascii=False))
    return int('error' in record)


if __name__ == '__main__':
    raise SystemExit(main())
