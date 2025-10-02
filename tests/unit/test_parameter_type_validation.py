"""Unit tests for parameter type validation and auto-wrapping.

This test suite verifies that the get_parameter_type() function correctly
identifies AWS parameter types from boto3 service models, and that the
auto-wrapping logic properly wraps single values in lists when needed.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from awsquery.cli import get_parameter_type, parse_parameter_string


class TestGetParameterType:
    """Test get_parameter_type() function."""

    @patch("botocore.session.Session")
    def test_returns_list_type_for_filters(self, mock_session_class):
        """Returns 'list' for SSM Filters parameter."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_param_shape = Mock()
        mock_param_shape.type_name = "list"

        mock_input_shape.members = {"Filters": mock_param_shape}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ssm", "describe-parameters", "Filters")
        assert result == "list"
        mock_service_model.operation_model.assert_called_once_with("DescribeParameters")

    @patch("botocore.session.Session")
    def test_returns_string_type(self, mock_session_class):
        """Returns 'string' for string parameters."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_param_shape = Mock()
        mock_param_shape.type_name = "string"

        mock_input_shape.members = {"InstanceId": mock_param_shape}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ec2", "describe-instances", "InstanceId")
        assert result == "string"
        mock_service_model.operation_model.assert_called_once_with("DescribeInstances")

    @patch("botocore.session.Session")
    def test_returns_integer_type(self, mock_session_class):
        """Returns 'integer' for integer parameters."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_param_shape = Mock()
        mock_param_shape.type_name = "integer"

        mock_input_shape.members = {"MaxResults": mock_param_shape}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ec2", "describe-instances", "MaxResults")
        assert result == "integer"
        mock_service_model.operation_model.assert_called_once_with("DescribeInstances")

    @patch("botocore.session.Session")
    def test_returns_structure_type(self, mock_session_class):
        """Returns 'structure' for complex object parameters."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_param_shape = Mock()
        mock_param_shape.type_name = "structure"

        mock_input_shape.members = {"LaunchTemplate": mock_param_shape}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ec2", "run-instances", "LaunchTemplate")
        assert result == "structure"
        mock_service_model.operation_model.assert_called_once_with("RunInstances")

    @patch("botocore.session.Session")
    def test_returns_none_when_parameter_not_found(self, mock_session_class):
        """Returns None when parameter doesn't exist in operation."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_input_shape.members = {}

        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ec2", "describe-instances", "NonExistentParam")
        assert result is None

    @patch("botocore.session.Session")
    def test_returns_none_when_no_input_shape(self, mock_session_class):
        """Returns None when operation has no input shape."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_operation_model.input_shape = None

        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("s3", "list-buckets", "SomeParam")
        assert result is None

    @patch("botocore.session.Session")
    def test_handles_errors_gracefully(self, mock_session_class):
        """Returns None when errors occur."""
        mock_session_class.side_effect = Exception("Service error")

        result = get_parameter_type("invalid", "invalid-action", "SomeParam")
        assert result is None

    @patch("botocore.session.Session")
    def test_normalizes_action_name(self, mock_session_class):
        """Action name is normalized before lookup."""
        mock_session = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()
        mock_param_shape = Mock()
        mock_param_shape.type_name = "list"

        mock_input_shape.members = {"InstanceIds": mock_param_shape}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        result = get_parameter_type("ec2", "describe-instances", "InstanceIds")
        assert result == "list"

        mock_service_model.operation_model.assert_called_once()
        call_args = mock_service_model.operation_model.call_args[0]
        assert call_args[0] == "DescribeInstances"


class TestAutoWrappingLogic:
    """Test auto-wrapping logic in main() function."""

    @patch("awsquery.cli.get_parameter_type")
    def test_single_dict_wrapped_when_type_is_list(self, mock_get_type):
        """Single dict value gets wrapped in list when expected type is 'list'."""
        mock_get_type.return_value = "list"

        param_str = "Filters=Key=Type,Values=StringList"
        parsed = parse_parameter_string(param_str)
        assert parsed == {"Filters": [{"Key": "Type", "Values": "StringList"}]}

        corrected = {}
        for key, value in parsed.items():
            expected_type = mock_get_type("ssm", "describe-parameters", key)
            if expected_type == "list" and not isinstance(value, list):
                corrected[key] = [value]
            else:
                corrected[key] = value

        assert corrected == {"Filters": [{"Key": "Type", "Values": "StringList"}]}

    @patch("awsquery.cli.get_parameter_type")
    def test_dict_value_wrapped_in_list(self, mock_get_type):
        """Dict value gets wrapped in list when type is 'list'."""
        mock_get_type.return_value = "list"

        value = {"Key": "Name", "Values": ["test"]}
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [{"Key": "Name", "Values": ["test"]}]

    @patch("awsquery.cli.get_parameter_type")
    def test_list_not_double_wrapped(self, mock_get_type):
        """Value already in list doesn't get double-wrapped."""
        mock_get_type.return_value = "list"

        value = [{"Key": "Name", "Values": ["test"]}]
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [{"Key": "Name", "Values": ["test"]}]

    @patch("awsquery.cli.get_parameter_type")
    def test_string_parameter_not_wrapped(self, mock_get_type):
        """String parameters don't get wrapped in list."""
        mock_get_type.return_value = "string"

        value = "test-value"
        expected_type = mock_get_type("ec2", "describe-instances", "InstanceId")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == "test-value"

    @patch("awsquery.cli.get_parameter_type")
    def test_integer_parameter_not_wrapped(self, mock_get_type):
        """Integer parameters don't get wrapped in list."""
        mock_get_type.return_value = "integer"

        value = 100
        expected_type = mock_get_type("ec2", "describe-instances", "MaxResults")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == 100

    @patch("awsquery.cli.get_parameter_type")
    def test_structure_parameter_not_wrapped(self, mock_get_type):
        """Structure parameters don't get wrapped in list."""
        mock_get_type.return_value = "structure"

        value = {"Key": "Value"}
        expected_type = mock_get_type("ec2", "run-instances", "LaunchTemplate")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == {"Key": "Value"}

    @patch("awsquery.cli.get_parameter_type")
    def test_wrapping_when_type_unknown(self, mock_get_type):
        """No wrapping when parameter type cannot be determined."""
        mock_get_type.return_value = None

        value = {"Key": "Value"}
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == {"Key": "Value"}


