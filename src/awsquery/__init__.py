"""
AWS Query Tool - A modular tool for querying AWS APIs with flexible filtering.

This package provides modular components for AWS API queries with automatic parameter
resolution, security policy validation, and flexible output formatting.
"""

from .cli import main
from .utils import debug_print, debug_enabled

__version__ = "1.0.0"
__all__ = ["main", "debug_print", "debug_enabled"]