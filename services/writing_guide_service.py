"""
services/writing_guide_service.py
Business logic for the Writing Guides feature.

Handles upload validation, file storage, and CRUD operations.
Parsing (extracting rules from PDF/DOCX) is a separate future concern.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from repositories.writing_guide_repository import WritingGuideRepository

logger = logging.getLogger(__name__)

# Where uploaded writing guide source files are kept
_GUIDE_STORAGE_DIR = Path("data/writing_guides")

# Allowed upload extensions
_ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx", ".doc", ".txt", ".md"}


class WritingGuideService:
    """
    Writing Guide business logic.

    Responsibilities:
      - Validate uploaded files
      - Save source files to disk (for future parsing)
      - CRUD via repository
      - Provide prompt-formatted rules for agents
    """

    def __init__(self, repository: WritingGuideRepository) -> None:
        self._repo = repository

    # ── Upload ──────────────────────────────────────────────────────────

    def upload_guide(
        self,
        file_bytes: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """
        Upload a writing guide file and create a DB record.

        The source file is saved to data/writing_guides/ for future parsing.
        Content is NULL until a parser extracts rules from the file.
        """
        ext = Path(filename).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
            )

        # Generate unique ID
        short_id = uuid.uuid4().hex[:8]
        guide_id = f"{Path(filename).stem.lower().replace(' ', '_')}_{short_id}"

        # Save source file to disk
        _GUIDE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{Path(filename).stem}_{short_id}{ext}"
        dest_path = _GUIDE_STORAGE_DIR / dest_filename
        dest_path.write_bytes(file_bytes)
        logger.info("Writing guide file saved: %s", dest_path)

        # Create DB record (content = NULL — parsing is a future step)
        self._repo.insert(
            guide_id=guide_id,
            name=Path(filename).stem,
            title=None,
            description=None,
            content=None,
            original_filename=filename,
        )

        logger.info("Writing guide uploaded: id='%s'", guide_id)
        return self._repo.get_by_id(guide_id)  # type: ignore[return-value]

    # ── Background parsing ──────────────────────────────────────────────

    def parse_and_update_guide(self, guide_id: str) -> None:
        """
        Parse the source file for a guide and update its DB content.

        Called as a background task after upload. Reads the file from
        data/writing_guides/, extracts text, and writes it to the
        ``content`` column.
        """
        from utils.writing_guide_parser import ParsingError, extract_text

        guide = self._repo.get_by_id(guide_id)
        if guide is None:
            logger.error("parse_and_update_guide: guide '%s' not found", guide_id)
            return

        original_filename = guide.get("original_filename", "")
        # Reconstruct the stored filename (same logic used in upload_guide)
        ext = Path(original_filename).suffix.lower()
        short_id = guide_id.rsplit("_", 1)[-1]
        dest_filename = f"{Path(original_filename).stem}_{short_id}{ext}"
        file_path = _GUIDE_STORAGE_DIR / dest_filename

        if not file_path.exists():
            logger.error(
                "parse_and_update_guide: source file not found at %s", file_path
            )
            return

        try:
            content = extract_text(file_path)

            # Extract metadata to gracefully populate omitted fields
            from utils.writing_guide_parser import extract_title, extract_description

            update_kwargs: dict[str, Any] = {"content": content}

            # Populate title if currently empty/None
            if not guide.get("title"):
                extracted_title = extract_title(content)
                if extracted_title:
                    update_kwargs["title"] = extracted_title

            # Only populate description if current one is empty/None
            if not guide.get("description"):
                extracted_description = extract_description(content)
                if extracted_description:
                    update_kwargs["description"] = extracted_description

            self._repo.update(guide_id, **update_kwargs)

            logger.info(
                "Writing guide parsed successfully: id='%s' (%d chars)",
                guide_id,
                len(content),
            )
        except (ParsingError, Exception) as exc:
            logger.error(
                "Failed to parse writing guide '%s': %s", guide_id, exc
            )

    # ── Read ────────────────────────────────────────────────────────────

    def list_guides(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Return all writing guides (active-only by default)."""
        return self._repo.list_all(active_only=active_only)

    def get_guide(self, guide_id: str) -> dict[str, Any]:
        """Fetch a guide by ID. Raises ValueError if not found."""
        guide = self._repo.get_by_id(guide_id)
        if guide is None:
            raise ValueError(f"Writing guide '{guide_id}' not found")
        return guide

    # ── Update ──────────────────────────────────────────────────────────

    def update_guide(self, guide_id: str, **fields: Any) -> dict[str, Any]:
        """Partial update. Raises ValueError if not found."""
        if not self._repo.exists(guide_id):
            raise ValueError(f"Writing guide '{guide_id}' not found")
        self._repo.update(guide_id, **fields)
        return self._repo.get_by_id(guide_id)  # type: ignore[return-value]

    # ── Delete ──────────────────────────────────────────────────────────

    def delete_guide(self, guide_id: str) -> None:
        """Soft-delete. Raises ValueError if not found."""
        if not self._repo.exists(guide_id):
            raise ValueError(f"Writing guide '{guide_id}' not found")
        self._repo.soft_delete(guide_id)
        logger.info("Writing guide soft-deleted: id='%s'", guide_id)

    # ── Default ─────────────────────────────────────────────────────────

    def set_default(self, guide_id: str) -> None:
        """Mark a guide as default. Raises ValueError if not found."""
        if not self._repo.exists(guide_id):
            raise ValueError(f"Writing guide '{guide_id}' not found")
        self._repo.set_default(guide_id)
        logger.info("Writing guide set as default: id='%s'", guide_id)

    # ── Prompt formatting (used by agents) ──────────────────────────────

    def get_prompt_rules(self, guide_id: str) -> str | None:
        """
        Get the writing guide content formatted for LLM prompt injection.

        Returns the Markdown content if available, None if the guide
        hasn't been parsed yet (content is NULL).
        """
        guide = self._repo.get_by_id(guide_id)
        if guide is None:
            return None
        return guide.get("content")
