"""Unit tests for -p parameter option parsing and handling.

This test suite verifies that the -p option correctly parses various parameter
formats and converts them to appropriate Python objects for boto3 API calls.
"""

from unittest.mock import Mock, patch

import pytest

from awsquery.cli import parse_parameter_string


class TestParameterParsing:
    """Test parameter string parsing functionality."""

    def test_parse_simple_parameter(self):
        """Parse simple key=value parameter."""
        result = parse_parameter_string("SomeParameter=Value")
        assert result == {"SomeParameter": "Value"}

    def test_parse_list_parameter(self):
        """Parse comma-separated list values."""
        result = parse_parameter_string("Values=Ubuntu,2024,Amazon")
        assert result == {"Values": ["Ubuntu", 2024, "Amazon"]}

    def test_parse_dict_parameter(self):
        """Parse key=value pairs into dict structure."""
        # This should be treated as a single parameter with a list value
        result = parse_parameter_string("Tags=Environment,Production,Debug")
        expected = {"Tags": ["Environment", "Production", "Debug"]}
        assert result == expected

    def test_parse_complex_structure(self):
        """Parse nested structures with semicolons as separators."""
        param_str = (
            "ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu,2024;"
            "Key=Name,Option=Contains,Values=Amazon,Linux;"
        )
        result = parse_parameter_string(param_str)
        expected = {
            "ParameterFilters": [
                {"Key": "Name", "Option": "Contains", "Values": ["Ubuntu", 2024]},
                {"Key": "Name", "Option": "Contains", "Values": ["Amazon", "Linux"]},
            ]
        }
        assert result == expected

    def test_parameter_filters_example(self):
        """Real SSM ParameterFilters example from Todo.md."""
        param_str = (
            "ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu,2024;"
            "Key=Name,Option=Contains,Values=Amazon,Linux;"
        )
        result = parse_parameter_string(param_str)

        # Should create list of filter dicts
        assert "ParameterFilters" in result
        assert isinstance(result["ParameterFilters"], list)
        assert len(result["ParameterFilters"]) == 2

        # First filter
        filter1 = result["ParameterFilters"][0]
        assert filter1["Key"] == "Name"
        assert filter1["Option"] == "Contains"
        assert filter1["Values"] == ["Ubuntu", 2024]

        # Second filter
        filter2 = result["ParameterFilters"][1]
        assert filter2["Key"] == "Name"
        assert filter2["Option"] == "Contains"
        assert filter2["Values"] == ["Amazon", "Linux"]

    def test_multiple_p_options(self):
        """Handle multiple -p flags with parameter merging."""
        params = ["InstanceIds=i-123,i-456", "MaxResults=10"]

        # Test merging multiple parameter strings
        result = {}
        for param in params:
            parsed = parse_parameter_string(param)
            result.update(parsed)

        expected = {"InstanceIds": ["i-123", "i-456"], "MaxResults": 10}
        assert result == expected

    def test_invalid_parameter_format(self):
        """Error handling for malformed parameter input."""
        with pytest.raises(ValueError, match="Invalid parameter format"):
            parse_parameter_string("InvalidFormat")

        with pytest.raises(ValueError, match="Invalid parameter format"):
            parse_parameter_string("=MissingKey")

    def test_parameter_type_conversion(self):
        """Auto-convert parameter values to appropriate types."""
        # Test boolean conversion
        result = parse_parameter_string("EnableEncryption=true")
        assert result == {"EnableEncryption": True}

        result = parse_parameter_string("DisableMetrics=false")
        assert result == {"DisableMetrics": False}

        # Test integer conversion
        result = parse_parameter_string("MaxResults=100")
        assert result == {"MaxResults": 100}

        # Test string preservation
        result = parse_parameter_string("TagKey=Environment")
        assert result == {"TagKey": "Environment"}

    def test_empty_parameter_handling(self):
        """Handle empty or whitespace parameter strings."""
        with pytest.raises(ValueError):
            parse_parameter_string("")

        with pytest.raises(ValueError):
            parse_parameter_string("   ")

    def test_special_characters_in_values(self):
        """Handle special characters in parameter values."""
        result = parse_parameter_string("TagFilter=Environment:prod-2024")
        assert result == {"TagFilter": "Environment:prod-2024"}

        result = parse_parameter_string("S3Key=data/logs/2024-09-26.log")
        assert result == {"S3Key": "data/logs/2024-09-26.log"}

    def test_nested_comma_handling(self):
        """Handle commas within values vs commas as separators."""
        # For now, let's handle the simple case - commas always separate values
        # If you need a comma in a value, it would need to be escaped or quoted

        # Multiple values should split on commas
        result = parse_parameter_string("Tags=Environment,Production")
        assert result == {"Tags": ["Environment", "Production"]}

        # Single value without commas
        result = parse_parameter_string("Description=SingleValue")
        assert result == {"Description": "SingleValue"}

    def test_whitespace_handling(self):
        """Handle whitespace in parameter strings."""
        result = parse_parameter_string("Key = Value")
        assert result == {"Key": "Value"}

        result = parse_parameter_string("Values = Item1 , Item2 ")
        assert result == {"Values": ["Item1", "Item2"]}

    def test_case_sensitivity(self):
        """Parameter names and values should preserve case."""
        result = parse_parameter_string("InstanceType=t3.micro")
        assert result == {"InstanceType": "t3.micro"}

        result = parse_parameter_string("Environment=PRODUCTION")
        assert result == {"Environment": "PRODUCTION"}


