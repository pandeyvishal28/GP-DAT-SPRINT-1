"""
repositories/sop_repository.py
Data-access layer for SOP (Standard Operating Procedure) documents.

Wraps the Database SOP methods to provide a clean repository interface.
"""

from __future__ import annotations

import logging
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)


class SopRepository:
    """Thin data-access wrapper around Database SOP operations."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def register(
        self,
        sop_id: str,
        filename: str,
        filepath: str,
        file_type: str | None = None,
        version: str = "1",
        title: str | None = None,
        description: str | None = None,
        md_content: str | None = None,
    ) -> None:
        """Register or upsert an SOP document."""
        self._db.register_sop(
            sop_id=sop_id,
            filename=filename,
            filepath=filepath,
            file_type=file_type,
            version=version,
            title=title,
            description=description,
            md_content=md_content,
        )

    def list_all(self) -> list[dict[str, Any]]:
        """Return all SOP documents ordered by most recently updated."""
        return self._db.list_sops()

    def get_by_id(self, sop_id: str) -> dict[str, Any] | None:
        """Fetch a single SOP document by ID."""
        return self._db.get_sop_by_id(sop_id)

    def delete(self, sop_id: str) -> bool:
        """Delete an SOP document by ID. Returns True if a row was deleted."""
        return self._db.delete_sop(sop_id)
