import json

import xbmcgui

from lib.clients.tmdb.utils.excluded_languages_data import EXCLUDABLE_LANGUAGES
from lib.utils.kodi.utils import get_setting, set_setting, translation

SETTING_KEY = "excluded_languages"
_LANGUAGE_PO_IDS = {
    "ar": 91126, "bn": 91127, "bg": 91128, "zh": 91129, "hr": 91130,
    "cs": 91131, "da": 91132, "nl": 91133, "en": 91134, "fi": 91135,
    "fr": 91136, "de": 91137, "el": 91138, "he": 91139, "hi": 91140,
    "hu": 91141, "id": 91142, "it": 91143, "ja": 91144, "kn": 91145,
    "ko": 91146, "ml": 91147, "no": 91148, "fa": 91149, "pl": 91150,
    "pt": 91151, "pa": 91152, "ro": 91153, "ru": 91154, "sr": 91155,
    "es": 91156, "sv": 91157, "ta": 91158, "te": 91159, "th": 91160,
    "tr": 91161, "uk": 91162, "vi": 91163,
}


def _language_label(entry):
    po_id = _LANGUAGE_PO_IDS.get(entry.get("id"))
    label = translation(po_id) if po_id else ""
    return label if isinstance(label, str) and label else entry["name"]


def open_excluded_languages_dialog():
    current_raw = get_setting(SETTING_KEY, "[]")
    try:
        current = json.loads(current_raw) if current_raw else []
    except (ValueError, TypeError):
        current = []

    options = [_language_label(lang) for lang in EXCLUDABLE_LANGUAGES]
    preselect = [i for i, lang in enumerate(EXCLUDABLE_LANGUAGES) if lang["id"] in current]

    selected = xbmcgui.Dialog().multiselect(
        translation(90813),
        options,
        preselect=preselect,
    )

    if selected is None:
        return

    new_selection = [EXCLUDABLE_LANGUAGES[i]["id"] for i in selected]
    set_setting(SETTING_KEY, json.dumps(new_selection))
