"""
services/docling_parser.py
Utility service wrapping IBM Docling to parse legacy PDF files
into structured, formatting-preserved Markdown optimized for LLM comprehension.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DoclingParser:
    """Helper to parse PDFs into rich Markdown format using IBM Docling."""

    def __init__(self) -> None:
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            
            # Disable external OCR to prevent the system from hitting the firewall
            # (which causes SSL cert verification errors through the corporate proxy).
            # We rely strictly on the native digital text layer of the PDF instead.
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        except ImportError:
            logger.error("docling is not installed. Run: pip install docling")
            self._converter = None

    def parse_to_markdown(self, file_path: Path | str) -> str:
        """
        Convert a PDF document directly into Markdown format,
        extracting complex layouts, reading order, and native tables.
        
        Args:
            file_path: Path to the target PDF file.
            
        Returns:
            str: Rich Markdown string formatted identically to the document's flow.
            
        Raises:
            FileNotFoundError: If the PDF does not exist.
            RuntimeError: If Docling is not installed or conversion fails.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        if not self._converter:
            raise RuntimeError("docling module is not available. Please install 'docling'.")

        logger.info("Parsing document with Docling: %s", path.name)

        try:
            # the convert function evaluates the PDF and outputs a representation with tables
            result = self._converter.convert(str(path))
            
            # extract into clean markdown with default styling preserved
            markdown_text = result.document.export_to_markdown()
            
            logger.info("Successfully parsed %s to Markdown (%d chars).", path.name, len(markdown_text))
            return markdown_text
            
        except Exception as exc:
            logger.exception("Error converting document using Docling: %s", exc)
            raise RuntimeError(f"Docling conversion failed: {exc}") from exc
