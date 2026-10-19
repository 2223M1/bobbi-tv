"""Visible startup failure, before opening credentials or creating agent homes."""
from .data_paths import ensure_profile, LayoutError


def prepare_profile(profile, cancelled=None, service=False):
    import xbmc
    if cancelled is None:
        cancelled = xbmc.Monitor().abortRequested
    try:
        ensure_profile(profile, cancelled, stop_service=service)
        return True
    except InterruptedError:
        return False
    except LayoutError as error:
        import xbmcgui
        xbmc.log('[voice-migration] ' + str(error), xbmc.LOGERROR)
        xbmcgui.Dialog().ok('语音助手 · 升级数据迁移', str(error))
        return False
