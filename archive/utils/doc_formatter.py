"""
utils/doc_formatter.py

This module is intentionally empty.

DOCX formatting is now handled in-place:
  - PDF → DOCX conversion: services/pdf_converter.py  (pdf2docx)
  - In-DOCX translation:   services/translation_service.py  (apply_translations)
  - Output saving:          agents/language_agent.py  (LanguageAgent.execute)
"""
