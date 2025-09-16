"""Consolidated tests for CLI flag handling in all positions.

This test suite ensures that CLI flags (-d, -j, -k, --region, --profile) work
correctly regardless of their position in the command line, including after
the -- separator.
"""

import sys
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import main


class TestCLIFlagHandling:
    """Test that CLI flags work in all positions."""

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_debug_flag_positions(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test -d flag works in various positions."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-d", "ec2", "describe-instances"],  # Before service
            ["awsquery", "ec2", "-d", "describe-instances"],  # Between service and action
            ["awsquery", "ec2", "describe-instances", "-d"],  # After action
            ["awsquery", "ec2", "describe-instances", "prod", "-d"],  # After filters
            ["awsquery", "ec2", "describe-instances", "--", "Name", "-d"],  # After separator
            ["awsquery", "ec2", "describe-instances", "--", "-d", "Name"],  # Right after separator
        ]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    for argv in test_cases:
                        sys.argv = argv
                        # Reset debug mode
                        from awsquery import utils

                        utils.debug_enabled = False

                        try:
                            main()
                        except SystemExit:
                            pass

                        assert utils.debug_enabled is True, f"Debug not enabled for: {argv}"

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_json_flag_positions(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test -j flag works in various positions."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-j", "ec2", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "-j"],
            ["awsquery", "ec2", "describe-instances", "--", "InstanceId", "-j"],
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    for argv in test_cases:
                        sys.argv = argv
                        mock_json.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_json.assert_called_once()

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_keys_flag_positions(self, mock_validate, mock_load_policy, mock_execute, mock_session):
        """Test -k flag works in various positions."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_session.return_value = Mock()

        test_cases = [
            ["awsquery", "-k", "ec2", "describe-instances"],
            ["awsquery", "ec2", "describe-instances", "-k"],
            ["awsquery", "ec2", "describe-instances", "--", "Name", "-k"],
        ]

        with patch("awsquery.cli.execute_with_tracking") as mock_tracking:
            from awsquery.core import CallResult

            result = CallResult()
            result.final_success = True
            result.last_successful_response = [{"Instances": [{"InstanceId": "i-123"}]}]
            mock_tracking.return_value = result

            with patch("awsquery.cli.show_keys_from_result", return_value="  InstanceId"):
                with patch("builtins.print"):
                    for argv in test_cases:
                        sys.argv = argv
                        mock_tracking.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_tracking.assert_called_once()

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_region_profile_flags(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test --region and --profile flags in various positions."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = Mock()

        test_cases = [
            (
                ["awsquery", "--region", "us-west-2", "ec2", "describe-instances"],
                {"region": "us-west-2", "profile": None},
            ),
            (
                ["awsquery", "ec2", "describe-instances", "--region", "eu-west-1"],
                {"region": "eu-west-1", "profile": None},
            ),
            (
                ["awsquery", "ec2", "describe-instances", "--", "Name", "--region", "ap-south-1"],
                {"region": "ap-south-1", "profile": None},
            ),
            (
                ["awsquery", "--profile", "prod", "ec2", "describe-instances"],
                {"region": None, "profile": "prod"},
            ),
            (
                [
                    "awsquery",
                    "ec2",
                    "describe-instances",
                    "--profile",
                    "dev",
                    "--region",
                    "us-east-1",
                ],
                {"region": "us-east-1", "profile": "dev"},
            ),
        ]

        with patch("awsquery.cli.flatten_response", return_value=[]):
            with patch("awsquery.cli.filter_resources", return_value=[]):
                with patch("awsquery.cli.format_table_output", return_value=""):
                    for argv, expected in test_cases:
                        sys.argv = argv
                        mock_session.reset_mock()

                        try:
                            main()
                        except SystemExit:
                            pass

                        mock_session.assert_called_once_with(
                            region=expected["region"], profile=expected["profile"]
                        )

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_multiple_flags_after_separator(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test multiple flags work when placed after -- separator."""
        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_session.return_value = Mock()

        # Test all flags can appear after the separator
        sys.argv = [
            "awsquery",
            "ec2",
            "describe-instances",
            "--",
            "-j",  # JSON flag after separator
            "-d",  # Debug flag after separator
            "--region",
            "us-west-2",  # Region after separator
            "--profile",
            "prod",  # Profile after separator
            "InstanceId",  # Column filter mixed with flags
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [{"InstanceId": "i-123"}]
                    mock_filter.return_value = [{"InstanceId": "i-123"}]
                    mock_json.return_value = '{"InstanceId": "i-123"}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # All flags should be recognized
                    from awsquery import utils

                    assert utils.debug_enabled is True
                    mock_json.assert_called_once()
                    mock_session.assert_called_once_with(region="us-west-2", profile="prod")

                    # Column filter should still work
                    json_args = mock_json.call_args[0]
                    assert "InstanceId" in json_args[1]

    @patch("awsquery.cli.create_session")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    def test_flags_with_value_and_column_filters(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test flags work correctly with both value and column filters."""
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
            "-d",  # flag between filters
            "--",
            "InstanceId",
            "State.Name",  # column filters
            "-j",  # flag after column filters
        ]

        with patch("awsquery.cli.flatten_response") as mock_flatten:
            with patch("awsquery.cli.filter_resources") as mock_filter:
                with patch("awsquery.cli.format_json_output") as mock_json:
                    mock_flatten.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_filter.return_value = [
                        {"InstanceId": "i-123", "State": {"Name": "running"}}
                    ]
                    mock_json.return_value = '{"InstanceId": "i-123", "State": {"Name": "running"}}'

                    try:
                        main()
                    except SystemExit:
                        pass

                    # Verify value filters
                    filter_args = mock_filter.call_args[0]
                    assert "prod" in filter_args[1]
                    assert "running" in filter_args[1]

                    # Verify column filters
                    json_args = mock_json.call_args[0]
                    assert "InstanceId" in json_args[1]
                    assert "State.Name" in json_args[1]

                    # Verify flags
                    from awsquery import utils

                    assert utils.debug_enabled is True
                    mock_json.assert_called_once()
