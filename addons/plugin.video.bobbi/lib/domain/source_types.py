"""Stable wire strings; importing a source label must not open an account or history store."""


class Enum:
    @classmethod
    def values(cls):
        return [value for name, value in vars(cls).items() if not name.startswith("_")]


class IndexerType(Enum):
    TORRENT = "Torrent"
    DIRECT = "Direct"
    DEBRID = "Debrid"
    STREMIO_DEBRID = "Stremio"


class Indexer(Enum):
    PROWLARR = "Prowlarr"
    STREMIO = "Stremio"
    JACKETT = "Jackett"
    TORRENTIO = "Torrentio"
    PEERFLIX = "Peerflix"
    MEDIAFUSION = "MediaFusion"
    JACKGRAM = "Jackgram"
    TELEGRAM = "Telegram"
    ELHOSTED = "Elfhosted"
    BURST = "Burst"
    ZILEAN = "Zilean"
    EASYNEWS = "Easynews"
    EXTERNAL_SCRAPER = "External Scraper"
