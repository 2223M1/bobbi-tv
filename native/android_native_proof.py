"""Local clean-link provenance, not a signature or Android device certificate.

Only the build command below produces LINKED_NOT_DEVICE_VERIFIED. Packaging
checks the independent proof against current canonical inputs and exact ELF
bytes; compilation-only receipts and self-described APK hashes are insufficient.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
ABIS = {'arm64-v8a': 183, 'armeabi-v7a': 40}
UNITS = ('xbmc/cores/VideoPlayer/VideoPlayer.cpp', 'xbmc/application/ApplicationPlayer.cpp',
         'xbmc/cores/playercorefactory/PlayerCoreConfig.cpp', 'xbmc/interfaces/json-rpc/PlayerOperations.cpp',
         'xbmc/interfaces/json-rpc/JSONRPC.cpp', 'xbmc/interfaces/json-rpc/JSONServiceDescription.cpp')
BUILD = ['cmake', '--build', '<configured-build>', '--clean-first', '--parallel', '8']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate native proof field')
        value[key] = item
    return value


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError('Native proof budget exceeded')
    return json.loads(raw, object_pairs_hook=_object)


def canonical(root=ROOT):
    raw = (root / 'patches/series.json').read_bytes()
    series = json.loads(raw, object_pairs_hook=_object)
    patches, paths = {}, set()
    for item in series['patches']:
        name = item['file']
        if Path(name).name != name or name in patches:
            raise ValueError('Canonical patch inventory invalid')
        patch = (root / 'patches' / name).read_bytes()
        if digest(patch) != item['sha256']:
            raise ValueError('Canonical patch checksum changed')
        patches[name] = item['sha256']
        paths.update(re.findall(r'^\+\+\+ b/(.+)$', patch.decode('utf-8'), re.M))
    if not paths or any(Path(path).is_absolute() or '..' in Path(path).parts for path in paths):
        raise ValueError('Canonical source paths invalid')
    return dict(source_base=series['base_commit'], series_sha256=digest(raw), patches=patches,
                toolchain_lock_sha256=digest((root / 'toolchain-lock.json').read_bytes()),
                builder_sha256=digest((root / 'android_native_proof.py').read_bytes())), paths


def validate(proof, native, abi, root=ROOT):
    expected, paths = canonical(root)
    if not isinstance(proof, dict) or proof.get('schema') != 1 or type(proof.get('schema')) is not int:
        raise ValueError('Native build proof required')
    if (proof.get('state') != 'LINKED_NOT_DEVICE_VERIFIED' or proof.get('abi') != abi
            or proof.get('clean_link') is not True or proof.get('real_device_verified') is not False
            or proof.get('build_command') != BUILD or proof.get('compiled_units') != sorted(UNITS)):
        raise ValueError('Native proof is not a complete clean Android link')
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ValueError('Native proof differs from current canonical inputs')
    if (len(native) < 20 * 1024**2 or native[:4] != b'\x7fELF' or abi not in ABIS
            or struct.unpack_from('<H', native, 18)[0] != ABIS[abi]
            or proof.get('native_sha256') != digest(native) or proof.get('native_bytes') != len(native)):
        raise ValueError('Native proof binary/ABI mismatch')
    hashes = proof.get('source_files')
    if (not isinstance(hashes, dict) or set(hashes) != paths
            or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in hashes.values())
            or not re.fullmatch('[0-9a-f]{40}', str(proof.get('patched_tree', '')))):
        raise ValueError('Native canonical source proof incomplete')
    for key in ('compile_database_sha256', 'cmake_cache_sha256', 'compiler_sha256', 'build_log_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', str(proof.get(key, ''))):
            raise ValueError('Native link input proof incomplete')
    return proof


def canonical_source(source, root=ROOT):
    """Compare actual source bytes to a private index built from locked patches."""
    expected, paths = canonical(root)
    def git(*args, env=None):
        return subprocess.check_output(['git', *args], cwd=source, env=env)
    if git('rev-parse', 'HEAD').decode().strip() != expected['source_base']:
        raise ValueError('Native source base changed')
    with tempfile.TemporaryDirectory(prefix='bobbi-native-proof-index-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        git('read-tree', 'HEAD', env=env)
        for name in expected['patches']:
            git('apply', '--cached', str(root / 'patches' / name), env=env)
        hashes = {}
        for relative in sorted(paths):
            wanted = git('show', ':' + relative, env=env)
            path = source / relative
            if path.is_symlink() or path.read_bytes() != wanted:
                raise ValueError('Native source is not current canonical patch output: ' + relative)
            hashes[relative] = digest(wanted)
        changed = set(git('diff', '--name-only', 'HEAD').decode().splitlines())
        others = set(git('ls-files', '--others', '--exclude-standard').decode().splitlines())
        if (changed | others) - paths:
            raise ValueError('Unreviewed native source changes')
        return expected, hashes, git('write-tree', env=env).decode().strip()


def build(source, directory, abi, output):
    source, directory, output = source.resolve(), directory.resolve(), output.resolve()
    if source == output or source in output.parents:
        raise ValueError('Keep native build evidence outside the canonical source tree')
    if output.exists():
        raise ValueError('Use a new native proof output; preserve prior evidence')
    if os.name != 'posix' or any(shutil.which(tool) is None for tool in ('git', 'cmake')):
        raise ValueError('ANDROID_TOOLCHAIN_UNAVAILABLE: no native proof produced')
    expected, sources, tree = canonical_source(source)
    cache, database = directory / 'CMakeCache.txt', directory / 'compile_commands.json'
    cache_raw, database_raw = cache.read_bytes(), database.read_bytes()
    home = re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$', cache_raw.decode(), re.M)
    if home != [str(source)]:
        raise ValueError('Android build is configured for a different source tree')
    records = json.loads(database_raw)
    compilers = set()
    for unit in UNITS:
        rows = [row for row in records if Path(row['file']).resolve() == source / unit]
        if len(rows) != 1:
            raise ValueError('Android compile database lacks a required production unit')
        argv = rows[0].get('arguments') or shlex.split(rows[0]['command'])
        compiler = Path(argv[0]).resolve()
        if not compiler.is_file() or 'android' not in ' '.join(argv).lower():
            raise ValueError('ANDROID_TOOLCHAIN_UNAVAILABLE: configured compiler unproven')
        compilers.add(compiler)
    if len(compilers) != 1:
        raise ValueError('Android compiler identity is ambiguous')
    compiler_sha = digest(next(iter(compilers)).read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_suffix('.build.log')
    report = dict(schema=1, state='FAILED_NOT_PROVEN', real_device_verified=False)
    try:
        with log.open('x') as stream:
            subprocess.run(['cmake', '--build', str(directory), '--clean-first', '--parallel', '8'],
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=14400)
        after = canonical_source(source)
        if after != (expected, sources, tree) or cache.read_bytes() != cache_raw or database.read_bytes() != database_raw:
            raise ValueError('Native source/build inputs changed during link')
        if digest(next(iter(compilers)).read_bytes()) != compiler_sha:
            raise ValueError('Native compiler changed during link')
        native = (directory / 'libkodi.so').read_bytes()
        report.update(expected, state='LINKED_NOT_DEVICE_VERIFIED', abi=abi, clean_link=True,
            build_command=BUILD, compiled_units=sorted(UNITS), source_files=sources, patched_tree=tree,
            native_sha256=digest(native), native_bytes=len(native), compiler_sha256=compiler_sha,
            compile_database_sha256=digest(database_raw), cmake_cache_sha256=digest(cache_raw),
            build_log_sha256=digest(log.read_bytes()))
        validate(report, native, abi)
    except BaseException:
        report['state'] = 'FAILED_NOT_PROVEN'
        raise
    finally:
        output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--abi', choices=sorted(ABIS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source, args.build, args.abi, args.output)
    print(json.dumps(dict(state=result['state'], native_sha256=result['native_sha256'], real_device_verified=False)))
