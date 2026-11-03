"""Text matching against timed transcripts."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .transcript import Cue

SPAN = 4  # captions break mid-sentence, so a quote may run across this many consecutive cues
FUZZY = 0.85


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return re.sub(r"[^a-z0-9']+", " ", text).strip()


def find_quote(quote: str, cues: list[Cue], around: float | None = None, radius: float = 45.0) -> float | None:
    """Start time of the cue where ``quote`` begins, or None if it isn't in the transcript.

    Each cue starts a window of the next few cues. Every window that begins at or before the quote and
    reaches past it contains it, so the *latest* matching window starts at the cue where the quote begins.
    When ``around`` is given, only cues near that time are considered first.
    """
    q = normalise(quote)
    if len(q.split()) < 3:
        return None
    candidates = [i for i, c in enumerate(cues) if around is None or abs(c.start - around) <= radius]
    windows = {i: normalise(" ".join(c.text for c in cues[i : i + SPAN])) for i in candidates}

    exact = [i for i in candidates if q in windows[i]]
    if exact:
        return cues[max(exact)].start

    best_i, best = None, 0.0
    for i in candidates:
        w = windows[i]
        m = SequenceMatcher(None, q, w, autojunk=False).find_longest_match(0, len(q), 0, len(w))
        score = m.size / len(q)
        if score > best or (score == best and best_i is not None and i > best_i):
            best_i, best = i, score
    if best_i is not None and best >= FUZZY:
        return cues[best_i].start
    if around is not None:
        return find_quote(quote, cues, None)  # the model's time was off; look across the whole video
    return None
