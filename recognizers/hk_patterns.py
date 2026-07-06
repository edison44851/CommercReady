"""
HK-specific PII recognizers using PatternRecognizer for easy registration.

Patterns and contextual keywords are loaded from CSV files in the recognizers/data
folder so they can be maintained without editing Python code.
"""

import csv
import os
import re
from typing import Dict, List, Optional, Tuple

try:
    from presidio_analyzer import PatternRecognizer, Pattern
except ImportError:  # pragma: no cover - fallback for local/static validation
    class Pattern:  # type: ignore[override]
        def __init__(self, name: str, regex: str, score: float = 0.5):
            self.name = name
            self.regex = regex
            self.score = score

    class PatternRecognizer:  # type: ignore[override]
        def __init__(self, supported_entity: str = "PERSON", patterns=None, context=None, supported_language: str = "en"):
            self.supported_entities = [supported_entity]
            self.supported_language = supported_language
            self.patterns = patterns or []
            self.context = context or []
            self.name = supported_entity


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PATTERN_RULES_CSV_PATH = os.path.join(DATA_DIR, "pattern_rules.csv")
KEYWORD_TERMS_CSV_PATH = os.path.join(DATA_DIR, "keyword_terms.csv")
SURNAMES_CSV_PATH = os.path.join(DATA_DIR, "chinese_surnames.csv")
CHINESE_NAME_RULES_CSV_PATH = os.path.join(DATA_DIR, "chinese_name_rules.csv")

DEFAULT_ENTITY_TYPES = {
    "hkid": "HK_ID_CARD",
    "passport": "PASSPORT_NUMBER",
    "hk_phone": "HK_PHONE_NUMBER",
    "bank_account": "BANK_ACCOUNT",
    "english_address": "ADDRESS_EN",
    "chinese_address": "ADDRESS_ZH",
    "chinese_name": "PERSON",
}

DEFAULT_LANGUAGES = {
    "hkid": "en",
    "passport": "en",
    "hk_phone": "en",
    "bank_account": "en",
    "english_address": "en",
    "chinese_address": "zh",
    "chinese_name": "zh",
}

DEFAULT_CONTEXT_GROUPS = {
    "hkid": "hkid_context",
    "passport": "passport_context",
    "hk_phone": "hk_phone_context",
    "bank_account": "bank_account_context",
    "english_address": "english_address_context",
    "chinese_address": "chinese_address_context",
    "chinese_name": "chinese_name_context",
}


class CsvDrivenPatternRecognizer(PatternRecognizer):
    """Generic recognizer that loads its rules and context from CSV files."""

    def __init__(self, supported_entity: str, patterns=None, context=None, supported_language: str = "en", name: Optional[str] = None):
        super().__init__(
            supported_entity=supported_entity,
            patterns=patterns or [],
            context=context or [],
            supported_language=supported_language,
        )
        self.name = name or supported_entity


def _read_csv_rows(path: str) -> List[Dict[str, str]]:
    """Read rows from a CSV file, returning a list of dictionaries."""
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _load_pattern_rows() -> List[Dict[str, str]]:
    """Load pattern-rule rows from the CSV file."""
    rows: List[Dict[str, str]] = []
    for row in _read_csv_rows(PATTERN_RULES_CSV_PATH):
        category = (row.get("category") or "").strip()
        regex = (row.get("regex") or "").strip()
        if not category or not regex:
            continue
        rows.append(row)
    return rows


def _load_keyword_terms() -> Dict[str, List[str]]:
    """Load keywords grouped by group name from the CSV file."""
    grouped_terms: Dict[str, List[str]] = {}
    for row in _read_csv_rows(KEYWORD_TERMS_CSV_PATH):
        group = (row.get("group") or "").strip()
        value = (row.get("value") or "").strip()
        if not group or not value:
            continue
        grouped_terms.setdefault(group, []).append(value)
    return grouped_terms


def _load_surnames() -> List[str]:
    """Load surnames from the shared CSV so pattern rules can use them."""
    surnames: List[str] = []
    for row in _read_csv_rows(SURNAMES_CSV_PATH):
        for key in ("surname_traditional", "surname_simplified", "pinyin_cantonese", "pinyin_mandarin"):
            value = (row.get(key) or "").strip()
            if value and value not in surnames:
                surnames.append(value)
    return surnames


