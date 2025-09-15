"""Unit tests for keys mode display fix with multi-level calls."""

from unittest.mock import Mock, call, patch

import pytest

from src.awsquery.core import (
    CallResult,
    execute_multi_level_call_with_tracking,
    execute_with_tracking,
    show_keys_from_result,
)


@pytest.mark.unit
class TestCallResult:
    """Test CallResult class for tracking successful responses."""

    def test_call_result_initialization(self):
        """Test CallResult initializes with correct default values."""
        result = CallResult()

        assert result.successful_responses == []
        assert result.final_success is False
        assert result.last_successful_response is None
        assert result.error_messages == []

    def test_call_result_success_tracking(self):
        """Test CallResult tracks successful responses correctly."""
        result = CallResult()
        response1 = {"Instances": [{"InstanceId": "i-123"}]}
        response2 = {"Buckets": [{"Name": "test-bucket"}]}

        result.successful_responses.append(response1)
        result.successful_responses.append(response2)
        result.last_successful_response = response2
        result.final_success = True

        assert len(result.successful_responses) == 2
        assert result.last_successful_response == response2
        assert result.final_success is True

    def test_call_result_error_tracking(self):
        """Test CallResult tracks error messages correctly."""
        result = CallResult()

        result.error_messages.append("First error")
        result.error_messages.append("Second error")
        result.final_success = False

        assert len(result.error_messages) == 2
        assert "First error" in result.error_messages
        assert "Second error" in result.error_messages
        assert result.final_success is False


@pytest.mark.unit
class TestExecuteWithTracking:
    """Test execute_with_tracking function."""

    @patch("src.awsquery.core.execute_aws_call")
    def test_successful_call_tracking(self, mock_execute):
        """Test tracking of successful AWS call."""
        mock_response = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_execute.return_value = mock_response

        result = execute_with_tracking("ec2", "describe-instances")

        assert result.final_success is True
        assert result.last_successful_response == mock_response
        assert len(result.successful_responses) == 1
        assert result.successful_responses[0] == mock_response
        assert len(result.error_messages) == 0

    @patch("src.awsquery.core.execute_aws_call")
    def test_validation_error_tracking(self, mock_execute):
        """Test tracking of validation error response."""
        validation_response = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }
        mock_execute.return_value = validation_response

        result = execute_with_tracking("eks", "describe-cluster")

        assert result.final_success is False
        assert result.last_successful_response is None
        assert len(result.successful_responses) == 0
        assert len(result.error_messages) == 1
        assert "Validation error" in result.error_messages[0]

    @patch("src.awsquery.core.execute_aws_call")
    def test_exception_tracking(self, mock_execute):
        """Test tracking when execute_aws_call raises exception."""
        mock_execute.side_effect = Exception("AWS API error")

        result = execute_with_tracking("ec2", "describe-instances")

        assert result.final_success is False
        assert result.last_successful_response is None
        assert len(result.successful_responses) == 0
        assert len(result.error_messages) == 1
        assert "Call failed: AWS API error" in result.error_messages[0]

    @patch("src.awsquery.core.execute_aws_call")
    def test_tracking_with_session(self, mock_execute):
        """Test that session is passed through to execute_aws_call."""
        mock_response = [{"Buckets": []}]
        mock_execute.return_value = mock_response
        mock_session = Mock()

        result = execute_with_tracking("s3", "list-buckets", session=mock_session)

        mock_execute.assert_called_once_with("s3", "list-buckets", None, mock_session)
        assert result.final_success is True

    @patch("src.awsquery.core.execute_aws_call")
    def test_tracking_with_parameters(self, mock_execute):
        """Test that parameters are passed through to execute_aws_call."""
        mock_response = [{"Instances": []}]
        mock_execute.return_value = mock_response
        params = {"InstanceIds": ["i-123"]}

        result = execute_with_tracking("ec2", "describe-instances", parameters=params)

        mock_execute.assert_called_once_with("ec2", "describe-instances", params, None)
        assert result.final_success is True


