"""Actual actor negative controls on copied sources, never the supplied source."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile

import run_scoped_actor_test as actor

VIDEO = 'xbmc/cores/VideoPlayer/VideoPlayer.cpp'
HEADER = 'xbmc/cores/VideoPlayer/BobiScopedControl.h'
RPC = 'xbmc/interfaces/json-rpc/PlayerOperations.cpp'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--base-source', type=Path)
    parser.add_argument('--old-source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='user-transport-gate-', dir=args.output))
    original = {key: (args.source/key).read_text() for key in (VIDEO, HEADER, RPC)}
    hashes = {key: actor.sha(args.source/key) for key in original}
    mutations = (
        ('premature_stop', VIDEO, 'scopedCommand = CVariant(); // OnExit, not this turn\'s guard, settles stop.',
         'scopedApplied = true; // Deliberately broken acceptance-as-completion control.', 'user_stop_onexit'),
        ('rewritten_original', HEADER, 'item.row["terminal_reason"] = terminal["reason"];',
         'item.row["user_intent"] = terminal["user_intent"];\n          item.row["terminal_reason"] = terminal["reason"];', 'user_stop_original_scope'),
        ('foreign_terminal', HEADER, 'terminal["native_instance"] == command["native_instance"] &&',
         'true &&', 'user_stop_no_terminal_inference'),
        ('unscoped_resume', VIDEO, 'scopedResumeSeek = std::make_shared<CDVDMsgPlayerSeek>(mode);',
         'm_messenger.Put(std::make_shared<CDVDMsgPlayerSeek>(mode));', 'user_resume_replacement'),
        ('onexit_exception_gap', VIDEO,
         'void CVideoPlayer::OnExit()\n{\n  // An exception before the real terminal is unknown, never an applied stop.\n  KODI::UTILS::CScopeGuard<int, 0, void(int)> settleStop([&](int) { FinishBobiUserStop(); }, 1);',
         'void CVideoPlayer::OnExit()\n{', 'user_stop_unknown'),
        ('state_archive_missing', RPC, 'result["terminal_commands"] = CBobiScopedTerminals::Get().Recent();',
         'result["terminal_commands"] = CVariant(CVariant::VariantTypeArray);', 'user_state_read'),
        ('pause_requires_seek', VIDEO, 'result["can_pause"] = transport && m_State.canpause;',
         'result["can_pause"] = transport && m_State.canpause && m_State.canseek;', 'user_capabilities'),
        ('counter_type_gap', HEADER,
         'for (const auto* key : {"expected_sequence", "selection_epoch", "user_intent", "subtitle_intent", "audio_intent"})',
         'for (const auto* key : {"user_intent", "subtitle_intent", "audio_intent"})', 'user_strict_counters'),
        ('ce_unscoped_vc1', VIDEO,
         '          if (scopedCommand["action"].asString() == "user_resume")\n            scopedResumeSeek = std::make_shared<CDVDMsgPlayerSeek>(mode);\n          else\n            m_messenger.Put(std::make_shared<CDVDMsgPlayerSeek>(mode));',
         '          m_messenger.Put(std::make_shared<CDVDMsgPlayerSeek>(mode));', 'user_ce_vc1_replacement'),
        ('no_final_retirement', HEADER, 'if (Retirable(*it, state))',
         'if (false && Retirable(*it, state))', 'user_retire_many'),
        ('retire_unknown', HEADER, 'status != "applied" && status != "rejected" && status != "failed"',
         'status != "applied" && status != "rejected" && status != "failed" && status != "unknown"', 'user_retirement_guards'),
        ('guest_retirement_state', VIDEO, '!m_bobiCommands.Admit(command, m_bobiState)',
         '!m_bobiCommands.Admit(command, command)', 'user_retirement_real_state'),
        ('resume_tempo_retained', VIDEO, '        m_processInfo->SetTempo(1.0f);',
         '        (void)0;', 'user_tempo_150'),
        ('speed_only_projection', VIDEO, 'speed == DVD_PLAYSPEED_NORMAL && m_processInfo->GetNewTempo() == 1.0f ? "playing" : "other";',
         'speed == DVD_PLAYSPEED_NORMAL ? "playing" : "other";', 'user_tempo_projection'),
        ('speed_only_applied', VIDEO, '(scopedCommand["action"].asString() == "user_pause" || m_processInfo->GetNewTempo() == 1.0f);',
         'true;', 'user_tempo_applied_guard'),
    )

    def trial(spec):
        name, target, before, after, expected = spec
        snapshot = run/name/'source'
        assert before in original[target], 'MUTANT_CONTEXT_CHANGED:'+name
        for key, content in original.items():
            path = snapshot/key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content.replace(before, after) if key == target else content)
        proof, result = actor.run(snapshot, run/name/'actor', args.base_source or args.source)
        cases = {row['name']: row['passed'] for row in result['tests']}
        detected = result['compiled'] and cases.get(expected) is False
        return dict(name=name, detected=detected, expected_failed_case=expected,
                    result=str(proof), sha256=actor.sha(proof), actor_passed=result['passed'])

    with ThreadPoolExecutor(max_workers=2) as workers:
        rows = list(workers.map(trial, mutations))
    if args.old_source:
        proof, result = actor.run(args.old_source, run/'old-source', args.base_source)
        cases = {row['name'] for row in result['tests']}
        missing = sorted(set(actor.TRANSPORT_CASES + actor.CE_TRANSPORT_CASES)-cases)
        rows.append(dict(name='old_scoped_binary_is_not_transport_proof', detected=bool(missing),
            missing_required_cases=missing, historical_actor_passed=result['passed'],
            result=str(proof), sha256=actor.sha(proof)))
    report = dict(scope=__doc__, runner_sha256=actor.sha(__file__),
        source=str(args.source), source_sha256=hashes, tests=rows,
        original_source_unchanged=all(actor.sha(args.source/key)==digest for key,digest in hashes.items()))
    report['passed'] = report['original_source_unchanged'] and all(row['detected'] for row in rows)
    path = run/'result.json'
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(result=str(path), **report)))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
