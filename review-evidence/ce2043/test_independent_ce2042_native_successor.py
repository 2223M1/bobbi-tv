"""Independent bytes/source/schema checks; no author verifier imports or device IO."""
import hashlib
import json
from pathlib import Path
import re

PREVIOUS = Path('D:/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431')
RUN = Path('D:/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/builds/run-1792626905471062171')
SOURCE = 'xbmc/interfaces/json-rpc/JSONRPC.cpp'
DESCRIPTION = 'xbmc/interfaces/json-rpc/JSONServiceDescription.cpp'
PIN = '8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14'
ARCHIVES = ('VideoPlayer.a', 'application.a', 'jsonrpc_interface.a', 'playercorefactory.a')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def wsl(path):
    return path.as_posix().replace('D:', '/mnt/d')


def archive_members(path):
    """Parse regular GNU ar directly, independently of the author toolchain calls."""
    raw = path.read_bytes()
    assert raw.startswith(b'!<arch>\n')
    offset, names, result = 8, b'', {}
    while offset < len(raw):
        header = raw[offset:offset + 60]
        assert len(header) == 60 and header[58:60] == b'`\n'
        label = header[:16].decode('ascii').rstrip()
        length = int(header[48:58])
        start = offset + 60
        body = raw[start:start + length]
        assert len(body) == length
        offset = start + length + (length % 2)
        if label == '//':
            names = body
            continue
        if label in ('/', '/SYM64/'):
            continue
        if label.startswith('/'):
            index = int(label[1:])
            end = names.index(b'/\n', index)
            name = names[index:end].decode('utf-8')
        else:
            assert label.endswith('/')
            name = label[:-1]
        assert name and name not in result
        result[name] = body
    assert offset == len(raw)
    return result


def methods(path):
    result = {}
    for segment in path.read_bytes().split(b'\0'):
        if not re.match(rb'^"[A-Za-z0-9_.]+": \{', segment):
            continue
        try:
            value = json.loads(b'{' + segment + b'}')
        except (ValueError, UnicodeError):
            continue
        for name, item in value.items():
            if isinstance(item, dict) and item.get('type') == 'method':
                assert name not in result
                result[name] = item
    return result


def test_exact_predecessor_reproduced_and_every_frozen_source_preserved_plus_only_jsonrpc():
    before = load(PREVIOUS/'build-result.json')
    after = load(RUN/'build-result.json')
    assert sha(PREVIOUS/'candidate.bin') == sha(RUN/'predecessor-relink.bin') == PIN
    assert after['recompiled_units'] == [SOURCE]
    assert after['state'] == 'BUILT_NOT_DEPLOYED'
    assert after['original_tree_unchanged'] is True and after['predecessor_unchanged'] is True
    actual = {p.relative_to(RUN/'source-candidate').as_posix(): sha(p)
              for p in (RUN/'source-candidate').rglob('*') if p.is_file()}
    assert actual == after['source_sha256']
    assert actual.keys() == before['source_sha256'].keys() | {SOURCE}
    for name, digest in before['source_sha256'].items():
        assert actual[name] == digest == sha(PREVIOUS/'source-candidate'/name)
    assert actual[SOURCE] == 'b94dae82ab3d5b2b0390be2359112f51f15df4a953d4fe8fa1145e99bc83e7bb'


def test_direct_archive_bytes_only_jsonrpc_object_changes_and_new_archive_contains_exact_compiled_object():
    changes = []
    for name in ARCHIVES:
        before = archive_members(PREVIOUS/name)
        after = archive_members(RUN/name)
        assert list(before) == list(after)
        changes += [(name, item) for item in before if before[item] != after[item]]
        if name != 'jsonrpc_interface.a':
            assert (PREVIOUS/name).read_bytes() == (RUN/name).read_bytes()
    assert changes == [('jsonrpc_interface.a', 'JSONRPC.cpp.o')]
    members = archive_members(RUN/'jsonrpc_interface.a')
    assert members['JSONRPC.cpp.o'] == (RUN/'candidate'/SOURCE).with_name('JSONRPC.cpp.o').read_bytes()
    assert members['JSONServiceDescription.cpp.o'] == (
        PREVIOUS/'candidate'/DESCRIPTION).with_name('JSONServiceDescription.cpp.o').read_bytes()


