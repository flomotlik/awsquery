"""Command-line interface for AWS Query Tool."""

# pylint: disable=too-many-lines

import argparse
import os
import re
import sys
import traceback
from typing import Any

import argcomplete
import boto3

from .auto_filters import smart_select_columns
from .case_utils import to_kebab_case, to_snake_case
from .config import apply_default_filters, get_default_action
from .core import (
    check_parameter_requirements,
    execute_aws_call,
    execute_multi_level_call,
    execute_multi_level_call_with_tracking,
    execute_with_tracking,
    keys_from_result,
)
from .errors import (
    ExitCode,
    classify_exception,
    emit_notice,
    fail,
    looks_like_auth_failure,
    set_structured_errors,
)
from .filters import filter_resources, parse_multi_level_filters_for_mode
from .formatters import (
    flatten_response,
    format_csv_output,
    format_json_output,
    format_keys_output,
    format_ndjson_output,
    format_table_output,
    format_tsv_output,
)
from .introspection import (
    list_actions,
    list_services,
    print_docs,
    print_schema,
    validate_service_action,
)
from .security import (
    get_service_valid_operations,
    validate_readonly,
)
from .utils import (
    _BotocoreSessionContext,
    create_session,
    debug_print,
    get_aws_services,
    get_debug_enabled,
    get_service_operations,
    sanitize_input,
)

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
        from .case_utils import to_pascal_case

        with _BotocoreSessionContext() as botocore_session:
            service_model = botocore_session.get_service_model(service)

            # Convert action to PascalCase for operation model lookup
            if "-" in action:
                pascal_action = to_pascal_case(action.replace("-", "_"))
            else:
                pascal_action = to_pascal_case(action)

            # Get operation model
            operation_model = service_model.operation_model(pascal_action)

            if (
                operation_model.input_shape
                and parameter_name in operation_model.input_shape.members
            ):
                param_shape = operation_model.input_shape.members[parameter_name]
                return param_shape.type_name

            return None

    except Exception as e:
        debug_print(f"Could not determine parameter type for {parameter_name}: {e}")
        return None


# CLI flag constants
SIMPLE_FLAGS = [
    "-d",
    "--debug",
    "-j",
    "--json",
    "-k",
    "--keys",
    "--allow-unsafe",
    "--list-services",
    "--list-actions",
    "--schema",
    "--docs",
]
VALUE_FLAGS = [
    "--region",
    "--profile",
    "-p",
    "--parameter",
    "-i",
    "--input",
    "--format",
    "--limit",
]

OUTPUT_FORMATS = ["table", "json", "csv", "tsv", "ndjson"]
MACHINE_FORMATS = {"json", "ndjson", "csv", "tsv"}
STRUCTURED_ERROR_FORMATS = {"json", "ndjson"}


def service_completer(prefix, parsed_args, **kwargs):
    """Autocomplete AWS service names"""
    services = get_aws_services()
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


def _inject_default_action(argv):
    """Splice the configured default action in after a bare service name."""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            return argv
        if arg in VALUE_FLAGS:
            i += 2 if (i + 1 < len(argv) and not argv[i + 1].startswith("-")) else 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        break
    if i >= len(argv):
        return argv
    service = argv[i]
    following = argv[i + 1] if i + 1 < len(argv) else None
    if following is not None and following != "--" and not following.startswith("-"):
        return argv
    action = get_default_action(service)
    if not action:
        return argv
    action = to_kebab_case(to_snake_case(action))
    debug_print(f"Using default action for {service}: {action}")  # pragma: no mutate
    return argv[: i + 1] + [action] + argv[i + 1 :]


def _format_columns_copyable(columns, additive_marks=None):
    """Format column list as copy-pasteable command snippet.

    When additive_marks is a list of bools matching len(columns), entries at
    True positions are rendered with a leading '+' so the echoed command stays
    runnable in additive mode.
    """
    if not columns:
        return ""
    if additive_marks is None or len(additive_marks) != len(columns):
        return "-- " + " ".join(columns)
    rendered = [
        f"+{col}" if mark and not col.startswith("+") else col
        for col, mark in zip(columns, additive_marks)
    ]
    return "-- " + " ".join(rendered)


