"""Display platform names without changing source identity or transport.

These exact internal indexer values are emitted by the existing 115 providers.
Title text, addon aliases and BT metadata never establish a different platform.
This is presentation only, not an availability or file-identity assertion.
"""

from bobbi_core.library_labels import ref

_SHARED = ('自选源库 · 115', '自选源库 · 115分享')
_DOCS = ('115 资源目录', '腾讯文档 · 115分享')
_115_INDEXERS = frozenset((*_SHARED, *_DOCS, '115 · CD2', '115 · CD2 · 漫迪'))


def source_platform_label(source):
    indexer = getattr(source, 'indexer', '')
    if getattr(source, 'type', '') == 'Direct' and indexer in _115_INDEXERS:
        return '115 网盘'
    if indexer == '漫迪 MDsub' and getattr(source, 'type', '') == 'Direct':
        return '网页直连'
    return indexer


def source_libraries(source):
    """Memberships are supplied by the owning adapter, never guessed from a release name."""
    if getattr(source, 'type', '') != 'Direct':
        return {}
    site = getattr(source, 'indexer', '')
    if site == '漫迪 MDsub' and getattr(source, 'guid', '').startswith('mdsub:'):
        return {ref('mdsub', 'public'): '漫迪公开片库'}
    if site in _SHARED and getattr(source, 'guid', '').startswith('sharelib:'):
        return getattr(source, 'sourceLibraries', {}) or {}
    if site in _DOCS and getattr(source, 'guid', '').startswith('qqdocs:'):
        return getattr(source, 'sourceLibraries', {}) or {ref('qqdocs', 'catalogue'): '腾讯文档目录'}
    if site in ('115 · CD2', '115 · CD2 · 漫迪'):
        return {ref('personal', site): '我的 115 片库' if site == '115 · CD2' else '漫迪片库'}
    return {}
