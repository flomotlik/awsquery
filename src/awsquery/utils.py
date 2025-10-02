"""Utility functions for AWS Query Tool."""

import sys

import boto3

from .case_utils import to_kebab_case, to_snake_case


def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility.

    Note: This is NOT a general case conversion - it only capitalizes the first letter.
    For general case conversion, use case_utils module.
    """
    if not parameter_name:
        return parameter_name

    return (
        parameter_name[0].upper() + parameter_name[1:]
        if len(parameter_name) > 0
        else parameter_name
    )


# Compatibility wrappers using new case_utils functions
pascal_to_kebab_case = to_kebab_case
normalize_action_name = to_snake_case


class DebugContext:
    """Context manager for debug output"""

    def __init__(self, enabled=False):
        """Initialize debug context with optional enabled state."""
        self.enabled = enabled

    def print(self, *args, **kwargs):
        """Print debug messages with [DEBUG] prefix and timestamp when enabled"""
        if self.enabled:
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            debug_prefix = f"[DEBUG] {timestamp}"

            if args:
                first_arg = f"{debug_prefix} {args[0]}"
                remaining_args = args[1:]
                print(first_arg, *remaining_args, file=sys.stderr, **kwargs)
            else:
                print(debug_prefix, file=sys.stderr, **kwargs)

    def enable(self):
        """Enable debug output"""
        self.enabled = True

    def disable(self):
        """Disable debug output"""
        self.enabled = False


# Global debug context
_debug_context = DebugContext()


def debug_print(*args, **kwargs):
    """Print debug messages with [DEBUG] prefix and timestamp when debug mode is enabled"""
    _debug_context.print(*args, **kwargs)


def set_debug_enabled(value):
    """Set debug mode on or off"""
    if value:
        _debug_context.enable()
    else:
        _debug_context.disable()


def get_debug_enabled():
    """Get current debug mode state"""
    return _debug_context.enabled


# Simple debug_enabled property for module-level access
class _DebugEnabled:
    """Simple debug enabled property without backward compatibility complexity"""

    def __bool__(self):
        return _debug_context.enabled

    def __eq__(self, other):
        return _debug_context.enabled == other

    def __repr__(self):
        return str(_debug_context.enabled)


debug_enabled = _DebugEnabled()


def sanitize_input(value):
    """Basic input sanitization"""
    if not isinstance(value, str):
        return str(value)
    # Note: $ is not included as it's used for suffix matching in filters
    dangerous = ["|", ";", "&", "`", "(", ")", "[", "]", "{", "}"]
    for char in dangerous:
        value = value.replace(char, "")
    return value.strip()


def simplify_key(full_key):
    """Normalize key by removing numeric indices while preserving hierarchy

    Examples:
    - "Instances.0.NetworkInterfaces.0.SubnetId" -> "Instances.NetworkInterfaces.SubnetId"
    - "Buckets.0.Name" -> "Buckets.Name"
    - "Tags.0.Name" -> "Tags.Name"
    - "State.Name" -> "State.Name"
    - "Owner.DisplayName" -> "Owner.DisplayName"
    - "ReservationId" -> "ReservationId"
    """
    if not full_key:
        return full_key

    parts = full_key.split(".")
    non_numeric_parts = [part for part in parts if not part.isdigit()]

    return ".".join(non_numeric_parts) if non_numeric_parts else full_key


def get_aws_services():
    """Get list of available AWS services"""
    try:
        session = boto3.Session()
        return sorted(session.get_available_services())
    except Exception as e:
        print(f"ERROR: Failed to get AWS services: {e}", file=sys.stderr)
        return []


def create_session(region=None, profile=None):
    """Create boto3 session with optional region/profile"""
    debug_print(
        f"create_session called with region={repr(region)}, profile={repr(profile)}"
    )  # pragma: no mutate
    session_kwargs = {}
    if region and region.strip():
        session_kwargs["region_name"] = region
        debug_print(f"Added region_name={region} to session")  # pragma: no mutate
    if profile and profile.strip():
        session_kwargs["profile_name"] = profile
        debug_print(f"Added profile_name={profile} to session")  # pragma: no mutate
    debug_print(f"Creating session with kwargs: {session_kwargs}")  # pragma: no mutate
    return boto3.Session(**session_kwargs)


def get_client(service, session=None):
    """Get boto3 client from session or create default"""
    if session:
        return session.client(service)
    return boto3.client(service)