class TestAdvancedParameterPatterns:
    """Test advanced AWS parameter patterns that parse as lists of dictionaries."""

    def test_aws_lookup_attributes_pattern(self):
        """Test AWS LookupAttributes parameter pattern (CloudTrail, etc.)."""
        param_str = "LookupAttributes=AttributeKey=EventName,AttributeValue=DescribeStackResources"
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [
                {"AttributeKey": "EventName", "AttributeValue": "DescribeStackResources"}
            ]
        }
        assert result == expected

        # Verify this creates the correct structure for AWS APIs
        assert isinstance(result["LookupAttributes"], list)
        assert len(result["LookupAttributes"]) == 1
        lookup_attr = result["LookupAttributes"][0]
        assert isinstance(lookup_attr, dict)
        assert "AttributeKey" in lookup_attr
        assert "AttributeValue" in lookup_attr

    def test_multiple_lookup_attributes_with_semicolons(self):
        """Test multiple AWS LookupAttributes using semicolon separator."""
        param_str = (
            "LookupAttributes="
            "AttributeKey=EventName,AttributeValue=DescribeStackResources;"
            "AttributeKey=Username,AttributeValue=admin"
        )
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [
                {"AttributeKey": "EventName", "AttributeValue": "DescribeStackResources"},
                {"AttributeKey": "Username", "AttributeValue": "admin"},
            ]
        }
        assert result == expected

    def test_aws_tag_specification_pattern(self):
        """Test AWS TagSpecification parameter format."""
        param_str = "TagSpecifications=ResourceType=instance,Tags=Name,MyInstance"
        result = parse_parameter_string(param_str)

        # Since not all comma-separated items contain '=', this falls back to a simple list
        expected = {"TagSpecifications": ["ResourceType=instance", "Tags=Name", "MyInstance"]}
        assert result == expected

    def test_aws_parameter_group_pattern(self):
        """Test AWS parameter group parameter format (RDS, etc.)."""
        param_str = "Parameters=ParameterName=max_connections,ParameterValue=100"
        result = parse_parameter_string(param_str)

        # All items contain '=', so this creates a single dict in a list
        expected = {"Parameters": [{"ParameterName": "max_connections", "ParameterValue": 100}]}
        assert result == expected

    def test_aws_configuration_pattern(self):
        """Test AWS configuration parameter format (S3, etc.)."""
        param_str = "Configuration=LocationConstraint=us-west-2,CORSConfiguration=Enabled"
        result = parse_parameter_string(param_str)

        expected = {
            "Configuration": [{"LocationConstraint": "us-west-2", "CORSConfiguration": "Enabled"}]
        }
        assert result == expected

    def test_aws_environment_variables_pattern(self):
        """Test AWS environment variables parameter format (Lambda, etc.)."""
        param_str = "Environment=Variables=NODE_ENV,production,DEBUG,false"
        result = parse_parameter_string(param_str)

        # Not all comma-separated items contain '=', so this falls back to a simple list
        expected = {"Environment": ["Variables=NODE_ENV", "production", "DEBUG", False]}
        assert result == expected


