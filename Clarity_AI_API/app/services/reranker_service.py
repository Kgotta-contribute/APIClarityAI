import math
from typing import Any
import os
import torch
from sentence_transformers import CrossEncoder

# BAAI/bge-reranker-v2-m3 provides state-of-the-art multilingual & cross-lingual token-level cross-attention reranking
MODEL_NAME = "BAAI/bge-reranker-v2-m3"

_reranker_model = None

def get_reranker() -> CrossEncoder:
    global _reranker_model
    if _reranker_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading CrossEncoder ({MODEL_NAME}) on {device}...")
        _reranker_model = CrossEncoder(MODEL_NAME, device=device)
        print(f"CrossEncoder ({MODEL_NAME}) loaded successfully.")
    return _reranker_model


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 10,
    w1: float = 0.50,
    w2: float = 0.30,
    w3: float = 0.20,
) -> list[dict[str, Any]]:
    """
    Reranks a list of candidate chunks against the user query using weighted fusion:
    Final Score = w1 * reranker_prob + w2 * dense_score + w3 * lexical_score
    Returns the top_k highest scoring chunks.
    """
    if not chunks:
        return []
    
    if len(chunks) <= 1:
        return chunks

    try:
        model = get_reranker()
        pairs = [[query, chunk.get("text", "")] for chunk in chunks]
        scores = model.predict(pairs, batch_size=32, show_progress_bar=False)
        
        for i, chunk in enumerate(chunks):
            raw_rerank = float(scores[i])
            # Sigmoid normalization for bounded 0..1 probability
            rerank_prob = 1.0 / (1.0 + math.exp(-raw_rerank)) if -50 < raw_rerank < 50 else (1.0 if raw_rerank >= 50 else 0.0)
            
            dense_score = float(chunk.get("dense_similarity", chunk.get("similarity", 0.0)))
            lexical_score = float(chunk.get("lexical_score", 0.0))
            
            final_score = (w1 * rerank_prob) + (w2 * dense_score) + (w3 * lexical_score)
            
            chunk["raw_rerank_score"] = raw_rerank
            chunk["rerank_score"] = rerank_prob
            chunk["dense_score"] = dense_score
            chunk["lexical_score"] = lexical_score
            chunk["final_score"] = final_score
        
        reranked = sorted(chunks, key=lambda x: x.get("final_score", -999.0), reverse=True)
        return reranked[:top_k]
    except Exception as exc:
        print(f"Error in CrossEncoder reranking: {exc}. Falling back to original candidate order.")
        return chunks[:top_k]
