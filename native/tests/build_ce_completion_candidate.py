"""Apply the canonical completion delta to a frozen CE host, build in isolation.

The prior CE source/archives, maintained toolchain, and all unrelated objects are
read-only. Recompile all VideoPlayer layout consumers, prove the old host relinks
exactly, and link/verify a separate candidate. Does not access a device.
"""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predecessor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('schema_build',root/'ce-jsonrpc-schema-20261022/build_isolated.py')
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    sha = legacy.sha
    previous = json.loads((args.predecessor/'build-result.json').read_text())
    verified = json.loads((args.predecessor/'artifact-verification.json').read_text())
    expected = previous['candidate_sha256']
    assert previous['state'] == 'BUILT_NOT_DEPLOYED' and previous['original_tree_unchanged']
    assert verified['state'] == 'VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED'
    assert sha(args.predecessor/'candidate.bin') == expected == verified['candidate_sha256']
    assert {str(p.relative_to(args.predecessor/'source-candidate')):sha(p)
            for p in (args.predecessor/'source-candidate').rglob('*') if p.is_file()} == previous['source_sha256']
    assert all(sha(path) == digest for path,digest in previous['inputs'].items())
    args.output.mkdir(parents=True,exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='ce-completion-',dir=args.output))
    snapshot = run/'source-candidate'
    shutil.copytree(args.predecessor/'source-candidate',snapshot)
    patch = root/'patches/0006-bobbi-completion-observation.patch'
    # CE's frozen source has one extra include and component logging. Adapt
    # only those unchanged context lines; added implementation is identical.
    delta = patch.read_text()
    contexts = {
        '   CLog::Log(LOGDEBUG, "CVideoPlayer::FlushBuffers - flushing buffers");':
        '   logComponentM(LOGDEBUG, LOGVIDEO, "CVideoPlayer::FlushBuffers - flushing buffers");',
        '+#include "BobiCompletion.h"\n #include "DVDMessageQueue.h"':
        '+#include "BobiCompletion.h"\n #include "DVDInputStreams/DVDInputStream.h"\n #include "DVDMessageQueue.h"'}
    for old,new in contexts.items():
        assert delta.count(old)==1,'CANONICAL_CE_CONTEXT_DRIFT'
        delta=delta.replace(old,new)
    delta=delta.encode()
    subprocess.run(['git','apply','--recount','--check'],input=delta,cwd=snapshot,check=True)
    subprocess.run(['git','apply','--recount'],input=delta,cwd=snapshot,check=True)
    units = (
        ('xbmc/cores/VideoPlayer/VideoPlayer.cpp','build/cores/VideoPlayer/CMakeFiles/VideoPlayer.dir/VideoPlayer.cpp.o','build/cores/VideoPlayer/VideoPlayer.a'),
        ('xbmc/application/ApplicationPlayer.cpp','build/application/CMakeFiles/application.dir/ApplicationPlayer.cpp.o','build/application/application.a'),
        ('xbmc/cores/playercorefactory/PlayerCoreConfig.cpp','build/cores/playercorefactory/CMakeFiles/playercorefactory.dir/PlayerCoreConfig.cpp.o','build/cores/playercorefactory/playercorefactory.a'))
    deps = subprocess.check_output([str(legacy.TOOLS/'ninja'),'-C',str(legacy.BUILD),'-t','deps'],text=True)
    header = 'xbmc/cores/VideoPlayer/VideoPlayer.h'
    consumers = {block.splitlines()[0].split(':',1)[0] for block in deps.split('\n\n')
                 if any(line.strip() == str(legacy.SOURCE/header) for line in block.splitlines())}
    assert consumers == {row[1] for row in units}, 'VIDEOPLAYER_LAYOUT_CONSUMER_DRIFT'
    inputs = dict(previous['inputs'])
    for name in ('build-result.json','artifact-verification.json','candidate.bin',*[Path(a).name for a in legacy.ARCHIVES]):
        path=args.predecessor/name
        inputs[str(path)] = sha(path)
    inputs[str(patch)] = sha(patch)
    for path in (args.predecessor/'source-candidate').rglob('*'):
        if path.is_file(): inputs[str(path)] = sha(path)
    report = dict(state='STARTED',predecessor_sha256=expected,canonical_patch_sha256=sha(patch),
        ce_context_patch_sha256=hashlib.sha256(delta).hexdigest(),
        source_sha256={str(p.relative_to(snapshot)):sha(p) for p in snapshot.rglob('*') if p.is_file()},
        inputs=inputs,commands={},layout_consumers=sorted(consumers),objects={},retained_archive_members={})

    def execute(argv,label,cwd=legacy.BUILD):
        report['commands'][label]=list(map(str,argv))
        with (run/(label+'.log')).open('w') as stream:
            subprocess.run(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=1200)

    def compile_unit(unit):
        source,original,archive=unit
        obj=run/(Path(source).name+'.o')
        argv=shlex.split(legacy.command(original))
        argv[1:1]=['-I'+str(snapshot/'xbmc')]
        argv+=['-iquote',str((legacy.SOURCE/source).parent)]
        for option,value in (('-o',obj),('-MF',str(obj)+'.d'),('-MT',obj),('-c',snapshot/source)):
            legacy.output_arg(argv,option,value)
        execute(argv,Path(source).stem+'-compile')
        dependencies=legacy.deps(str(obj)+'.d')
        assert str(snapshot/header) in dependencies and str(legacy.SOURCE/header) not in dependencies
        report['objects'][source]=dict(sha256=sha(obj),depfile_sha256=sha(str(obj)+'.d'))
        return obj,archive

    raw=legacy.command('kodi.bin')
    assert raw.startswith(': && ') and raw.endswith(' && :')
    link=shlex.split(raw[5:-5])
    assert not any(arg in ('&&',';','|') for arg in link)
    replacements={archive:run/Path(archive).name for archive in legacy.ARCHIVES}
    def relink(label):
        argv=[str(replacements.get(arg,arg)) for arg in link]
        binary=run/(label+'.unstripped')
        legacy.output_arg(argv,'-o',binary)
        execute(argv,label+'-link')
        stripped=run/(label+'.bin')
        shutil.copyfile(binary,stripped)
        execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-strip'),'--strip-unneeded',str(stripped)],label+'-strip')
        report[label+'_sha256']=sha(stripped)
        return stripped
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            objects=list(pool.map(compile_unit,units))
        for archive,target in replacements.items():
            shutil.copyfile(args.predecessor/Path(archive).name,target)
        assert sha(relink('predecessor-relink')) == expected,'PREDECESSOR_RELINK_MISMATCH'
        for obj,archive in objects:
            execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ar'),'r',str(replacements[archive]),str(obj)],obj.stem+'-archive')
            execute([str(legacy.TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'),str(replacements[archive])],obj.stem+'-ranlib')
        for archive,target in replacements.items():
            replaced=tuple(obj.name for obj,path in objects if path==archive)
            report['retained_archive_members'][archive]=legacy.retained_members(args.predecessor/Path(archive).name,target,replaced)
        candidate=relink('candidate')
        assert sha(candidate) != expected and b'completion_observation' in candidate.read_bytes()
        assert legacy.binary_method(candidate) == legacy.binary_method(args.predecessor/'candidate.bin')
        for flags in (['-A'],['-d']):
            before=legacy.tool('readelf',*flags,args.predecessor/'candidate.bin')
            after=legacy.tool('readelf',*flags,candidate)
            if flags==['-d']:
                def needed(text):
                    return [line.split(')',1)[-1] for line in text.splitlines()
                            if any(token in line for token in ('(NEEDED)','(RPATH)','(RUNPATH)'))]
                before,after=needed(before),needed(after)
            assert before==after,'NATIVE_ABI_OR_DEPENDENCY_DRIFT'
        report.update(state='BUILT_NOT_DEPLOYED',architecture_and_dependencies_unchanged=True,
                      binary_bobicontrol_schema_unchanged=True,bytes=candidate.stat().st_size)
    except BaseException:
        report['state']='FAILED_NOT_DEPLOYED'
        raise
    finally:
        report['original_tree_unchanged']=all(sha(path)==digest for path,digest in inputs.items())
        (run/'build-result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(dict(run=str(run),state=report['state'],candidate_sha256=report.get('candidate_sha256'),unchanged=report['original_tree_unchanged'])))
        assert report['original_tree_unchanged']


if __name__=='__main__':
    main()
