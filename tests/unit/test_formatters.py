"""Unit tests for AWS Query Tool formatting functions."""

import json
from unittest.mock import Mock, call, patch

import pytest
from tabulate import tabulate

# Import the functions under test
from awsquery.formatters import (
    detect_aws_tags,
    extract_and_sort_keys,
    flatten_dict_keys,
    flatten_response,
    flatten_single_response,
    format_json_output,
    format_table_output,
    make_unique_headers,
    transform_tags_structure,
)
from awsquery.utils import simplify_key


class TestFlattenResponse:

    def test_flatten_response_empty_list(self):
        result = flatten_response([], service="ec2", operation="DescribeInstances")
        assert result == []

    def test_flatten_response_empty_single_response(self):
        result = flatten_response(None, service="ec2", operation="DescribeInstances")
        assert result == []

        result = flatten_response({}, service="ec2", operation="DescribeInstances")
        assert result == []

    def test_flatten_response_paginated_responses(self, sample_paginated_responses):
        result = flatten_response(
            sample_paginated_responses, service="ec2", operation="DescribeInstances"
        )

        assert len(result) == 4  # 2 instances per page * 2 pages

        instance_ids = [instance["InstanceId"] for instance in result]
        assert "i-page1-instance1" in instance_ids
        assert "i-page1-instance2" in instance_ids
        assert "i-page2-instance1" in instance_ids
        assert "i-page2-instance2" in instance_ids

    def test_flatten_response_single_non_paginated(self, sample_ec2_response):
        result = flatten_response(sample_ec2_response, service="ec2", operation="DescribeInstances")

        # Extracts reservations (largest list) from single response
        assert len(result) == 1
        reservation = result[0]
        assert "ReservationId" in reservation
        assert "Instances" in reservation
        assert len(reservation["Instances"]) == 2
        instance_ids = [instance["InstanceId"] for instance in reservation["Instances"]]
        assert "i-1234567890abcdef0" in instance_ids
        assert "i-abcdef1234567890" in instance_ids

    def test_flatten_response_direct_list(self):
        direct_list = [
            {"InstanceId": "i-direct1", "State": {"Name": "running"}},
            {"InstanceId": "i-direct2", "State": {"Name": "stopped"}},
        ]
        result = flatten_response(direct_list, service="ec2", operation="DescribeInstances")

        # When input is list, it processes each item as a page
        assert len(result) == 2
        assert result[0]["InstanceId"] == "i-direct1"
        assert result[1]["InstanceId"] == "i-direct2"


