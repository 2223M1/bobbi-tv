"""Public QR code rendering interface backed by bobbi_platform's pinned Segno."""
from pathlib import Path


def write_png(content, destination, *, scale=10, border=4, micro=False):
    """Render a QR code PNG to destination and verify valid PNG output."""
    if type(content) is not str or not 0 < len(content) <= 4096 or '\x00' in content:
        raise ValueError('QR_CONTENT_INVALID')
    if (type(scale) is not int or not 1 <= scale <= 64
            or type(border) is not int or not 0 <= border <= 16
            or type(micro) is not bool):
        raise ValueError('QR_PARAMETERS_INVALID')
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    from ._vendor import segno
    code = segno.make(content, micro=micro)
    code.save(str(target), scale=scale, border=border)
    return str(target)