def determine_column_filters(column_filters, service, action, json_output=False):
    """Determine which column filters to apply - user specified or defaults"""
    from .utils import normalize_action_name

    normalized_action = normalize_action_name(action)

    additive_present = any(isinstance(c, str) and c.startswith("+") for c in (column_filters or []))

    if additive_present:
        stripped = [
            c[1:] if isinstance(c, str) and c.startswith("+") else c for c in column_filters
        ]
        debug_print(f"Additive mode detected; stripped columns: {stripped}")  # pragma: no mutate
        merged = apply_default_filters(
            service, normalized_action, user_columns=stripped, additive=True
        )
        column_filters_to_use = merged if merged else stripped
        if not json_output:
            defaults_only = apply_default_filters(service, normalized_action) or []
            defaults_set = set(defaults_only)
            additive_marks = [c not in defaults_set for c in (column_filters_to_use or [])]
            cols = _format_columns_copyable(column_filters_to_use, additive_marks=additive_marks)
            print(f"Using default columns + additions: {cols}", file=sys.stderr)
    elif column_filters:
        debug_print(f"Using user-specified column filters: {column_filters}")  # pragma: no mutate
        column_filters_to_use = column_filters
    else:
        # Check for defaults - action already normalized at function top
        default_columns = apply_default_filters(service, normalized_action)
        if default_columns:
            debug_print(
                f"Applying default column filters for "
                f"{service}.{normalized_action}: {default_columns}"
            )  # pragma: no mutate
            column_filters_to_use = default_columns
            if not json_output:
                cols = _format_columns_copyable(default_columns)
                print(f"Using default columns: {cols}", file=sys.stderr)
        else:
            # Try auto-selection using shape introspection
            from .shapes import get_shape_cache

            shape_cache = get_shape_cache()
            auto_fields = shape_cache.get_fields_for_auto_select(service, action)
            if auto_fields:
                auto_columns = smart_select_columns(auto_fields, operation=action)
                if auto_columns:
                    # Wrap with exact match syntax to avoid partial matches
                    exact_columns = [f"^{col}$" for col in auto_columns]
                    debug_print(
                        f"Auto-selected columns for {service}.{normalized_action}: {exact_columns}"
                    )  # pragma: no mutate
                    column_filters_to_use = exact_columns
                    if not json_output:
                        cols = _format_columns_copyable(exact_columns)
                        print(f"Auto-selected columns: {cols}", file=sys.stderr)
                else:
                    debug_print(
                        f"No eligible columns for auto-selection, "
                        f"showing all for {service}.{normalized_action}"
                    )  # pragma: no mutate
                    column_filters_to_use = None
            else:
                debug_print(
                    f"No column filters (user or default) for {service}.{normalized_action}"
                )  # pragma: no mutate
                column_filters_to_use = None

    # Validate column filters against response shapes (MANDATORY)
    if column_filters_to_use and service and action:
        from .filter_validator import FilterValidator

        validator = FilterValidator()
        validation_results = validator.validate_columns(service, action, column_filters_to_use)

        # Print warnings for invalid filters (but don't fail - user might know better)
        errors = [(filter_pattern, error) for filter_pattern, error in validation_results if error]
        if errors:
            print(
                "WARNING: Some column filters may not match response fields:",
                file=sys.stderr,
            )
            for filter_pattern, error in errors:
                print(f"  - {error}", file=sys.stderr)

    return column_filters_to_use


def _has_prefix_matches(current_input, available_operations):
    """Check if any available operations start with the current input."""
    if not current_input or not available_operations:
        return False

    current_input_lower = current_input.lower()
    return any(op.lower().startswith(current_input_lower) for op in available_operations)


def _parse_function_field_limit(parts):
    """Parse parts array as function:field:limit format.

    Args:
        parts: List of string parts from split

    Returns:
        tuple: (function_hint, field_hint, limit)
    """
    function_hint = parts[0].strip() if parts[0].strip() else None
    field_hint = None
    limit = None

    if len(parts) >= 2:
        field_hint = parts[1].strip() if parts[1].strip() else None
    if len(parts) >= 3:
        limit_str = parts[2].strip()
        if limit_str and limit_str.isdigit():
            limit = int(limit_str)

    return function_hint, field_hint, limit


