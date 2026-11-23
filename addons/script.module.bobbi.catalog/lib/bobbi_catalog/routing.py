"""Routing-only eligibility and stable neutral ties; never relax file identity."""
import hashlib
import json
import re


UNSUPPORTED_SUFFIX = re.compile(
    r'(?i)\.(?:iso|img|cue|bin|mdf|mds|zip|rar|7z|tar|gz|bz2|xz|zst|tgz|torrent|'
    r'nfo|txt|md|pdf|docx?|xlsx?|srt|ass|ssa|sub|idx|vtt|sup|'
    r'flac|mp3|m4a|aac|wav|ape|ogg|opus|jpg|jpeg|png|gif|webp|bmp|tiff?|svg|'
    r'exe|msi|vob|webm|mov|wmv|flv|rmvb|rm|3gp)$'
)


def eligible_text(value):
    """Skip only explicit unsupported suffixes; genuine title directories stay."""
    return isinstance(value, str) and bool(value.strip()) and not UNSUPPORTED_SUFFIX.search(value.strip())


def route_order(item, spec):
    """Keep quality/year score, break ties without a legacy/supplement bias."""
    media = spec.get('media_key')
    if not media:
        media = json.dumps([spec.get('mode'), spec.get('tmdb_id'), spec.get('year'),
                            sorted(spec.get('aliases', []))], ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256((str(media) + '\0' + item['group']).encode('utf-8')).digest()
    return -item['score'], digest, item['group']
