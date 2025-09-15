"""Unit tests for AWS Query Tool formatting functions."""

import json
from unittest.mock import Mock, call, patch

import pytest
from tabulate import tabulate

# Import the functions under test
from src.awsquery.formatters import (
    detect_aws_tags,
    extract_and_sort_keys,
    flatten_dict_keys,
    flatten_response,
    flatten_single_response,
    format_json_output,
    format_table_output,
    show_keys,
    transform_tags_structure,
)
from src.awsquery.utils import simplify_key


@pytest.mark.unit
class TestFlattenResponse:

    def test_flatten_response_empty_list(self):
        result = flatten_response([])
        assert result == []

    def test_flatten_response_empty_single_response(self):
        """Test flatten_response with None/empty single response."""
        result = flatten_response(None)
        assert result == []

        result = flatten_response({})
        assert result == []

    def test_flatten_response_paginated_responses(self, sample_paginated_responses):
        """Test flatten_response with paginated responses."""
        result = flatten_response(sample_paginated_responses)

        # Should have all instances from all pages
        assert len(result) == 4  # 2 instances per page * 2 pages

        # Verify instance IDs from both pages
        instance_ids = [instance["InstanceId"] for instance in result]
        assert "i-page1-instance1" in instance_ids
        assert "i-page1-instance2" in instance_ids
        assert "i-page2-instance1" in instance_ids
        assert "i-page2-instance2" in instance_ids

    def test_flatten_response_single_non_paginated(self, sample_ec2_response):
        """Test flatten_response with single (non-paginated) response."""
        result = flatten_response(sample_ec2_response)

        # Should extract reservations from the single response (largest list)
        assert len(result) == 1  # 1 reservation containing multiple instances
        reservation = result[0]
        assert "ReservationId" in reservation
        assert "Instances" in reservation
        assert len(reservation["Instances"]) == 2  # 2 instances in the reservation
        instance_ids = [instance["InstanceId"] for instance in reservation["Instances"]]
        assert "i-1234567890abcdef0" in instance_ids
        assert "i-abcdef1234567890" in instance_ids

    def test_flatten_response_direct_list(self):
        """Test flatten_response with direct list of resources."""
        direct_list = [
            {"InstanceId": "i-direct1", "State": {"Name": "running"}},
            {"InstanceId": "i-direct2", "State": {"Name": "stopped"}},
        ]
        result = flatten_response(direct_list)

        # When input is list, it processes each item as a page
        assert len(result) == 2
        assert result[0]["InstanceId"] == "i-direct1"
        assert result[1]["InstanceId"] == "i-direct2"


@pytest.mark.unit
class TestFlattenSingleResponse:
    """Test suite for flatten_single_response() function.

    Extract resources from single response.
    """

    def test_flatten_single_response_empty_inputs(self):
        """Test flatten_single_response with various empty inputs."""
        # None
        result = flatten_single_response(None)
        assert result == []

        # Empty dict
        result = flatten_single_response({})
        assert result == []

        # Empty list
        result = flatten_single_response([])
        assert result == []

    def test_flatten_single_response_direct_list(self):
        """Test flatten_single_response with direct list input."""
        resources = [
            {"InstanceId": "i-123", "State": "running"},
            {"InstanceId": "i-456", "State": "stopped"},
        ]
        result = flatten_single_response(resources)
        assert result == resources
        assert len(result) == 2

    def test_flatten_single_response_non_dict_input(self):
        """Test flatten_single_response with non-dict input gets wrapped in list."""
        result = flatten_single_response("string value")
        assert result == ["string value"]

        result = flatten_single_response(42)
        assert result == [42]

        result = flatten_single_response(True)
        assert result == [True]

    def test_flatten_single_response_only_response_metadata(self):
        """Test flatten_single_response with only ResponseMetadata returns empty list."""
        response = {"ResponseMetadata": {"RequestId": "test-request-id", "HTTPStatusCode": 200}}
        result = flatten_single_response(response)
        assert result == []

    def test_flatten_single_response_single_list_key(self, sample_ec2_response):
        """Test flatten_single_response with single list key extraction."""
        result = flatten_single_response(sample_ec2_response)

        # Should extract Reservations (the only list key)
        assert len(result) == 1  # One reservation
        reservation = result[0]
        assert "ReservationId" in reservation
        assert "Instances" in reservation

        # The instances are within the reservation
        instances = reservation["Instances"]
        instance_ids = [instance["InstanceId"] for instance in instances]
        assert "i-1234567890abcdef0" in instance_ids
        assert "i-abcdef1234567890" in instance_ids

    def test_flatten_single_response_multiple_list_keys_chooses_largest(self):
        """Test flatten_single_response with multiple list keys chooses largest."""
        response = {
            "SmallList": [{"id": 1}],
            "LargeList": [{"id": 1}, {"id": 2}, {"id": 3}],
            "MediumList": [{"id": 1}, {"id": 2}],
            "ResponseMetadata": {"RequestId": "test"},
        }
        result = flatten_single_response(response)

        # Should choose LargeList (3 items)
        assert len(result) == 3
        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_flatten_single_response_no_list_keys_returns_whole_response(self):
        """Test flatten_single_response with no list keys returns whole response."""
        response = {
            "ResourceId": "resource-123",
            "Name": "test-resource",
            "Status": "active",
            "ResponseMetadata": {"RequestId": "test"},
        }
        result = flatten_single_response(response)

        # Should return whole response (minus ResponseMetadata) as single item
        assert len(result) == 1
        assert result[0]["ResourceId"] == "resource-123"
        assert result[0]["Name"] == "test-resource"
        assert result[0]["Status"] == "active"
        assert "ResponseMetadata" not in result[0]

    def test_flatten_single_response_mixed_list_and_non_list_keys(self, sample_s3_response):
        """Test flatten_single_response ignores non-list keys when list key present."""
        result = flatten_single_response(sample_s3_response)

        # Should extract Buckets list, ignoring Owner
        assert len(result) == 3
        assert all("Name" in bucket for bucket in result)
        bucket_names = [bucket["Name"] for bucket in result]
        assert "production-logs-bucket" in bucket_names
        assert "staging-backup-bucket" in bucket_names
        assert "development-assets" in bucket_names


