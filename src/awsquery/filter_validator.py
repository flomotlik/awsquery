"""Column filter validation against AWS service model shapes.

This module validates column filter patterns before API calls and provides
helpful error messages with suggestions for typos.
"""

import re
from typing import Dict, List, Optional, Tuple

from .filters import matches_pattern, parse_filter_pattern
from .shapes import ShapeCache
from .utils import debug_print


class FilterValidator:
    """Validate column filter patterns against available response fields."""

    def __init__(self, shape_cache: Optional[ShapeCache] = None):
        """Initialize validator with optional shape cache.

        Args:
            shape_cache: Optional ShapeCache instance to reuse
        """
        self.shape_cache = shape_cache or ShapeCache()

    def validate_columns(
        self, service: str, operation: str, column_filters: List[str]
    ) -> List[Tuple[str, Optional[str]]]:
        """Validate column filters against operation response structure.

        Args:
            service: AWS service name
            operation: Operation name
            column_filters: List of column filter patterns

        Returns:
            List of (filter, error_message) tuples. error_message is None if valid.
        """
        data_field, simplified_fields, full_fields = self.shape_cache.get_response_fields(
            service, operation
        )

        if not simplified_fields:
            # Shape loading failed - return errors for all filters
            error_msg = f"Could not load response shape for {service}:{operation}"
            return [(f, error_msg) for f in column_filters]

        debug_print(
            f"Validating {len(column_filters)} filters against "
            f"{len(simplified_fields)} available fields"
        )

        results: List[Tuple[str, Optional[str]]] = []
        for filter_text in column_filters:
            validation_result = self._validate_single_column(
                filter_text, simplified_fields, full_fields
            )
            results.append((filter_text, validation_result[1]))

        return results

    def _validate_single_column(
        self,
        column_filter: str,
        simplified_fields: Dict[str, str],
        full_fields: Dict[str, str],
    ) -> Tuple[bool, Optional[str]]:
        """Validate a single column filter.

        Args:
            column_filter: Filter pattern (may include ^, $, ! operators)
            simplified_fields: Simplified field names (what filters match)
            full_fields: Full field paths

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        # Special case: map-wildcard means any field name is valid (for map types)
        if "*" in simplified_fields and simplified_fields["*"] == "map-wildcard":
            debug_print(f"Filter '{column_filter}' valid - map-wildcard response type")
            return True, None

        # Parse the filter pattern using existing logic from filters.py
        pattern, mode = parse_filter_pattern(column_filter)

        # Check if pattern matches any simplified field
        matches = []
        for field in simplified_fields.keys():
            if matches_pattern(field, pattern, mode):
                matches.append(field)

        if matches:
            debug_print(f"Filter '{column_filter}' matches {len(matches)} field(s): {matches[:3]}")
            return True, None

        # No match - find similar field for suggestion
        suggestion = self._find_similar_field(pattern, simplified_fields)
        if suggestion:
            error_msg = f"'{column_filter}' matches no fields. Did you mean '{suggestion}'?"
        else:
            error_msg = f"'{column_filter}' matches no fields"

        debug_print(f"Filter validation failed: {error_msg}")
        return False, error_msg

    def _find_similar_field(self, pattern: str, fields: Dict[str, str]) -> Optional[str]:
        """Find most similar field name for suggestion.

        Args:
            pattern: The pattern to find similar fields for
            fields: Available field names

        Returns:
            Most similar field name or None
        """
        pattern_lower = pattern.lower()

        # Exact substring match
        for field in fields.keys():
            if pattern_lower in field.lower():
                return field

        # Partial word match using word overlap
        pattern_parts = set(re.findall(r"\w+", pattern_lower))
        best_match = None
        best_score = 0

        for field in fields.keys():
            field_parts = set(re.findall(r"\w+", field.lower()))
            overlap = len(pattern_parts & field_parts)
            if overlap > best_score:
                best_score = overlap
                best_match = field

        return best_match if best_score > 0 else None

    def get_available_fields(self, service: str, operation: str) -> Dict[str, str]:
        """Get available fields for an operation (for display/debugging).

        Args:
            service: AWS service name
            operation: Operation name

        Returns:
            Dict mapping field names to types
        """
        _, simplified_fields, _ = self.shape_cache.get_response_fields(service, operation)
        return simplified_fields