@pytest.mark.unit
class TestShowKeysFromResult:
    """Test show_keys_from_result function."""

    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.formatters.extract_and_sort_keys")
    def test_show_keys_successful_result(self, mock_extract_keys, mock_flatten):
        """Test showing keys from successful call result."""
        result = CallResult()
        result.final_success = True
        result.last_successful_response = [
            {"Instances": [{"InstanceId": "i-123", "State": "running"}]}
        ]

        mock_flatten.return_value = [{"InstanceId": "i-123", "State": "running"}]
        mock_extract_keys.return_value = ["InstanceId", "State"]

        output = show_keys_from_result(result)

        expected = "  InstanceId\n  State"
        assert output == expected
        mock_flatten.assert_called_once_with(result.last_successful_response)
        mock_extract_keys.assert_called_once()

    def test_show_keys_failed_result(self):
        """Test showing keys from failed call result."""
        result = CallResult()
        result.final_success = False
        result.error_messages = ["Initial call failed", "List operation failed"]

        output = show_keys_from_result(result)

        assert "Error: No successful response to show keys from" in output
        assert "Initial call failed; List operation failed" in output

    def test_show_keys_failed_result_no_errors(self):
        """Test showing keys from failed result with no error messages."""
        result = CallResult()
        result.final_success = False

        output = show_keys_from_result(result)

        assert output == "Error: No successful response to show keys from"

    @patch("src.awsquery.formatters.flatten_response")
    def test_show_keys_empty_resources(self, mock_flatten):
        """Test showing keys when successful response has no resources."""
        result = CallResult()
        result.final_success = True
        result.last_successful_response = [{"ResponseMetadata": {"RequestId": "test"}}]

        mock_flatten.return_value = []

        output = show_keys_from_result(result)

        assert output == "Error: No data to extract keys from in successful response"


