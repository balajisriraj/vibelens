"""HTTP API. Processing progress and chat answers stream as Server-Sent Events."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .config import Settings, get_settings
from .llm import LLMRefusal
from .service import Service
from .sources import SourceError
from .transcript import Cue, to_vtt

log = logging.getLogger("vibelens")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


class LinkBody(BaseModel):
    url: str = Field(max_length=300)


def _sse(events):
    async def gen():
        async for event in events:
            yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(gen())


def create_app(settings: Settings | None = None, service: Service | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service or Service.from_settings(settings)
        yield

    app = FastAPI(title="VibeLens", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    def svc(request: Request) -> Service:
        return request.app.state.service

    def video_or_404(request: Request, video_id: str) -> dict:
        video = svc(request).store.get(video_id)
        if not video:
            raise HTTPException(404, "No such video.")
        return video

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "llm": settings.llm,
            "model": settings.model if settings.llm == "anthropic" else "scripted",
        }

    @app.get("/api/videos")
    async def videos(request: Request) -> list[dict]:
        return svc(request).store.list()

    @app.post("/api/videos/youtube", status_code=201)
    async def youtube(body: LinkBody, request: Request) -> dict:
        try:
            return {"id": svc(request).add_youtube(body.url)}
        except SourceError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/videos/upload", status_code=201)
    async def upload(request: Request, file: UploadFile = File(...)) -> dict:
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        try:
            return {"id": svc(request).add_file(file.filename or "upload.mp4", data)}
        except SourceError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/videos/sample", status_code=201)
    async def sample(request: Request) -> dict:
        return {"id": svc(request).add_sample()}

    @app.get("/api/videos/{video_id}")
    async def video(video_id: str, request: Request) -> dict:
        return video_or_404(request, video_id)

    @app.delete("/api/videos/{video_id}")
    async def delete(video_id: str, request: Request) -> dict:
        return {"deleted": svc(request).store.delete(video_id)}

    @app.get("/api/videos/{video_id}/media")
    async def media(video_id: str, request: Request) -> FileResponse:
        path = svc(request).media(video_id)
        if not path:
            raise HTTPException(404, "No media for this video.")
        return FileResponse(path)  # Starlette answers Range requests, so the player can seek

    @app.get("/api/videos/{video_id}/transcript.vtt")
    async def transcript(video_id: str, request: Request) -> PlainTextResponse:
        video = video_or_404(request, video_id)
        return PlainTextResponse(to_vtt([Cue(**c) for c in video["cues"]]), media_type="text/vtt")

    @app.get("/api/videos/{video_id}/events")
    async def events(video_id: str, request: Request) -> EventSourceResponse:
        video_or_404(request, video_id)
        return _sse(svc(request).events(video_id))

    @app.post("/api/videos/{video_id}/ask")
    async def ask(video_id: str, body: AskBody, request: Request) -> EventSourceResponse:
        video = video_or_404(request, video_id)
        if video["status"] != "ready":
            raise HTTPException(409, "This video is still being processed.")

        async def stream():
            try:
                async for event in svc(request).ask(video_id, body.question, [t.model_dump() for t in body.history]):
                    yield event
            except LLMRefusal:
                yield {"type": "error", "message": "I can't help with that one."}
            except Exception:
                log.exception("chat failed")
                yield {"type": "error", "message": "Something went wrong. Try again?"}

        return _sse(stream())

    return app
