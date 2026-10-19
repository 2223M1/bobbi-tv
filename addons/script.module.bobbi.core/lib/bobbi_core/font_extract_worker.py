"""Short-lived, low-priority 7-Zip adapter; not a service or playback worker.

The caller supplies an already verified same-release archive. Output remains
private candidate material until the resource owner binds actual font faces.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bobbi_core.font_archive import ARCHIVE_LIMIT, EXPANSION_LIMIT, FONT_LIMIT, parse_listing
from bobbi_core.fonts import inspect_font

TOOL_HASH = '7f198102ba757b47da28d62fcb16a89afaad865f47a9feee4d489718cd3a219a'

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): value.update(chunk)
    return value.hexdigest()

def checked_file(path, limit):
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('No symlink worker inputs')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:
        raise ValueError('Worker file type/size')
    return info

def run(args):
    import resource
    if sys.platform!='linux': raise ValueError('Bounded Linux child required')
    checked_file(args.tool,4*1024*1024)
    if digest(args.tool)!=TOOL_HASH: raise ValueError('Archive helper identity drift')
    checked_file(args.archive,ARCHIVE_LIMIT)
    if digest(args.archive)!=args.sha256: raise ValueError('Archive input drift')
    if any(p.is_symlink() for p in (args.output,*args.output.parents)):
        raise ValueError('No symlink output')
    args.output.mkdir(mode=0o700,exist_ok=False)
    # These limits apply only to this short-lived worker and its decoder.
    resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(FONT_LIMIT,FONT_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    os.nice(19)
    started=time.monotonic()
    report=dict(state='CANDIDATE_INCOMPLETE',archive_sha256=args.sha256,tool_sha256=TOOL_HASH,commands=[],fonts=[])
    def call(arguments,name):
        remaining=40-(time.monotonic()-started)
        if remaining<=0: raise TimeoutError('Shared archive deadline')
        argv=[str(args.tool),*arguments,'-mmt=1','-sccUTF-8','-spd','-y','--',str(args.archive)]
        with (args.output/(name+'.stdout')).open('xb') as out, (args.output/(name+'.stderr')).open('xb') as err:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            try: code=process.wait(timeout=remaining)
            except BaseException:
                process.kill(); process.wait()
                raise
        report['commands'].append(dict(argv=argv,exit_code=code))
        if code: raise ValueError('Archive helper rejected content')
    try:
        call(['l','-slt'],'listing')
        path=args.output/'listing.stdout'
        checked_file(path,2*1024*1024)
        members=parse_listing(path.read_bytes())
        # Only font members, selected exactly with wildcard processing off.
        # All entries (including skipped ones) were checked for paths/links.
        destination=args.output/'unpacked'
        destination.mkdir(mode=0o700)
        remaining=40-(time.monotonic()-started)
        if remaining<=0: raise TimeoutError('Shared archive deadline')
        argv=[str(args.tool),'x','-o'+str(destination),'-mmt=1','-sccUTF-8','-spd','-y','--',str(args.archive),
              *[r['path'] for r in members]]
        with (args.output/'extract.stdout').open('xb') as out,(args.output/'extract.stderr').open('xb') as err:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            try: code=process.wait(timeout=remaining)
            except BaseException:
                process.kill(); process.wait()
                raise
        report['commands'].append(dict(argv=argv,exit_code=code))
        if code: raise ValueError('Archive extraction failed')
        expected={r['path']:r['bytes'] for r in members}
        actual={p.relative_to(destination).as_posix():p.stat().st_size for p in destination.rglob('*') if p.is_file()}
        if actual!=expected or sum(actual.values())>EXPANSION_LIMIT:
            raise ValueError('Extracted member set/size differs')
        for name,size in expected.items():
            if time.monotonic()-started>=40: raise TimeoutError('Shared archive deadline')
            path=destination/name
            checked_file(path,FONT_LIMIT)
            parsed=inspect_font(path.read_bytes())
            report['fonts'].append(dict(parsed,path=str(path),archive_member=name,origin='same_release_pack'))
        report['state']='EXTRACTED_FONTS_NOT_BOUND_OR_LOADED'
    finally:
        report.update(seconds=time.monotonic()-started,maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      child_maxrss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(state=report['state'],fonts=len(report['fonts']),output=str(args.output))))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tool',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())

if __name__=='__main__': main()
