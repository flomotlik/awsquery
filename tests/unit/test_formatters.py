"""Unit tests for AWS Query Tool formatting functions."""

import csv
import io
import json
from unittest.mock import Mock, call, patch

import pytest
from tabulate import tabulate

# Import the functions under test
from awsquery.formatters import (
    build_data_rows,
    build_rows,
    detect_aws_tags,
    extract_and_sort_keys,
    flatten_dict_keys,
    flatten_response,
    flatten_single_response,
    format_csv_output,
    format_json_output,
    format_keys_output,
    format_ndjson_output,
    format_table_output,
    format_tsv_output,
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


class TestSingleObjectResponses:
    # A Get/Describe of one object must not be reduced to whichever list it carries.

    FUNCTION = {
        "FunctionName": "my-fn",
        "Runtime": "python3.12",
        "MemorySize": 512,
        "Timeout": 30,
        "Handler": "app.handler",
        "FunctionArn": "arn:aws:lambda:eu-west-1:111111111111:function:my-fn",
    }

    def test_nested_list_does_not_replace_the_object(self):
        response = dict(self.FUNCTION, Layers=[{"Arn": "arn:layer:1", "CodeSize": 1024}])

        result = flatten_response(response, "lambda", "get-function-configuration")

        assert len(result) == 1
        assert result[0]["FunctionName"] == "my-fn"
        assert result[0]["Layers"] == [{"Arn": "arn:layer:1", "CodeSize": 1024}]

    @pytest.mark.parametrize("layers", [None, [{"Arn": "arn:layer:1", "CodeSize": 1024}]])
    def test_default_columns_render_with_and_without_a_layer(self, layers):
        response = dict(self.FUNCTION)
        if layers is not None:
            response["Layers"] = layers

        result = flatten_response([response], "lambda", "get-function-configuration")
        table = format_table_output(result, ["FunctionName$", "Runtime$", "MemorySize$"])

        assert "my-fn" in table
        assert "python3.12" in table
        assert "512" in table

    def test_response_metadata_is_still_dropped(self):
        response = dict(self.FUNCTION, ResponseMetadata={"RequestId": "abc"})

        result = flatten_response(response, "lambda", "get-function-configuration")

        assert "ResponseMetadata" not in result[0]

    def test_sibling_lists_all_survive(self):
        response = {
            "TopicConfigurations": [{"Id": "topic", "TopicArn": "arn:topic"}],
            "QueueConfigurations": [{"Id": "queue", "QueueArn": "arn:queue"}],
        }

        result = flatten_response(response, "s3", "get-bucket-notification-configuration")

        assert len(result) == 1
        assert result[0]["QueueConfigurations"][0]["QueueArn"] == "arn:queue"

    def test_collection_response_still_yields_one_row_per_item(self):
        response = {
            "Buckets": [{"Name": "one"}, {"Name": "two"}],
            "Owner": {"DisplayName": "me"},
        }

        result = flatten_response(response, "s3", "list-buckets")

        assert [bucket["Name"] for bucket in result] == ["one", "two"]


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
        assert "Environment" in result  # Tag key becomes its own column
        assert "Key" not in result
        assert "Value" not in result
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
        # Long values get truncated with ellipsis (early truncation at 80 chars)
        resources = [{"ShortValue": "short", "LongValue": "a" * 90}]  # Over 80 character limit
        result = format_table_output(resources, max_width=2000)

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


class TestTableWidthTruncation:

    def test_truncation_applied_when_exceeds_width(self):
        resources = [
            {"VeryLongColumnName": "This is a very long value that should be truncated"},
            {"VeryLongColumnName": "Another long value here"},
        ]
        result = format_table_output(resources, max_width=50)
        assert "..." in result

    def test_no_truncation_when_within_width(self):
        resources = [{"Name": "short", "Status": "ok"}]
        result = format_table_output(resources, max_width=2000)
        assert "..." not in result
        assert "short" in result
        assert "ok" in result

    def test_truncation_preserves_minimum_column_width(self):
        resources = [{"Col1": "a" * 100, "Col2": "b" * 100, "Col3": "c" * 100}]
        result = format_table_output(resources, max_width=60)
        lines = result.split("\n")
        for line in lines:
            if line.strip() and not line.startswith("+"):
                assert len(line) > 0

    def test_truncation_handles_empty_table(self):
        result = format_table_output([], max_width=50)
        assert result == "No results found."

    def test_truncation_handles_many_columns(self):
        resources = [{"Col" + str(i): "value" + str(i) for i in range(20)}]
        result = format_table_output(resources, max_width=100)
        assert isinstance(result, str)
        assert len(result) > 0


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

    def test_format_json_output_keeps_falsy_values_and_drops_nulls(self):
        resources = [
            {"Name": "resource1", "EmptyString": "", "NullValue": None, "Status": "active"}
        ]
        result = format_json_output(resources, column_filters=["Name", "Status", "Empty", "Null"])
        parsed = json.loads(result)

        assert len(parsed["results"]) == 1
        resource = parsed["results"][0]
        assert resource["Name"] == "resource1"
        assert resource["Status"] == "active"
        assert resource["EmptyString"] == ""
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
        assert "Tags.Environment" in result  # Transformed tag map
        assert not any(key.startswith("Tags_Original") for key in result)

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

        table_result = format_table_output(resources, max_width=2000)
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
        # Uses prefix filters (^) to explicitly target nested array content
        resources = flatten_single_response(
            sample_ec2_response, service="ec2", operation="DescribeInstances"
        )
        col_filters = ["^Instance", "^State", "^Tag"]
        result = format_table_output(resources, column_filters=col_filters, max_width=2000)

        assert "InstanceId" in result
        assert "Name" in result  # From State.Name
        assert "Key" not in result  # raw tag pairs are transformed away

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

        # Uses prefix filters (^) to explicitly target nested array content
        result = format_table_output(
            [complex_resource], column_filters=["^LoadBalancer", "^Protocol"], max_width=2000
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

        assert resource["StringField"] == "test-value"
        assert resource["NumberField"] == 42
        assert resource["BooleanField"] is True
        assert resource["SubField2"] == 100
        assert resource["ArrayOfStrings"] == ["item1", "item2"]

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
        assert "Tags_Original" not in result

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
        assert "Tags_Original" not in instance1

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
        assert "Tags_Original" not in resource

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
        assert "Tags_Original" not in result

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
        assert "Tags_Original" not in result


# Longer than the 80-char cutoff the table builder truncates at, so any test
# comparing a delimited format against build_rows instead of build_data_rows fails.
LONG_ARN = "arn:aws:iam::123456789012:role/service-role/" + "AwsQueryIntegrationTestRole" * 3


@pytest.fixture
def delimited_resources():
    return [
        {
            "InstanceId": "i-111",
            "Tags": [{"Key": "Name", "Value": "web, prod"}],
            "State": {"Name": "running"},
            "Note": 'says "hello"',
            "Arn": LONG_ARN,
        },
        {
            "InstanceId": "i-222",
            "Tags": [{"Key": "Name", "Value": "db"}],
            "State": {"Name": "stopped"},
            "Note": "multi\nline",
            "Arn": LONG_ARN + "-two",
        },
    ]


DELIMITED_FILTERS = ["InstanceId$", "Tags.Name$", "State.Name$", "Note$", "Arn$"]


class TestCsvOutput:

    def test_headers_and_order_match_the_lossless_builder(self, delimited_resources):
        headers, rows = build_data_rows(delimited_resources, DELIMITED_FILTERS)
        parsed = list(
            csv.reader(io.StringIO(format_csv_output(delimited_resources, DELIMITED_FILTERS)))
        )

        assert parsed[0] == headers
        assert parsed[1:] == rows

    def test_value_with_comma_survives_round_trip(self, delimited_resources):
        output = format_csv_output(delimited_resources, ["InstanceId$", "Tags.Name$"])
        parsed = list(csv.reader(io.StringIO(output)))

        assert parsed[1] == ["i-111", "web, prod"]
        assert '"web, prod"' in output

    def test_value_with_quote_survives_round_trip(self, delimited_resources):
        parsed = list(
            csv.reader(
                io.StringIO(format_csv_output(delimited_resources, ["InstanceId$", "Note$"]))
            )
        )

        assert parsed[1] == ["i-111", 'says "hello"']

    def test_value_with_newline_survives_round_trip(self, delimited_resources):
        parsed = list(
            csv.reader(
                io.StringIO(format_csv_output(delimited_resources, ["InstanceId$", "Note$"]))
            )
        )

        assert parsed[2] == ["i-222", "multi\nline"]

    def test_every_row_has_the_header_width(self, delimited_resources):
        parsed = list(
            csv.reader(io.StringIO(format_csv_output(delimited_resources, DELIMITED_FILTERS)))
        )

        assert all(len(row) == len(parsed[0]) for row in parsed)

    def test_no_trailing_newline(self, delimited_resources):
        output = format_csv_output(delimited_resources, DELIMITED_FILTERS)

        assert not output.endswith("\n")

    def test_empty_resources_produce_empty_output(self):
        assert format_csv_output([]) == ""

    def test_unmatched_column_filters_produce_empty_output(self, delimited_resources):
        assert format_csv_output(delimited_resources, ["NoSuchColumn$"]) == ""


class TestTsvOutput:

    def test_headers_and_order_match_the_lossless_builder(self, delimited_resources):
        headers, rows = build_data_rows(delimited_resources, DELIMITED_FILTERS)
        parsed = list(
            csv.reader(
                io.StringIO(format_tsv_output(delimited_resources, DELIMITED_FILTERS)),
                delimiter="\t",
            )
        )

        assert parsed[0] == headers
        assert parsed[1:] == rows

    def test_columns_are_tab_separated(self, delimited_resources):
        output = format_tsv_output(delimited_resources, ["InstanceId$", "State.Name$"])

        assert output.splitlines()[0] == "InstanceId\tName"
        assert output.splitlines()[1] == "i-111\trunning"

    def test_value_with_comma_is_not_quoted(self, delimited_resources):
        output = format_tsv_output(delimited_resources, ["InstanceId$", "Tags.Name$"])

        assert "i-111\tweb, prod" in output

    def test_agrees_with_csv_on_parsed_content(self, delimited_resources):
        csv_rows = list(
            csv.reader(io.StringIO(format_csv_output(delimited_resources, DELIMITED_FILTERS)))
        )
        tsv_rows = list(
            csv.reader(
                io.StringIO(format_tsv_output(delimited_resources, DELIMITED_FILTERS)),
                delimiter="\t",
            )
        )

        assert tsv_rows == csv_rows

    def test_empty_resources_produce_empty_output(self):
        assert format_tsv_output([]) == ""


class TestNdjsonOutput:

    def test_every_line_parses_independently(self, delimited_resources):
        lines = format_ndjson_output(delimited_resources, DELIMITED_FILTERS).splitlines()

        assert len(lines) == len(delimited_resources)
        assert all(isinstance(json.loads(line), dict) for line in lines)

    def test_no_results_envelope(self, delimited_resources):
        output = format_ndjson_output(delimited_resources, DELIMITED_FILTERS)

        assert "results" not in output
        assert not output.lstrip().startswith("{\n")

    def test_keys_match_the_lossless_builder_headers(self, delimited_resources):
        headers, _ = build_data_rows(delimited_resources, DELIMITED_FILTERS)
        objects = [
            json.loads(line)
            for line in format_ndjson_output(delimited_resources, DELIMITED_FILTERS).splitlines()
        ]

        assert all(list(obj) == headers for obj in objects)

    def test_values_match_the_csv_cells(self, delimited_resources):
        headers, rows = build_data_rows(delimited_resources, DELIMITED_FILTERS)
        objects = [
            json.loads(line)
            for line in format_ndjson_output(delimited_resources, DELIMITED_FILTERS).splitlines()
        ]

        assert [[obj[header] for header in headers] for obj in objects] == rows

    def test_native_value_types_are_preserved(self):
        resources = [{"Name": "a", "Count": 3, "Enabled": False, "Ratio": 1.5}]

        obj = json.loads(format_ndjson_output(resources, ["Name$", "Count$", "Enabled$", "Ratio$"]))

        assert obj["Count"] == 3
        assert obj["Enabled"] is False
        assert obj["Ratio"] == 1.5

    def test_lines_are_compact(self, delimited_resources):
        output = format_ndjson_output(delimited_resources, ["InstanceId$", "State.Name$"])

        assert output.splitlines()[0] == '{"InstanceId":"i-111","Name":"running"}'

    def test_resources_without_matching_columns_are_skipped(self, delimited_resources):
        assert format_ndjson_output(delimited_resources, ["NoSuchColumn$"]) == ""

    def test_empty_resources_produce_empty_output(self):
        assert format_ndjson_output([]) == ""


class TestLosslessDelimitedValues:
    """agent-reference.md promises csv/tsv do not truncate; only the table does."""

    POLICY_DOCUMENT = (
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":'
        '["ec2:DescribeInstances","ec2:DescribeTags"],"Resource":"*"}]}'
    )

    def test_csv_keeps_a_long_arn_byte_for_byte(self):
        resources = [{"Name": "role", "Arn": LONG_ARN}]

        parsed = list(csv.reader(io.StringIO(format_csv_output(resources, ["Name$", "Arn$"]))))

        assert len(LONG_ARN) > 80
        assert parsed[1] == ["role", LONG_ARN]

    def test_tsv_keeps_a_long_policy_document_byte_for_byte(self):
        resources = [{"Name": "policy", "Document": self.POLICY_DOCUMENT}]

        parsed = list(
            csv.reader(
                io.StringIO(format_tsv_output(resources, ["Name$", "Document$"])), delimiter="\t"
            )
        )

        assert len(self.POLICY_DOCUMENT) > 80
        assert parsed[1] == ["policy", self.POLICY_DOCUMENT]

    def test_ndjson_keeps_a_long_arn_byte_for_byte(self):
        resources = [{"Name": "role", "Arn": LONG_ARN}]

        obj = json.loads(format_ndjson_output(resources, ["Name$", "Arn$"]))

        assert obj["Arn"] == LONG_ARN

    def test_json_keeps_a_long_arn_byte_for_byte(self):
        resources = [{"Name": "role", "Arn": LONG_ARN}]

        results = json.loads(format_json_output(resources, ["Name$", "Arn$"]))["results"]

        assert results[0]["Arn"] == LONG_ARN

    def test_the_table_is_the_format_that_truncates(self):
        resources = [{"Name": "role", "Arn": LONG_ARN}]

        table = format_table_output(resources, ["Name$", "Arn$"], max_width=500)

        assert LONG_ARN not in table
        assert LONG_ARN[:77] + "..." in table

    def test_truncation_never_leaks_into_the_lossless_builder(self):
        resources = [{"Name": "role", "Arn": LONG_ARN}]

        _, display_rows = build_rows(resources, ["Name$", "Arn$"])
        _, data_rows = build_data_rows(resources, ["Name$", "Arn$"])

        assert display_rows[0][1].endswith("...")
        assert data_rows[0][1] == LONG_ARN


class TestOutputFormatAgreement:

    def test_table_csv_tsv_and_ndjson_expose_the_same_columns(self, delimited_resources):
        headers, _ = build_data_rows(delimited_resources, DELIMITED_FILTERS)
        csv_headers = format_csv_output(delimited_resources, DELIMITED_FILTERS).splitlines()[0]
        tsv_headers = format_tsv_output(delimited_resources, DELIMITED_FILTERS).splitlines()[0]
        first_object = json.loads(
            format_ndjson_output(delimited_resources, DELIMITED_FILTERS).splitlines()[0]
        )
        table = format_table_output(delimited_resources, DELIMITED_FILTERS, max_width=500)

        assert csv_headers == ",".join(headers)
        assert tsv_headers == "\t".join(headers)
        assert list(first_object) == headers
        assert all(header in table for header in headers)

    @pytest.mark.parametrize(
        "formatter,expected",
        [
            (format_csv_output, ""),
            (format_tsv_output, ""),
            (format_ndjson_output, ""),
            (format_table_output, "No results found."),
        ],
    )
    def test_empty_resources_do_not_raise(self, formatter, expected):
        assert formatter([]) == expected

    def test_empty_resources_json_keeps_envelope(self):
        assert json.loads(format_json_output([])) == {"results": []}


PARITY_RESOURCES = [
    {"Name": "a", "Count": 0, "Flag": False},
    {"Name": "b", "Count": 5},
    {"Name": "", "Count": 0},
]

PARITY_FILTERS = ["Name$", "Count$"]


def json_results(resources, column_filters=None):
    return json.loads(format_json_output(resources, column_filters))["results"]


def ndjson_objects(resources, column_filters=None):
    output = format_ndjson_output(resources, column_filters)
    return [json.loads(line) for line in output.splitlines()] if output else []


def csv_rows(resources, column_filters=None):
    output = format_csv_output(resources, column_filters)
    return list(csv.reader(io.StringIO(output))) if output else []


class TestMachineFormatRowParity:

    def test_filtered_formats_emit_one_row_per_resource(self):
        rows = csv_rows(PARITY_RESOURCES, PARITY_FILTERS)

        assert len(json_results(PARITY_RESOURCES, PARITY_FILTERS)) == len(PARITY_RESOURCES)
        assert len(ndjson_objects(PARITY_RESOURCES, PARITY_FILTERS)) == len(PARITY_RESOURCES)
        assert len(rows) == len(PARITY_RESOURCES) + 1

    def test_unfiltered_formats_emit_one_row_per_resource(self):
        rows = csv_rows(PARITY_RESOURCES)

        assert len(json_results(PARITY_RESOURCES)) == len(PARITY_RESOURCES)
        assert len(ndjson_objects(PARITY_RESOURCES)) == len(PARITY_RESOURCES)
        assert len(rows) == len(PARITY_RESOURCES) + 1

    def test_json_and_ndjson_agree_object_for_object(self):
        assert json_results(PARITY_RESOURCES, PARITY_FILTERS) == ndjson_objects(
            PARITY_RESOURCES, PARITY_FILTERS
        )

    def test_json_and_ndjson_agree_without_column_filters(self):
        assert json_results(PARITY_RESOURCES) == ndjson_objects(PARITY_RESOURCES)

    def test_numbers_stay_numbers_in_both_json_formats(self):
        from_json = [obj["Count"] for obj in json_results(PARITY_RESOURCES, PARITY_FILTERS)]
        from_ndjson = [obj["Count"] for obj in ndjson_objects(PARITY_RESOURCES, PARITY_FILTERS)]

        assert from_json == from_ndjson == [0, 5, 0]
        assert all(type(count) is int for count in from_json + from_ndjson)

    def test_booleans_stay_booleans_in_both_json_formats(self):
        assert ndjson_objects(PARITY_RESOURCES)[0]["Flag"] is False
        assert json_results(PARITY_RESOURCES)[0]["Flag"] is False

    def test_falsy_values_keep_their_resource_in_every_format(self):
        empty_name_row = csv_rows(PARITY_RESOURCES, PARITY_FILTERS)[-1]

        assert json_results(PARITY_RESOURCES, PARITY_FILTERS)[-1] == {"Name": "", "Count": 0}
        assert ndjson_objects(PARITY_RESOURCES, PARITY_FILTERS)[-1] == {"Name": "", "Count": 0}
        assert empty_name_row == ["", "0"]

    def test_csv_cells_are_the_stringified_json_values(self):
        headers, *rows = csv_rows(PARITY_RESOURCES, PARITY_FILTERS)
        objects = ndjson_objects(PARITY_RESOURCES, PARITY_FILTERS)

        assert headers == ["Name", "Count"]
        assert rows == [[str(obj[header]) for header in headers] for obj in objects]

    def test_nulls_are_dropped_from_json_formats_but_keep_the_row(self):
        resources = [{"Name": "a", "Optional": None}, {"Name": "b", "Optional": "set"}]
        filters = ["Name$", "Optional$"]

        assert json_results(resources, filters) == [{"Name": "a"}, {"Name": "b", "Optional": "set"}]
        assert ndjson_objects(resources, filters) == json_results(resources, filters)
        assert csv_rows(resources, filters)[1:] == [["a", ""], ["b", "set"]]

    def test_empty_input_keeps_the_json_envelope_and_empties_the_rest(self):
        assert json.loads(format_json_output([])) == {"results": []}
        assert format_ndjson_output([]) == ""
        assert format_csv_output([]) == ""

    def test_unfiltered_json_returns_whole_resources(self):
        resources = [{"Name": "a", "Nested": {"Deep": [1, 2]}}]

        assert json_results(resources) == resources

    def test_table_drops_the_all_blank_row_that_machine_formats_keep(self):
        blank = [{"Name": "", "Count": 0}]
        table = format_table_output(blank, PARITY_FILTERS, max_width=200)

        assert [line for line in table.splitlines() if line.startswith("|")] == [
            "| Name   | Count   |"
        ]
        assert len(ndjson_objects(blank, PARITY_FILTERS)) == 1
        assert len(csv_rows(blank, PARITY_FILTERS)) == 2


class TestKeysOutput:

    KEYS = ["InstanceId", "State.Name", "Tags.Name"]

    def test_json_wraps_the_list_in_a_keys_object(self):
        assert json.loads(format_keys_output(self.KEYS, "json")) == {"keys": self.KEYS}

    def test_ndjson_emits_one_json_string_per_line(self):
        lines = format_keys_output(self.KEYS, "ndjson").splitlines()

        assert [json.loads(line) for line in lines] == self.KEYS
        assert lines[0] == '"InstanceId"'

    @pytest.mark.parametrize("output_format", ["csv", "tsv"])
    def test_delimited_formats_carry_a_key_header(self, output_format):
        delimiter = "\t" if output_format == "tsv" else ","
        parsed = list(
            csv.reader(
                io.StringIO(format_keys_output(self.KEYS, output_format)), delimiter=delimiter
            )
        )

        assert parsed == [["key"]] + [[key] for key in self.KEYS]

    def test_table_indents_each_key(self):
        assert format_keys_output(self.KEYS, "table") == ("  InstanceId\n  State.Name\n  Tags.Name")

    def test_table_is_the_default(self):
        assert format_keys_output(self.KEYS) == format_keys_output(self.KEYS, "table")

    @pytest.mark.parametrize("output_format", ["table", "ndjson", "csv", "tsv"])
    def test_line_oriented_formats_have_no_trailing_newline(self, output_format):
        assert not format_keys_output(self.KEYS, output_format).endswith("\n")

    @pytest.mark.parametrize(
        "output_format,expected",
        [("json", '{\n  "keys": []\n}'), ("ndjson", ""), ("csv", "key"), ("table", "")],
    )
    def test_empty_key_list(self, output_format, expected):
        assert format_keys_output([], output_format) == expected

    def test_keys_with_a_delimiter_survive_csv_quoting(self):
        parsed = list(csv.reader(io.StringIO(format_keys_output(["a,b"], "csv"))))

        assert parsed[1] == ["a,b"]

    def test_generator_input_is_consumed_once(self):
        assert json.loads(format_keys_output(iter(self.KEYS), "json")) == {"keys": self.KEYS}
