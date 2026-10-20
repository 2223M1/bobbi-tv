"""Fixed offline maintenance entry, invoked only by an exclusive native host."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.offline_updates import SignedBundle, load_trust, rollback_engine
from bobbi_platform.maintenance_lease import WindowsLease, CoreELECLease, expected_request
from bobbi_platform.updates import UpdateError


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('apply', 'rollback', 'recover'))
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--addons-root', type=Path, required=True)
    parser.add_argument('--work-root', type=Path, required=True)
    parser.add_argument('--profile', choices=('windows', 'coreelec'), required=True)
    parser.add_argument('--lease-pipe-handle', type=int)
    parser.add_argument('--ce-stopped-lease', action='store_true')
    args = parser.parse_args(argv)
    if (args.operation == 'apply') != (args.bundle is not None):
        parser.error('Only apply requires a local signed bundle')
    expected = expected_request(args.operation, args.bundle, args.addons_root, args.work_root, args.profile)
    if args.profile == 'windows' and not args.ce_stopped_lease:
        lease = WindowsLease(args.lease_pipe_handle, expected)
    elif args.profile == 'coreelec' and args.ce_stopped_lease and args.lease_pipe_handle is None:
        lease = CoreELECLease(args.work_root)
    else:
        raise UpdateError('Exclusive lifecycle lease is missing')
    try:
        trust = load_trust()
        if args.operation == 'apply':
            with SignedBundle(args.bundle, trust, args.profile) as source:
                engine = source.engine(args.addons_root, args.work_root, lease.idle, lease.commit)
                result = engine.apply(source.raw, source.signature)
        else:
            engine = rollback_engine(trust, args.profile, args.addons_root, args.work_root, lease.idle, lease.commit)
            result = engine.rollback() if args.operation == 'rollback' else engine.available()
        print(json.dumps(dict(state='complete', operation=args.operation, result=result), sort_keys=True))
    finally:
        lease.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # No local paths/credentials/raw remote failures in launcher diagnostics.
        print(json.dumps(dict(state='failed', error=type(error).__name__)))
        sys.exit(1)