def _parse_with_service_prefix(parts, potential_service, available_services):
    """Parse hint when first part might be a service name.

    Args:
        parts: List of string parts from split
        potential_service: First part that might be service name
        available_services: List of valid AWS service names

    Returns:
        tuple: (resolved_service, function_hint, field_hint, limit)
    """
    if potential_service not in available_services:
        debug_print(f"'{potential_service}' is not a valid AWS service")  # pragma: no mutate
        return None, *_parse_function_field_limit(parts)

    # This is a service prefix
    resolved_service = potential_service
    debug_print(f"Detected service prefix: {resolved_service}")  # pragma: no mutate

    # Re-parse remaining parts as function:field:limit
    remaining = ":".join(parts[1:])
    if not remaining:
        return resolved_service, None, None, None

    remaining_parts = remaining.split(":", 2)
    function_hint, field_hint, limit = _parse_function_field_limit(remaining_parts)
    return resolved_service, function_hint, field_hint, limit


def find_hint_function(hint, service, session=None):
    """Find the best matching AWS function based on hint string.

    Args:
        hint: The hint string with formats:
              - "[service:]function" - optional service prefix + function hint
              - "[service:]function:field" - with field hint
              - "[service:]function:field:N" - with field and limit
              - ":field" - just field hint (use inferred function)
              - ":field:N" - field + limit (use inferred function)
              - "::N" - just limit (use inferred function, default field)
        service: AWS service name (fallback if no service prefix in hint)
        session: Optional boto3 session

    Returns:
        tuple: (resolved_service, selected_function, field_hint, limit, alternatives)
               - resolved_service: Service from hint prefix or None if using fallback
               - selected_function: None if no function specified
               - field_hint: None for default heuristic, string for specific field
               - limit: Integer limit or None for unlimited
               - alternatives: List of alternative function matches
    """

    if not hint or not service:
        return None, None, None, None, []

    # Parse hint format: [service:]function:field:N with support for empty parts
    parts = hint.split(":", 3)
    debug_print(f"Parsing hint '{hint}' into parts: {parts}")  # pragma: no mutate

    resolved_service = None
    function_hint = None
    field_hint = None
    limit = None

    # Check if first part is a valid AWS service
    if len(parts) >= 1 and parts[0].strip():
        potential_service = parts[0].strip().lower()

        try:
            available_services = get_aws_services()
            resolved_service, function_hint, field_hint, limit = _parse_with_service_prefix(
                parts, potential_service, available_services
            )
        except Exception:
            # If we can't check services, treat as function:field:limit format
            function_hint, field_hint, limit = _parse_function_field_limit(parts)
    else:
        # First part is empty (starts with :), parse as :field:limit
        if len(parts) >= 2:
            field_hint = parts[1].strip() if parts[1].strip() else None
        if len(parts) >= 3:
            limit_str = parts[2].strip()
            if limit_str and limit_str.isdigit():
                limit = int(limit_str)

    debug_print(
        f"Parsed - service: {resolved_service}, function: {function_hint}, "
        f"field: {field_hint}, limit: {limit}"
    )  # pragma: no mutate

    if not function_hint:
        debug_print("No function hint provided, will use inferred function")  # pragma: no mutate
        return resolved_service, None, field_hint, limit, []

    # Use resolved service if found, otherwise use the provided fallback service
    target_service = resolved_service if resolved_service else service

    try:
        # Get all operations for the target service
        all_operations = get_service_operations(target_service)
        if not all_operations:
            return resolved_service, None, field_hint, limit, []

        # Filter to only valid (readonly) operations
        available_operations = get_service_valid_operations(target_service, all_operations)

        if not available_operations:
            return resolved_service, None, field_hint, limit, []

        # Create mapping of CLI format to original operation names
        operation_mapping = {}
        for op in available_operations:
            cli_format = to_kebab_case(op)
            operation_mapping[cli_format] = op

        # Find all matches using the enhanced validator with function_hint
        matched_cli_names = []
        for cli_op in operation_mapping.keys():
            if _enhanced_completion_validator(cli_op, function_hint):
                matched_cli_names.append(cli_op)

        if not matched_cli_names:
            return resolved_service, None, field_hint, limit, []

        # Sort by preference: shortest first, then alphabetical
        matched_cli_names.sort(key=lambda x: (len(x), x))

        # Return original operation names, not CLI format
        selected_cli = matched_cli_names[0]
        selected_operation = operation_mapping[selected_cli]

        alternative_operations = []
        for cli_name in matched_cli_names[1:]:
            alternative_operations.append(operation_mapping[cli_name])

        return resolved_service, selected_operation, field_hint, limit, alternative_operations

    except Exception:
        return resolved_service, None, field_hint, limit, []


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