def test_both_generated_header_consumers_have_exact_rebuilt_or_retained_provenance():
    proof = load(RUN/'build-result.json')
    assert proof['schema_consumers'] == [
        'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONRPC.cpp.o',
        'build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONServiceDescription.cpp.o']
    assert proof['schema_include_sources'] == [SOURCE, DESCRIPTION]
    new_header = RUN/'generated/ServiceDescription.h'
    old_header = PREVIOUS/'candidate/generated/ServiceDescription.h'
    assert new_header.read_bytes() == old_header.read_bytes()
    assert sha(new_header) == proof['generated_header_sha256']
    for row, location, name, header in [
        (proof['rebuilt_schema_consumer'], RUN, SOURCE, new_header),
        (proof['reused_schema_consumer'], PREVIOUS, DESCRIPTION, old_header),
    ]:
        obj = (location/'candidate'/name).with_name(Path(name).name + '.o')
        depfile = Path(str(obj) + '.d')
        deps = depfile.read_text().replace('\\\n', ' ').split()
        assert wsl(header) in deps
        assert not any(item.endswith('/.armv8a-libreelec-linux-gnueabihf/build/ServiceDescription.h') for item in deps)
        assert row['object_sha256'] == sha(obj)
        assert row['depfile_sha256'] == sha(depfile)
        assert row['header_sha256'] == sha(header)
    source = (RUN/'source-candidate'/SOURCE).read_text()
    assert '#include "ServiceDescription.h"' in source
    assert 'AddBuiltinMethod(JSONRPC_SERVICE_METHODS[index])' in source


def test_final_binary_all_184_methods_equal_frozen_source_and_only_old_control_schema_changed():
    expected = load(RUN/'source-candidate/xbmc/interfaces/json-rpc/schema/methods.json')
    actual, before = methods(RUN/'candidate.bin'), methods(PREVIOUS/'candidate.bin')
    assert len(actual) == len(expected) == len(before) == 184
    assert actual == expected
    assert before.keys() == actual.keys()
    assert [name for name in actual if actual[name] != before[name]] == ['Player.BobiControl']
    control = actual['Player.BobiControl']
    assert len(control['params']) == 12
    action = next(row for row in control['params'] if row['name'] == 'action')
    assert action['enum'] == ['stop', 'pause', 'resume', 'handoff_capture', 'handoff_stop']


def test_link_arguments_identical_to_8bb2_except_isolated_run_paths():
    before = load(PREVIOUS/'build-result.json')['commands']['candidate-link']
    after = load(RUN/'build-result.json')['commands']['candidate-link']
    assert [token.replace(wsl(PREVIOUS), '<RUN>') for token in before] == [
        token.replace(wsl(RUN), '<RUN>') for token in after]


def test_candidate_receipts_hashes_and_restrip_agree_without_claiming_device_certification():
    build = load(RUN/'build-result.json')
    verified = load(RUN/'artifact-verification.json')
    assert verified['state'] == 'VERIFIED_LOCAL_NOT_DEVICE_CERTIFIED'
    assert verified['build_result_sha256'] == sha(RUN/'build-result.json')
    assert build['candidate_sha256'] == verified['candidate_sha256'] == sha(RUN/'candidate.bin')
    assert sha(RUN/'candidate.bin') == sha(RUN/'same-artifact-restrip.bin') != PIN
    assert verified['unstripped_sha256'] == sha(RUN/'candidate.unstripped')
    assert verified['rpc_method_count'] == 184 and verified['rpc_methods_exact'] is True