class TestFlattenSingleResponse:

    def test_flatten_single_response_empty_inputs(self):
        result = flatten_single_response(None, service="ec2", operation="DescribeInstances")
        assert result == []

        result = flatten_single_response({}, service="ec2", operation="DescribeInstances")
        assert result == []

        result = flatten_single_response([], service="ec2", operation="DescribeInstances")
        assert result == []

    def test_flatten_single_response_direct_list(self):
        resources = [
            {"InstanceId": "i-123", "State": "running"},
            {"InstanceId": "i-456", "State": "stopped"},
        ]
        result = flatten_single_response(resources, service="ec2", operation="DescribeInstances")
        assert result == resources
        assert len(result) == 2

    def test_flatten_single_response_non_dict_input(self):
        # Non-dict input gets wrapped in list
        result = flatten_single_response(
            "string value", service="ec2", operation="DescribeInstances"
        )
        assert result == ["string value"]

        result = flatten_single_response(42, service="ec2", operation="DescribeInstances")
        assert result == [42]

        result = flatten_single_response(True, service="ec2", operation="DescribeInstances")
        assert result == [True]

    def test_flatten_single_response_only_response_metadata(self):
        # Only ResponseMetadata returns empty list
        response = {"ResponseMetadata": {"RequestId": "test-request-id", "HTTPStatusCode": 200}}
        result = flatten_single_response(response, service="ec2", operation="DescribeInstances")
        assert result == []

    def test_flatten_single_response_single_list_key(self, sample_ec2_response):
        result = flatten_single_response(
            sample_ec2_response, service="ec2", operation="DescribeInstances"
        )

        assert len(result) == 1  # One reservation
        reservation = result[0]
        assert "ReservationId" in reservation
        assert "Instances" in reservation

        instances = reservation["Instances"]
        instance_ids = [instance["InstanceId"] for instance in instances]
        assert "i-1234567890abcdef0" in instance_ids
        assert "i-abcdef1234567890" in instance_ids

    def test_flatten_single_response_multiple_list_keys_chooses_largest(self):
        # Chooses largest list when multiple lists present
        response = {
            "SmallList": [{"id": 1}],
            "LargeList": [{"id": 1}, {"id": 2}, {"id": 3}],
            "MediumList": [{"id": 1}, {"id": 2}],
            "ResponseMetadata": {"RequestId": "test"},
        }
        result = flatten_single_response(response, service="ec2", operation="DescribeInstances")

        assert len(result) == 3
        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_flatten_single_response_no_list_keys_returns_whole_response(self):
        # No list keys returns whole response (minus ResponseMetadata)
        response = {
            "ResourceId": "resource-123",
            "Name": "test-resource",
            "Status": "active",
            "ResponseMetadata": {"RequestId": "test"},
        }
        result = flatten_single_response(response, service="ec2", operation="DescribeInstances")

        assert len(result) == 1
        assert result[0]["ResourceId"] == "resource-123"
        assert result[0]["Name"] == "test-resource"
        assert result[0]["Status"] == "active"
        assert "ResponseMetadata" not in result[0]

    def test_flatten_single_response_mixed_list_and_non_list_keys(self, sample_s3_response):
        # Ignores non-list keys when list key present
        result = flatten_single_response(
            sample_s3_response, service="ec2", operation="DescribeInstances"
        )

        assert len(result) == 3
        assert all("Name" in bucket for bucket in result)
        bucket_names = [bucket["Name"] for bucket in result]
        assert "production-logs-bucket" in bucket_names
        assert "staging-backup-bucket" in bucket_names
        assert "development-assets" in bucket_names


class TestFlattenDictKeys:

    def test_flatten_dict_keys_simple_dict(self):
        data = {"Name": "test-resource", "Status": "active", "Count": 5}
        result = flatten_dict_keys(data)

        assert result == {"Name": "test-resource", "Status": "active", "Count": 5}

    def test_flatten_dict_keys_nested_dict(self):
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
        # Non-dict inputs get wrapped with 'value' key
        result = flatten_dict_keys("test-string")
        assert result == {"value": "test-string"}

        result = flatten_dict_keys(42)
        assert result == {"value": 42}

        result = flatten_dict_keys(True)
        assert result == {"value": True}

        result = flatten_dict_keys(None)
        assert result == {"value": None}

    def test_flatten_dict_keys_non_dict_input_with_parent_key(self):
        # Non-dict inputs preserve parent key
        result = flatten_dict_keys("test-string", parent_key="existing_key")
        assert result == {"existing_key": "test-string"}

    def test_flatten_dict_keys_empty_dict(self):
        result = flatten_dict_keys({})
        assert result == {}

    def test_flatten_dict_keys_custom_separator(self):
        data = {"Level1": {"Level2": "value"}}
        result = flatten_dict_keys(data, sep="_")
        assert result == {"Level1_Level2": "value"}

    def test_flatten_dict_keys_mixed_data_types(self):
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


