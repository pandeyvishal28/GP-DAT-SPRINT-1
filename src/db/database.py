"""
db/database.py
SQLite3 connection manager and schema initialization for BI MVP-1.

Manages three tables:
  1. templates     — Registry of GP Doc templates (.docx)
  2. gwp_versions  — Good Writing Practice document version tracking
  3. jobs          — Generation job history and status tracking

Usage:
    from db.database import Database

    db = Database()          # uses SQLITE_DB_PATH from settings
    db.init_tables()         # creates tables if not exist
    templates = db.list_templates()
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from config.settings import get_settings

logger = logging.getLogger(__name__)


class Database:
    """
    SQLite3 connection manager for BI MVP-1.

    Thread-safe: creates a new connection per operation via context manager.
    The database file is created automatically if it doesn't exist.
    """

    def __init__(self, db_path: str | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or settings.SQLITE_DB_PATH
        # Ensure parent directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        logger.info("Database configured at: %s", self._db_path)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for a database connection with auto-commit."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row  # Dict-like row access
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ════════════════════════════════════════════════════════════════════
    #  Schema initialization
    # ════════════════════════════════════════════════════════════════════

    def init_tables(self) -> None:
        """Create all tables if they don't already exist."""
        logger.info("Initializing database tables...")

        with self._connect() as conn:
            # 1. Templates Registry
            conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id                TEXT PRIMARY KEY,
                    name              TEXT NOT NULL,
                    type              TEXT DEFAULT 'Global',
                    content           TEXT,
                    description       TEXT,
                    is_active         INTEGER DEFAULT 1,
                    is_default        INTEGER DEFAULT 0,
                    original_filename TEXT,
                    uploaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("  ✓ Table 'templates' ready")

            # 2. Writing Guides
            conn.execute("""
                CREATE TABLE IF NOT EXISTS writing_guides (
                    id                TEXT PRIMARY KEY,
                    name              TEXT NOT NULL,
                    title             TEXT,
                    description       TEXT,
                    content           TEXT,
                    is_active         INTEGER DEFAULT 1,
                    is_default        INTEGER DEFAULT 0,
                    original_filename TEXT,
                    uploaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("  ✓ Table 'writing_guides' ready")

            # 3. GWP Version Tracking (legacy — kept for backward compat)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gwp_versions (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_number     TEXT NOT NULL,
                    version        TEXT NOT NULL,
                    title          TEXT,
                    effective_date TEXT,
                    filepath       TEXT,
                    rules_json     TEXT,
                    is_active      INTEGER DEFAULT 1,
                    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("  ✓ Table 'gwp_versions' ready")

            # 4. Generation Job History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id          TEXT PRIMARY KEY,
                    template_id     TEXT,
                    gwp_version     TEXT,
                    status          TEXT DEFAULT 'pending',
                    user_prompt     TEXT,
                    reference_files TEXT,
                    output_path     TEXT,
                    error_message   TEXT,
                    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at    TEXT,
                    duration_ms     INTEGER
                )
            """)
            logger.info("  ✓ Table 'jobs' ready")

            # 5. SOP Documents Registry
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sop_documents (
                    id              TEXT PRIMARY KEY,
                    filename        TEXT NOT NULL,
                    filepath        TEXT NOT NULL,
                    type            TEXT,
                    version         TEXT DEFAULT '1',
                    title           TEXT,
                    description     TEXT,
                    md_content      TEXT,
                    uploaded_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("  ✓ Table 'sop_documents' ready")

            # 5. Glossary Entries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS glossary_entries (
                    glossary_id      TEXT PRIMARY KEY,
                    term             TEXT NOT NULL,
                    do_not_translate INTEGER DEFAULT 0,
                    translations     TEXT,
                    scope            TEXT NOT NULL,
                    comments         TEXT,
                    de_comments      TEXT,
                    es_comments      TEXT,
                    is_active        INTEGER DEFAULT 1,
                    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(term, scope)
                )
            """)
            logger.info("  ✓ Table 'glossary_entries' ready")

            # Add new SOP columns if they don't exist yet (for existing DBs)
            for col_def in [
                ("sop_documents", "type", "ALTER TABLE sop_documents ADD COLUMN type TEXT"),
                ("sop_documents", "version", "ALTER TABLE sop_documents ADD COLUMN version TEXT"),
                ("sop_documents", "updated_at", "ALTER TABLE sop_documents ADD COLUMN updated_at TEXT"),
                ("sop_documents", "title", "ALTER TABLE sop_documents ADD COLUMN title TEXT"),
                ("sop_documents", "description", "ALTER TABLE sop_documents ADD COLUMN description TEXT"),
                ("sop_documents", "md_content", "ALTER TABLE sop_documents ADD COLUMN md_content TEXT"),
            ]:
                try:
                    conn.execute(col_def[2])
                    logger.info("  ✓ Migration: added '%s' column to %s", col_def[1], col_def[0])
                except Exception:
                    pass  # Column already exists

            # Rename registered_at → uploaded_at for existing DBs
            try:
                conn.execute("ALTER TABLE sop_documents RENAME COLUMN registered_at TO uploaded_at")
                logger.info("  ✓ Migration: renamed 'registered_at' to 'uploaded_at' in sop_documents")
            except Exception:
                pass  # Column already renamed or table was created fresh

            # Rename id → glossary_id in glossary_entries for existing DBs
            try:
                conn.execute("ALTER TABLE glossary_entries RENAME COLUMN id TO glossary_id")
                logger.info("  ✓ Migration: renamed 'id' to 'glossary_id' in glossary_entries")
            except Exception:
                pass  # Column already renamed or table was created fresh

            # Rename notes → comments and add de_comments, es_comments for existing DBs
            try:
                conn.execute("ALTER TABLE glossary_entries RENAME COLUMN notes TO comments")
                logger.info("  ✓ Migration: renamed 'notes' to 'comments' in glossary_entries")
            except Exception:
                pass  # Column already renamed or table was created fresh
            for col_name in ("de_comments", "es_comments"):
                try:
                    conn.execute(f"ALTER TABLE glossary_entries ADD COLUMN {col_name} TEXT")
                    logger.info("  ✓ Migration: added '%s' column to glossary_entries", col_name)
                except Exception:
                    pass  # Column already exists

        logger.info("Database initialization complete — all 5 tables ready")

    # ════════════════════════════════════════════════════════════════════
    #  Template operations (legacy — used by _scan_and_register_templates)
    # ════════════════════════════════════════════════════════════════════
    def register_template(
        self,
        template_id: str,
        filename: str,
        filepath: str,
        template_type: str = "Global",
        version: str = "1.0",
        is_default: bool = False,
        metadata: dict[str, Any] | None = None,
        blueprint_path: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Register or update a template in the database.

        Legacy method — used by _scan_and_register_templates in main.py.
        New code should use TemplateRepository instead.
        """
        logger.info(
            "Registering template: id='%s', file='%s', type='%s', default=%s",
            template_id, filename, template_type, is_default,
        )

        # Load blueprint content from file if available
        content = None
        bp_path = blueprint_path
        if not bp_path and metadata and "blueprint_path" in metadata:
            bp_path = metadata["blueprint_path"]
        if bp_path:
            from pathlib import Path as _Path
            bp = _Path(bp_path)
            if bp.exists():
                content = bp.read_text(encoding="utf-8")
                logger.info("  Loaded blueprint content from %s", bp.name)

        with self._connect() as conn:
            if is_default:
                conn.execute("UPDATE templates SET is_default = 0")

            conn.execute(
                """
                INSERT INTO templates
                    (id, name, type, content, description,
                     is_active, is_default, original_filename)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    content = excluded.content,
                    is_default = excluded.is_default,
                    original_filename = excluded.original_filename,
                    uploaded_at = CURRENT_TIMESTAMP
                """,
                (
                    template_id,
                    filename,     # used as name for legacy templates
                    template_type,
                    content,
                    description,
                    1 if is_default else 0,
                    filename,
                ),
            )
        logger.info("  ✓ Template '%s' registered successfully", template_id)

    def list_templates(self) -> list[dict[str, Any]]:
        """Return all active templates, ordered by default first then newest."""
        logger.info("Listing all registered templates")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM templates WHERE is_active = 1 "
                "ORDER BY is_default DESC, uploaded_at DESC"
            ).fetchall()

        templates = [dict(row) for row in rows]
        logger.info("  Found %d template(s)", len(templates))
        return templates

    def get_default_template(self) -> dict[str, Any] | None:
        """Return the default template, or the most recently uploaded one."""
        logger.info("Looking up default template")

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE is_default = 1 AND is_active = 1 LIMIT 1"
            ).fetchone()

            if not row:
                logger.info("  No explicit default — using most recent template")
                row = conn.execute(
                    "SELECT * FROM templates WHERE is_active = 1 "
                    "ORDER BY uploaded_at DESC LIMIT 1"
                ).fetchone()

        if row:
            template = dict(row)
            logger.info(
                "  Default template: id='%s', name='%s'",
                template["id"], template["name"],
            )
            return template

        logger.warning("  No templates found in database")
        return None

    def get_template_by_id(self, template_id: str) -> dict[str, Any] | None:
        """Fetch a specific template by ID."""
        logger.info("Looking up template: id='%s'", template_id)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (template_id,)
            ).fetchone()

        if row:
            logger.info("  ✓ Found template '%s'", template_id)
            return dict(row)

        logger.warning("  Template '%s' not found", template_id)
        return None

    # ════════════════════════════════════════════════════════════════════
    #  GWP operations
    # ════════════════════════════════════════════════════════════════════

    def save_gwp_version(
        self,
        doc_number: str,
        version: str,
        title: str = "",
        effective_date: str = "",
        filepath: str = "",
        rules_json: dict[str, Any] | None = None,
    ) -> int:
        """
        Insert a new GWP version and mark it as active.

        Deactivates all previous versions first so only one is active.
        Returns the new row ID.
        """
        logger.info(
            "Saving GWP version: %s v%s (effective: %s)",
            doc_number, version, effective_date or "unknown",
        )

        with self._connect() as conn:
            # Deactivate all previous versions
            conn.execute("UPDATE gwp_versions SET is_active = 0")
            logger.info("  Deactivated previous GWP versions")

            cursor = conn.execute(
                """
                INSERT INTO gwp_versions
                    (doc_number, version, title, effective_date, filepath, rules_json, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    doc_number,
                    version,
                    title,
                    effective_date,
                    filepath,
                    json.dumps(rules_json) if rules_json else None,
                ),
            )
            row_id = cursor.lastrowid

        logger.info("  ✓ GWP v%s saved as active (row_id=%d)", version, row_id)
        return int(row_id) if row_id is not None else 0

    def get_active_gwp(self) -> dict[str, Any] | None:
        """Return the currently active GWP version."""
        logger.info("Looking up active GWP version")

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gwp_versions WHERE is_active = 1 LIMIT 1"
            ).fetchone()

        if row:
            gwp = dict(row)
            logger.info(
                "  Active GWP: %s v%s (effective: %s)",
                gwp["doc_number"], gwp["version"], gwp.get("effective_date", "N/A"),
            )
            return gwp

        logger.warning("  No active GWP version found in database")
        return None

    def get_active_gwp_rules_json(self) -> dict[str, Any] | None:
        """Return the pre-extracted rules JSON for the active GWP version."""
        gwp = self.get_active_gwp()
        if gwp and gwp.get("rules_json"):
            try:
                rules = json.loads(gwp["rules_json"])
                logger.info("  Loaded %d rule categories from active GWP", len(rules))
                return rules
            except json.JSONDecodeError as exc:
                logger.error("  Failed to parse GWP rules JSON: %s", exc)
        return None

    # ════════════════════════════════════════════════════════════════════
    #  SOP document operations
    # ════════════════════════════════════════════════════════════════════

    def register_sop(
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
        """Register or update an SOP document in the database."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sop_documents
                    (id, filename, filepath, type, version, title, description, md_content, uploaded_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename    = excluded.filename,
                    filepath    = excluded.filepath,
                    type        = excluded.type,
                    version     = excluded.version,
                    title       = excluded.title,
                    description = excluded.description,
                    md_content  = excluded.md_content,
                    updated_at  = excluded.updated_at
                """,
                (sop_id, filename, filepath, file_type, version, title, description, md_content, now, now),
            )

    def list_sops(self) -> list[dict[str, Any]]:
        """Return all registered SOP documents, ordered by most recently updated."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sop_documents ORDER BY COALESCE(updated_at, uploaded_at) DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_sop_by_id(self, sop_id: str) -> dict[str, Any] | None:
        """Fetch a specific SOP document by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sop_documents WHERE id = ?", (sop_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_sop(self, sop_id: str) -> bool:
        """Delete an SOP document by ID. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sop_documents WHERE id = ?", (sop_id,)
            )
        return cursor.rowcount > 0

    # ════════════════════════════════════════════════════════════════════
    #  Job tracking operations
    # ════════════════════════════════════════════════════════════════════

    def create_job(
        self,
        job_id: str,
        template_id: str = "",
        gwp_version: str = "",
        user_prompt: str = "",
        reference_files: list[str] | None = None,
    ) -> None:
        """Create a new generation job record."""
        logger.info("Creating job record: job_id='%s', template='%s'", job_id, template_id)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, template_id, gwp_version, user_prompt, reference_files, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (
                    job_id,
                    template_id,
                    gwp_version,
                    user_prompt,
                    json.dumps(reference_files) if reference_files else "[]",
                ),
            )
        logger.info("  ✓ Job '%s' created with status=pending", job_id)

    def update_job_status(
        self,
        job_id: str,
        status: str,
        output_path: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update a job's status and optional fields."""
        logger.info("Updating job '%s': status='%s'", job_id, status)

        with self._connect() as conn:
            updates = ["status = ?"]
            values: list[Any] = [status]

            if output_path is not None:
                updates.append("output_path = ?")
                values.append(output_path)

            if error_message is not None:
                updates.append("error_message = ?")
                values.append(error_message)

            if duration_ms is not None:
                updates.append("duration_ms = ?")
                values.append(duration_ms)

            if status in ("completed", "failed"):
                updates.append("completed_at = ?")
                values.append(datetime.now(timezone.utc).isoformat())

            values.append(job_id)
            conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
                values,
            )
        logger.info("  ✓ Job '%s' updated to status='%s'", job_id, status)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Fetch a job record by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()

        if row:
            return dict(row)
        return None

    def list_recent_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent jobs."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ════════════════════════════════════════════════════════════════════
    #  Glossary operations
    # ════════════════════════════════════════════════════════════════════

    def insert_glossary_entry(
        self,
        glossary_id: str,
        term: str,
        scope: str,
        do_not_translate: bool = False,
        translations_json: str | None = None,
        comments: str | None = None,
        de_comments: str | None = None,
        es_comments: str | None = None,
    ) -> None:
        """Insert a new glossary entry. Raises on duplicate (term, scope)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO glossary_entries
                    (glossary_id, term, do_not_translate, translations, scope,
                     comments, de_comments, es_comments,
                     is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    glossary_id,
                    term,
                    1 if do_not_translate else 0,
                    translations_json,
                    scope,
                    comments,
                    de_comments,
                    es_comments,
                    now,
                    now,
                ),
            )

    def list_glossary_entries(
        self,
        scope: str | None = None,
        is_active: bool = True,
    ) -> list[dict[str, Any]]:
        """Return glossary entries with optional scope filter."""
        query = "SELECT * FROM glossary_entries WHERE is_active = ?"
        params: list[Any] = [1 if is_active else 0]

        if scope:
            query += " AND scope = ?"
            params.append(scope)

        query += " ORDER BY term ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_glossary_entry(self, glossary_id: str) -> dict[str, Any] | None:
        """Fetch a single glossary entry by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM glossary_entries WHERE glossary_id = ?", (glossary_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_glossary_entry_by_term_scope(
        self, term: str, scope: str
    ) -> dict[str, Any] | None:
        """Fetch a glossary entry by term + scope combination."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM glossary_entries WHERE term = ? AND scope = ?",
                (term, scope),
            ).fetchone()
        return dict(row) if row else None

    def update_glossary_entry(self, glossary_id: str, **fields: Any) -> bool:
        """
        Update specific fields on a glossary entry.
        Returns True if a row was updated.
        """
        if not fields:
            return False

        allowed = {"term", "do_not_translate", "translations", "scope",
                   "comments", "de_comments", "es_comments", "is_active"}
        updates: list[str] = []
        values: list[Any] = []

        for key, val in fields.items():
            if key not in allowed:
                continue
            updates.append(f"{key} = ?")
            values.append(val)

        if not updates:
            return False

        updates.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(glossary_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE glossary_entries SET {', '.join(updates)} WHERE glossary_id = ?",
                values,
            )
        return cursor.rowcount > 0

    def delete_glossary_entry(self, glossary_id: str) -> bool:
        """Delete a glossary entry. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM glossary_entries WHERE glossary_id = ?",
                (glossary_id,),
            )
        return cursor.rowcount > 0
