"""
services/sop_service.py
Business-logic layer for SOP (Standard Operating Procedure) management.

Handles file validation, disk storage, document parsing to Markdown,
unique-ID generation, and delegates persistence to `SopRepository`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from repositories.sop_repository import SopRepository
from services.sop_parser_service import SopParserService

logger = logging.getLogger(__name__)


class DuplicateSopError(Exception):
    """Raised when an SOP with the same ID already exists and no update action was requested."""

    def __init__(self, sop_id: str, existing_version: str) -> None:
        self.sop_id = sop_id
        self.existing_version = existing_version
        super().__init__(f"SOP '{sop_id}' already exists at version {existing_version}")


# Where uploaded SOPs are persisted on disk
_SOP_STORAGE_DIR = Path("data/sample_inputs")

# Allowed file extensions → human-readable type label
_ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".txt": "txt",
}


class SopService:
    """Encapsulates all SOP business logic."""

    def __init__(self, repository: SopRepository) -> None:
        self._repo = repository
        self._parser = SopParserService()

    # ── Upload ───────────────────────────────────────────────────────

    async def upload_sop(
        self,
        file: UploadFile,
        action: str = "",
        version: str = "",
    ) -> dict[str, Any]:
        """
        Validate, save to disk, and register an uploaded SOP file.

        On a duplicate filename the method raises ``DuplicateSopError`` unless
        ``action="update"`` is supplied, in which case the version is
        auto-incremented (or set to ``version`` if provided).

        Raises:
            ValueError: if filename is missing or file type is unsupported.
            DuplicateSopError: if the SOP already exists and action != 'update'.
        """
        if not file.filename:
            raise ValueError("Uploaded file must have a filename")

        ext = Path(file.filename).suffix.lower()
        if ext not in _ALLOWED_TYPES:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_TYPES)}"
            )

        file_type = _ALLOWED_TYPES[ext]

        safe_stem = Path(file.filename).stem
        sop_id = safe_stem
        original_filename = file.filename
        dest_path = _SOP_STORAGE_DIR / file.filename

        # ── Duplicate check ──────────────────────────────────────────
        existing = self._repo.get_by_id(sop_id)
        is_update = existing is not None

        if is_update and action != "update":
            existing_version = (existing or {}).get("version", "1")
            raise DuplicateSopError(sop_id=sop_id, existing_version=existing_version)

        # Resolve version
        if version:
            resolved_version = version
        elif is_update:
            old_ver = (existing or {}).get("version") or "1"
            try:
                resolved_version = str(int(old_ver) + 1)
            except ValueError:
                resolved_version = old_ver + ".1"
        else:
            resolved_version = "1"

        # Ensure the storage directory exists
        _SOP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        # Stream file to disk
        contents = await file.read()
        dest_path.write_bytes(contents)
        logger.info("SOP uploaded and saved: %s", dest_path)

        # Parse file to Markdown and extract metadata
        md_content = self._parser.parse_to_markdown(dest_path, file_type)
        title = None
        description = None
        if md_content:
            title = self._parser.extract_title(md_content)
            description = self._parser.extract_description(md_content)
            logger.info(
                "Parsed SOP to Markdown: title='%s', description length=%d",
                title or "(none)",
                len(description) if description else 0,
            )

        # Fallback title to filename stem if not found in content
        if not title:
            title = safe_stem

        # Register / update in database via repository
        self._repo.register(
            sop_id=sop_id,
            filename=original_filename,
            filepath=str(dest_path),
            file_type=file_type,
            version=resolved_version,
            title=title,
            description=description,
            md_content=md_content,
        )
        logger.info("SOP registered in database: id='%s', version='%s'", sop_id, resolved_version)

        message = (
            f"SOP updated to version {resolved_version} successfully"
            if is_update else
            "SOP uploaded and registered successfully"
        )

        return {
            "sop_id": sop_id,
            "filename": original_filename,
            "type": file_type,
            "title": title,
            "description": description,
            "version": resolved_version,
            "message": message,
        }

    # ── List ─────────────────────────────────────────────────────────

    def list_sops(self) -> dict[str, Any]:
        """Return all registered SOPs formatted for the API response."""
        sops = self._repo.list_all()
        return {
            "total": len(sops),
            "sops": [
                {
                    "sop_id": s["id"],
                    "filename": s["filename"],
                    "filepath": s.get("filepath"),
                    "type": s.get("type"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "version": s.get("version", "1"),
                    "uploaded_at": s.get("uploaded_at"),
                    "updated_at": s.get("updated_at"),
                }
                for s in sops
            ],
        }

    def get_sop(self, sop_id: str) -> dict[str, Any] | None:
        """Return full details of a single SOP, including md_content."""
        s = self._repo.get_by_id(sop_id)
        if s is None:
            return None
        return {
            "sop_id": s["id"],
            "filename": s["filename"],
            "filepath": s.get("filepath"),
            "type": s.get("type"),
            "title": s.get("title"),
            "description": s.get("description"),
            "version": s.get("version", "1"),
            "md_content": s.get("md_content"),
            "uploaded_at": s.get("uploaded_at"),
            "updated_at": s.get("updated_at"),
        }

    def delete_sop(self, sop_id: str) -> bool:
        """Delete an SOP and its file from disk. Returns True if deleted."""
        sop = self._repo.get_by_id(sop_id)
        if sop is None:
            return False

        # Remove file from disk
        filepath = sop.get("filepath")
        if filepath:
            path = Path(filepath)
            if path.exists():
                path.unlink()
                logger.info("Deleted SOP file from disk: %s", path)

        # Remove from database
        self._repo.delete(sop_id)
        logger.info("Deleted SOP from database: %s", sop_id)
        return True
