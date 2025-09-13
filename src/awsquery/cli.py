"""Command-line interface for AWS Query Tool."""

import argparse
import re
import sys

import argcomplete
import boto3

from .core import execute_aws_call, execute_multi_level_call, execute_with_tracking, execute_multi_level_call_with_tracking, show_keys_from_result
from .filters import filter_resources, parse_multi_level_filters_for_mode
from .formatters import (
    extract_and_sort_keys,
    flatten_response,
    format_json_output,
    format_table_output,
    show_keys,
)
from .security import action_to_policy_format, load_security_policy, validate_security
from .utils import debug_print, get_aws_services, sanitize_input, create_session
from .config import apply_default_filters


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

    # Check for defaults
    default_columns = apply_default_filters(service, action)
    if default_columns:
        debug_print(f"Applying default column filters for {service}.{action}: {default_columns}")
        return default_columns

    debug_print(f"No column filters (user or default) for {service}.{action}")
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
  awsquery ec2 describe_instances prod web -- Name State InstanceId
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
        "--dry-run", action="store_true", help="Show what would be executed without running"
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

    keys_mode = False
    debug_mode = False
    cleaned_argv = []
    skip_next = False
    for i, arg in enumerate(sys.argv[1:]):
        if skip_next:
            skip_next = False
            continue
        if arg in ["--keys", "-k"]:
            keys_mode = True
        elif arg in ["--debug", "-d"]:
            debug_mode = True
        elif arg in ["--region", "--profile"]:
            # Skip this argument and the next one (its value)
            skip_next = True
        else:
            cleaned_argv.append(arg)

    from . import utils

    utils.debug_enabled = debug_mode

    base_command, resource_filters, value_filters, column_filters = (
        parse_multi_level_filters_for_mode(cleaned_argv, mode="single")
    )

    modified_argv = ["awsquery"] + base_command

    original_argv = sys.argv[:]
    sys.argv = modified_argv

    try:
        args = parser.parse_args(original_argv[1:])
    except SystemExit:
        sys.argv = original_argv
        raise

    sys.argv = original_argv

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

    is_multi_level = False

    if keys_mode:
        print(f"Showing all available keys for {service}.{action}:", file=sys.stderr)

        try:
            # Use tracking to get keys from the last successful request
            call_result = execute_with_tracking(service, action, args.dry_run, session=session)

            # If the initial call failed, try multi-level resolution
            if not call_result.final_success:
                debug_print("Keys mode: Initial call failed, trying multi-level resolution")
                _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                    parse_multi_level_filters_for_mode(cleaned_argv, mode="multi")
                )
                call_result, _ = execute_multi_level_call_with_tracking(
                    service,
                    action,
                    multi_resource_filters,
                    multi_value_filters,
                    multi_column_filters,
                    args.dry_run,
                )

            result = show_keys_from_result(call_result)
            print(result)
            return
        except Exception as e:
            print(f"Could not retrieve keys: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        debug_print(f"Using single-level execution first")
        response = execute_aws_call(service, action, args.dry_run, session=session)

        if args.dry_run:
            return

        if isinstance(response, dict) and "validation_error" in response:
            debug_print(f"ValidationError detected in single-level call, switching to multi-level")
            _, multi_resource_filters, multi_value_filters, multi_column_filters = (
                parse_multi_level_filters_for_mode(cleaned_argv, mode="multi")
            )
            debug_print(
                f"Re-parsed filters for multi-level - "
                f"Resource: {multi_resource_filters}, Value: {multi_value_filters}, "
                f"Column: {multi_column_filters}"
            )
            # Apply defaults for multi-level if no user columns specified
            final_multi_column_filters = determine_column_filters(multi_column_filters, service, action)
            filtered_resources = execute_multi_level_call(
                service,
                action,
                multi_resource_filters,
                multi_value_filters,
                final_multi_column_filters,
                args.dry_run,
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

        if keys_mode:
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
