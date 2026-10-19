"""Archived v1 evidence generator, only for migration/diagnostic regression.

Not packaged with the addon and never used to decide subtitle readiness.
"""
import math
from bobbi_core.subtitle_binding import checked_video, digest


def six_window_timing(video, subtitle_sha256, reference_sha256, duration, measurements,
                      offset=0.0, scale=1.0):
    checked_video(video)
    digest(subtitle_sha256)
    digest(reference_sha256)
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    if (not finite(duration) or not 60 <= duration <= 21600 or not finite(offset)
            or abs(offset) > 600 or not finite(scale) or not 0.9 <= scale <= 1.1
            or not isinstance(measurements, list) or len(measurements) != 6):
        raise ValueError('Six bounded timing windows and finite transform required')
    windows = []
    for index, row in enumerate(measurements):
        if not isinstance(row, dict) or set(row) != {'at', 'samples', 'outliers', 'residuals', 'overlap_f1'}:
            raise ValueError('Complete timing measurements required')
        at, samples, outliers, residuals = row['at'], row['samples'], row['outliers'], row['residuals']
        if (not finite(at) or not index * duration / 6 <= at < (index + 1) * duration / 6
                or type(samples) is not int or not 5 <= samples <= 10000
                or type(outliers) is not int or not 0 <= outliers <= samples
                or not isinstance(residuals, list) or len(residuals) != samples
                or any(not finite(value) for value in residuals)
                or not finite(row['overlap_f1']) or not 0 <= row['overlap_f1'] <= 1):
            raise ValueError('Missing or malformed dispersed timing samples')
        passed = (outliers == 0 and max(abs(value) for value in residuals) <= .5
                  and row['overlap_f1'] >= .75)
        windows.append(dict(row, passed=passed))
    return dict(kind='six_windows', video_key=video['key'], subtitle_sha256=subtitle_sha256,
                reference_sha256=reference_sha256, duration=duration, offset=offset, scale=scale,
                windows=windows, state='TIMING_CORRELATION_NOT_VISUAL_PROOF' if all(w['passed'] for w in windows)
                else 'TIMING_REJECTED')
