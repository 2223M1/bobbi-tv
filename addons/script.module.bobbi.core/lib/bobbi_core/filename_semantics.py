"""One bounded filename grammar; parsing is evidence, never selection authority.

Keep original spans so family fingerprints retain their established bytes.
Dimensions and codecs are technical fields, not seasons. Unknown prose is not
a conflict and this module cannot authorize playback or automatic continuation.
"""
from dataclasses import dataclass
import re


STRONG = (
    re.compile(r'(?<![a-z0-9])s(?P<season>\d+)[ ._-]*e(?P<episode>\d+)(?!\d)', re.I),
    # Conventional NxM is contiguous with a short season. DD2.0.x264 and
    # 1920x1080 (including nonstandard widths) cannot become episode evidence.
    re.compile(r'(?<![a-z0-9])(?P<season>\d{1,2})x(?P<episode>\d+)(?!\d)', re.I),
)
WEAK = (
    re.compile(r'(?<![a-z0-9])(?:episode|ep|e)[ ._-]*(?P<episode>\d+)(?![a-z0-9])', re.I),
    re.compile(r'(?:\s-\s*|\[)(?P<episode>\d{1,3})(?P<revision>v\d+)?(?=$|[ ._\]])', re.I),
)
MULTI = re.compile(
    r'(?:[ ._]*e(?P<joined>\d+)|[ ._]*[-–~～+&][ ._]*(?:'
    r'(?:s(?P<season>\d+)[ ._-]*)?e(?:p(?:isode)?)?[ ._-]*(?P<labelled>\d+)|'
    r'(?P<plain>\d+)(?![a-z0-9])))', re.I)
TECHNICAL = re.compile(
    r'(?<![a-z0-9])(?:\d{3,5}\s*[x×]\s*\d{3,5}|(?:2160|1080|720|576|480)[pi]|'
    r'(?:hevc|avc|[hx][ ._-]?26[45])(?:-yuv\d+p\d*(?:le|be)?)?|'
    r'yuv\d+p\d*(?:le|be)?|\d{1,2}[ ._-]?bits?|\d\.[01]|'
    r'flac|aac|e?ac3|dts(?:-hd)?|truehd|opus)(?![a-z0-9])|\[[0-9a-f]{8}\]', re.I)
REVISION = re.compile(r'(?i)v[1-9]\d*(?=$|[ ._\]\)–~～+&-])')


@dataclass(frozen=True)
class FilenameSemantics:
    text: str
    strong: tuple
    explicit: tuple
    anime: tuple
    technical_spans: tuple
    revision_spans: tuple

    @property
    def markers(self):
        return self.strong or self.explicit + self.anime

    def range_after(self, marker):
        # A repair revision belongs to this episode, before a possible range.
        end = marker.end()
        revision = REVISION.match(self.text, end)
        return MULTI.match(self.text, revision.end() if revision else end)

    def episode_pairs(self):
        pairs = {(int(m['season']), int(m['episode'])) for m in self.strong}
        for marker in self.strong:
            tail = self.range_after(marker)
            if tail:
                last = tail['joined'] or tail['labelled'] or tail['plain']
                pairs.add((int(tail['season'] or marker['season']), int(last)))
        return pairs


def parse_filename(text):
    if not isinstance(text, str) or len(text) > 16384 or '\x00' in text:
        raise ValueError('Bounded filename required')
    strong = tuple(m for pattern in STRONG for m in pattern.finditer(text))
    explicit = tuple(WEAK[0].finditer(text))
    # A leading [01] could be a group, not a verified episode. Selectors keep
    # their existing explicit-season requirement for all weak markers.
    anime = tuple(m for m in WEAK[1].finditer(text) if m.start() != 0)
    revisions = set()
    for marker in strong + explicit + anime:
        if marker.groupdict().get('revision'):
            revisions.add(marker.span('revision'))
        else:
            repair = REVISION.match(text, marker.end())
            if repair:
                revisions.add(repair.span())
    return FilenameSemantics(text, strong, explicit, anime,
                             tuple(m.span() for m in TECHNICAL.finditer(text)),
                             tuple(sorted(revisions)))
