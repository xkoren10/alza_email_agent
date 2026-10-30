"""Text embeddings through the Gemini API (no local model, so no torch in the container).

Shared by the running service (query side) and `scripts/create_indices.py` (document side);
both must use the same model and dimensions.
"""
import numpy as np
from google import genai
from google.genai import types

DOCUMENT = "RETRIEVAL_DOCUMENT"
QUERY = "RETRIEVAL_QUERY"
BATCH_SIZE = 50  # the API accepts at most 100 texts per request


def embed_texts(
    client: genai.Client, model: str, dimensions: int, texts: list[str], task_type: str
) -> np.ndarray:
    """Returns one L2-normalised vector per text, shape (len(texts), dimensions)."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        response = client.models.embed_content(
            model=model,
            contents=texts[start : start + BATCH_SIZE],
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=dimensions),
        )
        vectors.extend(item.values for item in response.embeddings)

    matrix = np.array(vectors, dtype="float32")
    # Normalising makes a dot product equal to cosine similarity (and is required for truncated dimensions).
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
