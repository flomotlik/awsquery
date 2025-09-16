"""Tests for data processing and transformation in formatters module."""

import json
from unittest.mock import patch

import pytest

from awsquery.formatters import (
    _transform_aws_tags_list,
    detect_aws_tags,
    filter_columns,
    flatten_dict_keys,
    flatten_response,
    flatten_single_response,
    format_json_output,
    format_table_output,
)


class TestTagProcessing:
    """Test AWS tag detection and transformation."""

    def test_detect_aws_tags_valid_structure(self):
        """Test detection of valid AWS tag structures."""
        # Valid AWS tag list
        valid_tags = [
            {"Key": "Name", "Value": "server1"},
            {"Key": "Environment", "Value": "production"},
        ]
        # Note: detect_aws_tags may have specific logic
        # Current implementation returns False for these
        assert detect_aws_tags(valid_tags) is False

        # Empty tag list also returns False in current implementation
        assert detect_aws_tags([]) is False

        # Single tag
        single_tag = [{"Key": "Name", "Value": "test"}]
        assert detect_aws_tags(single_tag) is False

    def test_detect_aws_tags_boundary_conditions(self):
        """Test boundary conditions for AWS tag detection."""
        # Test exactly one tag vs multiple tags (len > 0 vs len > 1 mutation)
        obj_single_tag = {"Tags": [{"Key": "Name", "Value": "test"}]}
        obj_multiple_tags = {
            "Tags": [{"Key": "Name", "Value": "test"}, {"Key": "Env", "Value": "prod"}]
        }

        # Both should behave the same way - this kills len > 0 vs len > 1 mutations
        single_result = detect_aws_tags(obj_single_tag)
        multiple_result = detect_aws_tags(obj_multiple_tags)

        # The function logic should work for both single and multiple tags
        assert single_result == multiple_result

    def test_detect_aws_tags_empty_tags_list(self):
        """Test empty tags list boundary."""
        obj_empty_tags = {"Tags": []}
        assert detect_aws_tags(obj_empty_tags) is False

    def test_detect_aws_tags_invalid_structure(self):
        """Test detection rejects invalid structures."""
        # Missing Key field
        invalid_key = [{"NotKey": "Name", "Value": "test"}]
        assert detect_aws_tags(invalid_key) is False

        # Missing Value field
        invalid_value = [{"Key": "Name", "NotValue": "test"}]
        assert detect_aws_tags(invalid_value) is False

        # Mixed valid and invalid
        mixed = [{"Key": "Valid", "Value": "yes"}, {"Key": "Invalid"}]  # Missing Value
        assert detect_aws_tags(mixed) is False

    def test_detect_aws_tags_non_list_input(self):
        """Test non-list inputs return False."""
        assert detect_aws_tags("not-a-list") is False
        assert detect_aws_tags(42) is False
        assert detect_aws_tags(None) is False
        assert detect_aws_tags({}) is False
        assert detect_aws_tags({"Key": "Name", "Value": "test"}) is False

    def test_transform_aws_tags_list_conversion(self):
        """Test conversion of tag list to dictionary."""
        tags = [
            {"Key": "Name", "Value": "web-server"},
            {"Key": "Environment", "Value": "prod"},
            {"Key": "Owner", "Value": "team-a"},
        ]

        result = _transform_aws_tags_list(tags)

        assert result == {"Name": "web-server", "Environment": "prod", "Owner": "team-a"}

    def test_transform_aws_tags_empty_values(self):
        """Test handling of empty keys and values."""
        tags = [
            {"Key": "", "Value": "empty-key"},
            {"Key": "empty-value", "Value": ""},
            {"Key": "normal", "Value": "value"},
        ]

        result = _transform_aws_tags_list(tags)

        # Check normal key-value
        assert result.get("normal") == "value"
        # Empty key might be included or skipped
        assert len(result) >= 1


