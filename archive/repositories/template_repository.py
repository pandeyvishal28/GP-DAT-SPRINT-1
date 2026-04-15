"""
repositories/template_repository.py
Pure database access for the templates table.

All SQL for the templates table lives here. Business logic belongs
in services/template_service.py; HTTP handling in routers/template_router.py.
"""

from __future__ import annotations

import logging
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)


class TemplateRepository:
    """Data-access layer for the ``templates`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Create ──────────────────────────────────────────────────────────

    def insert(
        self,
        template_id: str,
        name: str,
        *,
        template_type: str = "Global",
        content: str | None = None,
        description: str | None = None,
        is_active: bool = True,
        is_default: bool = False,
        original_filename: str | None = None,
    ) -> None:
        """Insert a new template row."""
        logger.info("TemplateRepo.insert: id='%s', name='%s'", template_id, name)

        with self._db._connect() as conn:
            # If marking as default, clear all others first
            if is_default:
                conn.execute("UPDATE templates SET is_default = 0")

            conn.execute(
                """
                INSERT INTO templates
                    (id, name, type, content, description,
                     is_active, is_default, original_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    name,
                    template_type,
                    content,
                    description,
                    1 if is_active else 0,
                    1 if is_default else 0,
                    original_filename,
                ),
            )

    # ── Read ────────────────────────────────────────────────────────────

    def get_by_id(self, template_id: str) -> dict[str, Any] | None:
        """Fetch a single template by ID. Returns None if not found."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (template_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """
        Return all templates ordered by default-first then newest-first.

        If *active_only* is True (default), archived templates are excluded.
        """
        query = "SELECT * FROM templates"
        params: tuple = ()

        if active_only:
            query += " WHERE is_active = 1"

        query += " ORDER BY is_default DESC, uploaded_at DESC"

        with self._db._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def exists(self, template_id: str) -> bool:
        """Check whether a template with the given ID exists."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM templates WHERE id = ?", (template_id,)
            ).fetchone()
        return row is not None

    # ── Update ──────────────────────────────────────────────────────────

    def update(self, template_id: str, **fields: Any) -> bool:
        """
        Partial update — only the provided keyword arguments are changed.

        Allowed fields: name, type, content, description, is_active,
                        is_default, original_filename.

        Returns True if a row was updated, False if the ID was not found.
        """
        allowed = {
            "name", "type", "content", "description",
            "is_active", "is_default", "original_filename",
        }
        to_update = {k: v for k, v in fields.items() if k in allowed}

        if not to_update:
            return False

        set_clause = ", ".join(f"{col} = ?" for col in to_update)
        values = list(to_update.values()) + [template_id]

        with self._db._connect() as conn:
            # If setting as default, clear others first
            if to_update.get("is_default"):
                conn.execute("UPDATE templates SET is_default = 0")

            cursor = conn.execute(
                f"UPDATE templates SET {set_clause} WHERE id = ?",
                values,
            )
        return cursor.rowcount > 0

    # ── Delete ──────────────────────────────────────────────────────────

    def soft_delete(self, template_id: str) -> bool:
        """Set ``is_active = 0`` (archive). Returns True if row existed."""
        return self.update(template_id, is_active=0)

    def hard_delete(self, template_id: str) -> bool:
        """Permanently remove the row. Returns True if row existed."""
        with self._db._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM templates WHERE id = ?", (template_id,)
            )
        return cursor.rowcount > 0

    # ── Convenience ─────────────────────────────────────────────────────

    def set_default(self, template_id: str) -> None:
        """Mark *template_id* as the default; un-default all others."""
        with self._db._connect() as conn:
            conn.execute("UPDATE templates SET is_default = 0")
            conn.execute(
                "UPDATE templates SET is_default = 1 WHERE id = ?",
                (template_id,),
            )

    def get_default(self) -> dict[str, Any] | None:
        """Return the default template, or the newest one as fallback."""
        with self._db._connect() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE is_default = 1 AND is_active = 1 LIMIT 1"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM templates WHERE is_active = 1 "
                    "ORDER BY uploaded_at DESC LIMIT 1"
                ).fetchone()
        return dict(row) if row else None
