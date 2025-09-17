"""Output formatting for AWS Query Tool."""

import json

from tabulate import tabulate

from .utils import debug_print, simplify_key


def filter_columns(flattened_data, column_filters):
    """Filter columns based on filter patterns with ! operators.

    Args:
        flattened_data: Dictionary with flattened keys
        column_filters: List of column filter patterns

    Returns:
        Dictionary with only the columns that match the filters, in filter order
    """
    # Import here to avoid circular dependency
    from .filters import matches_pattern, parse_filter_pattern

    if not column_filters:
        return flattened_data

    # Parse filter patterns
    parsed_filters = []
    for filter_text in column_filters:
        pattern, mode = parse_filter_pattern(filter_text)
        parsed_filters.append((pattern, mode))
        debug_print(f"Applying column filter: {filter_text} (mode: {mode})")  # pragma: no mutate

    # Preserve order by processing filters in sequence
    filtered_columns = {}
    matched_keys = set()

    # Process each filter in order
    for pattern, mode in parsed_filters:
        for key, value in flattened_data.items():
            # Skip keys already matched by previous filters
            if key in matched_keys:
                continue

            if not pattern or matches_pattern(key, pattern, mode):
                filtered_columns[key] = value
                matched_keys.add(key)
                if pattern:
                    debug_print(
                        f"Column '{key}' matched filter '{pattern}' (mode: {mode})"
                    )  # pragma: no mutate

    return filtered_columns


def detect_aws_tags(obj):
    """Detect if object contains AWS Tag structure"""
    if isinstance(obj, dict) and "Tags" in obj:
        tags = obj["Tags"]
        if isinstance(tags, list) and len(tags) > 0:
            # Check if first item has Key/Value structure
            if isinstance(tags[0], dict) and "Key" in tags[0] and "Value" in tags[0]:
                return True
    return False


def _transform_aws_tags_list(tags_list):
    """Transform AWS Tags list to map format."""
    tag_map = {}
    for tag in tags_list:
        if isinstance(tag, dict) and "Key" in tag and "Value" in tag:
            # Only add tags with non-empty keys
            tag_key = tag["Key"]
            if tag_key and tag_key.strip():
                tag_map[tag_key] = tag["Value"]
    return tag_map


def _is_aws_tags_structure(value):
    """Check if value looks like AWS Tags structure."""
    return (
        isinstance(value, list)
        and value
        and isinstance(value[0], dict)
        and "Key" in value[0]
        and "Value" in value[0]
    )


def transform_tags_structure(data, visited=None):
    """Transform AWS Tag lists to searchable maps recursively with circular reference protection

    Converts Tags from [{"Key": "Name", "Value": "web-server"}] format
    to {"Name": "web-server"} format for easier searching and filtering.
    Preserves original data alongside transformed data for debugging.
    """
    if visited is None:
        visited = set()

    # Circular reference protection
    if isinstance(data, (dict, list)) and id(data) in visited:
        return data  # Return original to avoid infinite recursion

    if isinstance(data, dict):
        visited.add(id(data))
        result = {}
        for key, value in data.items():
            if key == "Tags" and _is_aws_tags_structure(value):
                # Transform Tag list to map
                tag_map = _transform_aws_tags_list(value)
                result[key] = tag_map
                # Preserve original for debugging
                result[f"{key}_Original"] = value
                debug_print(
                    f"Transformed {len(tag_map)} AWS Tags to map format"
                )  # pragma: no mutate
            else:
                # Recursively transform nested structures
                result[key] = transform_tags_structure(value, visited)
        visited.remove(id(data))
        return result
    elif isinstance(data, list):
        visited.add(id(data))
        list_result = [transform_tags_structure(item, visited) for item in data]
        visited.remove(id(data))
        return list_result
    else:
        return data


def flatten_response(data):
    """Flatten AWS response to extract resource lists"""
    # First, transform tags in the entire response
    transformed_data = transform_tags_structure(data)

    if isinstance(transformed_data, list):
        debug_print(f"Paginated response with {len(transformed_data)} pages")  # pragma: no mutate
        all_items = []
        for i, page in enumerate(transformed_data):
            debug_print(f"Processing page {i+1}")  # pragma: no mutate
            items = flatten_single_response(page)
            all_items.extend(items)
        debug_print(
            f"Total resources extracted from all pages: {len(all_items)}"
        )  # pragma: no mutate
        return all_items
    else:
        debug_print("Single response (not paginated)")  # pragma: no mutate
        result = flatten_single_response(transformed_data)
        debug_print(f"Total resources extracted: {len(result)}")  # pragma: no mutate
        return result


