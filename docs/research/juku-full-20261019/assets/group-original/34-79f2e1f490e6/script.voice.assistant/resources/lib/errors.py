"""Shared capture exception without importing ALSA or native decoders."""


class AudioError(RuntimeError):
    pass
