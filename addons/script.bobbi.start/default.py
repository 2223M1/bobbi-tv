"""Single offline CE entry. The build embeds the reviewed installer and payload."""
from pathlib import Path
import sys
import xbmcaddon

root = Path(xbmcaddon.Addon('script.bobbi.start').getAddonInfo('path'))
bootstrap = root / 'bootstrap'
if bootstrap.is_dir():
    sys.path.insert(0, str(bootstrap))
else:
    sys.path.insert(0, str(Path(xbmcaddon.Addon('script.module.bobbi.platform').getAddonInfo('path')) / 'lib'))
from bobbi_platform.ce_install_ui import main
main(root / 'resources' / 'complete.bobbi-update.zip')
