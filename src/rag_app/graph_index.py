"""Graph-augmented RAG — link chunks by shared concepts and document structure."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .rag_config import GRAPH_MAX_EXPANDED, GRAPH_MIN_SHARED_TERMS

_TERM_RE = re.compile(r"[\wÀ-ỹ]{4,}")
_STOP = {
    "trong", "này", "được", "các", "như", "theo", "với", "cho", "từ", "khi",
    "that", "this", "with", "from", "have", "been", "were", "which", "their",
    "about", "would", "there", "these", "other", "after", "before", "between",
}


@dataclass
class ChunkGraph:
    """Undirected graph connecting semantically related chunks."""

    neighbors: Dict[int, Set[int]] = field(default_factory=dict)
    term_to_chunks: Dict[str, Set[int]] = field(default_factory=dict)

    def expand(
        self,
        seed_indices: Sequence[int],
        max_total: int = GRAPH_MAX_EXPANDED,
    ) -> List[int]:
        """Add graph neighbors to retrieval seeds (seeds keep priority)."""
        ordered: List[int] = []
        seen: Set[int] = set()

        for idx in seed_indices:
            if idx not in seen:
                seen.add(idx)
                ordered.append(idx)

        for idx in list(ordered):
            for neighbor in self.neighbors.get(idx, set()):
                if neighbor not in seen and len(ordered) < max_total:
                    seen.add(neighbor)
                    ordered.append(neighbor)

        return ordered


def _extract_terms(text: str, top_n: int = 12) -> Set[str]:
    tokens = [t.lower() for t in _TERM_RE.findall(text) if t.lower() not in _STOP]
    if not tokens:
        return set()
    counts = Counter(tokens)
    return {term for term, _ in counts.most_common(top_n)}


def build_chunk_graph(
    chunk_texts: Sequence[str],
    chunk_sources: Sequence[str],
) -> ChunkGraph:
    """Build a lightweight knowledge graph over document chunks."""
    graph = ChunkGraph()
    n = len(chunk_texts)
    if n == 0:
        return graph

    chunk_terms: List[Set[str]] = []
    doc_freq: Counter[str] = Counter()

    for text in chunk_texts:
        terms = _extract_terms(text)
        chunk_terms.append(terms)
        for term in terms:
            doc_freq[term] += 1

    # IDF-weighted term importance
    idf: Dict[str, float] = {}
    for term, df in doc_freq.items():
        idf[term] = math.log((n + 1) / (df + 1)) + 1.0

    for idx, terms in enumerate(chunk_terms):
        graph.neighbors.setdefault(idx, set())
        for term in terms:
            graph.term_to_chunks.setdefault(term, set()).add(idx)

    # Sequential edges within the same source (reading-order context)
    by_source: Dict[str, List[int]] = defaultdict(list)
    for idx, source in enumerate(chunk_sources):
        by_source[source].append(idx)

    for indices in by_source.values():
        for i in range(len(indices) - 1):
            a, b = indices[i], indices[i + 1]
            graph.neighbors[a].add(b)
            graph.neighbors[b].add(a)

    # Semantic edges: chunks sharing weighted key terms
    for i in range(n):
        for j in range(i + 1, n):
            if chunk_sources[i] != chunk_sources[j]:
                continue
            shared = chunk_terms[i] & chunk_terms[j]
            if len(shared) < GRAPH_MIN_SHARED_TERMS:
                continue
            weight = sum(idf.get(t, 1.0) for t in shared)
            if weight >= GRAPH_MIN_SHARED_TERMS * 1.5:
                graph.neighbors[i].add(j)
                graph.neighbors[j].add(i)

    return graph


def graph_expand_indices(
    graph: Optional[ChunkGraph],
    seed_indices: Sequence[int],
    max_total: int = GRAPH_MAX_EXPANDED,
) -> List[int]:
    if not graph or not seed_indices:
        return list(seed_indices)
    return graph.expand(seed_indices, max_total=max_total)
