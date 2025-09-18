"""Security validation for AWS Query Tool using simple prefix matching."""

import sys
from typing import Optional

from .utils import debug_print

# Common read-only operation prefixes based on AWS ReadOnly policy analysis
# These prefixes appear 20+ times across AWS services
SAFE_READONLY_PREFIXES = [
    "List",
    "Get",
    "Describe",
    "Batch",
    "Search",
    "Query",
    "View",
    "Lookup",
    "Read",
    "Scan",
    "Select",
    "Check",
    "Validate",
    "Test",
    "Preview",
    "Verify",
    "Estimate",
    "Discover",
    "Retrieve",
    "Is",
    "Has",
    "Can",
]


def is_readonly_operation(action: str) -> bool:
    """Check if an operation is read-only based on common prefixes."""
    # Convert kebab-case to PascalCase for checking
    if "-" in action:
        parts = action.split("-")
        action = "".join(part.capitalize() for part in parts)

    # Check if action starts with any safe prefix
    for prefix in SAFE_READONLY_PREFIXES:
        if action.startswith(prefix):
            debug_print(f"DEBUG: Operation {action} matches safe prefix {prefix}")
            return True

    debug_print(f"DEBUG: Operation {action} does not match any safe prefix")
    return False


def prompt_unsafe_operation(service: str, action: str) -> bool:
    """Prompt user to confirm unsafe operation."""
    print(f"\nWARNING: Operation '{service}:{action}' may not be read-only.", file=sys.stderr)
    print("This operation could potentially modify AWS resources.", file=sys.stderr)

    while True:
        response = input("Do you want to proceed? (yes/no): ").lower().strip()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("Please answer 'yes' or 'no'.", file=sys.stderr)


def validate_readonly(service: str, action: str, allow_unsafe: bool = False) -> bool:
    """Validate if an operation is safe to execute.

    Args:
        service: AWS service name
        action: Action/operation name
        allow_unsafe: If True, allow all operations without prompting

    Returns:
        True if operation should proceed, False otherwise
    """
    # If allow_unsafe flag is set, allow everything
    if allow_unsafe:
        debug_print(f"DEBUG: --allow-unsafe flag set, allowing {service}:{action}")
        return True

    # Check if operation matches read-only prefixes
    if is_readonly_operation(action):
        return True

    # For non-readonly operations, prompt the user
    return prompt_unsafe_operation(service, action)


# Legacy functions for backward compatibility (will be removed later)
def load_security_policy():
    """Legacy function - returns empty set to avoid breaking existing code."""
    return set()


def validate_security(service: str, action: str, allowed_actions) -> bool:
    """Legacy function - always returns True to avoid breaking existing code."""
    return True


def action_to_policy_format(action: str) -> str:
    """Convert kebab-case or snake_case action to PascalCase."""
    if "-" in action:
        parts = action.split("-")
        return "".join(part.capitalize() for part in parts)
    elif "_" in action:
        parts = action.split("_")
        return "".join(part.capitalize() for part in parts)
    return action


def get_service_valid_operations(service: str, all_operations: list) -> set:
    """Get operations that match read-only prefixes."""
    valid_ops = set()
    for op in all_operations:
        if is_readonly_operation(op):
            valid_ops.add(op)
    return valid_ops
