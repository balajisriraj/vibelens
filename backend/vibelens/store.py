"""SQLite storage: videos, their cues and segments, and a hybrid index (sqlite-vec + FTS5) per segment."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec

from .embeddings import tokens
from .transcript import Cue, Segment

RRF_K = 60


@dataclass
class Hit:
    segment: Segment
    score: float
    vector_rank: int | None
    keyword_rank: int | None


class Store:
    def __init__(self, data_dir: Path, dim: int) -> None:
        self.dir = Path(data_dir)
        (self.dir / "media").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "vibelens.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS videos (
                  id TEXT PRIMARY KEY, title TEXT, kind TEXT, ref TEXT, duration REAL, status TEXT,
                  error TEXT, cues TEXT, summary TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS segments (
                  rowid INTEGER PRIMARY KEY, video_id TEXT, idx INTEGER, start REAL, end REAL, text TEXT);
                CREATE INDEX IF NOT EXISTS segments_video ON segments(video_id, idx);
                CREATE VIRTUAL TABLE IF NOT EXISTS segments_vec USING vec0(
                  video_id TEXT partition key, embedding float[{dim}]);
                CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
                  text, content='segments', content_rowid='rowid', tokenize='porter unicode61');
                """
            )

    # ── videos ──
    def media_path(self, video_id: str, suffix: str = "") -> Path:
        return self.dir / "media" / f"{video_id}{suffix}"

    def create(self, title: str, kind: str, ref: str) -> str:
        video_id = uuid.uuid4().hex[:12]
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO videos(id, title, kind, ref, status) VALUES (?,?,?,?,?)",
                (video_id, title, kind, ref, "processing"),
            )
        return video_id

    def update(self, video_id: str, **fields) -> None:
        cols = {k: json.dumps(v) if k in ("cues", "summary") else v for k, v in fields.items()}
        with self.lock, self.db:
            self.db.execute(
                f"UPDATE videos SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", (*cols.values(), video_id)
            )

    def get(self, video_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            return None
        video = dict(row)
        video["cues"] = json.loads(video["cues"]) if video["cues"] else []
        video["summary"] = json.loads(video["summary"]) if video["summary"] else None
        video["segments"] = [
            dict(r)
            for r in self.db.execute(
                "SELECT idx AS id, start, end, text FROM segments WHERE video_id = ? ORDER BY idx", (video_id,)
            )
        ]
        return video

    def cues(self, video_id: str) -> list[Cue]:
        return [Cue(**c) for c in (self.get(video_id) or {}).get("cues", [])]

    def list(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, title, kind, ref, duration, status, created_at FROM videos ORDER BY created_at DESC, rowid DESC"
        )
        return [dict(r) for r in rows]

    def delete(self, video_id: str) -> bool:
        with self.lock, self.db:
            self._clear_segments(video_id)
            gone = self.db.execute("DELETE FROM videos WHERE id = ?", (video_id,)).rowcount
        for path in self.dir.joinpath("media").glob(f"{video_id}*"):
            path.unlink(missing_ok=True)
        return bool(gone)

    # ── index ──
    def _clear_segments(self, video_id: str) -> None:
        rows = self.db.execute("SELECT rowid, text FROM segments WHERE video_id = ?", (video_id,)).fetchall()
        for r in rows:
            self.db.execute("INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', ?, ?)", (r[0], r[1]))
            self.db.execute("DELETE FROM segments_vec WHERE rowid = ?", (r[0],))
        self.db.execute("DELETE FROM segments WHERE video_id = ?", (video_id,))

    def index(self, video_id: str, segments: list[Segment], vectors: list[list[float]]) -> None:
        with self.lock, self.db:
            self._clear_segments(video_id)
            for s, vec in zip(segments, vectors, strict=True):
                rowid = self.db.execute(
                    "INSERT INTO segments(video_id, idx, start, end, text) VALUES (?,?,?,?,?)",
                    (video_id, s.id, s.start, s.end, s.text),
                ).lastrowid
                self.db.execute(
                    "INSERT INTO segments_vec(rowid, video_id, embedding) VALUES (?,?,?)",
                    (rowid, video_id, sqlite_vec.serialize_float32(vec)),
                )
                self.db.execute("INSERT INTO segments_fts(rowid, text) VALUES (?,?)", (rowid, s.text))

    def search(self, video_id: str, query: str, vec: list[float], k: int = 4) -> list[Hit]:
        """Hybrid search within one video: vector and BM25 rankings merged with reciprocal rank fusion."""
        pool = max(k * 4, 16)
        vec_ids = [
            r[0]
            for r in self.db.execute(
                "SELECT rowid FROM segments_vec WHERE embedding MATCH ? AND k = ? AND video_id = ? ORDER BY distance",
                (sqlite_vec.serialize_float32(vec), pool, video_id),
            )
        ]
        kw_ids: list[int] = []
        terms = tokens(query)
        if terms:
            kw_ids = [
                r[0]
                for r in self.db.execute(
                    "SELECT f.rowid FROM segments_fts f JOIN segments s ON s.rowid = f.rowid "
                    "WHERE segments_fts MATCH ? AND s.video_id = ? ORDER BY bm25(segments_fts) LIMIT ?",
                    (" OR ".join(f'"{t}"' for t in terms), video_id, pool),
                )
            ]
        scores: dict[int, list] = {}
        for rank, rid in enumerate(vec_ids, 1):
            scores.setdefault(rid, [0.0, None, None])
            scores[rid][0] += 1 / (RRF_K + rank)
            scores[rid][1] = rank
        for rank, rid in enumerate(kw_ids, 1):
            scores.setdefault(rid, [0.0, None, None])
            scores[rid][0] += 1 / (RRF_K + rank)
            scores[rid][2] = rank
        top = sorted(scores.items(), key=lambda x: -x[1][0])[:k]
        if not top:
            return []
        rows = {
            r["rowid"]: r
            for r in self.db.execute(
                f"SELECT rowid, idx, start, end, text FROM segments WHERE rowid IN ({','.join('?' * len(top))})",
                [rid for rid, _ in top],
            )
        }
        return [
            Hit(Segment(rows[rid]["idx"], rows[rid]["start"], rows[rid]["end"], rows[rid]["text"]), s, vr, kr)
            for rid, (s, vr, kr) in top
        ]