def flatten_single_response(response):
    """Simple extraction of data from AWS API responses"""
    if not response:
        debug_print("Empty response, returning empty list")  # pragma: no mutate
        return []

    if isinstance(response, list):
        debug_print(f"Direct list response with {len(response)} items")  # pragma: no mutate
        return response

    if not isinstance(response, dict):
        debug_print(f"Non-dict response ({type(response)}), wrapping in list")  # pragma: no mutate
        return [response]

    original_keys = list(response.keys())
    debug_print(f"Original response keys: {original_keys}")  # pragma: no mutate

    filtered_response = {k: v for k, v in response.items() if k != "ResponseMetadata"}
    filtered_keys = list(filtered_response.keys())  # pragma: no mutate

    if "ResponseMetadata" in response:
        debug_print(
            f"Removed ResponseMetadata. Filtered keys: {filtered_keys}"
        )  # pragma: no mutate
    else:
        debug_print(f"No ResponseMetadata found. Keys remain: {filtered_keys}")  # pragma: no mutate

    if len(filtered_response) == 0:
        debug_print("Only ResponseMetadata present -> RETURNING EMPTY LIST")  # pragma: no mutate
        return []

    list_keys = []
    non_list_keys = []
    for key, value in filtered_response.items():
        if isinstance(value, list):
            list_keys.append((key, len(value)))
        else:
            non_list_keys.append(key)

    debug_print(
        f"Found {len(list_keys)} list keys and {len(non_list_keys)} non-list keys"
    )  # pragma: no mutate
    if list_keys:
        debug_print(f"List keys: {[(k, l) for k, l in list_keys]}")  # pragma: no mutate
    if non_list_keys:
        debug_print(f"Non-list keys: {non_list_keys}")  # pragma: no mutate

    if len(list_keys) == 1:
        list_key, list_length = list_keys[0]
        list_value = filtered_response[list_key]
        if non_list_keys:
            debug_print(
                f"Single list key '{list_key}' with {list_length} items, "
                f"ignoring metadata {non_list_keys} -> EXTRACTING LIST ONLY"
            )  # pragma: no mutate
        else:
            debug_print(
                f"Single list key '{list_key}' with {list_length} items -> EXTRACTING LIST"
            )  # pragma: no mutate
        return list_value
    elif len(list_keys) > 1:
        list_keys.sort(key=lambda x: x[1], reverse=True)
        largest_key, largest_length = list_keys[0]
        largest_list = filtered_response[largest_key]
        debug_print(
            f"Multiple list keys found, using '{largest_key}' with {largest_length} "
            f"items (largest) -> EXTRACTING LARGEST LIST"
        )  # pragma: no mutate
        return largest_list
    else:
        debug_print(
            f"No list keys found among {non_list_keys} -> USING WHOLE RESPONSE"
        )  # pragma: no mutate
        return [filtered_response]


def flatten_dict_keys(d, parent_key="", sep="."):
    """Flatten nested dictionary keys with dot notation"""
    if not isinstance(d, dict):
        key = parent_key if parent_key else "value"
        return {key: d}

    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict_keys(v, new_key, sep=sep).items())
        elif isinstance(v, list):
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

    # Apply tag transformation before processing
    transformed_resources = []
    for resource in resources:
        transformed = transform_tags_structure(resource)
        transformed_resources.append(transformed)

    flattened_resources = []
    all_keys_list = []  # Use list instead of set to preserve order

    for resource in transformed_resources:
        flat = flatten_dict_keys(resource)
        flattened_resources.append(flat)
        # Collect keys preserving order
        for key in flat.keys():
            if key not in all_keys_list:
                all_keys_list.append(key)

    if column_filters:
        # Use filter_columns to apply pattern matching with ! operators
        # Create a dummy dict with all keys to test which ones match
        all_keys_dict = {key: True for key in all_keys_list}
        filtered_dict = filter_columns(all_keys_dict, column_filters)
        selected_keys = list(filtered_dict.keys())

        if not selected_keys:
            debug_print(f"No columns matched filters: {column_filters}")  # pragma: no mutate
        else:
            debug_print(
                f"Selected {len(selected_keys)} columns from {len(all_keys_list)} available"
            )  # pragma: no mutate
    else:
        selected_keys = sorted(all_keys_list, key=str.lower)

    if not selected_keys:
        return "No matching columns found."

    simplified_to_full_keys: dict[str, list[str]] = {}
    unique_headers_ordered = []

    for key in selected_keys:
        simplified = simplify_key(key)
        if simplified not in simplified_to_full_keys:
            simplified_to_full_keys[simplified] = []
            unique_headers_ordered.append(simplified)
        simplified_to_full_keys[simplified].append(key)

    unique_headers = unique_headers_ordered

    table_data = []
    for resource in flattened_resources:
        row = []
        for simplified_key in unique_headers:
            values = set()
            for full_key in simplified_to_full_keys[simplified_key]:
                value = resource.get(full_key, "")
                if value:
                    if isinstance(value, str) and len(value) > 80:
                        value = value[:77] + "..."
                    values.add(str(value))

            if values:
                cell_value = ", ".join(sorted(values)) if len(values) > 1 else list(values)[0]
            else:
                cell_value = ""
            row.append(cell_value)

        if any(cell.strip() for cell in row):
            table_data.append(row)

    return tabulate(table_data, headers=unique_headers, tablefmt="grid")


