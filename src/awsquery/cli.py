"""
Command-line interface for AWS Query Tool.

This module provides the main CLI interface, argument parsing, autocomplete
functionality, and orchestrates the execution of AWS queries.
"""

import argparse
import sys
import re
import boto3
import argcomplete

from .utils import debug_print, sanitize_input, get_aws_services
from .security import load_security_policy, validate_security, action_to_policy_format
from .core import execute_aws_call, execute_multi_level_call
from .filters import filter_resources, parse_multi_level_filters
from .formatters import (
    format_table_output, format_json_output, show_keys, 
    extract_and_sort_keys, flatten_response
)


def service_completer(prefix, parsed_args, **kwargs):
    """Autocomplete AWS service names"""
    session = boto3.Session()
    services = session.get_available_services()
    return [s for s in services if s.startswith(prefix)]


def action_completer(prefix, parsed_args, **kwargs):
    """Autocomplete action names based on selected service"""
    if not parsed_args.service:
        return []
    
    try:
        client = boto3.client(parsed_args.service)
        operations = client.meta.service_model.operation_names
        
        # Load security policy to filter allowed actions
        try:
            allowed_actions = load_security_policy()
        except:
            # If policy loading fails during autocomplete, be restrictive
            # Only allow common read operations
            allowed_actions = set()
            for op in operations:
                if any(op.startswith(prefix) for prefix in ['Describe', 'List', 'Get']):
                    allowed_actions.add(f"{parsed_args.service}:{op}")
        
        # Convert PascalCase to kebab-case for CLI-friendly names
        cli_operations = []
        for op in operations:
            # Check if this operation is allowed by security policy (using original operation name)
            if not validate_security(parsed_args.service, op, allowed_actions):
                continue  # Skip operations not allowed by policy
            
            # Convert PascalCase to kebab-case: DescribeInstances -> describe-instances
            kebab_case = re.sub('([a-z0-9])([A-Z])', r'\1-\2', op).lower()
            cli_operations.append(kebab_case)
        
        # Return unique operations that match the prefix and are allowed by security policy
        matched_ops = [op for op in cli_operations if op.startswith(prefix)]
        return sorted(list(set(matched_ops)))  # Remove duplicates and sort
    except:
        # If anything fails during autocomplete, return empty list
        return []


