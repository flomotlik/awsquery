"""Test suite for messaging enhancements in AWS Query Tool."""

import datetime
import re
import sys
from io import StringIO
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from src.awsquery.core import execute_multi_level_call

# Import the functions under test
from src.awsquery.utils import debug_enabled, debug_print


@pytest.mark.unit
@pytest.mark.messaging
class TestEnhancedDebugPrint:
    def test_debug_print_disabled_no_output(self, debug_disabled, capsys):
        debug_print("This should not appear")

        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    @patch("src.awsquery.utils.debug_enabled", True)
    def test_debug_print_enabled_has_debug_prefix(self, capsys):
        debug_print("Test message")

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.err
        assert "Test message" in captured.err

    @patch("src.awsquery.utils.debug_enabled", True)
    def test_debug_print_enabled_has_timestamp(self, capsys):
        """Test debug_print includes timestamp when enabled."""
        debug_print("Test message")

        captured = capsys.readouterr()
        # Look for timestamp pattern: YYYY-MM-DD HH:MM:SS
        timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        assert re.search(timestamp_pattern, captured.err)

    @patch("src.awsquery.utils.debug_enabled", True)
    def test_debug_print_format_order(self, capsys):
        """Test debug_print output format: [DEBUG] TIMESTAMP MESSAGE."""
        debug_print("Test message")

        captured = capsys.readouterr()
        # Should match pattern: [DEBUG] YYYY-MM-DD HH:MM:SS Test message
        expected_pattern = r"\[DEBUG\] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} Test message"
        assert re.search(expected_pattern, captured.err)

    @patch("src.awsquery.utils.debug_enabled", True)
    def test_debug_print_multiple_args(self, capsys):
        """Test debug_print handles multiple arguments correctly."""
        debug_print("Message", 123, {"key": "value"})

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.err
        assert "Message" in captured.err
        assert "123" in captured.err
        assert "{'key': 'value'}" in captured.err

    @patch("src.awsquery.utils.debug_enabled", True)
    def test_debug_print_kwargs_preserved(self, capsys):
        """Test debug_print preserves keyword arguments like sep."""
        debug_print("A", "B", "C", sep="-")

        captured = capsys.readouterr()
        assert "A-B-C" in captured.err
        assert "[DEBUG]" in captured.err