@pytest.mark.unit
class TestMultiLevelCallWithTracking:
    """Test execute_multi_level_call_with_tracking function."""

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    def test_successful_initial_call_tracking(self, mock_filter, mock_flatten, mock_execute):
        """Test tracking when initial call succeeds."""
        mock_response = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_execute.return_value = mock_response
        mock_flatten.return_value = [{"InstanceId": "i-123"}]
        mock_filter.return_value = [{"InstanceId": "i-123"}]

        call_result, resources = execute_multi_level_call_with_tracking(
            "ec2", "describe-instances", [], [], []
        )

        assert call_result.final_success is True
        assert call_result.last_successful_response == mock_response
        assert len(call_result.successful_responses) == 1
        assert len(resources) == 1
        assert resources[0]["InstanceId"] == "i-123"

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_multi_level_resolution_tracking(
        self, mock_get_param, mock_extract, mock_filter, mock_flatten, mock_infer, mock_execute
    ):
        """Test tracking through complete multi-level resolution."""
        # Setup validation error for initial call
        validation_error = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }

        # Setup successful list and final responses
        list_response = [{"Clusters": [{"ClusterName": "test-cluster"}]}]
        final_response = [{"Cluster": {"ClusterName": "test-cluster", "Status": "ACTIVE"}}]

        mock_execute.side_effect = [validation_error, list_response, final_response]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [
            [{"ClusterName": "test-cluster"}],  # List response
            [{"ClusterName": "test-cluster", "Status": "ACTIVE"}],  # Final response
        ]
        mock_filter.side_effect = [
            [{"ClusterName": "test-cluster"}],  # Filtered list
            [{"ClusterName": "test-cluster", "Status": "ACTIVE"}],  # Filtered final
        ]
        mock_extract.return_value = ["test-cluster"]
        mock_get_param.return_value = "ClusterName"

        call_result, resources = execute_multi_level_call_with_tracking(
            "eks", "describe-cluster", [], [], []
        )

        # Should track both list and final responses as successful
        assert call_result.final_success is True
        assert call_result.last_successful_response == final_response
        assert len(call_result.successful_responses) == 2
        assert call_result.successful_responses[0] == list_response
        assert call_result.successful_responses[1] == final_response
        assert len(resources) == 1

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    def test_failed_list_operation_tracking(self, mock_infer, mock_execute):
        """Test tracking when list operation fails."""
        validation_error = {
            "validation_error": {
                "parameter_name": "unknownParam",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }

        mock_execute.side_effect = [
            validation_error,  # Initial call fails
            Exception("List operation failed"),  # List operation fails
        ]
        mock_infer.return_value = ["list_unknown"]

        call_result, resources = execute_multi_level_call_with_tracking(
            "service", "describe-something", [], [], []
        )

        assert call_result.final_success is False
        assert call_result.last_successful_response is None
        assert len(call_result.successful_responses) == 0
        assert len(call_result.error_messages) >= 2
        assert any(
            "Could not find working list operation" in msg for msg in call_result.error_messages
        )
        assert len(resources) == 0

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    def test_no_parameter_values_tracking(
        self, mock_extract, mock_filter, mock_flatten, mock_infer, mock_execute
    ):
        """Test tracking when no parameter values can be extracted."""
        validation_error = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }

        list_response = [{"Clusters": [{"DifferentField": "value"}]}]

        mock_execute.side_effect = [validation_error, list_response]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.return_value = [{"DifferentField": "value"}]
        mock_filter.return_value = [{"DifferentField": "value"}]
        mock_extract.return_value = []  # No parameter values extracted

        call_result, resources = execute_multi_level_call_with_tracking(
            "eks", "describe-cluster", [], [], []
        )

        assert call_result.final_success is False
        assert len(call_result.successful_responses) == 1  # List call succeeded
        assert call_result.successful_responses[0] == list_response
        assert any("Could not extract parameter" in msg for msg in call_result.error_messages)
        assert len(resources) == 0

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_final_call_failure_tracking(
        self, mock_get_param, mock_extract, mock_filter, mock_flatten, mock_infer, mock_execute
    ):
        """Test tracking when final call fails after successful resolution."""
        validation_error = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }

        list_response = [{"Clusters": [{"ClusterName": "test-cluster"}]}]

        mock_execute.side_effect = [
            validation_error,  # Initial call
            list_response,  # List call succeeds
            Exception("Final call failed"),  # Final call fails
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.return_value = [{"ClusterName": "test-cluster"}]
        mock_filter.return_value = [{"ClusterName": "test-cluster"}]
        mock_extract.return_value = ["test-cluster"]
        mock_get_param.return_value = "ClusterName"

        call_result, resources = execute_multi_level_call_with_tracking(
            "eks", "describe-cluster", [], [], []
        )

        assert call_result.final_success is False
        assert len(call_result.successful_responses) == 1  # Only list call succeeded
        assert call_result.successful_responses[0] == list_response
        assert any("Final call failed" in msg for msg in call_result.error_messages)
        assert len(resources) == 0


@pytest.mark.unit
class TestKeysModeBehavior:
    """Test keys mode behavior with tracking."""

    @patch("src.awsquery.cli.execute_with_tracking")
    @patch("src.awsquery.cli.execute_multi_level_call_with_tracking")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_keys_mode_successful_initial_call(
        self, mock_create_session, mock_services, mock_policy, mock_multi_level, mock_tracking
    ):
        """Test keys mode when initial call succeeds."""
        # Setup mocks
        mock_services.return_value = ["ec2"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Setup successful initial call
        successful_result = CallResult()
        successful_result.final_success = True
        successful_result.last_successful_response = [{"Instances": [{"InstanceId": "i-123"}]}]

        mock_tracking.return_value = successful_result

        test_args = ["awsquery", "--keys", "ec2", "describe-instances"]

        with patch("sys.argv", test_args), patch(
            "src.awsquery.cli.show_keys_from_result"
        ) as mock_show_keys:

            mock_show_keys.return_value = "  InstanceId\n  State"

            from src.awsquery.cli import main

            try:
                main()
            except SystemExit:
                pass

            # Verify initial tracking call was made
            mock_tracking.assert_called_once()
            # Multi-level should not be called since initial call succeeded
            mock_multi_level.assert_not_called()

    @patch("src.awsquery.cli.execute_with_tracking")
    @patch("src.awsquery.cli.execute_multi_level_call_with_tracking")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_keys_mode_fallback_to_multi_level(
        self, mock_create_session, mock_services, mock_policy, mock_multi_level, mock_tracking
    ):
        """Test keys mode falls back to multi-level when initial call fails."""
        # Setup mocks
        mock_services.return_value = ["eks"]
        mock_policy.return_value = {"eks:DescribeCluster"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Setup failed initial call
        failed_result = CallResult()
        failed_result.final_success = False
        failed_result.error_messages = ["Initial call failed"]

        # Setup successful multi-level call
        successful_multi_result = CallResult()
        successful_multi_result.final_success = True
        successful_multi_result.last_successful_response = [{"Cluster": {"ClusterName": "test"}}]

        mock_tracking.return_value = failed_result
        mock_multi_level.return_value = (successful_multi_result, [])

        test_args = ["awsquery", "--keys", "eks", "describe-cluster"]

        with patch("sys.argv", test_args), patch(
            "src.awsquery.cli.show_keys_from_result"
        ) as mock_show_keys:

            mock_show_keys.return_value = "  ClusterName\n  Status"

            from src.awsquery.cli import main

            try:
                main()
            except SystemExit:
                pass

            # Verify both calls were made
            mock_tracking.assert_called_once()
            mock_multi_level.assert_called_once()

    def test_keys_extraction_from_last_successful_response(self):
        """Test that keys are extracted only from the last successful response."""
        result = CallResult()

        # Add multiple successful responses
        first_response = [{"Instances": [{"InstanceId": "i-123", "State": "running"}]}]
        second_response = [{"Buckets": [{"Name": "bucket1", "CreationDate": "2023-01-01"}]}]

        result.successful_responses.append(first_response)
        result.successful_responses.append(second_response)
        result.last_successful_response = second_response  # This should be used for keys
        result.final_success = True

        with patch("src.awsquery.formatters.flatten_response") as mock_flatten, patch(
            "src.awsquery.formatters.extract_and_sort_keys"
        ) as mock_extract:

            mock_flatten.return_value = [{"Name": "bucket1", "CreationDate": "2023-01-01"}]
            mock_extract.return_value = ["Name", "CreationDate"]

            output = show_keys_from_result(result)

            # Should only use the last successful response, not the first
            mock_flatten.assert_called_once_with(second_response)
            assert "Name" in output
            assert "CreationDate" in output


@pytest.mark.unit
class TestTrackingDebugOutput:
    """Test debug output for tracking functionality."""

    @patch("src.awsquery.core.execute_aws_call")
    def test_tracking_debug_output(self, mock_execute, capsys):
        """Test that tracking produces appropriate debug output."""
        from src.awsquery import utils

        # Enable debug mode
        original_debug = utils.debug_enabled
        utils.debug_enabled = True

        try:
            mock_response = [{"Instances": []}]
            mock_execute.return_value = mock_response

            execute_with_tracking("ec2", "describe-instances")

            # Verify debug output was generated
            captured = capsys.readouterr()
            assert "Tracking: Successful call to ec2.describe-instances" in captured.err

        finally:
            utils.debug_enabled = original_debug

    @patch("src.awsquery.core.execute_aws_call")
    def test_tracking_debug_failure(self, mock_execute, capsys):
        """Test debug output for tracking failures."""
        from src.awsquery import utils

        original_debug = utils.debug_enabled
        utils.debug_enabled = True

        try:
            mock_execute.side_effect = Exception("Test failure")

            execute_with_tracking("ec2", "describe-instances")

            # Verify failure debug output
            captured = capsys.readouterr()
            assert "Tracking: Failed call to ec2.describe-instances" in captured.err

        finally:
            utils.debug_enabled = original_debug
