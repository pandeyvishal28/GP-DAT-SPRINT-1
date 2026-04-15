"""
models/schemas.py
Pydantic models for request/response validation, agent I/O, and internal data structures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.enums import (CritiqueVerdict, DocumentStatus, GlossaryScope,
                          Language)

# =============================================================================
#  API Request Models
# =============================================================================


class GenerationRequest(BaseModel):
    """Request payload for GP Doc generation (JSON body, used alongside file uploads)."""

    template_id: str = Field(
        default="", description="Template to use (empty = default/latest)"
    )
    user_prompt: str = Field(
        default="", description="Freeform user instructions for document generation"
    )
    source_language: Language = Field(
        default=Language.ENGLISH, description="Language of the input data"
    )


class TemplateListItem(BaseModel):
    """Single template entry returned by the template listing endpoint."""

    id: str = Field(..., description="Template identifier")
    filename: str = Field(..., description="Template filename on disk")
    type: str = Field(
        default="main_gp_doc",
        description="Template type: main_gp_doc or associated_document",
    )
    version: str = Field(default="1.0")
    is_default: bool = Field(
        default=False,
        description="Whether this is the currently active default template",
    )
    uploaded_at: Optional[str] = Field(default=None)


class GWPInfo(BaseModel):
    """Metadata about the currently active GWP version."""

    doc_number: str = Field(..., description="GWP document number, e.g. BI-VQD-24416-G")
    version: str = Field(..., description="GWP version, e.g. 3.0")
    title: str = Field(default="")
    effective_date: str = Field(default="")
    is_active: bool = Field(default=True)


class AdaptationRequest(BaseModel):
    """Request payload for adapting an older document to a new template."""

    old_document_content: str = Field(
        ..., description="Full text content of the older document"
    )
    new_template_id: str = Field(..., description="Target template ID to adapt to")
    preserve_sections: Optional[list[str]] = Field(
        default=None,
        description="Specific section names to ensure are preserved during adaptation",
    )


class SOPTranslationRequest(BaseModel):
    """Request payload for translating a pharma/healthcare SOP document."""

    sop_document: str = Field(
        ...,
        min_length=1,
        description="Full text content of the SOP document to translate",
    )
    gwp_document: Optional[str] = Field(
        default=None,
        description="Optional GWP (Good Writing Practice) guidelines to apply during translation",
    )
    user_prompt: Optional[str] = Field(
        default=None,
        description="Optional user instructions to adjust translation style (must not change meaning)",
    )
    target_language: Language = Field(
        ...,
        description="Target language for translation (German or Spanish)",
    )

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: Language) -> Language:
        if v not in (Language.GERMAN, Language.SPANISH):
            raise ValueError("target_language must be 'de' (German) or 'es' (Spanish)")
        return v


# =============================================================================
#  API Response Models
# =============================================================================


class JobResponse(BaseModel):
    """Response returned when a pipeline job is initiated."""

    job_id: str = Field(..., description="Unique identifier for the processing job")
    status: DocumentStatus = Field(..., description="Current status of the job")
    message: str = Field(
        default="Job accepted", description="Human-readable status message"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentResponse(BaseModel):
    """Response containing a completed document."""

    job_id: str
    status: DocumentStatus
    content: str = Field(default="", description="Final document content (text)")
    document_path: str = Field(
        default="", description="Path to the generated .docx file"
    )
    download_url: str = Field(
        default="", description="API endpoint to download the generated file"
    )
    template_id: Optional[str] = None
    language: Language = Language.ENGLISH
    metadata: Optional[dict[str, Any]] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)


class SOPTranslationResponse(BaseModel):
    """Response containing the translated SOP document."""

    translated_sop: str = Field(
        ..., description="Fully translated SOP document with preserved formatting"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional translator notes (e.g. untranslatable terms, ambiguous passages)",
    )
    document_path: str = Field(
        default="", description="Path to the saved .docx translation output file"
    )


class SOPListItem(BaseModel):
    """Single SOP entry returned by the SOP listing endpoint."""

    id: str = Field(..., description="SOP identifier (derived from filename)")
    filename: str = Field(..., description="SOP filename on disk")


# =============================================================================
#  Internal Models (used between agents)
# =============================================================================


class TemplateInfo(BaseModel):
    """Parsed template data used by agents."""

    template_id: str = ""
    template_type: str = "main_gp_doc"
    source_file: str = ""
    chapter_count: int = 0
    chapters: list[TemplateChapter] = Field(default_factory=list)
    prompt_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TemplateChapter(BaseModel):
    """Single chapter within a parsed .docx GP template."""

    number: int
    title: str
    instructions: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    body_text: list[str] = Field(default_factory=list)
    list_items: list[str] = Field(default_factory=list)
    has_table: bool = False
    table_headers: list[list[str]] = Field(default_factory=list)
    is_optional: bool = False


# Rebuild TemplateInfo to resolve the forward reference to TemplateChapter
TemplateInfo.model_rebuild()


class CritiqueResult(BaseModel):
    """Output of the Critic Agent's quality evaluation."""

    verdict: CritiqueVerdict
    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Quality score from 0.0 to 1.0"
    )
    section_scores: Optional[dict[str, float]] = Field(
        default=None,
        description="Per-section quality scores",
    )
    issues: list[str] = Field(
        default_factory=list, description="List of identified issues"
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Improvement suggestions"
    )
    requires_human_review: bool = False
    review_reason: Optional[str] = None


