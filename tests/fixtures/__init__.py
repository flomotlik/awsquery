"""
Test fixtures package for AWS Query Tool.

This package contains specialized fixtures and test data for comprehensive
testing scenarios including AWS responses, security policies, and complex
nested structures.
"""

from .aws_responses import get_complex_nested_response, get_paginated_response
from .policy_samples import (
    get_deny_policy,
    get_readonly_policy,
    get_restrictive_policy,
    get_wildcard_policy,
)

__all__ = [
    "get_paginated_response",
    "get_complex_nested_response",
    "get_readonly_policy",
    "get_restrictive_policy",
    "get_wildcard_policy",
    "get_deny_policy",
]
