"""AWS Query Tool - A modular tool for querying AWS APIs with flexible filtering."""

from .cli import main
from .utils import debug_print, debug_enabled

__version__ = "1.0.0"
__all__ = ["main", "debug_print", "debug_enabled"]
