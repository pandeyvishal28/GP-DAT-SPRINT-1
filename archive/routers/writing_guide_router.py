"""
routers/writing_guide_router.py
API routes for Writing Guides.

Thin HTTP layer — all business logic lives in
services/writing_guide_service.py.

Endpoints:
  GET    /api/v1/writing-guides             — List all active guides
  POST   /api/v1/writing-guides             — Upload a guide file
  GET    /api/v1/writing-guides/{id}        — Get guide detail
  PUT    /api/v1/writing-guides/{id}        — Update guide fields
  DELETE /api/v1/writing-guides/{id}        — Soft-delete
  POST   /api/v1/writing-guides/{id}/set-default — Mark as default
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from models.writing_guide_schemas import (
    WritingGuideDetail,
    WritingGuideListItem,
    WritingGuideUpdateRequest,
    WritingGuideUploadResponse,
)
from services.writing_guide_service import WritingGuideService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/writing-guides", tags=["Writing Guides"])

# Injected from main.py lifespan
_service: WritingGuideService | None = None


def set_service(service: WritingGuideService) -> None:
    """Called from main.py lifespan to inject the WritingGuideService."""
    global _service
    _service = service
    logger.info("Writing guide router: service injected")


def _get_service() -> WritingGuideService:
    if _service is None:
        raise HTTPException(
            status_code=503, detail="Writing guide service not initialised"
        )
    return _service


# =============================================================================
#  GET /api/v1/writing-guides — List
# =============================================================================


@router.get(
    "",
    summary="List all writing guides",
    description=(
        "Returns all active writing guides. "
        "Pass ?include_archived=true to also show archived ones."
    ),
)
async def list_guides(include_archived: bool = False) -> dict:
    service = _get_service()
    guides = service.list_guides(active_only=not include_archived)
    return {
        "total": len(guides),
        "writing_guides": [
            WritingGuideListItem(
                id=g["id"],
                name=g["name"],
                description=g.get("description"),
                is_active=bool(g.get("is_active", 1)),
                is_default=bool(g.get("is_default", 0)),
                original_filename=g.get("original_filename"),
                uploaded_at=g.get("uploaded_at"),
            ).model_dump()
            for g in guides
        ],
    }


# =============================================================================
#  POST /api/v1/writing-guides — Upload
# =============================================================================


@router.post(
    "",
    response_model=WritingGuideUploadResponse,
    summary="Upload a writing guide",
    description=(
        "Upload a PDF, DOCX, or TXT writing guide file. "
        "The file is stored for future parsing. Content is initially empty "
        "until parsing is run."
    ),
)
async def upload_guide(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Writing guide file (PDF/DOCX/TXT)"),
    name: str = Form(..., description="Human-readable guide name"),
    description: str = Form(default="", description="Short description (optional)"),
) -> WritingGuideUploadResponse:
    service = _get_service()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

    try:
        file_bytes = await file.read()
        result = service.upload_guide(
            file_bytes=file_bytes,
            filename=file.filename,
            name=name,
            description=description or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Schedule background parsing of the uploaded file
    background_tasks.add_task(service.parse_and_update_guide, result["id"])

    return WritingGuideUploadResponse(
        guide_id=result["id"],
        name=result["name"],
        has_content=False,
        message="Writing guide uploaded. Content extraction in progress.",
    )


# =============================================================================
#  GET /api/v1/writing-guides/{guide_id} — Detail
# =============================================================================


@router.get(
    "/{guide_id}",
    response_model=WritingGuideDetail,
    summary="Get writing guide by ID",
    description="Returns the full guide including parsed content (if available).",
)
async def get_guide(guide_id: str) -> WritingGuideDetail:
    service = _get_service()

    try:
        g = service.get_guide(guide_id)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Writing guide '{guide_id}' not found"
        )

    return WritingGuideDetail(
        id=g["id"],
        name=g["name"],
        description=g.get("description"),
        content=g.get("content"),
        is_active=bool(g.get("is_active", 1)),
        is_default=bool(g.get("is_default", 0)),
        original_filename=g.get("original_filename"),
        uploaded_at=g.get("uploaded_at"),
    )


# =============================================================================
#  PUT /api/v1/writing-guides/{guide_id} — Update
# =============================================================================


@router.put(
    "/{guide_id}",
    response_model=WritingGuideDetail,
    summary="Update writing guide",
    description="Partial update — only provided fields are changed.",
)
async def update_guide(
    guide_id: str,
    body: WritingGuideUpdateRequest,
) -> WritingGuideDetail:
    service = _get_service()

    update_fields = body.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        g = service.update_guide(guide_id, **update_fields)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Writing guide '{guide_id}' not found"
        )

    return WritingGuideDetail(
        id=g["id"],
        name=g["name"],
        description=g.get("description"),
        content=g.get("content"),
        is_active=bool(g.get("is_active", 1)),
        is_default=bool(g.get("is_default", 0)),
        original_filename=g.get("original_filename"),
        uploaded_at=g.get("uploaded_at"),
    )


# =============================================================================
#  DELETE /api/v1/writing-guides/{guide_id} — Soft-delete
# =============================================================================


@router.delete(
    "/{guide_id}",
    status_code=204,
    summary="Delete writing guide",
    description="Soft-deletes the guide (sets is_active=0).",
)
async def delete_guide(guide_id: str) -> None:
    service = _get_service()

    try:
        service.delete_guide(guide_id)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Writing guide '{guide_id}' not found"
        )


# =============================================================================
#  POST /api/v1/writing-guides/{guide_id}/set-default
# =============================================================================


@router.post(
    "/{guide_id}/set-default",
    summary="Set as default writing guide",
    description="Marks this guide as the default. Removes default from all others.",
)
async def set_default_guide(guide_id: str) -> dict:
    service = _get_service()

    try:
        service.set_default(guide_id)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Writing guide '{guide_id}' not found"
        )

    return {"guide_id": guide_id, "message": "Writing guide set as default"}
