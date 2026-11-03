"""Command line: ``vibelens serve | watch <url-or-file> | ask <id> "question" | eval``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import get_settings


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("vibelens.api:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


def _watch(args: argparse.Namespace) -> None:
    from .service import Service

    async def run() -> None:
        service = Service.from_settings(get_settings())
        if not args.source:
            video_id = service.add_sample()
        elif Path(args.source).exists():
            video_id = service.add_file(Path(args.source).name, Path(args.source).read_bytes())
        else:
            video_id = service.add_youtube(args.source)
        async for e in service.events(video_id):
            if e["type"] == "step" and e["status"] == "done":
                print(f"  ✓ {e['step']:<10} {e['detail']}  ({e['ms']} ms)")
            elif e["type"] == "done":
                s = e["summary"]
                print(f"\n{s['title']}\n{s['tldr']}\n")
                for c in s["chapters"]:
                    print(f"  {int(c['start'] // 60)}:{int(c['start'] % 60):02d}  {c['title']}")
                print(f"\nVideo id {video_id}")
            elif e["type"] == "error":
                print(e["message"], file=sys.stderr)

    asyncio.run(run())


def _ask(args: argparse.Namespace) -> None:
    from .service import Service

    async def run() -> None:
        service = Service.from_settings(get_settings())
        async for e in service.ask(args.video, args.question, []):
            if e["type"] == "text":
                print(e["text"], end="", flush=True)
            elif e["type"] == "tool":
                print(f"\n  · {e['name']}({e['input']}) -> {e['result']}", file=sys.stderr)
            elif e["type"] == "done":
                marks = ", ".join(f"{c['stamp']}{'' if c['verified'] else ' (unverified)'}" for c in e["citations"])
                print(f"\n\ncited: {marks or 'nothing'}")

    asyncio.run(run())


def _eval(args: argparse.Namespace) -> None:
    from .evals import run

    sys.exit(0 if asyncio.run(run(verbose=args.verbose)) else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="vibelens", description="Watch less, know more.")
    commands = parser.add_subparsers(required=True)

    serve = commands.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(run=_serve)

    watch = commands.add_parser("watch", help="process a YouTube link or a local file (default: the sample)")
    watch.add_argument("source", nargs="?")
    watch.set_defaults(run=_watch)

    ask = commands.add_parser("ask", help="ask a processed video a question")
    ask.add_argument("video")
    ask.add_argument("question")
    ask.set_defaults(run=_ask)

    evals = commands.add_parser("eval", help="run the evaluation suite on the sample talk")
    evals.add_argument("--verbose", action="store_true")
    evals.set_defaults(run=_eval)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
