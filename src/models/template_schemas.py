"""
models/template_schemas.py
Pydantic request/response schemas for the Template Library API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Response models ─────────────────────────────────────────────────────


class TemplateListItem(BaseModel):
    """Lightweight summary returned in list endpoints (no content)."""

    id: str
    name: str
    type: str = "Global"
    description: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    original_filename: Optional[str] = None
    uploaded_at: Optional[str] = None


class TemplateDetail(BaseModel):
    """Full template detail including content."""

    id: str
    name: str
    type: str = "Global"
    content: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    original_filename: Optional[str] = None
    uploaded_at: Optional[str] = None


class TemplateUploadResponse(BaseModel):
    """Returned after successful template upload."""

    template_id: str
    name: str
    type: str
    message: str = "Template uploaded and registered successfully"


# ── Request models ──────────────────────────────────────────────────────


class TemplateUpdateRequest(BaseModel):
    """Body for PUT /templates/{id}. All fields optional (partial update)."""

    name: Optional[str] = Field(default=None, description="Human-readable template name")
    type: Optional[str] = Field(default=None, description="Global / Local / Function-specific")
    content: Optional[str] = Field(default=None, description="Markdown template content")
    description: Optional[str] = Field(default=None, description="Short description")


class TemplateFromTextRequest(BaseModel):
    """Body for POST /templates/from-text. Content is user-supplied Markdown."""

    name: str = Field(..., description="Human-readable template name")
    content: str = Field(..., description="Markdown template content (pasted from UI)")
    type: str = Field(default="Global", description="Global / Local / Function-specific")
    description: Optional[str] = Field(default=None, description="Short description (optional)")
