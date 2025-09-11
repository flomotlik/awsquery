"""
Output formatting for AWS Query Tool.

This module handles formatting of API responses including table output,
JSON output, response flattening, and key extraction utilities.
"""

import json
from tabulate import tabulate
from .utils import debug_print, simplify_key


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
    # Import here to avoid circular dependency
    from .core import execute_aws_call
    
    response = execute_aws_call(service, action, dry_run)
    if dry_run:
        return "DRY RUN: Would show keys for this response."
    
    resources = flatten_response(response)
    if not resources:
        return "No data to extract keys from."
    
    sorted_keys = extract_and_sort_keys(resources)
    return "\n".join(f"  {key}" for key in sorted_keys)


def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility"""
    if not parameter_name:
        return parameter_name
    
    # Convert camelCase to PascalCase (first letter uppercase)
    # stackName -> StackName
    # instanceId -> InstanceId
    # bucketName -> BucketName
    
    return parameter_name[0].upper() + parameter_name[1:] if len(parameter_name) > 0 else parameter_name