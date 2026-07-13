"""LLM-based answer synthesis with structured Vietnamese prompts."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .rag_config import GENERATION_MODEL_NAME, GENERATION_TEMPERATURE, MAX_NEW_TOKENS

load_dotenv()

logger = logging.getLogger(__name__)

# Module-level singleton — loaded once at startup via get_synthesizer()
_SYNTHESIZER: Optional["AnswerSynthesizer"] = None


def get_synthesizer() -> "AnswerSynthesizer":
    global _SYNTHESIZER
    if _SYNTHESIZER is None:
        _SYNTHESIZER = AnswerSynthesizer()
    return _SYNTHESIZER


def load_synthesizer_eager() -> "AnswerSynthesizer":
    """Force-load the LLM weights now (call once at startup)."""
    synth = get_synthesizer()
    if synth.use_api:
        logger.info("Using Gemini API for synthesis.")
        return synth
    logger.info("Loading generation model: %s", GENERATION_MODEL_NAME)
    synth.load()
    logger.info("Generation model loaded.")
    return synth


def _parse_json_block(text: str) -> Optional[Any]:
    """Best-effort extraction of a JSON array/object from raw LLM output."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip("` \n")
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    starts = [i for i in (cleaned.find("["), cleaned.find("{")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    opener = cleaned[start]
    closer = "]" if opener == "[" else "}"
    end = cleaned.rfind(closer)
    if end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None

_SYSTEM_PROMPT = """Bạn là trợ lý nghiên cứu chuyên nghiệp. Trả lời câu hỏi DỰA TRÊN các đoạn trích từ tài liệu.

Quy tắc bắt buộc:
- Chỉ dùng thông tin có trong nguồn trích dẫn [1], [2], ...
- Gắn [số] sau mỗi ý quan trọng để trích dẫn nguồn
- Viết tiếng Việt tự nhiên, mạch lạc, có cấu trúc (mở đầu → chi tiết → kết luận nếu phù hợp)
- Nếu tài liệu không đủ thông tin, nói rõ phần nào chưa có
- Không bịa đặt, không lặp lại câu hỏi"""


class AnswerSynthesizer:
    def __init__(self) -> None:
        self.tokenizer: Optional[AutoTokenizer] = None
        self.model: Optional[AutoModelForCausalLM] = None
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.use_api = bool(self.gemini_api_key)
        self.client = None
        if self.use_api:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.gemini_api_key,
                base_url=self.gemini_base_url,
            )

    def load(self) -> None:
        if self.use_api:
            return
        if self.model is not None and self.tokenizer is not None:
            return
        self.tokenizer = AutoTokenizer.from_pretrained(GENERATION_MODEL_NAME, trust_remote_code=True)
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            GENERATION_MODEL_NAME,
            dtype=dtype,
            trust_remote_code=True,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(device)
        self.model.eval()

    def _build_context(self, chunks: Sequence[Tuple[str, str]]) -> str:
        parts: List[str] = []
        for idx, (source, text) in enumerate(chunks, start=1):
            parts.append(f"[{idx}] ({source})\n{text}")
        return "\n\n".join(parts)

    @staticmethod
    def _build_history_block(history: Optional[Sequence[dict]]) -> str:
        if not history:
            return ""
        turns = []
        for turn in history[-3:]:
            q = str(turn.get("query", "")).strip()
            a = str(turn.get("answer", "")).strip()
            if q and a:
                turns.append(f"Người dùng: {q}\nTrợ lý: {a}")
        if not turns:
            return ""
        return "## Lịch sử hội thoại gần đây\n" + "\n\n".join(turns) + "\n\n"

    def _build_answer_prompt(
        self,
        query: str,
        chunks: Sequence[Tuple[str, str]],
        brief: bool,
        extra_context: str,
        history: Optional[Sequence[dict]],
    ) -> str:
        context = self._build_context(chunks)
        style = "Trả lời ngắn gọn, 2-4 câu." if brief else "Trả lời đầy đủ, chi tiết nhưng súc tích."
        global_block = ""
        if extra_context.strip():
            global_block = f"## Bối cảnh tổng quan (Graph RAG)\n{extra_context.strip()}\n\n"
        history_block = self._build_history_block(history)
        user_prompt = (
            f"{style}\n\n"
            f"{history_block}"
            f"{global_block}"
            f"## Nguồn tài liệu\n{context}\n\n"
            f"## Câu hỏi\n{query}\n\n"
            "## Trả lời"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def _build_answer_prompt(
        self,
        query: str,
        chunks: Sequence[Tuple[str, str]],
        brief: bool,
        extra_context: str,
        history: Optional[Sequence[dict]],
    ) -> str:
        messages = self._build_api_messages(query, chunks, brief, extra_context, history)
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    def synthesize(
        self,
        query: str,
        chunks: Sequence[Tuple[str, str]],
        brief: bool = False,
        extra_context: str = "",
        history: Optional[Sequence[dict]] = None,
    ) -> str:
        if self.use_api:
            messages = self._build_api_messages(query, chunks, brief, extra_context, history)
            try:
                response = self.client.chat.completions.create(
                    model=self.gemini_model,
                    messages=messages,
                    max_tokens=MAX_NEW_TOKENS if not brief else 180,
                    temperature=GENERATION_TEMPERATURE,
                )
                answer = response.choices[0].message.content.strip()
                return self._clean_answer(answer)
            except Exception as e:
                logger.error(f"Error calling Gemini API in synthesize: {e}")
                if not (self.model and self.tokenizer):
                    raise e

        self.load()
        assert self.tokenizer is not None and self.model is not None

        prompt = self._build_answer_prompt(query, chunks, brief, extra_context, history)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=3072)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS if not brief else 180,
                temperature=GENERATION_TEMPERATURE,
                do_sample=GENERATION_TEMPERATURE > 0,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[1]:]
        answer = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return self._clean_answer(answer)

    def synthesize_stream(
        self,
        query: str,
        chunks: Sequence[Tuple[str, str]],
        brief: bool = False,
        extra_context: str = "",
        history: Optional[Sequence[dict]] = None,
    ):
        """Yield answer text incrementally as the model generates it."""
        if self.use_api:
            messages = self._build_api_messages(query, chunks, brief, extra_context, history)
            try:
                response = self.client.chat.completions.create(
                    model=self.gemini_model,
                    messages=messages,
                    max_tokens=MAX_NEW_TOKENS if not brief else 180,
                    temperature=GENERATION_TEMPERATURE,
                    stream=True,
                )
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
                return
            except Exception as e:
                logger.error(f"Error calling Gemini API stream in synthesize_stream: {e}")
                if not (self.model and self.tokenizer):
                    raise e

        from threading import Thread

        from transformers import TextIteratorStreamer

        self.load()
        assert self.tokenizer is not None and self.model is not None

        prompt = self._build_answer_prompt(query, chunks, brief, extra_context, history)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=3072)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = dict(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS if not brief else 180,
            temperature=GENERATION_TEMPERATURE,
            do_sample=GENERATION_TEMPERATURE > 0,
            top_p=0.9,
            repetition_penalty=1.1,
            pad_token_id=self.tokenizer.eos_token_id,
            streamer=streamer,
        )
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs, daemon=True)
        thread.start()
        try:
            for piece in streamer:
                if piece:
                    yield piece
        finally:
            thread.join(timeout=1)

    @staticmethod
    def _clean_answer(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^(Trả lời|Answer)\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def summarize(self, chunks: Sequence[Tuple[str, str]]) -> str:
        if not chunks:
            return ""
        context = self._build_context(chunks)
        user_prompt = (
            "Tóm tắt nội dung chính của các đoạn trích sau. "
            "Nêu các ý chính, khái niệm quan trọng và kết luận nếu có.\n\n"
            f"{context}"
        )
        system = "Bạn là trợ lý tóm tắt tài liệu. Viết tiếng Việt, súc tích, có cấu trúc."
        return self._generate(system, user_prompt, max_new_tokens=280)

    def _generate(self, system: str, user: str, max_new_tokens: int = 320) -> str:
        if self.use_api:
            try:
                response = self.client.chat.completions.create(
                    model=self.gemini_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_new_tokens,
                    temperature=GENERATION_TEMPERATURE,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Error calling Gemini API in _generate: {e}")
                if not (self.model and self.tokenizer):
                    raise e

        self.load()
        assert self.tokenizer is not None and self.model is not None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=3072)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=GENERATION_TEMPERATURE,
                do_sample=GENERATION_TEMPERATURE > 0,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = outputs[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()

    def extract_graph_from_text(self, text: str) -> str:
        system = (
            "Bạn trích xuất đồ thị tri thức từ văn bản. "
            "Chỉ trả về danh sách, mỗi dòng một mục, đúng định dạng."
        )
        user = (
            "Trích xuất thực thể và quan hệ quan trọng.\n"
            "Định dạng:\n"
            "ENTITY: tên | loại\n"
            "RELATION: thực_thể_1 | quan_hệ | thực_thể_2\n\n"
            f"Văn bản:\n{text[:5500]}"
        )
        return self._generate(system, user, max_new_tokens=400)

    def summarize_community(self, entity_names: Sequence[str], chunk_texts: Sequence[str]) -> str:
        entities = ", ".join(entity_names[:10]) or "không rõ"
        combined = "\n\n".join(chunk_texts[:4])[:4000]
        system = "Tóm tắt một cụm khái niệm trong tài liệu. Viết tiếng Việt, 3-5 câu, súc tích."
        user = f"Thực thể: {entities}\n\nĐoạn văn:\n{combined}"
        return self._generate(system, user, max_new_tokens=220)

    def generate_quiz(self, chunks: Sequence[Tuple[str, str]], n: int = 4) -> List[dict]:
        context = self._build_context(chunks)
        system = (
            "Bạn là trợ lý tạo câu hỏi trắc nghiệm (quiz) bằng tiếng Việt dựa CHÍNH XÁC trên tài liệu "
            "được cung cấp. Chỉ trả về JSON hợp lệ, không thêm bất kỳ chữ nào khác."
        )
        user = (
            f"Dựa trên các đoạn trích tài liệu dưới đây, hãy tạo {n} câu hỏi trắc nghiệm 4 đáp án "
            "để kiểm tra mức độ hiểu bài. Mỗi câu chỉ có 1 đáp án đúng, các đáp án sai phải hợp lý "
            "(không quá dễ đoán). Trả lời DUY NHẤT một mảng JSON đúng định dạng sau, không giải thích thêm:\n"
            '[{"question": "...", "options": ["...", "...", "...", "..."], '
            '"answer_idx": 0, "explanation": "...", "source": "tên nguồn"}]\n\n'
            f"## Tài liệu\n{context}"
        )
        raw = self._generate(system, user, max_new_tokens=1024)
        data = _parse_json_block(raw)
        if not isinstance(data, list):
            raise ValueError("LLM did not return a JSON quiz array")
        cleaned: List[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            options = item.get("options")
            if not isinstance(options, list) or len(options) < 2:
                continue
            try:
                answer_idx = int(item.get("answer_idx", 0))
            except (TypeError, ValueError):
                answer_idx = 0
            if not 0 <= answer_idx < len(options):
                answer_idx = 0
            cleaned.append(
                {
                    "question": str(item.get("question", "")).strip(),
                    "options": [str(o) for o in options],
                    "answer_idx": answer_idx,
                    "explanation": str(item.get("explanation", "")).strip(),
                    "source": str(item.get("source", "")).strip(),
                }
            )
        if not cleaned:
            raise ValueError("LLM quiz JSON had no usable items")
        return cleaned

    def generate_flashcards(self, chunks: Sequence[Tuple[str, str]], n: int = 8) -> List[dict]:
        context = self._build_context(chunks)
        system = (
            "Bạn tạo flashcard (thẻ ghi nhớ) thuật ngữ/khái niệm bằng tiếng Việt dựa trên tài liệu. "
            "Chỉ trả về JSON hợp lệ."
        )
        user = (
            f"Trích xuất tối đa {n} thuật ngữ/khái niệm quan trọng nhất trong tài liệu sau và định nghĩa "
            "ngắn gọn cho từng thuật ngữ. Trả lời DUY NHẤT một mảng JSON đúng định dạng:\n"
            '[{"front": "Thuật ngữ", "back": "Định nghĩa ngắn gọn", "source": "tên nguồn"}]\n\n'
            f"## Tài liệu\n{context}"
        )
        raw = self._generate(system, user, max_new_tokens=800)
        data = _parse_json_block(raw)
        if not isinstance(data, list):
            raise ValueError("LLM did not return a JSON flashcard array")
        cleaned = [
            {
                "front": str(item.get("front", "")).strip(),
                "back": str(item.get("back", "")).strip(),
                "source": str(item.get("source", "")).strip(),
            }
            for item in data
            if isinstance(item, dict) and item.get("front") and item.get("back")
        ]
        if not cleaned:
            raise ValueError("LLM flashcard JSON had no usable items")
        return cleaned

    def generate_audio_dialogue(self, chunks: Sequence[Tuple[str, str]]) -> List[dict]:
        context = self._build_context(chunks)
        system = (
            "Bạn viết kịch bản podcast tiếng Việt giữa hai người dẫn chương trình tên Dan và Lily, "
            "thảo luận sôi nổi, tự nhiên về nội dung tài liệu. Chỉ trả về JSON hợp lệ."
        )
        user = (
            "Viết một đoạn hội thoại podcast (8-10 lượt thoại, xen kẽ Dan/Lily) tóm tắt và thảo luận "
            "các ý chính trong tài liệu dưới đây. Giọng văn tự nhiên, hào hứng, có mở đầu chào hỏi và "
            "kết luận cảm ơn người nghe. Trả lời DUY NHẤT một mảng JSON đúng định dạng:\n"
            '[{"role": "Dan", "text": "..."}, {"role": "Lily", "text": "..."}]\n\n'
            f"## Tài liệu\n{context}"
        )
        raw = self._generate(system, user, max_new_tokens=1200)
        data = _parse_json_block(raw)
        if not isinstance(data, list):
            raise ValueError("LLM did not return a JSON dialogue array")
        cleaned = [
            {"role": str(item.get("role", "Dan")).strip() or "Dan", "text": str(item.get("text", "")).strip()}
            for item in data
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        if len(cleaned) < 2:
            raise ValueError("LLM dialogue JSON too short")
        return cleaned

    def generate_mindmap(self, chunks: Sequence[Tuple[str, str]]) -> dict:
        context = self._build_context(chunks)
        system = (
            "Bạn tạo sơ đồ tư duy (mind map) từ tài liệu. Chỉ trả về JSON hợp lệ, không giải thích thêm."
        )
        user = (
            "Phân tích tài liệu sau và tạo cấu trúc mind map với 1 chủ đề gốc và 3-6 nhánh con, "
            "mỗi nhánh có thể có 0-3 nhánh cháu. Trả lời DUY NHẤT JSON đúng định dạng:\n"
            '{"root": "Chủ đề chính", "branches": [{"label": "Nhánh 1", "children": ["ý con 1", "ý con 2"]}]}\n\n'
            f"## Tài liệu\n{context}"
        )
        raw = self._generate(system, user, max_new_tokens=700)
        data = _parse_json_block(raw)
        if not isinstance(data, dict) or not data.get("root") or not data.get("branches"):
            raise ValueError("LLM did not return a valid mindmap JSON")
        return data
