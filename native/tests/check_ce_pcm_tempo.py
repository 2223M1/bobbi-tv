"""Compile CE's final timeline and audio-thread transition against identical controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def between(text, start, end, *, keep_start=False):
    assert text.count(start) == 1
    rest = text.split(start, 1)[1]
    assert end in rest
    return (start if keep_start else '') + rest.split(end, 1)[0]


def check(old, new, base, output):
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='ce-pcm-contract-', dir=output))
    template = Path(__file__).with_name('ce_pcm_tempo_contract.cpp.in').read_text()
    variants = {}
    for label, overlay in [('before',old), ('after',new)]:
        def source(file):
            name = Path('xbmc/cores/VideoPlayer') / file
            return ((overlay/name) if (overlay/name).is_file() else base/name).read_text()
        video = source('VideoPlayer.cpp').split('void CVideoPlayer::UpdatePlayState(',1)[1]
        timeline = between(video, '  if (state.timeMin == state.timeMax)', '  m_processInfo->SetPlayTimes(', keep_start=True)
        audio = source('VideoPlayerAudio.cpp').split('CVideoPlayerAudio - CDVDMsg::PLAYER_SETSPEED:',1)[1]
        borrow = between(audio, 'else\n      {\n        m_audioSink.Pause();\n      }', 'm_speed = (int)speed;')
        cpp = work/(label+'.cpp')
        cpp.write_text(template.replace('/*@timeline@*/', timeline).replace('/*@borrow@*/', borrow))
        exe = work/label
        subprocess.run(['g++','-std=c++17','-O2',str(cpp),'-o',str(exe)],check=True)
        run = subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        errors = int(run.stdout)
        assert (run.returncode, errors == 0) == ((1, False) if label=='before' else (0, True))
        variants[label] = dict(invariant_failures=errors, extracted_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest())
    (work/'result.json').write_text(json.dumps(variants, indent=2))
    print(json.dumps(dict(report=str(work/'result.json'), **variants)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('old','new','base','output'):
        parser.add_argument('--'+arg, required=True, type=Path)
    check(**vars(parser.parse_args()))
