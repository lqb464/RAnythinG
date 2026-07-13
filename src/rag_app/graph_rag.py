"""Full Graph RAG — entity graph, communities, global + local retrieval."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np

from .graph_index import ChunkGraph, build_chunk_graph, graph_expand_indices
from .rag_config import (
    GRAPH_GLOBAL_TOP_COMMUNITIES,
    GRAPH_MAX_EXPANDED,
    GRAPH_MIN_SHARED_TERMS,
)

if TYPE_CHECKING:
    from .synthesis import AnswerSynthesizer

_ENTITY_LINE = re.compile(r"^ENTITY:\s*(.+?)\s*\|\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_RELATION_LINE = re.compile(
    r"^RELATION:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_TERM_RE = re.compile(r"[\wÀ-ỹ]{4,}")
_STOP = {
    "trong", "này", "được", "các", "như", "theo", "với", "cho", "từ", "khi",
    "that", "this", "with", "from", "have", "been", "were", "which", "their",
}
_GLOBAL_QUERY_RE = re.compile(
    r"tóm tắt|tổng quan|overview|summarize|summary|chủ đề chính|toàn bộ|"
    r"big picture|nói về gì|main theme|ý chính|bức tranh tổng thể|"
    r"paper này|tài liệu này|document about|what is this about",
    re.IGNORECASE,
)


@dataclass
class Entity:
    name: str
    entity_type: str = "concept"


@dataclass
class Relation:
    source: str
    target: str
    relation: str


@dataclass
class Community:
    id: int
    entity_names: List[str]
    chunk_indices: Set[int]
    summary: str


@dataclass
class KnowledgeGraph:
    """Entity-relationship graph with community summaries (GraphRAG-style)."""

    entities: Dict[str, Entity] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)
    entity_to_chunks: Dict[str, Set[int]] = field(default_factory=dict)
    chunk_to_entities: Dict[int, Set[str]] = field(default_factory=dict)
    communities: List[Community] = field(default_factory=list)
    chunk_graph: Optional[ChunkGraph] = None
    community_embeddings: Optional[np.ndarray] = None

    def expand_indices(
        self,
        seed_indices: Sequence[int],
        max_total: int = GRAPH_MAX_EXPANDED,
    ) -> List[int]:
        ordered = graph_expand_indices(self.chunk_graph, seed_indices, max_total=max_total)
        seen = set(ordered)
        for idx in list(ordered):
            for entity in self.chunk_to_entities.get(idx, set()):
                for linked in self.entity_to_chunks.get(entity, set()):
                    if linked not in seen and len(ordered) < max_total:
                        seen.add(linked)
                        ordered.append(linked)
        return ordered

    def global_community_indices(
        self,
        query: str,
        embedder,
        allowed_indices: Optional[Set[int]],
        top_k: int = GRAPH_GLOBAL_TOP_COMMUNITIES,
    ) -> List[int]:
        if not self.communities or self.community_embeddings is None:
            return []
        from .rag_config import EMBEDDING_QUERY_PREFIX

        q_input = EMBEDDING_QUERY_PREFIX + query if EMBEDDING_QUERY_PREFIX else query
        query_vec = embedder.encode([q_input], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = self.community_embeddings @ query_vec
        ranked = np.argsort(scores)[::-1]
        indices: List[int] = []
        seen: Set[int] = set()
        for comm_idx in ranked[:top_k]:
            community = self.communities[int(comm_idx)]
            for chunk_idx in community.chunk_indices:
                if allowed_indices is not None and chunk_idx not in allowed_indices:
                    continue
                if chunk_idx not in seen:
                    seen.add(chunk_idx)
                    indices.append(chunk_idx)
        return indices

    def global_context(self, query: str, embedder, top_k: int = GRAPH_GLOBAL_TOP_COMMUNITIES) -> str:
        if not self.communities or self.community_embeddings is None:
            return ""
        from .rag_config import EMBEDDING_QUERY_PREFIX

        q_input = EMBEDDING_QUERY_PREFIX + query if EMBEDDING_QUERY_PREFIX else query
        query_vec = embedder.encode([q_input], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = self.community_embeddings @ query_vec
        ranked = np.argsort(scores)[::-1][:top_k]
        parts = []
        for rank, comm_idx in enumerate(ranked, start=1):
            comm = self.communities[int(comm_idx)]
            if comm.summary.strip():
                parts.append(f"[Community {rank}] {comm.summary}")
        return "\n\n".join(parts)


def is_global_query(query: str) -> bool:
    return bool(_GLOBAL_QUERY_RE.search(query))


def _normalize_entity(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _rule_entities(text: str, top_n: int = 10) -> List[Entity]:
    tokens = [t for t in _TERM_RE.findall(text) if t.lower() not in _STOP]
    counts = Counter(tokens)
    entities: List[Entity] = []
    for term, _ in counts.most_common(top_n):
        entities.append(Entity(name=term, entity_type="term"))
    # Acronyms / proper nouns
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", text):
        name = match.group(0)
        key = _normalize_entity(name)
        if key not in {_normalize_entity(e.name) for e in entities}:
            entities.append(Entity(name=name, entity_type="proper_noun"))
    return entities[:top_n + 5]


def parse_graph_extraction(raw: str) -> Tuple[List[Entity], List[Relation]]:
    entities: List[Entity] = []
    relations: List[Relation] = []
    for match in _ENTITY_LINE.finditer(raw):
        entities.append(Entity(name=match.group(1).strip(), entity_type=match.group(2).strip()))
    for match in _RELATION_LINE.finditer(raw):
        relations.append(
            Relation(
                source=match.group(1).strip(),
                target=match.group(3).strip(),
                relation=match.group(2).strip(),
            )
        )
    return entities, relations


def _link_entities_to_chunks(
    graph: KnowledgeGraph,
    chunk_texts: Sequence[str],
    entities: Sequence[Entity],
) -> None:
    for entity in entities:
        key = _normalize_entity(entity.name)
        if not key or len(key) < 3:
            continue
        graph.entities.setdefault(key, entity)
        graph.entity_to_chunks.setdefault(key, set())
        for idx, text in enumerate(chunk_texts):
            if key in text.lower() or entity.name in text:
                graph.entity_to_chunks[key].add(idx)
                graph.chunk_to_entities.setdefault(idx, set()).add(key)


def _detect_communities(graph: KnowledgeGraph) -> List[Set[str]]:
    nx_graph = nx.Graph()
    for key in graph.entities:
        nx_graph.add_node(key)
    for rel in graph.relations:
        s, t = _normalize_entity(rel.source), _normalize_entity(rel.target)
        if s and t:
            nx_graph.add_edge(s, t, weight=1.0, relation=rel.relation)
    for key, chunks in graph.entity_to_chunks.items():
        chunk_list = list(chunks)
        for i in range(len(chunk_list)):
            for j in range(i + 1, len(chunk_list)):
                co_entities = graph.chunk_to_entities.get(chunk_list[i], set()) & graph.chunk_to_entities.get(
                    chunk_list[j], set()
                )
                for a in co_entities:
                    for b in co_entities:
                        if a != b:
                            nx_graph.add_edge(a, b, weight=0.5)

    if nx_graph.number_of_nodes() == 0:
        return []
    if nx_graph.number_of_edges() == 0:
        return [{n} for n in nx_graph.nodes]

    try:
        communities = list(nx.community.louvain_communities(nx_graph, weight="weight"))
    except Exception:
        communities = [set(nx_graph.nodes)]
    return communities


def build_knowledge_graph(
    chunk_texts: Sequence[str],
    chunk_sources: Sequence[str],
    synthesizer: Optional["AnswerSynthesizer"] = None,
    embedder=None,
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    graph.chunk_graph = build_chunk_graph(chunk_texts, chunk_sources)

    if not chunk_texts:
        return graph

    # Rule-based entities per chunk (always available)
    for idx, text in enumerate(chunk_texts):
        _link_entities_to_chunks(graph, chunk_texts, _rule_entities(text))

    # LLM entity extraction per source (GraphRAG-style, stronger)
    by_source: Dict[str, List[int]] = defaultdict(list)
    for idx, source in enumerate(chunk_sources):
        by_source[source].append(idx)

    if synthesizer is not None:
        for indices in by_source.values():
            sample_texts = [chunk_texts[i] for i in indices[:6]]
            combined = "\n\n---\n\n".join(sample_texts)[:6000]
            try:
                raw = synthesizer.extract_graph_from_text(combined)
                llm_entities, llm_relations = parse_graph_extraction(raw)
                _link_entities_to_chunks(graph, chunk_texts, llm_entities)
                graph.relations.extend(llm_relations)
            except Exception:
                pass

    entity_communities = _detect_communities(graph)
    for comm_id, entity_keys in enumerate(entity_communities):
        chunk_ids: Set[int] = set()
        names: List[str] = []
        for key in entity_keys:
            names.append(graph.entities.get(key, Entity(name=key)).name)
            chunk_ids.update(graph.entity_to_chunks.get(key, set()))
        summary = ""
        if synthesizer is not None and chunk_ids:
            texts = [chunk_texts[i] for i in sorted(chunk_ids)[:5]]
            try:
                summary = synthesizer.summarize_community(names[:8], texts)
            except Exception:
                summary = ""
        if not summary.strip() and chunk_ids:
            preview = chunk_texts[sorted(chunk_ids)[0]][:240]
            summary = f"Các khái niệm: {', '.join(names[:6])}. {preview}..."
        graph.communities.append(
            Community(id=comm_id, entity_names=names, chunk_indices=chunk_ids, summary=summary)
        )

    if graph.communities and embedder is not None:
        from .retrieval import encode_passages

        summaries = [c.summary for c in graph.communities]
        graph.community_embeddings = encode_passages(embedder, summaries)

    return graph


def _recompute_communities(
    graph: KnowledgeGraph,
    all_chunk_texts: Sequence[str],
    synthesizer: Optional["AnswerSynthesizer"],
    embedder,
) -> None:
    """Re-run Louvain community detection (cheap, no LLM) and reuse cached summaries
    for communities whose entity membership hasn't changed, only calling the LLM for
    genuinely new/changed communities."""
    summary_cache = {frozenset(c.entity_names): c.summary for c in graph.communities}
    entity_communities = _detect_communities(graph)

    communities: List[Community] = []
    for comm_id, entity_keys in enumerate(entity_communities):
        chunk_ids: Set[int] = set()
        names: List[str] = []
        for key in entity_keys:
            names.append(graph.entities.get(key, Entity(name=key)).name)
            chunk_ids.update(graph.entity_to_chunks.get(key, set()))
        fingerprint = frozenset(names)
        summary = summary_cache.get(fingerprint, "")
        if not summary and synthesizer is not None and chunk_ids:
            texts = [all_chunk_texts[i] for i in sorted(chunk_ids)[:5]]
            try:
                summary = synthesizer.summarize_community(names[:8], texts)
            except Exception:
                summary = ""
        if not summary.strip() and chunk_ids:
            preview = all_chunk_texts[sorted(chunk_ids)[0]][:240]
            summary = f"Các khái niệm: {', '.join(names[:6])}. {preview}..."
        communities.append(Community(id=comm_id, entity_names=names, chunk_indices=chunk_ids, summary=summary))

    graph.communities = communities
    if graph.communities and embedder is not None:
        from .retrieval import encode_passages

        summaries = [c.summary for c in graph.communities]
        graph.community_embeddings = encode_passages(embedder, summaries)
    else:
        graph.community_embeddings = None


def add_source_to_knowledge_graph(
    graph: KnowledgeGraph,
    new_chunk_texts: Sequence[str],
    new_chunk_indices: Sequence[int],
    all_chunk_texts: Sequence[str],
    all_chunk_sources: Sequence[str],
    synthesizer: Optional["AnswerSynthesizer"] = None,
    embedder=None,
) -> None:
    """Extend an existing KnowledgeGraph with a newly-added source's chunks.

    Avoids re-running rule/LLM entity extraction on chunks that were already indexed —
    only the new chunks are mined, existing entities/relations are kept as-is.
    """
    for idx, text in zip(new_chunk_indices, new_chunk_texts):
        _link_entities_to_chunks(graph, all_chunk_texts, _rule_entities(text))
        graph.chunk_to_entities.setdefault(idx, graph.chunk_to_entities.get(idx, set()))

    if synthesizer is not None:
        combined = "\n\n---\n\n".join(new_chunk_texts[:6])[:6000]
        try:
            raw = synthesizer.extract_graph_from_text(combined)
            llm_entities, llm_relations = parse_graph_extraction(raw)
            _link_entities_to_chunks(graph, all_chunk_texts, llm_entities)
            graph.relations.extend(llm_relations)
        except Exception:
            pass

    graph.chunk_graph = build_chunk_graph(all_chunk_texts, all_chunk_sources)
    _recompute_communities(graph, all_chunk_texts, synthesizer, embedder)


def remove_chunks_from_knowledge_graph(
    graph: KnowledgeGraph,
    index_remap: Dict[int, int],
    remaining_chunk_texts: Sequence[str],
    remaining_chunk_sources: Sequence[str],
    synthesizer: Optional["AnswerSynthesizer"] = None,
    embedder=None,
) -> None:
    """Drop chunks (and now-orphaned entities) from a KnowledgeGraph in place.

    ``index_remap`` maps old chunk index -> new chunk index for chunks that survive;
    indices not present in the map are treated as removed.
    """
    new_entity_to_chunks: Dict[str, Set[int]] = {}
    for key, chunk_ids in graph.entity_to_chunks.items():
        remapped = {index_remap[i] for i in chunk_ids if i in index_remap}
        if remapped:
            new_entity_to_chunks[key] = remapped
    graph.entity_to_chunks = new_entity_to_chunks

    graph.entities = {k: v for k, v in graph.entities.items() if k in graph.entity_to_chunks}
    live_keys = set(graph.entities.keys())
    graph.relations = [
        r
        for r in graph.relations
        if _normalize_entity(r.source) in live_keys and _normalize_entity(r.target) in live_keys
    ]
    graph.chunk_to_entities = {
        new_idx: {k for k in graph.chunk_to_entities.get(old_idx, set()) if k in live_keys}
        for old_idx, new_idx in index_remap.items()
    }

    graph.chunk_graph = build_chunk_graph(remaining_chunk_texts, remaining_chunk_sources)
    _recompute_communities(graph, remaining_chunk_texts, synthesizer, embedder)


def serialize_knowledge_graph(graph: Optional[KnowledgeGraph]) -> dict:
    if graph is None:
        return {}
    return {
        "entities": {k: {"name": v.name, "entity_type": v.entity_type} for k, v in graph.entities.items()},
        "relations": [r.__dict__ for r in graph.relations],
        "entity_to_chunks": {k: list(v) for k, v in graph.entity_to_chunks.items()},
        "chunk_to_entities": {str(k): list(v) for k, v in graph.chunk_to_entities.items()},
        "communities": [
            {
                "id": c.id,
                "entity_names": c.entity_names,
                "chunk_indices": list(c.chunk_indices),
                "summary": c.summary,
            }
            for c in graph.communities
        ],
    }


def deserialize_knowledge_graph(
    data: dict,
    chunk_texts: Sequence[str],
    chunk_sources: Sequence[str],
    embedder=None,
) -> Optional[KnowledgeGraph]:
    if not data:
        return None
    graph = KnowledgeGraph()
    graph.chunk_graph = build_chunk_graph(chunk_texts, chunk_sources)
    for key, val in data.get("entities", {}).items():
        graph.entities[key] = Entity(name=val["name"], entity_type=val.get("entity_type", "concept"))
    graph.relations = [Relation(**r) for r in data.get("relations", [])]
    graph.entity_to_chunks = {k: set(v) for k, v in data.get("entity_to_chunks", {}).items()}
    graph.chunk_to_entities = {int(k): set(v) for k, v in data.get("chunk_to_entities", {}).items()}
    for item in data.get("communities", []):
        graph.communities.append(
            Community(
                id=item["id"],
                entity_names=item["entity_names"],
                chunk_indices=set(item["chunk_indices"]),
                summary=item["summary"],
            )
        )
    if graph.communities and embedder is not None:
        from .retrieval import encode_passages

        summaries = [c.summary for c in graph.communities]
        graph.community_embeddings = encode_passages(embedder, summaries)
    return graph
