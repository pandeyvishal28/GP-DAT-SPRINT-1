"""
routers/template_router.py
API routes for the Template Library.

This router is a thin HTTP layer — all business logic is in
services/template_service.py, database access in
repositories/template_repository.py.

Endpoints:
  POST   /api/v1/templates            — Upload a template file
  POST   /api/v1/templates/from-text  — Create template from raw Markdown (no file)
  GET    /api/v1/templates             — List all active templates
  GET    /api/v1/templates/{id}        — Get template by ID (with content)
  PUT    /api/v1/templates/{id}        — Update template fields
  DELETE /api/v1/templates/{id}        — Soft-delete template
  POST   /api/v1/templates/{id}/set-default  — Mark as default
  POST   /api/v1/templates/{id}/parse  — Re-parse source .docx
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.template_schemas import (
    TemplateDetail,
    TemplateListItem,
    TemplateUpdateRequest,
    TemplateUploadResponse,
    TemplateFromTextRequest,
)
from services.template_service import TemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/templates", tags=["Template Library"])

# Injected from main.py lifespan
_service: TemplateService | None = None


def set_service(service: TemplateService) -> None:
    """Called from main.py lifespan to inject the TemplateService."""
    global _service
    _service = service
    logger.info("Template router: service injected")


def _get_service() -> TemplateService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Template service not initialised")
    return _service


# =============================================================================
#  POST /api/v1/templates  — Upload
# =============================================================================


@router.post(
    "",
    response_model=TemplateUploadResponse,
    summary="Upload a template document",
    description=(
        "Upload a .docx template file. The file is parsed to Markdown and "
        "the content is stored in the database. The original file is kept "
        "on disk as a backup for re-parsing."
    ),
)
async def upload_template(
    file: UploadFile = File(..., description="Template file (.docx)"),
    name: str = Form(..., description="Human-readable template name"),
    description: str = Form(default="", description="Short description of the template"),
    template_type: str = Form(default="Global", description="Template type: Global / Local / Function-specific"),
) -> TemplateUploadResponse:
    service = _get_service()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

    try:
        file_bytes = await file.read()
        result = service.upload_template(
            file_bytes=file_bytes,
            filename=file.filename,
            name=name,
            template_type=template_type,
            description=description or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return TemplateUploadResponse(
        template_id=result["id"],
        name=result["name"],
        type=result["type"],
    )


# =============================================================================
#  POST /api/v1/templates/from-text  — Create from Markdown text
# =============================================================================


@router.post(
    "/from-text",
    response_model=TemplateUploadResponse,
    summary="Create a template from Markdown text",
    description=(
        "Create a template by directly supplying Markdown content. "
        "No file upload required — content is stored in the database as-is."
    ),
)
async def create_template_from_text(
    body: TemplateFromTextRequest,
) -> TemplateUploadResponse:
    service = _get_service()

    try:
        result = service.create_from_text(
            name=body.name,
            content=body.content,
            template_type=body.type,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return TemplateUploadResponse(
        template_id=result["id"],
        name=result["name"],
        type=result["type"],
        message="Template created from text successfully",
    )



# =============================================================================
#  GET /api/v1/templates  — List
# =============================================================================


@router.get(
    "",
    summary="List all templates",
    description="Returns all active templates. Pass ?include_archived=true to also show archived ones.",
)
async def list_templates(include_archived: bool = False) -> dict:
    service = _get_service()
    templates = service.list_templates(active_only=not include_archived)
    return {
        "total": len(templates),
        "templates": [
            TemplateListItem(
                id=t["id"],
                name=t["name"],
                type=t.get("type", "Global"),
                description=t.get("description"),
                is_active=bool(t.get("is_active", 1)),
                is_default=bool(t.get("is_default", 0)),
                original_filename=t.get("original_filename"),
                uploaded_at=t.get("uploaded_at"),
            ).model_dump()
            for t in templates
        ],
    }


# =============================================================================
#  GET /api/v1/templates/{template_id}  — Get by ID
# =============================================================================


@router.get(
    "/{template_id}",
    response_model=TemplateDetail,
    summary="Get template by ID",
    description="Returns the full template including parsed Markdown content.",
)
async def get_template(template_id: str) -> TemplateDetail:
    service = _get_service()

    try:
        t = service.get_template(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return TemplateDetail(
        id=t["id"],
        name=t["name"],
        type=t.get("type", "Global"),
        content=t.get("content"),
        description=t.get("description"),
        is_active=bool(t.get("is_active", 1)),
        is_default=bool(t.get("is_default", 0)),
        original_filename=t.get("original_filename"),
        uploaded_at=t.get("uploaded_at"),
    )


# =============================================================================
#  PUT /api/v1/templates/{template_id}  — Update
# =============================================================================


@router.put(
    "/{template_id}",
    response_model=TemplateDetail,
    summary="Update template",
    description="Partial update — only provided fields are changed.",
)
async def update_template(
    template_id: str,
    body: TemplateUpdateRequest,
) -> TemplateDetail:
    service = _get_service()

    # Collect only the fields that were actually provided
    update_fields = body.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        t = service.update_template(template_id, **update_fields)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return TemplateDetail(
        id=t["id"],
        name=t["name"],
        type=t.get("type", "Global"),
        content=t.get("content"),
        description=t.get("description"),
        is_active=bool(t.get("is_active", 1)),
        is_default=bool(t.get("is_default", 0)),
        original_filename=t.get("original_filename"),
        uploaded_at=t.get("uploaded_at"),
    )


# =============================================================================
#  DELETE /api/v1/templates/{template_id}  — Soft-delete
# =============================================================================


@router.delete(
    "/{template_id}",
    status_code=204,
    summary="Delete template",
    description="Soft-deletes the template (sets is_active=0). The record is preserved for audit.",
)
async def delete_template(template_id: str) -> None:
    service = _get_service()

    try:
        service.delete_template(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")


# =============================================================================
#  POST /api/v1/templates/{template_id}/set-default
# =============================================================================


@router.post(
    "/{template_id}/set-default",
    summary="Set as default template",
    description="Marks this template as the default. Removes default from all others.",
)
async def set_default_template(template_id: str) -> dict:
    service = _get_service()

    try:
        service.set_default(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return {"template_id": template_id, "message": "Template set as default"}


# =============================================================================
#  POST /api/v1/templates/{template_id}/parse  — Re-parse
# =============================================================================


@router.post(
    "/{template_id}/parse",
    response_model=TemplateDetail,
    summary="Re-parse template",
    description=(
        "Re-parses the source .docx file and updates the Markdown content "
        "in the database. Use this if the parser was improved or the source "
        "file was replaced."
    ),
)
async def reparse_template(template_id: str) -> TemplateDetail:
    service = _get_service()

    try:
        t = service.reparse_blueprint(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return TemplateDetail(
        id=t["id"],
        name=t["name"],
        type=t.get("type", "Global"),
        content=t.get("content"),
        description=t.get("description"),
        is_active=bool(t.get("is_active", 1)),
        is_default=bool(t.get("is_default", 0)),
        original_filename=t.get("original_filename"),
        uploaded_at=t.get("uploaded_at"),
    )
