"""File-level choices that allow one play but do not verify catalogue identity."""
from enum import Enum


class PlayOnceAction(Enum):
    # Values describe evidence only after a file has actually been selected.
    NO_MATCH = None
    USE_SOLE = 'SOLE_ELIGIBLE_FILE'
    ASK_USER = 'USER_CONFIRMED_FILE'

    @classmethod
    def for_candidates(cls, files):
        if not files:
            return cls.NO_MATCH
        return cls.USE_SOLE if len(files) == 1 else cls.ASK_USER


PLAY_ONCE_EVIDENCE = (PlayOnceAction.ASK_USER.value, PlayOnceAction.USE_SOLE.value)
