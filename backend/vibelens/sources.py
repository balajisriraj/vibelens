"""Where transcripts come from: YouTube captions, local speech recognition, or a caption file."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from .transcript import Cue

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class SourceError(ValueError):
    pass


def youtube_id(url: str) -> str:
    """Accepts watch, youtu.be, shorts, embed and live links. Anything else is rejected."""
    u = urllib.parse.urlparse(url.strip())
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = ""
    if host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        if u.path == "/watch":
            vid = urllib.parse.parse_qs(u.query).get("v", [""])[0]
        else:
            m = re.match(r"^/(?:shorts|embed|live|v)/([^/?#]+)", u.path)
            vid = m.group(1) if m else ""
    if not YOUTUBE_ID.match(vid):
        raise SourceError("That doesn't look like a YouTube video link.")
    return vid


def youtube_captions(video_id: str) -> list[Cue]:
    """Captions through youtube-transcript-api: the uploader's English track if there is one, else auto-captions."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import CouldNotRetrieveTranscript

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-GB", "en-US"])
    except CouldNotRetrieveTranscript as exc:
        raise SourceError("This video has no English captions to read. Try uploading the file instead.") from exc
    return [Cue(s.start, s.start + s.duration, s.text.replace("\n", " ").strip()) for s in fetched if s.text.strip()]


def youtube_title(video_id: str) -> str:
    """Public oEmbed endpoint: no key, no scraping."""
    query = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"})
    try:
        with urllib.request.urlopen(f"https://www.youtube.com/oembed?{query}", timeout=10) as res:
            return json.load(res).get("title") or "YouTube video"
    except Exception:
        return "YouTube video"


@lru_cache(maxsize=2)
def _whisper(model: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model, device="cpu", compute_type="int8")


def decode_audio(path: Path, rate: int = 16000):
    """Any audio or video file to 16 kHz mono float32, the input Whisper expects.

    Done here rather than inside faster-whisper so the PyAV version isn't pinned to what it expects.
    """
    import av
    import numpy as np

    try:
        container = av.open(str(path))
    except av.error.FFmpegError as exc:
        raise SourceError("That file isn't audio or video PyAV can read.") from exc
    with container:
        if not container.streams.audio:
            raise SourceError("That file has no audio track.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        chunks = [
            frame.to_ndarray().reshape(-1)
            for packet in container.decode(audio=0)
            for frame in resampler.resample(packet)
        ]
        chunks += [frame.to_ndarray().reshape(-1) for frame in resampler.resample(None)]
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe(path: Path, model: str = "base.en") -> tuple[list[Cue], float]:
    """Local speech recognition with faster-whisper. Returns cues and the media duration in seconds."""
    audio = decode_audio(path)
    segments, info = _whisper(model).transcribe(audio, vad_filter=True, beam_size=5)
    cues = [Cue(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments if s.text.strip()]
    if not cues:
        raise SourceError("No speech found in that file.")
    return cues, info.duration
