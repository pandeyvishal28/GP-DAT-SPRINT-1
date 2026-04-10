"""
models/enums.py
Enumeration types used across the GP-DAT pipeline.
"""

from enum import Enum


class TaskType(str, Enum):
    """Type of document processing task."""

    GENERATION = "generation"
    ADAPTATION = "adaptation"
    TRANSLATION = "translation"


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


class AgentType(str, Enum):
    """Identifiers for each agent in the pipeline."""

    DATA_RETRIEVAL = "data_retrieval_agent"
    CONTEXT = "context_agent"
    REASONING = "reasoning_agent"
    CRITIC = "critic_agent"
    RESPONSE = "response_agent"
    LANGUAGE = "language_agent"


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    AZURE_OPENAI = "azure_openai"
    OPENAI = "openai"
    APOLLO = "apollo"


class CritiqueVerdict(str, Enum):
    """Possible outcomes from the Critic Agent's quality check."""

    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class GlossaryScope(str, Enum):
    """Scope level for a glossary entry."""

    GLOBAL = "global"
    LOCAL = "local"
    FUNCTIONAL = "functional"