def _load_name_rule(key: str) -> str:
    """Load a regex fragment from the Chinese-name rules CSV file."""
    for row in _read_csv_rows(CHINESE_NAME_RULES_CSV_PATH):
        if (row.get("key") or "").strip() == key:
            return (row.get("value") or "").strip()
    return ""


def _resolve_regex(row: Dict[str, str], surname_variants: Optional[List[str]] = None) -> str:
    """Resolve CSV-based regex placeholders before creating patterns."""
    regex = (row.get("regex") or "").strip()
    if not regex:
        return regex

    if "{{SURNAME_PATTERN}}" in regex:
        if not surname_variants:
            surname_variants = _load_surnames()
        pattern = "|".join(sorted(re.escape(term) for term in surname_variants))
        regex = regex.replace("{{SURNAME_PATTERN}}", pattern)

    if "{{NAME_PREFIXES}}" in regex:
        name_prefixes = _load_name_rule("name_prefixes") or ""
        regex = regex.replace("{{NAME_PREFIXES}}", name_prefixes)

    if "{{TITLE_SUFFIXES}}" in regex:
        title_suffixes = _load_name_rule("title_suffixes") or ""
        regex = regex.replace("{{TITLE_SUFFIXES}}", title_suffixes)

    return regex


def _build_patterns(rows: List[Dict[str, str]], keyword_terms: Dict[str, List[str]]) -> Dict[Tuple[str, str], List[Pattern]]:
    """Build pattern objects grouped by entity type and language."""
    grouped_rules: Dict[Tuple[str, str], List[Pattern]] = {}
    surname_variants = _load_surnames()

    for row in rows:
        category = (row.get("category") or "").strip()
        regex = _resolve_regex(row, surname_variants=surname_variants)
        if not regex:
            continue

        entity_type = (row.get("entity_type") or DEFAULT_ENTITY_TYPES.get(category, "PERSON")).strip()
        language = (row.get("language") or DEFAULT_LANGUAGES.get(category, "en")).strip() or "en"
        name = (row.get("name") or category).strip()
        score = float(row.get("score") or 0.5)
        context_group = (row.get("context_group") or "").strip()
        context = keyword_terms.get(context_group, []) if context_group else []
        key = (entity_type, language)
        grouped_rules.setdefault(key, []).append(
            Pattern(name=name, regex=regex, score=score)
        )

    return grouped_rules


def build_recognizer(category: str, entity_type: Optional[str] = None, language: Optional[str] = None, name: Optional[str] = None):
    """Build a single recognizer from the shared CSV rule set for one category."""
    rows = _load_pattern_rows()
    keyword_terms = _load_keyword_terms()
    matching_rows = [row for row in rows if (row.get("category") or "").strip() == category]
    if not matching_rows:
        return None

    resolved_entity_type = entity_type or (matching_rows[0].get("entity_type") or DEFAULT_ENTITY_TYPES.get(category, "PERSON")).strip()
    resolved_language = language or (matching_rows[0].get("language") or DEFAULT_LANGUAGES.get(category, "en")).strip() or "en"
    context_group = DEFAULT_CONTEXT_GROUPS.get(category, "")
    context = list(dict.fromkeys(keyword_terms.get(context_group, [])))
    patterns = []

    for row in matching_rows:
        regex = _resolve_regex(row, surname_variants=_load_surnames())
        if regex:
            patterns.append(
                Pattern(
                    name=(row.get("name") or category).strip(),
                    regex=regex,
                    score=float(row.get("score") or 0.5),
                )
            )

    return CsvDrivenPatternRecognizer(
        supported_entity=resolved_entity_type,
        patterns=patterns,
        context=context,
        supported_language=resolved_language,
        name=name or f"csv_{category}_{resolved_language}",
    )


def get_all_recognizers():
    """Return CSV-driven recognizers for all configured categories."""
    recognizers = []
    rows = _load_pattern_rows()
    categories = sorted({(row.get("category") or "").strip() for row in rows if (row.get("category") or "").strip()})

    for category in categories:
        recognizer = build_recognizer(category)
        if recognizer is not None:
            recognizers.append(recognizer)

    return recognizers
