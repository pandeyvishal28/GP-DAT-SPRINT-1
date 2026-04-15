"""
services/template_service.py
Business logic for the Template Library.

Handles upload validation, file storage, blueprint parsing, and
delegates database access to TemplateRepository.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from repositories.template_repository import TemplateRepository

logger = logging.getLogger(__name__)

# Where uploaded .docx source files are kept (backup only)
_TEMPLATE_STORAGE_DIR = Path("data/templates")

# Allowed upload extensions
_ALLOWED_EXTENSIONS: set[str] = {".docx", ".doc"}


class TemplateService:
    """
    Template Library business logic.

    Responsibilities:
      - Validate uploaded files
      - Save .docx to disk (backup) and parse to Markdown
      - Store parsed content in the database via repository
      - CRUD operations with business rules
    """

    def __init__(self, repository: TemplateRepository) -> None:
        self._repo = repository

    # ── Upload ──────────────────────────────────────────────────────────

    def upload_template(
        self,
        file_bytes: bytes,
        filename: str,
        name: str,
        *,
        template_type: str = "Global",
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a template file, parse it to Markdown, and store in DB.

        Steps:
          1. Validate file extension
          2. Save .docx to data/templates/ (backup, needed for re-parse)
          3. Parse .docx → Markdown via template_parser
          4. Store Markdown content in the database

        Returns the new template record as a dict.
        """
        ext = Path(filename).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
            )

        # Generate unique ID
        short_id = uuid.uuid4().hex[:8]
        template_id = f"{Path(filename).stem.lower().replace(' ', '_')}_{short_id}"

        # Save .docx to disk (backup)
        _TEMPLATE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{Path(filename).stem}_{short_id}{ext}"
        dest_path = _TEMPLATE_STORAGE_DIR / dest_filename
        dest_path.write_bytes(file_bytes)
        logger.info("Template file saved: %s", dest_path)

        # Parse .docx → Markdown
        content = self._parse_docx_to_markdown(dest_path)

        # Store in DB
        self._repo.insert(
            template_id=template_id,
            name=name,
            template_type=template_type,
            content=content,
            description=description,
            original_filename=filename,
        )

        logger.info("Template uploaded and registered: id='%s'", template_id)
        return self._repo.get_by_id(template_id)  # type: ignore[return-value]

    def create_from_text(
        self,
        name: str,
        content: str,
        *,
        template_type: str = "Global",
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a template from user-supplied Markdown text.

        Skips file upload and parsing — content is stored directly in the DB.
        """
        short_id = uuid.uuid4().hex[:8]
        safe_name = name.lower().replace(" ", "_")[:40]
        template_id = f"{safe_name}_{short_id}"

        self._repo.insert(
            template_id=template_id,
            name=name,
            template_type=template_type,
            content=content,
            description=description,
            original_filename=None,
        )

        logger.info("Template created from text: id='%s'", template_id)
        return self._repo.get_by_id(template_id)  # type: ignore[return-value]

    # ── Read ────────────────────────────────────────────────────────────

    def list_templates(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Return all templates (active-only by default)."""
        return self._repo.list_all(active_only=active_only)

    def get_template(self, template_id: str) -> dict[str, Any]:
        """
        Fetch a template by ID.
        Raises ValueError if not found.
        """
        template = self._repo.get_by_id(template_id)
        if template is None:
            raise ValueError(f"Template '{template_id}' not found")
        return template

    # ── Update ──────────────────────────────────────────────────────────

    def update_template(self, template_id: str, **fields: Any) -> dict[str, Any]:
        """
        Partial update of a template.
        Raises ValueError if the template doesn't exist.
        Returns the updated record.
        """
        if not self._repo.exists(template_id):
            raise ValueError(f"Template '{template_id}' not found")

        self._repo.update(template_id, **fields)
        return self._repo.get_by_id(template_id)  # type: ignore[return-value]

    # ── Delete ──────────────────────────────────────────────────────────

    def delete_template(self, template_id: str) -> None:
        """
        Soft-delete a template (set is_active = 0).
        Raises ValueError if not found.
        """
        if not self._repo.exists(template_id):
            raise ValueError(f"Template '{template_id}' not found")
        self._repo.soft_delete(template_id)
        logger.info("Template soft-deleted: id='%s'", template_id)

    # ── Default ─────────────────────────────────────────────────────────

    def set_default(self, template_id: str) -> None:
        """
        Mark a template as the default. Clears default from all others.
        Raises ValueError if not found.
        """
        if not self._repo.exists(template_id):
            raise ValueError(f"Template '{template_id}' not found")
        self._repo.set_default(template_id)
        logger.info("Template set as default: id='%s'", template_id)

    # ── Re-parse ────────────────────────────────────────────────────────

    def reparse_blueprint(self, template_id: str) -> dict[str, Any]:
        """
        Re-parse the source .docx file and update the content in DB.

        Looks for the source file using original_filename or falls back
        to scanning data/templates/ for a matching file.
        Raises ValueError if template or source file not found.
        """
        template = self.get_template(template_id)

        # Try to find the source .docx on disk
        source_path = self._find_source_file(template)
        if source_path is None:
            raise ValueError(
                f"Source .docx file not found for template '{template_id}'. "
                "Cannot re-parse without the original file."
            )

        content = self._parse_docx_to_markdown(source_path)
        self._repo.update(template_id, content=content)
        logger.info("Template re-parsed: id='%s'", template_id)
        return self._repo.get_by_id(template_id)  # type: ignore[return-value]

    # ── Blueprint access (used by agents) ───────────────────────────────

    def load_blueprint(self, template_id: str) -> dict[str, Any]:
        """
        Load the parsed Markdown content for use by agents.

        Returns a dict compatible with the old TemplateService interface
        so downstream agents work without changes.
        """
        template = self._repo.get_by_id(template_id)

        if template is None or not template.get("content"):
            logger.warning(
                "No blueprint content for '%s' — returning empty template",
                template_id,
            )
            return {
                "template_id": template_id,
                "template_type": "unknown",
                "chapters": [],
                "chapter_count": 0,
                "prompt_text": "",
                "source_file": "",
                "metadata": {},
            }

        content = template["content"]
        chapter_count = content.count("# CHAPTER:")

        return {
            "template_id": template_id,
            "template_type": template.get("type", "Global"),
            "chapters": [],
            "chapter_count": chapter_count,
            "prompt_text": content,
            "source_file": template.get("original_filename", ""),
            "metadata": {},
        }

    def has_blueprint(self, template_id: str) -> bool:
        """Check whether a template has parsed content in the DB."""
        template = self._repo.get_by_id(template_id)
        return template is not None and bool(template.get("content"))

    # ── Private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_docx_to_markdown(docx_path: Path) -> str:
        """Parse a .docx file to Markdown and return the content string."""
        from services.template_parser import (
            group_into_chapters,
            render_to_markdown,
        )
        from docx import Document

        logger.info("Parsing .docx to Markdown: %s", docx_path.name)
        doc = Document(str(docx_path))
        chapters = group_into_chapters(doc)
        markdown = render_to_markdown(chapters)
        logger.info(
            "Parsed %d chapters, %d chars of Markdown",
            len(chapters), len(markdown),
        )
        return markdown

    @staticmethod
    def _find_source_file(template: dict[str, Any]) -> Path | None:
        """
        Try to locate the source .docx on disk for a template.
        Searches data/templates/ for files matching the template ID or
        original filename.
        """
        # Direct match by original filename
        if template.get("original_filename"):
            for candidate in _TEMPLATE_STORAGE_DIR.glob("*"):
                if template["original_filename"] in candidate.name:
                    return candidate

        # Fallback: match by template ID prefix
        tid = template["id"]
        for candidate in _TEMPLATE_STORAGE_DIR.glob("*.docx"):
            if tid in candidate.stem:
                return candidate

        return None
