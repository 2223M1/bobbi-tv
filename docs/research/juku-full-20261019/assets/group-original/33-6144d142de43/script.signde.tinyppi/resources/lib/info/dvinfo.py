"""Dolby Vision and HDR values exposed by the CoreELEC 21 player API.

The CE21 forks already parse the active stream and publish the fields TinyPPI
needs through ``Player.Process``. Keeping this small formatting layer lets the
overlay, splash, and property publisher share consistent values directly from
the fork's parsed player state.
"""

import re

import xbmc
import xbmcaddon
import xbmcgui


_ADDON = xbmcaddon.Addon()
_LABEL_NA = 32033

L5_EMPTY = "0 | 0 | 0 | 0"
L1_EMPTY = "0 | 0 | 0"


def _na_label() -> str:
    return _ADDON.getLocalizedString(_LABEL_NA) or "N/A"


def na_label() -> str:
    """Return TinyPPI's localized unavailable-value label."""
    return _na_label()


def is_status_label(value: str) -> bool:
    """Whether *value* is TinyPPI's unavailable-value label."""
    return value == _na_label()


def _process(name: str) -> str:
    """Read one CE21 Player.Process label, rejecting unknown-label echoes."""
    label = f"Player.Process({name})"
    value = (xbmc.getInfoLabel(label) or "").strip()
    return "" if value.lower() == label.lower() else value


def _playing() -> bool:
    return xbmc.getCondVisibility("Player.HasVideo")


def _value(name: str) -> str:
    value = _process(name)
    return value or (_na_label() if _playing() else "")


def _bool(name: str) -> str:
    value = _process(name).lower()
    if value in ("1", "true", "yes"):
        return "true"
    if value in ("0", "false", "no"):
        return "false"
    return ""


def _joined(*names: str) -> str:
    values = [_process(name) for name in names]
    return " | ".join(values) if all(values) else ""


def _source_hdr_label() -> str:
    return _process("video.source.hdr.type") or _process("video.hdr.type")


def _normalise_el(value: str) -> str:
    lowered = value.lower()
    if "full" in lowered or "fel" in lowered:
        return "FEL"
    if "minimum" in lowered or "mel" in lowered:
        return "MEL"
    return value


def _profile() -> str:
    """Return the source profile and compatibility id, such as ``7.6``."""
    profile = (
        _process("video.source.dovi.profile")
        or _process("video.dovi.profile")
    )
    if not profile or profile == "0":
        return ""
    compatibility = (
        _process("video.source.dovi.bl.signal.compatibility")
        or _process("video.dovi.bl.signal.compatibility")
    )
    return f"{profile}.{compatibility}" if compatibility else profile


def get_hdr_format() -> str:
    """Return the normalized source HDR token used by TinyPPI's layouts."""
    value = _source_hdr_label().lower()
    if "dolby" in value or "dovi" in value:
        return "dolbyvision"
    if "hdr10+" in value or "hdr10plus" in value:
        return "hdr10+"
    if "hdr10" in value or value == "hdr":
        return "hdr10"
    if "hlg" in value:
        return "hlg"
    return ""


def get_output_mode() -> str:
    """Return a readable description of the source video format."""
    hdr = get_hdr_format()
    if hdr == "dolbyvision":
        profile = _profile()
        el_type = get_dv_el_type_raw()
        parts = ["Dolby Vision"]
        if profile:
            parts.extend(("Profile", profile))
        if el_type in ("FEL", "MEL"):
            parts.append(el_type)
        return " ".join(parts)
    return {"hdr10+": "HDR10+", "hdr10": "HDR10", "hlg": "HLG", "": "SDR"}[hdr]


def get_cm_version() -> str:
    """Return the active Dolby Vision metadata/CM version."""
    return _value("video.dovi.meta.version")


