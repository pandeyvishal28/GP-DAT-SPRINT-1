"""
models/writing_guide_schemas.py
Pydantic request/response schemas for the Writing Guides API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Response models ─────────────────────────────────────────────────────


class WritingGuideListItem(BaseModel):
    """Lightweight summary for list endpoint (no content)."""

    id: str
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    has_content: bool = False
    original_filename: Optional[str] = None
    uploaded_at: Optional[str] = None


class WritingGuideDetail(BaseModel):
    """Full writing guide detail including content."""

    id: str
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    has_content: bool = False
    original_filename: Optional[str] = None
    uploaded_at: Optional[str] = None


class WritingGuideUploadResponse(BaseModel):
    """Returned after successful writing guide upload."""

    guide_id: str
    name: str
    title: Optional[str] = None
    has_content: bool = False
    message: str = "Writing guide uploaded successfully"


# ── Request models ──────────────────────────────────────────────────────


class WritingGuideUpdateRequest(BaseModel):
    """Body for PUT /writing-guides/{id}. All fields optional."""

    title: Optional[str] = Field(default=None, description="Extracted / user-corrected title")
    description: Optional[str] = Field(default=None, description="Short description (optional)")
    content: Optional[str] = Field(default=None, description="Markdown content")
