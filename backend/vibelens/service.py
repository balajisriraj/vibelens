"""Application service: ingest videos in the background and answer questions about them."""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from .agent import Agent
from .config import Settings
from .embeddings import Embedder, make_embedder
from .llm import LLM, LLMRefusal, make_llm
from .pipeline import Job, Pipeline
from .sources import SourceError, youtube_id
from .store import Store

log = logging.getLogger("vibelens")
MEDIA = {".mp4", ".m4a", ".mp3", ".wav", ".webm", ".mov", ".ogg", ".flac", ".aac", ".mkv"}
CAPTIONS = {".vtt", ".srt"}


class Bus:
    """Replayable event stream: late subscribers get the history first, then live events."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.closed = False
        self._changed = asyncio.Condition()

    async def publish(self, event: dict, final: bool = False) -> None:
        async with self._changed:
            self.events.append(event)
            self.closed = self.closed or final
            self._changed.notify_all()

    async def subscribe(self) -> AsyncIterator[dict]:
        seen = 0
        while True:
            async with self._changed:
                await self._changed.wait_for(lambda seen=seen: len(self.events) > seen or self.closed)
                fresh, seen, closed = self.events[seen:], len(self.events), self.closed
            for event in fresh:
                yield event
            if closed and seen == len(self.events):
                return


@dataclass
class Service:
    settings: Settings
    llm: LLM
    store: Store
    embedder: Embedder
    buses: dict[str, Bus] = field(default_factory=dict)
    _tasks: set[asyncio.Task] = field(default_factory=set)

    @classmethod
    def from_settings(cls, settings: Settings, llm: LLM | None = None, embedder: Embedder | None = None) -> Service:
        return cls(
            settings,
            llm or make_llm(settings),
            Store(settings.data_dir, settings.embedding_dim),
            embedder or make_embedder(settings),
        )

    @property
    def pipeline(self) -> Pipeline:
        return Pipeline(self.settings, self.llm, self.store, self.embedder)

    @property
    def agent(self) -> Agent:
        return Agent(self.settings, self.llm, self.store, self.embedder)

    # ── ingest ──
    def add_youtube(self, url: str) -> str:
        vid = youtube_id(url)
        video_id = self.store.create("YouTube video", "youtube", vid)
        self._start(Job(video_id, "youtube", vid))
        return video_id

    def add_file(self, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in MEDIA | CAPTIONS:
            raise SourceError("Upload a video, an audio file, or a .vtt / .srt caption file.")
        if len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise SourceError(f"Files up to {self.settings.max_upload_mb} MB, please.")
        kind = "captions" if suffix in CAPTIONS else "upload"
        video_id = self.store.create(Path(filename).stem.replace("-", " ").replace("_", " ")[:120], kind, filename)
        path = self.store.media_path(video_id, suffix)
        path.write_bytes(data)
        self.store.update(video_id, ref=path.name)
        self._start(Job(video_id, kind, str(path)))
        return video_id

    def add_sample(self) -> str:
        src = self.settings.sample_video
        video_id = self.store.create("What does a forward deployment engineer do?", "sample", src.name)
        path = self.store.media_path(video_id, src.suffix)
        shutil.copyfile(src, path)
        self.store.update(video_id, ref=path.name)
        self._start(Job(video_id, "sample", str(path)))
        return video_id

    def media(self, video_id: str) -> Path | None:
        video = self.store.get(video_id)
        if not video or video["kind"] not in ("upload", "sample"):
            return None
        path = self.store.dir / "media" / video["ref"]
        return path if path.exists() else None

    # ── background processing ──
    def _start(self, job: Job) -> None:
        self.buses[job.video_id] = Bus()
        task = asyncio.get_running_loop().create_task(self._process(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(self, job: Job) -> None:
        bus = self.buses[job.video_id]
        try:
            async for event in self.pipeline.run(job):
                await bus.publish(event, final=event["type"] == "done")
        except Exception as exc:
            log.exception("processing failed for %s", job.video_id)
            if isinstance(exc, SourceError):
                message = str(exc)
            elif isinstance(exc, LLMRefusal):
                message = "Claude declined to summarise this video."
            else:
                message = "Processing failed. Try again?"
            self.store.update(job.video_id, status="failed", error=message)
            await bus.publish({"type": "error", "message": message}, final=True)

    async def events(self, video_id: str) -> AsyncIterator[dict]:
        bus = self.buses.get(video_id)
        if bus is None:
            video = self.store.get(video_id)
            yield (
                {"type": "done", "summary": video["summary"]}
                if video["status"] == "ready"
                else {
                    "type": "error",
                    "message": video["error"] or "This video was interrupted. Add it again.",
                }
            )
            return
        async for event in bus.subscribe():
            yield event

    async def ask(self, video_id: str, question: str, history: list[dict]) -> AsyncIterator[dict]:
        async for event in self.agent.ask(video_id, question, history):
            yield event
