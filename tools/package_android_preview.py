"""Export a verified local-only APK preview, never a stable cinema release."""
import json
from pathlib import Path
import shutil

from verify_android_apk import verify

ROOT = Path(__file__).resolve().parents[1]


def package():
    source = ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk'
    report = verify(source)
    destination = ROOT / 'dist/android-preview'
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / 'bobbi-android-helper-0.1.0-preview.apk'
    if output.is_symlink():
        raise ValueError('Unexpected preview symlink')
    shutil.copyfile(source, output)
    copied = verify(output)
    if copied['sha256'] != report['sha256']:
        raise ValueError('APK copy verification failed')
    (destination / 'verification.json').write_text(json.dumps(copied, indent=2) + '\n', encoding='utf-8')
    (destination / 'README.txt').write_text(
        'bobbi Android 本机助手：仅本地开发预览，不是完整影院安装包。\n'
        'Android 8.0+，ARM32/ARM64 通用，不选盒子型号；尚未实机安装/播放验收。\n'
        '可测试启动/停止真实本机引擎、导出配对文件、打开已有 Kodi。\n'
        '完整影院安装、115扫码登录与自动更新仍未集成，不要以此替换日常看片系统。\n'
        '界面沿用原新影院配色、圆角卡片、焦点和克制动效。\n'
        '使用开发签名，正式发布前须完成独立发行签名、对应源码/许可与干净安装审查。\n',
        encoding='utf-8')
    return copied


if __name__ == '__main__':
    print(json.dumps(package(), indent=2))
