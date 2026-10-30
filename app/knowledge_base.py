"""Hybrid (semantic + keyword) search over the Pulsar-1 documentation.

The index files are built offline by `scripts/create_indices.py` and loaded once at start-up:
    embeddings.npy  one normalised Gemini embedding per chunk
    bm25.pkl        keyword index
    chunks.pkl      the chunk texts and their source files
The knowledge base is small (dozens of chunks), so a numpy dot product is all the vector search we need.
"""
import logging
import pickle
from pathlib import Path
from typing import Callable

import numpy as np

from app.models import Evidence

log = logging.getLogger(__name__)

SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4


class KnowledgeBase:
    def __init__(self, index_dir: Path, embed_query: Callable[[str], np.ndarray], dimensions: int):
        """`embed_query` turns a query string into a normalised vector (provided by the agent's Gemini client)."""
        self._embed_query = embed_query
        self._embeddings: np.ndarray = np.load(index_dir / "embeddings.npy")
        # These pickles are produced by our own build script; never load pickles from untrusted sources.
        with open(index_dir / "bm25.pkl", "rb") as f:
            self._bm25 = pickle.load(f)
        with open(index_dir / "chunks.pkl", "rb") as f:
            self._chunks: list[dict] = pickle.load(f)

        if self._embeddings.shape != (len(self._chunks), dimensions):
            raise ValueError(
                f"Index has embeddings of shape {self._embeddings.shape} but expected "
                f"({len(self._chunks)}, {dimensions}). Rebuild it with scripts/create_indices.py "
                "using the same EMBEDDING_MODEL and EMBEDDING_DIMENSIONS."
            )
        log.info("Knowledge base loaded: %d chunks", len(self._chunks))

    def __len__(self) -> int:
        return len(self._chunks)

    def search(self, query: str, top_k: int = 3) -> list[Evidence]:
        """Returns the `top_k` most relevant chunks, best first."""
        if not self._chunks or not query.strip():
            return []

        candidates = top_k * 2  # each method nominates a few extra, then the combined score decides
        scores = self._semantic_scores(query, candidates)
        for idx, score in self._keyword_scores(query, candidates).items():
            scores[idx] = scores.get(idx, 0.0) + score

        best = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            Evidence(source=self._chunks[idx]["source"], content=self._chunks[idx]["content"], score=score)
            for idx, score in best
        ]

    def _semantic_scores(self, query: str, candidates: int) -> dict[int, float]:
        """Cosine similarity of the best chunks (embeddings are normalised, so a dot product), weighted."""
        similarity = self._embeddings @ self._embed_query(query)
        top = np.argsort(similarity)[::-1][:candidates]
        return {int(idx): SEMANTIC_WEIGHT * max(float(similarity[idx]), 0.0) for idx in top}

    def _keyword_scores(self, query: str, candidates: int) -> dict[int, float]:
        """BM25 scores of the best chunks, normalised by the top hit and weighted."""
        raw = self._bm25.get_scores(query.lower().split(" "))
        best = max(raw) if len(raw) and max(raw) > 0 else 1.0
        top = np.argsort(raw)[::-1][:candidates]
        return {int(idx): KEYWORD_WEIGHT * float(raw[idx]) / best for idx in top}
