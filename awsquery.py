#!/usr/bin/env python3

import argparse
import json
import sys
import fnmatch
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tabulate import tabulate
import argcomplete

# Global debug mode flag
debug_enabled = False

def debug_print(*args, **kwargs):
    """Print debug messages only when debug mode is enabled"""
    if debug_enabled:
        print(*args, file=sys.stderr, **kwargs)


def load_security_policy():
    """Load and parse AWS ReadOnly policy from policy.json"""
    try:
        with open('policy.json', 'r') as f:
            policy = json.load(f)
        
        debug_print(f"DEBUG: Loaded policy with keys: {list(policy.keys())}")
        
        allowed_actions = set()
        
        # Handle nested PolicyVersion structure
        if 'PolicyVersion' in policy:
            debug_print(f"DEBUG: Found PolicyVersion structure")
            policy_doc = policy['PolicyVersion'].get('Document', {})
            statements = policy_doc.get('Statement', [])
        else:
            # Handle direct Statement structure
            statements = policy.get('Statement', [])
        
        debug_print(f"DEBUG: Found {len(statements)} statements in policy")
        
        for i, statement in enumerate(statements):
            effect = statement.get('Effect')
            actions = statement.get('Action', [])
            debug_print(f"DEBUG: Statement {i}: Effect={effect}, Actions count={len(actions) if isinstance(actions, list) else 1}")
            
            if effect == 'Allow':
                if isinstance(actions, str):
                    actions = [actions]
                allowed_actions.update(actions)
                debug_print(f"DEBUG: Added {len(actions)} actions from statement {i}")
        
        debug_print(f"DEBUG: Total allowed actions loaded: {len(allowed_actions)}")
        if len(allowed_actions) < 10:  # Show first few if small set
            debug_print(f"DEBUG: Sample actions: {list(allowed_actions)[:5]}")
        
        return allowed_actions
    except FileNotFoundError:
        print("ERROR: policy.json not found. This file is required for security validation.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON in policy.json. This file is required for security validation.", file=sys.stderr)
        sys.exit(1)

def validate_security(service, action, allowed_actions):
    """Validate service:action against security policy"""
    service_action = f"{service}:{action}"
    
    if not allowed_actions:
        debug_print(f"DEBUG: No allowed_actions provided, allowing {service_action} by default")
        return True
    
    debug_print(f"DEBUG: Validating {service_action} against {len(allowed_actions)} policy rules")
    
    # Direct match
    if service_action in allowed_actions:
        debug_print(f"DEBUG: Direct match found for {service_action}")
        return True
    
    # Wildcard match
    for allowed in allowed_actions:
        if fnmatch.fnmatch(service_action, allowed):
            debug_print(f"DEBUG: Wildcard match: {service_action} matches {allowed}")
            return True
    
    debug_print(f"DEBUG: No match found for {service_action}")
    return False

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

def action_to_policy_format(action):
    """Convert CLI-style action name to PascalCase format used in security policy"""
    # Convert kebab-case to PascalCase: "create-capacity-provider" -> "CreateCapacityProvider"
    # Convert snake_case to PascalCase: "create_capacity_provider" -> "CreateCapacityProvider"
    
    # First normalize to words separated by spaces
    words = action.replace('-', ' ').replace('_', ' ').split()
    
    # Capitalize each word and join
    pascal_case = ''.join(word.capitalize() for word in words)
    
    return pascal_case