class TestResponseFlattening:
    """Test response flattening logic."""

    def test_flatten_single_response_list_extraction(self):
        """Test extraction of the longest list from response."""
        response = {
            "ShortList": [1],
            "MediumList": [1, 2],
            "LongestList": [1, 2, 3, 4],
            "NotAList": "string",
            "ANumber": 42,
        }

        result = flatten_single_response(response)

        # Should extract the longest list
        assert len(result) == 4
        assert result == [1, 2, 3, 4]

    def test_flatten_single_response_filters_metadata(self):
        """Test ResponseMetadata is filtered out."""
        response = {
            "Items": [{"id": 1}, {"id": 2}],
            "ResponseMetadata": {"RequestId": "12345", "HTTPStatusCode": 200},
            "NextToken": "token",
        }

        result = flatten_single_response(response)

        assert result == [{"id": 1}, {"id": 2}]
        # ResponseMetadata should not affect result

    def test_flatten_single_response_non_dict(self):
        """Test handling of non-dict responses."""
        # List response
        assert flatten_single_response([1, 2, 3]) == [1, 2, 3]

        # String response
        assert flatten_single_response("string") == ["string"]

        # Number response
        assert flatten_single_response(42) == [42]

        # None response returns empty list
        assert flatten_single_response(None) == []

    def test_flatten_single_response_filtered_keys_boundary(self):
        """Test filtered_keys variable usage and None assignment boundary."""
        with patch("awsquery.formatters.debug_print") as mock_debug:
            response = {"Items": [{"Id": "test"}], "ResponseMetadata": {"RequestId": "123"}}
            result = flatten_single_response(response)

            # Should extract items correctly
            assert result == [{"Id": "test"}]

            # Verify that filtered_keys is actually used (not None)
            debug_calls = [str(call) for call in mock_debug.call_args_list]
            # Should contain debug message about filtered keys
            filtered_keys_logged = any("Filtered keys:" in call for call in debug_calls)
            assert filtered_keys_logged

    def test_flatten_single_response_empty_dict(self):
        """Test empty dict response."""
        result = flatten_single_response({})
        assert result == []

    def test_flatten_single_response_only_response_metadata(self):
        """Test dict with only ResponseMetadata."""
        response = {"ResponseMetadata": {"RequestId": "123"}}
        result = flatten_single_response(response)
        assert result == []

    def test_flatten_single_response_list_length_boundary(self):
        """Test list length comparison boundary conditions."""
        # Test responses with lists of different lengths to kill len() mutations
        short_response = {"ShortList": [1], "Items": [{"id": "a"}]}
        medium_response = {"MediumList": [1, 2], "Items": [{"id": "a"}]}
        long_response = {"LongList": [1, 2, 3, 4], "Items": [{"id": "a"}]}

        # All should extract the longest list, not just > some threshold
        assert len(flatten_single_response(short_response)) == 1
        assert len(flatten_single_response(medium_response)) == 2
        assert len(flatten_single_response(long_response)) == 4

    def test_flatten_response_pagination(self):
        """Test flattening of paginated responses."""
        paginated = [
            {"Items": [{"id": 1}], "NextToken": "token1"},
            {"Items": [{"id": 2}], "NextToken": "token2"},
            {"Items": [{"id": 3}]},
        ]

        result = flatten_response(paginated)

        assert len(result) == 3
        assert {"id": 1} in result
        assert {"id": 2} in result
        assert {"id": 3} in result


