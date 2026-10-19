"""Wrap full chat messages into readable rows in Kodi's single conversation list."""
import unicodedata


def message_lines(text, width=84):
    lines = []
    for paragraph in text.split('\n'):
        line, used = '', 0
        for char in paragraph:
            size = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
            if line and used + size > width:
                lines.append(line)
                line, used = '', 0
            line += char
            used += size
        lines.append(line)
    return lines


def message_rows(text, width=84):
    lines = message_lines(text, width)
    return ['\n'.join(lines[index:index + 2]) for index in range(0, len(lines), 2)]


def message_page(starts, total, block, top, direction, entering=False, page=12):
    """Return the visible range to select, or None for the bottom controls.

    A message is one navigation stop. Only content outside the viewport needs
    another step; page-sized moves overlap so no text disappears between steps.
    ``total`` includes a trailing spacer for each logical block.
    """
    def bounds(number):
        return starts[number], (starts[number + 1] if number + 1 < len(starts) else total) - 2

    start, end = bounds(block)
    if not entering:
        at_edge = start >= top if direction < 0 else end < top + page
        if at_edge:
            block += direction
            if not 0 <= block < len(starts):
                return None
            start, end = bounds(block)
            entering = True
    if entering:
        top = start if direction > 0 else max(start, end - page + 1)
    else:
        top = max(start, min(top + direction * (page - 3), end - page + 1))
    return top, min(end, top + page - 1)