def execute_aws_call(service, action, dry_run=False, parameters=None):
    """Execute AWS API call with pagination support and optional parameters"""
    # Normalize the action name for boto3 compatibility
    normalized_action = normalize_action_name(action)
    
    if dry_run:
        params_str = f" with parameters {parameters}" if parameters else ""
        print(f"DRY RUN: Would execute {service}.{normalized_action}(){params_str}", file=sys.stderr)
        return []
    
    try:
        client = boto3.client(service)
        operation = getattr(client, normalized_action, None)
        
        if not operation:
            # Try the original action name as a fallback
            operation = getattr(client, action, None)
            if not operation:
                raise ValueError(f"Action {action} (normalized: {normalized_action}) not available for service {service}")
        
        # Prepare parameters
        call_params = parameters or {}
        
        # Try to get paginator first
        try:
            # Use normalized action for paginator too
            paginator = client.get_paginator(normalized_action)
            results = []
            for page in paginator.paginate(**call_params):
                results.append(page)
            return results
        except Exception as e:
            # Check the exception type
            exception_name = type(e).__name__
            debug_print(f"Pagination exception type: {exception_name}, message: {e}")
            
            # Handle specific exception types
            if exception_name == 'OperationNotPageableError':
                # This operation cannot be paginated - fall back to direct call
                debug_print(f"Operation not pageable, falling back to direct call")
                return [operation(**call_params)]
            elif exception_name == 'ParamValidationError':
                # This is a parameter validation error - let it bubble up to be handled by multi-level logic
                debug_print(f"ParamValidationError detected during pagination, re-raising")
                raise e
            elif isinstance(e, ClientError):
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ['ValidationException', 'ValidationError']:
                    # This is a validation error - let it bubble up to be handled by multi-level logic
                    debug_print(f"ValidationError ({error_code}) detected during pagination, re-raising")
                    raise e
                else:
                    # Other ClientError - fall back to direct call
                    debug_print(f"ClientError ({error_code}) during pagination, falling back to direct call")
                    return [operation(**call_params)]
            else:
                # Unknown exception type - fall back to direct call
                debug_print(f"Unknown pagination error, falling back to direct call")
                return [operation(**call_params)]
    
    except NoCredentialsError:
        print("ERROR: AWS credentials not found. Configure credentials first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Check for ParamValidationError specifically
        if type(e).__name__ == 'ParamValidationError':
            # This is a parameter validation error that we can handle
            error_info = parse_validation_error(e)
            if error_info:
                # Return a special result indicating we need parameter resolution
                return {'validation_error': error_info, 'original_error': e}
            else:
                print(f"ERROR: Could not parse parameter validation error: {e}", file=sys.stderr)
                sys.exit(1)
        # Fall through to other exception handlers
        
        # Check for ClientError
        if isinstance(e, ClientError):
            # Check if this is a validation error that we can handle
            error_info = parse_validation_error(e)
            if error_info:
                # Return a special result indicating we need parameter resolution
                return {'validation_error': error_info, 'original_error': e}
            else:
                print(f"ERROR: AWS API call failed: {e}", file=sys.stderr)
                sys.exit(1)
                
        # Unknown error type
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

def execute_multi_level_call(service, action, resource_filters, value_filters, column_filters, dry_run=False):
    """Handle multi-level API calls with automatic parameter resolution"""
    debug_print(f"Starting multi-level call for {service}.{action}")
    debug_print(f"Resource filters: {resource_filters}, Value filters: {value_filters}, Column filters: {column_filters}")
    
    # Try initial call without parameters
    response = execute_aws_call(service, action, dry_run)
    
    # Check if we got a validation error
    if isinstance(response, dict) and 'validation_error' in response:
        error_info = response['validation_error']
        parameter_name = error_info['parameter_name']
        
        debug_print(f"Validation error - missing parameter: {parameter_name}")
        
        # Infer list operation using both parameter name and action name
        possible_operations = infer_list_operation(service, parameter_name, action)
        
        # Try each possible list operation
        list_response = None
        successful_operation = None
        
        for operation in possible_operations:
            try:
                debug_print(f"Trying list operation: {operation}")
                list_response = execute_aws_call(service, operation, dry_run)
                
                # Check if this returned actual data (not an error)
                if isinstance(list_response, list) and list_response:
                    successful_operation = operation
                    debug_print(f"Successfully executed: {operation}")
                    break
                    
            except Exception as e:
                debug_print(f"Operation {operation} failed: {e}")
                continue
        
        if not list_response or not successful_operation:
            print(f"ERROR: Could not find a working list operation for parameter '{parameter_name}'", file=sys.stderr)
            print(f"ERROR: Tried operations: {possible_operations}", file=sys.stderr)
            sys.exit(1)
        
        # Flatten and filter the list response
        list_resources = flatten_response(list_response)
        debug_print(f"Got {len(list_resources)} resources from {successful_operation}")
        
        # Apply resource filters to the list results
        if resource_filters:
            filtered_list_resources = filter_resources(list_resources, resource_filters)
            debug_print(f"After resource filtering: {len(filtered_list_resources)} resources")
        else:
            filtered_list_resources = list_resources
        
        if not filtered_list_resources:
            print(f"ERROR: No resources found matching resource filters: {resource_filters}", file=sys.stderr)
            sys.exit(1)
        
        # Extract parameter values from filtered results
        parameter_values = extract_parameter_values(filtered_list_resources, parameter_name)
        
        if not parameter_values:
            print(f"ERROR: Could not extract parameter '{parameter_name}' from filtered results", file=sys.stderr)
            sys.exit(1)
        
        # Determine if we need single value or list
        expects_list = parameter_expects_list(parameter_name)
        
        if expects_list:
            param_value = parameter_values
        else:
            # Show all options when multiple values found
            if len(parameter_values) > 1:
                print(f"Multiple {parameter_name} values found matching filters:", file=sys.stderr)
                for value in parameter_values:
                    print(f"- {value}", file=sys.stderr)
                print(f"Using first match: {parameter_values[0]}", file=sys.stderr)
            elif len(parameter_values) == 1:
                # Even for single values, show what was found for transparency
                print(f"Found {parameter_name}: {parameter_values[0]}", file=sys.stderr)
            
            param_value = parameter_values[0]  # Use first match
        
        debug_print(f"Using parameter value(s): {param_value}")
        
        # Create a client to introspect the correct parameter name
        try:
            client = boto3.client(service)
            # Get the correct case-sensitive parameter name using service model introspection
            converted_parameter_name = get_correct_parameter_name(client, action, parameter_name)
            debug_print(f"Parameter name resolution: {parameter_name} -> {converted_parameter_name}")
        except Exception as e:
            debug_print(f"Could not create client for parameter introspection: {e}")
            # Fallback to PascalCase conversion
            converted_parameter_name = convert_parameter_name(parameter_name)
            debug_print(f"Fallback parameter name conversion: {parameter_name} -> {converted_parameter_name}")
        
        # Retry the original call with the parameter
        parameters = {converted_parameter_name: param_value}
        response = execute_aws_call(service, action, dry_run, parameters)
        
        # Check for another validation error
        if isinstance(response, dict) and 'validation_error' in response:
            print(f"ERROR: Still getting validation error after parameter resolution: {response['validation_error']}", file=sys.stderr)
            sys.exit(1)
    
    # We now have a successful response - process it normally
    resources = flatten_response(response)
    debug_print(f"Final call returned {len(resources)} resources")
    
    # Apply value filters
    if value_filters:
        filtered_resources = filter_resources(resources, value_filters)
        debug_print(f"After value filtering: {len(filtered_resources)} resources")
    else:
        filtered_resources = resources
    
    return filtered_resources

def flatten_response(data):
    """Flatten AWS response to extract resource lists"""
    if isinstance(data, list):
        # Handle paginated results
        debug_print(f"Paginated response with {len(data)} pages")
        all_items = []
        for i, page in enumerate(data):
            debug_print(f"Processing page {i+1}")
            items = flatten_single_response(page)
            all_items.extend(items)
        debug_print(f"Total resources extracted from all pages: {len(all_items)}")
        return all_items
    else:
        debug_print("Single response (not paginated)")
        result = flatten_single_response(data)
        debug_print(f"Total resources extracted: {len(result)}")
        return result


def flatten_single_response(response):
    """Simple extraction of data from AWS API responses"""
    if not response:
        debug_print("Empty response, returning empty list")
        return []
    
    # Direct list response
    if isinstance(response, list):
        debug_print(f"Direct list response with {len(response)} items")
        return response
    
    if not isinstance(response, dict):
        debug_print(f"Non-dict response ({type(response)}), wrapping in list")
        return [response]
    
    # Show original response structure for debugging
    original_keys = list(response.keys())
    debug_print(f"Original response keys: {original_keys}")
    
    # Remove ResponseMetadata before processing (AWS metadata, not actual data)
    # Only filter at the top level - ResponseMetadata should only appear at the root of boto3 responses
    filtered_response = {k: v for k, v in response.items() if k != 'ResponseMetadata'}
    filtered_keys = list(filtered_response.keys())
    
    if 'ResponseMetadata' in response:
        debug_print(f"Removed ResponseMetadata. Filtered keys: {filtered_keys}")
    else:
        debug_print(f"No ResponseMetadata found. Keys remain: {filtered_keys}")
    
    # Validate that we still have meaningful data after filtering
    if len(filtered_response) == 0:
        debug_print("Only ResponseMetadata present -> RETURNING EMPTY LIST")
        return []
    
    # Count how many keys have list values
    list_keys = []
    non_list_keys = []
    for key, value in filtered_response.items():
        if isinstance(value, list):
            list_keys.append((key, len(value)))
        else:
            non_list_keys.append(key)
    
    debug_print(f"Found {len(list_keys)} list keys and {len(non_list_keys)} non-list keys")
    if list_keys:
        debug_print(f"List keys: {[(k, l) for k, l in list_keys]}")
    if non_list_keys:
        debug_print(f"Non-list keys: {non_list_keys}")
    
    # Decision logic based on number of list keys
    if len(list_keys) == 1:
        # One list element on top level - ignore all other elements and extract the list cleanly
        list_key, list_length = list_keys[0]
        list_value = filtered_response[list_key]
        if non_list_keys:
            debug_print(f"Single list key '{list_key}' with {list_length} items, ignoring metadata {non_list_keys} -> EXTRACTING LIST ONLY")
        else:
            debug_print(f"Single list key '{list_key}' with {list_length} items -> EXTRACTING LIST")
        return list_value
    elif len(list_keys) > 1:
        # Multiple list keys - take the one with the most items
        list_keys.sort(key=lambda x: x[1], reverse=True)  # Sort by length, descending
        largest_key, largest_length = list_keys[0]
        largest_list = filtered_response[largest_key]
        debug_print(f"Multiple list keys found, using '{largest_key}' with {largest_length} items (largest) -> EXTRACTING LARGEST LIST")
        return largest_list
    else:
        # No list keys - use whole response as single element
        debug_print(f"No list keys found among {non_list_keys} -> USING WHOLE RESPONSE")
        return [filtered_response]


def flatten_dict_keys(d, parent_key='', sep='.'):
    """Flatten nested dictionary keys with dot notation"""
    # Handle non-dictionary inputs (e.g., strings, numbers, lists)
    if not isinstance(d, dict):
        # For non-dict items, create a simple key-value pair
        key = parent_key if parent_key else 'value'
        return {key: d}
    
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict_keys(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Handle lists by including indices
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    items.extend(flatten_dict_keys(item, f"{new_key}.{i}", sep=sep).items())
                else:
                    items.append((f"{new_key}.{i}", item))
        else:
            items.append((new_key, v))
    return dict(items)

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

def filter_resources(resources, value_filters):
    """Filter resources by value filters (ALL must match)"""
    if not value_filters:
        return resources
    
    # Debug output
    for filter_text in value_filters:
        debug_print(f"Applying value filter: {filter_text}")
    
    filtered = []
    for resource in resources:
        # First flatten the resource to get all keys and values
        flattened = flatten_dict_keys(resource)
        
        # Create searchable text from both keys and values
        searchable_items = []
        
        # Add all flattened keys (like "NetworkInterfaces.0.SubnetId")
        searchable_items.extend([key.lower() for key in flattened.keys()])
        
        # Add all values
        searchable_items.extend([str(value).lower() for value in flattened.values()])
        
        # Debug output for first few resources to show what we're searching
        if len(filtered) + len([r for r in resources if r != resource]) < 3:  # First few resources
            debug_print(f"Sample flattened keys: {list(flattened.keys())[:5]}")
            debug_print(f"Sample searchable items: {searchable_items[:10]}")
        
        # Check if ALL filters match in either keys or values
        matches_all = True
        for filter_text in value_filters:
            filter_lower = filter_text.lower()
            if not any(filter_lower in item for item in searchable_items):
                matches_all = False
                break
            else:
                # Show what matched for debugging
                matching_items = [item for item in searchable_items if filter_lower in item]
                debug_print(f"Filter '{filter_text}' matched: {matching_items[:3]}{'...' if len(matching_items) > 3 else ''}")
        
        if matches_all:
            filtered.append(resource)
    
    debug_print(f"Found {len(filtered)} resources matching filters (out of {len(resources)} total)")
    return filtered

def format_table_output(resources, column_filters=None):
    """Format resources as table using tabulate"""
    if not resources:
        return "No results found."
    
    # Flatten all resources
    flattened_resources = []
    all_keys = set()
    
    for resource in resources:
        flat = flatten_dict_keys(resource)
        flattened_resources.append(flat)
        all_keys.update(flat.keys())
    
    # Select columns
    if column_filters:
        # Debug output
        for filter_word in column_filters:
            debug_print(f"Applying column filter: {filter_word}")
        
        selected_keys = []
        for filter_word in column_filters:
            matching_keys = []
            for key in all_keys:
                # Check both full key and simplified key for matching
                simplified = simplify_key(key)
                if filter_word.lower() in key.lower() or filter_word.lower() in simplified.lower():
                    matching_keys.append(key)
            selected_keys.extend(matching_keys)
            if matching_keys:
                debug_print(f"Column filter '{filter_word}' matched: {', '.join(matching_keys[:5])}{'...' if len(matching_keys) > 5 else ''}")
            else:
                debug_print(f"Column filter '{filter_word}' matched no columns")
        selected_keys = list(dict.fromkeys(selected_keys))  # Remove duplicates, preserve order
        # No defaults - if no matches, that's intentional
    else:
        # No column filters provided - show all columns (no defaults for now)
        selected_keys = sorted(list(all_keys))
    
    if not selected_keys:
        return "No matching columns found."
    
    # Group selected keys by their simplified names to handle duplicates
    # Preserve order from column filters by tracking order of appearance
    simplified_to_full_keys = {}
    unique_headers_ordered = []  # Track order of first appearance
    
    for key in selected_keys:
        simplified = simplify_key(key)
        if simplified not in simplified_to_full_keys:
            simplified_to_full_keys[simplified] = []
            unique_headers_ordered.append(simplified)  # Add in order of first occurrence
        simplified_to_full_keys[simplified].append(key)
    
    # Use ordered headers instead of sorted ones
    unique_headers = unique_headers_ordered
    
    # Build table data with deduplication
    table_data = []
    for resource in flattened_resources:
        row = []
        for simplified_key in unique_headers:
            # Collect all values for this simplified key from all matching full keys
            values = set()
            for full_key in simplified_to_full_keys[simplified_key]:
                value = resource.get(full_key, '')
                if value:  # Only include non-empty values
                    # Truncate long values
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + '...'
                    values.add(str(value))
            
            # Create cell content - join unique values with comma
            if values:
                cell_value = ', '.join(sorted(values)) if len(values) > 1 else list(values)[0]
            else:
                cell_value = ''
            row.append(cell_value)
        
        # Only add row if it contains at least one non-empty cell
        if any(cell.strip() for cell in row):
            table_data.append(row)
    
    return tabulate(table_data, headers=unique_headers, tablefmt="grid")

def format_json_output(resources, column_filters=None):
    """Format resources as JSON output"""
    if not resources:
        return json.dumps({"results": []}, indent=2)
    
    # If column filters are specified, filter the keys
    if column_filters:
        # Debug output
        for filter_word in column_filters:
            debug_print(f"Applying column filter to JSON: {filter_word}")
        
        filtered_resources = []
        for resource in resources:
            flat = flatten_dict_keys(resource)
            
            # Group matching keys by simplified name for deduplication
            simplified_groups = {}
            for key, value in flat.items():
                # Check both full key and simplified key for matching
                simplified = simplify_key(key)
                if any(cf.lower() in key.lower() or cf.lower() in simplified.lower() for cf in column_filters):
                    if simplified not in simplified_groups:
                        simplified_groups[simplified] = set()
                    if value:  # Only include non-empty values
                        simplified_groups[simplified].add(str(value))
            
            # Create deduplicated output
            filtered = {}
            for simplified_key, values in simplified_groups.items():
                if values:  # Only include if we have values
                    # Join unique values with comma, or single value if only one
                    filtered[simplified_key] = ', '.join(sorted(values)) if len(values) > 1 else list(values)[0]
            
            if filtered:  # Only include resources that have matching columns
                filtered_resources.append(filtered)
        return json.dumps({"results": filtered_resources}, indent=2, default=str)
    else:
        return json.dumps({"results": resources}, indent=2, default=str)

def extract_and_sort_keys(resources):
    """Extract all keys from resources and sort them case-insensitively"""
    if not resources:
        return []
    
    all_keys = set()
    for resource in resources:
        flat = flatten_dict_keys(resource)
        all_keys.update(flat.keys())
    
    # Convert to simplified keys and remove duplicates
    simplified_keys = set()
    for key in all_keys:
        simplified = simplify_key(key)
        simplified_keys.add(simplified)
    
    # Sort case-insensitively
    sorted_keys = sorted(list(simplified_keys), key=str.lower)
    return sorted_keys

def show_keys(service, action, dry_run=False):
    """Show all available keys from API response"""
    response = execute_aws_call(service, action, dry_run)
    if dry_run:
        return "DRY RUN: Would show keys for this response."
    
    resources = flatten_response(response)
    if not resources:
        return "No data to extract keys from."
    
    sorted_keys = extract_and_sort_keys(resources)
    return "\n".join(f"  {key}" for key in sorted_keys)

def parse_multi_level_filters(argv):
    """Parse command line args with multiple -- separators for multi-level filtering"""
    # Find all -- positions
    separator_positions = []
    for i, arg in enumerate(argv):
        if arg == '--':
            separator_positions.append(i)
    
    if not separator_positions:
        # No separators, return empty lists for value and column filters
        return argv, [], [], []
    
    # Split into segments based on -- positions
    segments = []
    start = 0
    
    for pos in separator_positions:
        segments.append(argv[start:pos])
        start = pos + 1
    
    # Add the final segment after the last --
    segments.append(argv[start:])
    
    # Parse segments
    # Segment 0 contains: service, action, and resource filters
    # Segment 1 contains: value filters  
    # Segment 2 contains: column filters
    # Segment 3+ contains: additional filters (if any)
    
    first_segment = segments[0] if segments else []
    value_filters = segments[1] if len(segments) > 1 else []
    column_filters = segments[2] if len(segments) > 2 else []
    
    # Extract base command (service, action) and resource filters from first segment
    base_command = []
    resource_filters = []
    
    # Find service and action in first segment, everything else becomes resource filters
    service_found = False
    action_found = False
    
    for arg in first_segment:
        if arg.startswith('-'):
            base_command.append(arg)  # Flags go to base command
        elif not service_found:
            base_command.append(arg)  # First non-flag is service
            service_found = True
        elif not action_found:
            base_command.append(arg)  # Second non-flag is action
            action_found = True
        else:
            resource_filters.append(arg)  # Everything else is resource filters
    
    debug_print(f"Multi-level parsing - Base: {base_command}, Resource: {resource_filters}, Value: {value_filters}, Column: {column_filters}")
    
    return base_command, resource_filters, value_filters, column_filters

def parse_validation_error(error):
    """Extract missing parameter info from ValidationError"""
    import re
    
    error_message = str(error)
    
    # Look for patterns like "Value null at 'parameterName'"
    pattern = r"Value null at '([^']+)'"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'null_value'
        }
    
    # Look for patterns like "Member must not be null" with parameter context
    pattern = r"'([^']+)'[^:]*: Member must not be null"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'required_parameter'
        }
    
    # Look for patterns like "Either StackName or PhysicalResourceId must be specified"
    pattern = r"Either (\w+) or \w+ must be specified"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'either_parameter'
        }
    
    # Look for patterns like "Missing required parameter in input: 'clusterName'"
    pattern = r"Missing required parameter in input: ['\"]([^'\"]+)['\"]"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'missing_parameter'
        }
    
    # Add debug output to help identify unmatched patterns
    debug_print(f"Could not parse validation error: {error_message}")
    
    return None