def _process_json_resource_with_filters(resource, column_filters):
    """Process a single resource with column filters for JSON output."""
    from collections import OrderedDict

    flat = flatten_dict_keys(resource)

    # Use filter_columns to apply pattern matching with ! operators
    filtered_flat = filter_columns(flat, column_filters)

    # Preserve order by using ordered dictionary
    simplified_ordered: OrderedDict[str, list[str]] = OrderedDict()

    # Process keys in the order they appear in filtered_flat
    for key, value in filtered_flat.items():
        simplified = simplify_key(key)
        if simplified not in simplified_ordered:
            simplified_ordered[simplified] = []
        if value:
            simplified_ordered[simplified].append(str(value))

    # Build final filtered dict preserving order
    filtered: OrderedDict[str, str] = OrderedDict()
    for simplified_key, values in simplified_ordered.items():
        if not values:
            continue
        # Deduplicate values while preserving order
        unique_values = []
        seen = set()
        for v in values:
            if v not in seen:
                unique_values.append(v)
                seen.add(v)
        filtered[simplified_key] = (
            ", ".join(unique_values) if len(unique_values) > 1 else unique_values[0]
        )

    return dict(filtered) if filtered else None


def format_json_output(resources, column_filters=None):
    """Format resources as JSON output"""
    if not resources:
        return json.dumps({"results": []}, indent=2)

    # Apply tag transformation before processing
    transformed_resources = []
    for resource in resources:
        transformed = transform_tags_structure(resource)
        transformed_resources.append(transformed)

    if column_filters:
        debug_print(f"Applying column filters to JSON: {column_filters}")  # pragma: no mutate

        filtered_resources = []
        for resource in transformed_resources:
            filtered = _process_json_resource_with_filters(resource, column_filters)
            if filtered:
                filtered_resources.append(filtered)
        return json.dumps({"results": filtered_resources}, indent=2, default=str)
    else:
        return json.dumps({"results": transformed_resources}, indent=2, default=str)


def extract_and_sort_keys(resources, simplify=True):
    """Extract all keys from resources and sort them case-insensitively"""
    if not resources:
        return []

    # Apply tag transformation before processing
    transformed_resources = []
    for resource in resources:
        transformed = transform_tags_structure(resource)
        transformed_resources.append(transformed)

    all_keys = set()
    for resource in transformed_resources:
        flat = flatten_dict_keys(resource)
        all_keys.update(flat.keys())

    if simplify:
        # Simplify keys for column filtering and basic display
        simplified_keys = set()
        for key in all_keys:
            simplified = simplify_key(key)
            simplified_keys.add(simplified)
        sorted_keys = sorted(list(simplified_keys), key=str.lower)
    else:
        # Return full nested keys for detailed structure display
        sorted_keys = sorted(list(all_keys), key=str.lower)

    return sorted_keys


def show_keys(service, action):
    """Show all available keys from API response"""
    from .core import execute_aws_call

    response = execute_aws_call(service, action, session=None)
    resources = flatten_response(response)
    if not resources:
        return "No data to extract keys from."

    sorted_keys = extract_and_sort_keys(resources)
    return "\n".join(f"  {key}" for key in sorted_keys)


def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility"""
    if not parameter_name:
        return parameter_name

    return (
        parameter_name[0].upper() + parameter_name[1:]
        if len(parameter_name) > 0
        else parameter_name
    )
