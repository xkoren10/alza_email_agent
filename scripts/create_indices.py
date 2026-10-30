"""Step 2 of the knowledge base build: embeds the chunks and writes the search indices.

Run from anywhere:  python scripts/create_indices.py
Needs GEMINI_API_KEY (or Vertex settings) in .env. Uses the same EMBEDDING_MODEL / EMBEDDING_DIMENSIONS
as the service; if you change either, rebuild the index.
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from google import genai
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.embeddings import DOCUMENT, embed_texts  # noqa: E402

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
CHUNKS_FILE = KNOWLEDGE_DIR / "knowledge_chunks.json"


def build_and_save_indices() -> None:
    settings = Settings.from_env()
    index_dir = settings.index_dir
    index_dir.mkdir(parents=True, exist_ok=True)

    if not CHUNKS_FILE.exists():
        sys.exit(f"{CHUNKS_FILE} not found. Run scripts/preprocess_files.py first.")
    chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
    texts = [chunk["content"] for chunk in chunks]
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    # 1. Semantic index: one normalised Gemini embedding per chunk
    print(f"Embedding chunks with {settings.embedding_model} ({settings.embedding_dimensions} dimensions)...")
    if settings.gemini_use_vertex:
        client = genai.Client(vertexai=True, project=settings.gcp_project, location=settings.gcp_location)
    else:
        client = genai.Client(api_key=settings.gemini_api_key)
    embeddings = embed_texts(client, settings.embedding_model, settings.embedding_dimensions, texts, DOCUMENT)
    np.save(index_dir / "embeddings.npy", embeddings)

    # 2. Keyword index
    bm25 = BM25Okapi([text.lower().split(" ") for text in texts])
    with open(index_dir / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)

    # 3. The chunks themselves
    with open(index_dir / "chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)

    print(f"Success! embeddings.npy, bm25.pkl and chunks.pkl saved to '{index_dir}'.")


if __name__ == "__main__":
    build_and_save_indices()
