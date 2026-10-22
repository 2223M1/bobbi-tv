"""Rebuild only the missing schema registrar on exact frozen 8bb2 archives.

No maintained-tree writes, Ninja build invocation, device access or deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
TARGET = Path('/opt/am6b-maintainable-r10-20260922/build.CoreELEC-Amlogic-ng.arm-21')
SOURCE = TARGET/'build/kodi-e0614d7a6713369bbcfe42152223f1cdaec3dbf1'
BUILD = SOURCE/'.armv8a-libreelec-linux-gnueabihf'
TOOLS = TARGET/'toolchain/bin'
PREDECESSOR = Path('/mnt/d/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431')
PREDECESSOR_SHA = '8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14'
PROOF_SHA = '0c6069fe71c83c491dd48f363ca44efb3c2dbd775aa8fd0aaccc944c6aca52c9'
VERIFICATION_SHA = 'c0be45eeb70302f8a1b1ff93fffaefd4c8b1116fe4132d95ddd80651747f00ff'
RPC_SOURCE = 'xbmc/interfaces/json-rpc/JSONRPC.cpp'
RPC_SHA = 'b94dae82ab3d5b2b0390be2359112f51f15df4a953d4fe8fa1145e99bc83e7bb'
RPC_OBJECT = 'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONRPC.cpp.o'
DESCRIPTION_SOURCE = 'xbmc/interfaces/json-rpc/JSONServiceDescription.cpp'
DESCRIPTION_OBJECT = 'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONServiceDescription.cpp.o'
SCHEMA_CONSUMERS = {RPC_OBJECT, DESCRIPTION_OBJECT}
ARCHIVES = ('build/cores/VideoPlayer/VideoPlayer.a', 'build/application/application.a',
            'build/interfaces/json-rpc/jsonrpc_interface.a',
            'build/cores/playercorefactory/playercorefactory.a')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def command(target):
    return subprocess.check_output([str(TOOLS/'ninja'), '-C', str(BUILD), '-t',
                                    'commands', target], text=True).splitlines()[-1]


def tool(name, *args, binary=False):
    return subprocess.check_output([str(TOOLS/('armv8a-libreelec-linux-gnueabihf-'+name)),
                                    *map(str, args)], text=not binary)


def output_arg(argv, option, value):
    assert argv.count(option) == 1
    argv[argv.index(option)+1] = str(value)


def schema_consumers():
    output = subprocess.check_output([str(TOOLS/'ninja'), '-C', str(BUILD), '-t', 'deps'], text=True)
    header = str(BUILD/'build/ServiceDescription.h')
    consumers = {block.splitlines()[0].split(':', 1)[0] for block in output.split('\n\n')
                 if any(line.strip() == header for line in block.splitlines())}
    assert consumers == SCHEMA_CONSUMERS, 'SCHEMA_CONSUMER_DRIFT:'+repr(sorted(consumers))
    # Independently close the direct include set, rather than relying on a
    # possibly incomplete/stale dependency database alone.
    includes = {str(path.relative_to(SOURCE)) for path in (SOURCE/'xbmc').rglob('*.cpp')
                if re.search(r'^\s*#\s*include\s*[<"]ServiceDescription\.h[>"]',
                             path.read_text(errors='strict'), re.M)}
    assert includes == {RPC_SOURCE, DESCRIPTION_SOURCE}, 'SCHEMA_INCLUDE_DRIFT:'+repr(sorted(includes))
    return sorted(consumers), sorted(includes)


def deps(path):
    return Path(path).read_text().replace('\\\n', ' ').split()


def binary_method(path):
    prefix = b'"Player.BobiControl": {'
    records = [json.loads(b'{'+part+b'}')['Player.BobiControl']
               for part in Path(path).read_bytes().split(b'\0') if part.startswith(prefix)]
    assert len(records) == 1, 'BINARY_BOBICONTROL_COUNT:'+str(len(records))
    return records[0]


def retained_members(before, after, replaced=()):
    members = tool('ar', 't', before).splitlines()
    assert members == tool('ar', 't', after).splitlines(), 'ARCHIVE_MEMBER_DRIFT'
    assert len(members) == len(set(members)), 'AMBIGUOUS_ARCHIVE_MEMBER'
    result = {}
    for member in members:
        previous = tool('ar', 'p', before, member, binary=True)
        current = tool('ar', 'p', after, member, binary=True)
        if member not in replaced:
            assert previous == current, 'RETAINED_MEMBER_CHANGED:'+member
            result[member] = hashlib.sha256(current).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    assert sha(PREDECESSOR/'build-result.json') == PROOF_SHA
    assert sha(PREDECESSOR/'artifact-verification.json') == VERIFICATION_SHA
    assert sha(PREDECESSOR/'candidate.bin') == PREDECESSOR_SHA
    previous = json.loads((PREDECESSOR/'build-result.json').read_text())
    assert previous['state'] == 'BUILT_NOT_DEPLOYED' and previous['original_tree_unchanged']
    assert sha(SOURCE/RPC_SOURCE) == sha(HERE/'candidate'/RPC_SOURCE) == RPC_SHA
    inputs = dict(previous['inputs'])
    assert all(sha(path) == digest for path, digest in inputs.items()), 'MAINTAINED_INPUT_DRIFT'
    consumers, include_sources = schema_consumers()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run = args.output_dir/('run-'+str(time.time_ns()))
    run.mkdir()
    snapshot = run/'source-candidate'
    shutil.copytree(HERE/'candidate', snapshot)
    hashes = {str(p.relative_to(snapshot)): sha(p) for p in snapshot.rglob('*') if p.is_file()}
    assert set(hashes) == set(previous['source_sha256']) | {RPC_SOURCE}
    assert all(hashes[name] == digest == sha(PREDECESSOR/'source-candidate'/name)
               for name, digest in previous['source_sha256'].items()), 'PREDECESSOR_SOURCE_DRIFT'
    for path in (SOURCE/RPC_SOURCE, BUILD/RPC_OBJECT):
        inputs[str(path)] = sha(path)
    schema = SOURCE/'xbmc/interfaces/json-rpc/schema'
    for name in ('version.txt', 'license.txt', 'types.json', 'notifications.json'):
        inputs[str(schema/name)] = sha(schema/name)
    predecessor_inputs = {str(p): sha(p) for p in PREDECESSOR.rglob('*') if p.is_file()}
    report = dict(state='STARTED', inputs=inputs, baseline_inputs=previous['inputs'],
                  additional_inputs={p: digest for p, digest in inputs.items() if p not in previous['inputs']},
                  predecessor_inputs=predecessor_inputs, predecessor_sha256=PREDECESSOR_SHA,
                  predecessor_proof=str(PREDECESSOR/'build-result.json'),
                  baseline_sha256=previous['baseline_sha256'], baseline_proof=previous['baseline_proof'],
                  builder_sha256=sha(__file__), source_sha256=hashes, commands={},
                  schema_consumers=consumers, schema_include_sources=include_sources,
                  recompiled_units=[RPC_SOURCE], retained_archive_members={},
                  original_tree_unchanged=False, predecessor_unchanged=False)
    def execute(argv, label, cwd):
        report['commands'][label] = [str(arg) for arg in argv]
        with (run/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                           timeout=1200, check=True)
    raw = command('kodi.bin')
    assert raw.startswith(': && ') and raw.endswith(' && :')
    link = shlex.split(raw[5:-5])
    assert not any(arg in ('&&', ';', '|') for arg in link)
    replacements = {archive: run/Path(archive).name for archive in ARCHIVES}
    def relink(label):
        argv = [str(replacements.get(arg, arg)) for arg in link]
        binary = run/(label+'.unstripped')
        output_arg(argv, '-o', binary)
        execute(argv, label+'-link', BUILD)
        stripped = run/(label+'.bin')
        shutil.copyfile(binary, stripped)
        execute([str(TOOLS/'armv8a-libreelec-linux-gnueabihf-strip'), '--strip-unneeded', str(stripped)],
                label+'-strip', run)
        report[label+'_sha256'] = sha(stripped)
        return stripped
    try:
        generated = run/'generated'
        generated.mkdir()
        execute([str(TOOLS/'JsonSchemaBuilder'), str(schema/'version.txt'), str(schema/'license.txt'),
                 str(snapshot/'xbmc/interfaces/json-rpc/schema/methods.json'), str(schema/'types.json'),
                 str(schema/'notifications.json')], 'schema', generated)
        header = generated/'ServiceDescription.h'
        old_header = PREDECESSOR/'candidate/generated/ServiceDescription.h'
        assert header.read_bytes() == old_header.read_bytes(), 'GENERATED_SCHEMA_CHANGED'
        report['generated_header_sha256'] = sha(header)
        old_object = PREDECESSOR/'candidate'/DESCRIPTION_SOURCE
        old_object = old_object.with_name(old_object.name+'.o')
        old_depfile = Path(str(old_object)+'.d')
        assert str(old_header) in deps(old_depfile)
        assert str(BUILD/'build/ServiceDescription.h') not in deps(old_depfile)
        member = tool('ar', 'p', PREDECESSOR/'jsonrpc_interface.a', 'JSONServiceDescription.cpp.o', binary=True)
        assert hashlib.sha256(member).hexdigest() == sha(old_object), 'RETAINED_CONSUMER_OBJECT_MISMATCH'
        report['reused_schema_consumer'] = dict(source=DESCRIPTION_SOURCE, object_sha256=sha(old_object),
            depfile=str(old_depfile), depfile_sha256=sha(old_depfile), header=str(old_header),
            header_sha256=sha(old_header), new_header_byte_identical=True)
        objdir = run/'candidate'/Path(RPC_SOURCE).parent
        objdir.mkdir(parents=True)
        obj = objdir/'JSONRPC.cpp.o'
        argv = shlex.split(command(RPC_OBJECT))
        argv[1:1] = ['-I'+str(generated), '-I'+str(snapshot/'xbmc')]
        argv += ['-iquote', str((SOURCE/RPC_SOURCE).parent)]
        for option, value in (('-o', obj), ('-MF', str(obj)+'.d'), ('-MT', obj), ('-c', snapshot/RPC_SOURCE)):
            output_arg(argv, option, value)
        execute(argv, 'JSONRPC-compile', BUILD)
        dependency = Path(str(obj)+'.d')
        assert str(header) in deps(dependency), 'WRONG_RPC_SCHEMA_HEADER'
        assert str(BUILD/'build/ServiceDescription.h') not in deps(dependency), 'MIXED_RPC_SCHEMA_HEADER'
        report['rebuilt_schema_consumer'] = dict(source=RPC_SOURCE, object_sha256=sha(obj),
            depfile=str(dependency), depfile_sha256=sha(dependency), header=str(header), header_sha256=sha(header))
        for archive, target in replacements.items():
            shutil.copyfile(PREDECESSOR/Path(archive).name, target)
        assert sha(relink('predecessor-relink')) == PREDECESSOR_SHA, 'PREDECESSOR_RELINK_MISMATCH'
        rpc_archive = replacements[ARCHIVES[2]]
        execute([str(TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ar'), 'r', str(rpc_archive), str(obj)],
                'JSONRPC-archive', run)
        execute([str(TOOLS/'armv8a-libreelec-linux-gnueabihf-gcc-ranlib'), str(rpc_archive)], 'JSONRPC-ranlib', run)
        for archive, target in replacements.items():
            replaced = ('JSONRPC.cpp.o',) if archive == ARCHIVES[2] else ()
            report['retained_archive_members'][archive] = retained_members(
                PREDECESSOR/Path(archive).name, target, replaced)
        candidate = relink('candidate')
        expected = json.loads((snapshot/'xbmc/interfaces/json-rpc/schema/methods.json').read_text())['Player.BobiControl']
        actual = binary_method(candidate)
        assert actual == expected, 'BINARY_BOBICONTROL_SCHEMA_MISMATCH'
        report['binary_bobicontrol'] = actual
        report['bytes'] = candidate.stat().st_size
        report['state'] = 'BUILT_NOT_DEPLOYED'
    except BaseException as error:
        report.update(state='FAILED_NOT_DEPLOYED', error=type(error).__name__, detail=str(error))
        raise
    finally:
        report['original_tree_unchanged'] = all(sha(path) == digest for path, digest in inputs.items())
        report['predecessor_unchanged'] = all(sha(path) == digest for path, digest in predecessor_inputs.items())
        with (run/'build-result.json').open('x') as out:
            json.dump(report, out, indent=2)
        print(json.dumps(dict(run=str(run), state=report['state'], candidate_sha256=report.get('candidate_sha256'),
                              original_tree_unchanged=report['original_tree_unchanged'],
                              predecessor_unchanged=report['predecessor_unchanged'])), flush=True)
        assert report['original_tree_unchanged'] and report['predecessor_unchanged']


if __name__ == '__main__':
    main()
