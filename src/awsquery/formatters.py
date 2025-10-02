"""Output formatting for AWS Query Tool."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Dict, List

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


def transform_tags_structure(data, max_depth=10, current_depth=0):
    """Transform AWS Tag lists to searchable maps recursively with depth limiting

    Converts Tags from [{"Key": "Name", "Value": "web-server"}] format
    to {"Name": "web-server"} format for easier searching and filtering.
    Preserves original data alongside transformed data for debugging.
    """
    # Depth limiting prevents infinite recursion
    if current_depth > max_depth:
        return data

    if isinstance(data, dict):
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
                result[key] = transform_tags_structure(value, max_depth, current_depth + 1)
        return result
    elif isinstance(data, list):
        return [transform_tags_structure(item, max_depth, current_depth + 1) for item in data]
    else:
        return data


def flatten_response(data, service: str, operation: str):
    """Flatten AWS response to extract resource lists

    Args:
        data: AWS API response data
        service: AWS service name for shape-aware extraction
        operation: Operation name for shape-aware extraction

    Returns:
        List of extracted resource items
    """
    # First, transform tags in the entire response
    transformed_data = transform_tags_structure(data)

    if isinstance(transformed_data, list):
        debug_print(f"Paginated response with {len(transformed_data)} pages")  # pragma: no mutate
        all_items = []
        for i, page in enumerate(transformed_data):
            debug_print(f"Processing page {i+1}")  # pragma: no mutate
            items = flatten_single_response(page, service, operation)
            all_items.extend(items)
        debug_print(
            f"Total resources extracted from all pages: {len(all_items)}"
        )  # pragma: no mutate
        return all_items
    else:
        debug_print("Single response (not paginated)")  # pragma: no mutate
        result = flatten_single_response(transformed_data, service, operation)
        debug_print(f"Total resources extracted: {len(result)}")  # pragma: no mutate
        return result


def flatten_single_response(response, service: str, operation: str):
    """Simple extraction of data from AWS API responses

    Args:
        response: AWS API response
        service: AWS service name for shape-aware extraction
        operation: Operation name for shape-aware extraction

    Returns:
        List of extracted resource items
    """
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

    # Shape-aware data field detection (REQUIRED)
    from .shapes import ShapeCache

    shape_cache = ShapeCache()
    data_field, _, _ = shape_cache.get_response_fields(service, operation)

    if data_field and data_field in response:
        data_value = response[data_field]
        if isinstance(data_value, list):
            debug_print(
                f"Shape-aware extraction: using data field '{data_field}' "
                f"with {len(data_value)} items"
            )  # pragma: no mutate
            return data_value
        else:
            debug_print(
                f"Shape-aware extraction: data field '{data_field}' is not a list, wrapping in list"
            )  # pragma: no mutate
            return [data_value]
    else:
        # Shape didn't identify data field - apply simple extraction
        debug_print(
            f"No data field identified for {service}:{operation}, using simple extraction"
        )  # pragma: no mutate
        # Remove ResponseMetadata
        filtered = {k: v for k, v in response.items() if k != "ResponseMetadata"}
        if not filtered:
            return []

        # Simple heuristic: extract list fields
        list_fields = [(k, v) for k, v in filtered.items() if isinstance(v, list)]
        if len(list_fields) == 1:
            field_name, field_value = list_fields[0]
            debug_print(
                f"Simple extraction: found single list field '{field_name}' "
                f"with {len(field_value)} items"
            )  # pragma: no mutate
            return field_value
        elif len(list_fields) > 1:
            # Multiple lists - choose the largest
            field_name, field_value = max(list_fields, key=lambda x: len(x[1]))
            debug_print(
                f"Simple extraction: found {len(list_fields)} list fields, "
                f"using largest '{field_name}' with {len(field_value)} items"
            )  # pragma: no mutate
            return field_value

        # No list fields - return filtered response as single item
        debug_print(
            f"Simple extraction: no list fields, returning response as item"
        )  # pragma: no mutate
        return [filtered]


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

    simplified_to_full_keys: Dict[str, List[str]] = {}
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
    flat = flatten_dict_keys(resource)

    # Use filter_columns to apply pattern matching with ! operators
    filtered_flat = filter_columns(flat, column_filters)

    # Preserve order by using ordered dictionary
    simplified_ordered: Dict[str, List[str]] = OrderedDict()

    # Process keys in the order they appear in filtered_flat
    for key, value in filtered_flat.items():
        simplified = simplify_key(key)
        if simplified not in simplified_ordered:
            simplified_ordered[simplified] = []
        if value:
            simplified_ordered[simplified].append(str(value))

    # Build final filtered dict preserving order
    filtered: Dict[str, str] = OrderedDict()
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
