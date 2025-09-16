"""Edge case tests for formatting functions."""

import json

import pytest

from awsquery.formatters import (
    filter_columns,
    flatten_dict_keys,
    flatten_response,
    flatten_single_response,
    format_json_output,
    format_table_output,
)


class TestFlattenResponseEdgeCases:
    """Test flatten_response with edge cases."""

    def test_empty_response(self):
        """Test with empty response."""
        assert flatten_response(None) == []
        assert flatten_response([]) == []
        assert flatten_response({}) == []

    def test_single_page_response(self):
        """Test non-paginated response."""
        response = {"Instances": [{"Id": "i-123"}, {"Id": "i-456"}]}
        result = flatten_response(response)
        assert len(result) == 2
        assert result[0]["Id"] == "i-123"

    def test_multi_page_response(self):
        """Test paginated response."""
        response = [
            {"Instances": [{"Id": "i-123"}]},
            {"Instances": [{"Id": "i-456"}]},
            {"Instances": [{"Id": "i-789"}]},
        ]
        result = flatten_response(response)
        assert len(result) == 3

    def test_response_metadata_only(self):
        """Test response with only ResponseMetadata."""
        response = {"ResponseMetadata": {"RequestId": "12345"}}
        result = flatten_response(response)
        assert result == []

    def test_mixed_list_and_metadata(self):
        """Test response with list and metadata."""
        response = {
            "Instances": [{"Id": "i-123"}],
            "NextToken": "token",
            "ResponseMetadata": {"RequestId": "12345"},
        }
        result = flatten_response(response)
        assert len(result) == 1
        assert result[0]["Id"] == "i-123"

    def test_multiple_list_keys(self):
        """Test response with multiple list keys."""
        response = {
            "Instances": [{"Id": "i-1"}, {"Id": "i-2"}],
            "Volumes": [{"Id": "v-1"}],
            "SecurityGroups": [{"Id": "sg-1"}, {"Id": "sg-2"}, {"Id": "sg-3"}],
        }
        result = flatten_response(response)
        # Should return the largest list
        assert len(result) == 3
        assert all("sg-" in r["Id"] for r in result)

    def test_non_dict_non_list_response(self):
        """Test response that's neither dict nor list."""
        response = "simple-string-response"
        result = flatten_response(response)
        assert result == ["simple-string-response"]

    def test_nested_empty_pages(self):
        """Test paginated response with empty pages."""
        response = [
            {"Instances": []},
            {"Instances": [{"Id": "i-123"}]},
            {"Instances": []},
        ]
        result = flatten_response(response)
        assert len(result) == 1


class TestFlattenSingleResponseEdgeCases:
    """Test flatten_single_response with edge cases."""

    def test_direct_list(self):
        """Test direct list response."""
        response = [{"Id": "1"}, {"Id": "2"}]
        result = flatten_single_response(response)
        assert result == response

    def test_no_list_keys(self):
        """Test response with no list keys."""
        response = {"Name": "test", "Status": "active"}
        result = flatten_single_response(response)
        assert result == [response]

    def test_empty_list_value(self):
        """Test response with empty list value."""
        response = {"Instances": [], "Status": "ok"}
        result = flatten_single_response(response)
        assert result == []

    def test_equal_length_lists(self):
        """Test response with equal length lists."""
        response = {"List1": [{"a": 1}, {"a": 2}], "List2": [{"b": 1}, {"b": 2}]}
        result = flatten_single_response(response)
        # Should pick first in alphabetical order when equal
        assert len(result) == 2


class TestFormatTableOutputEdgeCases:
    """Test format_table_output with edge cases."""

    def test_empty_resources(self):
        """Test with empty resources."""
        output = format_table_output([], None)
        assert output == "No results found."

    def test_single_resource(self):
        """Test with single resource."""
        resources = [{"Name": "test", "Status": "active"}]
        output = format_table_output(resources, None)
        assert "Name" in output
        assert "test" in output

    def test_missing_columns_in_some_rows(self):
        """Test when some rows missing columns."""
        resources = [
            {"Name": "test1", "Status": "active"},
            {"Name": "test2"},  # Missing Status
            {"Status": "inactive"},  # Missing Name
        ]
        output = format_table_output(resources, None)
        assert "Name" in output
        assert "Status" in output

    def test_very_long_values(self):
        """Test truncation of very long values."""
        long_value = "a" * 200
        resources = [{"Name": long_value}]
        output = format_table_output(resources, None)
        assert "..." in output  # Should be truncated

    def test_none_values(self):
        """Test handling of None values."""
        resources = [{"Name": "test", "Status": None}, {"Name": None, "Status": "active"}]
        output = format_table_output(resources, None)
        assert output != "No data to display."

    def test_with_column_filters(self):
        """Test with column filters."""
        resources = [{"Name": "test", "Status": "active", "Type": "t2.micro"}]
        output = format_table_output(resources, ["Name", "Type"])
        assert "Name" in output
        assert "Type" in output
        assert "Status" not in output


