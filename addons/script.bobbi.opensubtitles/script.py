# Modified for bobbi portability and explicit credentials, 2026-10-19.
"""A manual download-only entry point, not a Kodi subtitle-service callback."""
import json


def main():
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcvfs
    from resources.lib.provider import Provider
    from resources.lib.ui import run
    from bobbi_platform.runtime import call

    def rpc(method, params):
        response = json.loads(xbmc.executeJSONRPC(json.dumps(
            dict(jsonrpc="2.0", id=1, method=method, params=params))))
        if "error" in response:
            raise RuntimeError("READ_ONLY_RPC_UNAVAILABLE")
        return response.get("result")

    addon = xbmcaddon.Addon()
    profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
    def provider(directory):
        return Provider(directory, api_key=addon.getSetting('api_key'))
    return run(rpc, xbmcgui.Dialog(), xbmcgui.DialogProgress, xbmc.Monitor(),
               xbmc.executebuiltin, provider, profile,
               account_reader=lambda: call('account_status', {}, timeout=.2))


if __name__ == "__main__":
    main()
