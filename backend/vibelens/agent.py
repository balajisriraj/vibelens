"""The chat agent: Claude with three transcript tools, run in a bounded loop.

The agent decides what to look up. Every range it sees is recorded, and after the answer is written each
timestamp it cites is checked against those ranges, so a citation is "verified" only if the agent actually
read the transcript at that moment.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .embeddings import Embedder
from .llm import LLM
from .store import Store
from .transcript import Cue, parse_ts, ts

SYSTEM = """You answer questions about one video using its transcript tools.
- Look things up before answering: search the transcript, and read around a moment when you need exact wording.
- Put a timestamp like [3:41] after every claim, pointing to where it is said. Use only times from tool results.
- If the video doesn't cover the question, say so in one sentence and suggest a related thing it does cover.
- Under 120 words. Plain language. British spelling. Never use em dashes; use a plain hyphen.

Video: {title} ({duration})"""

TOOLS = [
    {
        "name": "search_transcript",
        "description": "Hybrid keyword + semantic search over the video's transcript. Returns the best matching "
        "passages, each with its time range and its individual timed lines.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look for, in a few words."}},
            "required": ["query"],
        },
    },
    {
        "name": "read_transcript",
        "description": "Read the exact transcript lines between two times (at most five minutes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start time, m:ss or h:mm:ss."},
                "end": {"type": "string", "description": "End time, m:ss or h:mm:ss."},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "list_chapters",
        "description": "The video's chapters with start times and one-line summaries.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

CITATION = re.compile(r"\[(\d{1,2}(?::\d{2}){1,2})\]")


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)


class ReadInput(BaseModel):
    start: str = Field(pattern=r"^\d{1,2}(:\d{2}){1,2}$")
    end: str = Field(pattern=r"^\d{1,2}(:\d{2}){1,2}$")


@dataclass
class Seen:
    """Transcript ranges the agent has looked at during one answer."""

    ranges: list[tuple[float, float]] = field(default_factory=list)

    def covers(self, t: float, tolerance: float) -> bool:
        return any(a - tolerance <= t <= b + tolerance for a, b in self.ranges)


def lines(cues: list[Cue], start: float, end: float) -> str:
    return "\n".join(f"[{ts(c.start)}] {c.text}" for c in cues if c.end >= start and c.start <= end)


@dataclass
class Agent:
    settings: Settings
    llm: LLM
    store: Store
    embedder: Embedder

    def _run_tool(self, video: dict, cues: list[Cue], name: str, args: dict, seen: Seen) -> tuple[str, str]:
        """Returns (result for the model, short summary for the UI)."""
        if name == "search_transcript":
            q = SearchInput.model_validate(args)
            hits = self.store.search(video["id"], q.query, self.embedder.embed([q.query])[0], 3)
            if not hits:
                return "No matching passages.", "no matches"
            blocks = []
            for i, h in enumerate(hits, 1):
                seen.ranges.append((h.segment.start, h.segment.end))
                span = f"{ts(h.segment.start)}-{ts(h.segment.end)}"
                blocks.append(f"Hit {i} [{span}]\n{lines(cues, h.segment.start, h.segment.end)}")
            return "\n\n".join(blocks), ", ".join(f"{ts(h.segment.start)}" for h in hits)
        if name == "read_transcript":
            r = ReadInput.model_validate(args)
            start, end = parse_ts(r.start), parse_ts(r.end)
            if end < start:
                start, end = end, start
            end = min(end, start + 300)
            seen.ranges.append((start, end))
            text = lines(cues, start, end)
            return text or "No transcript in that range.", f"{ts(start)}-{ts(end)}"
        if name == "list_chapters":
            chapters = (video.get("summary") or {}).get("chapters", [])
            return "\n".join(
                f"[{ts(c['start'])}] {c['title']}: {c['summary']}" for c in chapters
            ) or "No chapters yet.", (f"{len(chapters)} chapters")
        raise ValueError(f"Unknown tool {name}")

    async def ask(self, video_id: str, question: str, history: list[dict]) -> AsyncIterator[dict]:
        video = self.store.get(video_id)
        cues = [Cue(**c) for c in video["cues"]]
        system = SYSTEM.format(title=video["title"], duration=ts(video["duration"] or 0))
        messages: list[dict] = [*history[-8:], {"role": "user", "content": question}]
        seen = Seen()
        answer = ""
        started = time.perf_counter()

        for _step in range(self.settings.max_tool_steps):
            message = None
            async for event in self.llm.turn(system, messages, TOOLS, self.settings.chat_effort):
                if event["type"] == "text":
                    answer += event["text"]
                    yield event
                else:
                    message = event
            assert message is not None
            uses = [b for b in message["content"] if b["type"] == "tool_use"]
            if not uses or message["stop_reason"] in ("end_turn", "refusal"):
                break
            if message["stop_reason"] == "max_tokens":
                yield {"type": "text", "text": "\n\n(I ran out of room mid-lookup. Try a narrower question.)"}
                break
            messages.append({"role": "assistant", "content": message["content"]})
            results = []
            for use in uses:
                try:
                    output, brief = self._run_tool(video, cues, use["name"], use["input"], seen)
                    results.append({"type": "tool_result", "tool_use_id": use["id"], "content": output})
                    yield {"type": "tool", "name": use["name"], "input": use["input"], "result": brief}
                except (ValidationError, ValueError) as exc:
                    results.append(
                        {"type": "tool_result", "tool_use_id": use["id"], "content": str(exc), "is_error": True}
                    )
                    yield {"type": "tool", "name": use["name"], "input": use["input"], "result": "invalid input"}
            messages.append({"role": "user", "content": results})
            answer = ""  # only the final turn's text is the answer

        citations = []
        for stamp in dict.fromkeys(CITATION.findall(answer)):
            t = parse_ts(stamp)
            citations.append({"stamp": stamp, "t": t, "verified": seen.covers(t, self.settings.cite_tolerance)})
        yield {"type": "done", "citations": citations, "ms": round((time.perf_counter() - started) * 1000)}
