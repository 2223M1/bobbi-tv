"""Import explicit pure-policy regressions and their test helpers, not runtime data."""
import argparse
import ast
import json
import hashlib
from pathlib import Path
import subprocess
from prepare_candidate import rename

ROOT = Path(__file__).resolve().parents[1]
REV = 'ff530e09c34c6285ccb05c1d4179140b097174fb'
PREFIX = 'ui-redesign/backend/source/addons/plugin.video.jacktook/tests/'
SEEDS = ('test_subtitle_content_policy', 'test_font_byte_warmup',
         'test_font_hardlink_verification', 'test_source_card_readability',
         'test_subtitle_candidate_ranking', 'test_subtitle_manual_intent',
         'test_video_context_migration', 'test_anime_navigation_hub')


def run(repo):
    names = set(subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only',REV,'--',PREFIX]).decode().splitlines())
    pending, done = list(SEEDS), set()
    output = ROOT / 'tests/private_baseline'
    output.mkdir(parents=True, exist_ok=True)
    def read(name):
        return subprocess.check_output(['git','-C',str(repo),'show',REV+':'+name]).decode('utf-8-sig')
    fixture = rename(read(PREFIX+'fixtures/jacktorr-release317/subtitles.py')).encode('utf-8')
    fixture_dir = ROOT / 'tests/fixtures/jacktorr-release317'
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / 'subtitles.py').write_bytes(fixture)
    for notice in ('LICENSE', 'README.md'):
        (fixture_dir / notice).write_text(read(PREFIX+'fixtures/jacktorr-release317/'+notice), encoding='utf-8')
    while pending:
        item = pending.pop()
        if item in done:
            continue
        source = PREFIX + 'unit/' + item + '.py'
        if source not in names:
            continue
        text = read(source)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom) and node.module:
                dependency = node.module.removeprefix('tests.unit.')
                if PREFIX + 'unit/' + dependency + '.py' in names:
                    pending.append(dependency)
        text = rename(text).replace('from tests.unit.', 'from ')
        text = text.replace('53c6777121feb0adb5ce5efa4b60532146ef7fe1c8e9bc8b16a2a05abadbd8ea',
                            hashlib.sha256(fixture).hexdigest())
        (output / (item + '.py')).write_text(text, encoding='utf-8')
        done.add(item)
    # Reuse Kodi test types but not the old global SQLite mock: these tests must
    # operate real temporary SQLite databases against the migrated modules.
    content = read(PREFIX+'conftest.py')
    content = content[:content.index('# Mock sqlite3.connect')]
    content = rename(content)
    content = content.replace("os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))",
        "str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'addons/plugin.video.bobbi')")
    content += '''\nfrom pathlib import Path
_root = Path(__file__).resolve().parents[2]
for _dir in ('plugin.video.bobbi', 'script.module.bobbi.core/lib', 'script.module.bobbi.platform/lib', 'script.module.bobbi.catalog/lib'):
    sys.path.insert(0, str(_root / 'addons' / _dir))
sys.path.insert(0, str(Path(__file__).parent))

def pytest_sessionfinish(session, exitstatus):
    module = sys.modules.get('lib.db.cached')
    if module is not None:
        module.cache.close()
'''
    (output / 'conftest.py').write_text(content, encoding='utf-8')
    print(json.dumps(dict(imported=len(done), tests=sorted(done))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    run(parser.parse_args().source)
