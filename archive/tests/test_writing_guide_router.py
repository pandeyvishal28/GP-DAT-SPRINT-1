"""
tests/test_writing_guide_router.py
Unit tests for routers/writing_guide_router.py

Test IDs: TC-WGRT-01 → TC-WGRT-07

Uses FastAPI's TestClient with WritingGuideService fully mocked so
no database or file system is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.writing_guide_router as writing_guide_router_module
from routers.writing_guide_router import router


# ── App fixture ────────────────────────────────────────────────────────────────

def _sample_guide(**overrides) -> dict:
    """Build a minimal writing guide dict for mock returns."""
    base = {
        "id": "wg_abc123",
        "name": "Sample Guide",
        "content": "Rule 1",
        "description": "A sample guide",
        "is_active": 1,
        "is_default": 0,
        "original_filename": "Guide.pdf",
        "uploaded_at": "2026-04-08T10:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_service():
    """Return a MagicMock that stands in for WritingGuideService."""
    svc = MagicMock()
    svc.list_guides.return_value = [_sample_guide()]
    svc.get_guide.return_value = _sample_guide()
    svc.upload_guide.return_value = _sample_guide()
    svc.update_guide.return_value = _sample_guide(name="Updated Name")
    svc.delete_guide.return_value = None
    svc.set_default.return_value = None
    return svc


@pytest.fixture
def client(mock_service):
    """Create a TestClient with the mock service injected."""
    app = FastAPI()
    app.include_router(router)
    writing_guide_router_module.set_service(mock_service)
    return TestClient(app)


# ── TC-WGRT-01: GET /api/v1/writing-guides ───────────────────────────────────

class TestListGuides:
    """TC-WGRT-01"""

    def test_returns_200_and_list(self, client, mock_service):
        response = client.get("/api/v1/writing-guides")
        assert response.status_code == 200
        data = response.json()
        assert "writing_guides" in data
        assert data["total"] == 1
        assert data["writing_guides"][0]["id"] == "wg_abc123"

    def test_calls_service_with_active_only_true_by_default(self, client, mock_service):
        client.get("/api/v1/writing-guides")
        mock_service.list_guides.assert_called_once_with(active_only=True)

    def test_include_archived_param_passes_active_only_false(self, client, mock_service):
        client.get("/api/v1/writing-guides?include_archived=true")
        mock_service.list_guides.assert_called_once_with(active_only=False)


# ── TC-WGRT-02: GET /api/v1/writing-guides/{id} ──────────────────────────────

class TestGetGuide:
    """TC-WGRT-02"""

    def test_returns_200_for_existing_guide(self, client, mock_service):
        response = client.get("/api/v1/writing-guides/wg_abc123")
        assert response.status_code == 200
        assert response.json()["id"] == "wg_abc123"

    def test_returns_404_when_service_raises_value_error(self, client, mock_service):
        mock_service.get_guide.side_effect = ValueError("Not found")
        response = client.get("/api/v1/writing-guides/missing_id")
        assert response.status_code == 404

    def test_response_includes_content_field(self, client, mock_service):
        response = client.get("/api/v1/writing-guides/wg_abc123")
        assert "content" in response.json()


# ── TC-WGRT-03: POST /api/v1/writing-guides (file upload) ────────────────────

class TestUploadGuide:
    """TC-WGRT-03"""

    def test_returns_200_with_valid_pdf(self, client, mock_service):
        dummy_bytes = b"%PDF-1.4"  # minimal pdf magic bytes
        response = client.post(
            "/api/v1/writing-guides",
            files={"file": ("guide.pdf", dummy_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "guide_id" in data
        assert "name" in data
        # Content extraction happens in background, so has_content is False
        assert data["has_content"] is False

    def test_upload_response_contains_message(self, client, mock_service):
        response = client.post(
            "/api/v1/writing-guides",
            files={"file": ("guide.pdf", b"%PDF-1.4", "application/pdf")},
        )
        data = response.json()
        assert "message" in data
        assert "extraction" in data["message"].lower() or "upload" in data["message"].lower()

    def test_returns_400_when_filename_missing(self, client, mock_service):
        response = client.post(
            "/api/v1/writing-guides",
            files={"file": ("", b"content", "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "must have a filename" in response.json()["detail"]

    def test_returns_400_on_service_value_error(self, client, mock_service):
        mock_service.upload_guide.side_effect = ValueError("Unsupported file type '.xyz'")
        response = client.post(
            "/api/v1/writing-guides",
            files={"file": ("file.xyz", b"content", "text/plain")},
        )
        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]


# ── TC-WGRT-04: PUT /api/v1/writing-guides/{id} ──────────────────────────────

class TestUpdateGuide:
    """TC-WGRT-04"""

    def test_returns_200_with_valid_update(self, client, mock_service):
        response = client.put(
            "/api/v1/writing-guides/wg_abc123",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_returns_400_when_no_fields_provided(self, client, mock_service):
        response = client.put("/api/v1/writing-guides/wg_abc123", json={})
        assert response.status_code == 400

    def test_returns_404_when_guide_not_found(self, client, mock_service):
        mock_service.update_guide.side_effect = ValueError("Not found")
        response = client.put(
            "/api/v1/writing-guides/missing_id",
            json={"name": "New Name"},
        )
        assert response.status_code == 404


# ── TC-WGRT-05: DELETE /api/v1/writing-guides/{id} ───────────────────────────

class TestDeleteGuide:
    """TC-WGRT-05"""

    def test_returns_204_on_success(self, client, mock_service):
        response = client.delete("/api/v1/writing-guides/wg_abc123")
        assert response.status_code == 204

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.delete_guide.side_effect = ValueError("Not found")
        response = client.delete("/api/v1/writing-guides/ghost_id")
        assert response.status_code == 404


# ── TC-WGRT-06: POST /api/v1/writing-guides/{id}/set-default ─────────────────

class TestSetDefaultGuide:
    """TC-WGRT-06"""

    def test_returns_200_and_confirmation(self, client, mock_service):
        response = client.post("/api/v1/writing-guides/wg_abc123/set-default")
        assert response.status_code == 200
        data = response.json()
        assert data["guide_id"] == "wg_abc123"
        assert "default" in data["message"].lower()

    def test_returns_404_when_guide_not_found(self, client, mock_service):
        mock_service.set_default.side_effect = ValueError("Not found")
        response = client.post("/api/v1/writing-guides/ghost_id/set-default")
        assert response.status_code == 404


# ── TC-WGRT-07: Service not initialised ──────────────────────────────────────

class TestServiceNotInitialised:
    """TC-WGRT-07 — Guard: 503 when service is None."""

    def test_returns_503_when_service_missing(self):
        app = FastAPI()
        app.include_router(router)
        writing_guide_router_module._service = None  # force uninitialised
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/writing-guides")
        assert response.status_code == 503
