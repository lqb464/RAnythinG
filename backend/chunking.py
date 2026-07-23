"""Semantic chunking — groups text by meaning using sentence embeddings."""

from __future__ import annotations

import re
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from .rag_config import CHUNK_MAX_WORDS, CHUNK_MIN_WORDS, SEMANTIC_BREAK_PERCENTILE

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

_CHUNK_EMBEDDER: Optional[SentenceTransformer] = None


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


def word_count(text: str) -> int:
    return len(text.split())


def _split_text_units(text: str) -> List[str]:
    """Split into sentences, markdown sections, CSV rows, or slide bullets."""
    units: List[str] = []
    for paragraph in re.split(r"\n\n+", text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # Markdown headings start a new semantic unit
        if paragraph.startswith("#"):
            lines = paragraph.split("\n", 1)
            units.append(lines[0].strip())
            if len(lines) > 1 and lines[1].strip():
                paragraph = lines[1].strip()
            else:
                continue
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        if len(lines) > 1 and all(word_count(line) <= 40 for line in lines):
            units.extend(lines)
            continue
        sentences = split_sentences(paragraph)
        units.extend(sentences if sentences else [paragraph])
    return units


def _split_long_unit(text: str, max_words: int, overlap_words: int) -> List[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(start + 1, end - overlap_words)
    return chunks


def _merge_small_chunks(chunks: List[str], min_words: int) -> List[str]:
    if len(chunks) <= 1:
        return chunks
    merged: List[str] = []
    for chunk in chunks:
        if merged and word_count(chunk) < min_words:
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    if len(merged) > 1 and word_count(merged[-1]) < min_words:
        merged[-2] = f"{merged[-2]} {merged[-1]}".strip()
        merged.pop()
    return merged


def _pack_units_to_max_words(units: List[str], max_words: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_words = 0

    for unit in units:
        unit_words = word_count(unit)
        if current and current_words + unit_words > max_words:
            chunks.append(" ".join(current))
            current = []
            current_words = 0
        current.append(unit)
        current_words += unit_words

    if current:
        chunks.append(" ".join(current))
    return chunks


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _get_chunk_embedder() -> SentenceTransformer:
    global _CHUNK_EMBEDDER
    if _CHUNK_EMBEDDER is None:
        from .rag_config import EMBEDDING_MODEL_NAME

        _CHUNK_EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _CHUNK_EMBEDDER


def _semantic_chunk_units(
    units: List[str],
    embedder: SentenceTransformer,
    max_words: int,
    min_words: int,
    breakpoint_percentile: float,
) -> List[str]:
    if not units:
        return []

    expanded_units: List[str] = []
    overlap_words = max(20, max_words // 5)
    for unit in units:
        if word_count(unit) > max_words:
            expanded_units.extend(_split_long_unit(unit, max_words, overlap_words))
        else:
            expanded_units.append(unit)

    if len(expanded_units) <= 1:
        return _merge_small_chunks(expanded_units, min_words)

    from .rag_config import EMBEDDING_PASSAGE_PREFIX

    units_to_encode = [EMBEDDING_PASSAGE_PREFIX + u for u in expanded_units] if EMBEDDING_PASSAGE_PREFIX else expanded_units
    embeddings = embedder.encode(units_to_encode, convert_to_numpy=True, show_progress_bar=False)
    similarities = [
        _cosine_similarity(embeddings[i], embeddings[i + 1])
        for i in range(len(embeddings) - 1)
    ]

    threshold = float(np.percentile(similarities, breakpoint_percentile))
    breakpoints = {0}
    for idx, sim in enumerate(similarities):
        if sim < threshold:
            breakpoints.add(idx + 1)
    breakpoints.add(len(expanded_units))

    chunks: List[str] = []
    sorted_breaks = sorted(breakpoints)
    for start, end in zip(sorted_breaks[:-1], sorted_breaks[1:]):
        group = expanded_units[start:end]
        chunks.extend(_pack_units_to_max_words(group, max_words))

    return _merge_small_chunks(chunks, min_words)


def semantic_chunk_text(
    text: str,
    embedder: SentenceTransformer,
    max_words: int = CHUNK_MAX_WORDS,
    min_words: int = CHUNK_MIN_WORDS,
    breakpoint_percentile: float = SEMANTIC_BREAK_PERCENTILE,
) -> List[str]:
    """Split text at paragraph boundaries, then group sentences by embedding similarity."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\n+", cleaned) if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    for paragraph in paragraphs:
        units = _split_text_units(paragraph)
        chunks.extend(
            _semantic_chunk_units(units, embedder, max_words, min_words, breakpoint_percentile)
        )
    return chunks


def chunk_text(
    text: str,
    max_words: int = CHUNK_MAX_WORDS,
    overlap_sentences: int = 0,
    embedder: Optional[SentenceTransformer] = None,
) -> List[str]:
    del overlap_sentences
    model = embedder or _get_chunk_embedder()
    return semantic_chunk_text(text, model, max_words=max_words, min_words=CHUNK_MIN_WORDS)
