from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from lib.utils.general.utils import Indexer
from lib.utils.kodi.settings import get_int_setting
from lib.utils.kodi.utils import get_setting, notification, translation


def validate_host(host: Optional[str], indexer: str) -> Optional[bool]:
    if not host or not host.strip():
        notification(f"{translation(30223)}: {indexer}")
        return None
    parsed = urlparse(host.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        notification(translation(30258) % indexer)
        return None
    return True


def validate_key(api_key: Optional[str], indexer: str) -> Optional[bool]:
    if not api_key:
        notification(f"{translation(30221)}: {indexer}")
        return None
    return True


def update_dialog(title: str, message: str, dialog: Any, percent: int = 0) -> None:
    if dialog:
        dialog.update(percent, translation(90661) % title, message)


def validate_credentials(indexer: str, host: Optional[str], api_key: Optional[str] = None) -> bool:
    """
    Validates the host and API key for a given indexer.
    """
    if not validate_host(host, indexer):
        return False
    return not (api_key is not None and not validate_key(api_key, indexer))


def build_jackett_client(settings_getter=None) -> Optional[object]:
    from lib.clients.jackett import Jackett
    setting = settings_getter or get_setting
    host = str(setting("jackett_host", ""))
    api_key = str(setting("jackett_apikey", ""))
    port = str(setting("jackett_port", "9117"))

    if not validate_credentials(Indexer.JACKETT, host, api_key):
        return None
    return Jackett(host, api_key, port, notification,
                   **({'settings_getter': setting} if settings_getter is not None else {}))


def build_prowlarr_client(settings_getter=None) -> Optional[object]:
    from lib.clients.prowlarr import Prowlarr
    setting = settings_getter or get_setting
    host = str(setting("prowlarr_host"))
    api_key = str(setting("prowlarr_apikey"))
    port = str(setting("prowlarr_port", "9696"))

    if not validate_credentials(Indexer.PROWLARR, host, api_key):
        return None
    return Prowlarr(host, api_key, port, notification,
                    **({'settings_getter': setting} if settings_getter is not None else {}))


def build_jackgram_client(settings_getter=None) -> Optional[object]:
    from lib.clients.jackgram.client import Jackgram
    setting = settings_getter or get_setting
    host = str(setting("jackgram_host"))
    token = str(setting("jackgram_token", ""))

    if not validate_credentials(Indexer.JACKGRAM, host):
        return None
    return Jackgram(host, notification, token)


def build_zilean_client(settings_getter=None) -> Optional[object]:
    from lib.clients.zilean import Zilean

    setting = settings_getter or get_setting
    timeout = int(setting("zilean_timeout"))
    host = str(setting("zilean_host"))

    if not validate_credentials(Indexer.ZILEAN, host):
        return None
    return Zilean(host, timeout, notification)


def build_burst_client(settings_getter=None) -> object:
    from lib.jacktook.client import Burst

    return Burst(notification, **({'settings_getter': settings_getter} if settings_getter is not None else {}))


def build_easynews_client(settings_getter=None) -> Optional[object]:
    from lib.clients.easynews import Easynews
    setting = settings_getter or get_setting
    user = str(setting("easynews_user"))
    password = str(setting("easynews_password"))
    timeout = int(setting("easynews_timeout"))

    if not validate_key(user, Indexer.EASYNEWS) or not validate_key(password, Indexer.EASYNEWS):
        return None
    return Easynews(user, password, timeout, notification)


def build_external_scraper_client(settings_getter=None) -> Optional[object]:
    from lib.clients.external_scraper import ExternalScraperClient
    from lib.utils.kodi.utils import kodilog

    kodilog("[ExternalScraper] build_external_scraper_client() called")

    setting = settings_getter or get_setting
    module_id = setting("external_scraper_module")
    if not module_id:
        return None

    module_display_name = (
        setting("external_scraper_module_name") or module_id.split(".")[-1].title()
    )
    client = ExternalScraperClient(module_id, module_display_name, notification)
    kodilog(
        f"[ExternalScraper] initialized={client.initialized}, "
        f"providers={len(client._providers) if client._providers else 0}"
    )
    if not client.initialized:
        return None
    return client


CLIENT_BUILDERS: Dict[str, Callable[[], Optional[object]]] = {
    Indexer.JACKETT: build_jackett_client,
    Indexer.PROWLARR: build_prowlarr_client,
    Indexer.JACKGRAM: build_jackgram_client,
    Indexer.BURST: build_burst_client,
    Indexer.EASYNEWS: build_easynews_client,
    Indexer.EXTERNAL_SCRAPER: build_external_scraper_client,
}


def get_client(indexer: str, *, settings_getter=None) -> Optional[object]:
    builder = CLIENT_BUILDERS.get(indexer)
    if not builder:
        return None
    return builder() if settings_getter is None else builder(settings_getter=settings_getter)
