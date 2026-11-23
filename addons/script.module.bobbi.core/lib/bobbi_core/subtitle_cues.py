"""Bounded timing projection; original subtitle bytes and styles stay intact.

Adapts the existing compare_release_subtitles SRT parser and fonts ASS event
column logic. This projection is for evidence, not a replacement renderer.
"""
import math
import re

from bobbi_core.fonts import subtitle_text
MAX_CUES = 100000
CONTENT_POLICY = 'ass-invisible-events-v1'


def _seconds(value, ass=False):
    pattern = r'(\d{1,2}):([0-5]\d):([0-5]\d)\.(\d{2})' if ass else r'(?:(\d{1,2}):)?([0-5]\d):([0-5]\d)[,.](\d{3})'
    found = re.fullmatch(pattern, value.strip())
    if found is None:
        raise ValueError('Unsupported subtitle timestamp')
    hours, minutes, seconds, fraction = found.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction) / (100 if ass else 1000)


def parse(raw, extension, duration=None):
    # Duration is an optional diagnostic bound, not an automatic-load gate.
    # The subtitle's own timestamp syntax remains bounded independently.
    if duration is not None and (type(duration) not in (float, int) or not math.isfinite(duration) or not 60 <= duration <= 21600):
        raise ValueError('Actual finite video duration required')
    text = subtitle_text(raw).replace('\r\n', '\n').replace('\r', '\n')
    rows = []
    def append(start, stop, content):
        if not 0 <= start < stop or (duration is not None and stop > duration):
            raise ValueError('Subtitle cue outside exact video timeline')
        plain = re.sub(r'<[^>]*>|\{[^}]*\}', '', content).replace('\\N', '\n').replace('\\n', '\n')
        if not plain.strip():
            return
        rows.append(dict(start=start, end=stop, text=plain))
        if len(rows) > MAX_CUES:
            raise ValueError('Subtitle cue count budget')
    if extension in ('.ass', '.ssa'):
        if '[script info]' not in text.casefold() or '[events]' not in text.casefold():
            raise ValueError('ASS/SSA header required')
        # libass owns styles and fallback fonts. Font-analysis limitations
        # (animated font tags, legacy styles) must not reject valid text cues.
        section, columns = '', []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                section, columns = line.casefold(), []
            elif section == '[events]' and line.casefold().startswith('format:'):
                columns = [part.strip().casefold() for part in line.split(':', 1)[1].split(',')]
            elif section == '[events]' and line.casefold().startswith('dialogue:'):
                if not columns or columns[-1] != 'text' or not {'start', 'end'} <= set(columns):
                    raise ValueError('ASS timing columns required')
                values = line.split(':', 1)[1].split(',', len(columns) - 1)
                if len(values) != len(columns):
                    raise ValueError('Truncated ASS event')
                row = dict(zip(columns, values))
                # Vector-only events are not dialogue evidence. Do not rewrite
                # or drop them from the actual ASS supplied to libass.
                if re.search(r'\\p[1-9]', row['text']):
                    continue
                start, stop = _seconds(row['start'], True), _seconds(row['end'], True)
                # Invisible ASS events are not dialogue evidence. Keep the
                # original bytes for libass; malformed/reversed times still fail.
                if start == stop:
                    continue
                append(start, stop, row['text'])
    elif extension in ('.srt', '.vtt'):
        if extension == '.vtt' and not text.lstrip().startswith('WEBVTT'):
            raise ValueError('WebVTT signature required')
        stamp = r'(?:\d{1,2}:)?[0-5]\d:[0-5]\d[,.]\d{3}'
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = block.splitlines()
            if extension == '.vtt' and lines and lines[0].split(' ', 1)[0] in {'NOTE', 'STYLE', 'REGION'}:
                continue
            for index, line in enumerate(lines):
                match = re.fullmatch(r'\s*(' + stamp + r')\s+-->\s+(' + stamp + r')(?:\s+.*)?', line)
                if match:
                    append(_seconds(match[1]), _seconds(match[2]), '\n'.join(lines[index + 1:]))
                    break
                if '-->' in line:
                    raise ValueError('Malformed subtitle timing line')
    else:
        raise ValueError('Text timing projection unavailable for this format')
    if not rows:
        raise ValueError('No subtitle dialogue cues')
    return rows
