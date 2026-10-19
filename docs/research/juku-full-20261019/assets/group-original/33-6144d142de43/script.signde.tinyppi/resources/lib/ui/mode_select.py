"""VS10-mode selection dialog.

Open via ``RunScript(script.signde.tinyppi,dialog)`` or ``open_dialog()``.
"""

import json
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
from core import display
from core.utils import clear_overlay_state

_ADDON      = xbmcaddon.Addon()
_ADDON_PATH = _ADDON.getAddonInfo("path")

# The Dolby Vision driver, as this fork (kernel 4.9, amdolby_vision) exposes it.
# Every value below is the one CoreELEC's own Kodi writes to these nodes in
# CAMLCodec::OpenDecoder / CloseDecoder, which is what this add-on has to agree
# with: it drives the same driver, on the same box, mid-playback.
_POLICY  = "/sys/module/amdolby_vision/parameters/dolby_vision_policy"
_ENABLE  = "/sys/module/amdolby_vision/parameters/dolby_vision_enable"
_DVMODE  = "/sys/module/amdolby_vision/parameters/dolby_vision_mode"

# Whether the driver runs Dolby Vision low latency, i.e. Player-LED: 0 is
# DOLBY_VISION_LL_DISABLE (TV-LED), 1 is DOLBY_VISION_LL_YUV422 (Player-LED).
# Kodi only writes it for a stream it turns Dolby Vision on for, so it answers
# for that playback and not for an HDR10 one -- see ``_player_led_mode``.
_LL_POLICY = "/sys/module/amdolby_vision/parameters/dolby_vision_ll_policy"

# dolby_vision_policy: DOLBY_VISION_FOLLOW_SINK, DOLBY_VISION_FOLLOW_SOURCE and
# DOLBY_VISION_FORCE_OUTPUT_MODE.  Forcing is what a VS10 mode is; follow-source is what
# Kodi leaves behind when it turns Dolby Vision off, and so what a mode that
# wants no VS10 at all restores.
_POLICY_FOLLOW_SOURCE = "1"
_POLICY_FORCE_OUTPUT  = "2"

# The output mode the Dolby Vision driver is sending.  This kernel has one
# mode node, so this is the same node as _DVMODE; the two spellings are a
# CoreELEC 22 arrangement.  Values follow the driver's own enum, where 0 (IPT)
# and 1 (IPT tunnelled) are the two Dolby Vision outputs and the rest are
# HDR10 (2), SDR10 (3), SDR8 (4) and bypass (5).
_DV_OUTPUT       = "/sys/module/amdolby_vision/parameters/dolby_vision_mode"
_DV_OUTPUT_MODES = ("0", "1")

# On this kernel there is one mode node, read and written with the enum
# unshifted -- the same node and the same values Kodi uses.
_MODE_BYPASS     = "5"   # DOLBY_VISION_OUTPUT_MODE_BYPASS, i.e. the source untouched
_MODE_DV_IPT     = "0"   # DOLBY_VISION_OUTPUT_MODE_IPT, Dolby Vision for Player-LED
_MODE_DV_TUNNEL  = "1"   # DOLBY_VISION_OUTPUT_MODE_IPT_TUNNEL, DV for TV-LED
_MODE_HDR10      = "2"
_MODE_SDR10      = "3"
_MODE_SDR8       = "4"

# How long the driver gets to pick up a mode change before the switch is taken
# to have stayed on the same side of the Dolby Vision line.
_DV_OUTPUT_TIMEOUT_MS = 1000

# One of the settings introduced alongside the native VS10 keymap actions in
# SamuriHL/coreelec-xbmc commit 7df0943. Both were added in the same change, so
# its presence over JSON-RPC tells us the running Kodi build ships the VS10
# output engine (and therefore the vs10.* actions).
_VS10_PROBE_SETTING = "coreelec.amlogic.dolbyvision.vs10.dv"

# Cached result of the one-time capability probe (None = not yet probed).
_vs10_actions = None

_BTN_TINYPPI = 1001


