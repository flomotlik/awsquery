"""Algorithmic case transformation utilities.

No hardcoded acronym dictionaries - uses pattern matching to preserve acronyms.
"""

import re


def to_snake_case(text: str) -> str:
    """Convert any format (PascalCase, camelCase, kebab-case) to snake_case.

    Uses algorithmic pattern matching to preserve acronyms (VPC, HTTPS, DB).

    Args:
        text: Input string in any case format

    Returns:
        snake_case string

    Examples:
        >>> to_snake_case('DescribeInstances')
        'describe_instances'
        >>> to_snake_case('HTTPSListener')
        'https_listener'
        >>> to_snake_case('VPCId')
        'vpc_id'
        >>> to_snake_case('describe-instances')
        'describe_instances'
    """
    if not text:
        return text

    # Handle kebab-case first
    if "-" in text:
        return text.replace("-", "_").lower()

    # Handle PascalCase/camelCase with acronym preservation
    # Pattern 1: Split before the last capital when followed by lowercase
    # Handles: "HTTPSListener" -> "HTTPS_Listener", "DBClusters" -> "DB_Clusters"
    s1 = re.sub("([A-Z]+)([A-Z][a-z])", r"\1_\2", text)

    # Pattern 2: Insert underscore before uppercase after lowercase/digit
    # Handles: "VPCId" -> "VPC_Id", "load2Balancer" -> "load2_Balancer"
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)

    return s2.lower()


def to_pascal_case(text: str) -> str:
    """Convert snake_case or kebab-case to PascalCase.

    Preserves existing PascalCase input unchanged.

    Args:
        text: Input string in snake_case, kebab-case, or PascalCase

    Returns:
        PascalCase string

    Examples:
        >>> to_pascal_case('describe_instances')
        'DescribeInstances'
        >>> to_pascal_case('https_listener')
        'HttpsListener'
        >>> to_pascal_case('describe-instances')
        'DescribeInstances'
        >>> to_pascal_case('DescribeInstances')
        'DescribeInstances'
    """
    if not text:
        return text

    # If no separators and starts with uppercase, assume already PascalCase
    if "_" not in text and "-" not in text and text[0].isupper():
        return text

    # Normalize to snake_case first
    normalized = text.replace("-", "_")

    # Capitalize each word
    return "".join(word.capitalize() for word in normalized.split("_"))


def to_kebab_case(text: str) -> str:
    """Convert PascalCase to kebab-case for display.

    Uses same algorithm as to_snake_case for consistency.

    Args:
        text: Input string in PascalCase

    Returns:
        kebab-case string

    Examples:
        >>> to_kebab_case('DescribeInstances')
        'describe-instances'
        >>> to_kebab_case('HTTPSListener')
        'https-listener'
        >>> to_kebab_case('VPCId')
        'vpc-id'
    """
    snake = to_snake_case(text)
    return snake.replace("_", "-")
