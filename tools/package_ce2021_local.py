"""Freeze this CE review locally; no staging, commit, push or device operation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'dist/ce2021-local-delivery-20261021'
ORIGINAL_BASE = 'c8de17ae9dabbe0f37753e1751b1d88107311316'
REWRITTEN_BASE = 'f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def changed_files():
    paths = set()
    for args in (('diff', '--name-only', '-z', 'HEAD'),
                 ('ls-files', '--others', '--exclude-standard', '-z')):
        paths.update(x.decode('utf-8') for x in git(*args).split(b'\0') if x)
    return sorted(paths)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def copy(source, relative):
    if source.is_symlink() or not source.is_file():
        raise ValueError('Not a regular deliverable: ' + relative)
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Duplicate output: ' + relative)
    shutil.copyfile(source, target)


def main():
    current = git('rev-parse', 'HEAD').decode().strip()
    if current != REWRITTEN_BASE:
        raise ValueError('Baseline moved again; inspect before packaging')
    DEST.mkdir()  # Never overwrite an earlier handoff.
    files = changed_files()
    allowed = {'addons', 'release', 'tests', 'tools', 'docs', 'review-evidence'}
    for relative in files:
        parts = Path(relative).parts
        if parts[0] not in allowed or any(x in parts for x in ('.private', '__pycache__', 'userdata')):
            raise ValueError('Unreviewed changed path: ' + relative)
        source = ROOT / relative
        if not source.exists():
            continue  # Deletions remain explicit in tracked-changes.patch.
        target = relative if parts[0] in {'review-evidence', 'docs'} else 'source-delta/' + relative
        copy(source, target)
    for name in ('script.bobbi.start-0.2.13-ce2021.zip',
                 'bobbi-private-2026102021-coreelec.bobbi-update.zip'):
        copy(ROOT / 'dist/private-releases' / name, 'installers/' + name)
    for name in ('BobbiTV-PR3-CE2014-Review-20261021.zip',
                 'BobiTV-PR3-CE2014-c8de17a-Audit-20261021.zip'):
        copy(Path('D:/Downloads') / name, 'original-reviews/' + name)
    (DEST / 'tracked-changes.patch').write_bytes(git('diff', '--binary', 'HEAD'))
    (DEST / 'README.md').write_text(
        '# CE2021 本地交付\n\n'
        '盒子已安装 CE2021，测试结束后已停止测试影片并回到影院首页。\n\n'
        '- 报告：docs/CE-REVIEW-CLOSURE-2021-20261021.md\n'
        '- 普通入口：installers/script.bobbi.start-0.2.13-ce2021.zip\n'
        '- 同代完整载荷：installers/bobbi-private-2026102021-coreelec.bobbi-update.zip\n'
        '- 原审查：original-reviews；测试/失败/截图：review-evidence。\n'
        '- tracked-changes.patch 和 source-delta 保存当前未提交改动。\n\n'
        '按最终确认不提交、不推送，不运行新远端 CI。安装包原样复制，未重打包。\n'
        '并行任务重写历史、删除部分许可/来源文件后，当前源码 source-check 失败；'
        '旧通过结果只适用于清理前完整候选及已测安装包，不能称当前源码已通过。\n'
        'source-delta 不是完整源码包；后续先解决缺失文件与构建一致性，再重新验 CI。\n'
        '本轮未解决《元气囝仔》诸神BT元数据超时，以及《乒乓》Vodes版本缺中文字幕。\n',
        encoding='utf-8')
    entries = [dict(path=p.relative_to(DEST).as_posix(), bytes=p.stat().st_size,
                    sha256=digest(p)) for p in sorted(DEST.rglob('*')) if p.is_file()]
    manifest = dict(schema=1, sequence=2026102021, delivery='local_only',
                    original_review_base=ORIGINAL_BASE, rewritten_base=current,
                    rewritten_tree=git('rev-parse', 'HEAD^{tree}').decode().strip(),
                    new_commit=None, new_remote_ci=None, pushed=False,
                    current_workspace_build='FAILED_SOURCE_INVENTORY_AFTER_PARALLEL_CLEANUP',
                    installed_candidate='CE2021_TESTED_BEFORE_CLEANUP',
                    files=entries)
    (DEST / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive = DEST.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x') as output:
        for path in sorted(DEST.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(DEST).as_posix(),
                             compress_type=zipfile.ZIP_STORED if path.suffix.lower() in {'.zip', '.png'}
                             else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise ValueError('Handoff archive failed integrity check')
    print(json.dumps(dict(directory=str(DEST), archive=str(archive),
                          files=len(entries) + 1, bytes=archive.stat().st_size,
                          sha256=digest(archive), pushed=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
