"""Exercise verbatim scoped admission and actor branches with downstream stubs.

This compiles the real BobiControl body, HandleMessages scoped guard/dispatch,
and its seek/audio/subtitle actor branches. Kodi decoders, queue and services
are instrumented stand-ins. It is not a real decoder or device certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def block(text, marker):
    assert text.count(marker) == 1, 'PRODUCTION_BRANCH_DRIFT:' + marker
    start = text.index(marker)
    brace = text.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def dependency(source, relative, base=None):
    path = source/relative
    return path if path.is_file() or base is None else base/relative


def extracted(source, base=None):
    text = (source/'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
    method = block(text, 'void CVideoPlayer::HandleMessages()')
    outer = block(method, 'if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL))')
    scoped = block(outer, 'if (BobiScopedAction(action))')
    prefix = method[method.index('    std::unique_lock<std::recursive_mutex> scopedEpoch;'):
                    method.index('    if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL))')]
    action_header = outer[outer.index('{') + 1:outer.index('      if (BobiScopedAction(action))')]
    branches = [block(method, marker) for marker in (
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SEEK) &&',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_AUDIOSTREAM))',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_SUBTITLESTREAM))',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_SUBTITLESTREAM_VISIBLE))')]
    branches[0] = branches[0].removeprefix('else ')
    actor = ('void CVideoPlayer::HandleMessages() {\n'
             'std::shared_ptr<CDVDMsg> pMsg = nullptr;\n'
             'while (m_messenger.Get(pMsg, 0ms) == MSGQ_OK) {\n' + prefix +
             'if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL)) {' + action_header + scoped +
             '\nelse { continue; }\n}\n' + '\n'.join(branches) + '\n}\n}\n')
    admission = block(text, 'bool CVideoPlayer::BobiControl(const CVariant& command)')
    if 'void CVideoPlayer::QueueSubtitleSwitchSeek(' in text:
        actor += '\n' + block(text, 'void CVideoPlayer::QueueSubtitleSwitchSeek(')
        actor = block(text, 'int64_t NormalizeTarget(') + '\n' + actor
    messages = dependency(source, 'xbmc/cores/VideoPlayer/DVDMessage.h', base).read_text()
    message_types = '\n'.join(block(messages, marker) + ';' for marker in (
        'class CDVDMsgPlayerSeek : public CDVDMsg',
        'class CDVDMsgPlayerSetAudioStream : public CDVDMsg',
        'class CDVDMsgPlayerSetSubtitleStream : public CDVDMsg'))
    return admission + '\n' + actor, message_types


CASES = ('seek_receipt', 'seek_failed', 'stale_cas', 'stream_key', 'duplicate',
         'manual_subtitle_off', 'audio_failed', 'audio_resync', 'resync_replacement',
         'same_id_replacement', 'pending_manual', 'gate_contention',
         'decoder_intent_lock', 'resync_new_manual')


def run(source, output, base_source=None):
    source, output = Path(source), Path(output)
    base = Path(base_source) if base_source else None
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='scoped-actor-', dir=output))
    actor, messages = extracted(source, base)
    ce_subtitle = 'void CVideoPlayer::QueueSubtitleSwitchSeek(' in actor
    (work/'actual_scoped_actor.inc').write_text(actor)
    (work/'actual_scoped_messages.inc').write_text(messages)
    fixture = Path(__file__).with_name('scoped_actor_test.cpp')
    legacy = Path(__file__).resolve().parent.parent/'ce-original-audio-handoff-20261022/tests/includes'
    binary = work/'scoped-actor-test'
    command = ['g++', '-std=c++17', '-O1', '-pthread', '-Wall', '-Wextra',
               *(['-DBOBBI_CE_SUBTITLE_SYNC'] if ce_subtitle else []),
               '-Wno-unused-parameter', '-DTARGET_POSIX', '-I'+str(source/'xbmc'),
               *(['-I'+str(base/'xbmc')] if base else []),
               '-I'+str(legacy), '-I'+str(work), str(fixture),
               str(dependency(source, 'xbmc/utils/Variant.cpp', base)), '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
    report = dict(scope=__doc__, command=command, compiled=compiled.returncode == 0,
                  compilation=compiled.stdout+compiled.stderr, tests=[],
                  fixture_sha256=sha(fixture), extracted_sha256=sha(work/'actual_scoped_actor.inc'),
                  source_sha256={path: sha(dependency(source, path, base)) for path in (
                      'xbmc/cores/VideoPlayer/VideoPlayer.cpp',
                      'xbmc/cores/VideoPlayer/DVDMessage.h',
                      'xbmc/cores/VideoPlayer/BobiScopedControl.h',
                      'xbmc/cores/BobiOpenGate.h', 'xbmc/utils/Variant.cpp', 'xbmc/utils/Variant.h')},
                  source=str(source), base_source=str(base) if base else None)
    if report['compiled']:
        for name in CASES + (('ce_subtitle_resync', 'ce_subtitle_replacement', 'ce_subtitle_new_manual',
                              'ce_subtitle_original_mode', 'ce_subtitle_non_demux') if ce_subtitle else ()):
            trial = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=15)
            report['tests'].append(dict(name=name, passed=trial.returncode == 0,
                                       output=trial.stdout+trial.stderr))
        report['binary_sha256'] = sha(binary)
    report['passed'] = report['compiled'] and all(row['passed'] for row in report['tests'])
    path = work/'result.json'
    path.write_text(json.dumps(report, indent=2))
    return path, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-source', type=Path)
    args = parser.parse_args()
    path, report = run(args.source, args.output, args.base_source)
    print(json.dumps(dict(result=str(path), **report)))
    raise SystemExit(0 if report['passed'] else 1)
