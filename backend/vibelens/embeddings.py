"""Text embeddings.

``HashEmbedder`` is deterministic and dependency-free (signed feature hashing over words and
word pairs), which keeps tests and the default local setup fast. ``FastEmbedder`` runs a real
sentence-embedding model (bge-small) locally through ONNX.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections import Counter
from typing import Protocol

from .config import Settings

TOKEN = re.compile(r"[a-z0-9]+")
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "me",
        "my",
        "do",
        "does",
        "did",
        "how",
        "can",
        "about",
        "tell",
        "any",
        "there",
        "also",
        "more",
        "some",
        "been",
        "were",
        "they",
        "them",
        "their",
    ]
)


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


class HashEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        return value % self.dim, 1.0 if value >> 63 else -1.0

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            words = tokens(text)
            # Light stemming so "agents" and "agent" share a bucket.
            words = [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words]
            features = [*words, *(f"{a}_{b}" for a, b in itertools.pairwise(words))]
            # Sublinear term frequency: a word repeated ten times shouldn't outweigh ten distinct words.
            for feature, count in Counter(features).items():
                index, sign = self._bucket(feature)
                vec[index] += sign * (1 + math.log(count))
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedder:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model)
        self.dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


def make_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "hash":
        return HashEmbedder(settings.embedding_dim)
    if settings.embedder == "fastembed":
        return FastEmbedder()
    raise ValueError(f"Unknown embedder: {settings.embedder}")


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
