"""
routers/glossary_router.py
REST endpoints for glossary CRUD operations.
"""

from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from models.enums import GlossaryScope
from models.schemas import (
    GlossaryEntryCreate,
    GlossaryEntryResponse,
    GlossaryEntryUpdate,
    GlossaryListResponse,
    GlossaryTranslations,
)
from services.glossary_service import GlossaryService

router = APIRouter(prefix="/api/v1/glossary", tags=["Glossary"])

# ── Service injection (set during app lifespan) ────────────────────────

_service: GlossaryService | None = None


def set_service(service: GlossaryService) -> None:
    global _service
    _service = service


def _get_service() -> GlossaryService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Glossary service not initialized")
    return _service


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=GlossaryEntryResponse,
    status_code=201,
    summary="Create glossary entry",
    description=(
        "Add a new glossary term to the translation glossary.\n\n"
        "**Fields:**\n"
        "- **term** *(required)*: The source word or phrase in English, "
        "e.g. `Active Ingredient`, `Batch Record`.\n"
        "- **scope** *(required)*: Choose one of `global` (applies to all documents), "
        "`local` (applies to a single document), or `functional` (applies to a specific department).\n"
        "- **do_not_translate** *(required)*: Set to `true` if the term must stay in its "
        "original form across all languages (e.g. brand names like `Spiriva`). "
        "When `true`, the `de` and `es` fields are ignored and can be left empty. "
        "Set to `false` if translations should be provided.\n"
        "- **de**: German translation of the term. Required when `do_not_translate` is `false`.\n"
        "- **es**: Spanish translation of the term. Required when `do_not_translate` is `false`.\n"
        "- **notes**: Optional free-text field for additional context, "
        "e.g. `Also known as API in pharma context`.\n\n"
        "**Example — translated term:**\n"
        "```\n"
        "term: Active Ingredient\n"
        "scope: global\n"
        "do_not_translate: false\n"
        "de: Wirkstoff\n"
        "es: Principio activo\n"
        "notes: Also known as API\n"
        "```\n\n"
        "**Example — keep as-is (brand name):**\n"
        "```\n"
        "term: Spiriva Respimat\n"
        "scope: global\n"
        "do_not_translate: true\n"
        "de: (leave empty)\n"
        "es: (leave empty)\n"
        "```"
    ),
)
async def create_glossary_entry(
    term: str = Form(..., description="Glossary term / source word (e.g. 'Active Ingredient')"),
    scope: GlossaryScope = Form(..., description="Scope: global / local / functional"),
    do_not_translate: bool = Form(default=False, description="Check as-is — if true, the term will not be translated"),
    de: str = Form(default="", description="German translation of the glossary term"),
    es: str = Form(default="", description="Spanish translation of the glossary term"),
    notes: str = Form(default="", description="Optional notes or remarks about this entry"),
) -> GlossaryEntryResponse:
    """Add a new glossary term with optional translations."""
    service = _get_service()

    translations = GlossaryTranslations(
        de=de or None,
        es=es or None,
    ) if (de or es) else None

    data = GlossaryEntryCreate(
        term=term,
        scope=scope,
        do_not_translate=do_not_translate,
        translations=translations,
        notes=notes or None,
    )
    entry = service.create_entry(data)
    return GlossaryEntryResponse(**entry)


@router.get(
    "/",
    response_model=GlossaryListResponse,
    summary="List glossary entries",
    description=(
        "Return all active glossary entries.\n\n"
        "**Optional filter:**\n"
        "- **scope**: Pass `global`, `local`, or `functional` as a query parameter "
        "to filter entries by scope. If omitted, all entries are returned.\n\n"
        "**Example:** `GET /api/v1/glossary/?scope=global`"
    ),
)
async def list_glossary_entries(
    scope: Optional[GlossaryScope] = Query(default=None, description="Filter by scope"),
) -> GlossaryListResponse:
    """Return all active glossary entries, optionally filtered by scope."""
    service = _get_service()
    result = service.list_entries(scope=scope.value if scope else None)
    return GlossaryListResponse(
        items=[GlossaryEntryResponse(**item) for item in result["items"]],
        total=result["total"],
    )


@router.post(
    "/import",
    summary="Import glossary from Excel",
    description=(
        "Upload an `.xlsx` file to bulk-import glossary entries.\n\n"
        "**Excel format:**\n"
        "- Row 1 must contain headers: `term`, `scope`, `do_not_translate`, `de`, `es`, `notes`\n"
        "- `term` *(required)*: The source glossary term.\n"
        "- `scope` *(required)*: One of `global`, `local`, `functional`.\n"
        "- `do_not_translate` *(required)*: `true`/`false`, `yes`/`no`, or `1`/`0`.\n"
        "- `de`: German translation (required when `do_not_translate` is false).\n"
        "- `es`: Spanish translation (required when `do_not_translate` is false).\n"
        "- `notes`: Optional remarks.\n\n"
        "**Duplicate handling:** If a term + scope combination already exists, "
        "the existing entry is **updated** with the values from the Excel row.\n\n"
        "Use `GET /api/v1/glossary/template` to download a blank template with the correct format."
    ),
)
async def import_glossary(
    file: UploadFile = File(..., description="Excel file (.xlsx) with glossary entries"),
) -> dict:
    """Bulk-import glossary entries from an uploaded .xlsx file."""
    service = _get_service()

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    contents = await file.read()
    return service.import_from_excel(contents)


