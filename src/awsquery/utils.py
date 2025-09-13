"""Utility functions for AWS Query Tool."""

import sys

import boto3

# Global debug mode flag
debug_enabled = False


def debug_print(*args, **kwargs):
    """Print debug messages with [DEBUG] prefix and timestamp when debug mode is enabled"""
    if debug_enabled:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        debug_prefix = f"[DEBUG] {timestamp}"

        if args:
            first_arg = f"{debug_prefix} {args[0]}"
            remaining_args = args[1:]
            print(first_arg, *remaining_args, file=sys.stderr, **kwargs)
        else:
            print(debug_prefix, file=sys.stderr, **kwargs)


def sanitize_input(value):
    """Basic input sanitization"""
    if not isinstance(value, str):
        return str(value)
    dangerous = ["|", ";", "&", "`", "$", "(", ")", "[", "]", "{", "}"]
    for char in dangerous:
        value = value.replace(char, "")
    return value.strip()


def normalize_action_name(action):
    """Convert CLI-style action names to boto3 method names"""
    normalized = action.replace("-", "_")

    import re

    normalized = re.sub("([a-z0-9])([A-Z])", r"\1_\2", normalized)

    normalized = normalized.lower()

    return normalized


def simplify_key(full_key):
    """Extract the last non-numeric attribute from a flattened key

    Examples:
    - "Instances.0.NetworkInterfaces.0.SubnetId" -> "SubnetId"
    - "Buckets.0.Name" -> "Name"
    - "Owner.DisplayName" -> "DisplayName"
    - "ReservationId" -> "ReservationId"
    """
    if not full_key:
        return full_key

    parts = full_key.split(".")

    for part in reversed(parts):
        if not part.isdigit():
            return part

    return parts[-1] if parts else full_key


def get_aws_services():
    """Get list of available AWS services"""
    try:
        session = boto3.Session()
        return sorted(session.get_available_services())
    except Exception as e:
        print(f"ERROR: Failed to get AWS services: {e}", file=sys.stderr)
        return []


def get_service_actions(service):
    """Get available actions for a service"""
    try:
        client = boto3.client(service)
        operations = client.meta.service_model.operation_names
        read_ops = [
            op
            for op in operations
            if any(op.lower().startswith(prefix) for prefix in ["describe", "list", "get"])
        ]
        return sorted(read_ops)
    except Exception as e:
        print(f"ERROR: Failed to get actions for {service}: {e}", file=sys.stderr)
        return []


def create_session(region=None, profile=None):
    """Create boto3 session with optional region/profile"""
    debug_print(f"create_session called with region={repr(region)}, profile={repr(profile)}")
    session_kwargs = {}
    if region and region.strip():
        session_kwargs["region_name"] = region
        debug_print(f"Added region_name={region} to session")
    if profile and profile.strip():
        session_kwargs["profile_name"] = profile
        debug_print(f"Added profile_name={profile} to session")
    debug_print(f"Creating session with kwargs: {session_kwargs}")
    return boto3.Session(**session_kwargs)


def get_client(service, session=None):
    """Get boto3 client from session or create default"""
    if session:
        return session.client(service)
    return boto3.client(service)
