"""Display platform names without changing source identity or transport.

These exact internal indexer values are emitted by the existing 115 providers.
Title text, addon aliases and BT metadata never establish a different platform.
This is presentation only, not an availability or file-identity assertion.
"""

_115_INDEXERS = frozenset(('115 资源目录', '腾讯文档 · 115分享', '115 · CD2', '115 · CD2 · 漫迪'))


def source_platform_label(source):
    indexer = getattr(source, 'indexer', '')
    if getattr(source, 'type', '') == 'Direct' and indexer in _115_INDEXERS:
        return '115 网盘'
    return indexer