class EnrichedContext(BaseModel):
    """Output of the Context Agent — enriched understanding of the user request."""

    model_config = {
        "extra": "forbid"
    }
    '''Ensures additionalProperties: false at top level'''

    detected_intent: str = Field(..., description="Detected user intent")
    document_title: str = Field(
        default="",
        description=(
            "A natural, professional title for the document being generated"
            " (e.g. 'Clinical Summary for Spiriva Respimat')"
        ),
    )
    key_topics: list[str] = Field(default_factory=list)
    extracted_entities: dict[str, str] = Field(
        default_factory=dict,
        description="Key entities extracted from input, e.g. product name, indication",
    )
    input_summary: str = Field(
        default="", description="Summarised version of the user input"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    additional_context: dict[str, str] = Field(
        default_factory=dict,
        description="Any extra context key-value pairs",
    )


class AdaptedContentSection(BaseModel):
    """A single adapted section generated by the Reasoning Agent."""

    section_id: str = Field(
        ...,
        description=(
            "The template placeholder or chapter ID this content"
            " belongs to (e.g. 'definitions_abbreviations')"
        ),
    )
    section_title: str = Field(
        ...,
        description=(
            "The proper human-readable chapter heading exactly as it appears"
            " in the template (e.g. 'DEFINITIONS & ABBREVIATIONS')"
        ),
    )
    content: str = Field(
        ..., description="The generated Markdown content adapted for this section"
    )
    original_excerpt: str = Field(
        default="", description="Relevant text extracted from the old document"
    )
    changes_made: str = Field(
        default="",
        description="Summary of syntactic or structural changes made to the original text",
    )
    reasoning: str = Field(
        default="", description="Why this content was generated or modified in this way"
    )


class AdaptationMap(BaseModel):
    """Full mapping output containing all adapted sections for the document."""

    sections: list[AdaptedContentSection] = Field(
        ..., description="List of all adapted sections"
    )
    overall_mapping_strategy: str = Field(
        default="",
        description="High-level strategy used for mapping the old document to the new template",
    )


# =============================================================================
#  Translation Batch Models (structured LLM output for per-element translation)
# =============================================================================


class TranslationItem(BaseModel):
    """A single text fragment and its translation."""

    id: str = Field(..., description="Unique identifier for this text fragment")
    translated: str = Field(..., description="Translated text")


class TranslationBatch(BaseModel):
    """Batch of translated text fragments returned by the LLM."""

    items: list[TranslationItem] = Field(
        ..., description="List of translated text fragments"
    )


# =============================================================================
#  Glossary Models
# =============================================================================


class GlossaryTranslations(BaseModel):
    """Translation fields for a glossary term. Currently supports German and Spanish."""

    de: Optional[str] = Field(
        default=None,
        description="German translation of the glossary term",
        json_schema_extra={"example": "Wirkstoff"},
    )
    es: Optional[str] = Field(
        default=None,
        description="Spanish translation of the glossary term",
        json_schema_extra={"example": "Principio activo"},
    )


class GlossaryEntryCreate(BaseModel):
    """
    Request payload for creating a glossary entry.

    - **term**: The source word / phrase to be added to the glossary.
    - **scope**: Where this term applies — `global` (all documents),
      `local` (single document), or `functional` (specific department).
    - **do_not_translate**: Check this box if the term must be kept as-is
      in every language (e.g. brand names). When checked, translation
      fields are ignored.
    - **translations**: Provide the German (`de`) and Spanish (`es`)
      translations. Required unless *do_not_translate* is checked.
    - **comments**: Free-text English comment for additional context.
    - **de_comments**: German-specific comment (only when `de` translation is provided).
    - **es_comments**: Spanish-specific comment (only when `es` translation is provided).
    """

    term: str = Field(
        ...,
        min_length=1,
        description="The glossary term / source word (e.g. 'Active Ingredient')",
        json_schema_extra={"example": "Active Ingredient"},
    )
    scope: GlossaryScope = Field(
        ...,
        description="Scope level: 'global', 'local', or 'functional'",
    )
    do_not_translate: bool = Field(
        default=False,
        description=(
            "Check as-is flag. If true the term will not be translated "
            "and translation fields can be left empty."
        ),
    )
    translations: Optional[GlossaryTranslations] = Field(
        default=None,
        description=(
            "German and Spanish translations. "
            "Required when do_not_translate is false."
        ),
    )
    comments: Optional[str] = Field(
        default=None,
        description="Optional English comment for additional context",
        json_schema_extra={"example": "Also known as API in pharma context"},
    )
    de_comments: Optional[str] = Field(
        default=None,
        description="German-specific comment (only when de translation is provided)",
    )
    es_comments: Optional[str] = Field(
        default=None,
        description="Spanish-specific comment (only when es translation is provided)",
    )

    @model_validator(mode="after")
    def validate_translations(self) -> GlossaryEntryCreate:
        if self.do_not_translate:
            self.translations = None
            self.de_comments = None
            self.es_comments = None
        elif not self.translations or (
            not self.translations.de and not self.translations.es
        ):
            raise ValueError(
                "At least one translation (de or es) is required when "
                "do_not_translate is false"
            )
        # Silently clear language-specific comments when translation is absent
        if self.de_comments and (not self.translations or not self.translations.de):
            self.de_comments = None
        if self.es_comments and (not self.translations or not self.translations.es):
            self.es_comments = None
        return self


class GlossaryEntryUpdate(BaseModel):
    """
    Request payload for updating a glossary entry (partial update).

    Only include the fields you want to change.
    """

    term: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Updated glossary term",
    )
    scope: Optional[GlossaryScope] = Field(
        default=None,
        description="Updated scope: 'global', 'local', or 'functional'",
    )
    do_not_translate: bool = Field(
        default=False,
        description="Check as-is flag — always true or false",
    )
    translations: Optional[GlossaryTranslations] = Field(
        default=None,
        description="Updated German and/or Spanish translations",
    )
    comments: Optional[str] = Field(
        default=None,
        description="Updated English comment",
    )
    de_comments: Optional[str] = Field(
        default=None,
        description="Updated German-specific comment",
    )
    es_comments: Optional[str] = Field(
        default=None,
        description="Updated Spanish-specific comment",
    )

    @model_validator(mode="after")
    def validate_translations(self) -> GlossaryEntryUpdate:
        if self.do_not_translate:
            self.translations = None
            self.de_comments = None
            self.es_comments = None
        return self


