import time
from typing import Optional
from app.config.config import settings

_model = None
MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024


def _get_model():
    global _model
    if _model is None:
        print(f"Loading multilingual embedding model '{MODEL_NAME}' into memory...")
        t0 = time.time()
        from sentence_transformers import SentenceTransformer

        token = settings.huggingface_token if settings.huggingface_token else None
        _model = SentenceTransformer(MODEL_NAME, token=token)
        print(f"Embedding model '{MODEL_NAME}' loaded in {time.time() - t0:.2f}s!")
    return _model


def get_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM
    model = _get_model()
    vec = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vec.tolist()


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    clean_texts = [t if t and t.strip() else " " for t in texts]
    vecs = model.encode(clean_texts, convert_to_numpy=True, normalize_embeddings=True)
    return vecs.tolist()
