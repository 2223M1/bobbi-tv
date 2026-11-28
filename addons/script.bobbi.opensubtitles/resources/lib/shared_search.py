"""Reuse the player's inspected Chinese subtitles in the existing manual picker."""
from bobbi_core.subtitle_candidates import AssrtCandidates, LookupStopped


class SharedSearch:
    shared_search = True

    def __init__(self, profile, root, current):
        self.source = AssrtCandidates(None, profile / 'subtitle-cache283',
                                      token_file=profile / 'assrt-token', current=current)
        self.root = root
        self.match = None

    def search(self, context, deadline, cancelled):
        self.match = None
        query = dict(context, mode='series' if context['mode'] == 'tv' else 'movie')
        try:
            found = self.source.candidates(query, deadline, cancelled, root=self.root)
        except LookupStopped as error:
            if str(error) in {'NO_MATCHED_CHINESE_TEXT', 'MATCHED_SUBTITLE_UNAVAILABLE'}:
                return []
            raise
        info = found.get('source') or {}
        self.match = dict(title=info.get('filename') or info.get('title') or context['title'],
                          language='中文双语' if found.get('bilingual') else '中文')
        self.result = dict(found['file'], bilingual=found.get('bilingual') is True,
                           sync_verified=False, cached=True)
        return [self.match]

    def download(self, choice, context, deadline, cancelled, root):
        self.source.guard(deadline, cancelled)
        if choice is not self.match or root != self.root:
            raise ValueError('DOWNLOAD_DESCRIPTOR_INVALID')
        return self.result
