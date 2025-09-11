"""
Filtering logic for AWS Query Tool.

This module handles filtering of AWS resources, multi-level filter parsing,
and parameter value extraction from API responses.
"""

import sys
from .utils import debug_print, simplify_key
from .formatters import flatten_dict_keys, convert_parameter_name


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
    
    # Handle single -- separator case for single-level commands
    # If there are no resource filters and only one -- separator,
    # treat the content after -- as column filters instead of value filters
    if len(segments) == 2 and not resource_filters and value_filters:
        column_filters = value_filters
        value_filters = []
    
    debug_print(f"Multi-level parsing - Base: {base_command}, Resource: {resource_filters}, Value: {value_filters}, Column: {column_filters}")
    
    return base_command, resource_filters, value_filters, column_filters


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