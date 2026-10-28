import os
import pickle
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from google import genai
from extra.color_print import printGreen, printRed
import warnings
# Suppress Hugging Face clean_up_tokenization_spaces future warning
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers.*")


INDEX_DIR = "knowledge_base/vector_index"

class EmailRAGRouter:
    def __init__(self, client: genai.Client):
        print("Initializing Email RAG Router & Hybrid Search Engine...", end='')
        self.client = client
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2', similarity_fn_name="cosine")
        
        # Load indices and preprocessed metadata chunks
        self.faiss_index = faiss.read_index(os.path.join(INDEX_DIR, "faiss.index"))
        with open(os.path.join(INDEX_DIR, "bm25.pkl"), "rb") as f:
            self.bm25 = pickle.load(f)
        with open(os.path.join(INDEX_DIR, "chunks.pkl"), "rb") as f:
            self.chunks = pickle.load(f)
            
        chunks_count = len(self.chunks)
        printGreen(f"Loaded {chunks_count} knowledge chunks into memory.")

    def should_search_knowledge_base(self, email_body: str) -> bool:
        """
        Determines whether the email body requires looking up technical manuals, 
        error codes, or parts, avoiding unnecessary database searches for casual chat.
        """
        # Fast keyword heuristic check for error codes or part numbers
        upper_body = email_body.upper()
        if any(term in upper_body for term in ["ERR-", "PLS-", "SKU", "PRICE", "BATTERY", "SCRUBBER", "SHIELD", "NOZZLE"]):
            return True

        # Fallback to a fast LLM intent check if ambiguous
        prompt = (
            "Analyze this customer support email. Does this message require looking up "
            "technical manuals, error codes, part pricing, or spacecraft system specifications? "
            "Answer with ONLY 'YES' or 'NO'.\n\n"
            f"Email: {email_body}"
        )
        
        response = self.client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            contents=prompt
        )
        
        return "YES" in response.text.strip().upper()

    def search_chunks(self, query: str, top_k: int = 3) -> list[str]:
        """Performs hybrid retrieval combining FAISS (semantic) and BM25 (keyword)."""
        if not self.chunks:
            return []

        # 1. Dense Retrieval (FAISS)
        query_vector = self.encoder.encode([query]).astype('float32')
        distances, faiss_indices = self.faiss_index.search(query_vector, top_k * 2)
        
        faiss_scores = {}
        for rank, idx in enumerate(faiss_indices[0]):
            if idx < len(self.chunks):
                faiss_scores[idx] = 1.0 / (1.0 + float(distances[0][rank]))

        # 2. Sparse Retrieval (BM25)
        tokenized_query = query.lower().split(" ")
        bm25_scores_list = self.bm25.get_scores(tokenized_query)
        
        bm25_scores = {}
        top_bm25_indices = np.argsort(bm25_scores_list)[::-1][:top_k * 2]
        max_bm25 = max(bm25_scores_list) if len(bm25_scores_list) > 0 and max(bm25_scores_list) > 0 else 1.0
        
        for idx in top_bm25_indices:
            bm25_scores[idx] = float(bm25_scores_list[idx]) / max_bm25

        # 3. Reciprocal Rank Fusion (RRF) Combination
        combined_scores = {}
        all_indices = set(list(faiss_scores.keys()) + list(bm25_scores.keys()))
        
        for idx in all_indices:
            f_score = faiss_scores.get(idx, 0.0)
            b_score = bm25_scores.get(idx, 0.0)
            combined_scores[idx] = (0.6 * f_score) + (0.4 * b_score)

        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        
        retrieved_contexts = []
        for idx, score in sorted_results[:top_k]:
            chunk = self.chunks[idx]
            retrieved_contexts.append(f"[{chunk['source']} | Score: {score:.2f}]\n{chunk['content']}")
        print(f"Found {len(retrieved_contexts)} relevant knowledge chunks")
        return retrieved_contexts

    def process_incoming_email(self, email_subject: str, email_body: str) -> list[str]:
        """Core trigger pipeline: analyzes email intent and retrieves chunks if needed."""
        full_query = f"Subject: {email_subject}\n\nBody: {email_body}"
        
        if not self.should_search_knowledge_base(full_query):
            print("Email is conversational or non-technical. Skipping RAG retrieval.")
            return []
            
        print("Technical intent detected. Triggering hybrid chunk retrieval...")
        return self.search_chunks(full_query, top_k=3)