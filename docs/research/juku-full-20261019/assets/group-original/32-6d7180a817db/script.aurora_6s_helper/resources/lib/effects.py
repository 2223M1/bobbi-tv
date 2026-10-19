"""Pure TCA6507 encoder. Outputs P0/P1/P2 are red/green/blue."""
import math

TIMES = (0, 64, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 5760, 8128, 16320)


def levels(rgb, brightness):
    return tuple(max(0, min(15, int(c * brightness * 15 / 25500 + .5))) for c in rgb)


def smooth_levels(values):
    """Fit three RGB levels into two fade banks with least squared level error.

    Keep zero channels off; merging the closest pair minimizes the error.
    """
    unique = sorted(set(values) - {0})
    if len(unique) <= 2:
        return tuple(values)
    a, b = min(zip(unique, unique[1:]), key=lambda pair: pair[1] - pair[0])
    middle = int((a + b) / 2 + .5)
    return tuple(middle if v in (a, b) else v for v in values)


def encode(values, breathing=False, fade_ms=1536):
    """11 registers; never touches outputs P3-P6 except to leave them off.

    Steady has three programmable levels (bank0, bank1, master).
    Hardware breathing has two. Reject excess levels instead of changing color.
    """
    if len(values) != 3 or any(not 0 <= v <= 15 for v in values):
        raise ValueError('Invalid RGB hardware levels')
    unique = sorted(set(values) - {0})
    if breathing and len(unique) > 2:
        raise ValueError('Three independent levels require software breathing')
    registers = bytearray(11)
    for channel, value in enumerate(values):
        if not value:
            continue
        bank = unique.index(value)
        selector = (6 + bank) if breathing else (2, 3, 5)[bank]
        for bit in range(3):
            registers[bit] |= ((selector >> bit) & 1) << channel
    registers[8] = (unique[0] if unique else 0) | ((unique[1] if len(unique) > 1 else 0) << 4)
    registers[9] = unique[2] if len(unique) > 2 else 0
    if breathing:
        code = min(range(1, 16), key=lambda i: abs(TIMES[i] - fade_ms))
        registers[3] = registers[5] = code * 17
        registers[4] = 0x22  # 128 ms at peak
        off_code = min(range(16), key=lambda i: abs(TIMES[i] - fade_ms / 4))
        registers[6] = registers[7] = off_code * 17  # fast/medium/slow: 192/384/768 ms
        registers[10] = 0x88  # both banks start at fade-on
    return bytes(registers)


def software_frame(values, elapsed, fade_ms):
    fade = fade_ms / 1000.0
    t = elapsed % (2 * fade + .128 + fade / 4)
    if t < fade:
        factor = (1 - math.cos(math.pi * t / fade)) / 2
    elif t < fade + .128:
        factor = 1
    elif t < 2 * fade + .128:
        factor = (1 + math.cos(math.pi * (t - fade - .128) / fade)) / 2
    else:
        factor = 0
    return tuple(int(v * factor + .5) for v in values)
