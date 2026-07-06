"""
Post-processing filter for Presidio analyzer results.

Filters out common false positives and improves accuracy for HK-specific contexts.
"""

import csv
import os
import re
from typing import List, Dict, Any


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULT_FILTER_RULES_CSV_PATH = os.path.join(DATA_DIR, "result_filter_rules.csv")


def _read_csv_rows(path: str) -> List[Dict[str, str]]:
    """Read rows from a CSV file, returning a list of dictionaries."""
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class ResultFilter:
    """
    Filters and validates Presidio analyzer results to remove false positives
    common in Hong Kong / academic document contexts.
    """

    FALSE_PERSON_PATTERNS = []
    FALSE_DATETIME_PATTERNS = []
    FALSE_LOCATION_PATTERNS = []
    PERSON_DENY_LIST = set()
    DATETIME_DENY_LIST = set()
    NAME_CONTEXT_KEYWORDS = []

    def __init__(self, min_score: float = 0.7):
        """
        Initialize filter with minimum confidence threshold.
        
        Args:
            min_score: Minimum confidence score to keep (0.0-1.0)
        """
        self.min_score = min_score
        self._load_rules()

    def _load_rules(self) -> None:
        """Load filter patterns and keyword lists from CSV data."""
        rows = _read_csv_rows(RESULT_FILTER_RULES_CSV_PATH)

        for row in rows:
            category = (row.get("category") or "").strip()
            value = (row.get("value") or "").strip()
            if not category or not value:
                continue

            if category == "false_person_pattern":
                self.FALSE_PERSON_PATTERNS.append(re.compile(value, re.IGNORECASE))
            elif category == "false_datetime_pattern":
                self.FALSE_DATETIME_PATTERNS.append(re.compile(value, re.IGNORECASE))
            elif category == "false_location_pattern":
                self.FALSE_LOCATION_PATTERNS.append(re.compile(value, re.IGNORECASE))
            elif category == "person_deny_list":
                self.PERSON_DENY_LIST.add(value.lower())
            elif category == "datetime_deny_list":
                self.DATETIME_DENY_LIST.add(value)
            elif category == "name_context_keywords":
                self.NAME_CONTEXT_KEYWORDS.append(value)

    def filter_results(self, text: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter analyzer results to remove false positives.
        
        Args:
            text: Original text
            results: List of Presidio results (each with entity_type, start, end, score)
            
        Returns:
            Filtered list of results
        """
        filtered = []
        
        for result in results:
            entity_text = text[result['start']:result['end']]
            
            # Skip low confidence results
            if result['score'] < self.min_score:
                continue
            
            # Validate based on entity type
            if self._is_valid_entity(result['entity_type'], entity_text, text, result['start'], result['end']):
                filtered.append(result)
        
        # Remove overlapping entities (keep higher confidence)
        filtered = self._remove_overlapping(filtered)
        
        return filtered

    def _is_valid_entity(self, entity_type: str, entity_text: str, full_text: str, start: int, end: int) -> bool:
        """Check if an entity is valid based on its type and text."""
        
        if entity_type == "PERSON":
            return self._is_valid_person(entity_text, full_text, start, end)
        
        elif entity_type == "DATE_TIME":
            return self._is_valid_datetime(entity_text)
        
        elif entity_type == "LOCATION":
            return self._is_valid_location(entity_text)
        
        elif entity_type == "URL":
            # URLs that are part of emails should be filtered
            return self._is_valid_url(entity_text)
        
        return True

    def _is_valid_person(self, text: str, full_text: str, start: int, end: int) -> bool:
        """Check if PERSON entity is valid."""
        text_lower = text.lower().strip()
        
        # Check deny list
        if text_lower in self.PERSON_DENY_LIST:
            return False
        
        # Check false positive patterns
        for pattern in self.FALSE_PERSON_PATTERNS:
            if pattern.match(text):
                return False
        
        # Must contain at least one letter or Chinese character
        if not re.search(r'[a-zA-Z\u4e00-\u9fa5]', text):
            return False
        
        # Chinese token checks: require nearby name/title context for short isolated Chinese entities
        if re.search(r'[\u4e00-\u9fa5]', text):
            if len(text.strip()) <= 4:
                surrounding = full_text[max(0, start - 12):start] + full_text[end:end + 12]
                context_keywords = re.compile(
                    r'(?:' + '|'.join(re.escape(term) for term in self.NAME_CONTEXT_KEYWORDS) + r')',
                    re.IGNORECASE
                )
                if not context_keywords.search(surrounding):
                    return False
        
        return True

    def _is_valid_datetime(self, text: str) -> bool:
        """Check if DATE_TIME entity is valid."""
        text_stripped = text.strip()
        
        # Check deny list
        if text_stripped in self.DATETIME_DENY_LIST:
            return False
        
        # Check false positive patterns
        for pattern in self.FALSE_DATETIME_PATTERNS:
            if pattern.match(text_stripped):
                return False
        
        # Must look like an actual date/time
        # Should contain at least 2 non-digit characters (/, -, :, etc.) or month names
        date_indicators = re.search(r'[/\-:年月日]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec', text_lower := text.lower())
        if not date_indicators:
            # If it's mostly digits with spaces, likely a phone number
            digit_ratio = sum(c.isdigit() for c in text) / len(text) if text else 0
            if digit_ratio > 0.7:
                return False
        
        return True

    def _is_valid_location(self, text: str) -> bool:
        """Check if LOCATION entity is valid."""
        # If it's a full street address, it might be better handled as ADDRESS
        # But we'll keep it as LOCATION for now
        return True

    def _is_valid_url(self, text: str) -> bool:
        """Check if URL entity is valid (not part of email)."""
        # If it looks like just a domain without protocol, might be part of email
        if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', text.strip()):
            # Check if it looks like an email domain
            return False
        return True

    def _remove_overlapping(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove overlapping entities, keeping higher confidence ones."""
        if not results:
            return results
        
        # Sort by start position, then by score (descending)
        sorted_results = sorted(results, key=lambda r: (r['start'], -r['score']))
        
        filtered = []
        for result in sorted_results:
            # Check if this overlaps with any already kept result
            overlaps = False
            for kept in filtered:
                if (result['start'] < kept['end'] and result['end'] > kept['start']):
                    overlaps = True
                    break
            
            if not overlaps:
                filtered.append(result)
        
        return filtered

    def enhance_results(self, text: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance results with additional metadata and corrections.
        
        Args:
            text: Original text
            results: Filtered results
            
        Returns:
            Enhanced results with additional metadata
        """
        enhanced = []
        
        for result in results:
            entity_text = text[result['start']:result['end']]
            
            # Add redaction suggestions
            result['redaction_suggestion'] = self._get_redaction_suggestion(
                result['entity_type'], entity_text
            )
            
            # Add entity category for grouping
            result['category'] = self._get_category(result['entity_type'])
            
            enhanced.append(result)
        
        return enhanced

    def _get_redaction_suggestion(self, entity_type: str, entity_text: str) -> str:
        """Get redaction suggestion based on entity type."""
        suggestions = {
            "PERSON": "[REDACTED NAME]",
            "EMAIL_ADDRESS": "[REDACTED EMAIL]",
            "PHONE_NUMBER": "[REDACTED PHONE]",
            "HK_ID_CARD": "[REDACTED HKID]",
            "ADDRESS_EN": "[REDACTED ADDRESS]",
            "ADDRESS_ZH_TRAD": "[REDACTED ADDRESS]",
            "ADDRESS_ZH_SIMP": "[REDACTED ADDRESS]",
            "LOCATION": "[REDACTED LOCATION]",
            "DATE_TIME": entity_text,  # Usually don't redact dates
            "URL": "[REDACTED URL]",
        }
        return suggestions.get(entity_type, "[REDACTED]")

    def _get_category(self, entity_type: str) -> str:
        """Get high-level category for entity."""
        categories = {
            "PERSON": "identity",
            "PERSON_ZH": "identity",
            "EMAIL_ADDRESS": "contact",
            "PHONE_NUMBER": "contact",
            "HK_PHONE_NUMBER": "contact",
            "HK_ID_CARD": "identity",
            "PASSPORT_NUMBER": "identity",
            "ADDRESS_EN": "location",
            "ADDRESS_ZH_TRAD": "location",
            "ADDRESS_ZH_SIMP": "location",
            "LOCATION": "location",
            "BANK_ACCOUNT": "financial",
            "CREDIT_CARD": "financial",
        }
        return categories.get(entity_type, "other")


# Convenience function for use in n8n
def filter_analyzer_results(text: str, results: List[Dict[str, Any]], min_score: float = 0.7) -> List[Dict[str, Any]]:
    """
    Convenience function to filter and enhance analyzer results.
    
    Usage in n8n Code node:
        const filter = require('/app/recognizers/result_filter.py');
        const filtered = filter.filter_analyzer_results(text, results, 0.7);
    """
    filter_obj = ResultFilter(min_score=min_score)
    filtered = filter_obj.filter_results(text, results)
    return filter_obj.enhance_results(text, filtered)
