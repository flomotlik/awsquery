"""Tests for CLI flag positioning, especially flags at the end of command.

This test suite ensures that CLI flags (-d, -j, -k, --region, --profile) work
correctly regardless of their position in the command line, as long as they
appear before the -- separator.

The fix uses parse_known_args() instead of parse_args() to properly handle
flags that appear after the service and action arguments without treating
them as unrecognized arguments.

Note: Flags appearing after -- are treated as column filters, which is the
correct and expected behavior.
"""

import sys
from unittest.mock import Mock, patch

import pytest

from src.awsquery.cli import main


@pytest.mark.unit
class TestFlagPositioning:
    """Test that CLI flags work regardless of their position in the command."""

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_debug_flag_at_end(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test that -d flag works when placed at the end of the command."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        # Test with -d at the end
        sys.argv = ["awsquery", "ec2", "describe-instances", "-d"]

        with patch("src.awsquery.cli.flatten_response", return_value=[]):
            with patch("src.awsquery.cli.filter_resources", return_value=[]):
                with patch("src.awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Debug should be enabled
                    from src.awsquery import utils

                    assert utils.debug_enabled is True

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_debug_flag_after_filters(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test that -d flag works when placed after value filters."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        # Test with -d after value filters
        sys.argv = ["awsquery", "ec2", "describe-instances", "prod", "-d"]

        with patch("src.awsquery.cli.flatten_response", return_value=[]):
            with patch("src.awsquery.cli.filter_resources", return_value=[]):
                with patch("src.awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Debug should be enabled
                    from src.awsquery import utils

                    assert utils.debug_enabled is True

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_json_flag_at_end(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test that -j flag works when placed at the end."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "-j"]

        with patch("src.awsquery.cli.flatten_response") as mock_flatten:
            with patch("src.awsquery.cli.filter_resources") as mock_filter:
                with patch("src.awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # JSON formatter should be called
                    mock_json.assert_called_once()

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_keys_flag_at_end(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test that -k flag works when placed at the end."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "-k"]

        with patch("src.awsquery.cli.execute_with_tracking") as mock_tracking:
            from src.awsquery.core import CallResult

            result = CallResult()
            result.final_success = True
            result.last_successful_response = [{"Instances": [{"InstanceId": "i-123"}]}]
            mock_tracking.return_value = result

            with patch("src.awsquery.cli.show_keys_from_result", return_value="  InstanceId"):
                with patch("builtins.print") as mock_print:
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Should have called tracking for keys mode
                    mock_tracking.assert_called_once()

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_region_flag_at_end(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test that --region flag works when placed at the end."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "--region", "us-west-2"]

        with patch("src.awsquery.cli.flatten_response", return_value=[]):
            with patch("src.awsquery.cli.filter_resources", return_value=[]):
                with patch("src.awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Session should be created with the region
                    mock_session.assert_called_once_with(region="us-west-2", profile=None)

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_multiple_flags_at_end(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test multiple flags at the end of command."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "--region", "eu-west-1", "-j", "-d"]

        with patch("src.awsquery.cli.flatten_response") as mock_flatten:
            with patch("src.awsquery.cli.filter_resources") as mock_filter:
                with patch("src.awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # All flags should work
                    mock_session.assert_called_once_with(region="eu-west-1", profile=None)
                    mock_json.assert_called_once()
                    from src.awsquery import utils

                    assert utils.debug_enabled is True

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_flags_mixed_with_filters(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test flags mixed with value and column filters."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [
            {"Instances": [{"InstanceId": "i-123", "State": {"Name": "running"}}]}
        ]
        mock_session.return_value = Mock()

        # Complex command with flags before the -- separator
        sys.argv = ["awsquery", "ec2", "describe-instances", "prod", "-d", "-j", "--", "InstanceId"]

        with patch("src.awsquery.cli.flatten_response") as mock_flatten:
            with patch("src.awsquery.cli.filter_resources") as mock_filter:
                with patch("src.awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_filter.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # Verify flags were recognized
                    from src.awsquery import utils

                    assert utils.debug_enabled is True
                    mock_json.assert_called_once()

                    # Verify filters were recognized
                    args = mock_filter.call_args[0]
                    assert "prod" in args[1]  # value_filters

                    # Verify column filter was recognized
                    json_args = mock_json.call_args[0]
                    assert "InstanceId" in json_args[1]  # column_filters