@pytest.mark.unit
@pytest.mark.messaging
class TestMultiLevelUserMessages:
    """Test suite for user-friendly messages in multi-level operations."""

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    def test_no_multi_level_messages_for_successful_direct_call(
        self, mock_filter, mock_flatten, mock_execute, capsys
    ):
        """Test no multi-level messages when direct call succeeds."""
        mock_execute.return_value = [{"InstanceId": "i-123"}]
        mock_flatten.return_value = [{"InstanceId": "i-123"}]
        mock_filter.return_value = [{"InstanceId": "i-123"}]

        execute_multi_level_call("ec2", "describe-instances", [], [], [])

        captured = capsys.readouterr()
        # Should not see any "Resolving" or "Calling" messages
        assert "Resolving required parameter" not in captured.err
        assert "Calling" not in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_parameter_resolution_start_message(
        self,
        mock_get_param,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test 'Resolving required parameter' message appears."""
        # Setup validation error scenario
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "cluster1"}],
            [{"Cluster": {"Name": "cluster1"}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [[{"Name": "cluster1"}], [{"Name": "cluster1"}]]
        mock_filter.side_effect = [[{"Name": "cluster1"}], [{"Name": "cluster1"}]]
        mock_extract.return_value = ["cluster1"]
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Resolving required parameter 'clusterName'" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_list_operation_call_message(
        self,
        mock_get_param,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test 'Calling X to find available resources' message appears."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "cluster1"}],
            [{"Cluster": {"Name": "cluster1"}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [[{"Name": "cluster1"}], [{"Name": "cluster1"}]]
        mock_filter.side_effect = [[{"Name": "cluster1"}], [{"Name": "cluster1"}]]
        mock_extract.return_value = ["cluster1"]
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Calling list_clusters to find available resources..." in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_resources_found_count_message(
        self,
        mock_get_param,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test 'Found X resources matching filters' message with count."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        # Setup 5 resources found
        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": f"cluster{i}"} for i in range(1, 6)],  # 5 clusters
            [{"Cluster": {"Name": "cluster1"}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [
            [{"Name": f"cluster{i}"} for i in range(1, 6)],
            [{"Name": "cluster1"}],
        ]
        mock_filter.side_effect = [
            [{"Name": f"cluster{i}"} for i in range(1, 6)],
            [{"Name": "cluster1"}],
        ]
        mock_extract.return_value = [f"cluster{i}" for i in range(1, 6)]
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Found 5 resources matching filters" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_single_resource_using_message(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test 'Using: resource_name' message for single resource."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "test-cluster"}],
            [{"Cluster": {"Name": "test-cluster"}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [[{"Name": "test-cluster"}], [{"Name": "test-cluster"}]]
        mock_filter.side_effect = [[{"Name": "test-cluster"}], [{"Name": "test-cluster"}]]
        mock_extract.return_value = ["test-cluster"]
        mock_expects_list.return_value = False
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Using: test-cluster" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_multiple_resources_limited_to_10_items(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test resource list is limited to 10 items when showing multiple."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        # Generate 15 clusters to test limiting
        cluster_names = [f"cluster-{i:02d}" for i in range(1, 16)]

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": name} for name in cluster_names],
            [{"Cluster": {"Name": cluster_names[0]}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [
            [{"Name": name} for name in cluster_names],
            [{"Name": cluster_names[0]}],
        ]
        mock_filter.side_effect = [
            [{"Name": name} for name in cluster_names],
            [{"Name": cluster_names[0]}],
        ]
        mock_extract.return_value = cluster_names
        mock_expects_list.return_value = False
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        # Should show only first 10 clusters
        for i in range(1, 11):
            assert f"cluster-{i:02d}" in captured.err

        # Should not show clusters 11-15
        for i in range(11, 16):
            assert f"cluster-{i:02d}" not in captured.err

        # Should indicate total count
        assert "15" in captured.err
        assert "(showing first 10)" in captured.err or "... and 5 more" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_user_messages_not_debug_only(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        debug_disabled,
        capsys,
    ):
        """Test user-friendly messages appear even when debug is disabled."""
        # Debug is disabled via fixture

        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "test-cluster"}],
            [{"Cluster": {"Name": "test-cluster"}}],
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [[{"Name": "test-cluster"}], [{"Name": "test-cluster"}]]
        mock_filter.side_effect = [[{"Name": "test-cluster"}], [{"Name": "test-cluster"}]]
        mock_extract.return_value = ["test-cluster"]
        mock_expects_list.return_value = False
        mock_get_param.return_value = "ClusterName"

        execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        # These user messages should appear even with debug disabled
        assert "Resolving required parameter 'clusterName'" in captured.err
        assert "Calling list_clusters to find available resources..." in captured.err
        assert "Found 1 resources matching filters" in captured.err
        assert "Using: test-cluster" in captured.err

        # Debug messages should NOT appear
        assert "[DEBUG]" not in captured.err


@pytest.mark.unit
@pytest.mark.messaging
class TestUserMessageIntegration:
    """Integration tests for user messaging system."""

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_complete_multi_level_message_sequence(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test complete sequence of user messages in multi-level operation."""
        validation_error = {
            "parameter_name": "instanceId",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"InstanceId": f"i-{i}"} for i in range(1, 4)],  # 3 instances
            [{"Instance": {"InstanceId": "i-1"}}],
        ]
        mock_infer.return_value = ["describe_instances"]
        mock_flatten.side_effect = [
            [{"InstanceId": f"i-{i}"} for i in range(1, 4)],
            [{"InstanceId": "i-1"}],
        ]
        mock_filter.side_effect = [
            [{"InstanceId": f"i-{i}"} for i in range(1, 4)],
            [{"InstanceId": "i-1"}],
        ]
        mock_extract.return_value = [f"i-{i}" for i in range(1, 4)]
        mock_expects_list.return_value = False
        mock_get_param.return_value = "InstanceId"

        execute_multi_level_call("ec2", "describe-instance-attribute", [], [], [])

        captured = capsys.readouterr()

        # Verify message sequence appears in correct order
        lines = captured.err.strip().split("\n")

        # Find relevant message lines
        resolving_line = next(
            (i for i, line in enumerate(lines) if "Resolving required parameter" in line), -1
        )
        calling_line = next(
            (i for i, line in enumerate(lines) if "Calling describe_instances" in line), -1
        )
        found_line = next((i for i, line in enumerate(lines) if "Found 3 resources" in line), -1)
        multiple_line = next(
            (i for i, line in enumerate(lines) if "Multiple instanceId values" in line), -1
        )
        using_line = next(
            (i for i, line in enumerate(lines) if "Using first match: i-1" in line), -1
        )

        # Verify all messages appear
        assert resolving_line >= 0, "Missing 'Resolving required parameter' message"
        assert calling_line >= 0, "Missing 'Calling X to find resources' message"
        assert found_line >= 0, "Missing 'Found X resources' message"
        assert multiple_line >= 0, "Missing 'Multiple values found' message"
        assert using_line >= 0, "Missing 'Using first match' message"

        # Verify correct sequence
        assert resolving_line < calling_line, "Messages not in correct order"
        assert calling_line < found_line, "Messages not in correct order"
        assert found_line < multiple_line, "Messages not in correct order"
        assert multiple_line < using_line, "Messages not in correct order"

    def test_debug_and_user_messages_distinction(self, debug_mode, capsys):
        """Test that debug and user messages are clearly distinguished."""
        import src.awsquery.utils

        # Debug mode is enabled via fixture
        assert src.awsquery.utils.debug_enabled

        # Test debug message
        debug_print("This is a debug message")

        # Test user message (simulate)
        print("Resolving required parameter 'clusterName'", file=sys.stderr)

        captured = capsys.readouterr()

        lines = captured.err.strip().split("\n")

        # Debug line should have [DEBUG] prefix and timestamp
        debug_line = next((line for line in lines if "This is a debug message" in line), "")
        assert "[DEBUG]" in debug_line
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", debug_line)

        # User line should NOT have [DEBUG] prefix
        user_line = next((line for line in lines if "Resolving required parameter" in line), "")
        assert "[DEBUG]" not in user_line
        assert user_line == "Resolving required parameter 'clusterName'"