def _print_service_actions(service):
    """List a service's read-only actions on stderr when no default is configured."""
    operations = get_service_operations(service)
    if not operations:
        fail(
            ExitCode.USAGE,
            "UnknownService",
            f"Unknown service '{service}'",
            hint="Run: awsquery --list-services",
        )
    valid = get_service_valid_operations(service, operations)
    actions = sorted(to_kebab_case(op) for op in operations if op in valid)
    print(
        f"No default action configured for '{service}'. Available actions:",
        file=sys.stderr,
    )
    for action in actions:
        print(f"  {action}", file=sys.stderr)


def action_completer(prefix, parsed_args, **kwargs):
    """Autocomplete action names based on selected service"""
    if not parsed_args.service:
        return []

    service = parsed_args.service

    try:
        # Get all operations for the service
        operations = get_service_operations(service)
        if not operations:
            return []

        # Filter operations to only show read-only ones in autocomplete
        valid_operations = get_service_valid_operations(service, operations)

        # Convert to CLI format
        cli_operations = []
        for op in operations:
            if op in valid_operations:
                kebab_case = to_kebab_case(op)
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


def _handle_introspection_flags(args, output_format):
    """Answer the credential-free introspection flags and exit."""
    # Name lists are one-per-line under the line-oriented formats; only json wants an array
    as_json = output_format == "json"
    # A schema is a single object, so it stays JSON under both structured formats
    schema_as_json = output_format in STRUCTURED_ERROR_FORMATS

    if args.docs:
        print_docs()
        sys.exit(ExitCode.SUCCESS)

    if args.list_services:
        list_services(as_json=as_json)
        sys.exit(ExitCode.SUCCESS)

    if args.list_actions:
        if not args.service:
            fail(
                ExitCode.USAGE,
                "MissingService",
                "--list-actions needs a service name",
                hint="Run: awsquery --list-services",
            )
        list_actions(sanitize_input(args.service), as_json=as_json)
        sys.exit(ExitCode.SUCCESS)

    if args.schema:
        if not args.service or not args.action:
            fail(
                ExitCode.USAGE,
                "MissingAction",
                "--schema needs a service and an action",
                hint=(
                    f"Run: awsquery {sanitize_input(args.service)} --list-actions"
                    if args.service
                    else "Run: awsquery --list-services"
                ),
            )
        print_schema(
            sanitize_input(args.service), sanitize_input(args.action), as_json=schema_as_json
        )
        sys.exit(ExitCode.SUCCESS)


def _is_real_action(action):
    """Whether an action survived parsing as an actual operation name."""
    return bool(action) and str(action).strip() not in ("", "None")


def _apply_row_limit(resources, limit):
    """Truncate results to limit rows, reporting the truncation on stderr."""
    if limit is None or len(resources) <= limit:
        return resources

    print(f"Showing {limit} of {len(resources)} rows (--limit {limit})", file=sys.stderr)
    return resources[:limit]


def _render_output(resources, column_filters, output_format):
    """Render results in the selected output format."""
    if output_format == "json":
        return format_json_output(resources, column_filters)
    if output_format == "csv":
        return format_csv_output(resources, column_filters)
    if output_format == "tsv":
        return format_tsv_output(resources, column_filters)
    if output_format == "ndjson":
        return format_ndjson_output(resources, column_filters)
    return format_table_output(resources, column_filters)


