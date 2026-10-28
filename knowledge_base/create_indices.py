import os
import json
import pickle
import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "knowledge_chunks.json"
INDEX_DIR = "vector_index"
os.makedirs(INDEX_DIR, exist_ok=True)

def build_and_save_indices():
    if not os.path.exists(CHUNKS_FILE):
        print(f"❌ Error: {CHUNKS_FILE} not found. Run the preprocessor first.")
        return

    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    # 1. Initialize lightweight local embedding model
    print("Embedding chunks using sentence-transformers (all-MiniLM-L6-v2)...")
    encoder = SentenceTransformer('all-MiniLM-L6-v2')
    texts = [c["content"] for c in chunks]
    embeddings = encoder.encode(texts, show_progress_bar=True)

    # 2. Build FAISS Dense Index
    dimension = embeddings.shape[1]
    faiss_index = faiss.IndexFlatL2(dimension)
    faiss_index.add(np.array(embeddings).astype('float32'))

    # Save FAISS index
    faiss.write_index(faiss_index, os.path.join(INDEX_DIR, "faiss.index"))

    # 3. Build BM25 Sparse Index
    tokenized_corpus = [doc.lower().split(" ") for doc in texts]
    bm25 = BM25Okapi(tokenized_corpus)

    # Save BM25 and chunks metadata
    with open(os.path.join(INDEX_DIR, "bm25.pkl"), "wb") as f:
        pickle.dump(bm25, f)
        
    with open(os.path.join(INDEX_DIR, "chunks.pkl"), "wb") as f:
        pickle.dump(chunks, f)

    print("Success! FAISS vector index, BM25 keyword index, and chunks saved to 'vector_index/'.")

if __name__ == "__main__":
    build_and_save_indices()