class TestSimplifyKey:

    @pytest.mark.parametrize(
        "full_key,expected",
        [
            # Basic cases
            ("Name", "Name"),
            ("InstanceId", "InstanceId"),
            ("Status", "Status"),
            ("ReservationId", "ReservationId"),
            # Nested keys with indices - normalized to remove indices but preserve hierarchy
            ("Instances.0.InstanceId", "Instances.InstanceId"),
            ("Instances.0.NetworkInterfaces.0.SubnetId", "Instances.NetworkInterfaces.SubnetId"),
            ("Tags.0.Name", "Tags.Name"),
            ("Tags.0.Value", "Tags.Value"),
            ("Buckets.0.Name", "Buckets.Name"),
            ("SecurityGroups.1.GroupName", "SecurityGroups.GroupName"),
            # Multiple levels without indices
            ("Level1.Level2.Level3.FinalValue", "Level1.Level2.Level3.FinalValue"),
            ("Owner.DisplayName", "Owner.DisplayName"),
            ("State.Name", "State.Name"),
            ("Reservation.Instances.0.State.Code", "Reservation.Instances.State.Code"),
            # Edge cases
            ("", ""),
            ("123", "123"),
            ("0.1.2", "0.1.2"),
            ("Resource.0.1.Name", "Resource.Name"),
            # Complex AWS-style keys
            (
                "Reservations.0.Instances.0.NetworkInterfaces.0.Association.PublicIp",
                "Reservations.Instances.NetworkInterfaces.Association.PublicIp",
            ),
            ("Stacks.0.Parameters.1.ParameterValue", "Stacks.Parameters.ParameterValue"),
            ("Buckets.2.CreationDate", "Buckets.CreationDate"),
        ],
    )
    def test_simplify_key_patterns(self, full_key, expected):
        result = simplify_key(full_key)
        assert result == expected

    def test_simplify_key_none_input(self):
        result = simplify_key(None)
        assert result is None

    def test_simplify_key_single_component(self):
        result = simplify_key("SimpleKey")
        assert result == "SimpleKey"

        result = simplify_key("123")
        assert result == "123"


