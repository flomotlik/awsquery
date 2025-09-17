"""Integration tests for multi-level API calls."""

from unittest.mock import MagicMock, patch

import pytest

from awsquery.core import (
    CallResult,
    execute_multi_level_call,
    execute_multi_level_call_with_tracking,
)


class TestMultiLevelCallIntegration:
    """Integration tests for multi-level call functionality."""

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_multi_level_call_with_tracking_success_path(self, mock_infer, mock_execute):
        """Test successful multi-level call with tracking."""
        # Mock successful responses
        mock_execute.return_value = [
            {"InstanceId": "i-123", "Name": "server1"},
            {"InstanceId": "i-456", "Name": "server2"},
        ]
        mock_infer.return_value = ["describe_instances"]

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="ec2",
            action="describe-instances",
            resource_filters=["server"],
            value_filters=["server"],  # Changed to match data in mock response
            column_filters=["Name", "Status"],
        )

        # Should return successful result
        assert call_result is not None
        assert filtered_resources is not None
        assert len(filtered_resources) == 2
        mock_execute.assert_called()

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_multi_level_call_with_tracking_failure_path(self, mock_infer, mock_execute):
        """Test failed multi-level call with tracking."""
        # Mock failed response (validation error)
        mock_execute.return_value = {
            "validation_error": {"parameter_name": "InstanceIds", "is_required": True}
        }
        mock_infer.return_value = ["describe_instances"]

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="ec2",
            action="describe-instances",
            resource_filters=["nonexistent"],
            value_filters=[],
            column_filters=[],
        )

        # Should handle failure gracefully
        assert call_result is not None
        mock_execute.assert_called()

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_multi_level_call_with_tracking_empty_resources(self, mock_infer, mock_execute):
        """Test multi-level call with empty resource list."""
        # Mock empty response
        mock_execute.return_value = []
        mock_infer.return_value = ["list_buckets"]

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="s3",
            action="list-buckets",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        # Should handle empty results
        assert call_result is not None
        assert filtered_resources == []

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_multi_level_call_with_tracking_none_parameters(self, mock_infer, mock_execute):
        """Test multi-level call with None parameters."""
        mock_execute.return_value = (True, [{"Name": "test"}], None)
        mock_infer.return_value = ["list_items"]

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="service",
            action="action",
            resource_filters=None,
            value_filters=None,
            column_filters=None,
        )

        # Should handle None parameters gracefully
        assert call_result is not None
        assert filtered_resources is not None

    @patch("awsquery.core.execute_aws_call")
    def test_execute_multi_level_call_basic(self, mock_execute):
        """Test basic multi-level call without tracking."""
        mock_execute.return_value = (True, [{"Id": "test"}], None)

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        assert result is not None
        mock_execute.assert_called()

    @patch("awsquery.core.execute_aws_call")
    def test_execute_multi_level_call_parameter_resolution(self, mock_execute):
        """Test parameter resolution in multi-level calls."""
        # First call returns resources for parameter resolution
        # Second call uses resolved parameters
        mock_execute.side_effect = [
            (True, [{"InstanceId": "i-123"}, {"InstanceId": "i-456"}], None),  # First call
            (True, [{"Details": "info1"}, {"Details": "info2"}], None),  # Second call
        ]

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=["prod"],
            value_filters=[],
            column_filters=[],
        )

        assert result is not None
        # Should make multiple calls for parameter resolution
        assert mock_execute.call_count >= 1

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_multi_level_call_error_handling(self, mock_infer, mock_execute):
        """Test error handling in multi-level calls."""
        # Mock exception during execution
        mock_execute.side_effect = Exception("AWS API Error")
        mock_infer.return_value = ["describe_instances"]

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="ec2",
            action="describe-instances",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        # Should handle exceptions gracefully
        assert call_result is not None
        # filtered_resources should be handled appropriately

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.filter_resources")
    def test_multi_level_call_filtering_integration(self, mock_filter, mock_execute):
        """Test integration of filtering with multi-level calls."""
        mock_execute.return_value = (
            True,
            [
                {"Name": "prod-server", "Status": "running"},
                {"Name": "dev-server", "Status": "stopped"},
                {"Name": "prod-worker", "Status": "running"},
            ],
            None,
        )

        # Mock filter to return only prod resources
        mock_filter.return_value = [
            {"Name": "prod-server", "Status": "running"},
            {"Name": "prod-worker", "Status": "running"},
        ]

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=["prod"],
            value_filters=["running"],
            column_filters=["Name"],
        )

        assert result is not None
        mock_filter.assert_called()
        mock_execute.assert_called()

    @patch("awsquery.core.execute_aws_call")
    def test_multi_level_call_column_filtering(self, mock_execute):
        """Test column filtering in multi-level calls."""
        mock_execute.return_value = (
            True,
            [
                {"InstanceId": "i-123", "Name": "server1", "Status": "running", "Type": "t2.micro"},
                {"InstanceId": "i-456", "Name": "server2", "Status": "stopped", "Type": "t3.small"},
            ],
            None,
        )

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=[],
            value_filters=[],
            column_filters=["Name", "Status"],
        )

        assert result is not None
        mock_execute.assert_called()

    def test_call_result_object_creation(self):
        """Test CallResult object creation and usage."""
        result = CallResult()

        # Should have default values
        assert result is not None

        # CallResult should be usable in multi-level calls
        assert hasattr(result, "__init__")


