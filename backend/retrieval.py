"""Hybrid retrieval, query rewriting, and cross-encoder reranking."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from .rag_config import (
    MAX_QUERY_VARIANTS,
    RERANK_POOL_SIZE,
    RERANK_TOP_K,
    RERANKER_MODEL_NAME,
    RETRIEVAL_CANDIDATES,
    RRF_K,
)

_RERANKER: Optional[CrossEncoder] = None

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "what", "which", "who", "whom", "whose", "this", "that", "these", "those",
}


def tokenize_for_bm25(text: str) -> List[str]:
    return re.findall(r"[\wÀ-ỹ]+", text.lower())


def build_bm25_index(chunk_texts: Sequence[str]) -> BM25Okapi:
    corpus = [tokenize_for_bm25(text) for text in chunk_texts]
    return BM25Okapi(corpus)


def extract_keywords(query: str, limit: int = 8) -> List[str]:
    words = re.findall(r"[\wÀ-ỹ]+", query.lower())
    keywords = [w for w in words if len(w) > 2 and w not in _STOPWORDS]
    seen: Set[str] = set()
    unique: List[str] = []
    for word in keywords:
        if word not in seen:
            seen.add(word)
            unique.append(word)
        if len(unique) >= limit:
            break
    return unique


def rewrite_queries(query: str) -> List[str]:
    """Expand a user query into multiple retrieval-focused variants."""
    base = query.strip()
    if not base:
        return []

    variants: List[str] = [base]
    keywords = extract_keywords(base)
    if keywords:
        variants.append(" ".join(keywords))

    stripped = base.rstrip("?").strip()
    if not base.endswith("?"):
        variants.append(f"what is {stripped}")
        variants.append(f"explain {stripped}")
    else:
        variants.append(stripped)
        if keywords:
            variants.append(f"document about {' '.join(keywords[:5])}")

    deduped: List[str] = []
    seen: Set[str] = set()
    for item in variants:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:MAX_QUERY_VARIANTS]


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def encode_queries(embedder: SentenceTransformer, queries: Sequence[str]) -> np.ndarray:
    from .rag_config import EMBEDDING_QUERY_PREFIX

    prefixed = [EMBEDDING_QUERY_PREFIX + q for q in queries] if EMBEDDING_QUERY_PREFIX else list(queries)
    return embedder.encode(
        prefixed,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )


def encode_passages(embedder: SentenceTransformer, texts: Sequence[str]) -> np.ndarray:
    from .rag_config import EMBEDDING_PASSAGE_PREFIX

    prefixed = [EMBEDDING_PASSAGE_PREFIX + t for t in texts] if EMBEDDING_PASSAGE_PREFIX else list(texts)
    return embedder.encode(
        prefixed,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> List[Tuple[int, float]]:
    scores: Dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _filter_indices(allowed_indices: Optional[Set[int]], indices: Sequence[int]) -> List[int]:
    if allowed_indices is None:
        return list(indices)
    return [idx for idx in indices if idx in allowed_indices]


def dense_rankings(
    embedder: SentenceTransformer,
    index: faiss.Index,
    queries: Sequence[str],
    allowed_indices: Optional[Set[int]],
    candidate_k: int,
) -> List[List[int]]:
    if index.ntotal == 0:
        return []

    query_vecs = encode_queries(embedder, queries).astype("float32")
    search_k = min(index.ntotal, max(candidate_k * 3, candidate_k))
    distances, indices = index.search(query_vecs, search_k)

    rankings: List[List[int]] = []
    for row in indices:
        filtered = _filter_indices(allowed_indices, row.tolist())
        rankings.append(filtered[:candidate_k])
    return rankings


def bm25_rankings(
    bm25: BM25Okapi,
    queries: Sequence[str],
    allowed_indices: Optional[Set[int]],
    candidate_k: int,
) -> List[List[int]]:
    rankings: List[List[int]] = []
    for query in queries:
        tokens = tokenize_for_bm25(query)
        scores = bm25.get_scores(tokens)
        ranked = np.argsort(scores)[::-1]
        filtered = _filter_indices(allowed_indices, ranked.tolist())
        rankings.append(filtered[:candidate_k])
    return rankings


def hybrid_retrieve_indices(
    queries: Sequence[str],
    embedder: SentenceTransformer,
    index: faiss.Index,
    bm25: BM25Okapi,
    allowed_indices: Optional[Set[int]],
    candidate_k: int = RETRIEVAL_CANDIDATES,
) -> List[int]:
    dense = dense_rankings(embedder, index, queries, allowed_indices, candidate_k)
    sparse = bm25_rankings(bm25, queries, allowed_indices, candidate_k)
    fused = reciprocal_rank_fusion(dense + sparse)
    return [idx for idx, _ in fused[:candidate_k]]


def get_reranker() -> CrossEncoder:
    global _RERANKER
    if _RERANKER is None:
        _RERANKER = CrossEncoder(RERANKER_MODEL_NAME, max_length=512)
    return _RERANKER


def rerank_indices(
    query: str,
    candidate_indices: Sequence[int],
    chunk_texts: Sequence[str],
    pool_size: int = RERANK_POOL_SIZE,
    top_k: int = RERANK_TOP_K,
) -> List[int]:
    if not candidate_indices:
        return []

    pool = list(candidate_indices[:pool_size])
    if len(pool) == 1:
        return pool

    pairs = [(query, chunk_texts[idx]) for idx in pool]
    scores = get_reranker().predict(pairs, show_progress_bar=False)
    ranked = sorted(zip(pool, scores), key=lambda item: item[1], reverse=True)
    return [idx for idx, _ in ranked[:top_k]]
