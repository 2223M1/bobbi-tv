"""Run the unchanged Web probe against this candidate, not its bundled sources."""
import argparse
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(args.bundle) as archive:
        name = 'BobiTV-CE1909-cdf0c48-Review-20261019/tests/identity_probe.py'
        namespace = {'__name__': 'ce_web_identity_probe'}
        exec(compile(archive.read(name), name, 'exec'), namespace)
    result = namespace['run'](root / 'addons/script.module.bobbi.core/lib/bobbi_core')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('scope', 'total', 'passed', 'failed')}))


if __name__ == '__main__':
    main()