class GlossaryEntryResponse(BaseModel):
    """Response model for a single glossary entry."""

    glossary_id: str = Field(
        ..., description="Unique identifier for this glossary entry"
    )
    term: str = Field(..., description="The glossary term / source word")
    scope: GlossaryScope = Field(..., description="Scope: global, local, or functional")
    do_not_translate: bool = Field(
        ..., description="True if the term should be kept as-is"
    )
    translations: Optional[GlossaryTranslations] = Field(
        default=None,
        description="German and Spanish translations (null when do_not_translate is true)",
    )
    comments: Optional[str] = Field(
        default=None, description="English comment for additional context"
    )
    de_comments: Optional[str] = Field(
        default=None, description="German-specific comment"
    )
    es_comments: Optional[str] = Field(
        default=None, description="Spanish-specific comment"
    )
    is_active: bool = Field(..., description="Whether this entry is active")
    created_at: str = Field(..., description="ISO timestamp when the entry was created")
    updated_at: str = Field(
        ..., description="ISO timestamp when the entry was last updated"
    )


class GlossaryListResponse(BaseModel):
    """Response model for listing glossary entries."""

    items: list[GlossaryEntryResponse] = Field(
        ..., description="List of glossary entries"
    )
    total: int = Field(..., description="Total number of entries returned")
