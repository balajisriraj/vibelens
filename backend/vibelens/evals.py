"""Evaluation on the bundled sample talk: summary grounding, plus chat citation accuracy to the second."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import ROOT, get_settings
from .service import Service
from .transcript import parse_ts

CASES = ROOT / "evals" / "questions.yaml"


async def run(verbose: bool = False) -> bool:
    service = Service.from_settings(get_settings())
    video_id = service.add_sample()
    async for event in service.events(video_id):
        if event["type"] == "error":
            print(event["message"])
            return False
    video = service.store.get(video_id)
    summary = video["summary"]

    chapters_ok = summary["chapters"][0]["start"] == 0 and all(
        a["start"] < b["start"] for a, b in zip(summary["chapters"], summary["chapters"][1:], strict=False)
    )
    pinned = sum(m["verified"] for m in summary["moments"])
    print(f"Summary of: {summary['title']}")
    print(f"  chapters      {len(summary['chapters'])} in order: {'yes' if chapters_ok else 'NO'}")
    print(f"  moments       {pinned}/{len(summary['moments'])} pinned to their quote")

    cases = yaml.safe_load(Path(CASES).read_text(encoding="utf-8"))
    passed = cited = verified = 0
    errors: list[float] = []
    for case in cases:
        events = [e async for e in service.ask(video_id, case["question"], [])]
        done = events[-1]
        cites = done["citations"]
        cited += len(cites)
        verified += sum(c["verified"] for c in cites)
        if case.get("uncited"):
            good = not cites
            detail = "no citations" if good else f"cited {[c['stamp'] for c in cites]}"
        else:
            target, tol = parse_ts(case["at"]), case.get("tolerance", 6)
            off = min((abs(c["t"] - target) for c in cites), default=None)
            good = off is not None and off <= tol and all(c["verified"] for c in cites)
            if off is not None:
                errors.append(off)
            detail = f"cited {[c['stamp'] for c in cites]} (expected {case['at']}, off by {off if off is not None else '-'}s)"
        passed += good
        if verbose or not good:
            print(f"  {'PASS' if good else 'FAIL'}  {case['id']}: {detail}")
    print(f"  questions     {passed}/{len(cases)}")
    print(f"  citations     {verified}/{cited} verified against what the agent read")
    if errors:
        print(f"  timing        mean {sum(errors) / len(errors):.1f}s off, worst {max(errors):.1f}s")
    service.store.delete(video_id)
    return chapters_ok and passed == len(cases) and verified == cited and pinned == len(summary["moments"])
