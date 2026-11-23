"""Diagnostic only: real tempo setters and actor vs explicit restore-1x contract.

Does not change the pinned candidate or production source. Reuses the formal
actor runner's real ProcessInfo/VideoPlayer extraction in a fresh temporary
harness; decoder/clock/data-cache endpoints remain instruments.
Advanced maxTempo=2.1 is an explicit fixture setting so both 1.5x and 2x are legal
under both generic's strict upper bound and CE's additional 0.05 allowance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import run_scoped_actor_test as actor


DIAGNOSTIC = '''
void tempoDiagnostic(const std::string& name) {
  const float tempo=name.find("150")!=std::string::npos?1.5f:2.0f;
  CVideoPlayer p;
  p.SetTempo(tempo);p.HandleMessages();
  require(p.m_playSpeed==static_cast<int>(tempo*1000) && p.m_processInfo->GetNewTempo()==tempo,"native tempo setup failed");
  if(name.find("legacy_control")!=std::string::npos) {
    p.SetTempo(1.0f);p.HandleMessages();p.SetSpeed(1.0f);p.HandleMessages();
  } else {
    require(p.BobiControl(p.Command("user_resume")),"scoped resume admission");p.HandleMessages();
    require(p.Status()=="applied","resume result not applied");
    if(name.find("legacy_rebound")!=std::string::npos) {
      p.SetSpeed(0.0f);p.HandleMessages();p.SetSpeed(1.0f);p.HandleMessages();
    }
  }
  std::cout << "initial_tempo=" << tempo << " actor_speed=" << p.m_playSpeed
    << " new_speed=" << p.m_processInfo->GetNewSpeed()
    << " current_tempo=" << p.m_processInfo->m_tempo
    << " new_tempo=" << p.m_processInfo->GetNewTempo()
    << " cache_tempo=" << p.m_processInfo->cache.tempo
    << " cache_speed=" << p.m_processInfo->cache.speed
    << " audio_speed=" << p.m_VideoPlayerAudio->speed
    << " video_speed=" << p.m_VideoPlayerVideo->speed
    << " transport=" << p.GetBobiState()["transport_state"].asString() << "\\n";
  require(p.m_playSpeed==1000 && p.m_processInfo->GetNewSpeed()==1.0f &&
      p.m_processInfo->GetNewTempo()==1.0f && p.m_processInfo->m_tempo==1.0f &&
      p.m_processInfo->cache.tempo==1.0f && p.m_processInfo->cache.speed==1.0f,
      "explicit restore 1x retained tempo or rebounded");
}
int main(int argc,char** argv) {
  try {require(argc==2,"one case required");tempoDiagnostic(argv[1]);std::cout<<"PASS\\n";}
  catch(const std::exception& e) {std::cerr<<"FAIL "<<e.what()<<"\\n";return 1;}
}
'''


def run(source, base, output):
    source,base,output=Path(source),Path(base),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='user-tempo-diagnostic-',dir=output))
    fixture_path=Path(__file__).with_name('scoped_actor_test.cpp')
    fixture=fixture_path.read_text()
    fixture=fixture[:fixture.index('int main(int argc, char** argv)')]+DIAGNOSTIC
    actual,messages=actor.extracted(source,base)
    process_path=actor.dependency(source,'xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp',base)
    (work/'actual_scoped_actor.inc').write_text(actual)
    (work/'actual_scoped_messages.inc').write_text(messages)
    (work/'tempo_fixture.cpp').write_text(fixture)
    binary=work/'tempo-actor-test'
    command=['g++','-std=c++17','-O1','-pthread','-Wall','-Wextra','-Wno-unused-parameter',
        '-DBOBBI_USER_TRANSPORT',*(['-DBOBBI_CE_SUBTITLE_SYNC'] if 'QueueSubtitleSwitchSeek' in actual else []),
        '-DTARGET_POSIX','-I'+str(source/'xbmc'),'-I'+str(base/'xbmc'),'-I'+str(work),
        str(work/'tempo_fixture.cpp'),str(actor.dependency(source,'xbmc/utils/Variant.cpp',base)),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True,timeout=90)
    report=dict(scope=__doc__,source=str(source),base_source=str(base),command=command,
        compiled=compiled.returncode==0,compilation=compiled.stdout+compiled.stderr,tests=[],
        runner_sha256=actor.sha(__file__),original_fixture_sha256=actor.sha(fixture_path),
        generated_fixture_sha256=actor.sha(work/'tempo_fixture.cpp'),
        extracted_sha256=actor.sha(work/'actual_scoped_actor.inc'),
        source_sha256={'VideoPlayer.cpp':actor.sha(source/'xbmc/cores/VideoPlayer/VideoPlayer.cpp'),
            'ProcessInfo.cpp':actor.sha(process_path)})
    if report['compiled']:
        for tempo in ('150','200'):
            for action in ('scoped_resume','legacy_rebound','legacy_control'):
                name=tempo+'_'+action
                result=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=20)
                report['tests'].append(dict(name=name,passed=result.returncode==0,exit_code=result.returncode,
                    output=result.stdout+result.stderr))
        report['binary_sha256']=actor.sha(binary)
    report['passed']=report['compiled'] and all(row['passed'] for row in report['tests'])
    path=work/'result.json';path.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(result=str(path),**report)))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--base-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(run(args.source,args.base_source,args.output))