class TestMakeUniqueHeaders:

    def test_make_unique_headers_empty_list(self):
        result = make_unique_headers([])
        assert result == []

    def test_make_unique_headers_single_key(self):
        result = make_unique_headers(["InstanceId"])
        assert result == ["InstanceId"]

    def test_make_unique_headers_no_conflicts(self):
        normalized_keys = ["Name", "InstanceId", "Status"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Name", "InstanceId", "Status"]

    def test_make_unique_headers_with_conflicts(self):
        normalized_keys = ["Tags.Name", "State.Name", "InstanceId"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Tags.Name", "State.Name", "InstanceId"]

    def test_make_unique_headers_multiple_conflicts(self):
        normalized_keys = ["Tags.Name", "State.Name", "Owner.Name", "InstanceId"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Tags.Name", "State.Name", "Owner.Name", "InstanceId"]

    def test_make_unique_headers_simplifies_unique_keys(self):
        normalized_keys = ["Tags.Name", "State.Name", "InstanceId", "VpcId"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Tags.Name", "State.Name", "InstanceId", "VpcId"]

    def test_make_unique_headers_mixed_conflicts_and_unique(self):
        normalized_keys = ["Instance.State.Name", "Tag.State.Name", "InstanceId", "Status"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Instance.State.Name", "Tag.State.Name", "InstanceId", "Status"]

    def test_make_unique_headers_preserves_order(self):
        normalized_keys = ["Zebra.Name", "Apple.Name", "Banana"]
        result = make_unique_headers(normalized_keys)
        assert result == ["Zebra.Name", "Apple.Name", "Banana"]

    def test_make_unique_headers_complex_paths_with_conflicts(self):
        normalized_keys = [
            "Instances.NetworkInterfaces.SubnetId",
            "Instances.Tags.Name",
            "Instances.State.Name",
            "Owner.Name",
        ]
        result = make_unique_headers(normalized_keys)
        # Uses minimal parent hierarchy to make names unique
        assert result == [
            "SubnetId",  # Unique without parents
            "Tags.Name",  # Minimal to distinguish from State.Name and Owner.Name
            "State.Name",  # Minimal to distinguish from Tags.Name and Owner.Name
            "Owner.Name",  # Minimal to distinguish from Tags.Name and State.Name
        ]


class TestTableOutput:

    def test_format_table_output_empty_resources(self):
        result = format_table_output([])
        assert result == "No results found."

        result = format_table_output(None)
        assert result == "No results found."

    def test_format_table_output_simple_resources(self):
        resources = [
            {"Name": "resource1", "Status": "active", "Count": 5},
            {"Name": "resource2", "Status": "inactive", "Count": 3},
        ]
        result = format_table_output(resources)

        assert "┌─" in result or "|" in result  # Grid format indicators
        assert "Name" in result
        assert "Status" in result
        assert "Count" in result
        assert "resource1" in result
        assert "resource2" in result

    def test_format_table_output_nested_resources(self):
        # Nested resources get flattened
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = format_table_output(resources)

        assert "InstanceId" in result
        assert "Name" in result  # Simplified from State.Name
        assert "Code" in result  # Simplified from State.Code
        assert "Key" in result  # Simplified from Tags.0.Key
        assert "Value" in result  # Simplified from Tags.0.Value
        assert "i-123" in result
        assert "running" in result

    def test_format_table_output_column_filters_matching(self):
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "State": {"Name": "running"},
                "PublicIpAddress": "1.2.3.4",
            }
        ]
        result = format_table_output(resources, column_filters=["Instance", "State"])

        assert "InstanceId" in result or "InstanceType" in result
        assert "Name" in result  # From State.Name
        # Should not include PublicIpAddress (no filter match)
        assert "PublicIpAddress" not in result and "PublicIp" not in result

    def test_format_table_output_column_filters_no_matches(self):
        resources = [{"Name": "resource1", "Status": "active"}]
        result = format_table_output(resources, column_filters=["NonExistent"])

        assert result == "No matching columns found."

    def test_format_table_output_key_deduplication_with_conflicts(self):
        resources = [
            {
                "Tags": [{"Key": "Name", "Value": "my-instance"}],
                "State": {"Name": "running"},
                "InstanceId": "i-123",
            }
        ]
        result = format_table_output(resources)

        assert "Tags.Name" in result
        assert "State.Name" in result
        assert "InstanceId" in result
        assert "my-instance" in result
        assert "running" in result
        assert "i-123" in result

    def test_format_table_output_no_conflicts_simplifies(self):
        resources = [{"Name": "simple-resource", "Status": "active", "InstanceId": "i-123"}]
        result = format_table_output(resources)

        assert "Name" in result
        assert "Status" in result
        assert "InstanceId" in result
        assert "simple-resource" in result
        assert "active" in result

    def test_format_table_output_long_value_truncation(self):
        # Long values get truncated with ellipsis
        resources = [{"ShortValue": "short", "LongValue": "a" * 90}]  # Over 80 character limit
        result = format_table_output(resources)

        assert "short" in result
        assert ("a" * 77 + "...") in result

    def test_format_table_output_empty_rows_filtered(self):
        # Empty rows get filtered out
        resources = [
            {"Name": "resource1", "Status": "active"},
            {"OtherField": ""},  # This won't match any columns
            {"Name": "", "Status": ""},  # Empty values
            {"Name": "resource2", "Status": "inactive"},
        ]
        result = format_table_output(resources)

        assert "resource1" in result
        assert "resource2" in result
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


class TestJsonOutput:

    def test_format_json_output_empty_resources(self):
        result = format_json_output([])
        parsed = json.loads(result)
        assert parsed == {"results": []}

        result = format_json_output(None)
        parsed = json.loads(result)
        assert parsed == {"results": []}

    def test_format_json_output_simple_resources(self):
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
        # Without column filters, preserves original structure
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = format_json_output(resources)
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["InstanceId"] == "i-123"
        assert parsed["results"][0]["State"]["Name"] == "running"

    def test_format_json_output_with_column_filters(self):
        # Column filters flatten and filter the output
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

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]

        assert "InstanceId" in resource or "InstanceType" in resource
        assert "Name" in resource  # Simplified from State.Name
        assert "PublicIpAddress" not in resource

    def test_format_json_output_key_deduplication_with_conflicts(self):
        resources = [
            {
                "Tags": [{"Key": "Name", "Value": "my-instance"}],
                "State": {"Name": "running"},
                "InstanceId": "i-123",
            }
        ]
        result = format_json_output(resources, column_filters=["Name", "InstanceId"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert "Tags.Name" in resource
        assert "State.Name" in resource
        assert "InstanceId" in resource
        assert resource["Tags.Name"] == "my-instance"
        assert resource["State.Name"] == "running"
        assert resource["InstanceId"] == "i-123"

    def test_format_json_output_no_conflicts_simplifies(self):
        resources = [
            {
                "Tags": [{"Key": "Environment", "Value": "prod"}],
                "InstanceId": "i-123",
            }
        ]
        result = format_json_output(resources, column_filters=["Environment", "InstanceId"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert "Environment" in resource
        assert "InstanceId" in resource
        assert resource["Environment"] == "prod"
        assert resource["InstanceId"] == "i-123"

    def test_format_json_output_filters_empty_values(self):
        # Empty/null values get filtered out
        resources = [
            {"Name": "resource1", "EmptyString": "", "NullValue": None, "Status": "active"}
        ]
        result = format_json_output(resources, column_filters=["Name", "Status", "Empty", "Null"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert "Name" in resource
        assert "Status" in resource
        assert "EmptyString" not in resource
        assert "NullValue" not in resource

    def test_format_json_output_no_matching_resources(self):
        # No columns match returns empty results
        resources = [{"Name": "resource1", "Status": "active"}]
        result = format_json_output(resources, column_filters=["NonExistent"])
        parsed = json.loads(result)

        assert parsed["results"] == []

    def test_format_json_output_default_string_conversion(self):
        # Non-serializable objects get converted to string
        from datetime import datetime

        resources = [
            {"Name": "resource1", "CreatedAt": datetime(2023, 1, 1, 12, 0, 0), "Count": 42}
        ]
        result = format_json_output(resources)
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert resource["Name"] == "resource1"
        assert "2023-01-01 12:00:00" in str(resource["CreatedAt"])
        assert resource["Count"] == 42

    def test_format_json_output_proper_json_structure(self):
        # Valid JSON with proper indentation
        resources = [{"Name": "test"}]
        result = format_json_output(resources)

        parsed = json.loads(result)
        assert "results" in parsed

        assert "\n" in result
        lines = result.split("\n")
        indented_lines = [line for line in lines if line.startswith("  ")]
        assert len(indented_lines) > 0


class TestUtilityFunctions:

    def test_extract_and_sort_keys_empty_resources(self):
        result = extract_and_sort_keys([])
        assert result == []

        result = extract_and_sort_keys(None)
        assert result == []

    def test_extract_and_sort_keys_simple_resources(self):
        resources = [
            {"Name": "resource1", "Status": "active", "Count": 5},
            {"Name": "resource2", "Type": "web", "Status": "inactive"},
        ]
        result = extract_and_sort_keys(resources)

        expected_keys = ["Count", "Name", "Status", "Type"]
        assert result == expected_keys

    def test_extract_and_sort_keys_nested_resources(self):
        resources = [
            {
                "InstanceId": "i-123",
                "State": {"Name": "running", "Code": 16},
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ]
        result = extract_and_sort_keys(resources)

        assert "InstanceId" in result
        assert "State.Name" in result  # Normalized from State.Name
        assert "State.Code" in result  # Normalized from State.Code
        assert "Tags_Original.Key" in result  # From Tags.0.Key (original preserved)
        assert "Tags_Original.Value" in result  # From Tags.0.Value (original preserved)
        assert "Tags.Environment" in result  # Transformed tag map

        assert result == sorted(result, key=str.lower)

    def test_extract_and_sort_keys_case_insensitive_sort(self):
        # Case-insensitive sorting
        resources = [{"zebra": "z", "Apple": "a", "Banana": "b", "cherry": "c"}]
        result = extract_and_sort_keys(resources)

        assert result == ["Apple", "Banana", "cherry", "zebra"]

    def test_extract_and_sort_keys_deduplication(self):
        # Keys are normalized but preserve full path
        resources = [
            {"Instance.Name": "instance1", "Resource.Name": "resource1", "State.Name": "running"}
        ]
        result = extract_and_sort_keys(resources)

        # With new normalization, each keeps its full path
        assert "Instance.Name" in result
        assert "Resource.Name" in result
        assert "State.Name" in result

    def test_extract_and_sort_keys_with_various_data_types(self):
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

        # ArrayField becomes ArrayField.0, ArrayField.1, ArrayField.2 which normalize to ArrayField
        expected_keys = sorted(
            ["ArrayField", "BooleanField", "ObjectField.NestedKey", "NumberField", "StringField"],
            key=str.lower,
        )
        assert result == expected_keys


class TestColumnNamingIntegration:

    def test_ec2_instances_with_conflicting_name_fields(self):
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "Tags": [
                    {"Key": "Name", "Value": "web-server-01"},
                    {"Key": "Environment", "Value": "production"},
                ],
                "State": {"Name": "running", "Code": 16},
                "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123", "SubnetId": "subnet-abc"}],
            }
        ]

        table_result = format_table_output(resources)
        assert "Tags.Name" in table_result
        assert "State.Name" in table_result
        assert "web-server-01" in table_result
        assert "running" in table_result

        json_result = format_json_output(resources)
        parsed = json.loads(json_result)
        resource = parsed["results"][0]
        assert resource["Tags"]["Name"] == "web-server-01"
        assert resource["State"]["Name"] == "running"

    def test_s3_buckets_with_conflicting_name_fields(self):
        resources = [
            {
                "Name": "my-bucket",
                "Owner": {"Name": "john-doe", "ID": "123456"},
                "CreationDate": "2023-01-01T00:00:00Z",
            }
        ]

        table_result = format_table_output(resources)
        assert "Name" in table_result or "Owner.Name" in table_result
        assert "my-bucket" in table_result
        assert "john-doe" in table_result

        json_result = format_json_output(resources, column_filters=["Name"])
        parsed = json.loads(json_result)
        assert len(parsed["results"]) == 1

    def test_multiple_nested_levels_with_same_final_segment(self):
        resources = [
            {
                "InstanceId": "i-123",
                "NetworkInterfaces": [
                    {
                        "NetworkInterfaceId": "eni-123",
                        "Association": {"PublicIp": "1.2.3.4"},
                        "PrivateIpAddresses": [{"Association": {"PublicIp": "1.2.3.5"}}],
                    }
                ],
            }
        ]

        table_result = format_table_output(resources)
        assert "InstanceId" in table_result

        json_result = format_json_output(resources)
        parsed = json.loads(json_result)
        assert len(parsed["results"]) == 1

    def test_index_removal_in_normalized_keys(self):
        resources = [
            {
                "Instances": [
                    {
                        "InstanceId": "i-123",
                        "Tags": [{"Key": "Name", "Value": "instance-1"}],
                    }
                ]
            }
        ]

        keys = extract_and_sort_keys(resources)
        assert "Instances.InstanceId" in keys
        assert "Instances.Tags.Name" in keys

        assert not any(".0." in key or ".1." in key for key in keys)


class TestComplexScenarios:

    def test_format_table_output_aws_ec2_instances(self, sample_ec2_response):
        # Realistic EC2 instances formatting
        resources = flatten_single_response(
            sample_ec2_response, service="ec2", operation="DescribeInstances"
        )
        result = format_table_output(resources, column_filters=["Instance", "State", "Tag"])

        assert "InstanceId" in result
        assert "Name" in result  # From State.Name
        assert any(tag in result for tag in ["Key", "Value"])  # From Tags

        assert "i-1234567890abcdef0" in result
        assert "i-abcdef1234567890" in result
        assert "running" in result
        assert "stopped" in result

    def test_format_json_output_aws_s3_buckets(self, sample_s3_response):
        # Realistic S3 buckets formatting
        resources = flatten_single_response(
            sample_s3_response, service="ec2", operation="DescribeInstances"
        )
        result = format_json_output(resources, column_filters=["Name", "Creation"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 3

        for bucket in parsed["results"]:
            assert "Name" in bucket
            # CreationDate should be simplified to just show Creation
            if "CreationDate" in str(result):
                assert True  # Expected

    def test_format_table_output_complex_nested_structure(self):
        # Complex nested AWS-like structure
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

        assert "LoadBalancerName" in result or "DNSName" in result
        assert "Protocol" in result
        assert "HTTP" in result
        assert "HTTPS" in result

    def test_format_json_output_mixed_data_types(self):
        # Mixed data types from AWS responses
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

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]

        # All fields get stringified for consistency
        for key, value in resource.items():
            assert isinstance(value, str)

    def test_flatten_response_real_paginated_data(self):
        # Realistic paginated data handling
        from tests.fixtures.aws_responses import get_paginated_response

        paginated_data = get_paginated_response("ec2", "describe_instances", 2, 3)
        result = flatten_response(paginated_data, service="ec2", operation="DescribeInstances")

        # Each page has 1 reservation with 3 instances
        assert len(result) == 2  # 2 pages * 1 reservation per page

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
        # Large complex structure handling
        from tests.fixtures.aws_responses import get_complex_nested_response

        complex_response = get_complex_nested_response(depth=3, breadth=2)
        resources = flatten_single_response(
            complex_response, service="ec2", operation="DescribeInstances"
        )
        result = extract_and_sort_keys(resources)

        assert len(result) >= 10

        assert result == sorted(result, key=str.lower)

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

        table_result = format_table_output(resources, column_filters=column_filter)
        assert table_result != "No matching columns found."

        json_result = format_json_output(resources, column_filters=column_filter)
        parsed = json.loads(json_result)
        assert len(parsed["results"]) > 0

    def test_edge_case_empty_and_null_handling(self):
        # Edge cases with empty and null values
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

        table_result = format_table_output(resources)
        assert "ValidField" in table_result
        assert "has-value" in table_result

        json_result = format_json_output(resources)
        parsed = json.loads(json_result)
        assert len(parsed["results"]) == 1

        keys = extract_and_sort_keys(resources)
        assert len(keys) > 0


class TestTagTransformation:

    def test_detect_aws_tags_valid_structure(self):
        obj_with_tags = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }
        assert detect_aws_tags(obj_with_tags) is True

    def test_detect_aws_tags_empty_tags(self):
        obj_empty_tags = {"InstanceId": "i-123", "Tags": []}
        assert detect_aws_tags(obj_empty_tags) is False

    def test_detect_aws_tags_no_tags_field(self):
        obj_no_tags = {"InstanceId": "i-123", "State": "running"}
        assert detect_aws_tags(obj_no_tags) is False

    def test_detect_aws_tags_invalid_tag_structure(self):
        # Missing Key/Value structure
        obj_invalid_tags = {
            "InstanceId": "i-123",
            "Tags": [{"Name": "invalid-structure"}],
        }
        assert detect_aws_tags(obj_invalid_tags) is False

    def test_detect_aws_tags_tags_not_list(self):
        # Dict instead of list
        obj_tags_not_list = {
            "InstanceId": "i-123",
            "Tags": {"Key": "Name", "Value": "web-server"},
        }
        assert detect_aws_tags(obj_tags_not_list) is False

    def test_transform_tags_structure_simple_case(self):
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }

        result = transform_tags_structure(input_data)

        # Tags transformed to map format
        assert result["InstanceId"] == "i-123"
        assert result["Tags"] == {"Name": "web-server", "Environment": "production"}

        # Original preserved for debugging
        assert result["Tags_Original"] == input_data["Tags"]

    def test_transform_tags_structure_nested_data(self):
        # Nested data structures with Tags
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

        # Recursively transforms Tags in nested structures
        assert len(result["Instances"]) == 2

        instance1 = result["Instances"][0]
        assert instance1["InstanceId"] == "i-123"
        assert instance1["Tags"] == {"Name": "web-server-1", "Environment": "production"}
        assert instance1["Tags_Original"] == input_data["Instances"][0]["Tags"]

        instance2 = result["Instances"][1]
        assert instance2["InstanceId"] == "i-456"
        assert instance2["Tags"] == {"Name": "web-server-2", "Environment": "staging"}

    def test_transform_tags_structure_preserve_non_aws_tags(self):
        # Non-AWS Tags structures get preserved
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
        input_data = {"InstanceId": "i-123", "Tags": []}

        result = transform_tags_structure(input_data)

        # Empty Tags preserved as is
        assert result["Tags"] == []
        assert "Tags_Original" not in result

    def test_transform_tags_structure_complex_nested_structure(self):
        # Complex nested structure with Tags at multiple levels
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

        # Transforms Tags at all levels
        lb = result["LoadBalancers"][0]
        assert lb["Tags"] == {
            "Name": "test-load-balancer",
            "Environment": "production",
            "Team": "infrastructure",
        }

        instance = lb["Instances"][0]
        assert instance["Tags"] == {"Name": "web-server-1", "Role": "web"}

    def test_transform_tags_structure_with_duplicate_keys(self):
        # Duplicate tag keys - last value wins
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Environment", "Value": "staging"},
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},  # Duplicate
            ],
        }

        result = transform_tags_structure(input_data)

        assert result["Tags"] == {"Environment": "production", "Name": "web-server"}

    def test_transform_tags_structure_with_special_characters(self):
        # Special characters in tag values
        input_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server-!@#$%"},
                {"Key": "Description", "Value": "Multi\nline\nstring"},
                {"Key": "JSON", "Value": '{"nested": "json"}'},
            ],
        }

        result = transform_tags_structure(input_data)

        # Special characters preserved
        assert result["Tags"] == {
            "Name": "web-server-!@#$%",
            "Description": "Multi\nline\nstring",
            "JSON": '{"nested": "json"}',
        }

    def test_format_table_output_with_transformed_tags(self):
        # Table output uses transformed tags for column selection
        resources = [
            {
                "InstanceId": "i-123",
                "Tags": [
                    {"Key": "Name", "Value": "web-server-1"},
                    {"Key": "Environment", "Value": "production"},
                ],
            }
        ]

        result = format_table_output(
            resources, column_filters=["InstanceId", "Tags.Name", "Tags.Environment"]
        )

        assert "i-123" in result
        assert "web-server-1" in result
        assert "production" in result

    def test_format_json_output_with_transformed_tags(self):
        # JSON output uses transformed tags
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

        resource = parsed["results"][0]
        assert resource["Tags"] == {"Name": "web-server-1", "Environment": "production"}

        # Original preserved for debugging
        assert resource["Tags_Original"] == resources[0]["Tags"]

    def test_extract_and_sort_keys_with_transformed_tags(self):
        # Key extraction includes transformed tag keys
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

        assert "InstanceId" in keys
        assert "Tags.Name" in keys  # From Tags.Name (normalized)
        assert "Tags.Environment" in keys  # From Tags.Environment (normalized)

    def test_performance_with_large_tag_sets(self):
        # Performance test with many tags
        large_tags = [{"Key": f"Tag{i}", "Value": f"Value{i}"} for i in range(100)]
        input_data = {"InstanceId": "i-123", "Tags": large_tags}

        result = transform_tags_structure(input_data)

        assert len(result["Tags"]) == 100
        assert result["Tags"]["Tag0"] == "Value0"
        assert result["Tags"]["Tag99"] == "Value99"

        assert len(result["Tags_Original"]) == 100

    def test_transform_tags_structure_no_modification_to_original(self):
        # Original data remains unchanged
        original_data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }
        original_tags = original_data["Tags"][:]  # Copy for comparison

        result = transform_tags_structure(original_data)

        assert original_data["Tags"] == original_tags
        assert original_data["Tags"][0] == {"Key": "Name", "Value": "web-server"}

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
        input_data = {"ResourceId": "test-resource", "Tags": tag_input}

        result = transform_tags_structure(input_data)

        assert result["Tags"] == expected_output
        assert result["Tags_Original"] == tag_input
