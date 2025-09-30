"""Command-line interface for AWS Query Tool."""

# pylint: disable=too-many-lines

import argparse
import os
import re
import sys
from typing import Any, List, Optional, Tuple

import argcomplete
import boto3

from .config import apply_default_filters
from .core import (
    check_parameter_requirements,
    execute_aws_call,
    execute_multi_level_call,
    execute_multi_level_call_with_tracking,
    execute_with_tracking,
    show_keys_from_result,
)
from .filters import filter_resources, parse_multi_level_filters_for_mode
from .formatters import (
    extract_and_sort_keys,
    flatten_response,
    format_json_output,
    format_table_output,
    show_keys,
)
from .security import (
    action_to_policy_format,
    get_service_valid_operations,
    is_readonly_operation,
    validate_readonly,
)
from .utils import create_session, debug_print, get_aws_services, sanitize_input

# Global variable to store current completion context for smart prefix matching
_current_completion_context = {"operations": [], "current_input": ""}


def parse_parameter_string(param_str):
    """Parse parameter string into Python objects for boto3 API calls.

    Examples:
    - "Key=Value" -> {"Key": "Value"}
    - "Values=a,b,c" -> {"Values": ["a", "b", "c"]}
    - Complex structures with ; and , delimiters for nested objects
    """
    if not param_str or not param_str.strip():
        raise ValueError("Invalid parameter format: empty parameter string")

    param_str = param_str.strip()

    # Split on first '=' to get key and value
    if "=" not in param_str:
        raise ValueError("Invalid parameter format: missing '=' separator")

    key, value = param_str.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not key:
        raise ValueError("Invalid parameter format: empty parameter key")

    # Parse the value based on its structure
    parsed_value = _parse_parameter_value(value)

    return {key: parsed_value}


def _parse_parameter_value(value):
    """Parse a parameter value, handling type conversion and complex structures."""
    if not value:
        return ""

    # Check for complex structure with semicolons (list of dicts)
    if ";" in value and "," in value:
        # This is likely a list of objects like ParameterFilters
        return _parse_list_of_dicts(value)

    # Check for comma-separated key=value pairs (single dict in a list)
    if "," in value and "=" in value:
        # Check if all comma-separated items contain '=' (indicating key=value pairs)
        items = [item.strip() for item in value.split(",")]
        if all("=" in item for item in items if item):
            # This is a single dictionary that should be wrapped in a list
            # Parse as key=value pairs into a single dict
            single_dict = {}
            for item in items:
                if "=" in item:
                    k, v = item.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k:
                        single_dict[k] = _convert_type(v)
            return [single_dict] if single_dict else []

    # Check for simple comma-separated list
    if "," in value:
        # Split and clean each item
        items = [item.strip() for item in value.split(",")]
        # Apply type conversion to each item
        return [_convert_type(item) for item in items if item]

    # Single value - apply type conversion
    return _convert_type(value)


def _parse_list_of_dicts(value):
    """Parse semicolon-separated list of comma-separated key=value pairs."""
    result = []

    # Split by semicolons to get individual objects
    dict_strings = [s.strip() for s in value.split(";") if s.strip()]

    for dict_str in dict_strings:
        if not dict_str:
            continue

        # Parse each object as comma-separated key=value pairs
        obj = {}
        pairs = [pair.strip() for pair in dict_str.split(",") if pair.strip()]

        for pair in pairs:
            if "=" not in pair:
                continue

            pair_key, pair_value = pair.split("=", 1)
            pair_key = pair_key.strip()
            pair_value = pair_value.strip()

            if not pair_key:
                continue

            # Special handling for Values field - it should be a list
            if pair_key == "Values":
                # If there are more values after this, they should be collected
                remaining_values = []
                # Look for additional values in subsequent pairs
                value_start_index = pairs.index(pair)
                for i in range(value_start_index + 1, len(pairs)):
                    next_pair = pairs[i]
                    if "=" in next_pair:
                        break  # This is a new key=value pair
                    remaining_values.append(_convert_type(next_pair.strip()))

                # Create the Values list
                values_list = [_convert_type(pair_value)]
                values_list.extend(remaining_values)
                obj[pair_key] = values_list

                # Remove processed values from pairs list
                for _ in remaining_values:
                    if pairs:
                        pairs.pop(value_start_index + 1)
            else:
                obj[pair_key] = _convert_type(pair_value)

        if obj:
            result.append(obj)

    return result


