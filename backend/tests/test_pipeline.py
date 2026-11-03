from conftest import ready

from vibelens.llm import Chapter, Moment, Summary, Vibe
from vibelens.pipeline import verify
from vibelens.transcript import Cue


async def test_sample_runs_every_stage(service):
    video_id = service.add_sample()
    events = await ready(service, video_id)
    steps = [(e["step"], e["status"]) for e in events if e["type"] == "step"]
    assert steps == [(s, st) for s in ("transcript", "index", "summary") for st in ("running", "done")]
    video = service.store.get(video_id)
    assert video["status"] == "ready" and video["duration"] > 90
    assert len(video["segments"]) >= 5
    assert all(m["verified"] for m in video["summary"]["moments"])


def test_verify_snaps_chapters_and_pins_quotes():
    cues = [Cue(0, 10, "Welcome to the talk."), Cue(10, 20, "Ranks are always comparable here."), Cue(20, 30, "Done.")]
    summary = Summary(
        title="t",
        tldr="t",
        vibe=Vibe(tone="calm", energy="low", audience="all", format="talk"),
        chapters=[
            Chapter(start=11, title="b", summary=""),
            Chapter(start=3, title="a", summary=""),
            Chapter(start=12, title="dup", summary=""),
        ],
        moments=[
            Moment(start=25, title="m", why="", quote="ranks are always comparable"),
            Moment(start=5, title="x", why="", quote="a sentence nobody said at all"),
        ],
        topics=[],
        questions=[],
    )
    out = verify(summary, cues, 30)
    assert [(c["title"], c["start"], c["end"]) for c in out["chapters"]] == [("a", 0.0, 10), ("b", 10, 30)]
    assert out["moments"][0]["start"] == 10 and out["moments"][0]["verified"]
    assert not out["moments"][1]["verified"]
