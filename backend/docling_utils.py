"""Docling converter helpers with OCR for scanned/image PDFs."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Optional

import PyPDF2

OCR_LANGS = os.getenv("RAG_OCR_LANGS", "en,vi").split(",")
# Avg chars/page below this → treat as scanned and force full-page OCR
OCR_CHAR_THRESHOLD_PER_PAGE = int(os.getenv("RAG_OCR_CHAR_THRESHOLD", "80"))


def pdf_text_stats(content: bytes) -> tuple[int, int]:
    """Return (page_count, non-whitespace character count from PyPDF2)."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        pages = max(len(reader.pages), 1)
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                texts.append("")
        chars = len("".join(texts).strip())
        return pages, chars
    except Exception:
        return 1, 0


def pdf_needs_full_ocr(content: bytes) -> bool:
    pages, chars = pdf_text_stats(content)
    return chars < pages * OCR_CHAR_THRESHOLD_PER_PAGE


def build_docling_converter(force_full_page_ocr: bool = False):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    try:
        import torch

        use_gpu = torch.cuda.is_available()
    except Exception:
        use_gpu = False

    ocr_options = EasyOcrOptions(
        lang=[lang.strip() for lang in OCR_LANGS if lang.strip()],
        use_gpu=use_gpu,
    )
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=ocr_options,
    )
    if force_full_page_ocr and hasattr(pipeline_options, "force_full_page_ocr"):
        pipeline_options.force_full_page_ocr = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def convert_file_with_docling(path: str, force_full_page_ocr: bool = False) -> str:
    converter = build_docling_converter(force_full_page_ocr=force_full_page_ocr)
    result = converter.convert(path)
    return result.document.export_to_markdown() or ""


def convert_bytes_with_docling(content: bytes, suffix: str, force_full_page_ocr: bool = False) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return convert_file_with_docling(tmp_path, force_full_page_ocr=force_full_page_ocr)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
