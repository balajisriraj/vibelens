from conftest import ready

from vibelens.service import Service


class Liar:
    """Answers immediately with a timestamp it never looked up."""

    async def structured(self, *a, **k):
        raise AssertionError

    async def turn(self, system, messages, tools, effort):
        yield {"type": "text", "text": "It's at [1:30]."}
        yield {"type": "message", "content": [{"type": "text", "text": "It's at [1:30]."}], "stop_reason": "end_turn"}


class BadTool:
    """Calls a tool with invalid input, then answers."""

    def __init__(self):
        self.calls = 0

    async def turn(self, system, messages, tools, effort):
        self.calls += 1
        if self.calls == 1:
            use = {
                "type": "tool_use",
                "id": "t1",
                "name": "read_transcript",
                "input": {"start": "soon", "end": "later"},
            }
            yield {"type": "message", "content": [use], "stop_reason": "tool_use"}
        else:
            self.result = messages[-1]["content"][0]
            yield {"type": "message", "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}


async def test_answers_cite_what_was_read(service):
    video_id = service.add_sample()
    await ready(service, video_id)
    events = [e async for e in service.ask(video_id, "What should you do in the first two weeks?", [])]
    tools = [e for e in events if e["type"] == "tool"]
    assert tools and tools[0]["name"] == "search_transcript"
    done = events[-1]
    assert done["citations"] and all(c["verified"] for c in done["citations"])
    assert abs(done["citations"][0]["t"] - 32) <= 6


async def test_unread_timestamps_are_flagged(service):
    video_id = service.add_sample()
    await ready(service, video_id)
    liar = Service(service.settings, Liar(), service.store, service.embedder)
    done = [e async for e in liar.ask(video_id, "anything", [])][-1]
    assert done["citations"] == [{"stamp": "1:30", "t": 90.0, "verified": False}]


async def test_invalid_tool_input_returns_an_error_result(service):
    video_id = service.add_sample()
    await ready(service, video_id)
    model = BadTool()
    agent = Service(service.settings, model, service.store, service.embedder)
    events = [e async for e in agent.ask(video_id, "q", [])]
    assert events[0] == {
        "type": "tool",
        "name": "read_transcript",
        "input": {"start": "soon", "end": "later"},
        "result": "invalid input",
    }
    assert model.result["is_error"] is True
