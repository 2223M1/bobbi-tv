"""Legacy namespace bridge; implementations live only in bobbi_core."""
import importlib
from pathlib import Path
import sys

try:
    import bobbi_core as _shared
except ModuleNotFoundError as error:
    if error.name != 'bobbi_core':
        raise
    # Kodi adds declared module dependencies. This exact sibling fallback also
    # supports repository tests and offline tools without importing Kodi.
    _library = Path(__file__).resolve().parents[3] / 'script.module.bobbi.core/lib'
    if not (_library / 'bobbi_core/__init__.py').is_file():
        raise RuntimeError('AM6B shared core dependency is missing') from None
    sys.path.insert(0, str(_library))
    _shared = importlib.import_module('bobbi_core')
if _shared.CORE_API != 1:
    raise RuntimeError('AM6B shared core API is incompatible')