def _fail_from_call_result(call_result, message):
    """Exit with the AWS/auth exit code matching a failed call result."""
    details = " ".join(call_result.error_messages or [])
    if looks_like_auth_failure(details) or looks_like_auth_failure(message):
        fail(ExitCode.AUTH_ERROR, "CredentialsError", message)
    fail(ExitCode.AWS_ERROR, "AwsApiError", message)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Query AWS APIs with flexible filtering and automatic parameter resolution"
        ),  # pragma: no mutate
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  awsquery --docs  (full reference for AI agents and LLM tool calls)
  awsquery --list-services  (every supported service, no AWS call)
  awsquery ec2 --list-actions  (read-only actions of a service, no AWS call)
  awsquery --schema ec2 describe-instances  (parameters and output fields, no AWS call)
  awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
  awsquery s3 list-buckets backup
  awsquery cloudformation describe-stack-events prod -- Created StackName
  awsquery ssm get-parameters -i ::5  (limit to 5 parameters)
  awsquery elbv2 describe-tags -i desc-clus:arn prod  (function + field hint)
  awsquery ssm describe-instance-patch-states -i ec2:desc-inst:instanceid prod  (cross-service)
  awsquery ec2 describe-instances -p MaxResults=10 prod  (parameter propagation)
  awsquery ec2 describe-instances --keys  (show all keys)
  awsquery ec2 describe-instances --debug  (enable debug output)
  awsquery ec2  (uses the default action, describe-instances)
  awsquery s3 -- Name  (default action + column filter)

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
        """,  # pragma: no mutate
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
        help="Parameter for AWS API call, propagates to list operations (e.g., -p MaxResults=10)",
    )  # pragma: no mutate
    parser.add_argument(
        "-i",
        "--input",
        help=(
            "Multi-step hints: [service:]function:field:limit "
            "(e.g., 'ec2:desc-inst:instanceid', 'desc-clus', ':arn', '::5')"
        ),
    )  # pragma: no mutate
    parser.add_argument(
        "--allow-unsafe",
        action="store_true",
        help="Allow potentially unsafe (non-readonly) operations without prompting",
    )  # pragma: no mutate
    parser.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        default=None,
        help="Output format (default: table); -j is equivalent to --format json",
    )  # pragma: no mutate
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Truncate output to the first N rows",
    )  # pragma: no mutate
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="List every supported AWS service (no AWS call)",
    )  # pragma: no mutate
    parser.add_argument(
        "--list-actions",
        action="store_true",
        help="List a service's read-only actions (no AWS call)",
    )  # pragma: no mutate
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Show an operation's parameters and output fields (no AWS call)",
    )  # pragma: no mutate
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Print the full reference for AI agents and LLM tool calls",
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

    # Enable debug mode ahead of the pre-parse injection step below, so a
    # debug_print inside _inject_default_action is not silently dropped.
    # args.debug (parsed further down) is the authoritative value and is
    # re-applied once available.
    from . import utils

    utils.set_debug_enabled(any(flag in sys.argv[1:] for flag in ("-d", "--debug")))

    # First pass: parse known args to get service and action
    args, remaining = parser.parse_known_args(_inject_default_action(sys.argv[1:]))

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
        if getattr(args, "list_services", False):
            flags.append("--list-services")
        if getattr(args, "list_actions", False):
            flags.append("--list-actions")
        if getattr(args, "schema", False):
            flags.append("--schema")
        if getattr(args, "docs", False):
            flags.append("--docs")
        if getattr(args, "format", None):
            flags.extend(["--format", args.format])
        if getattr(args, "limit", None) is not None:
            flags.extend(["--limit", str(args.limit)])
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

    # Set debug mode globally (authoritative value, supersedes the early guess above)
    utils.set_debug_enabled(args.debug)

    if args.json and args.format not in (None, "json"):
        fail(
            ExitCode.USAGE,
            "ConflictingFormat",
            f"-j/--json conflicts with --format {args.format}",
            hint="Pass only one of -j or --format",
        )

    output_format = "json" if args.json else (args.format or "table")
    set_structured_errors(output_format in STRUCTURED_ERROR_FORMATS)

    try:
        # Credential-free introspection: answer and exit before touching AWS.
        # Its sys.exit raises SystemExit (a BaseException), so it passes through
        # the except Exception boundary below untouched.
        _handle_introspection_flags(args, output_format)

        if args.limit is not None and args.limit < 0:
            fail(ExitCode.USAGE, "InvalidLimit", f"--limit must not be negative (got {args.limit})")

        # Build the argv for filter parsing (service, action, and remaining arguments)
        # But exclude any flags that were already processed
        filter_argv = _build_filter_argv(args, remaining)

        _, resource_filters, value_filters, column_filters = parse_multi_level_filters_for_mode(
            filter_argv, mode="single"
        )

        if not args.service:
            # stdout must stay parseable under the machine formats
            if output_format in MACHINE_FORMATS:
                list_services(as_json=output_format == "json")
            else:
                print("Available services:", ", ".join(get_aws_services()))
            sys.exit(ExitCode.SUCCESS)

        if not args.action:
            _print_service_actions(sanitize_input(args.service))
            fail(
                ExitCode.USAGE,
                "NoDefaultAction",
                f"No default action configured for '{sanitize_input(args.service)}'",
                hint=f"Run: awsquery {sanitize_input(args.service)} --list-actions",
            )

        service = sanitize_input(args.service)
        action = sanitize_input(args.action)

        # Offline: an unknown service or action is a usage error, not a failed AWS call
        validate_service_action(service, action if _is_real_action(action) else None)

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
                    fail(
                        ExitCode.USAGE,
                        "InvalidParameter",
                        f"Invalid parameter format '{param_str}': {e}",
                        hint=f"Run: awsquery --schema {service} {action}",
                    )

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
            service,
            action,
            filter_argv,
            session,
            hint_service,
            hint_function,
            hint_field,
            hint_limit,
            parsed_parameters,
        ):
            """Helper to execute multi-level call with filter parsing."""
            _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                parse_multi_level_filters_for_mode(filter_argv, mode="multi")
            )
            final_multi_column_filters = determine_column_filters(
                multi_column_filters, service, action, json_output=output_format == "json"
            )
            return execute_multi_level_call(
                service,
                action,
                multi_resource_filters,
                multi_value_filters,
                final_multi_column_filters,
                session,
                hint_function,
                hint_field,
                hint_limit,
                user_parameters=parsed_parameters,
                hint_service=hint_service,
            )

        # Process -i hint if provided
        hint_service = None
        hint_function = None
        hint_field = None
        hint_limit = None
        hint_alternatives = []
        if args.input:
            hint_service, hint_function, hint_field, hint_limit, hint_alternatives = (
                find_hint_function(args.input, service, session=None)
            )
            if hint_function:
                # Convert hint function to CLI format for display
                hint_function_cli = to_kebab_case(hint_function)
                hint_parts = []
                if hint_service:
                    hint_parts.append(f"service '{hint_service}'")
                hint_parts.append(f"function '{hint_function_cli}'")
                if hint_field:
                    hint_parts.append(f"field '{hint_field}'")
                if hint_limit is not None:
                    hint_parts.append(f"limit {hint_limit}")

                print(
                    f"Using hint {' with '.join(hint_parts)} for multi-step calls",
                    file=sys.stderr,
                )
                if hint_alternatives:
                    # Convert alternatives to CLI format for display
                    cli_alternatives = [to_kebab_case(alt) for alt in hint_alternatives]
                    print(f"Alternative options: {', '.join(cli_alternatives)}", file=sys.stderr)
                debug_print(
                    f"DEBUG: Hint '{args.input}' matched service: {hint_service}, "
                    f"function: {hint_function}, field: {hint_field}, limit: {hint_limit}"
                )  # pragma: no mutate
                if hint_alternatives:
                    cli_alternatives_debug = [to_kebab_case(alt) for alt in hint_alternatives]
                    debug_print(
                        f"DEBUG: Alternative matches: {', '.join(cli_alternatives_debug)}"
                    )  # pragma: no mutate
            elif hint_field or hint_limit is not None:
                # No function hint but we have field or limit
                hint_parts = []
                if hint_field:
                    hint_parts.append(f"field '{hint_field}'")
                if hint_limit is not None:
                    hint_parts.append(f"limit {hint_limit}")
                print(
                    f"Using hint {' with '.join(hint_parts)} for multi-step calls "
                    f"(function will be inferred)",
                    file=sys.stderr,
                )
                debug_print(
                    f"DEBUG: Hint '{args.input}' - field: {hint_field}, limit: {hint_limit}, "
                    f"function will be inferred"
                )  # pragma: no mutate
            else:
                print(
                    f"Warning: Hint '{args.input}' did not match any available functions",
                    file=sys.stderr,
                )
                debug_print(f"DEBUG: Hint '{args.input}' found no matches")  # pragma: no mutate

        # Validate operation safety (only if we have a non-empty action)
        if _is_real_action(action) and not validate_readonly(
            service, action, allow_unsafe=args.allow_unsafe
        ):
            fail(
                ExitCode.USAGE,
                "UnsafeOperationRefused",
                f"Operation {service}:{action} was not allowed",
                hint="Pass --allow-unsafe to override",
            )

        debug_print(
            f"DEBUG: Operation {service}:{action} validated successfully"
        )  # pragma: no mutate

        # Create session with region/profile if specified
        session = create_session(region=args.region, profile=args.profile)
        debug_print(
            f"DEBUG: Created session with region={args.region}, profile={args.profile}"
        )  # pragma: no mutate

        # Determine final column filters (user-specified or defaults)
        final_column_filters = determine_column_filters(
            column_filters, service, action, json_output=output_format == "json"
        )

        if args.keys:
            print(f"Showing all available keys for {service}.{action}:", file=sys.stderr)
            if args.limit is not None:
                print("Note: --limit does not apply to --keys output", file=sys.stderr)

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
                        hint_service=hint_service,
                        hint_function=hint_function,
                        hint_field=hint_field,
                        limit=hint_limit,
                        user_parameters=parsed_parameters,
                    )

                keys, keys_error = keys_from_result(call_result)

                if not call_result.final_success:
                    # Never let a failure reach stdout as if it were data
                    _fail_from_call_result(
                        call_result, keys_error or "No successful response to show keys from"
                    )

                if keys_error:
                    # Call succeeded but carried no data: an empty result, not a failure
                    emit_notice("EmptyResult", keys_error)
                    print(format_keys_output([], output_format))
                    return

                print(format_keys_output(keys, output_format))
                return
            except Exception as e:
                if get_debug_enabled():
                    traceback.print_exc(file=sys.stderr)
                code, error_type, message, hint = classify_exception(e)
                fail(code, error_type, f"Could not retrieve keys: {message}", hint)

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
                service,
                action,
                filter_argv,
                session,
                hint_service,
                hint_function,
                hint_field,
                hint_limit,
                parsed_parameters,
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

            resources = flatten_response(response, service, action)
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
                    service,
                    action,
                    filter_argv,
                    session,
                    hint_service,
                    hint_function,
                    hint_field,
                    hint_limit,
                    parsed_parameters,
                )
            else:
                resources = flatten_response(response, service, action)
                debug_print(f"Total resources extracted: {len(resources)}")  # pragma: no mutate

                filtered_resources = filter_resources(resources, value_filters)

        if final_column_filters:
            for filter_word in final_column_filters:
                debug_print(f"Applying column filter: {filter_word}")  # pragma: no mutate

        filtered_resources = _apply_row_limit(filtered_resources, args.limit)

        output = _render_output(filtered_resources, final_column_filters, output_format)
        if output or output_format in ("table", "json"):
            print(output)

    except KeyboardInterrupt:
        fail(ExitCode.ERROR, "KeyboardInterrupt", "Operation cancelled by user")
    except Exception as e:  # error boundary: one exit code per failure class
        if get_debug_enabled():
            traceback.print_exc(file=sys.stderr)
        code, error_type, message, hint = classify_exception(e)
        fail(code, error_type, message, hint)


if __name__ == "__main__":
    main()