def infer_list_operation(service, parameter_name, action):
    """Infer the list operation from parameter name first, then action name as fallback"""
    
    possible_operations = []
    
    # FIRST: Try parameter-based inference (unless parameter is too generic)
    if parameter_name.lower() not in ['name', 'id', 'arn']:
        # Remove common suffixes from parameter name
        resource_name = parameter_name
        suffixes_to_remove = ['Name', 'Id', 'Arn', 'ARN']
        for suffix in suffixes_to_remove:
            if resource_name.endswith(suffix):
                resource_name = resource_name[:-len(suffix)]
                break
        
        # Convert to lowercase and pluralize
        resource_name = resource_name.lower()
        
        if resource_name.endswith('y'):
            plural_name = resource_name[:-1] + 'ies'
        elif resource_name.endswith(('s', 'sh', 'ch', 'x', 'z')):
            plural_name = resource_name + 'es'
        else:
            plural_name = resource_name + 's'
        
        # Add parameter-based operations
        possible_operations.extend([
            f'list_{plural_name}',
            f'describe_{plural_name}',
            f'get_{plural_name}',
            f'list_{resource_name}',
            f'describe_{resource_name}',
            f'get_{resource_name}'
        ])
        
        debug_print(f"Parameter-based inference: '{parameter_name}' -> '{resource_name}' -> {len(possible_operations)} operations")
    else:
        debug_print(f"Parameter '{parameter_name}' is too generic, skipping parameter-based inference")
    
    # SECOND: Add action-based inference as fallback
    # Extract resource name from action
    prefixes = ['describe', 'get', 'update', 'delete', 'create', 'list']
    action_lower = action.lower().replace('-', '_')
    
    action_resource = action_lower
    for prefix in prefixes:
        if action_lower.startswith(prefix + '_'):
            action_resource = action_lower[len(prefix) + 1:]
            break
    
    # Pluralize action-derived resource (if not already plural)
    if action_resource.endswith('s') and len(action_resource) > 1:
        # Likely already plural (instances, clusters, etc.)
        action_plural = action_resource
    elif action_resource.endswith('y'):
        action_plural = action_resource[:-1] + 'ies'
    elif action_resource.endswith(('sh', 'ch', 'x', 'z')):
        action_plural = action_resource + 'es'
    else:
        action_plural = action_resource + 's'
    
    # Add action-based operations (avoiding duplicates)
    action_operations = [
        f'list_{action_plural}',
        f'describe_{action_plural}',
        f'get_{action_plural}',
        f'list_{action_resource}',
        f'describe_{action_resource}',
        f'get_{action_resource}'
    ]
    
    for op in action_operations:
        if op not in possible_operations:
            possible_operations.append(op)
    
    debug_print(f"Action-based inference: '{action}' -> '{action_resource}' -> added {len(action_operations)} operations")
    debug_print(f"Total possible operations: {possible_operations}")
    
    return possible_operations

