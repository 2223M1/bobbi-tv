"""Exercise verbatim scoped admission and actor branches with downstream stubs.

This compiles real BobiControl and HandleMessages scoped branches, including
speed, legacy VideoPlayer speed/tempo setters, real ProcessInfo speed/tempo
methods and full BobiEvent/OnExit when user transport is present. Process/reset/
destructor probes execute extracted cleanup guards, not entire host methods.
Kodi decoders, queue and services are instrumented stand-ins, not a real
decoder or device certification.
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
    transport = 'void CVideoPlayer::FinishBobiUserStop(' in text
    method = block(text, 'void CVideoPlayer::HandleMessages()')
    outer = block(method, 'if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL))')
    scoped = block(outer, 'if (BobiScopedAction(action))')
    prefix = method[method.index('    std::unique_lock<std::recursive_mutex> scopedEpoch;'):
                    method.index('    if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL))')]
    action_header = outer[outer.index('{') + 1:outer.index('      if (BobiScopedAction(action))')]
    markers = (
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SEEK) &&',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_AUDIOSTREAM))',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_SUBTITLESTREAM))',
        'else if (pMsg->IsType(CDVDMsg::PLAYER_SET_SUBTITLESTREAM_VISIBLE))')
    if transport:
        markers += ('else if (pMsg->IsType(CDVDMsg::PLAYER_SETSPEED))',)
    branches = [block(method, marker) for marker in markers]
    branches[0] = branches[0].removeprefix('else ')
    actor = ('void CVideoPlayer::HandleMessages() {\n'
             'std::shared_ptr<CDVDMsg> pMsg = nullptr;\n'
             'while (m_messenger.Get(pMsg, 0ms) == MSGQ_OK) {\n' + prefix +
             'if (pMsg->IsType(CDVDMsg::PLAYER_BOBI_CONTROL)) {' + action_header + scoped +
             '\nelse { continue; }\n}\n' + '\n'.join(branches) + '\n}\n}\n')
    admission = block(text, 'bool CVideoPlayer::BobiControl(const CVariant& command)')
    if transport:
        actor += '\n' + '\n'.join(block(text, marker) for marker in (
            'void CVideoPlayer::FinishBobiUserStop(',
            'CVariant CVideoPlayer::BobiEvent(', 'void CVideoPlayer::OnExit()',
            'CVariant CVideoPlayer::GetBobiSubtitles() const',
            'void CVideoPlayer::SetSpeed(float speed)', 'void CVideoPlayer::SetTempo(float tempo)',
            'void CVideoPlayer::SetPlaySpeed(int speed)'))
        info = dependency(source, 'xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp', base).read_text()
        for signature in ('void SetSpeed', 'void SetNewSpeed', 'void SetTempo', 'void SetNewTempo',
                          'float GetNewSpeed', 'float GetNewTempo', 'float MinTempoPlatform',
                          'float MaxTempoPlatform', 'bool IsTempoAllowed'):
            result, name = signature.split()
            method = block(info, result+' CProcessInfo::'+name+'(').replace('CProcessInfo::', 'Process::')
            # The wrapper calls this real setter before the controlled race hook.
            if name == 'SetSpeed': method = method.replace('Process::SetSpeed(', 'Process::ProductionSetSpeed(')
            actor += '\n' + method
        rpc = dependency(source, 'xbmc/interfaces/json-rpc/PlayerOperations.cpp', base).read_text()
        application = dependency(source, 'xbmc/application/ApplicationPlayer.cpp', base).read_text()
        actor += '\n' + block(application, 'CVariant CApplicationPlayer::GetBobiState() const')
        actor += '\n' + block(rpc, 'JSONRPC_STATUS CPlayerOperations::BobiState(')
        process = block(text, 'void CVideoPlayer::Process()')
        prefix = process[process.index('{')+1:process.index('  // Try to resolve')]
        assert 'std::uncaught_exceptions() > exceptions' in prefix, 'PROCESS_UNKNOWN_GUARD_MISSING'
        actor += '\nvoid CVideoPlayer::ProcessFailureProbe() {' + prefix + '\nthrow std::runtime_error("process failure");\n}\n'
        begin = block(text, 'void CVideoPlayer::BeginBobiInstance(')
        prefix = begin[begin.index('{')+1:begin.index('  InvalidateBobiCompletion();')]
        assert 'FinishBobiUserStop();' in prefix, 'RESET_UNKNOWN_GUARD_MISSING'
        actor += '\nvoid CVideoPlayer::ResetStopProbe() {' + prefix + '\n}\n'
        destructor = block(text, 'CVideoPlayer::~CVideoPlayer()')
        prefix = destructor[destructor.index('{')+1:destructor.index('  CServiceBroker::')]
        assert 'FinishBobiUserStop();' in prefix, 'DESTRUCTOR_UNKNOWN_GUARD_MISSING'
        actor += '\nCVideoPlayer::~CVideoPlayer() {' + prefix + '\n}\n'
    if 'void CVideoPlayer::QueueSubtitleSwitchSeek(' in text:
        actor += '\n' + block(text, 'void CVideoPlayer::QueueSubtitleSwitchSeek(')
        actor = block(text, 'int64_t NormalizeTarget(') + '\n' + actor
    messages = dependency(source, 'xbmc/cores/VideoPlayer/DVDMessage.h', base).read_text()
    markers = (
        'class CDVDMsgPlayerSeek : public CDVDMsg',
        'class CDVDMsgPlayerSetAudioStream : public CDVDMsg',
        'class CDVDMsgPlayerSetSubtitleStream : public CDVDMsg')
    if transport:
        markers += ('class CDVDMsgPlayerSetSpeed : public CDVDMsg',)
    message_types = '\n'.join(block(messages, marker) + ';' for marker in markers)
    return admission + '\n' + actor, message_types


CASES = ('seek_receipt', 'seek_failed', 'stale_cas', 'stream_key', 'duplicate',
         'manual_subtitle_off', 'audio_failed', 'audio_resync', 'resync_replacement',
         'same_id_replacement', 'pending_manual', 'gate_contention',
         'decoder_intent_lock', 'resync_new_manual')

TRANSPORT_CASES = ('user_pause', 'user_resume', 'user_idempotent', 'user_no_seek',
    'user_unsupported', 'user_stale', 'user_execution_race', 'user_stop_onexit',
    'user_stop_error', 'user_stop_unknown', 'user_stop_reset', 'user_stop_destroy',
    'user_stop_process_exception', 'user_stop_original_scope', 'user_stop_full',
    'user_stop_ttl', 'user_stop_no_terminal_inference', 'user_resume_sync',
    'user_resume_replacement', 'user_resume_new_intent', 'user_intent_lock',
    'user_state_read', 'user_capabilities', 'user_terminal_binding',
    'user_pending_open', 'user_gate_contention', 'user_duplicate', 'user_active_full',
    'user_strict_counters', 'user_retire_many', 'user_retire_replay',
    'user_retirement_guards', 'user_retirement_real_state', 'user_full_result_fields',
    'user_tempo_150', 'user_tempo_200', 'user_tempo_pause', 'user_tempo_legacy_rebound',
    'user_tempo_legacy_reset', 'user_tempo_projection', 'user_tempo_applied_guard')

CE_TRANSPORT_CASES = ('user_ce_vc1_resume', 'user_ce_vc1_replacement', 'user_ce_vc1_new_intent')


def run(source, output, base_source=None):
    source, output = Path(source), Path(output)
    base = Path(base_source) if base_source else None
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='scoped-actor-', dir=output))
    actor, messages = extracted(source, base)
    ce_subtitle = 'void CVideoPlayer::QueueSubtitleSwitchSeek(' in actor
    transport = 'void CVideoPlayer::FinishBobiUserStop(' in actor
    (work/'actual_scoped_actor.inc').write_text(actor)
    (work/'actual_scoped_messages.inc').write_text(messages)
    fixture = Path(__file__).with_name('scoped_actor_test.cpp')
    legacy = Path(__file__).resolve().parent.parent/'ce-original-audio-handoff-20261022/tests/includes'
    binary = work/'scoped-actor-test'
    command = ['g++', '-std=c++17', '-O1', '-pthread', '-Wall', '-Wextra',
               *(['-DBOBBI_CE_SUBTITLE_SYNC'] if ce_subtitle else []),
               *(['-DBOBBI_USER_TRANSPORT'] if transport else []),
               '-Wno-unused-parameter', '-DTARGET_POSIX', '-I'+str(source/'xbmc'),
               *(['-I'+str(base/'xbmc')] if base else []),
               '-I'+str(legacy), '-I'+str(work), str(fixture),
               str(dependency(source, 'xbmc/utils/Variant.cpp', base)), '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
    report = dict(scope=__doc__, command=command, compiled=compiled.returncode == 0,
                  compilation=compiled.stdout+compiled.stderr, tests=[],
                  runner_sha256=sha(__file__), fixture_sha256=sha(fixture),
                  extracted_sha256=sha(work/'actual_scoped_actor.inc'),
                  messages_sha256=sha(work/'actual_scoped_messages.inc'),
                  source_sha256={path: sha(dependency(source, path, base)) for path in (
                      'xbmc/cores/VideoPlayer/VideoPlayer.cpp',
                      'xbmc/cores/VideoPlayer/DVDMessage.h',
                      'xbmc/cores/VideoPlayer/BobiScopedControl.h',
                      'xbmc/cores/BobiOpenGate.h', 'xbmc/utils/Variant.cpp', 'xbmc/utils/Variant.h',
                      *(['xbmc/interfaces/json-rpc/PlayerOperations.cpp', 'xbmc/application/ApplicationPlayer.cpp',
                         'xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp'] if transport else []))},
                              source=str(source), base_source=str(base) if base else None)
    if report['compiled']:
        for name in CASES + (('ce_subtitle_resync', 'ce_subtitle_replacement', 'ce_subtitle_new_manual',
                              'ce_subtitle_original_mode', 'ce_subtitle_non_demux') if ce_subtitle else ()) + (TRANSPORT_CASES if transport else ()) + (CE_TRANSPORT_CASES if transport and ce_subtitle else ()):
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
