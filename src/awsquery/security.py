"""Security validation for AWS Query Tool using simple prefix matching."""

import os
import sys
from typing import NoReturn, Optional

from .case_utils import to_pascal_case
from .errors import ExitCode, fail
from .utils import debug_print

# Common read-only operation prefixes based on AWS ReadOnly policy analysis
# These prefixes appear 20+ times across AWS services
# Note: Only specific BatchXxx prefixes are included to avoid false positives
# with write operations like BatchCreate, BatchDelete, BatchUpdate, etc.
# Note: "Can" prefix removed as it matches Cancel* operations (write operations)
SAFE_READONLY_PREFIXES = [
    "List",
    "Get",
    "Describe",
    "BatchGet",
    "BatchDescribe",
    "BatchCheck",
    "BatchDetect",
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
    "Has",
]


def is_readonly_operation(action: str) -> bool:
    """Check if an operation is read-only based on common prefixes."""
    # Convert kebab-case to PascalCase for checking
    if "-" in action:
        action = to_pascal_case(action.replace("-", "_"))

    # Check if action starts with any safe prefix
    for prefix in SAFE_READONLY_PREFIXES:
        if action.startswith(prefix):
            debug_print(f"DEBUG: Operation {action} matches safe prefix {prefix}")
            return True

    debug_print(f"DEBUG: Operation {action} does not match any safe prefix")
    return False


def _is_non_interactive() -> bool:
    """Whether confirmation prompts are impossible (agent loops, pipes, CI)."""
    flag = os.environ.get("AWSQUERY_NON_INTERACTIVE", "").strip().lower()
    if flag and flag not in ("0", "false", "no", "off"):
        return True
    try:
        return not sys.stdin.isatty()
    except Exception:  # stdin replaced or closed
        return True


def _refuse_unsafe(service: str, action: str) -> NoReturn:
    """Refuse an unsafe operation that cannot be confirmed interactively."""
    fail(
        ExitCode.USAGE,
        "UnsafeOperationRefused",
        f"Operation '{service}:{action}' may not be read-only and cannot be "
        f"confirmed without an interactive terminal.",
        hint="Pass --allow-unsafe to override",
    )


def prompt_unsafe_operation(service: str, action: str) -> bool:
    """Prompt user to confirm unsafe operation."""
    if _is_non_interactive():
        _refuse_unsafe(service, action)

    print(f"\nWARNING: Operation '{service}:{action}' may not be read-only.", file=sys.stderr)
    print("This operation could potentially modify AWS resources.", file=sys.stderr)

    while True:
        try:
            response = input("Do you want to proceed? (yes/no): ").lower().strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            _refuse_unsafe(service, action)

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


def get_service_valid_operations(service: str, all_operations: list) -> set:
    """Get operations that match read-only prefixes."""
    valid_ops = set()
    for op in all_operations:
        if is_readonly_operation(op):
            valid_ops.add(op)
    return valid_ops