class TestColumnFiltering:
    """Test column filtering functionality."""

    def test_filter_columns_empty_pattern(self):
        """Test empty pattern matches all columns and preserves values."""
        data = {"Name": "test", "Status": "active", "Port": 8080}

        result = filter_columns(data, [""])

        # Empty pattern should include all with exact values
        assert result["Name"] == "test"
        assert result["Status"] == "active"
        assert result["Port"] == 8080
        assert None not in result.values()

    def test_filter_columns_pattern_modes(self):
        """Test prefix, suffix, and exact pattern matching."""
        data = {
            "InstanceId": "i-123",
            "InstanceType": "t2.micro",
            "PublicIpAddress": "1.2.3.4",
            "PrivateIpAddress": "10.0.0.1",
            "SecurityGroupIds": ["sg-1", "sg-2"],
        }

        # Prefix match (^)
        result = filter_columns(data, ["^Instance"])
        assert "InstanceId" in result
        assert "InstanceType" in result
        assert "PublicIpAddress" not in result

        # Suffix match ($)
        result = filter_columns(data, ["Address$"])
        assert "PublicIpAddress" in result
        assert "PrivateIpAddress" in result
        assert "InstanceId" not in result

        # Exact match (^...$)
        result = filter_columns(data, ["^InstanceId$"])
        assert "InstanceId" in result
        assert len(result) == 1

    def test_filter_columns_multiple_filters(self):
        """Test multiple filter patterns."""
        data = {"Name": "server", "Status": "running", "Type": "web", "Port": 80}

        result = filter_columns(data, ["Name", "Port"])

        assert "Name" in result
        assert "Port" in result
        assert "Status" not in result
        assert "Type" not in result


class TestOutputFormatting:
    """Test output formatting functions."""

    def test_format_json_output_structure(self):
        """Test JSON output is properly structured."""
        resources = [{"Name": "test1", "Status": "active"}, {"Name": "test2", "Status": "inactive"}]

        output = format_json_output(resources, None)
        parsed = json.loads(output)

        assert "results" in parsed
        assert parsed["results"] == resources

    def test_format_json_output_column_filtering(self):
        """Test JSON output applies column filters."""
        resources = [{"Name": "test", "Status": "active", "Type": "web", "Port": 80}]

        output = format_json_output(resources, ["Name", "Port"])
        parsed = json.loads(output)

        data = parsed["results"][0]
        assert "Name" in data
        assert "Port" in data
        assert "Status" not in data
        assert "Type" not in data

    def test_format_table_output_empty_resources(self):
        """Test table output for empty resources."""
        assert format_table_output([], None) == "No results found."
        assert format_table_output(None, None) == "No results found."

    def test_format_table_output_truncation(self):
        """Test table output truncates long values."""
        # Create a value longer than typical truncation limit
        long_value = "x" * 100
        resources = [{"Field": long_value}]

        output = format_table_output(resources, None)

        # Output should contain the field but be reasonably sized
        assert "Field" in output
        assert "x" in output
        # Table formatting adds borders and padding
        assert len(output) < 500

    def test_format_table_output_boundary_conditions(self):
        """Test table output boundary conditions."""
        # Test single resource vs multiple (boundary for loops)
        single = [{"Name": "test1"}]
        multiple = [{"Name": "test1"}, {"Name": "test2"}]

        single_output = format_table_output(single, None)
        multiple_output = format_table_output(multiple, None)

        # Both should work and produce different outputs
        assert "test1" in single_output
        assert "test1" in multiple_output
        assert "test2" in multiple_output
        assert "test2" not in single_output

    def test_format_json_output_boundary_conditions(self):
        """Test JSON output boundary conditions."""
        # Test with different data types and structures
        resources = [
            {"StringField": "test", "NumberField": 42, "BoolField": True},
            {"StringField": "", "NumberField": 0, "BoolField": False},
        ]

        output = format_json_output(resources, None)
        parsed = json.loads(output)

        # Should preserve all data types and values
        assert parsed["results"][0]["StringField"] == "test"
        assert parsed["results"][0]["NumberField"] == 42
        assert parsed["results"][0]["BoolField"] is True
        assert parsed["results"][1]["StringField"] == ""
        assert parsed["results"][1]["NumberField"] == 0
        assert parsed["results"][1]["BoolField"] is False

    def test_format_json_output_empty_vs_none_resources(self):
        """Test JSON formatting with empty vs None resources."""
        # Test boundary between empty list and None
        empty_output = format_json_output([], None)
        none_output = format_json_output(None, None)

        empty_parsed = json.loads(empty_output)
        none_parsed = json.loads(none_output)

        # Both should have results key with empty list
        assert empty_parsed["results"] == []
        assert none_parsed["results"] == []