def _convert_type(value):
    """Convert string value to appropriate Python type."""
    if not isinstance(value, str):
        return value

    value = value.strip()

    # Boolean conversion
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integer conversion
    if value.isdigit():
        return int(value)

    # Keep as string
    return value


def get_parameter_type(service, action, parameter_name, session=None):
    """Get expected parameter type from boto3 service model.

    Args:
        service: AWS service name (e.g., 'ec2', 'ssm')
        action: Operation name (e.g., 'describe-parameters')
        parameter_name: Parameter to check (e.g., 'Filters')
        session: Optional boto3 session

    Returns:
        str or None: Parameter type ('list', 'string', 'structure', 'integer', etc.)
                     or None if parameter not found or error occurs
    """
    try:
        from .utils import get_client, normalize_action_name

        client = get_client(service, session)
        normalized_action = normalize_action_name(action)

        # Get operation model
        operation_model = client.meta.service_model.operation_model(normalized_action)

        if operation_model.input_shape and parameter_name in operation_model.input_shape.members:
            param_shape = operation_model.input_shape.members[parameter_name]
            return param_shape.type_name

        return None

    except Exception as e:
        debug_print(f"Could not determine parameter type for {parameter_name}: {e}")
        return None


# CLI flag constants
SIMPLE_FLAGS = ["-d", "--debug", "-j", "--json", "-k", "--keys", "--allow-unsafe"]
VALUE_FLAGS = ["--region", "--profile", "-p", "--parameter", "-i", "--input"]


def _extract_flags_from_args(remaining_args):
    """Extract CLI flags from remaining arguments."""
    flags = []
    non_flags = []
    i = 0
    while i < len(remaining_args):
        arg = remaining_args[i]
        if arg in SIMPLE_FLAGS:
            flags.append(arg)
        elif arg in VALUE_FLAGS:
            flags.append(arg)
            # Check for value after the flag
            if i + 1 < len(remaining_args):
                next_arg = remaining_args[i + 1]
                if not next_arg.startswith("-"):
                    flags.append(next_arg)
                    i += 1
        else:
            non_flags.append(arg)
        i += 1
    return flags, non_flags


def _preserve_parsed_flags(args):
    """Preserve flags that were already parsed."""
    flags = []
    if args.debug:
        flags.append("-d")
    if getattr(args, "json", False):
        flags.append("-j")
    if getattr(args, "keys", False):
        flags.append("-k")
    if getattr(args, "allow_unsafe", False):
        flags.append("--allow-unsafe")
    if getattr(args, "region", None):
        flags.extend(["--region", args.region])
    if getattr(args, "profile", None):
        flags.extend(["--profile", args.profile])
    return flags


def service_completer(prefix, parsed_args, **kwargs):
    """Autocomplete AWS service names"""
    try:
        # Create a session without requiring valid credentials
        # This works locally to get service names from botocore's data files
        import botocore.session

        # Temporarily clear AWS_PROFILE to avoid validation errors
        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            session = botocore.session.Session()
            # Get available services from botocore's local data
            services = session.get_available_services()
        finally:
            # Restore AWS_PROFILE if it existed
            if old_profile is not None:
                os.environ["AWS_PROFILE"] = old_profile

    except Exception:
        # If even local session fails, return empty
        return []

    return [s for s in services if s.startswith(prefix)]


def _extract_flag_and_value(args, i):
    """Extract a flag and optionally its value from args list."""
    flags = []
    flags.append(args[i])
    if args[i] in VALUE_FLAGS:
        if i + 1 < len(args) and not args[i + 1].startswith("-") and args[i + 1] != "--":
            flags.append(args[i + 1])
            return flags, 2  # consumed 2 args
    return flags, 1  # consumed 1 arg


def _process_remaining_args_after_separator(remaining):
    """Process remaining args when -- was in original but not in remaining."""
    flags = []
    non_flags = []
    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if arg in SIMPLE_FLAGS:
            flags.append(arg)
            i += 1
        elif arg in VALUE_FLAGS:
            extracted, consumed = _extract_flag_and_value(remaining, i)
            flags.extend(extracted)
            i += consumed
        else:
            non_flags.append(arg)
            i += 1
    return flags, non_flags