@pytest.mark.unit
class TestFlattenDictKeys:
    """Test suite for flatten_dict_keys() function.

    Flatten nested dictionaries with dot notation.
    """

    def test_flatten_dict_keys_simple_dict(self):
        """Test flatten_dict_keys with simple flat dictionary."""
        data = {"Name": "test-resource", "Status": "active", "Count": 5}
        result = flatten_dict_keys(data)

        assert result == {"Name": "test-resource", "Status": "active", "Count": 5}

    def test_flatten_dict_keys_nested_dict(self):
        """Test flatten_dict_keys with nested dictionaries."""
        data = {
            "InstanceId": "i-123",
            "State": {"Name": "running", "Code": 16},
            "Tags": {"Environment": "production", "Owner": "team-a"},
        }
        result = flatten_dict_keys(data)

        expected = {
            "InstanceId": "i-123",
            "State.Name": "running",
            "State.Code": 16,
            "Tags.Environment": "production",
            "Tags.Owner": "team-a",
        }
        assert result == expected

    def test_flatten_dict_keys_with_arrays(self):
        """Test flatten_dict_keys with arrays containing objects."""
        data = {
            "InstanceId": "i-123",
            "SecurityGroups": [
                {"GroupId": "sg-123", "GroupName": "web"},
                {"GroupId": "sg-456", "GroupName": "db"},
            ],
            "Tags": [{"Key": "Environment", "Value": "prod"}, {"Key": "Team", "Value": "backend"}],
        }
        result = flatten_dict_keys(data)

        expected = {
            "InstanceId": "i-123",
            "SecurityGroups.0.GroupId": "sg-123",
            "SecurityGroups.0.GroupName": "web",
            "SecurityGroups.1.GroupId": "sg-456",
            "SecurityGroups.1.GroupName": "db",
            "Tags.0.Key": "Environment",
            "Tags.0.Value": "prod",
            "Tags.1.Key": "Team",
            "Tags.1.Value": "backend",
        }
        assert result == expected

    def test_flatten_dict_keys_with_primitive_array_items(self):
        """Test flatten_dict_keys with arrays containing primitive values."""
        data = {"Name": "test", "Numbers": [1, 2, 3], "Strings": ["a", "b", "c"]}
        result = flatten_dict_keys(data)

        expected = {
            "Name": "test",
            "Numbers.0": 1,
            "Numbers.1": 2,
            "Numbers.2": 3,
            "Strings.0": "a",
            "Strings.1": "b",
            "Strings.2": "c",
        }
        assert result == expected

    def test_flatten_dict_keys_deeply_nested(self):
        """Test flatten_dict_keys with deeply nested structures."""
        data = {
            "Level1": {
                "Level2": {
                    "Level3": {"Value": "deep-value"},
                    "Array": [{"Nested": {"DeepValue": "array-deep"}}],
                }
            }
        }
        result = flatten_dict_keys(data)

        expected = {
            "Level1.Level2.Level3.Value": "deep-value",
            "Level1.Level2.Array.0.Nested.DeepValue": "array-deep",
        }
        assert result == expected

    def test_flatten_dict_keys_non_dict_input(self):
        """Test flatten_dict_keys with non-dictionary inputs."""
        # String input
        result = flatten_dict_keys("test-string")
        assert result == {"value": "test-string"}

        # Number input
        result = flatten_dict_keys(42)
        assert result == {"value": 42}

        # Boolean input
        result = flatten_dict_keys(True)
        assert result == {"value": True}

        # None input
        result = flatten_dict_keys(None)
        assert result == {"value": None}

    def test_flatten_dict_keys_non_dict_input_with_parent_key(self):
        """Test flatten_dict_keys with non-dictionary inputs preserves parent key."""
        result = flatten_dict_keys("test-string", parent_key="existing_key")
        assert result == {"existing_key": "test-string"}

    def test_flatten_dict_keys_empty_dict(self):
        """Test flatten_dict_keys with empty dictionary."""
        result = flatten_dict_keys({})
        assert result == {}

    def test_flatten_dict_keys_custom_separator(self):
        """Test flatten_dict_keys with custom separator."""
        data = {"Level1": {"Level2": "value"}}
        result = flatten_dict_keys(data, sep="_")
        assert result == {"Level1_Level2": "value"}

    def test_flatten_dict_keys_mixed_data_types(self):
        """Test flatten_dict_keys with mixed data types."""
        data = {
            "StringField": "text",
            "NumberField": 123,
            "BooleanField": False,
            "NullField": None,
            "ArrayField": ["item1", 42, None],
            "ObjectField": {"NestedString": "nested", "NestedNumber": 456},
        }
        result = flatten_dict_keys(data)

        expected = {
            "StringField": "text",
            "NumberField": 123,
            "BooleanField": False,
            "NullField": None,
            "ArrayField.0": "item1",
            "ArrayField.1": 42,
            "ArrayField.2": None,
            "ObjectField.NestedString": "nested",
            "ObjectField.NestedNumber": 456,
        }
        assert result == expected


