#!/usr/bin/env python3
"""Read-only migration inventory and rsync dry-run for the running external CE."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from aurora_emmc import probe, plan, read
from file_attributes import ignored_attribute_names,rsync_xattr_filters
from storage_mounts import storage_source

EXCLUDE = ('aurora-emmc-backups', 'aurora-emmc-staging', 'aurora-emmc-jobs', 'lost+found')


def scan_tree(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('A real source directory is required')
    device = root.stat().st_dev
    counts = dict(files=0, directories=0, symlinks=0, other=0, xattr_objects=0)
    attributes = set()
    if not hasattr(os, 'listxattr'):
        raise ValueError('Cannot inspect extended attributes on this Python build')

    def inspect(path):
        info = path.lstat()
        if info.st_dev != device:
            raise ValueError('Nested filesystem encountered: ' + str(path))
        mode = info.st_mode
        kind = ('symlinks' if stat.S_ISLNK(mode) else 'directories' if stat.S_ISDIR(mode)
                else 'files' if stat.S_ISREG(mode) else 'other')
        counts[kind] += 1
        names = os.listxattr(path, follow_symlinks=False)
        if names:
            counts['xattr_objects'] += 1
            attributes.update(names)

    def fail(error):
        raise error

    for base, directories, files in os.walk(root, followlinks=False, onerror=fail):
        if Path(base) == root:
            directories[:] = [d for d in directories if d not in EXCLUDE]
        inspect(Path(base))
        for name in directories:
            path = Path(base) / name
            if path.is_symlink():
                inspect(path)
        for name in files:
            inspect(Path(base) / name)
    return dict(counts=counts, xattr_names=sorted(attributes))


def rsync_flags(version, inventory, metadata_fallback=False):
    # Separate ACLs from other attributes because rsync implements them separately.
    names = set(inventory['xattr_names']) - set(ignored_attribute_names())
    acl = {x for x in names if x.startswith('system.posix_acl_')}
    if inventory['counts']['other']:
        raise ValueError('Special source files need explicit migration review')
    if acl and 'no ACLs' in version and not metadata_fallback:
        raise ValueError('Source has ACLs but rsync cannot preserve them')
    if names - acl and 'no xattrs' in version and not metadata_fallback:
        raise ValueError('Source has extended attributes but rsync cannot preserve them')
    if not version.startswith('rsync  version') or 'Capabilities:' not in version:
        raise ValueError('Unrecognized rsync capability output')
    return '-aHnx' + ('A' if acl and 'no ACLs' not in version else '') + ('X' if names - acl and 'no xattrs' not in version else '')


def run():
    report = probe()
    plan(report, 20, 1024, 'reset-data', 16)
    with storage_source() as source:
        inventory = scan_tree(source)
        version = subprocess.run(['rsync', '--version'], check=True, capture_output=True, text=True).stdout
        flags = rsync_flags(version, inventory)
        with tempfile.TemporaryDirectory(prefix='aurora-storage-dryrun-', dir='/tmp') as dest:
            args = ['rsync', flags, '--numeric-ids', '--stats'] + rsync_xattr_filters(flags)
            args += ['--exclude=/' + x + '/' for x in EXCLUDE]
            args += [str(source)+'/', dest + '/']
            p = subprocess.run(args, capture_output=True, text=True, timeout=180,
                               env={**os.environ, 'LC_ALL': 'C'})
            if p.returncode:
                raise ValueError('rsync dry-run failed: ' + p.stderr)
    return dict(schema=1, dry_run=True, consistent_snapshot=False, copied_files=0,
                installation_ready=False, inventory=inventory, excludes=EXCLUDE,
                rsync_version=version, command=args, stats=p.stdout,
                notes=['No source files were copied or modified; temporary empty destination removed.',
                       'Live estimate only. Repeat checks and copy with writers stopped.',
                       'Excluded backup/staging directories must remain on external recovery storage.'])


if __name__ == '__main__':
    try:
        print(json.dumps(run(), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit('Storage inventory refused: ' + str(exc))
