"""Offline text helpers + recall@k toy metric (no HF / faiss)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\t", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    parts = SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


def _rrf(rankings: Sequence[Sequence[int]], k: int = 60) -> List[Tuple[int, float]]:
    scores: Dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def test_text_cleaning_and_sentences():
    raw = "Xin chào.   Đây là RAG.\n\nChunk thứ hai!"
    cleaned = clean_text(raw)
    assert "  " not in cleaned
    sents = split_sentences(cleaned)
    assert len(sents) >= 2


def test_recall_at_k_heuristic():
    relevant = 42
    fused = _rrf([[relevant, 1, 2], [1, relevant, 3]], k=60)
    top_k = [idx for idx, _ in fused[:3]]
    assert relevant in top_k
