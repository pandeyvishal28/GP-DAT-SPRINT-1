"""
utils/doc_extractor.py
Lightweight plain-text extraction from PDF, DOCX, and TXT files.

Used only for extracting GWP guidance text and similar auxiliary content.
Full PDF → DOCX conversion is handled by services/pdf_converter.py.
In-DOCX translation is handled by services/translation_service.py.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("utils.doc_extractor")


def extract_text_plain(content_bytes: bytes, filename: str) -> str:
    """
    Extract plain text from a file's raw bytes.

    Supports:
      - .pdf  → pdfplumber page-by-page extraction
      - .docx → python-docx paragraph text
      - .txt  → UTF-8 decode (BOM-safe, latin-1 fallback)

    Args:
        content_bytes: Raw bytes of the file.
        filename: Original filename (used to detect extension).

    Returns:
        Extracted plain text as a string.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _extract_pdf_text(content_bytes)
    if ext == "docx":
        return _extract_docx_text(content_bytes)
    # Default: treat as plain text
    return _decode_text(content_bytes)


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using pdfplumber."""
    import io
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    return "\n\n".join(pages)


def _extract_docx_text(data: bytes) -> str:
    """Extract text from a DOCX using python-docx."""
    import io
    from docx import Document

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _decode_text(data: bytes) -> str:
    """Decode plain text bytes with BOM-safe UTF-8 and latin-1 fallback."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")
