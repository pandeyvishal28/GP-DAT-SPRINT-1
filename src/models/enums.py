"""
models/enums.py
Enumeration types used across the GP-DAT pipeline.
"""

from enum import Enum


class Language(str, Enum):
    """Supported languages for translation and document processing."""

    ENGLISH = "en"
    SPANISH = "es"
    GERMAN = "de"

    @property
    def display_name(self) -> str:
        names = {
            "en": "English",
            "es": "Spanish",
            "de": "German",
        }
        return names[self.value]


class DocumentStatus(str, Enum):
    """Status of a document through the pipeline."""

    PENDING = "pending"
    CONTEXT_ENRICHED = "context_enriched"
    DATA_RETRIEVED = "data_retrieved"
    DRAFT_GENERATED = "draft_generated"
    UNDER_REVIEW = "under_review"
    HITL_PENDING = "hitl_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FINALIZED = "finalized"
    FAILED = "failed"


class GlossaryScope(str, Enum):
    """Scope level for a glossary entry."""

    GLOBAL = "global"
    LOCAL = "local"
    FUNCTIONAL = "functional"
