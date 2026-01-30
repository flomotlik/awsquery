"""Output formatting for AWS Query Tool."""

from __future__ import annotations

import json
import shutil
import sys
from collections import OrderedDict
from typing import Dict, List, Tuple

from tabulate import tabulate

from .utils import debug_print, simplify_key

MAX_AGGREGATED_VALUES = 3
MIN_COLUMN_WIDTH = 10
TABLE_PADDING_PER_COLUMN = 5  # tabulate grid: | + space + content + space + internal padding
DEFAULT_TERMINAL_WIDTH = 200


def _calculate_column_widths(table_data: List[List[str]], headers: List[str]) -> List[int]:
    """Calculate the current width of each column (max of header and all cell values)."""
    widths = [len(h) for h in headers]
    for row in table_data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    return widths


def _truncate_value(value: str, max_len: int) -> str:
    """Truncate a value to max_len, adding ellipsis if needed."""
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."


def _fit_table_to_width(
    table_data: List[List[str]], headers: List[str], max_width: int
) -> Tuple[List[List[str]], List[str], bool]:
    """Fit table to terminal width by truncating the widest columns.

    Returns:
        Tuple of (table_data, headers, was_truncated)
    """
    if not table_data or not headers:
        return table_data, headers, False

    col_widths = _calculate_column_widths(table_data, headers)
    overhead = TABLE_PADDING_PER_COLUMN * len(headers) + 1
    total_width = sum(col_widths) + overhead

    if total_width <= max_width:
        return table_data, headers, False

    available_width = max(max_width - overhead, len(headers) * MIN_COLUMN_WIDTH)

    while sum(col_widths) > available_width:
        max_idx = col_widths.index(max(col_widths))
        if col_widths[max_idx] <= MIN_COLUMN_WIDTH:
            break
        col_widths[max_idx] -= 1

    new_headers = [_truncate_value(h, col_widths[i]) for i, h in enumerate(headers)]
    new_table_data = []
    for row in table_data:
        new_row = [_truncate_value(str(cell), col_widths[i]) for i, cell in enumerate(row)]
        new_table_data.append(new_row)

    return new_table_data, new_headers, True


def make_unique_headers(normalized_keys):
    """Create unique column headers using minimal parent hierarchy.

    Args:
        normalized_keys: List of normalized keys (with indices removed)

    Returns:
        List of unique headers with minimal parent context

    Examples:
        ["Instances.Tags.Name", "Instances.State.Name"] -> ["Tags.Name", "State.Name"]
        ["Tags.Name", "State.Name", "InstanceId"] -> ["Tags.Name", "State.Name", "InstanceId"]
        ["Name", "InstanceId"] -> ["Name", "InstanceId"]
    """
    if not normalized_keys:
        return []

    # Build mapping of keys to their parts (reversed for easier suffix matching)
    key_parts: Dict[str, List[str]] = {}
    for key in normalized_keys:
        key_parts[key] = key.split(".")

    # For each key, find minimal suffix that's unique
    headers = []
    for key in normalized_keys:
        parts = key_parts[key]
        # Start with just the final segment
        for depth in range(1, len(parts) + 1):
            # Take the last 'depth' segments
            candidate = ".".join(parts[-depth:])
            # Check if this candidate is unique among all keys
            is_unique = True
            for other_key in normalized_keys:
                if other_key == key:
                    continue
                other_parts = key_parts[other_key]
                # Get the same depth suffix from the other key
                other_candidate = (
                    ".".join(other_parts[-depth:]) if depth <= len(other_parts) else other_key
                )
                if candidate == other_candidate:
                    is_unique = False
                    break
            if is_unique:
                headers.append(candidate)
                break
        else:
            # Fallback: use full key if no unique suffix found
            headers.append(key)

    return headers


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


