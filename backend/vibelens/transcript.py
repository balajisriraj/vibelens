"""Timed text: cues from captions or speech recognition, and the segments we index and cite."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str


def ts(seconds: float) -> str:
    """Seconds to m:ss or h:mm:ss, the format citations use."""
    s = round(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_ts(text: str) -> float:
    """m:ss, h:mm:ss or hh:mm:ss.mmm (comma or dot) to seconds."""
    parts = text.strip().replace(",", ".").split(":")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


TIMING = re.compile(r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}")


def parse_captions(raw: str) -> list[Cue]:
    """WebVTT or SRT to cues. Styling tags, cue ids and notes are dropped; rolling duplicates are merged."""
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r", "").strip()):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        timing = next((i for i, line in enumerate(lines) if TIMING.search(line)), None)
        if timing is None:
            continue
        start, end = (parse_ts(x.split()[0]) for x in lines[timing].split("-->"))
        text = re.sub(r"<[^>]+>", "", " ".join(lines[timing + 1 :])).strip()
        if not text:
            continue
        if cues and text == cues[-1].text:  # auto-captions repeat lines while they scroll
            cues[-1].end = end
            continue
        cues.append(Cue(start, end, text))
    return cues


def to_vtt(cues: list[Cue]) -> str:
    def stamp(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"

    body = "\n\n".join(f"{stamp(c.start)} --> {stamp(c.end)}\n{c.text}" for c in cues)
    return f"WEBVTT\n\n{body}\n"


def segment(cues: list[Cue], target: float = 40.0) -> list[Segment]:
    """Group cues into segments of about ``target`` seconds, preferring to break at a pause or a sentence end."""
    hard = target * 1.6
    segments: list[Segment] = []
    buf: list[Cue] = []

    def close() -> None:
        if buf:
            text = re.sub(r"\s+", " ", " ".join(c.text for c in buf)).strip()
            segments.append(Segment(len(segments), buf[0].start, buf[-1].end, text))
            buf.clear()

    for i, cue in enumerate(cues):
        buf.append(cue)
        length = cue.end - buf[0].start
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        pause = nxt is not None and nxt.start - cue.end >= 0.8
        sentence = cue.text.rstrip().endswith((".", "?", "!"))
        if length >= hard or (length >= target and (pause or sentence)):
            close()
    close()
    return segments


def target_length(duration: float) -> float:
    """Shorter segments for short videos, so a citation points somewhere specific."""
    return max(12.0, min(40.0, duration / 10))


def window(cues: list[Cue], start: float, end: float) -> str:
    return " ".join(c.text for c in cues if c.end >= start and c.start <= end)


def to_dicts(items) -> list[dict]:
    return [asdict(x) for x in items]
