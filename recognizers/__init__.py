# Custom PII recognizers for document redaction workflows
# Provides region-specific PII detection for Presidio Analyzer

from .hk_patterns import get_all_recognizers

__all__ = ["get_all_recognizers"]