def get_structure() -> str:
    """Return ``ST-SL``, ``ST-DL``, or ``DT-DL`` for the source."""
    source = _source_hdr_label()
    match = re.search(r"\((ST-SL|ST-DL|DT-DL)\)", source, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    structure = _process("video.dovi.dual.track")
    if structure:
        return structure
    if get_hdr_format() == "dolbyvision":
        return "ST-DL" if _bool("video.source.dovi.el.present") == "true" else "ST-SL"
    return _na_label() if _playing() else ""


def get_l5_offsets() -> str:
    """Return current L5 offsets as left | right | top | bottom."""
    return _joined(
        "video.dovi.l5.left.offset", "video.dovi.l5.right.offset",
        "video.dovi.l5.top.offset", "video.dovi.l5.bottom.offset",
    ) or (L5_EMPTY if _playing() else "")


def get_l1_nits() -> str:
    """Return current L1 luminance as min | max | average nits."""
    return _joined(
        "video.dovi.l1.min.nits", "video.dovi.l1.max.nits",
        "video.dovi.l1.avg.nits",
    ) or (L1_EMPTY if _playing() else "")


def get_l1_pq() -> str:
    """Return current L1 luminance as min | max | average PQ codes."""
    return _joined(
        "video.dovi.l1.min.pq", "video.dovi.l1.max.pq",
        "video.dovi.l1.avg.pq",
    ) or (L1_EMPTY if _playing() else "")


def _source_mdl() -> str:
    return _joined("video.dovi.source.min.nits", "video.dovi.source.max.nits")


def _l6_mdl() -> str:
    return _joined("video.dovi.l6.min.lum", "video.dovi.l6.max.lum")


def get_rpu_mdl() -> str:
    """Return source mastering range, falling back to L6."""
    return _source_mdl() or _l6_mdl() or ("0 | 0" if _playing() else "")


def get_rpu_mdl_from_source() -> str:
    """Return true when the source mastering range contains useful data."""
    maximum = _process("video.dovi.source.max.nits")
    return "true" if maximum and maximum not in ("0", "0.0", "0.0000") else ""


def get_l6_rpu_max_cll_fall() -> str:
    return _joined(
        "video.dovi.l6.max.cll", "video.dovi.l6.max.fall"
    ) or ("0 | 0" if _playing() else "")


def get_hdr10_mdl(l6_fallback: bool = False) -> str:
    value = _joined("video.hdr.min.lum", "video.hdr.max.lum")
    if not value and l6_fallback:
        value = _l6_mdl()
    return value or ("0 | 0" if _playing() else "")


def get_hdr10_max_cll_fall(l6_fallback: bool = False) -> str:
    value = _joined("video.hdr.max.cll", "video.hdr.max.fall")
    if not value and l6_fallback:
        value = _joined("video.dovi.l6.max.cll", "video.dovi.l6.max.fall")
    return value or ("0 | 0" if _playing() else "")


def get_dv_version() -> str:
    major = _process("video.dovi.version.major")
    minor = _process("video.dovi.version.minor")
    return f"{major}.{minor}" if major and minor else ""


def get_dv_profile() -> str:
    return _profile()


def get_dv_rpu_present() -> str:
    return _bool("video.dovi.rpu.present")


def get_dv_bl_present() -> str:
    return _bool("video.dovi.bl.present")


def get_dv_el_present() -> str:
    source = _bool("video.source.dovi.el.present")
    active = _bool("video.dovi.el.present")
    # Some CE21 builds initialise the source copy to false before (or instead
    # of) filling it, while the active-stream field already carries the real
    # EL state. A confirmed EL from either parsed view must win.
    if "true" in (source, active):
        return "true"
    if "false" in (source, active):
        return "false"
    return ""


def get_dv_el_type_raw() -> str:
    # Prefer the source field, but only when it identifies a real EL. On some
    # CE21 builds it is present as the literal ``none`` while the active-stream
    # field correctly reports ``full``/``minimum``. Treating ``none`` as a
    # usable value put every such P7 title in the neutral DV pill bucket.
    for name in ("video.source.dovi.el.type", "video.dovi.el.type"):
        value = _normalise_el(_process(name))
        if value in ("FEL", "MEL"):
            return value
    return _profile()


def get_dv_el_type() -> str:
    """Return FEL/MEL with TinyPPI's configured accent color."""
    value = get_dv_el_type_raw()
    if value not in ("FEL", "MEL"):
        return value
    prop = "SigndeTinyPPI.FelColor" if value == "FEL" else "SigndeTinyPPI.MelColor"
    fallback = "FF81C784" if value == "FEL" else "FFFFB74D"
    color = xbmcgui.Window(10000).getProperty(prop).strip() or fallback
    return f"[COLOR {color}]{value}[/COLOR]"


def get_bit_depth() -> str:
    return _value("video.bit.depth")