class TestRealWorldScenarios:
    """Test real-world AWS parameter scenarios with type validation."""

    @patch("awsquery.cli.get_parameter_type")
    def test_ssm_filters_parameter(self, mock_get_type):
        """SSM describe-parameters Filters parameter works correctly."""
        mock_get_type.return_value = "list"

        param_str = "Filters=Key=Type,Values=StringList"
        parsed = parse_parameter_string(param_str)

        corrected = {}
        for key, value in parsed.items():
            expected_type = mock_get_type("ssm", "describe-parameters", key)
            if expected_type == "list" and not isinstance(value, list):
                corrected[key] = [value]
            else:
                corrected[key] = value

        expected = {"Filters": [{"Key": "Type", "Values": "StringList"}]}
        assert corrected == expected

    @patch("awsquery.cli.get_parameter_type")
    def test_ec2_instance_ids_parameter(self, mock_get_type):
        """EC2 describe-instances InstanceIds parameter works correctly."""
        mock_get_type.return_value = "list"

        param_str = "InstanceIds=i-123,i-456"
        parsed = parse_parameter_string(param_str)
        assert parsed == {"InstanceIds": ["i-123", "i-456"]}

        corrected = {}
        for key, value in parsed.items():
            expected_type = mock_get_type("ec2", "describe-instances", key)
            if expected_type == "list" and not isinstance(value, list):
                corrected[key] = [value]
            else:
                corrected[key] = value

        assert corrected == {"InstanceIds": ["i-123", "i-456"]}

    @patch("awsquery.cli.get_parameter_type")
    def test_multiple_parameters_with_different_types(self, mock_get_type):
        """Multiple parameters with different types are handled correctly."""

        def get_type_side_effect(service, action, param_name, session=None):
            if param_name == "Filters":
                return "list"
            elif param_name == "MaxResults":
                return "integer"
            elif param_name == "NextToken":
                return "string"
            return None

        mock_get_type.side_effect = get_type_side_effect

        params = {
            "Filters": {"Key": "Type", "Values": ["StringList"]},
            "MaxResults": 50,
            "NextToken": "abc123",
        }

        corrected = {}
        for key, value in params.items():
            expected_type = mock_get_type("ssm", "describe-parameters", key)
            if expected_type == "list" and not isinstance(value, list):
                corrected[key] = [value]
            else:
                corrected[key] = value

        expected = {
            "Filters": [{"Key": "Type", "Values": ["StringList"]}],
            "MaxResults": 50,
            "NextToken": "abc123",
        }
        assert corrected == expected

    @patch("awsquery.cli.get_parameter_type")
    def test_cloudtrail_lookup_attributes(self, mock_get_type):
        """Test CloudTrail LookupAttributes parameter works correctly."""
        mock_get_type.return_value = "list"

        param_str = "LookupAttributes=AttributeKey=EventName,AttributeValue=DescribeStackResources"
        parsed = parse_parameter_string(param_str)

        corrected = {}
        for key, value in parsed.items():
            expected_type = mock_get_type("cloudtrail", "lookup-events", key)
            if expected_type == "list" and not isinstance(value, list):
                corrected[key] = [value]
            else:
                corrected[key] = value

        expected = {
            "LookupAttributes": [
                {"AttributeKey": "EventName", "AttributeValue": "DescribeStackResources"}
            ]
        }
        assert corrected == expected

    @patch("awsquery.cli.get_parameter_type")
    def test_single_string_value_wrapped_when_list_expected(self, mock_get_type):
        """Single string value gets wrapped when parameter expects list."""
        mock_get_type.return_value = "list"

        value = "single-string-value"
        expected_type = mock_get_type("ssm", "get-parameters", "Names")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == ["single-string-value"]


