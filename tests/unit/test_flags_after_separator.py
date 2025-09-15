"""Tests for CLI flags working after -- separator.

Users should be able to put flags like -d, -j, -k anywhere in the command,
including after the -- separator. The -- separator should only affect
non-flag arguments (which become column filters).
"""

import sys
from unittest.mock import Mock, patch

import pytest

from src.awsquery.cli import main


@pytest.mark.unit
class TestFlagsAfterSeparator:
    """Test that CLI flags work even after -- separator."""

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_debug_flag_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test that -d flag works when placed after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        # Test with -d after --
        sys.argv = ["awsquery", "ec2", "describe-instances", "--", "Name", "-d"]

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
    def test_json_flag_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test that -j flag works when placed after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "--", "InstanceId", "-j"]

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
                    # Column filter should still work
                    args = mock_json.call_args[0]
                    assert "InstanceId" in args[1]

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_region_flag_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test that --region flag works when placed after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        sys.argv = ["awsquery", "ec2", "describe-instances", "--", "Name", "--region", "eu-west-1"]

        with patch("src.awsquery.cli.flatten_response", return_value=[]):
            with patch("src.awsquery.cli.filter_resources", return_value=[]):
                with patch("src.awsquery.cli.format_table_output", return_value=""):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Session should be created with the region
                    mock_session.assert_called_once_with(region="eu-west-1", profile=None)

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_mixed_flags_and_columns_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test mixed flags and column filters after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [
            {"Instances": [{"InstanceId": "i-123", "State": {"Name": "running"}}]}
        ]
        mock_session.return_value = Mock()

        # Complex case: column filters and flags mixed after --
        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "--",
            "InstanceId",
            "-d",
            "State.Name",
            "-j",
        ]

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

                    # All flags should work
                    from src.awsquery import utils

                    assert utils.debug_enabled is True
                    mock_json.assert_called_once()

                    # Column filters should still work
                    args = mock_json.call_args[0]
                    column_filters = args[1]
                    assert "InstanceId" in column_filters
                    assert "State.Name" in column_filters

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_all_flags_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test all flags placed after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "--",
            "-j",
            "-d",
            "--region",
            "us-west-2",
            "--profile",
            "prod",
        ]

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

                    # All flags should be recognized
                    from src.awsquery import utils

                    assert utils.debug_enabled is True
                    mock_json.assert_called_once()
                    mock_session.assert_called_once_with(region="us-west-2", profile="prod")

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_value_filters_with_flags_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test value filters before -- and flags after."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [
            {"Instances": [{"InstanceId": "i-123", "State": {"Name": "running"}}]}
        ]
        mock_session.return_value = Mock()

        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "prod",
            "running",  # value filters
            "--",
            "InstanceId",
            "-d",
            "State.Name",  # column filters and flag
        ]

        with patch("src.awsquery.cli.flatten_response") as mock_flatten:
            with patch("src.awsquery.cli.filter_resources") as mock_filter:
                with patch("src.awsquery.cli.format_table_output") as mock_format:
                    mock_flatten.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_filter.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_format.return_value = ""

                    try:
                        main()
                    except SystemExit:
                        pass

                    # Debug should be enabled
                    from src.awsquery import utils

                    assert utils.debug_enabled is True

                    # Value filters should be recognized
                    filter_args = mock_filter.call_args[0]
                    value_filters = filter_args[1]
                    assert "prod" in value_filters
                    assert "running" in value_filters

                    # Column filters should work
                    format_args = mock_format.call_args[0]
                    column_filters = format_args[1]
                    assert "InstanceId" in column_filters
                    assert "State.Name" in column_filters
