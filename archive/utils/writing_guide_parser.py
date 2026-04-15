"""
utils/writing_guide_parser.py
Extracts text content from writing guide files (.txt, .md, .docx, .pdf).

Output is always a UTF-8 string (Markdown-formatted where possible)
ready for LLM prompt injection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Supported extensions and their handler names (for error messages)
_SUPPORTED_EXTENSIONS: set[str] = {".txt", ".md", ".docx", ".doc", ".pdf"}


class ParsingError(Exception):
    """Raised when a file cannot be parsed."""


# ── Public API ──────────────────────────────────────────────────────────────


def extract_text(file_path: Path) -> str:
    """
    Extract text content from a writing guide file.

    Parameters
    ----------
    file_path : Path
        Absolute or relative path to the source file.

    Returns
    -------
    str
        Extracted content as a UTF-8 string (Markdown where applicable).

    Raises
    ------
    ParsingError
        If the file type is unsupported or extraction fails.
    FileNotFoundError
        If the file does not exist on disk.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.suffix.lower()

    if ext not in _SUPPORTED_EXTENSIONS:
        raise ParsingError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    handler = _HANDLERS.get(ext)
    if handler is None:
        raise ParsingError(f"No handler registered for '{ext}'")

    logger.info("Parsing writing guide file: %s (type=%s)", file_path.name, ext)
    return handler(file_path)


# ── Private handlers ────────────────────────────────────────────────────────


def _parse_text(file_path: Path) -> str:
    """Handle .txt and .md files — plain UTF-8 read."""
    return file_path.read_text(encoding="utf-8")


def _parse_docx(file_path: Path) -> str:
    """
    Handle .docx files using python-docx.

    Extracts paragraphs preserving basic structure:
    - Heading styles → Markdown headings
    - Normal paragraphs → plain text lines
    """
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ParsingError(
            "python-docx is required for .docx parsing. "
            "Install it with: pip install python-docx"
        ) from exc

    doc = Document(str(file_path))
    lines: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = (para.style.name or "").lower()

        # Map Word heading styles to Markdown headings
        if style_name.startswith("heading"):
            try:
                level = int(style_name.replace("heading", "").strip())
            except ValueError:
                level = 1
            lines.append(f"{'#' * level} {text}")
        else:
            lines.append(text)

    return "\n\n".join(lines)


def _parse_pdf(file_path: Path) -> str:
    """
    Handle .pdf files using pymupdf4llm.

    pymupdf4llm produces high-quality Markdown output
    preserving headings, lists, and basic formatting.
    """
    try:
        import pymupdf4llm  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ParsingError(
            "pymupdf4llm is required for .pdf parsing. "
            "Install it with: pip install pymupdf4llm"
        ) from exc

    try:
        md_text: str = pymupdf4llm.to_markdown(str(file_path))
        return md_text.strip()
    except Exception as exc:
        raise ParsingError(f"Failed to parse PDF '{file_path.name}': {exc}") from exc


# ── Handler registry ────────────────────────────────────────────────────────


_HANDLERS: dict[str, Callable[[Path], str]] = {
    ".txt": _parse_text,
    ".md": _parse_text,
    ".docx": _parse_docx,
    ".doc": _parse_docx,
    ".pdf": _parse_pdf,
}