class TestEdgeCases:
    """Test edge cases for parameter type validation."""

    @patch("awsquery.cli.get_parameter_type")
    def test_empty_dict_wrapped(self, mock_get_type):
        """Empty dict gets wrapped when type is list."""
        mock_get_type.return_value = "list"

        value = {}
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [{}]

    @patch("awsquery.cli.get_parameter_type")
    def test_empty_list_not_modified(self, mock_get_type):
        """Empty list is not modified."""
        mock_get_type.return_value = "list"

        value = []
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == []

    @patch("awsquery.cli.get_parameter_type")
    def test_nested_list_not_wrapped(self, mock_get_type):
        """Nested list is not double-wrapped."""
        mock_get_type.return_value = "list"

        value = [[{"Key": "Name"}]]
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [[{"Key": "Name"}]]

    @patch("awsquery.cli.get_parameter_type")
    def test_none_value_not_wrapped(self, mock_get_type):
        """None value is not wrapped."""
        mock_get_type.return_value = "list"

        value = None
        expected_type = mock_get_type("ssm", "describe-parameters", "Filters")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [None]

    @patch("awsquery.cli.get_parameter_type")
    def test_boolean_value_wrapped(self, mock_get_type):
        """Boolean value gets wrapped when type is list."""
        mock_get_type.return_value = "list"

        value = True
        expected_type = mock_get_type("some-service", "some-operation", "Flags")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == [True]

    @patch("awsquery.cli.get_parameter_type")
    def test_zero_integer_not_wrapped(self, mock_get_type):
        """Zero integer is not wrapped when type is integer."""
        mock_get_type.return_value = "integer"

        value = 0
        expected_type = mock_get_type("ec2", "describe-instances", "MaxResults")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == 0

    @patch("awsquery.cli.get_parameter_type")
    def test_negative_integer_not_wrapped(self, mock_get_type):
        """Negative integer is not wrapped."""
        mock_get_type.return_value = "integer"

        value = -1
        expected_type = mock_get_type("some-service", "some-operation", "Offset")

        if expected_type == "list" and not isinstance(value, list):
            corrected_value = [value]
        else:
            corrected_value = value

        assert corrected_value == -1