class TestParameterParsingLogic:
    """Test the core logic that determines how parameters are parsed."""

    def test_all_items_have_equals_creates_dict_list(self):
        """Test that when ALL comma-separated items have '=', it creates a list with a dict."""
        param_str = "Config=Key1=Value1,Key2=Value2,Key3=Value3"
        result = parse_parameter_string(param_str)

        expected = {"Config": [{"Key1": "Value1", "Key2": "Value2", "Key3": "Value3"}]}
        assert result == expected

    def test_not_all_items_have_equals_creates_simple_list(self):
        """Test that when NOT ALL comma-separated items have '=', it creates a simple list."""
        param_str = "Config=Key1=Value1,plainvalue,Key3=Value3"
        result = parse_parameter_string(param_str)

        expected = {"Config": ["Key1=Value1", "plainvalue", "Key3=Value3"]}
        assert result == expected

    def test_mixed_equals_boundary_case(self):
        """Test boundary case where some items have '=' but not all."""
        param_str = "Items=first=1,second,third=3,fourth"
        result = parse_parameter_string(param_str)

        # Since not all items have '=', falls back to simple list
        expected = {"Items": ["first=1", "second", "third=3", "fourth"]}
        assert result == expected

    def test_single_key_value_pair_no_comma(self):
        """Test single key=value pair without commas."""
        param_str = "LookupAttributes=AttributeKey=EventName"
        result = parse_parameter_string(param_str)

        # This should not be treated as a list of dicts since there's no comma
        expected = {"LookupAttributes": "AttributeKey=EventName"}
        assert result == expected

    def test_empty_items_in_comma_list(self):
        """Test handling of empty items in comma-separated values."""
        param_str = "Values=item1,,item3"
        result = parse_parameter_string(param_str)

        # Empty items are filtered out
        expected = {"Values": ["item1", "item3"]}
        assert result == expected

    def test_empty_values_in_key_value_pairs(self):
        """Test handling of empty values in key=value pairs."""
        param_str = "LookupAttributes=AttributeKey=EventName,AttributeValue="
        result = parse_parameter_string(param_str)

        expected = {"LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": ""}]}
        assert result == expected


class TestParameterValueTypes:
    """Test automatic type conversion in parameter values."""

    def test_numbers_and_booleans_in_key_value_pairs(self):
        """Test automatic type conversion in key=value pairs."""
        param_str = "Parameters=MaxRetries=5,EnableSSL=true,Timeout=30,Debug=false"
        result = parse_parameter_string(param_str)

        expected = {
            "Parameters": [{"MaxRetries": 5, "EnableSSL": True, "Timeout": 30, "Debug": False}]
        }
        assert result == expected

    def test_special_characters_in_parameter_values(self):
        """Test special characters in parameter values."""
        param_str = "LookupAttributes=AttributeKey=EventName,AttributeValue=S3:GetObject"
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": "S3:GetObject"}]
        }
        assert result == expected

    def test_unicode_characters_in_values(self):
        """Test Unicode characters in parameter values."""
        param_str = "LookupAttributes=AttributeKey=ResourceName,AttributeValue=café-资源"
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": "café-资源"}]
        }
        assert result == expected

    def test_url_values(self):
        """Test values that are URLs."""
        param_str = (
            "LookupAttributes=AttributeKey=SourceIPAddress,"
            "AttributeValue=https://example.com/path?param=value"
        )
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [
                {
                    "AttributeKey": "SourceIPAddress",
                    "AttributeValue": "https://example.com/path?param=value",
                }
            ]
        }
        assert result == expected

    def test_arn_values(self):
        """Test values that are AWS ARNs."""
        param_str = (
            "LookupAttributes=AttributeKey=ResourceName,AttributeValue=arn:aws:s3:::my-bucket/path"
        )
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [
                {"AttributeKey": "ResourceName", "AttributeValue": "arn:aws:s3:::my-bucket/path"}
            ]
        }
        assert result == expected

    def test_timestamp_values(self):
        """Test values that are timestamps."""
        param_str = "LookupAttributes=AttributeKey=StartTime,AttributeValue=2024-09-27T10:00:00Z"
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [
                {"AttributeKey": "StartTime", "AttributeValue": "2024-09-27T10:00:00Z"}
            ]
        }
        assert result == expected

    def test_regex_like_values(self):
        """Test values that look like regex patterns."""
        param_str = "LookupAttributes=AttributeKey=EventName,AttributeValue=^.*Create.*$"
        result = parse_parameter_string(param_str)

        expected = {
            "LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": "^.*Create.*$"}]
        }
        assert result == expected

    def test_json_like_values(self):
        """Test values that contain JSON-like syntax."""
        param_str = 'Parameters=Key=Policy,Value={"Version":"2012-10-17"}'
        result = parse_parameter_string(param_str)

        expected = {"Parameters": [{"Key": "Policy", "Value": '{"Version":"2012-10-17"}'}]}
        assert result == expected