def _process_remaining_args(remaining):
    """Process remaining args, extracting flags from non-flags."""
    flags = []
    non_flags = []
    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if arg in SIMPLE_FLAGS:
            flags.append(arg)
            i += 1
        elif arg in VALUE_FLAGS:
            extracted, consumed = _extract_flag_and_value(remaining, i)
            flags.extend(extracted)
            i += consumed
        else:
            non_flags.append(arg)
            i += 1
    return flags, non_flags


def _build_filter_argv(args, remaining):
    """Build argv for filter parsing, excluding processed flags."""
    filter_argv = []
    if args.service:
        filter_argv.append(args.service)
    if args.action:
        filter_argv.append(args.action)

    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if arg in SIMPLE_FLAGS:
            i += 1
            continue
        if arg in VALUE_FLAGS:
            i += 1
            if i < len(remaining) and not remaining[i].startswith("-"):
                i += 1
            continue
        filter_argv.append(arg)
        i += 1
    return filter_argv


def determine_column_filters(column_filters, service, action):
    """Determine which column filters to apply - user specified or defaults"""
    if column_filters:
        debug_print(f"Using user-specified column filters: {column_filters}")  # pragma: no mutate
        return column_filters

    # Check for defaults - normalize action name for lookup
    from .utils import normalize_action_name

    normalized_action = normalize_action_name(action)
    default_columns = apply_default_filters(service, normalized_action)
    if default_columns:
        debug_print(
            f"Applying default column filters for {service}.{normalized_action}: {default_columns}"
        )  # pragma: no mutate
        return default_columns

    debug_print(
        f"No column filters (user or default) for {service}.{normalized_action}"
    )  # pragma: no mutate
    return None


def _has_prefix_matches(current_input, available_operations):
    """Check if any available operations start with the current input."""
    if not current_input or not available_operations:
        return False

    current_input_lower = current_input.lower()
    return any(op.lower().startswith(current_input_lower) for op in available_operations)


def find_hint_function(hint, service, session=None):
    """Find the best matching AWS function based on hint string.

    Args:
        hint: The hint string (e.g., "desc-clus" or "desc-clus:clusterarn")
        service: AWS service name
        session: Optional boto3 session

    Returns:
        tuple: (selected_function, field_hint, alternatives) or (None, None, []) if no matches
        where field_hint is the suggested field to extract (or None for default heuristic)
    """

    if not hint or not service:
        return None, None, []

    # Parse hint format: function:field or just function
    function_hint = hint
    field_hint = None
    if ":" in hint:
        function_hint, field_hint = hint.split(":", 1)
        field_hint = field_hint.strip() if field_hint else None

    function_hint = function_hint.strip()
    if not function_hint:
        return None, None, []

    try:
        # Get all operations for the service first
        import botocore.session

        # Temporarily clear AWS_PROFILE to avoid validation errors
        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            session_temp = botocore.session.Session()
            if service not in session_temp.get_available_services():
                return None, []

            service_model = session_temp.get_service_model(service)
            all_operations = list(service_model.operation_names)
        finally:
            if old_profile is not None:
                os.environ["AWS_PROFILE"] = old_profile

        # Filter to only valid (readonly) operations
        available_operations = get_service_valid_operations(service, all_operations)

        if not available_operations:
            return None, None, []

        # Create mapping of CLI format to original operation names
        operation_mapping = {}
        for op in available_operations:
            cli_format = op.replace("_", "-").lower()
            operation_mapping[cli_format] = op

        # Find all matches using the enhanced validator with function_hint
        matched_cli_names = []
        for cli_op in operation_mapping.keys():
            if _enhanced_completion_validator(cli_op, function_hint):
                matched_cli_names.append(cli_op)

        if not matched_cli_names:
            return None, None, []

        # Sort by preference: shortest first, then alphabetical
        matched_cli_names.sort(key=lambda x: (len(x), x))

        # Return original operation names, not CLI format
        selected_cli = matched_cli_names[0]
        selected_operation = operation_mapping[selected_cli]

        alternative_operations = []
        for cli_name in matched_cli_names[1:]:
            alternative_operations.append(operation_mapping[cli_name])

        return selected_operation, field_hint, alternative_operations

    except Exception:
        return None, None, []