def parameter_expects_list(parameter_name):
    """Determine if parameter expects list or single value"""
    # Check if parameter name suggests it expects multiple values
    list_indicators = ['s', 'Names', 'Ids', 'Arns', 'ARNs']
    
    for indicator in list_indicators:
        if parameter_name.endswith(indicator):
            return True
    
    return False

def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility"""
    if not parameter_name:
        return parameter_name
    
    # Convert camelCase to PascalCase (first letter uppercase)
    # stackName -> StackName
    # instanceId -> InstanceId
    # bucketName -> BucketName
    
    return parameter_name[0].upper() + parameter_name[1:] if len(parameter_name) > 0 else parameter_name

def get_correct_parameter_name(client, action, parameter_name):
    """Get the correct case-sensitive parameter name for an operation by introspecting the service model"""
    try:
        # Convert action name to PascalCase for service model lookup
        # list-nodegroups -> ListNodegroups  
        action_words = action.replace('-', '_').replace('_', ' ').split()
        pascal_case_action = ''.join(word.capitalize() for word in action_words)
        
        # Get the operation model from the service model
        operation_model = client.meta.service_model.operation_model(pascal_case_action)
        
        debug_print(f"Introspecting parameter name for {action} (PascalCase: {pascal_case_action})")
        
        # Get the input shape (parameters) for this operation
        if operation_model.input_shape:
            members = operation_model.input_shape.members
            debug_print(f"Available parameters: {list(members.keys())}")
            
            # Try exact match first
            if parameter_name in members:
                debug_print(f"Found exact match: {parameter_name}")
                return parameter_name
            
            # Try case-insensitive match
            for member_name in members:
                if member_name.lower() == parameter_name.lower():
                    debug_print(f"Found case-insensitive match: {parameter_name} -> {member_name}")
                    return member_name
            
            # Try PascalCase conversion as fallback
            pascal_case = parameter_name[0].upper() + parameter_name[1:]
            if pascal_case in members:
                debug_print(f"Found PascalCase match: {parameter_name} -> {pascal_case}")
                return pascal_case
            
            debug_print(f"No parameter match found for '{parameter_name}' in {list(members.keys())}")
        else:
            debug_print(f"Operation {normalized_action} has no input shape")
        
        # Default fallback to original parameter name
        debug_print(f"Using original parameter name: {parameter_name}")
        return parameter_name
        
    except Exception as e:
        debug_print(f"Could not introspect parameter name: {e}")
        # Fallback to PascalCase conversion
        fallback = convert_parameter_name(parameter_name)
        debug_print(f"Falling back to PascalCase: {parameter_name} -> {fallback}")
        return fallback


def extract_parameter_values(resources, parameter_name):
    """Extract parameter values from list operation results"""
    if not resources:
        return []
    
    values = []
    
    # Check if resources are simple strings (e.g., cluster names)
    if resources and isinstance(resources[0], str):
        debug_print(f"Resources are simple strings, using them directly for parameter '{parameter_name}'")
        return resources
    
    # Try both the original parameter name and the PascalCase version
    pascal_case_name = convert_parameter_name(parameter_name)
    search_names = [parameter_name, pascal_case_name]
    
    debug_print(f"Looking for parameter values using names: {search_names}")
    
    for resource in resources:
        flat = flatten_dict_keys(resource)
        
        # Look for exact matches first (try both names)
        found_value = None
        for search_name in search_names:
            if search_name in flat:
                value = flat[search_name]
                if value:
                    found_value = str(value)
                    break
        
        if found_value:
            values.append(found_value)
            continue
        
        # Look for case-insensitive matches
        for search_name in search_names:
            for key, value in flat.items():
                if key.lower() == search_name.lower() and value:
                    found_value = str(value)
                    break
            if found_value:
                break
        
        if found_value:
            values.append(found_value)
            continue
        
        # Look for partial matches (e.g., StackName in Stack.StackName)
        for search_name in search_names:
            matching_keys = [k for k in flat.keys() if search_name.lower() in k.lower()]
            if matching_keys:
                # Use the first matching key
                key = matching_keys[0]
                value = flat[key]
                if value:
                    values.append(str(value))
                    break
        
        if found_value:
            continue
            
        # NEW: Standard field fallback when parameter-specific field not found
        # Look for common standard fields based on parameter suffix or common resource names
        standard_fields = []
        param_lower = parameter_name.lower()
        
        if param_lower.endswith('name'):
            standard_fields.append('Name')
        elif param_lower.endswith('id'):
            standard_fields.append('Id')
        elif param_lower.endswith(('arn', 'ARN')):
            standard_fields.extend(['Arn', 'ARN'])
        elif param_lower.endswith('key'):
            standard_fields.append('Key')
        elif param_lower.endswith('value'):
            standard_fields.append('Value')
        else:
            # Handle single-word resource parameters that should map to Name field
            # Common AWS resource types that typically have a Name field
            resource_types_with_names = [
                'bucket', 'cluster', 'instance', 'volume', 'snapshot', 'image',
                'vpc', 'subnet', 'queue', 'topic', 'table', 'function', 'role',
                'user', 'group', 'policy', 'stack', 'template', 'pipeline',
                'repository', 'branch', 'commit', 'build', 'project', 'job',
                'task', 'service', 'container', 'node', 'nodegroup', 'database',
                'endpoint', 'domain', 'certificate', 'key', 'secret', 'parameter'
            ]
            
            if param_lower in resource_types_with_names:
                standard_fields.append('Name')
                debug_print(f"Parameter '{parameter_name}' is a resource type, will try Name field")
        
        if standard_fields:
            debug_print(f"No specific field found for '{parameter_name}', trying standard fields: {standard_fields}")
            for standard_field in standard_fields:
                # Try exact match first
                if standard_field in flat:
                    value = flat[standard_field]
                    if value:
                        debug_print(f"Found standard field '{standard_field}' for parameter '{parameter_name}'")
                        values.append(str(value))
                        found_value = str(value)
                        break
                
                # Try case-insensitive match for standard field
                for key, value in flat.items():
                    if key.lower() == standard_field.lower() and value:
                        debug_print(f"Found standard field '{key}' (case-insensitive) for parameter '{parameter_name}'")
                        values.append(str(value))
                        found_value = str(value)
                        break
                        
                if found_value:
                    break
    
    debug_print(f"Extracted {len(values)} values for parameter '{parameter_name}': {values[:3]}{'...' if len(values) > 3 else ''}")
    
    return values

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
        import re
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
    global debug_enabled
    debug_enabled = debug_mode
    
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