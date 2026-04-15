"""
repositories/writing_guide_repository.py
Pure database access for the writing_guides table.
"""

from __future__ import annotations

import logging
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)


class WritingGuideRepository:
    """Data-access layer for the ``writing_guides`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Create ──────────────────────────────────────────────────────────

    def insert(
        self,
        guide_id: str,
        name: str,
        *,
        title: str | None = None,
        description: str | None = None,
        content: str | None = None,
        is_active: bool = True,
        is_default: bool = False,
        original_filename: str | None = None,
    ) -> None:
        """Insert a new writing guide row."""
        logger.info("WritingGuideRepo.insert: id='%s', name='%s'", guide_id, name)

        with self._db._connect() as conn:
            if is_default:
                conn.execute("UPDATE writing_guides SET is_default = 0")

            conn.execute(
                """
                INSERT INTO writing_guides
                    (id, name, title, description, content,
                     is_active, is_default, original_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guide_id,
                    name,
                    title,
                    description,
                    content,
                    1 if is_active else 0,
                    1 if is_default else 0,
                    original_filename,
                ),
            )

    # ── Read ────────────────────────────────────────────────────────────

    def get_by_id(self, guide_id: str) -> dict[str, Any] | None:
        """Fetch a single writing guide by ID."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT * FROM writing_guides WHERE id = ?", (guide_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Return all writing guides ordered by default-first then newest."""
        query = "SELECT * FROM writing_guides"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY is_default DESC, uploaded_at DESC"

        with self._db._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def exists(self, guide_id: str) -> bool:
        """Check whether a writing guide with the given ID exists."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM writing_guides WHERE id = ?", (guide_id,)
            ).fetchone()
        return row is not None

    # ── Update ──────────────────────────────────────────────────────────

    def update(self, guide_id: str, **fields: Any) -> bool:
        """
        Partial update — only provided fields are changed.
        Returns True if a row was updated.
        """
        allowed = {
            "name", "title", "description", "content",
            "is_active", "is_default", "original_filename",
        }
        to_update = {k: v for k, v in fields.items() if k in allowed}
        if not to_update:
            return False

        set_clause = ", ".join(f"{col} = ?" for col in to_update)
        values = list(to_update.values()) + [guide_id]

        with self._db._connect() as conn:
            if to_update.get("is_default"):
                conn.execute("UPDATE writing_guides SET is_default = 0")

            cursor = conn.execute(
                f"UPDATE writing_guides SET {set_clause} WHERE id = ?",
                values,
            )
        return cursor.rowcount > 0

    # ── Delete ──────────────────────────────────────────────────────────

    def soft_delete(self, guide_id: str) -> bool:
        """Set ``is_active = 0``. Returns True if row existed."""
        return self.update(guide_id, is_active=0)

    # ── Convenience ─────────────────────────────────────────────────────

    def set_default(self, guide_id: str) -> None:
        """Mark *guide_id* as the default; un-default all others."""
        with self._db._connect() as conn:
            conn.execute("UPDATE writing_guides SET is_default = 0")
            conn.execute(
                "UPDATE writing_guides SET is_default = 1 WHERE id = ?",
                (guide_id,),
            )

    def get_default(self) -> dict[str, Any] | None:
        """Return the default writing guide, or newest as fallback."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT * FROM writing_guides "
                "WHERE is_default = 1 AND is_active = 1 LIMIT 1"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM writing_guides WHERE is_active = 1 "
                    "ORDER BY uploaded_at DESC LIMIT 1"
                ).fetchone()
        return dict(row) if row else None
