"""Explicit attended one-shot diagnostic runner; never ordinary product proof.

start uploads short-lived scripts into a new private /tmp directory and issues
RunScript once. collect only reads its safe receipt. A lost start ACK is not
permission to replay. No addon installation, settings write or state rollback.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import ce_115_direct_trial as driver
import ce_115_direct_remote as shared
from ce_115_direct_kodi import ROUTES, TOOL_REVISION, checked_route


def checked_inspection(inspection, target):
    shared.require(isinstance(inspection, dict) and inspection.get('state') == 'validated'
        and inspection.get('mode') == 'read_only' and inspection.get('operation') == 'inspect'
        and inspection.get('diagnostic_only') is True and inspection.get('product_proof') is False
        and inspection.get('playback_performed') is False
        and inspection.get('baseline_request') == target['request_id']
        and inspection.get('selection_identity') == target['selection_identity']
        and inspection.get('source_key') == target['source_key']
        and inspection.get('title') == target['title'] and inspection.get('size') == target['size']
        and inspection.get('media') == target['media'], 'INSPECT_CHANGED')
    return inspection


def start_code(parameters):
    parameters = dict(parameters, route=checked_route(parameters.get('route', 'direct')),
                      tool_revision=TOOL_REVISION)
    root = Path(__file__).resolve().parent
    files = {name: (root / name).read_text(encoding='utf-8') for name in
             ('ce_115_direct_remote.py', 'ce_115_direct_kodi.py')}
    files['run.py'] = ('import sys\nsys.dont_write_bytecode=True\nfrom ce_115_direct_kodi import kodi_entry\n'
        'kodi_entry(' + repr(parameters) + ', ' + repr('/tmp/bobbi-115-direct-' + parameters['run_id']) + ')\n')
    return ('import json,os,pathlib,shutil,subprocess\n'
        'directory=pathlib.Path(' + repr('/tmp/bobbi-115-direct-' + parameters['run_id']) + ')\n'
        'directory.mkdir(mode=0o700,exist_ok=False)\n'
        'files=' + repr(files) + '\n'
        'for name,code in files.items():\n'
        ' with (directory/name).open("x",encoding="utf-8") as output: output.write(code)\n'
        'command=shutil.which("kodi-send")\n'
        'if not command: raise RuntimeError("DIAGNOSTIC_LAUNCH_UNAVAILABLE")\n'
        'subprocess.run([command,"--action=RunScript("+str(directory/"run.py")+")"],'
        'check=True,timeout=4,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n'
        'print(json.dumps(dict(state="launched",run_id=' + repr(parameters['run_id']) + ',retry_allowed=False)))\n')


def collect_code(receipt):
    run_id = receipt.get('run_id')
    import re
    shared.require(re.fullmatch('[0-9a-f]{32}', str(run_id)) is not None, 'DIAGNOSTIC_SCOPE')
    return ('import hashlib,json,pathlib\npath=pathlib.Path(' + repr('/tmp/bobbi-115-direct-' + run_id + '/result.json') + ')\n'
        'if not path.is_file(): print(json.dumps(dict(state="unconfirmed",retry_allowed=False)))\n'
        'else:\n'
        ' if path.stat().st_size>2*1024*1024: raise RuntimeError("DIAGNOSTIC_RESULT_TOO_LARGE")\n'
        ' raw=path.read_bytes()\n result=json.loads(raw)\n'
        ' if result.get("run_id")!=' + repr(run_id) + ': raise RuntimeError("DIAGNOSTIC_RESULT_MISMATCH")\n'
        ' print(json.dumps(dict(artifact=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))\n')


def decode_result(raw, descriptor, receipt):
    expected = '/tmp/bobbi-115-direct-' + receipt['run_id'] + '/result.json'
    shared.require(descriptor.get('artifact') == expected and len(raw) <= 2 * 1024 * 1024
        and descriptor.get('bytes') == len(raw) and descriptor.get('sha256') == hashlib.sha256(raw).hexdigest(),
        'DIAGNOSTIC_SCOPE')
    result = json.loads(raw)
    shared.require(result.get('run_id') == receipt['run_id'] and result.get('request_id') == receipt['request_id']
                   and result.get('diagnostic_only') is True and result.get('product_proof') is False,
                   'DIAGNOSTIC_SCOPE')
    shared.require(checked_route(result.get('route', 'direct')) == checked_route(receipt.get('route', 'direct')),
                   'DIAGNOSTIC_SCOPE')
    return result


def fetch_result(source, receipt):
    sys.path.insert(0, str(source / 'ui-redesign/runtime/ssh-python'))
    spec = importlib.util.spec_from_file_location('ce_115_collect_transport', source / 'ui-redesign/tools/device_transport.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client, wire = transport.connect()
    try:
        rc, descriptor, diagnostic = wire.readonly(client, collect_code(receipt).encode(), deadline_seconds=15)
        shared.require(not rc and not diagnostic, 'OWNER_UNAVAILABLE')
        if descriptor.get('state') == 'unconfirmed':
            return descriptor
        expected = '/tmp/bobbi-115-direct-' + receipt['run_id'] + '/result.json'
        shared.require(descriptor.get('artifact') == expected, 'DIAGNOSTIC_SCOPE')
        with client.open_sftp() as sftp:
            with sftp.open(expected, 'rb') as stream:
                raw = stream.read(2 * 1024 * 1024 + 1)
        return decode_result(raw, descriptor, receipt)
    finally:
        client.close()


def stop_code(receipt):
    import re
    shared.require(all(re.fullmatch('[0-9a-f]{32}', str(receipt.get(k))) for k in ('run_id', 'request_id'))
        and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', str(receipt.get('native_instance'))),
        'OTHER_INSTANCE')
    params = {key: receipt[key] for key in ('run_id', 'request_id', 'native_instance')}
    params['command_id'] = uuid4().hex
    directory = '/tmp/bobbi-115-direct-' + receipt['run_id']
    return ('import json,sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,' + repr(directory) + ')\n'
        'from ce_115_direct_kodi import standalone_stop\n'
        'print(json.dumps(standalone_stop(' + repr(params) + ',' + repr(directory) + ')))\n')


def run_once(source, output, parameters, sender=driver.dispatch):
    parameters = dict(parameters, route=checked_route(parameters.get('route', 'direct')),
                      tool_revision=TOOL_REVISION)
    receipt = dict(schema=1, operation='start', state='unconfirmed', run_id=parameters['run_id'],
                   request_id=parameters['request_id'], route=parameters['route'], tool_revision=TOOL_REVISION,
                   retry_allowed=False, diagnostic_only=True, product_proof=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        result = sender(source, start_code(parameters))
        receipt.update(result)
    except Exception as error:
        receipt.update(shared.safe_error(error))
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('start', 'collect', 'stop'))
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--inspect', dest='inspection', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--attended', action='store_true', help='Explicit supervised diagnostic playback')
    parser.add_argument('--duration', type=int, default=45, choices=range(10, 61))
    parser.add_argument('--route', choices=ROUTES, default='direct',
                        help='Attended start route; direct remains the default')
    args = parser.parse_args()
    try:
        if args.operation == 'start':
            shared.require(args.attended and args.baseline and args.inspection and not args.receipt, 'DIAGNOSTIC_SCOPE')
            target = driver.target_from_baseline(args.baseline)
            inspection = checked_inspection(json.loads(args.inspection.read_text(encoding='utf-8')), target)
            result = run_once(args.transport_source, args.output, dict(run_id=uuid4().hex, request_id=uuid4().hex,
                target=target, inspection=inspection, duration=args.duration, route=args.route))
        else:
            shared.require(args.receipt and not args.baseline and not args.inspection
                           and args.route == 'direct'
                           and (args.attended if args.operation == 'stop' else not args.attended), 'DIAGNOSTIC_SCOPE')
            receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
            # Exclusive local output before even a read prevents accidental loss of evidence.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(dict(state='unconfirmed', retry_allowed=False), stream)
                stream.flush()
                os.fsync(stream.fileno())
            result = (driver.dispatch(args.transport_source, stop_code(receipt)) if args.operation == 'stop'
                      else fetch_result(args.transport_source, receipt))
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(evidence=str(args.output), state=result.get('state'),
                             run_id=result.get('run_id'), retry_allowed=False)))
        return 0 if result.get('state') in ('launched', 'completed', 'stopped') else 1
    except Exception as error:
        print(json.dumps(dict(evidence=str(args.output), retry_allowed=False, **shared.safe_error(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
