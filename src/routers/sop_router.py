"""
routers/sop_router.py
API routes for the SOP (Standard Operating Procedure) library.

Endpoints:
  POST /api/v1/sops/upload  — Upload an SOP file and register it in the database
  GET  /api/v1/sops         — List all registered SOPs
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.sop_service import DuplicateSopError, SopService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sops", tags=["SOP Library"])

# Injected from main.py lifespan
_service: SopService | None = None


def set_service(service: SopService) -> None:
    """Called from main.py lifespan to inject the shared SOP service."""
    global _service
    _service = service
    logger.info("SOP router: service injected")


def _get_service() -> SopService:
    if _service is None:
        raise HTTPException(status_code=503, detail="SOP service not initialised yet")
    return _service


# =============================================================================
#  POST /api/v1/sops/upload
# =============================================================================


@router.post(
    "/upload",
    summary="Upload an SOP document",
    description=(
        "Upload a Standard Operating Procedure file (.pdf, .docx, .doc, .txt). "
        "The file is saved to data/sample_inputs/ and registered in the database. "
        "If the SOP already exists a 409 is returned. Re-submit with action='update' to overwrite."
    ),
)
async def upload_sop(
    file: UploadFile = File(..., description="SOP file — .pdf, .docx, .doc, or .txt"),
    action: str = Form("", description="Set to 'update' to overwrite an existing SOP."),
    version: str = Form(
        "",
        description="Optional version string (e.g. '2.0'). Auto-incremented if not provided on re-upload.",
    ),
) -> dict:
    service = _get_service()
    try:
        return await service.upload_sop(file, action=action, version=version)
    except DuplicateSopError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"SOP '{exc.sop_id}' already exists at version {exc.existing_version}.",
                "sop_id": exc.sop_id,
                "existing_version": exc.existing_version,
                "hint": "Re-submit with action='update' to overwrite, or skip to cancel.",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
#  GET /api/v1/sops
# =============================================================================


@router.get(
    "",
    summary="List all SOP documents",
    description="Returns all registered SOP documents ordered by most recently updated.",
)
async def list_sops() -> dict:
    service = _get_service()
    return service.list_sops()


# =============================================================================
#  GET /api/v1/sops/{sop_id}
# =============================================================================


@router.get(
    "/{sop_id}",
    summary="Get SOP details",
    description="Returns full details of a single SOP document by its ID.",
)
async def get_sop(sop_id: str) -> dict:
    service = _get_service()
    sop = service.get_sop(sop_id)
    if sop is None:
        raise HTTPException(status_code=404, detail=f"SOP '{sop_id}' not found")
    return sop


# =============================================================================
#  DELETE /api/v1/sops/{sop_id}
# =============================================================================


@router.delete(
    "/{sop_id}",
    summary="Delete an SOP document",
    description="Deletes an SOP document from the database and removes its file from disk.",
)
async def delete_sop(sop_id: str) -> dict:
    service = _get_service()
    if not service.delete_sop(sop_id):
        raise HTTPException(status_code=404, detail=f"SOP '{sop_id}' not found")
    return {"sop_id": sop_id, "message": "SOP deleted successfully"}