@router.get(
    "/export",
    summary="Export glossary to Excel",
    description=(
        "Download all glossary entries as an `.xlsx` file.\n\n"
        "**Optional filter:**\n"
        "- **scope**: Pass `global`, `local`, or `functional` to export only entries "
        "of that scope. If omitted, all entries are exported.\n\n"
        "**Example:** `GET /api/v1/glossary/export?scope=global`"
    ),
)
async def export_glossary(
    scope: Optional[GlossaryScope] = Query(default=None, description="Filter by scope"),
) -> StreamingResponse:
    """Download glossary entries as an .xlsx file."""
    service = _get_service()
    data = service.export_to_excel(scope=scope.value if scope else None)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=glossary_export.xlsx"},
    )


@router.get(
    "/template",
    summary="Download glossary Excel template",
    description=(
        "Download a blank `.xlsx` template with the correct column headers "
        "and two example rows.\n\n"
        "Fill in the template and upload it via `POST /api/v1/glossary/import` "
        "to bulk-import glossary entries."
    ),
)
async def download_template() -> StreamingResponse:
    """Download a blank glossary template .xlsx file."""
    service = _get_service()
    data = service.get_template_excel()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=glossary_template.xlsx"},
    )


@router.get(
    "/{entry_id}",
    response_model=GlossaryEntryResponse,
    summary="Get glossary entry",
    description=(
        "Fetch a single glossary entry by its ID.\n\n"
        "**Path parameter:**\n"
        "- **entry_id**: The unique identifier returned when the entry was created.\n\n"
        "Returns `404` if no entry with the given ID exists."
    ),
)
async def get_glossary_entry(entry_id: str) -> GlossaryEntryResponse:
    """Fetch a single glossary entry by ID."""
    service = _get_service()
    entry = service.get_entry(entry_id)
    return GlossaryEntryResponse(**entry)


@router.put(
    "/{entry_id}",
    response_model=GlossaryEntryResponse,
    summary="Update glossary entry",
    description=(
        "Update an existing glossary entry. Only fill in the fields you want to change; "
        "leave the rest empty.\n\n"
        "**Fields (all optional):**\n"
        "- **term**: New term text.\n"
        "- **scope**: New scope (`global`, `local`, or `functional`).\n"
        "- **do_not_translate**: Set to `true` to mark the term as keep-as-is, "
        "or `false` to require translations.\n"
        "- **de**: Updated German translation.\n"
        "- **es**: Updated Spanish translation.\n"
        "- **notes**: Updated notes.\n\n"
        "**Example — update only the German translation:**\n"
        "```\n"
        "de: Pharmazeutischer Wirkstoff\n"
        "```\n\n"
        "Returns `404` if the entry does not exist, "
        "or `409` if the updated term+scope conflicts with another entry."
    ),
)
async def update_glossary_entry(
    entry_id: str,
    term: str = Form(default="", description="Updated glossary term"),
    scope: Optional[GlossaryScope] = Form(default=None, description="Updated scope: global / local / functional"),
    do_not_translate: bool = Form(default=False, description="Check as-is — true or false"),
    de: str = Form(default="", description="Updated German translation"),
    es: str = Form(default="", description="Updated Spanish translation"),
    notes: str = Form(default="", description="Updated notes or remarks"),
) -> GlossaryEntryResponse:
    """Partially update a glossary entry."""
    service = _get_service()

    # Build update payload from only the fields that were provided
    update_fields: dict = {}
    if term:
        update_fields["term"] = term
    if scope is not None:
        update_fields["scope"] = scope
    update_fields["do_not_translate"] = do_not_translate
    if de or es:
        update_fields["translations"] = GlossaryTranslations(
            de=de or None,
            es=es or None,
        )
    if notes:
        update_fields["notes"] = notes

    data = GlossaryEntryUpdate(**update_fields)
    entry = service.update_entry(entry_id, data)
    return GlossaryEntryResponse(**entry)


@router.delete(
    "/{entry_id}",
    summary="Delete glossary entry",
    description=(
        "Permanently delete a glossary entry by its ID.\n\n"
        "**Path parameter:**\n"
        "- **entry_id**: The unique identifier of the entry to delete.\n\n"
        "Returns `404` if no entry with the given ID exists. "
        "This action cannot be undone."
    ),
)
async def delete_glossary_entry(entry_id: str) -> dict[str, str]:
    """Delete a glossary entry permanently."""
    service = _get_service()
    return service.delete_entry(entry_id)
