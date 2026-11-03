import json

import pytest
from fastapi.testclient import TestClient

from vibelens.api import create_app


@pytest.fixture
def client(settings, service):
    with TestClient(create_app(settings, service)) as c:
        yield c


def sse(body: str) -> list[dict]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


def test_sample_end_to_end(client):
    video_id = client.post("/api/videos/sample").json()["id"]
    assert sse(client.get(f"/api/videos/{video_id}/events").text)[-1]["type"] == "done"
    video = client.get(f"/api/videos/{video_id}").json()
    assert video["summary"]["chapters"] and video["cues"]
    assert client.get("/api/videos").json()[0]["id"] == video_id

    media = client.get(f"/api/videos/{video_id}/media", headers={"Range": "bytes=0-99"})
    assert media.status_code == 206 and len(media.content) == 100
    assert client.get(f"/api/videos/{video_id}/transcript.vtt").text.startswith("WEBVTT")

    events = sse(
        client.post(f"/api/videos/{video_id}/ask", json={"question": "How is it different from consulting?"}).text
    )
    assert {"tool", "text", "done"} <= {e["type"] for e in events}
    assert client.delete(f"/api/videos/{video_id}").json() == {"deleted": True}


def test_caption_upload_and_validation(client):
    vtt = b"WEBVTT\n\n00:00:00.000 --> 00:00:04.000\nRanking is the quiet half of search.\n\n00:00:04.000 --> 00:00:09.000\nFusion merges two ranked lists by rank alone.\n"
    video_id = client.post("/api/videos/upload", files={"file": ("talk.vtt", vtt, "text/vtt")}).json()["id"]
    assert sse(client.get(f"/api/videos/{video_id}/events").text)[-1]["type"] == "done"
    assert client.get(f"/api/videos/{video_id}/media").status_code == 404  # captions have no media

    assert (
        client.post("/api/videos/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code
        == 422
    )
    assert client.post("/api/videos/youtube", json={"url": "https://vimeo.com/1"}).status_code == 422
    assert client.get("/api/videos/nope").status_code == 404
