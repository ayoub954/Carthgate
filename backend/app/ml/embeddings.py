"""Sentence-Transformer semantic matching (multilingual: FR / EN / AR)."""
from __future__ import annotations

import threading
import time

import numpy as np

from ..config import settings

_model = None
_lock = threading.Lock()
_status = {"loaded": False, "error": None, "model": settings.embedding_model}


def get_model():
    global _model
    with _lock:
        if _model is None:
            if _status.get("failed_at") and time.time() - _status["failed_at"] < 600:
                raise RuntimeError("semantic model unavailable (recent failure)")  # do not retry the download for 10 min
            try:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.embedding_model, device="cpu")
                _status.update(loaded=True, error=None)
            except Exception as e:  # model download failure etc.
                _status.update(loaded=False, error=str(e)[:300], failed_at=time.time())
                raise
    return _model


def status() -> dict:
    return dict(_status)


def encode(texts: list[str]) -> np.ndarray:
    m = get_model()
    return np.asarray(m.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False))


def best_matches(queries: list[str], corpus: list[str], top_k: int = 3, corpus_emb: np.ndarray | None = None):
    """Return, for each query, [(corpus_index, cosine_similarity), ...] sorted desc."""
    if not queries or not corpus:
        return [[] for _ in queries]
    q = encode(queries)
    c = corpus_emb if corpus_emb is not None else encode(corpus)
    sims = q @ c.T
    out = []
    for row in sims:
        idx = np.argsort(-row)[:top_k]
        out.append([(int(i), float(row[i])) for i in idx])
    return out
