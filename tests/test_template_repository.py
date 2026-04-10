"""
tests/test_template_repository.py
Unit tests for repositories/template_repository.py

Test IDs: TC-TR-01 → TC-TR-09

Uses an in-memory SQLite database so tests are fully isolated —
no external DB required, no file I/O side effects.
"""

from __future__ import annotations

import sqlite3
import pytest

from repositories.template_repository import TemplateRepository


# ── In-memory DB fixture ───────────────────────────────────────────────────────

class _InMemoryDB:
    """Minimal in-memory SQLite stand-in that mimics db.Database._connect()."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'Global',
                content TEXT,
                description TEXT,
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
    """Return a TemplateRepository backed by a fresh in-memory DB."""
    db = _InMemoryDB()
    return TemplateRepository(db)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _insert_one(repo: TemplateRepository, tid="tmpl_001", name="Test Template") -> None:
    repo.insert(
        template_id=tid,
        name=name,
        template_type="Global",
        content="# Hello",
        description="A test template",
        original_filename="test.docx",
    )


# ── TC-TR-01: insert + get_by_id ──────────────────────────────────────────────

class TestInsertAndGetById:
    """TC-TR-01"""

    def test_insert_returns_record(self, repo):
        _insert_one(repo)
        result = repo.get_by_id("tmpl_001")
        assert result is not None
        assert result["id"] == "tmpl_001"
        assert result["name"] == "Test Template"

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_by_id("does_not_exist") is None

    def test_inserted_record_has_correct_content(self, repo):
        _insert_one(repo)
        result = repo.get_by_id("tmpl_001")
        assert result["content"] == "# Hello"
        assert result["type"] == "Global"
        assert result["original_filename"] == "test.docx"


# ── TC-TR-02: exists ──────────────────────────────────────────────────────────

class TestExists:
    """TC-TR-02"""

    def test_returns_true_for_existing(self, repo):
        _insert_one(repo)
        assert repo.exists("tmpl_001") is True

    def test_returns_false_for_missing(self, repo):
        assert repo.exists("ghost_id") is False


# ── TC-TR-03: list_all ────────────────────────────────────────────────────────

class TestListAll:
    """TC-TR-03"""

    def test_lists_active_templates_only_by_default(self, repo):
        repo.insert("a1", "Active Template", content="x")
        repo.insert("a2", "Another Active", content="y")
        repo.soft_delete("a2")
        results = repo.list_all(active_only=True)
        ids = [r["id"] for r in results]
        assert "a1" in ids
        assert "a2" not in ids

    def test_lists_all_including_archived(self, repo):
        repo.insert("b1", "Active", content="x")
        repo.insert("b2", "Archived", content="y")
        repo.soft_delete("b2")
        results = repo.list_all(active_only=False)
        ids = [r["id"] for r in results]
        assert "b1" in ids
        assert "b2" in ids

    def test_empty_db_returns_empty_list(self, repo):
        assert repo.list_all() == []


# ── TC-TR-04: update ──────────────────────────────────────────────────────────

class TestUpdate:
    """TC-TR-04"""

    def test_update_name(self, repo):
        _insert_one(repo)
        repo.update("tmpl_001", name="Updated Name")
        result = repo.get_by_id("tmpl_001")
        assert result["name"] == "Updated Name"

    def test_update_content(self, repo):
        _insert_one(repo)
        repo.update("tmpl_001", content="# New Content")
        result = repo.get_by_id("tmpl_001")
        assert result["content"] == "# New Content"

    def test_update_nonexistent_returns_false(self, repo):
        updated = repo.update("ghost", name="X")
        assert updated is False

    def test_update_with_no_allowed_fields_returns_false(self, repo):
        _insert_one(repo)
        result = repo.update("tmpl_001", unknown_field="value")
        assert result is False


# ── TC-TR-05: soft_delete ─────────────────────────────────────────────────────

class TestSoftDelete:
    """TC-TR-05"""

    def test_soft_delete_sets_inactive(self, repo):
        _insert_one(repo)
        repo.soft_delete("tmpl_001")
        result = repo.get_by_id("tmpl_001")
        assert result["is_active"] == 0

    def test_soft_deleted_template_excluded_from_active_list(self, repo):
        _insert_one(repo)
        repo.soft_delete("tmpl_001")
        active = repo.list_all(active_only=True)
        assert all(r["id"] != "tmpl_001" for r in active)

    def test_soft_delete_nonexistent_returns_false(self, repo):
        assert repo.soft_delete("not_here") is False


# ── TC-TR-06: hard_delete ─────────────────────────────────────────────────────

class TestHardDelete:
    """TC-TR-06"""

    def test_hard_delete_removes_record(self, repo):
        _insert_one(repo)
        repo.hard_delete("tmpl_001")
        assert repo.get_by_id("tmpl_001") is None

    def test_hard_delete_nonexistent_returns_false(self, repo):
        assert repo.hard_delete("phantom") is False


# ── TC-TR-07: set_default ─────────────────────────────────────────────────────

class TestSetDefault:
    """TC-TR-07"""

    def test_only_one_default_at_a_time(self, repo):
        repo.insert("d1", "Doc 1", content="x")
        repo.insert("d2", "Doc 2", content="y")
        repo.set_default("d1")
        repo.set_default("d2")
        d1 = repo.get_by_id("d1")
        d2 = repo.get_by_id("d2")
        assert d1["is_default"] == 0
        assert d2["is_default"] == 1

    def test_set_default_marks_correct_template(self, repo):
        repo.insert("e1", "E1", content="x")
        repo.set_default("e1")
        assert repo.get_by_id("e1")["is_default"] == 1


# ── TC-TR-08: get_default ─────────────────────────────────────────────────────

class TestGetDefault:
    """TC-TR-08"""

    def test_returns_explicitly_marked_default(self, repo):
        repo.insert("f1", "F1", content="x")
        repo.insert("f2", "F2", content="y")
        repo.set_default("f2")
        result = repo.get_default()
        assert result is not None
        assert result["id"] == "f2"

    def test_falls_back_to_newest_when_no_default_set(self, repo):
        repo.insert("g1", "First", content="x")
        repo.insert("g2", "Second", content="y")
        result = repo.get_default()
        assert result is not None  # Returns some template

    def test_returns_none_on_empty_db(self, repo):
        assert repo.get_default() is None


# ── TC-TR-09: insert with is_default=True clears others ──────────────────────

class TestInsertAsDefault:
    """TC-TR-09"""

    def test_inserting_default_clears_previous_default(self, repo):
        repo.insert("h1", "H1", content="x", is_default=True)
        repo.insert("h2", "H2", content="y", is_default=True)
        h1 = repo.get_by_id("h1")
        h2 = repo.get_by_id("h2")
        assert h1["is_default"] == 0
        assert h2["is_default"] == 1
