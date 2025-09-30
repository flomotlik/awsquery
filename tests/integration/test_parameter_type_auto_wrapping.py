"""Integration tests for parameter type validation and auto-wrapping.

This test suite verifies the end-to-end behavior of auto-wrapping single
dict values in lists when AWS expects list parameter types.
"""

import sys
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import main


class TestAutoWrappingIntegration:
    """Integration tests for auto-wrapping in main() function."""

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_ssm_filters_auto_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """SSM Filters parameter is auto-wrapped when single dict provided."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Parameters": [{"Name": "/test/param"}]}
        mock_flatten.return_value = [{"Name": "/test/param"}]
        mock_filter.return_value = [{"Name": "/test/param"}]
        mock_format.return_value = "Name: /test/param"
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "ssm",
            "describe-parameters",
            "-p",
            "Filters=Key=Type,Values=StringList",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "Filters" in parameters
        assert isinstance(parameters["Filters"], list)
        assert len(parameters["Filters"]) == 1
        assert isinstance(parameters["Filters"][0], dict)

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_list_parameter_not_double_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """List parameter that's already a list is not double-wrapped."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Instances": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "-p",
            "InstanceIds=i-123,i-456",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "InstanceIds" in parameters
        assert isinstance(parameters["InstanceIds"], list)
        assert parameters["InstanceIds"] == ["i-123", "i-456"]

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_string_parameter_not_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """String parameter is not wrapped in list."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Instances": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "string"

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "-p",
            "NextToken=abc123",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "NextToken" in parameters
        assert isinstance(parameters["NextToken"], str)
        assert parameters["NextToken"] == "abc123"

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_integer_parameter_not_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Integer parameter is not wrapped in list."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Instances": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "integer"

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "-p",
            "MaxResults=100",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "MaxResults" in parameters
        assert isinstance(parameters["MaxResults"], int)
        assert parameters["MaxResults"] == 100

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_multiple_parameters_with_mixed_types(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Multiple parameters with different types are handled correctly."""

        def get_type_side_effect(service, action, param_name, session=None):
            if param_name == "Filters":
                return "list"
            elif param_name == "MaxResults":
                return "integer"
            return None

        mock_get_type.side_effect = get_type_side_effect
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Parameters": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""

        sys.argv = [
            "awsquery",
            "ssm",
            "describe-parameters",
            "-p",
            "Filters=Key=Type,Values=String",
            "-p",
            "MaxResults=50",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert isinstance(parameters["Filters"], list)
        assert isinstance(parameters["MaxResults"], int)
        assert parameters["MaxResults"] == 50

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_unknown_parameter_type_not_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Parameter with unknown type (None) is not modified."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Resources": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = None

        sys.argv = [
            "awsquery",
            "cloudformation",
            "describe-stack-resources",
            "-p",
            "LogicalResourceId=WebServer",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "LogicalResourceId" in parameters
        assert parameters["LogicalResourceId"] == "WebServer"

    @patch("awsquery.utils.get_client")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_error_in_get_parameter_type_does_not_crash(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_client,
    ):
        """Error in get_parameter_type() doesn't crash the application."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Instances": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_client.side_effect = Exception("Service model error")

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "-p",
            "MaxResults=10",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "MaxResults" in parameters
        assert parameters["MaxResults"] == 10


class TestRealWorldAutoWrappingScenarios:
    """Test real-world AWS scenarios with auto-wrapping."""

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_cloudtrail_lookup_attributes(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Test CloudTrail LookupAttributes parameter is auto-wrapped."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Events": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "cloudtrail",
            "lookup-events",
            "-p",
            "LookupAttributes=AttributeKey=EventName,AttributeValue=CreateBucket",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "LookupAttributes" in parameters
        assert isinstance(parameters["LookupAttributes"], list)

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_ssm_parameter_filters_complex(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """SSM ParameterFilters with multiple filters works correctly."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Parameters": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "ssm",
            "describe-parameters",
            "-p",
            "ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu,2024;"
            "Key=Name,Option=Contains,Values=Amazon,Linux;",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "ParameterFilters" in parameters
        assert isinstance(parameters["ParameterFilters"], list)

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    def test_cloudformation_parameters_wrapped(
        self,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Test CloudFormation Parameters parameter is auto-wrapped."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Stacks": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "cloudformation",
            "create-stack",
            "-p",
            "Parameters=ParameterKey=Environment,ParameterValue=Production",
        ]

        try:
            main()
        except SystemExit:
            pass

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        parameters = call_args[1]["parameters"]

        assert "Parameters" in parameters
        assert isinstance(parameters["Parameters"], list)


class TestDebugOutput:
    """Test debug output for auto-wrapping."""

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    @patch("awsquery.cli.debug_print")
    def test_debug_output_shows_wrapping(
        self,
        mock_debug_print,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Debug output shows auto-wrapping information when needed."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Parameters": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "-p",
            "NextToken=abc123",
            "--debug",
        ]

        try:
            main()
        except SystemExit:
            pass

        debug_calls = [call[0][0] for call in mock_debug_print.call_args_list]
        wrapping_messages = [msg for msg in debug_calls if "Auto-wrapping" in msg]

        assert (
            len(wrapping_messages) > 0
        ), "Expected debug message about auto-wrapping for NextToken"

    @patch("awsquery.cli.get_parameter_type")
    @patch("awsquery.cli.flatten_response")
    @patch("awsquery.cli.filter_resources")
    @patch("awsquery.cli.format_table_output")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.validate_readonly")
    @patch("awsquery.cli.debug_print")
    def test_debug_output_shows_parameters_before_and_after(
        self,
        mock_debug_print,
        mock_validate,
        mock_session,
        mock_execute,
        mock_format,
        mock_filter,
        mock_flatten,
        mock_get_type,
    ):
        """Debug output shows parameters before and after type correction."""
        mock_validate.return_value = True
        mock_session.return_value = Mock()
        mock_execute.return_value = {"Parameters": []}
        mock_flatten.return_value = []
        mock_filter.return_value = []
        mock_format.return_value = ""
        mock_get_type.return_value = "list"

        sys.argv = [
            "awsquery",
            "ssm",
            "describe-parameters",
            "-p",
            "Filters=Key=Type,Values=String",
            "--debug",
        ]

        try:
            main()
        except SystemExit:
            pass

        debug_calls = [call[0][0] for call in mock_debug_print.call_args_list]

        before_messages = [msg for msg in debug_calls if "before type correction" in msg]
        after_messages = [msg for msg in debug_calls if "after type correction" in msg]

        assert len(before_messages) > 0, "Expected debug message before type correction"
        assert len(after_messages) > 0, "Expected debug message after type correction"
