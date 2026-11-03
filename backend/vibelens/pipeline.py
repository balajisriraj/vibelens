"""The ingest pipeline: a straight line, each stage reporting progress.

    source ──> transcript ──> segments ──> index ──> summary ──> verify

Stages are plain async functions rather than a graph: nothing branches, and a linear pipeline is
easier to resume, time and explain. Each yields events the UI shows as a progress rail.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .embeddings import Embedder
from .llm import LLM, Summary
from .sources import SourceError, transcribe, youtube_captions, youtube_title
from .store import Store
from .text import find_quote
from .transcript import Cue, parse_captions, segment, target_length, to_dicts, ts

SYSTEM = """You turn video transcripts into a viewer's guide.
- Use only what is said in the transcript. Never invent claims, names or numbers.
- Times are in seconds and must come from the transcript's own timestamps.
- Quotes must be copied word for word from the transcript.
- British spelling. Never use em dashes; use a plain hyphen."""


@dataclass
class Job:
    video_id: str
    kind: str  # youtube | upload | captions | sample
    ref: str  # YouTube id, or the stored file path


def transcript_prompt(cues: list[Cue], title: str, duration: float) -> str:
    lines = "\n".join(f"[{ts(c.start)}] {c.text}" for c in cues)
    return (
        f"Video: {title}\nLength: {ts(duration)}\n\n"
        f"Write the guide for this video. Chapter and moment times are seconds, copied from the line where "
        f"they begin (for example [3:05] is 185).\n\n<transcript>\n{lines}\n</transcript>"
    )


def verify(summary: Summary, cues: list[Cue], duration: float) -> dict:
    """Snap chapters to real lines, and pin each moment to where its quote is actually said."""
    starts = [c.start for c in cues]

    def snap(t: float) -> float:
        return min(starts, key=lambda s: abs(s - t)) if starts else 0.0

    chapters = sorted(({**c.model_dump(), "start": snap(c.start)} for c in summary.chapters), key=lambda c: c["start"])
    deduped: list[dict] = []
    for c in chapters:
        if not deduped or c["start"] > deduped[-1]["start"]:
            deduped.append(c)
    if deduped:
        deduped[0]["start"] = 0.0
    for i, c in enumerate(deduped):
        c["end"] = deduped[i + 1]["start"] if i + 1 < len(deduped) else duration

    moments = []
    for m in summary.moments:
        found = find_quote(m.quote, cues, around=m.start)
        moments.append(
            {**m.model_dump(), "start": found if found is not None else snap(m.start), "verified": found is not None}
        )
    return {**summary.model_dump(), "chapters": deduped, "moments": moments}


@dataclass
class Pipeline:
    settings: Settings
    llm: LLM
    store: Store
    embedder: Embedder

    async def run(self, job: Job, emit: Callable[[dict], None] | None = None) -> AsyncIterator[dict]:
        def event(**e) -> dict:
            if emit:
                emit(e)
            return e

        vid = job.video_id
        title = self.store.get(vid)["title"]

        # 1. transcript
        started = time.perf_counter()
        yield event(type="step", step="transcript", status="running")
        if job.kind == "youtube":
            cues = await asyncio.to_thread(youtube_captions, job.ref)
            title = await asyncio.to_thread(youtube_title, job.ref)
            how = "YouTube captions"
        elif job.kind == "captions":
            cues = parse_captions(Path(job.ref).read_text(encoding="utf-8", errors="replace"))
            how = "caption file"
        elif job.kind == "sample" and self.settings.sample_transcript.exists():
            cues = parse_captions(self.settings.sample_transcript.read_text(encoding="utf-8"))
            how = "bundled Whisper transcript"
        else:
            cues, _ = await asyncio.to_thread(transcribe, Path(job.ref), self.settings.whisper_model)
            how = f"Whisper {self.settings.whisper_model}"
        if not cues:
            raise SourceError("No transcript found.")
        duration = cues[-1].end
        if duration > self.settings.max_minutes * 60:
            raise SourceError(f"VibeLens handles videos up to {self.settings.max_minutes} minutes.")
        self.store.update(vid, cues=to_dicts(cues), duration=duration, title=title)
        yield event(
            type="step",
            step="transcript",
            status="done",
            detail=f"{len(cues)} lines via {how}",
            ms=round((time.perf_counter() - started) * 1000),
            title=title,
            duration=duration,
        )

        # 2. segments + 3. index
        started = time.perf_counter()
        yield event(type="step", step="index", status="running")
        segments = segment(cues, target_length(duration))
        vectors = await asyncio.to_thread(self.embedder.embed, [s.text for s in segments])
        self.store.index(vid, segments, vectors)
        yield event(
            type="step",
            step="index",
            status="done",
            detail=f"{len(segments)} segments, hybrid search ready",
            ms=round((time.perf_counter() - started) * 1000),
        )

        # 4. summary + 5. verify
        started = time.perf_counter()
        yield event(type="step", step="summary", status="running")
        summary = await self.llm.structured(
            SYSTEM, transcript_prompt(cues, title, duration), Summary, self.settings.summary_effort
        )
        guide = verify(summary, cues, duration)
        self.store.update(vid, summary=guide, status="ready")
        verified = sum(m["verified"] for m in guide["moments"])
        yield event(
            type="step",
            step="summary",
            status="done",
            detail=f"{len(guide['chapters'])} chapters, {verified}/{len(guide['moments'])} moments pinned to their quote",
            ms=round((time.perf_counter() - started) * 1000),
        )
        yield event(type="done", summary=guide)