def format_table_output(resources, column_filters=None, max_width=None):
    """Format resources as table using tabulate."""
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

    # Normalize keys by removing numeric indices
    normalized_keys = []
    normalized_to_full_keys: Dict[str, List[str]] = {}

    for key in selected_keys:
        normalized = simplify_key(key)
        if normalized not in normalized_to_full_keys:
            normalized_keys.append(normalized)
            normalized_to_full_keys[normalized] = []
        normalized_to_full_keys[normalized].append(key)

    # Create unique headers with parent context only when needed
    unique_headers = make_unique_headers(normalized_keys)

    # Build mapping from headers to normalized keys
    header_to_normalized = {header: norm for header, norm in zip(unique_headers, normalized_keys)}

    table_data = []
    for resource in flattened_resources:
        row = []
        for header in unique_headers:
            normalized_key = header_to_normalized[header]
            values = set()
            for full_key in normalized_to_full_keys[normalized_key]:
                value = resource.get(full_key, "")
                if value:
                    if isinstance(value, str) and len(value) > 80:
                        value = value[:77] + "..."
                    values.add(str(value))

            if values:
                sorted_values = sorted(values)
                if len(sorted_values) > MAX_AGGREGATED_VALUES:
                    shown = ", ".join(sorted_values[:MAX_AGGREGATED_VALUES])
                    extra = len(sorted_values) - MAX_AGGREGATED_VALUES
                    cell_value = f"{shown} (+{extra} more)"
                else:
                    cell_value = ", ".join(sorted_values)
            else:
                cell_value = ""
            row.append(cell_value)

        if any(cell.strip() for cell in row):
            table_data.append(row)

    if max_width is None:
        max_width = shutil.get_terminal_size((DEFAULT_TERMINAL_WIDTH, 24)).columns
    table_data, unique_headers, was_truncated = _fit_table_to_width(
        table_data, unique_headers, max_width
    )

    if was_truncated:
        print(
            f"Table truncated to fit terminal ({max_width} chars). Use -j for full JSON output.",
            file=sys.stderr,
        )

    return tabulate(table_data, headers=unique_headers, tablefmt="grid")


def _process_json_resource_with_filters(resource, column_filters):
    """Process a single resource with column filters for JSON output."""
    flat = flatten_dict_keys(resource)

    # Use filter_columns to apply pattern matching with ! operators
    filtered_flat = filter_columns(flat, column_filters)

    # Normalize keys by removing numeric indices
    normalized_to_full_keys: Dict[str, List[str]] = OrderedDict()
    normalized_keys = []

    # Process keys in the order they appear in filtered_flat
    for key in filtered_flat.keys():
        normalized = simplify_key(key)
        if normalized not in normalized_to_full_keys:
            normalized_keys.append(normalized)
            normalized_to_full_keys[normalized] = []
        normalized_to_full_keys[normalized].append(key)

    # Create unique headers with parent context only when needed
    unique_headers = make_unique_headers(normalized_keys)

    # Build mapping from headers to normalized keys
    header_to_normalized = {header: norm for header, norm in zip(unique_headers, normalized_keys)}

    # Build final filtered dict preserving order
    filtered: Dict[str, str] = OrderedDict()
    for header in unique_headers:
        normalized_key = header_to_normalized[header]
        values = []
        for full_key in normalized_to_full_keys[normalized_key]:
            value = filtered_flat.get(full_key)
            if value:
                values.append(str(value))

        if not values:
            continue

        # Deduplicate values while preserving order
        unique_values = []
        seen = set()
        for v in values:
            if v not in seen:
                unique_values.append(v)
                seen.add(v)
        if len(unique_values) > MAX_AGGREGATED_VALUES:
            shown = ", ".join(unique_values[:MAX_AGGREGATED_VALUES])
            extra = len(unique_values) - MAX_AGGREGATED_VALUES
            filtered[header] = f"{shown} (+{extra} more)"
        elif len(unique_values) > 1:
            filtered[header] = ", ".join(unique_values)
        else:
            filtered[header] = unique_values[0]

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
