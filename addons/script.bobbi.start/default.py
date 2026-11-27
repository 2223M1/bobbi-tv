"""One CE entry for online installation and complete offline packages."""
from pathlib import Path
import sys
import xbmcaddon

try:
    root = Path(xbmcaddon.Addon('script.bobbi.start').getAddonInfo('path'))
    bootstrap = root / 'bootstrap'
    if bootstrap.is_dir():
        sys.path.insert(0, str(bootstrap))
    else:
        platform = Path(xbmcaddon.Addon('script.module.bobbi.platform').getAddonInfo('path'))
        sys.path.insert(0, str(platform / 'lib'))
    from bobbi_platform.ce_install_ui import main
except (ImportError, OSError, RuntimeError, SyntaxError):
    # A damaged bootstrap cannot import the normal error presenter.
    # Keep a dependency-free bilingual ASCII+ZH rescue message and stable code.
    import xbmc
    import xbmcgui
    diagnostic = '初始化 · ENTRY_BOOTSTRAP_UNAVAILABLE'
    xbmc.log('[bobbi-install] ' + diagnostic, xbmc.LOGERROR)
    xbmcgui.Dialog().ok(
        'Bobbi TV / 操作未完成',
        'Bootstrap unavailable; re-download the full script.bobbi.start ZIP.\n'
        '安装入口缺少可用组件，请重新下载完整安装 ZIP。\n'
        'Diagnostic / 诊断（可拍照） ' + diagnostic,
    )
    raise SystemExit(0)
main(
    root / 'resources' / 'complete.bobbi-update.zip',
    online='online' in sys.argv[1:],
    storage='storage' in sys.argv[1:],
    auto='auto' in sys.argv[1:],
)