def main():
    # Handle main query command
    parser = argparse.ArgumentParser(
        description='Query AWS APIs with flexible filtering and automatic parameter resolution',
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
        """
    )
    
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be executed without running')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output results in JSON format instead of table')
    parser.add_argument('-k', '--keys', action='store_true',
                       help='Show all available keys for the command')
    parser.add_argument('-d', '--debug', action='store_true',
                       help='Enable debug output')
    
    # Add service and action arguments with completers
    service_arg = parser.add_argument('service', nargs='?', help='AWS service name')
    service_arg.completer = service_completer
    
    action_arg = parser.add_argument('action', nargs='?', help='Service action name')
    action_arg.completer = action_completer
    
    # Enable autocomplete
    argcomplete.autocomplete(parser)
    
    # Extract keys and debug flags from anywhere in the command line
    keys_mode = False
    debug_mode = False
    cleaned_argv = []
    for arg in sys.argv[1:]:
        if arg in ['--keys', '-k']:
            keys_mode = True
        elif arg in ['--debug', '-d']:
            debug_mode = True
        else:
            cleaned_argv.append(arg)
    
    # Set global debug mode
    from . import utils
    utils.debug_enabled = debug_mode
    
    # Parse multi-level filters from cleaned argv
    base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(cleaned_argv)
    
    # Create a modified argv for argument parsing (just the base command)
    modified_argv = ['awsquery'] + base_command
    
    # Parse with the base command only
    original_argv = sys.argv[:]
    sys.argv = modified_argv
    
    try:
        args = parser.parse_args(modified_argv[1:])
    except SystemExit:
        # Restore argv and re-raise
        sys.argv = original_argv
        raise
    
    # Restore original argv
    sys.argv = original_argv
    
    # Validate required arguments
    if not args.service or not args.action:
        services = get_aws_services()
        print("Available services:", ", ".join(services))
        sys.exit(0)
    
    # Sanitize inputs
    service = sanitize_input(args.service)
    action = sanitize_input(args.action)
    resource_filters = [sanitize_input(f) for f in resource_filters] if resource_filters else []
    value_filters = [sanitize_input(f) for f in value_filters] if value_filters else []
    column_filters = [sanitize_input(f) for f in column_filters] if column_filters else []
    
    # Load security policy
    allowed_actions = load_security_policy()
    
    # Security validation - convert action to the PascalCase format used in security policy
    policy_action = action_to_policy_format(action)
    
    # Debug output to trace what's happening
    debug_print(f"DEBUG: Checking security for service='{service}', action='{action}', policy_action='{policy_action}'")
    debug_print(f"DEBUG: Policy has {len(allowed_actions)} allowed actions")
    
    if not validate_security(service, policy_action, allowed_actions):
        print(f"ERROR: Action {service}:{action} not permitted by security policy", file=sys.stderr)
        sys.exit(1)
    else:
        debug_print(f"DEBUG: Action {service}:{policy_action} IS ALLOWED by security policy")
    
    # Determine if this is a multi-level call
    is_multi_level = bool(resource_filters) or len([f for f in [resource_filters, value_filters, column_filters] if f]) > 1
    
    # Handle keys mode 
    if keys_mode:
        print(f"Showing all available keys for {service}.{action}:", file=sys.stderr)
        
        try:
            if is_multi_level:
                # For keys mode with multi-level commands, execute the full multi-level logic
                filtered_resources = execute_multi_level_call(service, action, resource_filters, [], [], args.dry_run)
                if args.dry_run:
                    return
                sorted_keys = extract_and_sort_keys(filtered_resources)
                result = "\n".join(f"  {key}" for key in sorted_keys)
            else:
                # For simple commands
                result = show_keys(service, action, args.dry_run)
            
            print(result)
            return
        except Exception as e:
            print(f"Could not retrieve keys: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Execute command
    try:
        if is_multi_level:
            # Use multi-level execution
            debug_print(f"Using multi-level execution")
            filtered_resources = execute_multi_level_call(service, action, resource_filters, value_filters, column_filters, args.dry_run)
            
            if args.dry_run:
                return
            
            debug_print(f"Multi-level call completed with {len(filtered_resources)} resources")
        else:
            # Use traditional single-level execution
            debug_print(f"Using single-level execution")
            response = execute_aws_call(service, action, args.dry_run)
            
            if args.dry_run:
                return
            
            # Check if we got a validation error that requires multi-level resolution
            if isinstance(response, dict) and 'validation_error' in response:
                debug_print(f"ValidationError detected in single-level call, switching to multi-level")
                # Switch to multi-level execution with empty filters
                filtered_resources = execute_multi_level_call(service, action, [], value_filters, column_filters, args.dry_run)
                debug_print(f"Multi-level call completed with {len(filtered_resources)} resources")
            else:
                # Normal response processing
                resources = flatten_response(response)
                debug_print(f"Total resources extracted: {len(resources)}")
                
                # Apply value filters for single-level calls
                filtered_resources = filter_resources(resources, value_filters)
        
        # Debug output for column filters
        if column_filters:
            for filter_word in column_filters:
                debug_print(f"Applying column filter: {filter_word}")
        
        # Handle keys mode for final output
        if keys_mode:
            sorted_keys = extract_and_sort_keys(filtered_resources)
            output = "\n".join(f"  {key}" for key in sorted_keys)
            print(f"All available keys:", file=sys.stderr)
            print(output)
        else:
            # Format output based on json flag
            if args.json:
                output = format_json_output(filtered_resources, column_filters)
            else:
                output = format_table_output(filtered_resources, column_filters)
            print(output)
    
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()