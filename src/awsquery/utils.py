"""
Utility functions for AWS Query Tool.

This module contains common utility functions including debug printing,
input sanitization, string manipulation, and AWS service introspection.
"""

import sys
import boto3

# Global debug mode flag
debug_enabled = False

def debug_print(*args, **kwargs):
    """Print debug messages only when debug mode is enabled"""
    if debug_enabled:
        print(*args, file=sys.stderr, **kwargs)


def sanitize_input(value):
    """Basic input sanitization"""
    if not isinstance(value, str):
        return str(value)
    # Remove potentially dangerous characters
    dangerous = ['|', ';', '&', '`', '$', '(', ')', '[', ']', '{', '}']
    for char in dangerous:
        value = value.replace(char, '')
    return value.strip()


def normalize_action_name(action):
    """Convert CLI-style action names to boto3 method names"""
    # Convert hyphens to underscores: "describe-instances" -> "describe_instances"
    normalized = action.replace('-', '_')
    
    # Handle camelCase to snake_case conversion if needed
    import re
    # Insert underscore before uppercase letters (except at start)
    normalized = re.sub('([a-z0-9])([A-Z])', r'\1_\2', normalized)
    
    # Convert to lowercase
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
    
    # Split by dots and find the last non-numeric part
    parts = full_key.split('.')
    
    # Work backwards to find the last non-numeric part
    for part in reversed(parts):
        if not part.isdigit():
            return part
    
    # If somehow all parts are numeric (shouldn't happen), return the last part
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
        # Filter for read-only operations
        read_ops = [op for op in operations if any(
            op.lower().startswith(prefix) for prefix in ['describe', 'list', 'get']
        )]
        return sorted(read_ops)
    except Exception as e:
        print(f"ERROR: Failed to get actions for {service}: {e}", file=sys.stderr)
        return []