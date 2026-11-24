"""Advance GitHub's already-active six-field stable alias after staged readback."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from ce_release_gate import parse_offer, release_url


def advance(root, receipt, proof):
    root = Path(root)
    source = parse_offer((root/'stable/current.json').read_bytes(), 'stable')
    if (source['schema'] != 2 or source['prerelease'] or receipt['track'] != 'stable'
            or source != receipt['offers']['github'] or source['url'] != release_url(source['tag'], 'github')
            or not proof.get('passed') or not proof.get('promotable')
            or proof.get('phase') != 'before-feed-commit' or proof.get('track') != 'stable'
            or any(proof.get(k) != receipt[k] for k in ('commit','tree','tag'))
            or set(proof.get('mirrors', ())) != set(receipt['offers'])):
        raise ValueError('Matching verified stable promotion required')
    path = root/'current.json'
    previous = parse_offer(path.read_bytes())
    if previous['schema'] != 1 or previous['url'] != release_url(previous['tag'], 'github'):
        raise ValueError('Unknown legacy pointer')
    new = {key: (1 if key == 'schema' else source[key]) for key in previous}
    if previous['sequence'] > new['sequence'] or (previous['sequence'] == new['sequence'] and previous != new):
        raise ValueError('Legacy pointer ahead or conflicted')
    if previous != new:
        with tempfile.NamedTemporaryFile(dir=root,delete=False) as fp:
            tmp = Path(fp.name)
            try:
                fp.write((json.dumps(new, indent=2)+'\n').encode())
                fp.flush(); os.fsync(fp.fileno())
            except BaseException:
                fp.close();tmp.unlink(missing_ok=True);raise
        try:
            os.replace(tmp,path)
        finally:
            tmp.unlink(missing_ok=True)
    return new


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','receipt','proof'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    print(advance(args.root,json.loads(args.receipt.read_bytes()),json.loads(args.proof.read_bytes()))['tag'])