class TestParameterErrorHandling:
    """Test error handling for malformed parameters."""

    def test_malformed_key_value_in_list(self):
        """Test handling of malformed key=value pairs in a list context."""
        # This should not raise an error, but should handle gracefully
        param_str = "LookupAttributes=AttributeKey=EventName,=MissingKey,AttributeValue=Test"
        result = parse_parameter_string(param_str)

        # Should skip the malformed entry and process valid ones
        expected = {"LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": "Test"}]}
        assert result == expected

    def test_none_input(self):
        """Test error handling for None input."""
        with pytest.raises(ValueError, match="Invalid parameter format: empty parameter string"):
            parse_parameter_string(None)


class TestComplexAWSScenarios:
    """Test complex real-world AWS parameter scenarios."""

    def test_cloudformation_parameters(self):
        """Test CloudFormation parameter format."""
        param_str = "Parameters=ParameterKey=Environment,ParameterValue=Production"
        result = parse_parameter_string(param_str)

        expected = {"Parameters": [{"ParameterKey": "Environment", "ParameterValue": "Production"}]}
        assert result == expected

    def test_ecs_task_definition(self):
        """Test ECS task definition parameter format."""
        param_str = "ContainerDefinitions=name=web,image=nginx:latest,memory=512"
        result = parse_parameter_string(param_str)

        expected = {
            "ContainerDefinitions": [{"name": "web", "image": "nginx:latest", "memory": 512}]
        }
        assert result == expected

    def test_route53_resource_record(self):
        """Test Route53 resource record parameter format."""
        param_str = "ResourceRecordSet=Name=example.com,Type=A,TTL=300"
        result = parse_parameter_string(param_str)

        expected = {"ResourceRecordSet": [{"Name": "example.com", "Type": "A", "TTL": 300}]}
        assert result == expected

    def test_dynamodb_attribute_definitions(self):
        """Test DynamoDB attribute definition parameter format."""
        param_str = "AttributeDefinitions=AttributeName=UserId,AttributeType=S"
        result = parse_parameter_string(param_str)

        expected = {"AttributeDefinitions": [{"AttributeName": "UserId", "AttributeType": "S"}]}
        assert result == expected

    def test_cloudwatch_metric_data(self):
        """Test CloudWatch metric data parameter format."""
        param_str = "MetricData=MetricName=CPUUtilization,Value=85.5,Unit=Percent"
        result = parse_parameter_string(param_str)

        # All items contain '=', so this creates a single dict in a list
        # Note: 85.5 stays as string since only integers are auto-converted
        expected = {
            "MetricData": [{"MetricName": "CPUUtilization", "Value": "85.5", "Unit": "Percent"}]
        }
        assert result == expected


class TestBackwardsCompatibility:
    """Test that existing parameter formats still work correctly."""

    def test_simple_key_value_unchanged(self):
        """Test that simple key=value parameters still work."""
        param_str = "MaxResults=100"
        result = parse_parameter_string(param_str)

        expected = {"MaxResults": 100}
        assert result == expected

    def test_comma_separated_list_unchanged(self):
        """Test that comma-separated lists still work."""
        param_str = "InstanceIds=i-123,i-456,i-789"
        result = parse_parameter_string(param_str)

        expected = {"InstanceIds": ["i-123", "i-456", "i-789"]}
        assert result == expected

    def test_boolean_conversion_unchanged(self):
        """Test that boolean conversion still works."""
        param_str = "DryRun=true"
        result = parse_parameter_string(param_str)

        expected = {"DryRun": True}
        assert result == expected

    def test_integer_conversion_unchanged(self):
        """Test that integer conversion still works."""
        param_str = "MaxResults=50"
        result = parse_parameter_string(param_str)

        expected = {"MaxResults": 50}
        assert result == expected

    def test_ssm_parameter_filters_unchanged(self):
        """Test that existing SSM ParameterFilters format still works."""
        param_str = (
            "ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu,2024;"
            "Key=Name,Option=Contains,Values=Amazon,Linux"
        )
        result = parse_parameter_string(param_str)

        expected = {
            "ParameterFilters": [
                {"Key": "Name", "Option": "Contains", "Values": ["Ubuntu", 2024]},
                {"Key": "Name", "Option": "Contains", "Values": ["Amazon", "Linux"]},
            ]
        }
        assert result == expected


class TestParameterIntegration:
    """Integration tests for parameter handling with CLI."""

    def test_parameter_argument_parsing(self):
        """Test that -p arguments are correctly parsed by argparse."""
        # This would test the actual CLI argument parsing
        # Will be implemented when we add the -p option to the argument parser
        pass

    def test_parameter_merging_with_existing_args(self):
        """Test that -p parameters merge correctly with existing CLI behavior."""
        # This would test integration with existing filtering
        pass

    def test_parameter_validation_with_aws_apis(self):
        """Test that parsed parameters are valid for AWS API calls."""
        # This would test integration with boto3 client calls
        pass
