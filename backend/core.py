import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level embedding singleton — loaded once at import time so the model
# is ready before any document is uploaded.
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        from .rag_config import EMBEDDING_MODEL_NAME

        logger.info("Loading embedding model: %s", EMBEDDING_MODEL_NAME)
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _EMBEDDING_MODEL

from .chunking import (
    chunk_text,
    clean_text,
    semantic_chunk_text,
    split_sentences,
)
from .graph_rag import (
    KnowledgeGraph,
    add_source_to_knowledge_graph,
    build_knowledge_graph,
    deserialize_knowledge_graph,
    export_knowledge_graph_view,
    is_global_query,
    normalize_entity_key,
    remove_chunks_from_knowledge_graph,
    serialize_knowledge_graph,
)
from .rag_config import FINAL_TOP_K, GRAPH_GLOBAL_TOP_COMMUNITIES, GRAPH_MAX_EXPANDED
from .retrieval import (
    build_bm25_index,
    encode_passages,
    hybrid_retrieve_indices,
    rerank_indices,
    rewrite_queries,
)
from .synthesis import AnswerSynthesizer, get_synthesizer


@dataclass
class DocumentChunk:
    source: str
    text: str


class RagAgent:
    def __init__(self):
        self.embedding_model = get_embedding_model()
        self.synthesizer = get_synthesizer()
        self.chunks: List[DocumentChunk] = []
        self.index: Optional[faiss.IndexFlatIP] = None
        self.embeddings: Optional[np.ndarray] = None
        self.bm25: Optional[BM25Okapi] = None
        self.knowledge_graph: Optional[KnowledgeGraph] = None

    def _allowed_indices(self, allowed_sources: Optional[List[str]]) -> Optional[Set[int]]:
        if allowed_sources is None:
            return None
        allowed = set(allowed_sources)
        return {idx for idx, chunk in enumerate(self.chunks) if chunk.source in allowed}

    def _rebuild_sparse_index(self) -> None:
        texts = [chunk.text for chunk in self.chunks]
        self.bm25 = build_bm25_index(texts) if texts else None

    def add_documents(self, docs: Sequence[Tuple[str, str]]) -> None:
        self.chunks = []
        for source, text in docs:
            cleaned = clean_text(text)
            if not cleaned:
                continue
            for chunk in semantic_chunk_text(cleaned, self.embedding_model):
                self.chunks.append(DocumentChunk(source=source, text=chunk))

        texts = [chunk.text for chunk in self.chunks]
        if not texts:
            self.embeddings = np.zeros((0, self.embedding_model.get_sentence_embedding_dimension()))
            self.index = None
            self.bm25 = None
            self.knowledge_graph = None
            return

        self.embeddings = encode_passages(self.embedding_model, texts).astype("float32")
        self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
        self.index.add(self.embeddings)
        self._rebuild_sparse_index()
        from .rag_config import graph_rag_enabled

        if graph_rag_enabled():
            self.knowledge_graph = build_knowledge_graph(
                texts,
                [chunk.source for chunk in self.chunks],
                synthesizer=self.synthesizer,
                embedder=self.embedding_model,
            )
        else:
            self.knowledge_graph = None

    def add_document(self, source: str, text: str) -> None:
        """Incrementally index one new document without recomputing existing chunks.

        Much cheaper than ``add_documents`` for notebooks that already have an index:
        only the new document is embedded and only its chunks are mined for the
        knowledge graph — existing embeddings/entities/relations are kept as-is.
        """
        cleaned = clean_text(text)
        if not cleaned:
            return
        new_texts = semantic_chunk_text(cleaned, self.embedding_model)
        if not new_texts:
            return

        start_idx = len(self.chunks)
        self.chunks.extend(DocumentChunk(source=source, text=t) for t in new_texts)
        new_embeddings = encode_passages(self.embedding_model, new_texts).astype("float32")

        if self.embeddings is None or self.embeddings.shape[0] == 0:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])

        if self.index is None:
            self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
            self.index.add(self.embeddings)
        else:
            self.index.add(new_embeddings)

        self._rebuild_sparse_index()

        from .rag_config import graph_rag_enabled

        if graph_rag_enabled() or self.knowledge_graph is not None:
            all_texts = [c.text for c in self.chunks]
            all_sources = [c.source for c in self.chunks]
            new_indices = list(range(start_idx, start_idx + len(new_texts)))
            if self.knowledge_graph is None:
                self.knowledge_graph = build_knowledge_graph(
                    all_texts, all_sources, synthesizer=self.synthesizer, embedder=self.embedding_model
                )
            else:
                add_source_to_knowledge_graph(
                    self.knowledge_graph,
                    new_chunk_texts=new_texts,
                    new_chunk_indices=new_indices,
                    all_chunk_texts=all_texts,
                    all_chunk_sources=all_sources,
                    synthesizer=self.synthesizer,
                    embedder=self.embedding_model,
                )

    def remove_document(self, source: str) -> None:
        """Incrementally drop a document's chunks without re-embedding survivors."""
        keep_indices = [i for i, c in enumerate(self.chunks) if c.source != source]
        if len(keep_indices) == len(self.chunks):
            return

        if not keep_indices:
            self.chunks = []
            self.embeddings = np.zeros((0, self.embedding_model.get_sentence_embedding_dimension()))
            self.index = None
            self.bm25 = None
            self.knowledge_graph = None
            return

        index_remap = {old: new for new, old in enumerate(keep_indices)}
        self.chunks = [self.chunks[i] for i in keep_indices]
        if self.embeddings is not None:
            self.embeddings = self.embeddings[keep_indices].astype("float32")
            self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
            self.index.add(self.embeddings)
        self._rebuild_sparse_index()

        if self.knowledge_graph is not None:
            remove_chunks_from_knowledge_graph(
                self.knowledge_graph,
                index_remap=index_remap,
                remaining_chunk_texts=[c.text for c in self.chunks],
                remaining_chunk_sources=[c.source for c in self.chunks],
                synthesizer=self.synthesizer,
                embedder=self.embedding_model,
            )

    def retrieve(self, query: str, top_k: int = FINAL_TOP_K, allowed_sources: Optional[List[str]] = None) -> List[DocumentChunk]:
        if self.index is None or self.embeddings is None or len(self.chunks) == 0 or self.bm25 is None:
            return []

        queries = rewrite_queries(query)
        allowed_indices = self._allowed_indices(allowed_sources)
        candidate_indices = hybrid_retrieve_indices(
            queries,
            self.embedding_model,
            self.index,
            self.bm25,
            allowed_indices,
        )
        if not candidate_indices:
            return []

        if is_global_query(query) and self.knowledge_graph is not None:
            global_indices = self.knowledge_graph.global_community_indices(
                query,
                self.embedding_model,
                allowed_indices,
                top_k=GRAPH_GLOBAL_TOP_COMMUNITIES,
            )
            seen = set(candidate_indices)
            for idx in global_indices:
                if idx not in seen:
                    seen.add(idx)
                    candidate_indices.append(idx)

        expanded_indices = (
            self.knowledge_graph.expand_indices(candidate_indices, max_total=GRAPH_MAX_EXPANDED)
            if self.knowledge_graph is not None
            else candidate_indices
        )
        chunk_texts = [chunk.text for chunk in self.chunks]
        ranked_indices = rerank_indices(
            query,
            expanded_indices,
            chunk_texts,
            pool_size=len(expanded_indices),
            top_k=top_k,
        )
        return [self.chunks[idx] for idx in ranked_indices]

    def answer(
        self,
        query: str,
        top_k: int = FINAL_TOP_K,
        brief: bool = False,
        allowed_sources: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, List[DocumentChunk]]:
        search_query = self.synthesizer.reformulate_query(query, history) if history else query
        relevant = self.retrieve(search_query, top_k=top_k, allowed_sources=allowed_sources)
        if not relevant:
            return "No relevant information in the selected sources to answer.", []

        chunk_pairs = [(chunk.source, chunk.text) for chunk in relevant]
        global_context = ""
        if is_global_query(query) and self.knowledge_graph is not None:
            global_context = self.knowledge_graph.global_context(
                query, self.embedding_model, top_k=GRAPH_GLOBAL_TOP_COMMUNITIES
            )
        try:
            answer_text = self.synthesizer.synthesize(
                query, chunk_pairs, brief=brief, extra_context=global_context, history=history
            )
        except Exception:
            answer_text = ""

        if not self._is_valid_answer(answer_text):
            answer_text = self._synthesize_extractive(query, relevant)

        return answer_text, relevant

    def answer_stream(
        self,
        query: str,
        top_k: int = FINAL_TOP_K,
        brief: bool = False,
        allowed_sources: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ):
        """Yield incremental events while generating the answer.

        Events: {"type": "sources", "sources": [...]}
                {"type": "token", "text": "..."}
                {"type": "replace", "answer": "..."}  (LLM output rejected, extractive fallback used)
                {"type": "done", "answer": "..."}
        """
        search_query = self.synthesizer.reformulate_query(query, history) if history else query
        relevant = self.retrieve(search_query, top_k=top_k, allowed_sources=allowed_sources)
        if not relevant:
            fallback = "No relevant information in the selected sources to answer."
            yield {"type": "sources", "sources": []}
            yield {"type": "token", "text": fallback}
            yield {"type": "done", "answer": fallback}
            return

        yield {
            "type": "sources",
            "sources": [{"source": c.source, "text": c.text[:300]} for c in relevant],
        }

        chunk_pairs = [(chunk.source, chunk.text) for chunk in relevant]
        global_context = ""
        if is_global_query(query) and self.knowledge_graph is not None:
            global_context = self.knowledge_graph.global_context(
                query, self.embedding_model, top_k=GRAPH_GLOBAL_TOP_COMMUNITIES
            )

        full_text = ""
        try:
            for piece in self.synthesizer.synthesize_stream(
                query, chunk_pairs, brief=brief, extra_context=global_context, history=history
            ):
                full_text += piece
                yield {"type": "token", "text": piece}
        except Exception:
            full_text = ""

        cleaned = self.synthesizer._clean_answer(full_text) if full_text else full_text
        if not self._is_valid_answer(cleaned):
            fallback = self._synthesize_extractive(query, relevant)
            yield {"type": "replace", "answer": fallback}
            cleaned = fallback

        yield {"type": "done", "answer": cleaned}

    @staticmethod
    def _is_valid_answer(text: str) -> bool:
        if not text or len(text.strip()) < 25:
            return False
        lower = text.lower()
        bad_patterns = [
            "based on the following",
            "answer the question",
            "i don't know",
            "i do not have information",
        ]
        if any(pat in lower for pat in bad_patterns) and len(text) < 80:
            return False
        stripped = text.strip()
        if len(stripped) < 120 and not stripped[-1] in (".", "!", "?", ":", "\n", "`", "*", "]"):
            return False
        return True

    def _synthesize_extractive(self, query: str, relevant: List[DocumentChunk]) -> str:
        """High-quality extractive fallback: rank sentences by hybrid relevance."""
        if not relevant:
            return "No relevant information in the selected sources to answer."

        query_words = {w.lower() for w in re.findall(r"[\wÀ-ỹ]+", query) if len(w) > 2}
        query_vec = encode_passages(self.embedding_model, [query])[0]

        scored: List[Tuple[float, str, int]] = []
        for chunk_idx, chunk in enumerate(relevant):
            sentences = split_sentences(chunk.text)
            if not sentences:
                sentences = [chunk.text]
            sent_embs = encode_passages(self.embedding_model, sentences)
            for sent, emb in zip(sentences, sent_embs):
                if len(sent.split()) < 5:
                    continue
                sent_words = {w.lower() for w in re.findall(r"[\wÀ-ỹ]+", sent)}
                keyword_score = len(query_words & sent_words)
                semantic_score = float(np.dot(query_vec, emb))
                score = keyword_score * 2.0 + semantic_score
                scored.append((score, sent.strip(), chunk_idx + 1))

        if not scored:
            lead = relevant[0].text[:500].strip()
            return f"According to the documents, {lead} [1]"

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        parts: List[str] = []
        for _, sent, cite_idx in scored:
            key = sent.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{sent} [{cite_idx}]")
            if len(parts) >= 3:
                break
        return " ".join(parts)

    def generate_suggested_questions(
        self, allowed_sources: Optional[List[str]] = None, limit: int = 4
    ) -> List[str]:
        selected = self.chunks
        if allowed_sources is not None:
            selected = [c for c in self.chunks if c.source in allowed_sources]
        if not selected:
            return [
                "Summarize the main content of the documents?",
                "What are the most important concepts?",
                "Explain the key terms in the documents?",
                "Are any real-world examples or applications mentioned?",
            ]
        _templates = [
            "{}?",
            "Explain {} in detail?",
            "What does {} mean?",
            "Why is {} important?",
            "How can I understand {}?",
            "How is {} applied?",
        ]
        questions: List[str] = []
        seen: set = set()
        tmpl_idx = 0
        for chunk in selected[:8]:
            sentences = re.split(r"(?<=[.!?])\s+", chunk.text)
            for sent in sentences:
                sent = sent.strip()
                words = sent.split()
                if len(words) < 6 or len(sent) > 200:
                    continue
                # Use 5-9 words as topic to vary length
                n = min(len(words), 5 + (tmpl_idx % 5))
                topic = " ".join(words[:n]).rstrip(".,;:!? ")
                if not topic:
                    continue
                tmpl = _templates[tmpl_idx % len(_templates)]
                q = tmpl.format(topic)
                key = topic.lower()
                if key not in seen:
                    seen.add(key)
                    questions.append(q)
                    tmpl_idx += 1
                if len(questions) >= limit:
                    return questions
        defaults = [
            "Summarize the main content of the documents?",
            "List the most important points?",
            "Are there any conclusions or recommendations in the documents?",
        ]
        for q in defaults:
            if len(questions) >= limit:
                break
            if q.lower() not in seen:
                questions.append(q)
        return questions[:limit]

    def summarize_documents(self, max_chunks: int = 8, allowed_sources: Optional[List[str]] = None) -> str:
        selected_chunks = self.chunks
        if allowed_sources is not None:
            selected_chunks = [c for c in self.chunks if c.source in allowed_sources]

        if not selected_chunks:
            return "No documents in the selected sources to summarize."

        selected = selected_chunks[:max_chunks]
        chunk_pairs = [(chunk.source, chunk.text) for chunk in selected]
        try:
            return self.synthesizer.summarize(chunk_pairs)
        except Exception:
            return "\n\n".join(f"**{src}**: {text[:300]}..." for src, text in chunk_pairs[:4])

    def _extract_definitions(self, allowed_sources: Optional[List[str]] = None) -> List[Tuple[str, str, str]]:
        # Returns list of (Term, Definition, Source)
        selected_chunks = self.chunks
        if allowed_sources is not None:
            selected_chunks = [c for c in self.chunks if c.source in allowed_sources]
            
        if not selected_chunks:
            return []

        defs = []
        seen_terms = set()
        for chunk in selected_chunks:
            sentences = re.split(r'(?<=[.!?])\s+', chunk.text)
            for sent in sentences:
                match = re.search(
                    r'\b([A-ZÀ-ỹa-z0-9][A-ZÀ-ỹa-z0-9\s\-\u0300-\u036f]{1,35})\s+(?:refers to|is defined as|is an?|is the)\s+([^.!?\n]{12,150})',
                    sent,
                    re.IGNORECASE
                )
                if match:
                    term = match.group(1).strip()
                    definition = match.group(2).strip()
                    if 1 < len(term.split()) < 6 and term.lower() not in seen_terms:
                        term = term[0].upper() + term[1:]
                        defs.append((term, definition, chunk.source))
                        seen_terms.add(term.lower())
                        if len(defs) >= 12:
                            return defs
                            
        # Fallback if too few definitions found
        if len(defs) < 3:
            for chunk in selected_chunks:
                words = chunk.text.split()
                if len(words) > 18:
                    term = " ".join(words[:3]).strip(".,;:() ")
                    definition = " ".join(words[3:18]).strip(".,;:() ")
                    if term and len(term) > 3 and term.lower() not in seen_terms:
                        term = term[0].upper() + term[1:]
                        defs.append((term, definition, chunk.source))
                        seen_terms.add(term.lower())
                        if len(defs) >= 6:
                            return defs
        return defs

    def generate_audio_overview(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        # Retrieve key chunks
        chunks = self.retrieve("most important points, executive summary", top_k=6, allowed_sources=allowed_sources)
        if not chunks:
            return [
                {"role": "Dan", "text": "Welcome to Audio Overview! It looks like no documents are selected in the Sources panel."},
                {"role": "Lily", "text": "That's right! Upload a file or select notes as sources so we can start the discussion."}
            ]

        try:
            dialogue = self.synthesizer.generate_audio_dialogue([(c.source, c.text) for c in chunks])
            if dialogue:
                return dialogue
        except Exception:
            pass
        return self._generate_audio_overview_rule_based(chunks)

    def _generate_audio_overview_rule_based(self, chunks: List["DocumentChunk"]) -> List[Dict[str, str]]:
        sources_list = list({c.source for c in chunks})
        sources_str = ", ".join(sources_list)

        dialogue = []
        dialogue.append({"role": "Dan", "text": "Hello everyone! Welcome to today's Audio Overview summary. I'm Dan."})
        dialogue.append({"role": "Lily", "text": "And I'm Lily! Today we have a fascinating set of documents from sources: " + sources_str + "."})
        dialogue.append({"role": "Dan", "text": "Exactly! Let's start with the first important point. The documents mention: '" + chunks[0].text[:120] + "...'"})
        dialogue.append({"role": "Lily", "text": "Oh, I find this part really interesting. It clarifies the argument: '" + (chunks[0].text[120:260] if len(chunks[0].text) > 120 else chunks[0].text) + "'. It explains why things work this way."})
        
        if len(chunks) > 1:
            dialogue.append({"role": "Dan", "text": "Exactly! And there's more — in source " + chunks[1].source + ", we also see information about: '" + chunks[1].text[:130] + "...'"})
            dialogue.append({"role": "Lily", "text": "Right, this connects closely to what comes next: '" + (chunks[1].text[130:260] if len(chunks[1].text) > 130 else chunks[1].text) + "'. It helps solve a very practical problem."})

        if len(chunks) > 2:
            dialogue.append({"role": "Dan", "text": "Especially this part: '" + chunks[2].text[:130] + "...'"})
            dialogue.append({"role": "Lily", "text": "I agree! Understanding '" + (chunks[2].text[130:250] if len(chunks[2].text) > 130 else chunks[2].text) + "' is really the key to the big picture."})

        dialogue.append({"role": "Dan", "text": "In summary, these documents give us a deep, structured view of the topic."})
        dialogue.append({"role": "Lily", "text": "Absolutely. Thanks for listening. See you in the next Audio Overview!"})
        
        return dialogue

    def generate_quiz(self, allowed_sources: Optional[List[str]] = None) -> List[Dict]:
        chunks = self.retrieve(
            "important concepts, definitions, figures, main conclusions",
            top_k=6,
            allowed_sources=allowed_sources,
        )
        if chunks:
            try:
                quiz = self.synthesizer.generate_quiz(
                    [(c.source, c.text) for c in chunks], n=4
                )
                if quiz:
                    return quiz
            except Exception:
                pass
        return self._generate_quiz_rule_based(allowed_sources)

    def _generate_quiz_rule_based(self, allowed_sources: Optional[List[str]] = None) -> List[Dict]:
        defs = self._extract_definitions(allowed_sources)
        if not defs or len(defs) < 2:
            return [
                {
                    "question": "You need to upload documents before creating a quiz. Which action is correct?",
                    "options": [
                        "Upload PDF/DOCX/TXT in the Sources panel",
                        "Close the browser",
                        "Delete the notebook",
                        "Do nothing",
                    ],
                    "answer_idx": 0,
                    "explanation": "Upload at least one document so the system can extract content and generate questions automatically.",
                }
            ]

        quiz = []
        # Question 1: What is the term for this definition
        t1, d1, s1 = defs[0]
        options1 = [t1]
        for term, _, _ in defs[1:4]:
            options1.append(term)
        # Ensure we have 4 options
        while len(options1) < 4:
            options1.append(f"Supporting concept {len(options1)}")
        import random
        # Store original term to find its index after shuffling
        correct_term = t1
        random.shuffle(options1)
        ans_idx1 = options1.index(correct_term)
        
        quiz.append({
            "question": f"Which term is defined as: '{d1}'? (Source: {s1})",
            "options": options1,
            "answer_idx": ans_idx1,
            "explanation": f"According to source {s1}, '{correct_term}' is defined as: {d1}."
        })

        # Question 2: Definition of term 2
        if len(defs) > 1:
            t2, d2, s2 = defs[1]
            options2 = [d2]
            for _, d, _ in defs[2:5]:
                options2.append(d)
            while len(options2) < 4:
                options2.append(f"Alternative definition {len(options2)}")
            correct_def = d2
            random.shuffle(options2)
            ans_idx2 = options2.index(correct_def)
            
            quiz.append({
                "question": f"According to the documents, how is '{t2}' explained? (Source: {s2})",
                "options": options2,
                "answer_idx": ans_idx2,
                "explanation": f"In source {s2}, the term '{t2}' means: {correct_def}."
            })

        # Question 3: T/F or Fill in blank style
        if len(defs) > 2:
            t3, d3, s3 = defs[2]
            quiz.append({
                "question": f"True or False: '{t3} is {d3}'? (Source: {s3})",
                "options": ["True", "False"],
                "answer_idx": 0,
                "explanation": f"This statement is accurate according to source {s3}."
            })
            
        return quiz

    def generate_flashcards(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        chunks = self.retrieve(
            "terms, concepts, important definitions",
            top_k=8,
            allowed_sources=allowed_sources,
        )
        if chunks:
            try:
                cards = self.synthesizer.generate_flashcards(
                    [(c.source, c.text) for c in chunks], n=8
                )
                if cards:
                    return cards
            except Exception:
                pass
        return self._generate_flashcards_rule_based(allowed_sources)

    def _generate_flashcards_rule_based(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        defs = self._extract_definitions(allowed_sources)
        if not defs:
            return [
                {"front": "RAG", "back": "Retrieval-Augmented Generation — query documents then generate answers grounded in sources."},
                {"front": "Embedding", "back": "A numeric vector representing the meaning of a text passage."},
                {"front": "Chunk", "back": "A small text segment split from a source document for indexing."},
                {"front": "FAISS", "back": "A high-performance library for similarity search over vectors."},
            ]
        return [{"front": item[0], "back": f"{item[1]} (Source: {item[2]})"} for item in defs[:8]]

    def generate_slide_deck(self, allowed_sources: Optional[List[str]] = None) -> List[Dict]:
        chunks = self.retrieve("core concepts, overview, conclusions", top_k=4, allowed_sources=allowed_sources)
        if not chunks:
            return [
                {"title": "Slide Deck Introduction", "points": ["No source documents selected.", "Upload files so the system can analyze content.", "Slide decks visualize documents as presentation slides."]}
            ]

        slides = []
        slides.append({
            "title": "Slide 1: Topic Overview",
            "points": [
                f"Compiled from documents: {', '.join(list({c.source for c in chunks}))}",
                "Covers core aspects and structural analysis results.",
                "Focuses on semantic analysis and important definitions."
            ]
        })
        
        for i, chunk in enumerate(chunks[:3]):
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk.text) if len(s.strip()) > 15]
            points = sentences[:3] if len(sentences) >= 3 else [chunk.text[:120], chunk.text[120:240]]
            slides.append({
                "title": f"Slide {i+2}: Detailed Analysis - {chunk.source}",
                "points": points
            })
            
        slides.append({
            "title": "Final Slide: Summary & Next Steps",
            "points": [
                "Master the core definitions and terms covered.",
                "Use reference sources to compare with real-world practice.",
                "Ask follow-up questions in Chat for deeper understanding."
            ]
        })
        return slides

    def generate_mind_map(self, allowed_sources: Optional[List[str]] = None) -> Dict[str, str]:
        chunks = self.retrieve(
            "main topic, content structure, concept branches",
            top_k=6,
            allowed_sources=allowed_sources,
        )
        if chunks:
            try:
                data = self.synthesizer.generate_mindmap([(c.source, c.text) for c in chunks])
                if data:
                    return self._mindmap_json_to_output(data)
            except Exception:
                pass
        return self._generate_mind_map_rule_based(allowed_sources)

    @staticmethod
    def _mindmap_json_to_output(data: Dict) -> Dict[str, str]:
        root = str(data.get("root", "Documents")).strip() or "Documents"
        branches = data.get("branches") or []

        markdown_lines = [f"- **{root}**"]
        mermaid_lines = ["graph TD", f'  Root["{root}"]']
        for b_idx, branch in enumerate(branches):
            if not isinstance(branch, dict):
                continue
            label = str(branch.get("label", "")).strip()
            if not label:
                continue
            markdown_lines.append(f"  - **{label}**")
            node_id = f"B{b_idx}"
            safe_label = label.replace('"', "'")
            mermaid_lines.append(f'  Root --> {node_id}["{safe_label}"]')
            for c_idx, child in enumerate(branch.get("children") or []):
                child = str(child).strip()
                if not child:
                    continue
                markdown_lines.append(f"    - {child}")
                safe_child = child[:60].replace('"', "'")
                mermaid_lines.append(f'  {node_id} --> {node_id}C{c_idx}["{safe_child}"]')

        return {"markdown": "\n".join(markdown_lines), "mermaid": "\n".join(mermaid_lines)}

    def _generate_mind_map_rule_based(self, allowed_sources: Optional[List[str]] = None) -> Dict[str, str]:
        defs = self._extract_definitions(allowed_sources)
        if not defs:
            markdown_map = (
                "- **RAG NotebookLM System**\n"
                "  - **Document sources**\n"
                "    - Upload PDF / DOCX / TXT\n"
                "  - **Processing**\n"
                "    - Text chunking\n"
                "    - Embedding + FAISS\n"
                "  - **Interaction**\n"
                "    - Q&A chat\n"
                "    - Studio tools"
            )
            mermaid = (
                "graph TD\n"
                "  Root[RAG Notebook] --> Sources[Document sources]\n"
                "  Root --> Process[Processing]\n"
                "  Root --> Chat[Chat]\n"
                "  Sources --> Upload[Upload file]\n"
                "  Process --> Chunk[Chunk]\n"
                "  Process --> Emb[Embedding]\n"
                "  Process --> Vec[FAISS Index]\n"
                "  Chat --> Retrieve[Semantic query]\n"
                "  Chat --> Answer[Generate answer]"
            )
            return {"markdown": markdown_map, "mermaid": mermaid}

        # Build custom map
        source_names = list({item[2] for item in defs})
        markdown_map = f"- **Content from {', '.join(source_names)}**\n"
        mermaid = "graph TD\n"
        mermaid += f"  Root[\"Source document: {source_names[0]}\"]\n"
        
        for i, (term, definition, source) in enumerate(defs[:6]):
            short_def = definition[:50] + "..." if len(definition) > 50 else definition
            # Escape quotes
            term_clean = term.replace('"', '\\"')
            def_clean = short_def.replace('"', '\\"')
            
            markdown_map += f"  - **{term}**: {short_def}\n"
            mermaid += f"  Root --> Node{i}[\"{term_clean}\"]\n"
            mermaid += f"  Node{i} --> SubNode{i}[\"{def_clean}\"]\n"
            
        return {"markdown": markdown_map, "mermaid": mermaid}

    def generate_reports(self, allowed_sources: Optional[List[str]] = None) -> str:
        chunks = self.retrieve("results, analysis, conclusions, recommendations", top_k=4, allowed_sources=allowed_sources)
        if not chunks:
            return "### Overview Report\n\nNo source documents selected. Please select or upload documents."

        report = f"# Research Report & Study Guide\n\n**Analyzed document sources:** {', '.join(list({c.source for c in chunks}))}\n\n---\n\n"
        report += "## 1. Executive Summary\n"
        report += "The documents provide important foundational concepts. From the content analysis, the main points are:\n\n"
        for chunk in chunks[:2]:
            report += f"- **From {chunk.source}**: {chunk.text[:220]}...\n"
            
        report += "\n## 2. Key Concepts\n"
        defs = self._extract_definitions(allowed_sources)
        if defs:
            for term, definition, src in defs[:5]:
                report += f"- **{term}** (Source: *{src}*): {definition}\n"
        else:
            report += "No concepts were extracted automatically. Search the documents for more detail.\n"
            
        report += "\n## 3. Frequently Asked Questions (FAQ)\n"
        if defs:
            for i, (term, definition, src) in enumerate(defs[:3]):
                report += f"**Q{i+1}: How should {term} be understood?**\n"
                report += f"*Answer:* According to source *{src}*, {definition}\n\n"
        else:
            report += "**Q1: What is the main content of the documents?**\n*Answer:* The documents focus on optimization and information structure in the system.\n"

        report += "\n## 4. Study & Assessment Guide\n"
        report += "1. Read the definition sections carefully and compare with real-world examples.\n"
        report += "2. Answer the quiz questions in Studio to self-assess your understanding.\n"
        report += "3. Use Flashcards to memorize key terms quickly.\n"
        
        return report

    def generate_video_overview(self, allowed_sources: Optional[List[str]] = None) -> str:
        chunks = self.retrieve("summary, introduction, overview", top_k=3, allowed_sources=allowed_sources)
        if not chunks:
            return "### Video Storyboard\n\nNo source documents selected. Please select or upload documents."

        storyboard = "# Video Overview: Detailed Storyboard & Script\n\n"
        storyboard += f"**Documents analyzed:** {', '.join(list({c.source for c in chunks}))}\n"
        storyboard += "**Estimated duration:** 2 minutes | **Goal:** Briefly introduce the core ideas from the documents.\n\n---\n\n"
        
        storyboard += "### Scene 1: Introduction (0:00 - 0:30)\n"
        storyboard += "- **Visuals:** Intro graphics with the document title and linked book/technology icons.\n"
        storyboard += "- **Background audio:** Light, inspiring acoustic music.\n"
        storyboard += f"- **Voiceover:** \"Hello everyone! Today we'll explore this important document together. Based on the stored sources, let's walk through the main points.\"\n\n"
        
        storyboard += "### Scene 2: Main Points & Details (0:30 - 1:30)\n"
        storyboard += "- **Visuals:** Highlighted quote text on a dark background with diagram illustrations:\n"
        if chunks:
            storyboard += f"  > *\"{chunks[0].text[:120]}...\"*\n"
        storyboard += "- **Voiceover:** \"The first core point is this content. It explains the structure and approach to the topic in a rigorous way.\"\n\n"
        
        storyboard += "### Scene 3: Conclusion & Call to Action (1:30 - 2:00)\n"
        storyboard += "- **Visuals:** NotebookLM app logo with key takeaways shown as a checklist.\n"
        storyboard += "- **Voiceover:** \"That's a quick summary of this document. Use attached tools like Quiz and Flashcards in Studio to go deeper. See you next time!\"\n"
        
        return storyboard

    def generate_infographic(self, allowed_sources: Optional[List[str]] = None) -> str:
        defs = self._extract_definitions(allowed_sources)
        chunks = self.retrieve("counts, percentages, statistics, important", top_k=3, allowed_sources=allowed_sources)
        
        info = "# Infographic Blueprint: Visual Document Design\n\n"
        info += "This blueprint outlines the most effective visual layout for your documents.\n\n---\n\n"
        
        info += "## Primary color palette\n"
        info += "- **Primary:** Dark navy (#0b1220) for a modern, knowledge-focused feel.\n"
        info += "- **Accent:** Coral red (#ef4444) or amber to highlight important information.\n\n"
        
        info += "## Three main blocks (3-block layout)\n\n"
        info += "### Block 1: Foundational concepts (top)\n"
        if defs:
            t, d, s = defs[0]
            info += f"- **Focus:** {t}\n"
            info += f"- **Visual treatment:** Center circle frame. Short definition: \"*{d[:80]}...*\"\n"
        else:
            info += "- **Focus:** RAG & data mining overview.\n"
            
        info += "\n### Block 2: Metrics & detailed analysis (middle)\n"
        stats = self.get_stats()
        info += f"- **Metric 1:** {stats['documents']} source documents integrated.\n"
        info += f"- **Metric 2:** {stats['chunks']} information chunks segmented.\n"
        info += f"- **Metric 3:** Average {stats['avg_chunk_length']} words per chunk.\n"
        
        info += "\n### Block 3: Practical significance (bottom)\n"
        if len(chunks) > 0:
            info += f"- **Key quote:** \"{chunks[0].text[:120]}...\"\n"
        info += "- **Action:** Apply this knowledge to related analysis problems.\n"
        
        return info

    def generate_data_table(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        defs = self._extract_definitions(allowed_sources)
        if not defs:
            return [
                {"Term": "RAG", "Description": "Query documents and generate answers with source citations.", "Source": "System"},
                {"Term": "Embedding", "Description": "Vector representation of text for semantic search.", "Source": "System"},
                {"Term": "FAISS", "Description": "Vector index for fast similarity queries.", "Source": "System"},
            ]
        return [{"Term": term, "Description": definition, "Source": src} for term, definition, src in defs]


    def get_stats(self) -> Dict[str, int]:
        chunks = len(self.chunks)
        sources = len({chunk.source for chunk in self.chunks})
        avg_chunk_len = 0
        if chunks > 0:
            avg_chunk_len = int(sum(len(chunk.text.split()) for chunk in self.chunks) / chunks)
        return {
            "documents": sources,
            "chunks": chunks,
            "avg_chunk_length": avg_chunk_len,
            "graph_entities": len(self.knowledge_graph.entities) if self.knowledge_graph else 0,
            "graph_relations": len(self.knowledge_graph.relations) if self.knowledge_graph else 0,
        }

    def rebuild_knowledge_graph(self, use_llm: bool = True) -> dict:
        """Build / rebuild entity graph for Graph mode (on-demand)."""
        if not self.chunks:
            self.knowledge_graph = None
            return {"ok": False, "error": "No chunks yet — upload documents"}
        texts = [c.text for c in self.chunks]
        sources = [c.source for c in self.chunks]
        self.knowledge_graph = build_knowledge_graph(
            texts,
            sources,
            synthesizer=self.synthesizer if use_llm else None,
            embedder=self.embedding_model,
        )
        return {
            "ok": True,
            "entities": len(self.knowledge_graph.entities),
            "relations": len(self.knowledge_graph.relations),
            "communities": len(self.knowledge_graph.communities),
        }

    def clear_knowledge_graph(self) -> dict:
        """Drop on-demand entity graph (sources / FAISS index stay)."""
        self.knowledge_graph = None
        return {"ok": True, "cleared": True}

    def export_graph_view(self, max_nodes: int = 60) -> dict:
        if self.knowledge_graph is None:
            return {
                "ok": False,
                "built": False,
                "nodes": [],
                "edges": [],
                "communities": [],
                "message": "No knowledge graph yet — click Build Graph",
            }
        view = export_knowledge_graph_view(
            self.knowledge_graph,
            [c.source for c in self.chunks],
            max_nodes=max_nodes,
        )
        view["built"] = True
        return view

    def ask_about_entity(self, entity_id: str, question: str = "") -> Tuple[str, List[DocumentChunk]]:
        """Answer a question grounded in chunks linked to an entity."""
        if self.knowledge_graph is None:
            return "No knowledge graph yet. Build the graph first.", []
        key = normalize_entity_key(entity_id)
        if key not in self.knowledge_graph.entities and entity_id not in self.knowledge_graph.entities:
            # try label match
            for k, ent in self.knowledge_graph.entities.items():
                if normalize_entity_key(ent.name) == key or ent.name.lower() == entity_id.lower():
                    key = k
                    break
            else:
                return f"Entity «{entity_id}» not found in graph.", []
        chunk_ids = sorted(self.knowledge_graph.entity_to_chunks.get(key, set()))
        if not chunk_ids:
            return f"Entity «{entity_id}» is not linked to any chunks.", []
        label = self.knowledge_graph.entities[key].name
        q = (question or "").strip() or f"Explain the concept «{label}» based on the documents."
        # Restrict retrieval to entity-linked sources
        sources = list({self.chunks[i].source for i in chunk_ids if 0 <= i < len(self.chunks)})
        return self.answer(q, top_k=4, allowed_sources=sources or None)

    def save_query_history(self, history: Sequence[Dict[str, str]], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list(history), f, ensure_ascii=False, indent=2)

    def load_query_history(self, path: str) -> List[Dict[str, str]]:
        if not Path(path).exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def export_index_bytes(self) -> bytes:
        if self.index is None:
            raise ValueError("No index available to export.")
        return faiss.serialize_index(self.index)

    def load_index_from_bytes(self, data: bytes) -> None:
        self.index = faiss.deserialize_index(data)

    def export_metadata_bytes(self) -> bytes:
        if not self.chunks:
            raise ValueError("No metadata available to export.")
        payload = {
            "chunks": [chunk.__dict__ for chunk in self.chunks],
            "knowledge_graph": serialize_knowledge_graph(self.knowledge_graph),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def load_metadata_from_bytes(self, data: bytes) -> None:
        raw = json.loads(data.decode("utf-8"))
        self._apply_metadata_payload(raw)

    def save_index(self, path: str) -> None:
        if self.index is None or self.embeddings is None:
            raise ValueError("No index available to save. Build index first.")
        faiss.write_index(self.index, path)

    def load_index(self, path: str) -> None:
        self.index = faiss.read_index(path)

    def save_metadata(self, path: str) -> None:
        if not self.chunks:
            raise ValueError("No metadata to save.")
        payload = {
            "chunks": [chunk.__dict__ for chunk in self.chunks],
            "knowledge_graph": serialize_knowledge_graph(self.knowledge_graph),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _apply_metadata_payload(self, raw) -> None:
        if isinstance(raw, list):
            chunks_data = raw
            kg_data: dict = {}
        else:
            chunks_data = raw.get("chunks", [])
            kg_data = raw.get("knowledge_graph", {})

        self.chunks = [DocumentChunk(**item) for item in chunks_data]
        if not self.chunks:
            self.knowledge_graph = None
            return

        texts = [chunk.text for chunk in self.chunks]
        sources = [chunk.source for chunk in self.chunks]
        self.embeddings = encode_passages(self.embedding_model, texts).astype("float32")
        self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
        self.index.add(self.embeddings)
        self._rebuild_sparse_index()

        self.knowledge_graph = deserialize_knowledge_graph(kg_data, texts, sources, self.embedding_model)
        if self.knowledge_graph is None:
            self.knowledge_graph = build_knowledge_graph(
                texts, sources, synthesizer=None, embedder=self.embedding_model
            )

    def load_metadata(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            self._apply_metadata_payload(json.load(f))