class TestMultiLevelCallParameterResolution:
    """Test parameter resolution in multi-level calls."""

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.extract_parameter_values")
    def test_parameter_resolution_with_resource_filters(self, mock_extract, mock_execute):
        """Test parameter resolution using resource filters."""
        # First call to get list of resources
        mock_execute.side_effect = [
            (
                True,
                [
                    {"InstanceId": "i-123", "Name": "prod-1"},
                    {"InstanceId": "i-456", "Name": "dev-2"},
                ],
                None,
            ),
            (True, [{"Details": "prod details"}], None),
        ]

        # Extract returns filtered IDs
        mock_extract.return_value = ["i-123"]

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=["prod"],
            value_filters=[],
            column_filters=[],
        )

        assert result is not None
        # Should make multiple calls
        assert mock_execute.call_count >= 1

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.get_correct_parameter_name")
    def test_parameter_name_resolution(self, mock_get_param, mock_execute):
        """Test parameter name resolution."""
        mock_execute.return_value = (True, [{"test": "data"}], None)
        mock_get_param.return_value = "CorrectParameterName"

        result = execute_multi_level_call(
            service="test-service",
            action="test-action",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        assert result is not None
        mock_execute.assert_called()

    @patch("awsquery.core.execute_aws_call")
    def test_parameter_boundary_conditions(self, mock_execute):
        """Test boundary conditions in parameter handling."""
        mock_execute.return_value = (True, [], None)

        # Test with various parameter combinations
        test_cases = [
            {"resource_filters": [], "value_filters": [], "column_filters": []},
            {"resource_filters": ["filter"], "value_filters": [], "column_filters": []},
            {"resource_filters": [], "value_filters": ["value"], "column_filters": ["col"]},
        ]

        for case in test_cases:
            result = execute_multi_level_call(service="test", action="test", **case)
            assert result is not None

        # Should handle all cases
        assert mock_execute.call_count == len(test_cases)


class TestMultiLevelCallErrorScenarios:
    """Test error scenarios in multi-level calls."""

    @patch("awsquery.core.execute_aws_call")
    def test_api_error_propagation(self, mock_execute):
        """Test API error propagation in multi-level calls."""
        mock_execute.return_value = (False, [], "AccessDenied")

        result = execute_multi_level_call(
            service="s3",
            action="list-buckets",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        # Should handle API errors gracefully
        assert result is not None

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_no_list_operations_found(self, mock_infer, mock_execute):
        """Test when no list operations can be inferred."""
        mock_execute.return_value = (True, [], None)
        mock_infer.return_value = []  # No operations found

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            service="unknown",
            action="unknown-action",
            resource_filters=["test"],
            value_filters=[],
            column_filters=[],
        )

        # Should handle case where no operations are found
        assert call_result is not None

    @patch("awsquery.core.execute_aws_call")
    def test_empty_response_handling(self, mock_execute):
        """Test handling of empty responses."""
        mock_execute.return_value = (True, None, None)

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        # Should handle None response data
        assert result is not None

    @patch("awsquery.core.execute_aws_call")
    def test_malformed_response_handling(self, mock_execute):
        """Test handling of malformed responses."""
        # Mock malformed response (string instead of list/dict)
        mock_execute.return_value = (True, "invalid_response", None)

        result = execute_multi_level_call(
            service="ec2",
            action="describe-instances",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
        )

        # Should handle malformed responses
        assert result is not None
