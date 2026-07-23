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
            return "Không có thông tin phù hợp trong các nguồn được chọn để trả lời.", []

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
            fallback = "Không có thông tin phù hợp trong các nguồn được chọn để trả lời."
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
            "không biết",
            "tôi không có thông tin",
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
            return "Không có thông tin phù hợp trong các nguồn được chọn để trả lời."

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
            return f"Theo tài liệu, {lead} [1]"

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
                "Tóm tắt nội dung chính của tài liệu?",
                "Các khái niệm quan trọng nhất là gì?",
                "Giải thích các thuật ngữ chính trong tài liệu?",
                "Có ví dụ hoặc ứng dụng thực tế nào được đề cập không?",
            ]
        _templates = [
            "{}?",
            "Giải thích chi tiết về {}?",
            "{} có nghĩa là gì?",
            "Tại sao {} lại quan trọng?",
            "Làm thế nào để hiểu {}?",
            "{} được áp dụng như thế nào?",
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
            "Tóm tắt nội dung chính của tài liệu?",
            "Liệt kê các điểm quan trọng nhất?",
            "Có kết luận hoặc khuyến nghị nào trong tài liệu không?",
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
            return "Không có tài liệu nào trong nguồn đã chọn để tóm tắt."

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
                    r'\b([A-ZÀ-ỹa-z0-9][A-ZÀ-ỹa-z0-9\s\-\u0300-\u036f]{1,35})\s+(?:là|được định nghĩa là|refers to|is defined as|is an?|is the)\s+([^.!?\n]{12,150})',
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
        chunks = self.retrieve("các điểm quan trọng nhất, tóm tắt tổng quan", top_k=6, allowed_sources=allowed_sources)
        if not chunks:
            return [
                {"role": "Dan", "text": "Chào mừng bạn đến với Audio Overview! Có vẻ như chưa có tài liệu nào được chọn ở bảng nguồn."},
                {"role": "Lily", "text": "Đúng thế! Bạn hãy upload file hoặc chọn các ghi chú làm nguồn để chúng ta bắt đầu buổi thảo luận nhé."}
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
        dialogue.append({"role": "Dan", "text": "Xin chào mọi người! Chào mừng đến với bản tóm tắt Audio Overview ngày hôm nay. Tôi là Dan."})
        dialogue.append({"role": "Lily", "text": "Còn tôi là Lily! Hôm nay chúng ta có một tập tài liệu cực kỳ thú vị thuộc các nguồn: " + sources_str + "."})
        dialogue.append({"role": "Dan", "text": "Đúng thế! Hãy bắt đầu với nội dung quan trọng đầu tiên. Tài liệu có đề cập đến: '" + chunks[0].text[:120] + "...'"})
        dialogue.append({"role": "Lily", "text": "Ồ, tôi thấy phần này rất hay. Nó làm rõ luận điểm: '" + (chunks[0].text[120:260] if len(chunks[0].text) > 120 else chunks[0].text) + "'. Nó giải thích tại sao mọi thứ hoạt động như vậy."})
        
        if len(chunks) > 1:
            dialogue.append({"role": "Dan", "text": "Chính xác! Chưa hết đâu, ở nguồn " + chunks[1].source + ", chúng ta còn thấy thông tin về: '" + chunks[1].text[:130] + "...'"})
            dialogue.append({"role": "Lily", "text": "Đúng vậy, điều này liên kết chặt chẽ với những gì được nói sau đó: '" + (chunks[1].text[130:260] if len(chunks[1].text) > 130 else chunks[1].text) + "'. Nó giúp giải quyết một bài toán rất thực tế."})

        if len(chunks) > 2:
            dialogue.append({"role": "Dan", "text": "Đặc biệt là nội dung này: '" + chunks[2].text[:130] + "...'"})
            dialogue.append({"role": "Lily", "text": "Tôi đồng ý! Việc hiểu được '" + (chunks[2].text[130:250] if len(chunks[2].text) > 130 else chunks[2].text) + "' thực sự là chìa khóa mở ra bức tranh toàn cảnh."})

        dialogue.append({"role": "Dan", "text": "Tóm lại, tài liệu này giúp chúng ta có một cái nhìn sâu sắc và có hệ thống về vấn đề."})
        dialogue.append({"role": "Lily", "text": "Hoàn toàn đồng ý. Cảm ơn các bạn đã lắng nghe. Hẹn gặp lại trong bản tin Audio Overview tiếp theo!"})
        
        return dialogue

    def generate_quiz(self, allowed_sources: Optional[List[str]] = None) -> List[Dict]:
        chunks = self.retrieve(
            "khái niệm quan trọng, định nghĩa, số liệu, kết luận chính",
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
                    "question": "Bạn cần upload tài liệu trước khi tạo quiz. Hành động nào sau đúng?",
                    "options": [
                        "Upload PDF/DOCX/TXT ở panel Sources",
                        "Đóng trình duyệt",
                        "Xóa notebook",
                        "Không cần làm gì",
                    ],
                    "answer_idx": 0,
                    "explanation": "Hãy upload ít nhất một tài liệu để hệ thống trích xuất nội dung và tạo câu hỏi tự động.",
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
            options1.append(f"Khái niệm bổ trợ {len(options1)}")
        import random
        # Store original term to find its index after shuffling
        correct_term = t1
        random.shuffle(options1)
        ans_idx1 = options1.index(correct_term)
        
        quiz.append({
            "question": f"Thuật ngữ nào sau đây được định nghĩa là: '{d1}'? (Nguồn: {s1})",
            "options": options1,
            "answer_idx": ans_idx1,
            "explanation": f"Theo tài liệu nguồn {s1}, '{correct_term}' chính là: {d1}."
        })

        # Question 2: Definition of term 2
        if len(defs) > 1:
            t2, d2, s2 = defs[1]
            options2 = [d2]
            for _, d, _ in defs[2:5]:
                options2.append(d)
            while len(options2) < 4:
                options2.append(f"Định nghĩa bổ trợ khác {len(options2)}")
            correct_def = d2
            random.shuffle(options2)
            ans_idx2 = options2.index(correct_def)
            
            quiz.append({
                "question": f"Theo tài liệu, khái niệm '{t2}' được giải thích như thế nào? (Nguồn: {s2})",
                "options": options2,
                "answer_idx": ans_idx2,
                "explanation": f"Trong tài liệu {s2}, thuật ngữ '{t2}' có nghĩa là: {correct_def}."
            })

        # Question 3: T/F or Fill in blank style
        if len(defs) > 2:
            t3, d3, s3 = defs[2]
            quiz.append({
                "question": f"Khẳng định sau đây Đúng hay Sai: '{t3} là {d3}'? (Nguồn: {s3})",
                "options": ["Đúng", "Sai"],
                "answer_idx": 0,
                "explanation": f"Khẳng định này hoàn toàn chính xác theo thông tin ghi trong nguồn {s3}."
            })
            
        return quiz

    def generate_flashcards(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        chunks = self.retrieve(
            "thuật ngữ, khái niệm, định nghĩa quan trọng",
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
                {"front": "RAG", "back": "Retrieval-Augmented Generation — truy vấn tài liệu rồi sinh câu trả lời dựa trên nguồn."},
                {"front": "Embedding", "back": "Vector số học biểu diễn ý nghĩa của một đoạn văn bản."},
                {"front": "Chunk", "back": "Đoạn văn bản nhỏ được tách từ tài liệu gốc để lập chỉ mục."},
                {"front": "FAISS", "back": "Thư viện tìm kiếm vector tương đồng hiệu năng cao."},
            ]
        return [{"front": item[0], "back": f"{item[1]} (Nguồn: {item[2]})"} for item in defs[:8]]

    def generate_slide_deck(self, allowed_sources: Optional[List[str]] = None) -> List[Dict]:
        chunks = self.retrieve("khái niệm cốt lõi, tổng quan, kết luận", top_k=4, allowed_sources=allowed_sources)
        if not chunks:
            return [
                {"title": "Giới thiệu Slide Deck", "points": ["Chưa chọn tài liệu nguồn.", "Hãy tải tệp tin lên để hệ thống phân tích nội dung.", "Slide deck giúp trực quan hóa tài liệu dưới dạng slide trình chiếu."]}
            ]

        slides = []
        slides.append({
            "title": "Slide 1: Tổng quan chủ đề",
            "points": [
                f"Được biên soạn từ tài liệu: {', '.join(list({c.source for c in chunks}))}",
                "Trình bày các khía cạnh cốt lõi và kết quả phân tích cấu trúc.",
                "Tập trung vào phân tích ngữ nghĩa và các định nghĩa quan trọng."
            ]
        })
        
        for i, chunk in enumerate(chunks[:3]):
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk.text) if len(s.strip()) > 15]
            points = sentences[:3] if len(sentences) >= 3 else [chunk.text[:120], chunk.text[120:240]]
            slides.append({
                "title": f"Slide {i+2}: Phân tích chi tiết - {chunk.source}",
                "points": points
            })
            
        slides.append({
            "title": "Slide Cuối: Tóm tắt & Hành động",
            "points": [
                "Nắm vững các định nghĩa và thuật ngữ cốt lõi đã nêu.",
                "Sử dụng các nguồn tài liệu tham khảo để đối chiếu thực tế.",
                "Hỏi đáp trực tiếp thông qua Chatbot để hiểu sâu hơn."
            ]
        })
        return slides

    def generate_mind_map(self, allowed_sources: Optional[List[str]] = None) -> Dict[str, str]:
        chunks = self.retrieve(
            "chủ đề chính, cấu trúc nội dung, các nhánh khái niệm",
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
        root = str(data.get("root", "Tài liệu")).strip() or "Tài liệu"
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
                "- **Hệ thống RAG NotebookLM**\n"
                "  - **Nguồn tài liệu**\n"
                "    - Upload PDF / DOCX / TXT\n"
                "  - **Xử lý**\n"
                "    - Chunk văn bản\n"
                "    - Embedding + FAISS\n"
                "  - **Tương tác**\n"
                "    - Chat hỏi đáp\n"
                "    - Studio tools"
            )
            mermaid = (
                "graph TD\n"
                "  Root[RAG Notebook] --> Sources[Nguồn tài liệu]\n"
                "  Root --> Process[Xử lý]\n"
                "  Root --> Chat[Chat]\n"
                "  Sources --> Upload[Upload file]\n"
                "  Process --> Chunk[Chunk]\n"
                "  Process --> Emb[Embedding]\n"
                "  Process --> Vec[FAISS Index]\n"
                "  Chat --> Retrieve[Truy vấn ngữ nghĩa]\n"
                "  Chat --> Answer[Sinh câu trả lời]"
            )
            return {"markdown": markdown_map, "mermaid": mermaid}

        # Build custom map
        source_names = list({item[2] for item in defs})
        markdown_map = f"- **Nội dung từ {', '.join(source_names)}**\n"
        mermaid = "graph TD\n"
        mermaid += f"  Root[\"Tài liệu nguồn: {source_names[0]}\"]\n"
        
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
        chunks = self.retrieve("kết quả, phân tích, kết luận, kiến nghị", top_k=4, allowed_sources=allowed_sources)
        if not chunks:
            return "### Báo cáo Tổng quan\n\nChưa chọn nguồn tài liệu nào. Vui lòng chọn hoặc tải tài liệu lên."

        report = f"# Báo cáo nghiên cứu & Hướng dẫn học tập\n\n**Các nguồn tài liệu phân tích:** {', '.join(list({c.source for c in chunks}))}\n\n---\n\n"
        report += "## 1. Tóm tắt điều hành (Executive Summary)\n"
        report += "Tài liệu cung cấp các khái niệm nền tảng quan trọng. Qua phân tích nội dung, chúng ta rút ra các luận điểm chính sau:\n\n"
        for chunk in chunks[:2]:
            report += f"- **Thông tin từ {chunk.source}**: {chunk.text[:220]}...\n"
            
        report += "\n## 2. Các khái niệm cốt lõi (Key Concepts)\n"
        defs = self._extract_definitions(allowed_sources)
        if defs:
            for term, definition, src in defs[:5]:
                report += f"- **{term}** (Nguồn: *{src}*): {definition}\n"
        else:
            report += "Không trích xuất được khái niệm tự động. Hãy tra cứu thêm trong tài liệu.\n"
            
        report += "\n## 3. Câu hỏi thường gặp (FAQ)\n"
        if defs:
            for i, (term, definition, src) in enumerate(defs[:3]):
                report += f"**Q{i+1}: {term} được hiểu như thế nào?**\n"
                report += f"*Trả lời:* Theo tài liệu nguồn *{src}*, {definition}\n\n"
        else:
            report += "**Q1: Nội dung chính của tài liệu là gì?**\n*Trả lời:* Tài liệu tập trung giải quyết các bài toán về tối ưu và cấu trúc thông tin trong hệ thống.\n"

        report += "\n## 4. Hướng dẫn ôn tập & Đánh giá học phần\n"
        report += "1. Đọc kỹ các phần định nghĩa khái niệm và đối chiếu với ví dụ thực tế.\n"
        report += "2. Trả lời các câu hỏi trắc nghiệm trong phần Studio để tự đánh giá mức độ hiểu bài.\n"
        report += "3. Sử dụng Flashcards để ghi nhớ nhanh các thuật ngữ chính.\n"
        
        return report

    def generate_video_overview(self, allowed_sources: Optional[List[str]] = None) -> str:
        chunks = self.retrieve("tóm tắt, giới thiệu, tổng quan", top_k=3, allowed_sources=allowed_sources)
        if not chunks:
            return "### Video Storyboard\n\nChưa chọn nguồn tài liệu nào. Vui lòng chọn hoặc tải tài liệu lên."

        storyboard = "# Video Overview: Storyboard & Kịch bản chi tiết\n\n"
        storyboard += f"**Tài liệu phân tích:** {', '.join(list({c.source for c in chunks}))}\n"
        storyboard += "**Thời lượng dự kiến:** 2 phút | **Mục tiêu:** Giới thiệu ngắn gọn các ý tưởng cốt lõi của tài liệu.\n\n---\n\n"
        
        storyboard += "### Phân cảnh 1: Giới thiệu (0:00 - 0:30)\n"
        storyboard += "- **Hình ảnh trực quan:** Đồ họa giới thiệu tiêu đề tài liệu xuất hiện kèm các biểu tượng sách và công nghệ liên kết.\n"
        storyboard += "- **Âm thanh nền:** Nhạc acoustic nhẹ nhàng, truyền cảm hứng.\n"
        storyboard += f"- **Lời thoại người dẫn (Voiceover):** \"Chào các bạn! Hôm nay chúng ta sẽ cùng khám phá tài liệu quan trọng nói về chủ đề này. Dựa trên các nguồn tư liệu được lưu trữ, hãy cùng điểm qua các ý chính nhé.\"\n\n"
        
        storyboard += "### Phân cảnh 2: Ý chính và Chi tiết (0:30 - 1:30)\n"
        storyboard += "- **Hình ảnh trực quan:** Văn bản trích dẫn nổi bật trên nền tối kèm hình minh họa sơ đồ:\n"
        if chunks:
            storyboard += f"  > *\"{chunks[0].text[:120]}...\"*\n"
        storyboard += "- **Lời thoại người dẫn:** \"Điểm cốt lõi đầu tiên chính là nội dung này. Nó giải thích rõ cấu trúc và phương pháp tiếp cận chủ đề một cách khoa học.\"\n\n"
        
        storyboard += "### Phân cảnh 3: Kết luận & Kêu gọi hành động (1:30 - 2:00)\n"
        storyboard += "- **Hình ảnh trực quan:** Logo của ứng dụng NotebookLM, tóm tắt các điểm đáng nhớ xuất hiện dạng checklist.\n"
        storyboard += "- **Lời thoại người dẫn:** \"Đó là tóm tắt nhanh về tài liệu này. Bạn có thể sử dụng các công cụ đính kèm như Quiz, Flashcards trong Studio để đào sâu kiến thức hơn nữa. Hẹn gặp lại các bạn!\"\n"
        
        return storyboard

    def generate_infographic(self, allowed_sources: Optional[List[str]] = None) -> str:
        defs = self._extract_definitions(allowed_sources)
        chunks = self.retrieve("số lượng, phần trăm, thống kê, quan trọng", top_k=3, allowed_sources=allowed_sources)
        
        info = "# Infographic Blueprint: Thiết kế trực quan tài liệu\n\n"
        info += "Bản thiết kế này chỉ ra cách bố cục thông tin trực quan nhất cho tài liệu của bạn.\n\n---\n\n"
        
        info += "## 🎨 Tông màu chủ đạo\n"
        info += "- **Chủ đạo:** Xanh navy tối (#0b1220) mang cảm giác tri thức và hiện đại.\n"
        info += "- **Nhấn mạnh:** Đỏ san hô (#ef4444) hoặc Hổ phách để highlight thông tin quan trọng.\n\n"
        
        info += "## 📊 Bố cục 3 phần chính (3-Block Layout)\n\n"
        info += "### Block 1: Khái niệm nền tảng (Đặt ở trên cùng)\n"
        if defs:
            t, d, s = defs[0]
            info += f"- **Tiêu điểm:** {t}\n"
            info += f"- **Mô tả trực quan:** Đặt trong khung tròn trung tâm. Định nghĩa ngắn: \"*{d[:80]}...*\"\n"
        else:
            info += "- **Tiêu điểm:** Tổng quan lý thuyết RAG & Data Mining.\n"
            
        info += "\n### Block 2: Số liệu & Phân tích chi tiết (Đặt ở giữa)\n"
        stats = self.get_stats()
        info += f"- **Chỉ số 1:** {stats['documents']} tài liệu nguồn được tích hợp.\n"
        info += f"- **Chỉ số 2:** {stats['chunks']} phân đoạn thông tin (Chunks) được băm nhỏ.\n"
        info += f"- **Chỉ số 3:** Trung bình {stats['avg_chunk_length']} từ trên mỗi phân đoạn.\n"
        
        info += "\n### Block 3: Ý nghĩa ứng dụng (Đặt ở dưới cùng)\n"
        if len(chunks) > 0:
            info += f"- **Trích dẫn đắt giá:** \"{chunks[0].text[:120]}...\"\n"
        info += "- **Hành động:** Sử dụng kiến thức này để giải quyết các bài toán phân tích liên quan.\n"
        
        return info

    def generate_data_table(self, allowed_sources: Optional[List[str]] = None) -> List[Dict[str, str]]:
        defs = self._extract_definitions(allowed_sources)
        if not defs:
            return [
                {"Thuật ngữ": "RAG", "Mô tả": "Truy vấn tài liệu và sinh câu trả lời có trích dẫn nguồn.", "Nguồn": "Hệ thống"},
                {"Thuật ngữ": "Embedding", "Mô tả": "Biểu diễn vector của văn bản để tìm kiếm ngữ nghĩa.", "Nguồn": "Hệ thống"},
                {"Thuật ngữ": "FAISS", "Mô tả": "Chỉ mục vector cho truy vấn nhanh.", "Nguồn": "Hệ thống"},
            ]
        return [{"Thuật ngữ": term, "Mô tả": definition, "Nguồn": src} for term, definition, src in defs]


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
            return {"ok": False, "error": "Chưa có chunks — hãy upload tài liệu"}
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
                "message": "Chưa có knowledge graph — bấm Build Graph",
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
            return "Chưa có knowledge graph. Hãy Build Graph trước.", []
        key = normalize_entity_key(entity_id)
        if key not in self.knowledge_graph.entities and entity_id not in self.knowledge_graph.entities:
            # try label match
            for k, ent in self.knowledge_graph.entities.items():
                if normalize_entity_key(ent.name) == key or ent.name.lower() == entity_id.lower():
                    key = k
                    break
            else:
                return f"Không tìm thấy entity «{entity_id}» trong graph.", []
        chunk_ids = sorted(self.knowledge_graph.entity_to_chunks.get(key, set()))
        if not chunk_ids:
            return f"Entity «{entity_id}» chưa liên kết chunk nào.", []
        label = self.knowledge_graph.entities[key].name
        q = (question or "").strip() or f"Giải thích khái niệm «{label}» dựa trên tài liệu."
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
