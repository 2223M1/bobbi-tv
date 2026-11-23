"""Exercise the actual prepare entry against a fresh generic Kodi checkout."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
proof = Path(tempfile.mkdtemp(prefix='series-entry-', dir=args.output))
subprocess.run(['git', 'clone', '--quiet', '--shared', str(args.source), str(proof)], check=True)
subprocess.run(['python3', str(Path(__file__).resolve().parents[1]/'apply-series.py'), str(proof)], check=True)
print('PASS ordered patch entry:', proof)
