"""
tests/test_writing_guide_repository.py
Unit tests for repositories/writing_guide_repository.py

Test IDs: TC-WGR-01 → TC-WGR-09

Uses an in-memory SQLite database to ensure tests are isolated
and fast, matching the db/database.py schema.
"""

from __future__ import annotations

import sqlite3
import pytest
from typing import Any

from db.database import Database
from repositories.writing_guide_repository import WritingGuideRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _InMemoryDB:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE writing_guides (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                content TEXT,
                is_active INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,
                original_filename TEXT,
                uploaded_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.commit()

    def _connect(self):
        return self._conn

@pytest.fixture
def repo():
    """Return a WritingGuideRepository tied to the memory DB."""
    db = _InMemoryDB()
    return WritingGuideRepository(db)


# ── TC-WGR-01: Insert and Get By ID ──────────────────────────────────────────

class TestInsertAndGetById:
    """TC-WGR-01"""

    def test_insert_returns_record(self, repo):
        repo.insert(guide_id="wg_001", name="Style Guide", description="Rules")
        record = repo.get_by_id("wg_001")
        assert record is not None
        assert record["id"] == "wg_001"
        assert record["name"] == "Style Guide"
        assert record["description"] == "Rules"

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_by_id("ghost_id") is None

    def test_inserted_record_has_null_content_by_default(self, repo):
        repo.insert(guide_id="wg_002", name="Guide 2")
        record = repo.get_by_id("wg_002")
        assert record["content"] is None


# ── TC-WGR-02: Exists Check ──────────────────────────────────────────────────

class TestExists:
    """TC-WGR-02"""

    def test_returns_true_for_existing(self, repo):
        repo.insert(guide_id="wg_001", name="Guide 1")
        assert repo.exists("wg_001") is True

    def test_returns_false_for_missing(self, repo):
        assert repo.exists("wg_missing") is False


# ── TC-WGR-03: List All ──────────────────────────────────────────────────────

class TestListAll:
    """TC-WGR-03"""

    def test_lists_active_guides_only_by_default(self, repo):
        repo.insert(guide_id="wg_active", name="Active Guide", is_active=True)
        repo.insert(guide_id="wg_archived", name="Archived Guide", is_active=False)

        results = repo.list_all()
        assert len(results) == 1
        assert results[0]["id"] == "wg_active"

    def test_lists_all_including_archived(self, repo):
        repo.insert(guide_id="wg_active", name="Active Guide", is_active=True)
        repo.insert(guide_id="wg_archived", name="Archived Guide", is_active=False)

        results = repo.list_all(active_only=False)
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert "wg_active" in ids
        assert "wg_archived" in ids

    def test_empty_db_returns_empty_list(self, repo):
        assert repo.list_all() == []


# ── TC-WGR-04: Update ────────────────────────────────────────────────────────

class TestUpdate:
    """TC-WGR-04"""

    def test_update_name_and_content(self, repo):
        repo.insert(guide_id="wg_001", name="Old Name")
        success = repo.update("wg_001", name="New Name", content="Rules: 1...")
        assert success is True
        
        record = repo.get_by_id("wg_001")
        assert record["name"] == "New Name"
        assert record["content"] == "Rules: 1..."

    def test_update_nonexistent_returns_false(self, repo):
        success = repo.update("ghost_id", name="New Name")
        assert success is False

    def test_update_with_no_allowed_fields_returns_false(self, repo):
        repo.insert(guide_id="wg_001", name="Current")
        # 'unknown_field' is not in the allowed list in update()
        success = repo.update("wg_001", unknown_field="X")
        assert success is False


# ── TC-WGR-05: Soft Delete ───────────────────────────────────────────────────

class TestSoftDelete:
    """TC-WGR-05"""

    def test_soft_delete_sets_inactive(self, repo):
        repo.insert(guide_id="wg_001", name="Kill Me")
        success = repo.soft_delete("wg_001")
        assert success is True

        record = repo.get_by_id("wg_001")
        assert record["is_active"] == 0

    def test_soft_deleted_guide_excluded_from_active_list(self, repo):
        repo.insert(guide_id="wg_001", name="Target")
        repo.soft_delete("wg_001")
        assert len(repo.list_all(active_only=True)) == 0

    def test_soft_delete_nonexistent_returns_false(self, repo):
        success = repo.soft_delete("ghost_id")
        assert success is False


# ── TC-WGR-06: Set Default ───────────────────────────────────────────────────

class TestSetDefault:
    """TC-WGR-06"""

    def test_only_one_default_at_a_time(self, repo):
        repo.insert(guide_id="d1", name="Guide 1", is_default=False)
        repo.insert(guide_id="d2", name="Guide 2", is_default=False)

        repo.set_default("d1")
        assert repo.get_by_id("d1")["is_default"] == 1
        assert repo.get_by_id("d2")["is_default"] == 0

        repo.set_default("d2")
        assert repo.get_by_id("d1")["is_default"] == 0
        assert repo.get_by_id("d2")["is_default"] == 1


# ── TC-WGR-07: Get Default ───────────────────────────────────────────────────

class TestGetDefault:
    """TC-WGR-07"""

    def test_returns_explicitly_marked_default(self, repo):
        repo.insert(guide_id="g1", name="G1")
        repo.insert(guide_id="g2", name="G2", is_default=True)
        repo.insert(guide_id="g3", name="G3")

        default_wg = repo.get_default()
        assert default_wg["id"] == "g2"

    def test_falls_back_to_newest_when_no_default_set(self, repo):
        # Even without explicit default, get_default() returns something
        repo.insert(guide_id="old", name="Old") # Inserted first
        repo.insert(guide_id="new", name="New") # Inserted second
        
        default_wg = repo.get_default()
        assert default_wg["id"] == "new"

    def test_returns_none_on_empty_db(self, repo):
        assert repo.get_default() is None


# ── TC-WGR-08: Insert as Default ─────────────────────────────────────────────

class TestInsertAsDefault:
    """TC-WGR-08"""

    def test_inserting_default_clears_previous_default(self, repo):
        repo.insert(guide_id="g1", name="G1", is_default=True)
        assert repo.get_by_id("g1")["is_default"] == 1

        repo.insert(guide_id="g2", name="G2", is_default=True)
        assert repo.get_by_id("g1")["is_default"] == 0
        assert repo.get_by_id("g2")["is_default"] == 1
