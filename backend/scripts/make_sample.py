"""Builds samples/forward-deployment.mp4: a short original talk for demos and tests.

The script is adapted from Balaji's essay "What Does a Forward Deployment Engineer Do?". The voice is
macOS text-to-speech and the slides are drawn with Pillow, so the whole asset is generated here.
Requires macOS (`say`) and the dev dependencies.  Run: uv run python scripts/make_sample.py
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "samples" / "forward-deployment.mp4"
VOICE = "Daniel"
W, H, FPS = 1280, 720, 2

CHAPTERS = [
    (
        "Working is not adopted",
        "Here is the short version. A forward deployment engineer takes something that works, and makes it work "
        "there, inside a specific business, with its own data, its own processes and its own people. "
        "Working software and adopted software are not the same thing, and this job exists in the gap between them.",
    ),
    (
        "Not support, not consulting",
        "It is not support, and it is not consulting. Support fixes what is broken. Consulting advises and leaves. "
        "Forward deployment builds the last mile, and the last mile is usually longer than the rest of the road.",
    ),
    (
        "Weeks one to two",
        "In the first two weeks, you learn the real process, not the documented one. Sit with the people doing the "
        "work and watch what they actually do, including the spreadsheet they keep on the side because the "
        "official system is too slow.",
    ),
    (
        "Weeks three to six",
        "From week three to week six, you make it fit. Data mapping, edge cases, and the integration nobody scoped. "
        "This is where most of the engineering happens, and almost none of it is glamorous.",
    ),
    (
        "Earn the handover",
        "From week six onward, you earn the handover. Train the people who will own it. Write down what breaks and "
        "how to tell. A deployment that depends on you is not finished.",
    ),
    (
        "Trust before code",
        "Most of the difficulty is not technical. You are asking a busy team to change how they work, on the "
        "strength of a promise from someone they met last month. That is a trust problem before it is an "
        "engineering problem. The best forward deployment engineers are unusually good listeners.",
    ),
    (
        "Why I like it",
        "Why do I like the job? Because you find out whether the thing was actually good. A model that scores well "
        "and is never used has taught you nothing. Real people, doing real work, will tell you the truth.",
    ),
]


def font(size: int, bold: bool = False):
    for name in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def slide(index: int, title: str) -> np.ndarray:
    img = Image.new("RGB", (W, H), "#f7f7f2")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill="#2f3cff")
    d.rectangle([70, 120, 70 + 120, 120 + 120], fill="#e4ff3a", outline="#111", width=6)
    d.text((130, 180), str(index + 1), font=font(70, True), fill="#111", anchor="mm")
    d.text((70, 300), title, font=font(78, True), fill="#111")
    d.text((70, 420), "What does a forward deployment engineer do?", font=font(34), fill="#555")
    d.text((70, H - 80), "VibeLens sample talk  ·  Balaji Sri Raj  ·  synthetic voice", font=font(24), fill="#777")
    return np.asarray(img)


def build() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        for i, (_, text) in enumerate(CHAPTERS):
            path = Path(tmp) / f"c{i}.aiff"
            subprocess.run(["say", "-v", VOICE, "-r", "175", "-o", str(path), text], check=True)
            clips.append(path)

        OUT.parent.mkdir(parents=True, exist_ok=True)
        out = av.open(str(OUT), "w")
        vstream = out.add_stream("libx264", rate=FPS)
        vstream.width, vstream.height, vstream.pix_fmt = W, H, "yuv420p"
        vstream.options = {"crf": "30", "preset": "veryslow", "tune": "stillimage"}
        astream = out.add_stream("aac", rate=22050)
        astream.layout = "mono"
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=22050)

        frame_no, a_pts = 0, 0
        for i, (title, _) in enumerate(CHAPTERS):
            seconds = 0.0
            with av.open(str(clips[i])) as clip:
                for frame in clip.decode(audio=0):
                    for f in resampler.resample(frame):
                        f.pts = a_pts
                        a_pts += f.samples
                        seconds += f.samples / 22050
                        for packet in astream.encode(f):
                            out.mux(packet)
            # Half a second of silence between chapters.
            gap = np.zeros((1, 11025), dtype=np.float32)
            silence = av.AudioFrame.from_ndarray(gap, format="fltp", layout="mono")
            silence.sample_rate, silence.pts = 22050, a_pts
            a_pts += 11025
            for packet in astream.encode(silence):
                out.mux(packet)
            seconds += 0.5
            image = slide(i, title)
            for _ in range(round(seconds * FPS)):
                vf = av.VideoFrame.from_ndarray(image, format="rgb24")
                vf.pts = frame_no
                frame_no += 1
                for packet in vstream.encode(vf):
                    out.mux(packet)
        for stream in (vstream, astream):
            for packet in stream.encode():
                out.mux(packet)
        out.close()
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {frame_no / FPS:.0f}s)")


if __name__ == "__main__":
    build()
