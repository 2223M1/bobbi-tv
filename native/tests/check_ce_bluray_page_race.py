"""Run the same deterministic overlap against the exact CE predecessor and candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

FOLDER = 'xbmc/cores/VideoPlayer/DVDInputStreams'


def check(old, new, output):
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='disc-overlap-', dir=output))
    fixture = Path(__file__).with_name('ce_bluray_page_race.cpp')
    digest = lambda b: hashlib.sha256(b).hexdigest()
    result = {'fixture_sha256': digest(fixture.read_bytes()), 'variants': {}}
    for name, tree in [('original', old), ('candidate', new)]:
        src = tree / FOLDER
        directory = work / name
        directory.mkdir()
        text = (src/'BlurayIsoCache.cpp').read_text()
        assert text.count('++m_pageMisses;') == 1
        # No additional timing/locking between the original miss check and callback
        # except for notifying the harness that the foreground really observed a miss.
        code = text.replace('++m_pageMisses;', '++m_pageMisses; TestMiss(pageIndex);')
        code = code.replace('#include "utils/log.h"', '#define logM(...) do {} while(0)\n'
                            '#define logComponentM(...) do {} while(0)\nvoid TestMiss(int64_t);')
        (directory/'BlurayIsoCache.cpp').write_text(code)
        binary = directory/'test'
        subprocess.run(['g++','-std=c++17','-pthread','-O2','-I'+str(src),
                        str(directory/'BlurayIsoCache.cpp'),str(fixture),'-o',str(binary)], check=True)
        rows = []
        for kind in ('ok','retry'):
            trial = subprocess.run([str(binary), kind], capture_output=True, text=True, timeout=15)
            expected = (1, 'duplicate page IO') if (name, kind)==('original', 'ok') else (0, 'OK:')
            rows.append(dict(case=kind, code=trial.returncode,
                             matched=trial.returncode == expected[0] and expected[1] in (trial.stdout+trial.stderr)))
        result['variants'][name] = dict(cpp=digest((src/'BlurayIsoCache.cpp').read_bytes()),
            header=digest((src/'BlurayIsoCache.h').read_bytes()), cases=rows)
    result['passed'] = all(case['matched'] for v in result['variants'].values() for case in v['cases'])
    path=work/'result.json'
    path.write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(report=str(path),**result)))
    return result['passed']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('old','new','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    raise SystemExit(0 if check(**vars(parser.parse_args())) else 1)