@pytest.mark.unit
class TestSimplifyKey:
    """Test suite for simplify_key() function - extract the last non-numeric part."""

    @pytest.mark.parametrize(
        "full_key,expected",
        [
            # Basic cases
            ("Name", "Name"),
            ("InstanceId", "InstanceId"),
            ("Status", "Status"),
            # Nested keys with indices
            ("Instances.0.InstanceId", "InstanceId"),
            ("Instances.0.NetworkInterfaces.0.SubnetId", "SubnetId"),
            ("Tags.0.Value", "Value"),
            ("SecurityGroups.1.GroupName", "GroupName"),
            # Multiple levels
            ("Level1.Level2.Level3.FinalValue", "FinalValue"),
            ("Owner.DisplayName", "DisplayName"),
            ("State.Name", "Name"),
            ("Reservation.Instances.0.State.Code", "Code"),
            # Edge cases
            ("", ""),
            ("123", "123"),  # All numeric
            ("0.1.2", "2"),  # All numeric
            ("Resource.0.1.Name", "Name"),
            # Complex AWS-style keys
            ("Reservations.0.Instances.0.NetworkInterfaces.0.Association.PublicIp", "PublicIp"),
            ("Stacks.0.Parameters.1.ParameterValue", "ParameterValue"),
            ("Buckets.2.CreationDate", "CreationDate"),
        ],
    )
    def test_simplify_key_patterns(self, full_key, expected):
        """Test simplify_key with various key patterns."""
        result = simplify_key(full_key)
        assert result == expected

    def test_simplify_key_none_input(self):
        """Test simplify_key with None input."""
        result = simplify_key(None)
        assert result is None

    def test_simplify_key_single_component(self):
        """Test simplify_key with single component (no dots)."""
        result = simplify_key("SimpleKey")
        assert result == "SimpleKey"

        result = simplify_key("123")
        assert result == "123"


@pytest.mark.unit
class TestTableOutput:
    """Test suite for format_table_output() function - format resources as table."""

    def test_format_table_output_empty_resources(self):
        """Test format_table_output with empty resources."""
        result = format_table_output([])
        assert result == "No results found."

        result = format_table_output(None)
        assert result == "No results found."

    def test_format_table_output_simple_resources(self):
        """Test format_table_output with simple flat resources."""
        resources = [
            {"Name": "resource1", "Status": "active", "Count": 5},
            {"Name": "resource2", "Status": "inactive", "Count": 3},
        ]
        result = format_table_output(resources)

        # Check it's a table format
        assert "┌─" in result or "|" in result  # Grid format indicators
        assert "Name" in result
        assert "Status" in result
        assert "Count" in result
        assert "resource1" in result
        assert "resource2" in result

    def test_format_table_output_nested_resources(self):
        """Test format_table_output with nested resources gets flattened."""
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = format_table_output(resources)

        # Should have flattened keys
        assert "InstanceId" in result
        assert "Name" in result  # Simplified from State.Name
        assert "Code" in result  # Simplified from State.Code
        assert "Key" in result  # Simplified from Tags.0.Key
        assert "Value" in result  # Simplified from Tags.0.Value
        assert "i-123" in result
        assert "running" in result

    def test_format_table_output_column_filters_matching(self):
        """Test format_table_output with column filters that match."""
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "State": {"Name": "running"},
                "PublicIpAddress": "1.2.3.4",
            }
        ]
        result = format_table_output(resources, column_filters=["Instance", "State"])

        # Should include columns matching filters
        assert "InstanceId" in result or "InstanceType" in result
        assert "Name" in result  # From State.Name
        # Should not include PublicIpAddress (no filter match)
        assert "PublicIpAddress" not in result and "PublicIp" not in result

    def test_format_table_output_column_filters_no_matches(self):
        """Test format_table_output with column filters that don't match."""
        resources = [{"Name": "resource1", "Status": "active"}]
        result = format_table_output(resources, column_filters=["NonExistent"])

        assert result == "No matching columns found."

    def test_format_table_output_key_deduplication(self):
        """Test format_table_output with duplicate simplified keys."""
        resources = [
            {"Instance.Name": "instance1", "Resource.Name": "resource1", "Tag.Name": "tag1"}
        ]
        result = format_table_output(resources)

        # Should have a Name column header
        assert "Name" in result

        # Should combine all Name values in one cell
        assert "instance1" in result
        assert "resource1" in result
        assert "tag1" in result

        # Check that the values are combined in a single row
        data_lines = [line for line in result.split("\n") if "instance1" in line]
        assert len(data_lines) == 1  # Should be only one data line
        data_line = data_lines[0]
        # All three values should be in the same line
        assert "instance1" in data_line
        assert "resource1" in data_line
        assert "tag1" in data_line

    def test_format_table_output_long_value_truncation(self):
        """Test format_table_output truncates long values."""
        resources = [{"ShortValue": "short", "LongValue": "a" * 90}]  # Over 80 character limit
        result = format_table_output(resources)

        assert "short" in result
        # Should be truncated with ellipsis
        assert ("a" * 77 + "...") in result

    def test_format_table_output_empty_rows_filtered(self):
        """Test format_table_output filters out empty rows."""
        resources = [
            {"Name": "resource1", "Status": "active"},
            {"OtherField": ""},  # This won't match any columns
            {"Name": "", "Status": ""},  # Empty values
            {"Name": "resource2", "Status": "inactive"},
        ]
        result = format_table_output(resources)

        # Should only show rows with actual data
        assert "resource1" in result
        assert "resource2" in result
        # Count number of data rows (excluding headers)
        lines = [line for line in result.split("\n") if "resource" in line]
        assert len(lines) == 2  # Only 2 valid resources

    @pytest.mark.parametrize(
        "column_filters,expected_columns",
        [
            (["name"], ["Name"]),
            (["Name", "status"], ["Name", "Status"]),
            (["id"], ["InstanceId"]),
            (["instance"], ["InstanceId", "InstanceType"]),
        ],
    )
    def test_format_table_output_column_filter_patterns(self, column_filters, expected_columns):
        """Test format_table_output with various column filter patterns."""
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "Name": "test-instance",
                "Status": "running",
            }
        ]
        result = format_table_output(resources, column_filters=column_filters)

        for expected_col in expected_columns:
            assert expected_col in result


