"""
tests/test_template_router.py
Unit tests for routers/template_router.py

Test IDs: TC-TRT-01 → TC-TRT-08

Uses FastAPI's TestClient with TemplateService fully mocked so
no database or file system is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.template_router as template_router_module
from routers.template_router import router


# ── App fixture ────────────────────────────────────────────────────────────────

def _sample_template(**overrides) -> dict:
    """Build a minimal template dict for mock returns."""
    base = {
        "id": "tmpl_abc123",
        "name": "Sample Template",
        "type": "Global",
        "content": "# CHAPTER: Overview\n\nSome content.",
        "description": "A sample template",
        "is_active": 1,
        "is_default": 0,
        "original_filename": "Template.docx",
        "uploaded_at": "2026-04-07T10:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_service():
    """Return a MagicMock that stands in for TemplateService."""
    svc = MagicMock()
    svc.list_templates.return_value = [_sample_template()]
    svc.get_template.return_value = _sample_template()
    svc.upload_template.return_value = _sample_template()
    svc.create_from_text.return_value = _sample_template(id="text_tmpl_001", name="Text Template")
    svc.update_template.return_value = _sample_template(name="Updated Name")
    svc.delete_template.return_value = None
    svc.set_default.return_value = None
    svc.reparse_blueprint.return_value = _sample_template()
    return svc


@pytest.fixture
def client(mock_service):
    """Create a TestClient with the mock service injected."""
    app = FastAPI()
    app.include_router(router)
    template_router_module.set_service(mock_service)
    return TestClient(app)


# ── TC-TRT-01: GET /api/v1/templates ─────────────────────────────────────────

class TestListTemplates:
    """TC-TRT-01"""

    def test_returns_200_and_list(self, client, mock_service):
        response = client.get("/api/v1/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert data["total"] == 1
        assert data["templates"][0]["id"] == "tmpl_abc123"

    def test_calls_service_with_active_only_true_by_default(self, client, mock_service):
        client.get("/api/v1/templates")
        mock_service.list_templates.assert_called_once_with(active_only=True)

    def test_include_archived_param_passes_active_only_false(self, client, mock_service):
        client.get("/api/v1/templates?include_archived=true")
        mock_service.list_templates.assert_called_once_with(active_only=False)


# ── TC-TRT-02: GET /api/v1/templates/{id} ─────────────────────────────────────

class TestGetTemplate:
    """TC-TRT-02"""

    def test_returns_200_for_existing_template(self, client, mock_service):
        response = client.get("/api/v1/templates/tmpl_abc123")
        assert response.status_code == 200
        assert response.json()["id"] == "tmpl_abc123"

    def test_returns_404_when_service_raises_value_error(self, client, mock_service):
        mock_service.get_template.side_effect = ValueError("Not found")
        response = client.get("/api/v1/templates/missing_id")
        assert response.status_code == 404

    def test_response_includes_content_field(self, client, mock_service):
        response = client.get("/api/v1/templates/tmpl_abc123")
        assert "content" in response.json()


# ── TC-TRT-03: POST /api/v1/templates (file upload) ──────────────────────────

class TestUploadTemplate:
    """TC-TRT-03"""

    def test_returns_200_with_valid_docx(self, client, mock_service):
        dummy_bytes = b"PK\x03\x04"  # minimal ZIP/docx magic bytes
        response = client.post(
            "/api/v1/templates",
            files={"file": ("template.docx", dummy_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"name": "My Template", "description": "Test", "template_type": "Global"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "template_id" in data
        assert "name" in data

    def test_returns_422_when_filename_missing(self, client, mock_service):
        # FastAPI File() with no filename — simulate via empty filename
        response = client.post(
            "/api/v1/templates",
            files={"file": ("", b"content", "application/octet-stream")},
            data={"name": "Test"},
        )
        assert response.status_code == 422

    def test_returns_400_on_service_value_error(self, client, mock_service):
        mock_service.upload_template.side_effect = ValueError("Unsupported file type '.txt'")
        response = client.post(
            "/api/v1/templates",
            files={"file": ("file.txt", b"content", "text/plain")},
            data={"name": "Bad Upload"},
        )
        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]


# ── TC-TRT-04: POST /api/v1/templates/from-text ───────────────────────────────

class TestCreateFromText:
    """TC-TRT-04"""

    def test_returns_200_with_valid_body(self, client, mock_service):
        response = client.post(
            "/api/v1/templates/from-text",
            json={"name": "Text Template", "content": "# CHAPTER: Intro\n\nContent here.", "type": "Global"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "template_id" in data
        assert data["message"] == "Template created from text successfully"

    def test_calls_service_create_from_text(self, client, mock_service):
        client.post(
            "/api/v1/templates/from-text",
            json={"name": "Text Template", "content": "# Content", "type": "Local"},
        )
        mock_service.create_from_text.assert_called_once()
        call_kwargs = mock_service.create_from_text.call_args.kwargs
        assert call_kwargs["name"] == "Text Template"
        assert call_kwargs["template_type"] == "Local"

    def test_returns_422_when_name_missing(self, client, mock_service):
        response = client.post(
            "/api/v1/templates/from-text",
            json={"content": "# Content"},
        )
        assert response.status_code == 422

    def test_returns_422_when_content_missing(self, client, mock_service):
        response = client.post(
            "/api/v1/templates/from-text",
            json={"name": "No Content Template"},
        )
        assert response.status_code == 422


# ── TC-TRT-05: PUT /api/v1/templates/{id} ────────────────────────────────────

class TestUpdateTemplate:
    """TC-TRT-05"""

    def test_returns_200_with_valid_update(self, client, mock_service):
        response = client.put(
            "/api/v1/templates/tmpl_abc123",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_returns_400_when_no_fields_provided(self, client, mock_service):
        response = client.put("/api/v1/templates/tmpl_abc123", json={})
        assert response.status_code == 400

    def test_returns_404_when_template_not_found(self, client, mock_service):
        mock_service.update_template.side_effect = ValueError("Not found")
        response = client.put(
            "/api/v1/templates/missing_id",
            json={"name": "New Name"},
        )
        assert response.status_code == 404


# ── TC-TRT-06: DELETE /api/v1/templates/{id} ─────────────────────────────────

class TestDeleteTemplate:
    """TC-TRT-06"""

    def test_returns_204_on_success(self, client, mock_service):
        response = client.delete("/api/v1/templates/tmpl_abc123")
        assert response.status_code == 204

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.delete_template.side_effect = ValueError("Not found")
        response = client.delete("/api/v1/templates/ghost_id")
        assert response.status_code == 404


# ── TC-TRT-07: POST /api/v1/templates/{id}/set-default ───────────────────────

class TestSetDefaultTemplate:
    """TC-TRT-07"""

    def test_returns_200_and_confirmation(self, client, mock_service):
        response = client.post("/api/v1/templates/tmpl_abc123/set-default")
        assert response.status_code == 200
        data = response.json()
        assert data["template_id"] == "tmpl_abc123"
        assert "default" in data["message"].lower()

    def test_returns_404_when_template_not_found(self, client, mock_service):
        mock_service.set_default.side_effect = ValueError("Not found")
        response = client.post("/api/v1/templates/ghost_id/set-default")
        assert response.status_code == 404


# ── TC-TRT-08: POST /api/v1/templates/{id}/parse ─────────────────────────────

class TestReparseTemplate:
    """TC-TRT-08"""

    def test_returns_200_on_success(self, client, mock_service):
        response = client.post("/api/v1/templates/tmpl_abc123/parse")
        assert response.status_code == 200
        assert response.json()["id"] == "tmpl_abc123"

    def test_returns_404_when_source_not_found(self, client, mock_service):
        mock_service.reparse_blueprint.side_effect = ValueError("Source file not found")
        response = client.post("/api/v1/templates/tmpl_abc123/parse")
        assert response.status_code == 404

    def test_calls_reparse_with_correct_id(self, client, mock_service):
        client.post("/api/v1/templates/tmpl_abc123/parse")
        mock_service.reparse_blueprint.assert_called_once_with("tmpl_abc123")


# ── TC-TRT-09: Service not initialised ───────────────────────────────────────

class TestServiceNotInitialised:
    """TC-TRT-09 — Guard: 503 when service is None."""

    def test_returns_503_when_service_missing(self):
        app = FastAPI()
        app.include_router(router)
        template_router_module._service = None  # force uninitialised
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/templates")
        assert response.status_code == 503