def _enhanced_completion_validator(completion_candidate, current_input):
    """Custom argcomplete validator for enhanced action matching with smart prefix priority."""
    if not current_input:
        return True

    current_input_lower = current_input.lower()
    candidate_lower = completion_candidate.lower()

    # 1. Exact prefix match (highest priority)
    if candidate_lower.startswith(current_input_lower):
        return True

    # 2. Smart prefix matching: If any operations start with current_input,
    #    exclude operations that only contain it as a substring
    available_operations = _current_completion_context.get("operations", [])
    if _has_prefix_matches(current_input, available_operations):
        # Only allow prefix matches when prefix matches exist
        return candidate_lower.startswith(current_input_lower)

    # 3. Partial substring match (when no prefix matches exist)
    if current_input_lower in candidate_lower:
        return True

    # 4. Split match - all parts must be found as substrings
    parts = [part for part in current_input_lower.split("-") if part]
    if len(parts) > 1 and all(part in candidate_lower for part in parts):
        return True

    return False


def action_completer(prefix, parsed_args, **kwargs):
    """Autocomplete action names based on selected service"""
    if not parsed_args.service:
        return []

    service = parsed_args.service

    try:
        # Create a client with minimal configuration to get operation names
        # This doesn't require valid AWS credentials, just the service model
        import botocore.session

        # Temporarily clear AWS_PROFILE to avoid validation errors
        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            session = botocore.session.Session()

            # Check if service exists in botocore's data
            if service not in session.get_available_services():
                return []

            # Load the service model to get operations
            service_model = session.get_service_model(service)
            operations = list(service_model.operation_names)
        finally:
            # Restore AWS_PROFILE if it existed
            if old_profile is not None:
                os.environ["AWS_PROFILE"] = old_profile

        # Filter operations to only show read-only ones in autocomplete
        valid_operations = get_service_valid_operations(service, operations)

        # Convert to CLI format
        cli_operations = []
        for op in operations:
            if op in valid_operations:
                kebab_case = re.sub("([a-z0-9])([A-Z])", r"\1-\2", op).lower()
                cli_operations.append(kebab_case)

        # Return all valid operations - let argcomplete validator handle filtering
        all_operations = sorted(cli_operations)

        # Update global context for smart prefix matching
        _current_completion_context["operations"] = all_operations
        _current_completion_context["current_input"] = prefix or ""

        return all_operations
    except Exception:
        # If we can't get operations, return empty
        return []


