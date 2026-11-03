import itertools

import pytest

from vibelens.sources import SourceError, youtube_id
from vibelens.text import find_quote
from vibelens.transcript import Cue, parse_captions, parse_ts, segment, target_length, to_vtt, ts

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.500
<v Speaker>Hello and welcome</v>

00:00:03.500 --> 00:00:05.000
Hello and welcome

00:00:05.000 --> 00:00:08.000
to the show about ranking.
"""

SRT = """1
00:00:01,000 --> 00:00:02,000
First line

2
00:01:02,500 --> 00:01:04,000
Second line
"""


def test_parse_vtt_strips_tags_and_merges_rolling_duplicates():
    cues = parse_captions(VTT)
    assert [c.text for c in cues] == ["Hello and welcome", "to the show about ranking."]
    assert cues[0].end == 5.0


def test_parse_srt_and_round_trip():
    cues = parse_captions(SRT)
    assert cues[1].start == 62.5
    assert parse_captions(to_vtt(cues)) == cues


def test_timestamps():
    assert ts(0) == "0:00" and ts(185.4) == "3:05" and ts(3723) == "1:02:03"
    assert parse_ts("3:05") == 185 and parse_ts("01:02:03.500") == 3723.5


def test_segments_cover_everything_in_order():
    cues = [Cue(i * 5.0, i * 5.0 + 5, f"Sentence number {i}.") for i in range(30)]
    segs = segment(cues, target_length(150))
    assert segs[0].start == 0 and segs[-1].end == 150
    assert all(a.end <= b.start for a, b in itertools.pairwise(segs))
    assert sum(len(s.text.split()) for s in segs) == sum(len(c.text.split()) for c in cues)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    ],
)
def test_youtube_links(url):
    assert youtube_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", ["https://vimeo.com/123", "https://evil.example/watch?v=dQw4w9WgXcQ", "not a url"])
def test_rejects_other_links(url):
    with pytest.raises(SourceError):
        youtube_id(url)


def test_find_quote_across_cue_boundaries():
    cues = [
        Cue(0, 4, "the last mile is usually"),
        Cue(4, 8, "longer than the rest of the road."),
        Cue(8, 12, "Next idea."),
    ]
    assert find_quote("usually longer than the rest", cues) == 0
    assert find_quote("longer than the rest of the road", cues) == 4
    assert find_quote("nothing like this was said here", cues) is None
