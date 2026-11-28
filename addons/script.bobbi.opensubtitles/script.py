# Modified for bobbi portability and explicit credentials, 2026-10-19.
"""A manual download-only entry point, not a Kodi subtitle-service callback."""
import json


def main():
    import xbmc
    import xbmcaddon
    import xbmcgui
    from resources.lib.provider import Provider
    from resources.lib.ui import run
    from bobbi_platform.runtime import bind_call
    from bobbi_platform.paths import ProfileBinding
    from bobbi_core.runtime_paths import ProfilePath
    # Capture before dialogs/worker admission, including this script's own state.
    class SubtitleBinding(ProfileBinding):
        ADDONS = ProfileBinding.ADDONS + ('script.bobbi.opensubtitles',)
    binding = SubtitleBinding()
    try:
        bound_call = bind_call(binding.root() / 'runtime.json')
    except (OSError, ValueError, RuntimeError):
        bound_call = None  # A missing resident owner never binds to a later host.
    def call(action, body, **options):
        binding.require_current()
        if bound_call is None:
            raise OSError('RUNTIME_NOT_CAPTURED')
        result = bound_call(action, body, **options)
        binding.require_current()
        return result
    from bobbi_platform.standard_subtitle_ui import offer
    if offer(xbmc.Player(), xbmcgui.Dialog(), call):
        return

    def rpc(method, params):
        response = json.loads(xbmc.executeJSONRPC(json.dumps(
            dict(jsonrpc="2.0", id=1, method=method, params=params))))
        if "error" in response:
            raise RuntimeError("READ_ONLY_RPC_UNAVAILABLE")
        return response.get("result")

    addon = xbmcaddon.Addon()
    api_key = addon.getSetting('api_key')
    profile = binding.root('script.bobbi.opensubtitles')
    root = ProfilePath('subtitle-browser', profile=binding.root('plugin.video.bobbi'))
    binding.require_current()
    def provider(directory):
        if api_key and api_key.strip():
            return Provider(directory, api_key=api_key)
        from resources.lib.shared_search import SharedSearch
        return SharedSearch(binding.root('plugin.video.bobbi'), root, binding.is_current)
    return run(rpc, xbmcgui.Dialog(), xbmcgui.DialogProgress, xbmc.Monitor(),
               xbmc.executebuiltin, provider, profile, root=root,
               account_reader=lambda: call('account_status', {}, timeout=.2), current=binding.is_current)


if __name__ == "__main__":
    main()
