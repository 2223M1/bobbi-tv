"""Explicit attended one-shot TorrServer interruption; never changes a player.

Requires a recent inspected exact BT/native/qualified file receipt. The remote
detached actor must report READY before ARM, owns the single STOP and recovery,
and uses pidfds exclusively. Collect is read-only. No retry after a lost ACK.
Resume is CONT-only, requiring the original actor to have already exited. The
actor withstands controller/SSH loss and normal TERM/INT, not SIGKILL or OOM.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

import ce_115_direct_trial as transport
import ce_torr_fault as inspect_driver
import ce_torr_fault_remote as common
import ce_torr_fault_watchdog as watchdog


def remote_code(expression):
    root = Path(__file__).resolve().parent
    sources = {name: (root / name).read_text(encoding='utf-8') for name in
               ('ce_torr_fault_remote.py','ce_torr_fault_watchdog.py')}
    # Execute definitions in isolated modules; imports perform no remote IO.
    return ('import json,sys,types\nsys.dont_write_bytecode=True\nsources=' + repr(sources) + '\n'
        'for name in ("ce_torr_fault_remote","ce_torr_fault_watchdog"):\n'
        ' module=types.ModuleType(name)\n sys.modules[name]=module\n'
        ' exec(compile(sources[name+".py"],name,"exec"),module.__dict__)\n'
        'try:\n result=' + expression + '\n'
        'except Exception as error:\n result=dict(state="unconfirmed",retry_allowed=False,'
        '**sys.modules["ce_torr_fault_remote"].safe_error(error))\n'
        'print(json.dumps(result))\n')


def launch_code(parameters):
    return remote_code('sys.modules["ce_torr_fault_watchdog"].launch(' + repr(parameters) + ',sources)')


def resume_code(receipt):
    common.require(receipt.get('operation') == 'pause'
        and common.RID.fullmatch(str(receipt.get('run_id')))
        and common.RID.fullmatch(str(receipt.get('request_id')))
        and common.UUID.fullmatch(str(receipt.get('native_instance'))), 'RECEIPT_INVALID')
    args = ','.join(repr(receipt[key]) for key in ('run_id','request_id','native_instance'))
    return remote_code('sys.modules["ce_torr_fault_watchdog"].resume_after_exit(' + args + ')')


def collect_code(run_id):
    require = common.require
    require(common.RID.fullmatch(str(run_id)), 'SCOPE_INVALID')
    path = '/tmp/bobbi-torr-fault-' + run_id + '/result.json'
    return ('import json,pathlib\npath=pathlib.Path(' + repr(path) + ')\n'
        'if not path.is_file(): result=dict(state="unconfirmed",retry_allowed=False)\n'
        'else:\n'
        ' if path.is_symlink() or path.stat().st_size>65536: raise RuntimeError("RECEIPT_INVALID")\n'
        ' result=json.loads(path.read_text())\n'
        ' if result.get("run_id")!=' + repr(run_id) + ': raise RuntimeError("RECEIPT_INVALID")\n'
        'print(json.dumps(result))\n')


def pause_once(source, output, inspection, seconds, sender=transport.dispatch):
    watchdog.stable_inspection(inspection)
    common.require(type(seconds) is int and 1 <= seconds <= watchdog.MAX_SECONDS, 'SCOPE_INVALID')
    run_id = uuid4().hex
    pending = dict(schema=1, operation='pause', state='unconfirmed', run_id=run_id, retry_allowed=False,
        request_id=inspection['native']['request_id'], native_instance=inspection['native']['native_instance'],
        requested_max_seconds=seconds, diagnostic_only=True)
    inspect_driver.exclusive(output, pending)  # Before connect/upload/ARM; survives lost transport ACK.
    try:
        result = sender(source, launch_code(dict(run_id=run_id, inspection=inspection, seconds=seconds)))
        result = dict(pending, **{key: value for key, value in result.items() if key != 'run_id'})
    except Exception as error:
        result = dict(pending, **common.safe_error(error))
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def resume_once(source, output, receipt, sender=transport.dispatch):
    code = resume_code(receipt)
    pending = dict(schema=1, operation='resume', state='unconfirmed', run_id=receipt['run_id'],
                   retry_allowed=False, diagnostic_only=True)
    inspect_driver.exclusive(output, pending)
    try:
        result = dict(pending, **sender(source, code))
    except Exception as error:
        result = dict(pending, **common.safe_error(error))
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('pause','collect','resume'))
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attended', action='store_true')
    parser.add_argument('--inject', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--seconds', type=int, default=60, choices=range(1,61))
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
        if args.operation == 'pause':
            common.require(args.attended and args.inject and not args.resume, 'SCOPE_INVALID')
            result = pause_once(args.transport_source, args.output, receipt, args.seconds)
        elif args.operation == 'resume':
            common.require(args.attended and args.resume and not args.inject, 'SCOPE_INVALID')
            result = resume_once(args.transport_source, args.output, receipt)
        else:
            common.require(not args.attended and not args.inject and not args.resume
                           and receipt.get('operation') == 'pause', 'SCOPE_INVALID')
            inspect_driver.exclusive(args.output, dict(state='unconfirmed', retry_allowed=False))
            result = transport.dispatch(args.transport_source, collect_code(receipt['run_id']))
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(dict(evidence=str(args.output), state=result.get('state'), run_id=result.get('run_id'),
                             retry_allowed=False), ensure_ascii=False))
        return 0 if result.get('state') in ('armed_unconfirmed','restored','already_restored','not_paused') else 1
    except Exception as error:
        print(json.dumps(dict(evidence=str(args.output), retry_allowed=False, **common.safe_error(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
