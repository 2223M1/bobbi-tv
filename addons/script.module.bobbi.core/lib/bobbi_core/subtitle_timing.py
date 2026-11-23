"""Bounded six-window display correlation for the existing subtitle binding.

Reuses the 100 Hz / +/-10 s method in tools/verify_subtitle_timing.py, with
integer bit signals instead of a PC numpy float array. No ASR, translation,
network, Kodi controls or claim that supplied intervals prove video identity.
Offsets are diagnostics only: this never silently shifts subtitle bytes.
"""
from bisect import bisect_left
import hashlib
import math

from bobbi_core.ledger import encode

RATE = 100
MARGIN = 10 * RATE
MAX_CUES = 10000


class TimingCancelled(RuntimeError):
    pass


def _intervals(rows, duration):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= MAX_CUES:
        raise ValueError('Bounded nonempty subtitle intervals required')
    checked = []
    for row in rows:
        if (not isinstance(row, (list, tuple)) or len(row) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                or not 0 <= row[0] < row[1] <= duration):
            raise ValueError('Finite ordered intervals within exact video duration required')
        ticks = (round(row[0] * RATE), round(row[1] * RATE))
        if ticks[0] == ticks[1]:
            raise ValueError('Cue shorter than timing measurement resolution')
        checked.append(ticks)
    return sorted(set(checked))


def _signal(rows, start, stop):
    signal = 0
    for left, right in rows:
        left, right = max(start, left), min(stop, right)
        if left < right:
            signal |= ((1 << (right - left)) - 1) << (left - start)
    return signal


def analyze(reference, candidate, duration, cancelled=lambda: False, windows=None):
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 60 <= duration <= 21600:
        raise ValueError('Bounded actual video duration required')
    expected, actual = _intervals(reference, duration), _intervals(candidate, duration)
    if windows is None:
        windows = [(index * duration / 6, (index + 1) * duration / 6) for index in range(6)]
    if not isinstance(windows, (list, tuple)) or len(windows) != 6:
        raise ValueError('Six explicit measured windows required')
    for index, window in enumerate(windows):
        if (not isinstance(window, (list, tuple)) or len(window) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in window)
                or not index * duration / 6 <= window[0] < window[1] <= (index + 1) * duration / 6
                or window[1] - window[0] < 5):
            raise ValueError('Measured windows must be continuous and dispersed')
    starts = [row[0] for row in actual]
    measurements, diagnostics = [], []
    insufficient = False
    for index in range(6):
        if cancelled():
            raise TimingCancelled('Subtitle timing cancelled')
        left, right = round(windows[index][0] * RATE), round(windows[index][1] * RATE)
        width = right - left
        ref = _signal(expected, left, right)
        sub = _signal(actual, left - MARGIN, right + MARGIN)
        mask = (1 << width) - 1
        ref_count = ref.bit_count()
        best, best_shift, best_bits = (-1, -MARGIN), 0, 0
        for shift in range(-MARGIN, MARGIN + 1):
            if shift % 100 == 0 and cancelled():
                raise TimingCancelled('Subtitle timing cancelled')
            bits = (sub >> (shift + MARGIN)) & mask
            key = ((bits & ref).bit_count(), -abs(shift))
            if key > best:
                best, best_shift, best_bits = key, shift, bits
        denominator = ref_count + best_bits.bit_count()
        overlap = 2 * best[0] / denominator if denominator else 0.0
        # Actual cue samples, not copies of one window correlation value.
        residuals = []
        for start, end in expected:
            if not left <= start < right:
                continue
            pos = bisect_left(starts, start)
            neighbors = starts[max(0, pos - 1):pos + 1]
            nearest = min(neighbors, key=lambda value: (abs(value - start), value))
            residuals.append((nearest - start) / RATE)
        outliers = sum(abs(value) > .5 for value in residuals)
        if len(residuals) < 5 or not .01 <= ref_count / width <= .95:
            insufficient = True
        measurements.append(dict(at=(left + right) / (2 * RATE), samples=len(residuals),
                                 outliers=outliers, residuals=residuals, overlap_f1=overlap))
        diagnostics.append(dict(from_seconds=left / RATE, to_seconds=right / RATE,
                                best_shift_seconds=best_shift / RATE,
                                reference_active_ticks=ref_count,
                                candidate_active_ticks=best_bits.bit_count(),
                                overlap_ticks=best[0]))
    passed = all(row['outliers'] == 0 and row['overlap_f1'] >= .75
                 and abs(detail['best_shift_seconds']) <= .5
                 for row, detail in zip(measurements, diagnostics))
    return dict(state='INSUFFICIENT_REFERENCE' if insufficient else
                'TIMING_CORRELATION_NOT_VISUAL_PROOF' if passed else 'TIMING_REJECTED',
                measurements=measurements, diagnostics=diagnostics, measured_windows=windows,
                reference_intervals_sha256=hashlib.sha256(encode(expected).encode()).hexdigest(),
                candidate_intervals_sha256=hashlib.sha256(encode(actual).encode()).hexdigest(),
                rate_hz=RATE, max_search_seconds=MARGIN / RATE,
                # Full two-signal payload upper bound, not process RSS evidence.
                signal_bytes_bound=math.ceil((duration * RATE + 2 * MARGIN) / 8) * 2)