class CLIArgumentProcessor:
    """Handles CLI argument processing and validation"""

    def __init__(self) -> None:
        """Initialize CLI argument processor."""
        self.parser: Optional[argparse.ArgumentParser] = None
        self.args: Optional[argparse.Namespace] = None
        self.remaining: Optional[List[str]] = None

    def create_parser(self) -> argparse.ArgumentParser:
        """Create and configure the argument parser"""
        self.parser = argparse.ArgumentParser(
            description=(
                "Query AWS APIs with flexible filtering and automatic parameter resolution"
            ),  # pragma: no mutate
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""  # pragma: no mutate
Examples:
  awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
  awsquery s3 list-buckets backup
  awsquery ec2 describe-instances  (shows available keys)
  awsquery cloudformation describe-stack-events prod -- Created -- StackName (multi-level)
  awsquery ec2 describe-instances --keys  (show all keys)
  awsquery cloudformation describe-stack-resources workers --keys -- EKS (multi-level keys)
  awsquery ec2 describe-instances --debug  (enable debug output)
  awsquery cloudformation describe-stack-resources workers --debug -- EKS (debug multi-level)

Autocomplete Setup:
  Bash:
    eval "$(register-python-argcomplete awsquery)"

  Zsh:
    autoload -U bashcompinit && bashcompinit
    eval "$(register-python-argcomplete awsquery)"

  Fish:
    register-python-argcomplete --shell fish awsquery | source

  Add the appropriate command to your shell config (~/.bashrc, ~/.zshrc, etc.)
  For more details: https://github.com/flomotlik/awsquery#enable-shell-autocomplete
        """,
        )

        self.parser.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="Output results in JSON format instead of table",  # pragma: no mutate
        )
        self.parser.add_argument(
            "-k",
            "--keys",
            action="store_true",
            help="Show all available keys for the command",  # pragma: no mutate
        )
        self.parser.add_argument(
            "-d", "--debug", action="store_true", help="Enable debug output"
        )  # pragma: no mutate
        self.parser.add_argument(
            "--region", help="AWS region to use for requests"
        )  # pragma: no mutate
        self.parser.add_argument(
            "--profile", help="AWS profile to use for requests"
        )  # pragma: no mutate
        self.parser.add_argument(
            "-p",
            "--parameter",
            action="append",
            help="Add parameter to AWS API call (e.g., -p InstanceIds=i-123,i-456)",
        )  # pragma: no mutate
        self.parser.add_argument(
            "-i",
            "--input",
            help="Hint for multi-step call function selection (e.g., -i desc-clus)",
        )  # pragma: no mutate
        self.parser.add_argument(
            "--allow-unsafe",
            action="store_true",
            help="Allow potentially unsafe operations without prompting",  # pragma: no mutate
        )
        self.parser.add_argument(
            "service", nargs="?", help="AWS service name (e.g., ec2, s3)"
        )  # pragma: no mutate
        self.parser.add_argument(
            "action", nargs="?", help="AWS action/operation name"
        )  # pragma: no mutate

        # Enable autocompletion
        argcomplete.autocomplete(self.parser)

        return self.parser

    def parse_initial_args(self) -> Tuple[argparse.Namespace, List[str]]:
        """Parse initial arguments and handle reordering if needed"""
        if not self.parser:
            self.create_parser()

        if self.parser is None:
            raise RuntimeError("Failed to create argument parser")

        self.args, self.remaining = self.parser.parse_known_args()

        if self.remaining:
            self._reorder_arguments()

        return self.args, self.remaining

    def _reorder_arguments(self) -> None:
        """Reorder arguments to handle flags mixed with positional args"""
        if self.args is None or self.remaining is None:
            raise RuntimeError("Arguments must be parsed before reordering")

        # Check if -- separator was in the original command line
        has_separator = "--" in sys.argv
        separator_in_remaining = "--" in self.remaining

        # Re-parse with the full argument list to catch all flags
        reordered_argv = [sys.argv[0]]  # Program name
        flags = []
        non_flags = []

        # Preserve flags that were already successfully parsed
        if self.args.debug:
            flags.append("-d")
        if getattr(self.args, "json", False):
            flags.append("-j")
        if getattr(self.args, "keys", False):
            flags.append("-k")
        if getattr(self.args, "allow_unsafe", False):
            flags.append("--allow-unsafe")
        if getattr(self.args, "region", None):
            flags.extend(["--region", self.args.region])
        if getattr(self.args, "profile", None):
            flags.extend(["--profile", self.args.profile])
        if getattr(self.args, "parameter", None):
            for param in self.args.parameter:
                flags.extend(["-p", param])
        if getattr(self.args, "input", None):
            flags.extend(["-i", self.args.input])

        # Process remaining arguments based on separator presence
        if has_separator and not separator_in_remaining:
            extracted_flags, non_flags = _process_remaining_args_after_separator(self.remaining)
            flags.extend(extracted_flags)
            if non_flags and "--" not in non_flags:
                non_flags.insert(0, "--")
        else:
            extracted_flags, non_flags = _process_remaining_args(self.remaining)
            flags.extend(extracted_flags)

        # Rebuild argv with proper order
        reordered_argv.extend(flags)
        if self.args.service:
            reordered_argv.append(self.args.service)
        if self.args.action:
            reordered_argv.append(self.args.action)

        # Re-parse with reordered arguments
        if self.parser is None:
            raise RuntimeError("Parser not available for reordering")

        self.args, _ = self.parser.parse_known_args(reordered_argv[1:])
        self.remaining = non_flags


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Query AWS APIs with flexible filtering and automatic parameter resolution"
        ),  # pragma: no mutate
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""  # pragma: no mutate
Examples:
  awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
  awsquery s3 list-buckets backup
  awsquery ec2 describe-instances  (shows available keys)
  awsquery cloudformation describe-stack-events prod -- Created -- StackName (multi-level)
  awsquery ec2 describe-instances --keys  (show all keys)
  awsquery cloudformation describe-stack-resources workers --keys -- EKS (multi-level keys)
  awsquery ec2 describe-instances --debug  (enable debug output)
  awsquery cloudformation describe-stack-resources workers --debug -- EKS (debug multi-level)

Autocomplete Setup:
  Bash:
    eval "$(register-python-argcomplete awsquery)"

  Zsh:
    autoload -U bashcompinit && bashcompinit
    eval "$(register-python-argcomplete awsquery)"

  Fish:
    register-python-argcomplete --shell fish awsquery | source

  Add the appropriate command to your shell config (~/.bashrc, ~/.zshrc, etc.)
  For more details: https://github.com/flomotlik/awsquery#enable-shell-autocomplete
        """,
    )

    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output results in JSON format instead of table",  # pragma: no mutate
    )
    parser.add_argument(
        "-k",
        "--keys",
        action="store_true",
        help="Show all available keys for the command",  # pragma: no mutate
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug output"
    )  # pragma: no mutate
    parser.add_argument("--region", help="AWS region to use for requests")  # pragma: no mutate
    parser.add_argument("--profile", help="AWS profile to use for requests")  # pragma: no mutate
    parser.add_argument(
        "-p",
        "--parameter",
        action="append",
        help="Add parameter to AWS API call (e.g., -p InstanceIds=i-123,i-456)",
    )  # pragma: no mutate
    parser.add_argument(
        "-i",
        "--input",
        help="Hint for multi-step call function selection (e.g., -i desc-clus)",
    )  # pragma: no mutate
    parser.add_argument(
        "--allow-unsafe",
        action="store_true",
        help="Allow potentially unsafe (non-readonly) operations without prompting",
    )  # pragma: no mutate

    service_arg = parser.add_argument(
        "service", nargs="?", help="AWS service name"
    )  # pragma: no mutate
    service_arg.completer = service_completer  # type: ignore[attr-defined]

    action_arg = parser.add_argument(
        "action", nargs="?", help="Service action name"
    )  # pragma: no mutate
    action_arg.completer = action_completer  # type: ignore[attr-defined]

    argcomplete.autocomplete(parser, validator=_enhanced_completion_validator)

    # First pass: parse known args to get service and action
    args, remaining = parser.parse_known_args()

    # If there are remaining args, check if any are flags that should be parsed
    # This handles cases where flags appear after service/action but BEFORE --
    if remaining:
        # Check if -- separator was in the original command line
        # argparse removes -- when it's right after recognized arguments,
        # so we need to check sys.argv to know if it was there
        has_separator = "--" in sys.argv
        separator_in_remaining = "--" in remaining

        # Re-parse with the full argument list to catch all flags
        # We need to build a new argv that puts flags before positional args
        reordered_argv = [sys.argv[0]]  # Program name
        flags = []
        non_flags = []

        # Preserve flags that were already successfully parsed
        if args.debug:
            flags.append("-d")
        if getattr(args, "json", False):
            flags.append("-j")
        if getattr(args, "keys", False):
            flags.append("-k")
        if getattr(args, "allow_unsafe", False):
            flags.append("--allow-unsafe")
        if getattr(args, "region", None):
            flags.extend(["--region", args.region])
        if getattr(args, "profile", None):
            flags.extend(["--profile", args.profile])
        if getattr(args, "parameter", None):
            for param in args.parameter:
                flags.extend(["-p", param])
        if getattr(args, "input", None):
            flags.extend(["-i", args.input])

        # If -- was in original but not in remaining, it means everything
        # in remaining is after the -- separator
        if has_separator and not separator_in_remaining:
            extracted_flags, non_flags = _process_remaining_args_after_separator(remaining)
            flags.extend(extracted_flags)
            # Re-insert the -- separator at the beginning for filter parsing
            if non_flags and "--" not in non_flags:
                non_flags.insert(0, "--")
        else:
            # Separate flags from non-flags in remaining args
            extracted_flags, non_flags = _process_remaining_args(remaining)
            flags.extend(extracted_flags)

        # Add flags to reordered_argv
        # The flags list contains all flags found in remaining args
        reordered_argv.extend(flags)

        # Add service and action
        if args.service:
            reordered_argv.append(args.service)
        if args.action:
            reordered_argv.append(args.action)

        # Re-parse with reordered arguments
        args, remaining = parser.parse_known_args(reordered_argv[1:])

        # Remaining should now only be non-flag arguments
        remaining = non_flags

    # Set debug mode globally
    from . import utils

    utils.set_debug_enabled(args.debug)

    # Build the argv for filter parsing (service, action, and remaining arguments)
    # But exclude any flags that were already processed
    filter_argv = _build_filter_argv(args, remaining)

    base_command, resource_filters, value_filters, column_filters = (
        parse_multi_level_filters_for_mode(filter_argv, mode="single")
    )

    if not args.service or not args.action:
        services = get_aws_services()
        print("Available services:", ", ".join(services))
        sys.exit(0)

    service = sanitize_input(args.service)
    action = sanitize_input(args.action)
    resource_filters = [sanitize_input(f) for f in resource_filters] if resource_filters else []
    value_filters = [sanitize_input(f) for f in value_filters] if value_filters else []
    column_filters = [sanitize_input(f) for f in column_filters] if column_filters else []

    # Parse -p parameters if provided
    parsed_parameters = {}
    if args.parameter:
        for param_str in args.parameter:
            try:
                param_dict = parse_parameter_string(param_str)
                parsed_parameters.update(param_dict)
            except ValueError as e:
                print(f"ERROR: Invalid parameter format '{param_str}': {e}", file=sys.stderr)
                sys.exit(1)

    debug_print(
        f"DEBUG: Parsed parameters (before type correction): {parsed_parameters}"
    )  # pragma: no mutate

    # Validate and correct parameter types
    if parsed_parameters:
        corrected_parameters = {}
        for key, value in parsed_parameters.items():
            expected_type = get_parameter_type(service, action, key, session=None)

            if expected_type == "list" and not isinstance(value, list):
                # Auto-wrap single values in list
                debug_print(
                    f"Auto-wrapping parameter '{key}' in list "
                    f"(expected type: list, got: {type(value).__name__})"
                )
                corrected_parameters[key] = [value]
            else:
                corrected_parameters[key] = value

        parsed_parameters = corrected_parameters

    debug_print(
        f"DEBUG: Parsed parameters (after type correction): {parsed_parameters}"
    )  # pragma: no mutate

    def _execute_multi_level_workflow(
        service, action, filter_argv, session, hint_function, hint_field
    ):
        """Helper to execute multi-level call with filter parsing."""
        _, multi_resource_filters, multi_value_filters, multi_column_filters = (
            parse_multi_level_filters_for_mode(filter_argv, mode="multi")
        )
        final_multi_column_filters = determine_column_filters(multi_column_filters, service, action)
        return execute_multi_level_call(
            service,
            action,
            multi_resource_filters,
            multi_value_filters,
            final_multi_column_filters,
            session,
            hint_function,
            hint_field,
        )

    # Process -i hint if provided
    hint_function = None
    hint_field = None
    hint_alternatives = []
    if args.input:
        hint_function, hint_field, hint_alternatives = find_hint_function(
            args.input, service, session=None
        )
        if hint_function:
            # Convert hint function to CLI format for display
            from .utils import pascal_to_kebab_case

            hint_function_cli = pascal_to_kebab_case(hint_function)
            if hint_field:
                print(
                    f"Using hint function '{hint_function_cli}' with field '{hint_field}' "
                    f"for multi-step calls",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Using hint function '{hint_function_cli}' for multi-step calls",
                    file=sys.stderr,
                )
            if hint_alternatives:
                # Convert alternatives to CLI format for display
                cli_alternatives = [pascal_to_kebab_case(alt) for alt in hint_alternatives]
                print(f"Alternative options: {', '.join(cli_alternatives)}", file=sys.stderr)
            debug_print(
                f"DEBUG: Hint '{args.input}' matched function: {hint_function}"
            )  # pragma: no mutate
            if hint_alternatives:
                cli_alternatives_debug = [pascal_to_kebab_case(alt) for alt in hint_alternatives]
                debug_print(
                    f"DEBUG: Alternative matches: {', '.join(cli_alternatives_debug)}"
                )  # pragma: no mutate
        else:
            print(
                f"Warning: Hint '{args.input}' did not match any available functions",
                file=sys.stderr,
            )
            debug_print(f"DEBUG: Hint '{args.input}' found no matches")  # pragma: no mutate

    # Validate operation safety (only if we have a non-empty action)
    if (
        action is not None
        and action
        and str(action).strip() != "None"
        and not validate_readonly(service, action, allow_unsafe=args.allow_unsafe)
    ):
        print(f"ERROR: Operation {service}:{action} was not allowed", file=sys.stderr)
        sys.exit(1)

    debug_print(f"DEBUG: Operation {service}:{action} validated successfully")  # pragma: no mutate

    # Create session with region/profile if specified
    session = create_session(region=args.region, profile=args.profile)
    debug_print(
        f"DEBUG: Created session with region={args.region}, profile={args.profile}"
    )  # pragma: no mutate

    # Determine final column filters (user-specified or defaults)
    final_column_filters = determine_column_filters(column_filters, service, action)

    if args.keys:
        print(f"Showing all available keys for {service}.{action}:", file=sys.stderr)

        try:
            # Use tracking to get keys from the last successful request
            call_result = execute_with_tracking(
                service, action, parameters=parsed_parameters, session=session
            )

            # If the initial call failed, try multi-level resolution
            if not call_result.final_success:
                debug_print(
                    "Keys mode: Initial call failed, trying multi-level resolution"
                )  # pragma: no mutate
                _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                    parse_multi_level_filters_for_mode(filter_argv, mode="multi")
                )
                call_result, _ = execute_multi_level_call_with_tracking(
                    service,
                    action,
                    multi_resource_filters,
                    multi_value_filters,
                    multi_column_filters,
                    session=session,
                    hint_function=hint_function,
                    hint_field=hint_field,
                )

            result = show_keys_from_result(call_result)
            print(result)
            return
        except Exception as e:
            print(f"Could not retrieve keys: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        requirements = check_parameter_requirements(service, action, parsed_parameters, session)

        if requirements["needs_params"]:
            debug_print(
                f"Preemptive multi-step: missing required parameters "
                f"{requirements['missing_required']}"
            )  # pragma: no mutate
            debug_print(
                "Skipping initial API call, going directly to multi-level resolution"
            )  # pragma: no mutate

            filtered_resources = _execute_multi_level_workflow(
                service, action, filter_argv, session, hint_function, hint_field
            )
            debug_print(
                f"Multi-level call completed with {len(filtered_resources)} resources"
            )  # pragma: no mutate

        elif requirements["conditional"] and not parsed_parameters:
            print(f"Note: {requirements['conditional']}", file=sys.stderr)
            print("Attempting to list all resources...", file=sys.stderr)

            debug_print(
                "Using single-level execution (conditional requirements noted)"
            )  # pragma: no mutate
            response = execute_aws_call(
                service, action, parameters=parsed_parameters, session=session
            )

            resources = flatten_response(response)
            debug_print(f"Total resources extracted: {len(resources)}")  # pragma: no mutate
            filtered_resources = filter_resources(resources, value_filters)

        else:
            debug_print("Using single-level execution")  # pragma: no mutate
            response = execute_aws_call(
                service, action, parameters=parsed_parameters, session=session
            )

            if isinstance(response, dict) and "validation_error" in response:
                debug_print(
                    "Unexpected validation error, switching to multi-level"
                )  # pragma: no mutate
                filtered_resources = _execute_multi_level_workflow(
                    service, action, filter_argv, session, hint_function, hint_field
                )
            else:
                resources = flatten_response(response)
                debug_print(f"Total resources extracted: {len(resources)}")  # pragma: no mutate

                filtered_resources = filter_resources(resources, value_filters)

        if final_column_filters:
            for filter_word in final_column_filters:
                debug_print(f"Applying column filter: {filter_word}")  # pragma: no mutate

        if args.keys:
            sorted_keys = extract_and_sort_keys(filtered_resources)
            output = "\n".join(f"  {key}" for key in sorted_keys)
            print("All available keys:", file=sys.stderr)
            print(output)
        else:
            if args.json:
                output = format_json_output(filtered_resources, final_column_filters)
            else:
                output = format_table_output(filtered_resources, final_column_filters)
            print(output)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
