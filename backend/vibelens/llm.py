"""Model layer.

- ``structured``: one JSON-schema call (the summary: chapters, key moments, vibe).
- ``turn``: one streamed step of the chat agent. It yields text deltas, then the full assistant message,
  whose content may include ``tool_use`` blocks for the agent loop to run.

``ScriptedLLM`` implements both deterministically from the transcript, so the pipeline, the agent loop
and the citation checks are all testable offline.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

from .config import Settings
from .embeddings import tokens

T = TypeVar("T", bound=BaseModel)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMRefusal(RuntimeError):
    pass


# ── summary schema ──
class Chapter(BaseModel):
    start: float = Field(description="Start time in seconds, taken from a transcript line.")
    title: str = Field(description="Three to six words.")
    summary: str = Field(description="One sentence.")


class Moment(BaseModel):
    start: float = Field(description="Time in seconds where the quote begins.")
    title: str = Field(description="A short headline for the moment.")
    why: str = Field(description="One sentence on why it matters.")
    quote: str = Field(description="Six to twenty words copied exactly from the transcript at that time.")


class Vibe(BaseModel):
    tone: str = Field(description="Two or three words, e.g. calm explainer, heated debate.")
    energy: Literal["low", "medium", "high"]
    audience: str = Field(description="Who will get the most from it, in a few words.")
    format: str = Field(description="talk, interview, tutorial, panel, lecture, vlog or other.")


class Summary(BaseModel):
    title: str = Field(description="A clear title for the video.")
    tldr: str = Field(description="Two or three sentences: what it covers and the main takeaway.")
    vibe: Vibe
    chapters: list[Chapter] = Field(description="Three to twelve chapters in order; the first starts at 0.")
    moments: list[Moment] = Field(description="Three to six moments worth jumping straight to.")
    topics: list[str] = Field(description="Three to eight topic tags, one or two words each.")
    questions: list[str] = Field(description="Three questions a viewer might ask about this video.")


class LLM(Protocol):
    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T: ...

    def turn(self, system: str, messages: list[dict], tools: list[dict], effort: str) -> AsyncIterator[dict]: ...


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    def tighten(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: tighten(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
        elif isinstance(node, list):
            node = [tighten(v) for v in node]
        return node

    schema = model.model_json_schema()
    defs = schema.pop("$defs", None)
    schema = tighten(schema)
    if defs:
        schema["$defs"] = {k: tighten(v) for k, v in defs.items()}
    return schema


class AnthropicLLM:
    def __init__(self, settings: Settings) -> None:
        import anthropic

        self.client = anthropic.AsyncAnthropic()
        self.model = settings.model

    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T:
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": strict_schema(schema)}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal("Claude declined this request.")
        return schema.model_validate(json.loads(next(b.text for b in response.content if b.type == "text")))

    async def turn(self, system: str, messages: list[dict], tools: list[dict], effort: str) -> AsyncIterator[dict]:
        # The transcript tools are tiny, but streamed tool calls still opt in to eager input streaming,
        # and every input is validated by the agent before it runs.
        async with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=3000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=[{**t, "eager_input_streaming": True} for t in tools],
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            async for event in stream:
                if event.type == "text":
                    yield {"type": "text", "text": event.text}
            final = await stream.get_final_message()
        if final.stop_reason == "refusal":
            raise LLMRefusal("Claude declined to answer.")
        content = []
        for block in final.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        yield {"type": "message", "content": content, "stop_reason": final.stop_reason}


TRANSCRIPT_LINE = re.compile(r"^\[(\d+(?::\d{2}){1,2})\] (.+)$", re.M)


def _seconds(stamp: str) -> float:
    total = 0.0
    for part in stamp.split(":"):
        total = total * 60 + float(part)
    return total


class ScriptedLLM:
    """Deterministic stand-in for Claude, built from the transcript text in the prompt or tool results."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay

    async def _pause(self, factor: float = 1.0) -> None:
        if self.delay:
            await asyncio.sleep(self.delay * factor)

    @staticmethod
    def _sentences(lines: list[tuple[float, str]]) -> list[tuple[float, str]]:
        """Rebuild sentences across caption lines; each starts at the line where its first word is."""
        out: list[tuple[float, str]] = []
        current, began = "", 0.0
        for t, text in lines:
            for piece in re.split(r"(?<=[.!?])\s+", text):
                if not current:
                    began = t
                current = f"{current} {piece}".strip()
                if re.search(r"[.!?]$", piece):
                    out.append((began, current))
                    current = ""
        if current:
            out.append((began, current))
        return out

    async def structured(self, system: str, prompt: str, schema: type[T], effort: str) -> T:
        await self._pause(30)
        lines = [(_seconds(t), text) for t, text in TRANSCRIPT_LINE.findall(prompt)]
        if schema is not Summary or not lines:
            raise ValueError("ScriptedLLM only writes summaries from a timestamped transcript.")
        said = self._sentences(lines)
        title = re.search(r"^Video: (.+)$", prompt, re.M)
        end = lines[-1][0] or 1

        def headline(text: str, words: int = 5) -> str:
            return " ".join(re.sub(r"[,.;:!?]", "", text).split()[:words]).capitalize()

        # Chapters at the sentence nearest each sixth of the video.
        marks = sorted({min(range(len(said)), key=lambda i: abs(said[i][0] - end * k / 6)) for k in range(6)})
        chapters = [{"start": said[i][0], "title": headline(said[i][1]), "summary": said[i][1]} for i in marks]
        chapters[0]["start"] = 0.0
        # Moments: the longest sentence in alternate chapters, quoted from its first words.
        moments = []
        for a, b in list(zip(marks, [*marks[1:], len(said)], strict=True))[::2][:4]:
            t, text = max(said[a:b], key=lambda x: len(x[1]))
            moments.append(
                {
                    "start": t,
                    "title": headline(text, 6),
                    "why": "A key point in the talk.",
                    "quote": " ".join(text.split()[:10]),
                }
            )
        filler = {"actually", "because", "people", "something", "really", "things", "there", "rather"}
        words = [w for _, text in lines for w in tokens(text) if len(w) > 5 and w not in filler]
        topics = [w for w, _ in sorted(((w, words.count(w)) for w in set(words)), key=lambda x: (-x[1], x[0]))[:5]]
        return schema.model_validate(
            {
                "title": title.group(1).strip() if title else "Untitled video",
                "tldr": " ".join(text for _, text in said[:2]),
                "vibe": {
                    "tone": "calm explainer",
                    "energy": "medium",
                    "audience": "engineers and leads",
                    "format": "talk",
                },
                "chapters": chapters,
                "moments": moments,
                "topics": topics,
                "questions": ["What is the main idea?", "What happens in the first weeks?", "Why does trust matter?"],
            }
        )

    async def turn(self, system: str, messages: list[dict], tools: list[dict], effort: str) -> AsyncIterator[dict]:
        await self._pause(8)
        last = messages[-1]["content"]
        if isinstance(last, str):
            call = {
                "type": "tool_use",
                "id": f"toolu_{len(messages)}",
                "name": "search_transcript",
                "input": {"query": last},
            }
            yield {"type": "message", "content": [call], "stop_reason": "tool_use"}
            return
        question = next(
            m["content"] for m in reversed(messages) if m["role"] == "user" and isinstance(m["content"], str)
        )
        asked = set(tokens(question))
        results = "\n".join(r["content"] for r in last if r.get("type") == "tool_result")
        hits = [(_seconds(t), text) for t, text in TRANSCRIPT_LINE.findall(results)]
        bags = [set(tokens(text)) for _, text in hits]
        idf = {w: math.log((len(bags) + 1) / (1 + sum(w in b for b in bags))) + 1 for w in asked}
        scored = sorted(
            ((sum(idf[w] for w in asked & bag), hit) for bag, hit in zip(bags, hits, strict=True)), key=lambda x: -x[0]
        )
        # Relevant means at least two content words in common, not one lucky match.
        if not scored or scored[0][0] < 2.5 or len(asked & set(tokens(scored[0][1][1]))) < 2:
            answer = "I couldn't find that in the video. Try asking about one of the chapters."
        else:
            start, text = scored[0][1]
            stamp = f"{int(start // 60)}:{int(start % 60):02d}"
            answer = f"The speaker covers this at [{stamp}]: {text.strip().rstrip(',.')}."
        for word in answer.split(" "):
            await self._pause()
            yield {"type": "text", "text": word + " "}
        yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}


def make_llm(settings: Settings) -> LLM:
    if settings.llm == "scripted":
        return ScriptedLLM(delay=settings.scripted_delay)
    if settings.llm == "anthropic":
        return AnthropicLLM(settings)
    raise ValueError(f"Unknown LLM backend: {settings.llm}")
