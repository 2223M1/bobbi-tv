from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TorrentStream:
    # Identification
    title: str = ""
    # Explicit personal-index provenance, not inferred from a cloud filename.
    bobiAnimeRelease: bool = False
    type: str = ""  # e.g., "torrent" or "debrid" or "direct"
    debridType: str = ""
    indexer: str = ""
    subindexer: str = ""
    addonKey: str = ""
    addonName: str = ""
    addonSourceName: str = ""
    addonInstanceLabel: str = ""
    guid: str = ""
    infoHash: str = ""

    # Stats
    size: int = 0  # in bytes
    seeders: int = 0
    peers: int = 0

    # Language info
    languages: List[str] = field(default_factory=list)
    fullLanguages: str = ""

    # Source info
    provider: str = ""
    publishDate: str = ""  # ISO format preferred

    # Quality and URLs
    quality: str = "N/A"
    url: str = ""
    streamSubtitles: List[Dict[str, Any]] = field(default_factory=list)

    # Flags
    isPack: bool = False
    isCached: bool = False
    addedToDebrid: bool = False

    # Codec & HDR
    codec: str = ""
    hdr: str = ""

    # Optional fields stay after the original positional fields for compatibility.
    stremioMetadata: Dict[str, Any] = field(default_factory=dict)
    localSubtitles: List[str] = field(default_factory=list)
    preparedResourceId: str = ""
    preparedVersionKey: str = ""
    preparedInfoHash: str = ""
    preparedSubtitle: Dict[str, Any] = field(default_factory=dict)
    # Set only after an independent catalogue's exact ID/episode gate.
    # Not a platform preference and not proof of playback or subtitle presence.
    catalogIdentity: Dict[str, Any] = field(default_factory=dict)
    # Converter-issued, exact-file-bound optional display facts; never authority.
    # Raw provider dictionaries are deliberately not accepted by its consumer.
    preparedMediaProfile: Any = None
    # Restriction only: unscoped range cards require catalogue-bearing exact
    # playback proof. Never a pack/file/readiness or provider identity claim.
    requiresCatalogEpisodeProof: bool = False
    # Account-scoped catalog failure; presentation/recommendation only.
    shareFailure: str = ''
    shareState: Dict[str, Any] = field(default_factory=dict)
