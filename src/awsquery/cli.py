"""Command-line interface for AWS Query Tool."""

import argparse
import re
import sys

import argcomplete
import boto3

from .config import apply_default_filters
from .core import (
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
from .security import action_to_policy_format, load_security_policy, validate_security
from .utils import create_session, debug_print, get_aws_services, sanitize_input


def service_completer(prefix, parsed_args, **kwargs):
    """Autocomplete AWS service names"""
    session = boto3.Session()
    services = session.get_available_services()
    return [s for s in services if s.startswith(prefix)]


def determine_column_filters(column_filters, service, action):
    """Determine which column filters to apply - user specified or defaults"""
    if column_filters:
        debug_print(f"Using user-specified column filters: {column_filters}")
        return column_filters

    # Check for defaults - normalize action name for lookup
    from .utils import normalize_action_name

    normalized_action = normalize_action_name(action)
    default_columns = apply_default_filters(service, normalized_action)
    if default_columns:
        debug_print(
            f"Applying default column filters for {service}.{normalized_action}: {default_columns}"
        )
        return default_columns

    debug_print(f"No column filters (user or default) for {service}.{normalized_action}")
    return None


def action_completer(prefix, parsed_args, **kwargs):
    """Autocomplete action names based on selected service"""
    if not parsed_args.service:
        return []

    try:
        client = boto3.client(parsed_args.service)
        operations = client.meta.service_model.operation_names

        try:
            allowed_actions = load_security_policy()
        except:
            allowed_actions = set()
            for op in operations:
                if any(op.startswith(prefix) for prefix in ["Describe", "List", "Get"]):
                    allowed_actions.add(f"{parsed_args.service}:{op}")

        cli_operations = []
        for op in operations:
            if not validate_security(parsed_args.service, op, allowed_actions):
                continue

            kebab_case = re.sub("([a-z0-9])([A-Z])", r"\1-\2", op).lower()
            cli_operations.append(kebab_case)

        matched_ops = [op for op in cli_operations if op.startswith(prefix)]
        return sorted(list(set(matched_ops)))
    except:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Query AWS APIs with flexible filtering and automatic parameter resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  awsquery ec2 describe_instances prod web -- Tags.Name State InstanceId
  awsquery s3 list_buckets backup
  awsquery ec2 describe_instances  (shows available keys)
  awsquery cloudformation describe-stack-events prod -- Created -- StackName (multi-level)
  awsquery ec2 describe_instances --keys  (show all keys)
  awsquery cloudformation describe-stack-resources workers --keys -- EKS (multi-level keys)
  awsquery ec2 describe_instances --debug  (enable debug output)
  awsquery cloudformation describe-stack-resources workers --debug -- EKS (debug multi-level)
        """,
    )

    parser.add_argument(
        "-j", "--json", action="store_true", help="Output results in JSON format instead of table"
    )
    parser.add_argument(
        "-k", "--keys", action="store_true", help="Show all available keys for the command"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--region", help="AWS region to use for requests")
    parser.add_argument("--profile", help="AWS profile to use for requests")

    service_arg = parser.add_argument("service", nargs="?", help="AWS service name")
    service_arg.completer = service_completer  # type: ignore[attr-defined]

    action_arg = parser.add_argument("action", nargs="?", help="Service action name")
    action_arg.completer = action_completer  # type: ignore[attr-defined]

    argcomplete.autocomplete(parser)

    # First pass: parse known args to get service and action
    args, remaining = parser.parse_known_args()

    # If there are remaining args, check if any are flags that should be parsed
    # This handles cases where flags appear after service/action or after --
    if remaining:
        # Re-parse with the full argument list to catch all flags
        # We need to build a new argv that puts flags before positional args
        reordered_argv = [sys.argv[0]]  # Program name
        flags = []
        non_flags = []

        # Separate flags from non-flags in remaining args
        i = 0
        while i < len(remaining):
            arg = remaining[i]
            if arg in ["-d", "--debug", "-j", "--json", "-k", "--keys"]:
                flags.append(arg)
            elif arg in ["--region", "--profile"]:
                # These flags take a value
                flags.append(arg)
                if i + 1 < len(remaining):
                    flags.append(remaining[i + 1])
                    i += 1
            else:
                non_flags.append(arg)
            i += 1

        # Add original flags from sys.argv that were already parsed
        for arg in sys.argv[1:]:
            if arg in ["-d", "--debug", "-j", "--json", "-k", "--keys"]:
                if arg not in flags:
                    reordered_argv.append(arg)
            elif arg == "--region" and args.region:
                reordered_argv.extend(["--region", args.region])
            elif arg == "--profile" and args.profile:
                reordered_argv.extend(["--profile", args.profile])

        # Add newly found flags
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

    utils.debug_enabled = args.debug

    # Build the argv for filter parsing (service, action, and remaining arguments)
    filter_argv = []
    if args.service:
        filter_argv.append(args.service)
    if args.action:
        filter_argv.append(args.action)
    # Add the remaining arguments (filters, --, column names, etc.)
    filter_argv.extend(remaining)

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

    allowed_actions = load_security_policy()

    policy_action = action_to_policy_format(action)

    debug_print(
        f"DEBUG: Checking security for service='{service}', "
        f"action='{action}', policy_action='{policy_action}'"
    )
    debug_print(f"DEBUG: Policy has {len(allowed_actions)} allowed actions")

    if not validate_security(service, policy_action, allowed_actions):
        print(f"ERROR: Action {service}:{action} not permitted by security policy", file=sys.stderr)
        sys.exit(1)
    else:
        debug_print(f"DEBUG: Action {service}:{policy_action} IS ALLOWED by security policy")

    # Create session with region/profile if specified
    session = create_session(region=args.region, profile=args.profile)
    debug_print(f"DEBUG: Created session with region={args.region}, profile={args.profile}")

    # Determine final column filters (user-specified or defaults)
    final_column_filters = determine_column_filters(column_filters, service, action)

    if args.keys:
        print(f"Showing all available keys for {service}.{action}:", file=sys.stderr)

        try:
            # Use tracking to get keys from the last successful request
            call_result = execute_with_tracking(service, action, session=session)

            # If the initial call failed, try multi-level resolution
            if not call_result.final_success:
                debug_print("Keys mode: Initial call failed, trying multi-level resolution")
                _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                    parse_multi_level_filters_for_mode(filter_argv, mode="multi")
                )
                call_result, _ = execute_multi_level_call_with_tracking(
                    service,
                    action,
                    multi_resource_filters,
                    multi_value_filters,
                    multi_column_filters,
                )

            result = show_keys_from_result(call_result)
            print(result)
            return
        except Exception as e:
            print(f"Could not retrieve keys: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        debug_print(f"Using single-level execution first")
        response = execute_aws_call(service, action, session=session)

        if isinstance(response, dict) and "validation_error" in response:
            debug_print(f"ValidationError detected in single-level call, switching to multi-level")
            _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                parse_multi_level_filters_for_mode(filter_argv, mode="multi")
            )
            debug_print(
                f"Re-parsed filters for multi-level - "
                f"Resource: {multi_resource_filters}, Value: {multi_value_filters}, "
                f"Column: {multi_column_filters}"
            )
            # Apply defaults for multi-level if no user columns specified
            final_multi_column_filters = determine_column_filters(
                multi_column_filters, service, action
            )
            filtered_resources = execute_multi_level_call(
                service,
                action,
                multi_resource_filters,
                multi_value_filters,
                final_multi_column_filters,
                session,
            )
            debug_print(f"Multi-level call completed with {len(filtered_resources)} resources")
        else:
            resources = flatten_response(response)
            debug_print(f"Total resources extracted: {len(resources)}")

            filtered_resources = filter_resources(resources, value_filters)

        if final_column_filters:
            for filter_word in final_column_filters:
                debug_print(f"Applying column filter: {filter_word}")

        if args.keys:
            sorted_keys = extract_and_sort_keys(filtered_resources)
            output = "\n".join(f"  {key}" for key in sorted_keys)
            print(f"All available keys:", file=sys.stderr)
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