def _w(path: str, value: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
        xbmc.log(f"TinyPPI: {path} = {value}", xbmc.LOGINFO)
    except OSError as e:
        xbmc.log(f"TinyPPI: FAILED {path}: {e}", xbmc.LOGERROR)


def _delay(ms: int) -> None:
    try:
        xbmc.sleep(ms)
    except Exception:
        time.sleep(ms / 1000)


def _read(path: str):
    """Read a sysfs node, returning its stripped contents or None on failure."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _dv_output_active() -> bool:
    """Return whether the driver is currently sending Dolby Vision."""
    return _read(_DV_OUTPUT) in _DV_OUTPUT_MODES


def _wait_for_dv_output_change(
    before: bool,
    timeout_ms: int = _DV_OUTPUT_TIMEOUT_MS,
    step_ms: int = 50,
) -> bool:
    """Poll the driver's output mode, returning True once it crossed the
    Dolby Vision line (and False if it never does)."""
    waited = 0
    while waited < timeout_ms:
        if _dv_output_active() != before:
            return True
        _delay(step_ms)
        waited += step_ms
    return False


def _is_playing_video() -> bool:
    """True when a video is playing, i.e. when native VS10 actions can apply.

    Fails CLOSED.  This gates the sysfs sequence, and "assume playing" only ever
    suppresses a raw write; assuming idle would let one through while a title is
    on screen, which is the two-writers case that took the video layer down.
    """
    try:
        return xbmc.Player().isPlayingVideo()
    except Exception:
        return True


def _reset_display_on_dv_change(name: str, dv_before: bool) -> None:
    """Re-init the HDMI output when a switch crossed the Dolby Vision line.

    Kodi only re-applies the display mode when the played stream's HDR type
    changes, and a VS10 switch made mid-playback never tells it about one.  The
    driver then starts sending Dolby Vision (or stops) while the HDMI output is
    still set up for the format before it, so the TV never switches over and the
    picture comes out with the wrong colours -- most visibly in Player-LED mode.
    Asking the display driver to re-apply its output is the missing step; see
    ``core.display`` for how that is done.

    Which switch needs one is decided twice over, and neither answer is the
    user's to give.  The crossing answers for the switch: a mode that stays on
    the same side of the line -- SDR8 to HDR10, say -- changes nothing about how
    the output is signalled and returns here at once.  The LED mode answers for
    the box: Player-LED is where the reset is needed, because the box maps the
    picture itself and sends it out as an ordinary carrier
    (``dolby_vision_ll_policy`` on, output IPT), so nothing re-negotiates the
    HDMI output on its own.  TV-LED tunnels Dolby Vision to the display and gets
    there without help -- and the reset there does harm rather than nothing: it
    re-applies the output over a VS10 mode the driver has only just taken, which
    leaves later switches in the same playback landing on SDR instead of the
    mode picked (issue #64).

    Only what is left waits for the driver to confirm the crossing, because a
    mode the driver did not take is a mode the display has nothing to re-apply
    for.  Playback gates it too, since a switch with nothing on screen has no
    output to re-apply.

    Only kernel 5.15 (CoreELEC 22) feels any of this: the reset is a DRM
    property on the HDMI connector, which the older kernels have no equivalent
    for, so there ``core.display`` finds nothing to drive either way.
    """
    if not _is_playing_video():
        return

    if (name in _DV_MODES) == dv_before:
        return

    if not _player_led_mode():
        xbmc.log(
            f"TinyPPI: '{name}' crossed the Dolby Vision line, but this box is "
            "TV-LED and signals that itself -> no display reset",
            xbmc.LOGINFO,
        )
        return

    if not _wait_for_dv_output_change(dv_before):
        xbmc.log(
            f"TinyPPI: '{name}' did not move the driver's output mode "
            "-> no display reset",
            xbmc.LOGWARNING,
        )
        return

    direction = "from" if dv_before else "to"
    display.reset(f"VS10 output switched {direction} Dolby Vision")


def _write_sequence(
    steps: tuple[tuple[str, str], ...],
    delay_ms: int = 100,
) -> None:
    """Write a sysfs sequence, waiting between steps when requested."""
    for index, (path, value) in enumerate(steps):
        if index and delay_ms > 0:
            _delay(delay_ms)
        _w(path, value)


def _set_passthrough_mode(dv_mode: str, delay_ms: int = 100) -> None:
    """Set the CoreELEC policy and enable Dolby Vision in the requested mode."""
    _write_sequence(
        (
            (_POLICY, _POLICY_FORCE_OUTPUT),
            (_ENABLE, "Y"),
            (_DVMODE, dv_mode),
        ),
        delay_ms=delay_ms,
    )


def _set_sdr_conversion_mode(dv_mode: str) -> None:
    """Reset to SDR first, then enable the requested conversion mode."""
    _write_sequence(
        (
            (_POLICY, _POLICY_FORCE_OUTPUT),
            (_DVMODE, _MODE_BYPASS),
            (_ENABLE, "Y"),
            (_DVMODE, dv_mode),
        )
    )


def original_sdr() -> None:
    _set_passthrough_mode(_MODE_BYPASS, delay_ms=0)


def hdr10() -> None:
    _set_sdr_conversion_mode(_MODE_HDR10)


def dv() -> None:
    # Which of the two Dolby Vision outputs the box wants: Player-LED takes IPT,
    # TV-LED the tunnelled one, exactly as Kodi picks between them itself.
    if _player_led_mode():
        _set_passthrough_mode(_MODE_DV_IPT)
    else:
        _set_passthrough_mode(_MODE_DV_TUNNEL)


def original_hdr() -> None:
    _set_passthrough_mode(_MODE_HDR10)


def original_hlg() -> None:
    # HLG is not a valid VS10 input, so turn VS10 off to let HLG pass through
    # the standard HDR path untouched.  That is also why neither the dialog nor
    # the selector offers HLG any modes at all; this one is left reachable
    # through ``run_mode`` for a keymap that wants to clear a VS10 mode an
    # earlier title left behind.  Follow-source with enable=N is the state
    # Kodi itself leaves the driver in when it releases Dolby Vision; policy 0 is
    # follow-sink, a different thing, and not what "off" means here.
    _write_sequence(
        (
            (_POLICY, _POLICY_FOLLOW_SOURCE),
            (_ENABLE, "N"),
        )
    )


# Outside playback there is no source stream for "Original" to follow, so the
# sysfs fallback restores bypass. During playback this name is routed to Kodi's
# source-aware ``vs10.original`` action below.
original_dv = original_sdr


def sdr8() -> None:
    _set_sdr_conversion_mode(_MODE_SDR8)


def sdr10() -> None:
    _set_sdr_conversion_mode(_MODE_SDR10)


_MODES = {
    "original_sdr": original_sdr,
    "hdr10": hdr10,
    "dv": dv,
    "original_hdr": original_hdr,
    "original_hlg": original_hlg,
    "original_dv": original_dv,
    "sdr8": sdr8,
    "sdr10": sdr10,
}

# The modes that leave Dolby Vision on the wire, whether converted to it or
# passed through: crossing in or out of this set is what needs a display reset.
_DV_MODES = ("dv", "original_dv")


# Native VS10 keymap action (SamuriHL/coreelec-xbmc commit 7df0943) that each
# TinyPPI mode maps to. When these actions are available they are fired instead
# of the sysfs sequences above, which are then skipped entirely.
#
# Only four actions exist, and vs10.sdr is hard-wired to SDR10 output
# (DOLBY_VISION_OUTPUT_MODE_SDR10, mode 3). There is no action for SDR8 output
# (mode 4), so 'sdr8' takes vs10.sdr during playback: SDR10 is the closest
# native mode, and the menu entry is labelled generically "-> SDR". The sysfs
# path, used when nothing is playing, still writes the true mode 4.
_VS10_ACTION = {
    "original_sdr": "vs10.original",
    "original_hdr": "vs10.original",
    "original_hlg": "vs10.original",
    "original_dv":  "vs10.original",
    "dv":           "vs10.dv",
    "hdr10":        "vs10.hdr10",
    "sdr10":        "vs10.sdr",
    "sdr8":         "vs10.sdr",
}


def _probe_vs10_actions() -> bool:
    """Return True if this Kodi build ships the native VS10 output engine.

    Probes one of its settings over JSON-RPC, since the settings and the
    ``vs10.*`` keymap actions were added in the same commit: a ``result`` means
    the actions exist too, an ``error`` means we must drive sysfs ourselves.
    """
    request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Settings.GetSettingValue",
            "params": {"setting": _VS10_PROBE_SETTING},
        }
    )
    try:
        response = json.loads(xbmc.executeJSONRPC(request))
    except Exception as e:
        xbmc.log(f"TinyPPI: VS10 Actions probe failed: {e}", xbmc.LOGWARNING)
        return False
    return isinstance(response, dict) and "result" in response


def _vs10_actions_available() -> bool:
    """Cached capability check, logging the chosen path once per session."""
    global _vs10_actions
    if _vs10_actions is None:
        _vs10_actions = _probe_vs10_actions()
        if _vs10_actions:
            xbmc.log(
                "TinyPPI: native VS10 Actions available -> preferred during "
                "playback; sysfs is used only when nothing is playing",
                xbmc.LOGINFO,
            )
        else:
            xbmc.log(
                "TinyPPI: native VS10 Actions not available -> using the "
                "built-in TinyPPI VS10 (sysfs) path",
                xbmc.LOGINFO,
            )
    return _vs10_actions


def _probe_dv_Player_LED_setting():
    """Return the configured Dolby Vision LED mode, or None when it cannot be
    read.

    ``coreelec.amlogic.dolbyvision.type`` is this fork's DV_TYPE
    (AMLUtils.h): 0 DISPLAY_LED (TV-LED), 1 PLAYER_LED_LLDV, 2 PLAYER_LED_HDR,
    3 VS10_ONLY, 4 PLAYER_LED_HDR2.  ``coreelec.amlogic.dolbyvisionled`` is a
    CoreELEC 22 spelling and does not exist here -- probing it returned
    "Invalid params" every time, so this always fell through to the driver's
    ll_policy, which holds a stale value after a non-DV title.  Unlike
    ``_probe_vs10_actions``, which asks whether a setting is there at all, this
    one has to read what it says.  Going by presence put a TV-LED box on the
    Player-LED output, where the picture went out SDR BT.2020nc.

    None, not False, when the value does not arrive: not knowing is not the same
    as TV-LED, and the caller has somewhere else to ask.
    """
    request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Settings.GetSettingValue",
            "params": {"setting": "coreelec.amlogic.dolbyvision.type"},
        }
    )
    try:
        response = json.loads(xbmc.executeJSONRPC(request))
    except Exception as e:
        xbmc.log(f"TinyPPI: probe failed: {e}", xbmc.LOGWARNING)
        return None
    if not isinstance(response, dict) or "result" not in response:
        return None
    value = response["result"].get("value")
    # Read as a number, so a "0" that arrives as text is still TV-LED: taking
    # it as a bare string would repeat the mistake this replaced.
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1 if value else 0


def _player_led_mode() -> bool:
    """Return True if Dolby Vision is being driven Player-LED on this box.

    Kodi's own setting answers first, because it answers for every source.  The
    driver's ``dolby_vision_ll_policy`` describes the same choice -- Kodi writes
    it from that very setting -- but only for a stream it turned Dolby Vision on
    for; an HDR10 one leaves it holding whatever the last title put there, which
    is why it stands in only when the setting cannot be read at all rather than
    being trusted over it.

    TV-LED is the answer when neither can be read: it is CoreELEC's default and
    the end that needs nothing done for it.
    """
    setting = _probe_dv_Player_LED_setting()
    if setting is not None:
        return setting in (1, 2, 4)

    ll_policy = _read(_LL_POLICY)
    if ll_policy is not None:
        xbmc.log(
            "TinyPPI: Dolby Vision LED mode unreadable from Kodi -> taking the "
            f"driver's low-latency policy ({ll_policy})",
            xbmc.LOGINFO,
        )
        return ll_policy not in ("", "0")

    return False


def set_mode(name: str) -> None:
    """Apply the VS10 mode ``name`` (see ``_MODES``).

    The output is switched by ``_apply_mode``; what is left here is the step
    neither path performs on its own -- the display reset a switch to or from
    Dolby Vision needs.  The driver's output mode is sampled before the switch
    so the two sides can be compared afterwards.
    """
    if name not in _MODES:
        xbmc.log(f"TinyPPI: Unknown mode '{name}'", xbmc.LOGERROR)
        return

    dv_before = _dv_output_active()
    _apply_mode(name)
    _reset_display_on_dv_change(name, dv_before)


def _apply_mode(name: str) -> None:
    """Switch the VS10 output to ``name`` the way the skin's VS10 buttons do.

    During playback the native ``vs10.*`` action is the whole mechanism, not a
    preferred route to the same place.  It is the same ACTION_VS10_* the skin
    fires, handled in CVideoPlayer::OnAction, which calls aml_dv_set_vs10_mode()
    with the playing stream's HDR type -- and that type is the part no sysfs
    write can supply.  The skin sends the action and trusts it; so do we.

    There is no verify-and-fall-back here on purpose.  Judging the action by
    whether the driver nodes moved cannot tell "correctly did nothing" from
    "failed": asking for the mode already in effect moves nothing, and the
    fallback then wrote policy, enable and mode underneath a running Kodi.  Two
    writers on the Dolby Vision core is what took the video layer down.  An
    action that no-ops now does what the skin's button does in the same case:
    nothing.

    The sysfs sequence is kept for the one case the action cannot serve --
    nothing playing, where there is no CVideoPlayer to take it and no
    transition to collide with.
    """
    action = _VS10_ACTION.get(name)
    if _is_playing_video():
        if not (action and _vs10_actions_available()):
            xbmc.log(
                f"TinyPPI: '{name}' not applied -- no native VS10 action is "
                "available for it, and the sysfs sequence must never run "
                "during playback: two writers on the Dolby Vision core is what "
                "took the video layer down",
                xbmc.LOGWARNING,
            )
            return
        if not xbmc.getCondVisibility("Window.IsActive(fullscreenvideo)"):
            xbmc.log(
                f"TinyPPI: '{name}' not applied -- Action({action}) is only "
                "delivered to the player from fullscreen video "
                "(Application.cpp gates it), and driving sysfs during playback "
                "is what took the video layer down",
                xbmc.LOGWARNING,
            )
            return
        xbmc.executebuiltin(f"Action({action})")
        xbmc.log(
            f"TinyPPI: mode '{name}' requested via VS10 Action({action}) -- "
            "sent, not confirmed; Kodi may decline it (already converting, "
            "VS10-only display, HDR10+ source or software decode)",
            xbmc.LOGINFO,
        )
        return

    _MODES[name]()
    xbmc.log(
        f"TinyPPI: mode '{name}' set via built-in TinyPPI VS10 (sysfs)",
        xbmc.LOGINFO,
    )


__all__ = list(_MODES.keys()) + ["open_dialog", "set_mode"]


# Dialog button id -> mode name (routed through ``set_mode`` so the dialog also
# prefers the native VS10 Actions when they are available).
_ACTIONS = {
    1102: "original",
    1103: "sdr10",
    1104: "hdr10",
    1105: "dv",
}


class SettingsDialog(xbmcgui.WindowXMLDialog):
    """Menu dialog to pick a VS10 output mode or launch the TinyPPI overlay."""

    def onInit(self) -> None:
        # The SDR / HDR10 / DV groups branch on SigndeTinyPPI.HdrType, derived from
        # the CE21 player API; refresh it so the right group appears as soon
        # as the player publishes it.
        self._running = True
        self._pending_mode = None
        self._pending_tinyppi = False
        self._monitor = xbmc.Monitor()
        threading.Thread(target=self._hdr_type_loop, daemon=True).start()

    def _hdr_type_loop(self) -> None:
        """Republish the HDR type until the dialog closes.

        A failed read only costs this cycle: the dialog would otherwise keep
        showing whichever SDR / HDR10 / DV group was up when the thread died.
        """
        from info.properties import publish_hdr_type

        home = xbmcgui.Window(10000)
        logged = False
        while self._running and not self._monitor.abortRequested():
            try:
                publish_hdr_type(home)
            except Exception as e:
                if not logged:
                    logged = True
                    xbmc.log(f"TinyPPI: HDR type refresh failed: {e}",
                             xbmc.LOGWARNING)
            if self._monitor.waitForAbort(0.5):
                break

    def close(self) -> None:
        self._running = False
        super().close()

    def onClick(self, control_id: int) -> None:
        if control_id == _BTN_TINYPPI:
            # Do not open a second modal WindowXMLDialog from this dialog's
            # click callback. Kodi is still closing this window at that point
            # and can discard the new PPI window. Hand it off after doModal()
            # returns, just as the VS10 actions below are deferred.
            self._pending_tinyppi = True
            self.close()
            return

        mode = _ACTIONS.get(control_id)
        if mode:
            if mode == "original":
                hdr_type = xbmcgui.Window(10000).getProperty(
                    "SigndeTinyPPI.HdrType"
                ).lower()
                if "dolby" in hdr_type:
                    mode = "original_dv"
                elif "hlg" in hdr_type:
                    mode = "original_hlg"
                elif "hdr" in hdr_type:
                    mode = "original_hdr"
                else:
                    mode = "original_sdr"
            # Defer applying: a native VS10 action fired now would be dropped by
            # the window manager while this modal dialog's closing animation is
            # still running ("ignoring action ..., because topmost modal dialog
            # closing animation is running"). open_dialog() applies it once
            # doModal() has returned, i.e. after the dialog is fully gone.
            self._pending_mode = mode
            self.close()

    def onAction(self, action: xbmcgui.Action) -> None:
        if action.getId() in (
            xbmcgui.ACTION_PREVIOUS_MENU,
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_STOP,
        ):
            self.close()


def open_dialog() -> None:
    """Create and display the mode-selection dialog modally."""
    win = SettingsDialog(
        "script-tinyppi-dialog.xml",
        _ADDON_PATH,
        "Default",
        "1080i",
    )
    win.doModal()
    mode = getattr(win, "_pending_mode", None)
    open_tinyppi_pending = getattr(win, "_pending_tinyppi", False)
    del win
    if open_tinyppi_pending:
        clear_overlay_state(xbmcgui.Window(10000))
        _delay(250)
        from ui.overlay import open_tinyppi
        open_tinyppi()
        return
    if mode:
        # The dialog and its closing animation are fully gone now, so a native
        # VS10 action will reach the fullscreen video player instead of being
        # ignored. Let the underlying window settle first, then apply.
        _delay(250)
        set_mode(mode)
