"""Prior 18-case runner; route its real runtime to the same temporary profile."""
import argparse
import difflib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ce2012-candidate-') as directory:
        target=Path(directory)/'review'
        shutil.copytree(ROOT/'review-evidence/ce2012-web-contracts',target)
        script=target/'checks/reproduce_installer_boundaries.py'
        before=script.read_text(encoding='utf-8')
        needle="with patch.object(ui, 'profile', lambda **_: runtime_path), \\\n"
        assert before.count(needle)==2
        after=before.replace(needle,needle+"                    patch.object(local_runtime, 'profile', lambda **_: runtime_path), \\\n")
        script.write_text(after,encoding='utf-8')
        result=subprocess.run([sys.executable,'-B',str(target/'run_review.py'),'--repo',str(ROOT),'--output',str(args.output.resolve())])
        (args.output/'profile-adapter.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
            fromfile='old UI-only profile routing',tofile='UI and runtime share the real temporary registration')),encoding='utf-8')
        raise SystemExit(result.returncode)
