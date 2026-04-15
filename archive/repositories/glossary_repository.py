"""
repositories/glossary_repository.py
Data-access layer for glossary entries used in SOP translation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)


class GlossaryRepository:
    """Thin data-access wrapper around Database glossary operations."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        entry_id: str,
        term: str,
        scope: str,
        do_not_translate: bool = False,
        translations: dict[str, str] | None = None,
        notes: str | None = None,
    ) -> None:
        """Insert a new glossary entry."""
        self._db.insert_glossary_entry(
            entry_id=entry_id,
            term=term,
            scope=scope,
            do_not_translate=do_not_translate,
            translations_json=json.dumps(translations) if translations else None,
            notes=notes,
        )

    def list_all(
        self,
        scope: str | None = None,
        is_active: bool = True,
    ) -> list[dict[str, Any]]:
        """Return glossary entries, optionally filtered by scope."""
        rows = self._db.list_glossary_entries(scope=scope, is_active=is_active)
        return [self._deserialize(row) for row in rows]

    def get_by_id(self, entry_id: str) -> dict[str, Any] | None:
        """Fetch a single glossary entry by ID."""
        row = self._db.get_glossary_entry(entry_id)
        return self._deserialize(row) if row else None

    def get_by_term_and_scope(self, term: str, scope: str) -> dict[str, Any] | None:
        """Fetch a glossary entry by term + scope."""
        row = self._db.get_glossary_entry_by_term_scope(term, scope)
        return self._deserialize(row) if row else None

    def update(self, entry_id: str, **fields: Any) -> bool:
        """Update specific fields on a glossary entry."""
        if "translations" in fields:
            val = fields["translations"]
            fields["translations"] = json.dumps(val) if val is not None else None
        if "do_not_translate" in fields:
            fields["do_not_translate"] = 1 if fields["do_not_translate"] else 0
        return self._db.update_glossary_entry(entry_id, **fields)

    def delete(self, entry_id: str) -> bool:
        """Delete a glossary entry. Returns True if a row was deleted."""
        return self._db.delete_glossary_entry(entry_id)

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _deserialize(row: dict[str, Any]) -> dict[str, Any]:
        """Convert stored JSON strings and integer flags back to Python types."""
        if row.get("translations"):
            try:
                row["translations"] = json.loads(row["translations"])
            except (json.JSONDecodeError, TypeError):
                row["translations"] = None
        row["do_not_translate"] = bool(row.get("do_not_translate", 0))
        row["is_active"] = bool(row.get("is_active", 1))
        return row
