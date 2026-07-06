"""Compatibility wrapper for the generic CSV-driven recognizer."""

from recognizers.hk_patterns import build_recognizer


def get_enhanced_name_recognizer():
    """Return the generic CSV-driven recognizer for Chinese-name rules."""
    return build_recognizer(
        category="chinese_name",
        entity_type="PERSON",
        language="zh",
        name="csv_person_zh",
    )