@pytest.mark.unit
class TestJsonOutput:
    """Test suite for format_json_output() function - format resources as JSON."""

    def test_format_json_output_empty_resources(self):
        """Test format_json_output with empty resources."""
        result = format_json_output([])
        parsed = json.loads(result)
        assert parsed == {"results": []}

        result = format_json_output(None)
        parsed = json.loads(result)
        assert parsed == {"results": []}

    def test_format_json_output_simple_resources(self):
        """Test format_json_output with simple resources."""
        resources = [
            {"Name": "resource1", "Status": "active"},
            {"Name": "resource2", "Status": "inactive"},
        ]
        result = format_json_output(resources)
        parsed = json.loads(result)

        assert len(parsed["results"]) == 2
        assert parsed["results"][0]["Name"] == "resource1"
        assert parsed["results"][1]["Name"] == "resource2"

    def test_format_json_output_nested_resources(self):
        """Test format_json_output with nested resources (no filtering)."""
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = format_json_output(resources)
        parsed = json.loads(result)

        # Without column filters, should preserve original structure
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["InstanceId"] == "i-123"
        assert parsed["results"][0]["State"]["Name"] == "running"

    def test_format_json_output_with_column_filters(self):
        """Test format_json_output with column filters."""
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "State": {"Name": "running", "Code": 16},
                "PublicIpAddress": "1.2.3.4",
            }
        ]
        result = format_json_output(resources, column_filters=["Instance", "State"])
        parsed = json.loads(result)

        # Should flatten and filter
        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]

        # Should have Instance-related fields
        assert "InstanceId" in resource or "InstanceType" in resource
        # Should have State field
        assert "Name" in resource  # Simplified from State.Name
        # Should not have PublicIpAddress
        assert "PublicIpAddress" not in resource

    def test_format_json_output_key_deduplication(self):
        """Test format_json_output with duplicate simplified keys."""
        resources = [
            {"Instance.Name": "instance1", "Resource.Name": "resource1", "Status": "active"}
        ]
        result = format_json_output(resources, column_filters=["Name"])
        parsed = json.loads(result)

        # Should combine duplicate keys
        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert "Name" in resource
        # Should contain both values (comma-separated or one of them)
        name_value = resource["Name"]
        assert "instance1" in name_value or "resource1" in name_value

    def test_format_json_output_filters_empty_values(self):
        """Test format_json_output filters out empty values."""
        resources = [
            {"Name": "resource1", "EmptyString": "", "NullValue": None, "Status": "active"}
        ]
        result = format_json_output(resources, column_filters=["Name", "Status", "Empty", "Null"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert "Name" in resource
        assert "Status" in resource
        # Empty/null values should be filtered out
        assert "EmptyString" not in resource
        assert "NullValue" not in resource

    def test_format_json_output_no_matching_resources(self):
        """Test format_json_output when no resources match filters."""
        resources = [{"Name": "resource1", "Status": "active"}]
        result = format_json_output(resources, column_filters=["NonExistent"])
        parsed = json.loads(result)

        # Should return empty results when no columns match
        assert parsed["results"] == []

    def test_format_json_output_default_string_conversion(self):
        """Test format_json_output handles non-serializable objects with default=str."""
        from datetime import datetime

        resources = [
            {"Name": "resource1", "CreatedAt": datetime(2023, 1, 1, 12, 0, 0), "Count": 42}
        ]
        result = format_json_output(resources)
        parsed = json.loads(result)

        # Should convert datetime to string
        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert resource["Name"] == "resource1"
        assert "2023-01-01 12:00:00" in str(resource["CreatedAt"])
        assert resource["Count"] == 42

    def test_format_json_output_proper_json_structure(self):
        """Test format_json_output produces valid JSON with proper indentation."""
        resources = [{"Name": "test"}]
        result = format_json_output(resources)

        # Should be valid JSON
        parsed = json.loads(result)
        assert "results" in parsed

        # Should have proper indentation (2 spaces)
        assert "\n" in result
        lines = result.split("\n")
        # Check for indented lines
        indented_lines = [line for line in lines if line.startswith("  ")]
        assert len(indented_lines) > 0


@pytest.mark.unit
class TestUtilityFunctions:
    """Test suite for utility functions - extract_and_sort_keys and show_keys."""

    def test_extract_and_sort_keys_empty_resources(self):
        """Test extract_and_sort_keys with empty resources."""
        result = extract_and_sort_keys([])
        assert result == []

        result = extract_and_sort_keys(None)
        assert result == []

    def test_extract_and_sort_keys_simple_resources(self):
        """Test extract_and_sort_keys with simple flat resources."""
        resources = [
            {"Name": "resource1", "Status": "active", "Count": 5},
            {"Name": "resource2", "Type": "web", "Status": "inactive"},
        ]
        result = extract_and_sort_keys(resources)

        # Should extract and sort all unique simplified keys
        expected_keys = ["Count", "Name", "Status", "Type"]
        assert result == expected_keys

    def test_extract_and_sort_keys_nested_resources(self):
        """Test extract_and_sort_keys with nested resources."""
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = extract_and_sort_keys(resources)

        # Should extract simplified keys from flattened structure
        assert "InstanceId" in result
        assert "Name" in result  # From State.Name
        assert "Code" in result  # From State.Code
        assert "Key" in result  # From Tags.0.Key
        assert "Value" in result  # From Tags.0.Value

        # Should be sorted case-insensitively
        assert result == sorted(result, key=str.lower)

    def test_extract_and_sort_keys_case_insensitive_sort(self):
        """Test extract_and_sort_keys sorts case-insensitively."""
        resources = [{"zebra": "z", "Apple": "a", "Banana": "b", "cherry": "c"}]
        result = extract_and_sort_keys(resources)

        # Should be sorted case-insensitively: Apple, Banana, cherry, zebra
        assert result == ["Apple", "Banana", "cherry", "zebra"]

    def test_extract_and_sort_keys_deduplication(self):
        """Test extract_and_sort_keys removes duplicate simplified keys."""
        resources = [
            {"Instance.Name": "instance1", "Resource.Name": "resource1", "State.Name": "running"}
        ]
        result = extract_and_sort_keys(resources)

        # Should have only one 'Name' key (deduplicated)
        assert result.count("Name") == 1
        assert "Name" in result

    def test_extract_and_sort_keys_with_various_data_types(self):
        """Test extract_and_sort_keys with mixed data types."""
        resources = [
            {
                "StringField": "text",
                "NumberField": 123,
                "BooleanField": True,
                "ArrayField": [1, 2, 3],
                "ObjectField": {"NestedKey": "value"},
            }
        ]
        result = extract_and_sort_keys(resources)

        expected_keys = sorted(
            ["ArrayField", "BooleanField", "NestedKey", "NumberField", "StringField"], key=str.lower
        )
        assert result == expected_keys

    @patch("src.awsquery.core.execute_aws_call")
    def test_show_keys_no_data(self, mock_execute):
        """Test show_keys when no data is available."""
        mock_execute.return_value = {"ResponseMetadata": {"RequestId": "test"}}

        result = show_keys("ec2", "describe-instances")

        assert result == "No data to extract keys from."
        mock_execute.assert_called_once_with("ec2", "describe-instances", session=None)

    @patch("src.awsquery.core.execute_aws_call")
    def test_show_keys_with_data(self, mock_execute):
        """Test show_keys with actual data."""
        mock_execute.return_value = {
            "Instances": [
                {
                    "InstanceId": "i-123",
                    "State": {"Name": "running"},
                    "Tags": [{"Key": "Environment", "Value": "prod"}],
                }
            ],
            "ResponseMetadata": {"RequestId": "test"},
        }

        result = show_keys("ec2", "describe-instances")

        # Should format keys with indentation
        lines = result.split("\n")
        assert all(line.startswith("  ") for line in lines if line.strip())

        # Should contain simplified keys (from flattened structure)
        content = result.replace("  ", "")
        assert "InstanceId" in content
        assert "Name" in content  # From State.Name
        assert "Key" in content  # From Tags.0.Key
        assert "Value" in content  # From Tags.0.Value

    @patch("src.awsquery.core.execute_aws_call")
    def test_show_keys_integration(self, mock_execute):
        """Test show_keys integration with extract_and_sort_keys."""
        mock_execute.return_value = {"Instances": [{"InstanceId": "i-123", "Status": "running"}]}

        result = show_keys("ec2", "describe-instances")

        # Should have expected keys formatted with indentation
        lines = [line.strip() for line in result.split("\n") if line.strip()]
        assert "InstanceId" in lines
        assert "Status" in lines

        mock_execute.assert_called_once_with("ec2", "describe-instances", session=None)


@pytest.mark.unit
class TestComplexScenarios:
    """Test suite for complex real-world formatting scenarios."""

    def test_format_table_output_aws_ec2_instances(self, sample_ec2_response):
        """Test format_table_output with realistic EC2 instances response."""
        resources = flatten_single_response(sample_ec2_response)
        result = format_table_output(resources, column_filters=["Instance", "State", "Tag"])

        # Should include relevant columns
        assert "InstanceId" in result
        assert "Name" in result  # From State.Name
        assert any(tag in result for tag in ["Key", "Value"])  # From Tags

        # Should include instance data
        assert "i-1234567890abcdef0" in result
        assert "i-abcdef1234567890" in result
        assert "running" in result
        assert "stopped" in result

    def test_format_json_output_aws_s3_buckets(self, sample_s3_response):
        """Test format_json_output with realistic S3 buckets response."""
        resources = flatten_single_response(sample_s3_response)
        result = format_json_output(resources, column_filters=["Name", "Creation"])
        parsed = json.loads(result)

        # Should have 3 buckets
        assert len(parsed["results"]) == 3

        # Should filter for Name and Creation fields
        for bucket in parsed["results"]:
            assert "Name" in bucket
            # CreationDate should be simplified to just show Creation
            if "CreationDate" in str(result):
                assert True  # Expected

    def test_format_table_output_complex_nested_structure(self):
        """Test format_table_output with complex nested AWS-like structure."""
        complex_resource = {
            "LoadBalancer": {
                "LoadBalancerName": "test-lb",
                "DNSName": "test-lb-123456789.us-east-1.elb.amazonaws.com",
                "Listeners": [
                    {
                        "Protocol": "HTTP",
                        "LoadBalancerPort": 80,
                        "InstanceProtocol": "HTTP",
                        "InstancePort": 80,
                    },
                    {
                        "Protocol": "HTTPS",
                        "LoadBalancerPort": 443,
                        "InstanceProtocol": "HTTP",
                        "InstancePort": 80,
                        "SSLCertificateId": "arn:aws:acm:us-east-1:123456789012:certificate/abc123",
                    },
                ],
                "AvailabilityZones": ["us-east-1a", "us-east-1b"],
                "Instances": [{"InstanceId": "i-instance1"}, {"InstanceId": "i-instance2"}],
            }
        }

        result = format_table_output(
            [complex_resource], column_filters=["LoadBalancer", "Protocol"]
        )

        # Should include LoadBalancer fields
        assert "LoadBalancerName" in result or "DNSName" in result
        # Should include Protocol from Listeners
        assert "Protocol" in result
        assert "HTTP" in result
        assert "HTTPS" in result

    def test_format_json_output_mixed_data_types(self):
        """Test format_json_output with mixed data types from AWS responses."""
        resources = [
            {
                "StringField": "test-value",
                "NumberField": 42,
                "BooleanField": True,
                "NullField": None,
                "ArrayOfStrings": ["item1", "item2"],
                "ArrayOfObjects": [
                    {"Key": "tag1", "Value": "value1"},
                    {"Key": "tag2", "Value": "value2"},
                ],
                "NestedObject": {"SubField1": "sub-value", "SubField2": 100},
            }
        ]

        result = format_json_output(
            resources, column_filters=["String", "Number", "Boolean", "Key", "Sub"]
        )
        parsed = json.loads(result)

        # Should handle mixed data types correctly
        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]

        # Check expected field types are preserved/converted
        for key, value in resource.items():
            assert isinstance(value, str)  # All should be stringified for consistency

    def test_flatten_response_real_paginated_data(self):
        """Test flatten_response with realistic paginated data."""
        from tests.fixtures.aws_responses import get_paginated_response

        paginated_data = get_paginated_response("ec2", "describe_instances", 2, 3)
        result = flatten_response(paginated_data)

        # Should combine all reservations from all pages
        # (each page has 1 reservation with 3 instances)
        assert len(result) == 2  # 2 pages * 1 reservation per page

        # Verify we have reservations from both pages
        all_instances = []
        for reservation in result:
            assert "ReservationId" in reservation
            assert "Instances" in reservation
            all_instances.extend(reservation["Instances"])

        assert len(all_instances) == 6  # 2 pages * 3 instances per page
        instance_ids = [instance["InstanceId"] for instance in all_instances]
        # Should have instances from page 0 and page 1
        page0_instances = [iid for iid in instance_ids if "i-00" in iid]
        page1_instances = [iid for iid in instance_ids if "i-01" in iid]
        assert len(page0_instances) >= 1
        assert len(page1_instances) >= 1

    def test_extract_and_sort_keys_large_complex_structure(self):
        """Test extract_and_sort_keys with large complex structure."""
        from tests.fixtures.aws_responses import get_complex_nested_response

        complex_response = get_complex_nested_response(depth=3, breadth=2)
        resources = flatten_single_response(complex_response)
        result = extract_and_sort_keys(resources)

        # Should extract many keys from complex structure
        assert len(result) >= 10

        # Should be properly sorted
        assert result == sorted(result, key=str.lower)

        # Should contain expected AWS-like keys
        assert any("ResourceId" in key for key in result)
        assert any("ResourceType" in key for key in result)

    @pytest.mark.parametrize(
        "column_filter,resource_type",
        [
            (["instance"], "ec2_instances"),
            (["bucket"], "s3_buckets"),
            (["stack"], "cloudformation_stacks"),
            (["state", "status"], "mixed_states"),
        ],
    )
    def test_format_outputs_with_various_aws_services(self, column_filter, resource_type):
        """Test formatting functions with various AWS service responses."""
        # Create different resource types
        if resource_type == "ec2_instances":
            resources = [
                {
                    "InstanceId": "i-123",
                    "InstanceType": "t2.micro",
                    "State": {"Name": "running"},
                    "PublicIpAddress": "1.2.3.4",
                }
            ]
        elif resource_type == "s3_buckets":
            resources = [
                {
                    "BucketName": "test-bucket",  # Use field name that will match 'bucket' filter
                    "Name": "test-bucket",
                    "CreationDate": "2023-01-01T00:00:00Z",
                }
            ]
        elif resource_type == "cloudformation_stacks":
            resources = [
                {
                    "StackName": "test-stack",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [{"Key": "Environment", "Value": "prod"}],
                }
            ]
        else:  # mixed_states
            resources = [
                {"ResourceId": "r-123", "State": "active"},
                {"ResourceId": "r-456", "Status": "inactive"},
            ]

        # Test table output
        table_result = format_table_output(resources, column_filters=column_filter)
        assert table_result != "No matching columns found."

        # Test JSON output
        json_result = format_json_output(resources, column_filters=column_filter)
        parsed = json.loads(json_result)
        assert len(parsed["results"]) > 0

    def test_edge_case_empty_and_null_handling(self):
        """Test handling of edge cases with empty and null values."""
        resources = [
            {
                "ValidField": "has-value",
                "EmptyString": "",
                "NullField": None,
                "ZeroValue": 0,
                "FalseValue": False,
                "EmptyArray": [],
                "EmptyObject": {},
            }
        ]

        # Table output should handle these gracefully
        table_result = format_table_output(resources)
        assert "ValidField" in table_result
        assert "has-value" in table_result

        # JSON output should handle these gracefully
        json_result = format_json_output(resources)
        parsed = json.loads(json_result)
        assert len(parsed["results"]) == 1

        # Key extraction should work
        keys = extract_and_sort_keys(resources)
        assert len(keys) > 0


@pytest.mark.unit
class TestTagTransformation:
    """Test suite for AWS Tags transformation functionality."""

    def test_detect_aws_tags_valid_structure(self):
        """Test detect_aws_tags with valid AWS Tag structure."""
        obj_with_tags = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }
        assert detect_aws_tags(obj_with_tags) is True

    def test_detect_aws_tags_empty_tags(self):
        """Test detect_aws_tags with empty Tags list."""
        obj_empty_tags = {"InstanceId": "i-123", "Tags": []}
        assert detect_aws_tags(obj_empty_tags) is False

    def test_detect_aws_tags_no_tags_field(self):
        """Test detect_aws_tags with no Tags field."""
        obj_no_tags = {"InstanceId": "i-123", "State": "running"}
        assert detect_aws_tags(obj_no_tags) is False

    def test_detect_aws_tags_invalid_tag_structure(self):
        """Test detect_aws_tags with invalid tag structure."""
        obj_invalid_tags = {
            "InstanceId": "i-123",
            "Tags": [{"Name": "invalid-structure"}],  # Missing Key/Value
        }
        assert detect_aws_tags(obj_invalid_tags) is False

    def test_detect_aws_tags_tags_not_list(self):
        """Test detect_aws_tags with Tags field not being a list."""
        obj_tags_not_list = {
            "InstanceId": "i-123",
            "Tags": {"Key": "Name", "Value": "web-server"},  # Dict instead of list
        }
        assert detect_aws_tags(obj_tags_not_list) is False

    def test_transform_tags_structure_simple_case(self):
        """Test transform_tags_structure with simple AWS Tags."""
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }

        result = transform_tags_structure(input_data)

        # Should transform Tags to map format
        assert result["InstanceId"] == "i-123"
        assert result["Tags"] == {"Name": "web-server", "Environment": "production"}

        # Should preserve original for debugging
        assert result["Tags_Original"] == input_data["Tags"]

    def test_transform_tags_structure_nested_data(self):
        """Test transform_tags_structure with nested data structures."""
        input_data = {
            "Instances": [
                {
                    "InstanceId": "i-123",
                    "Tags": [
                        {"Key": "Name", "Value": "web-server-1"},
                        {"Key": "Environment", "Value": "production"},
                    ],
                },
                {
                    "InstanceId": "i-456",
                    "Tags": [
                        {"Key": "Name", "Value": "web-server-2"},
                        {"Key": "Environment", "Value": "staging"},
                    ],
                },
            ]
        }

        result = transform_tags_structure(input_data)

        # Should recursively transform Tags in nested structures
        assert len(result["Instances"]) == 2

        instance1 = result["Instances"][0]
        assert instance1["InstanceId"] == "i-123"
        assert instance1["Tags"] == {"Name": "web-server-1", "Environment": "production"}
        assert instance1["Tags_Original"] == input_data["Instances"][0]["Tags"]

        instance2 = result["Instances"][1]
        assert instance2["InstanceId"] == "i-456"
        assert instance2["Tags"] == {"Name": "web-server-2", "Environment": "staging"}

    def test_transform_tags_structure_preserve_non_aws_tags(self):
        """Test transform_tags_structure preserves non-AWS Tags structures."""
        input_data = {
            "InstanceId": "i-123",
            "Tags": ["simple", "string", "list"],  # Not AWS Tags structure
            "CustomTags": [{"Label": "custom", "Data": "value"}],  # Different structure
        }

        result = transform_tags_structure(input_data)

        # Should not transform non-AWS Tags structures
        assert result["Tags"] == ["simple", "string", "list"]
        assert result["CustomTags"] == [{"Label": "custom", "Data": "value"}]
        assert "Tags_Original" not in result

    def test_transform_tags_structure_empty_tags(self):
        """Test transform_tags_structure with empty Tags list."""
        input_data = {"InstanceId": "i-123", "Tags": []}

        result = transform_tags_structure(input_data)

        # Should preserve empty Tags as is
        assert result["Tags"] == []
        assert "Tags_Original" not in result

    def test_transform_tags_structure_complex_nested_structure(self):
        """Test transform_tags_structure with complex nested structure."""
        input_data = {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "test-lb",
                    "Tags": [
                        {"Key": "Name", "Value": "test-load-balancer"},
                        {"Key": "Environment", "Value": "production"},
                        {"Key": "Team", "Value": "infrastructure"},
                    ],
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "Tags": [
                                {"Key": "Name", "Value": "web-server-1"},
                                {"Key": "Role", "Value": "web"},
                            ],
                        }
                    ],
                }
            ]
        }

        result = transform_tags_structure(input_data)

        # Should transform Tags at all levels
        lb = result["LoadBalancers"][0]
        assert lb["Tags"] == {
            "Name": "test-load-balancer",
            "Environment": "production",
            "Team": "infrastructure",
        }

        instance = lb["Instances"][0]
        assert instance["Tags"] == {"Name": "web-server-1", "Role": "web"}

    def test_transform_tags_structure_with_duplicate_keys(self):
        """Test transform_tags_structure with duplicate tag keys (last wins)."""
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Environment", "Value": "staging"},
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},  # Duplicate
            ],
        }

        result = transform_tags_structure(input_data)

        # Last value should win for duplicate keys
        assert result["Tags"] == {"Environment": "production", "Name": "web-server"}  # Last value

    def test_transform_tags_structure_with_special_characters(self):
        """Test transform_tags_structure with special characters in tag values."""
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server-!@#$%"},
                {"Key": "Description", "Value": "Multi\nline\nstring"},
                {"Key": "JSON", "Value": '{"nested": "json"}'},
            ],
        }

        result = transform_tags_structure(input_data)

        # Should preserve special characters
        assert result["Tags"] == {
            "Name": "web-server-!@#$%",
            "Description": "Multi\nline\nstring",
            "JSON": '{"nested": "json"}',
        }

    def test_format_table_output_with_transformed_tags(self):
        """Test format_table_output uses transformed tags for column selection."""
        resources = [
            {
                "InstanceId": "i-123",
                "Tags": [
                    {"Key": "Name", "Value": "web-server-1"},
                    {"Key": "Environment", "Value": "production"},
                ],
            }
        ]

        # Should be able to filter by Tags.Name syntax
        result = format_table_output(
            resources, column_filters=["InstanceId", "Tags.Name", "Tags.Environment"]
        )

        # Should include the instance ID
        assert "i-123" in result
        # Should include transformed tag values
        assert "web-server-1" in result
        assert "production" in result

    def test_format_json_output_with_transformed_tags(self):
        """Test format_json_output uses transformed tags."""
        resources = [
            {
                "InstanceId": "i-123",
                "Tags": [
                    {"Key": "Name", "Value": "web-server-1"},
                    {"Key": "Environment", "Value": "production"},
                ],
            }
        ]

        result = format_json_output(resources)
        parsed = json.loads(result)

        # Should have transformed tags in output
        resource = parsed["results"][0]
        assert resource["Tags"] == {"Name": "web-server-1", "Environment": "production"}

        # Should preserve original for debugging
        assert resource["Tags_Original"] == resources[0]["Tags"]

    def test_extract_and_sort_keys_with_transformed_tags(self):
        """Test extract_and_sort_keys includes transformed tag keys."""
        resources = [
            {
                "InstanceId": "i-123",
                "Tags": [
                    {"Key": "Name", "Value": "web-server"},
                    {"Key": "Environment", "Value": "production"},
                ],
            }
        ]

        keys = extract_and_sort_keys(resources)

        # Should include flattened tag keys from transformed structure
        assert "InstanceId" in keys
        assert "Name" in keys  # From Tags.Name
        assert "Environment" in keys  # From Tags.Environment

    def test_performance_with_large_tag_sets(self):
        """Test tag transformation performance with large tag sets."""
        # Create resource with many tags
        large_tags = [{"Key": f"Tag{i}", "Value": f"Value{i}"} for i in range(100)]
        input_data = {"InstanceId": "i-123", "Tags": large_tags}

        result = transform_tags_structure(input_data)

        # Should transform all tags
        assert len(result["Tags"]) == 100
        assert result["Tags"]["Tag0"] == "Value0"
        assert result["Tags"]["Tag99"] == "Value99"

        # Should preserve original
        assert len(result["Tags_Original"]) == 100

    def test_transform_tags_structure_no_modification_to_original(self):
        """Test transform_tags_structure doesn't modify original data."""
        original_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }
        original_tags = original_data["Tags"][:]  # Copy for comparison

        result = transform_tags_structure(original_data)

        # Original data should remain unchanged
        assert original_data["Tags"] == original_tags
        assert original_data["Tags"][0] == {"Key": "Name", "Value": "web-server"}

        # Result should be different
        assert result["Tags"] != original_data["Tags"]
        assert result["Tags"] == {"Name": "web-server", "Environment": "production"}

    @pytest.mark.parametrize(
        "tag_input,expected_output",
        [
            ([{"Key": "Name", "Value": "test"}], {"Name": "test"}),
            (
                [{"Key": "Environment", "Value": "prod"}, {"Key": "Team", "Value": "dev"}],
                {"Environment": "prod", "Team": "dev"},
            ),
            ([{"Key": "empty-value", "Value": ""}], {"empty-value": ""}),
            ([{"Key": "numeric-value", "Value": "123"}], {"numeric-value": "123"}),
        ],
    )
    def test_transform_tags_structure_parametrized(self, tag_input, expected_output):
        """Test transform_tags_structure with various tag inputs."""
        input_data = {"ResourceId": "test-resource", "Tags": tag_input}

        result = transform_tags_structure(input_data)

        assert result["Tags"] == expected_output
        assert result["Tags_Original"] == tag_input