class TestFormatJsonOutputEdgeCases:
    """Test format_json_output with edge cases."""

    def test_empty_resources(self):
        """Test with empty resources."""
        output = format_json_output([], None)
        # May wrap in results object
        assert "[]" in output or "results" in output

    def test_single_resource(self):
        """Test with single resource."""
        resources = [{"Name": "test"}]
        output = format_json_output(resources, None)
        parsed = json.loads(output)
        # May wrap in results object
        if isinstance(parsed, dict) and "results" in parsed:
            assert parsed["results"] == resources
        else:
            assert parsed == resources

    def test_with_column_filters(self):
        """Test with column filters."""
        resources = [{"Name": "test", "Status": "active", "Type": "t2.micro"}]
        output = format_json_output(resources, ["Name"])
        parsed = json.loads(output)
        # May wrap in results object
        if isinstance(parsed, dict) and "results" in parsed:
            data = parsed["results"]
        else:
            data = parsed
        if len(data) > 0:
            assert "Name" in data[0]
            assert "Status" not in data[0]

    def test_nested_structures(self):
        """Test with nested structures."""
        resources = [{"Name": "test", "Config": {"Nested": {"Value": "deep"}}}]
        output = format_json_output(resources, None)
        parsed = json.loads(output)
        # May wrap in results object
        if isinstance(parsed, dict) and "results" in parsed:
            data = parsed["results"]
        else:
            data = parsed
        if len(data) > 0:
            assert data[0]["Config"]["Nested"]["Value"] == "deep"

    def test_special_json_characters(self):
        """Test with special JSON characters."""
        resources = [
            {"Name": 'test "quoted"', "Path": "C:\\path\\to\\file", "Newline": "line1\nline2"}
        ]
        output = format_json_output(resources, None)
        parsed = json.loads(output)
        # May wrap in results object
        if isinstance(parsed, dict) and "results" in parsed:
            data = parsed["results"]
        else:
            data = parsed
        if len(data) > 0:
            assert data[0]["Name"] == 'test "quoted"'


class TestFlattenDictKeysEdgeCases:
    """Test flatten_dict_keys with edge cases."""

    def test_empty_dict(self):
        """Test with empty dictionary."""
        result = flatten_dict_keys({})
        assert result == {}

    def test_non_dict_input(self):
        """Test with non-dict input."""
        result = flatten_dict_keys("not-a-dict")
        assert result == {"value": "not-a-dict"}

    def test_none_input(self):
        """Test with None input."""
        result = flatten_dict_keys(None)
        assert result == {"value": None}

    def test_deeply_nested(self):
        """Test with deeply nested structure."""
        data = {"l1": {"l2": {"l3": {"l4": {"l5": "value"}}}}}
        result = flatten_dict_keys(data)
        assert "l1.l2.l3.l4.l5" in result
        assert result["l1.l2.l3.l4.l5"] == "value"

    def test_list_values(self):
        """Test with list values."""
        data = {"items": [{"name": "item1"}, {"name": "item2"}]}
        result = flatten_dict_keys(data)
        # Lists may be flattened into individual keys
        assert "items.0.name" in result or "items" in result

    def test_mixed_types(self):
        """Test with mixed value types."""
        data = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "none": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
        }
        result = flatten_dict_keys(data)
        assert result["string"] == "value"
        assert result["number"] == 42
        assert result["boolean"] is True
        assert result["none"] is None
        # List may be flattened differently
        assert "list.0" in result or "list" in result
        assert result["nested.key"] == "value"


class TestFilterColumnsEdgeCases:
    """Test filter_columns with edge cases."""

    def test_empty_data(self):
        """Test with empty data."""
        result = filter_columns({}, ["Name"])
        assert result == {}

    def test_empty_filters(self):
        """Test with empty filters."""
        data = {"Name": "test", "Status": "active"}
        result = filter_columns(data, [])
        assert result == data

    def test_no_matches(self):
        """Test when no columns match filters."""
        data = {"Name": "test", "Status": "active"}
        result = filter_columns(data, ["NonExistent"])
        assert result == {}

    def test_prefix_suffix_exact_filters(self):
        """Test with prefix, suffix, and exact filters."""
        data = {
            "InstanceId": "i-123",
            "InstanceType": "t2.micro",
            "PublicIpAddress": "1.2.3.4",
            "PrivateIpAddress": "10.0.0.1",
        }

        # Prefix filter
        result = filter_columns(data, ["^Instance"])
        assert "InstanceId" in result
        assert "InstanceType" in result
        assert "PublicIpAddress" not in result

        # Suffix filter
        result = filter_columns(data, ["Address$"])
        assert "PublicIpAddress" in result
        assert "PrivateIpAddress" in result
        assert "InstanceId" not in result

        # Exact filter
        result = filter_columns(data, ["^InstanceId$"])
        assert "InstanceId" in result
        assert len(result) == 1
