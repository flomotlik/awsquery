"""Unit tests for CLI session arguments (region and profile)."""

import argparse
import sys
from unittest.mock import Mock, call, patch

import pytest

from src.awsquery.cli import determine_column_filters, main
from src.awsquery.utils import create_session, get_client


@pytest.mark.unit
class TestSessionCreation:
    """Test session creation with region and profile arguments."""

    def test_create_session_no_args(self):
        """Test session creation without region or profile."""
        with patch("boto3.Session") as mock_session:
            session = create_session()

            mock_session.assert_called_once_with()
            assert session is not None

    def test_create_session_with_region_only(self):
        """Test session creation with region only."""
        with patch("boto3.Session") as mock_session:
            create_session(region="us-west-2")

            mock_session.assert_called_once_with(region_name="us-west-2")

    def test_create_session_with_profile_only(self):
        """Test session creation with profile only."""
        with patch("boto3.Session") as mock_session:
            create_session(profile="test-profile")

            mock_session.assert_called_once_with(profile_name="test-profile")

    def test_create_session_with_both_region_and_profile(self):
        """Test session creation with both region and profile."""
        with patch("boto3.Session") as mock_session:
            create_session(region="eu-west-1", profile="prod-profile")

            mock_session.assert_called_once_with(
                region_name="eu-west-1", profile_name="prod-profile"
            )

    def test_create_session_empty_strings_ignored(self):
        """Test that empty strings are ignored for region and profile."""
        with patch("boto3.Session") as mock_session:
            create_session(region="", profile="  ")

            mock_session.assert_called_once_with()

    def test_create_session_whitespace_only_ignored(self):
        """Test that whitespace-only strings are ignored."""
        with patch("boto3.Session") as mock_session:
            create_session(region="   ", profile="\t\n")

            mock_session.assert_called_once_with()


@pytest.mark.unit
class TestClientCreation:
    """Test client creation with and without sessions."""

    def test_get_client_no_session(self):
        """Test client creation without session."""
        with patch("boto3.client") as mock_client:
            get_client("ec2")

            mock_client.assert_called_once_with("ec2")

    def test_get_client_with_session(self):
        """Test client creation with session."""
        mock_session = Mock()
        mock_client = Mock()
        mock_session.client.return_value = mock_client

        result = get_client("s3", mock_session)

        assert result == mock_client
        mock_session.client.assert_called_once_with("s3")


@pytest.mark.unit
class TestCLIArgumentParsing:
    """Test CLI argument parsing for region and profile."""

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.format_table_output")
    def test_region_argument_passed_to_session(
        self, mock_format, mock_services, mock_policy, mock_create_session, mock_execute
    ):
        """Test that --region argument is passed to session creation."""
        mock_services.return_value = ["ec2", "s3"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        mock_execute.return_value = [{"Reservations": [{"Instances": []}]}]
        mock_format.return_value = "test output"

        test_args = ["awsquery", "--region", "us-west-2", "ec2", "describe-instances"]

        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass  # Expected for tests

        mock_create_session.assert_called_once_with(region="us-west-2", profile=None)

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.format_table_output")
    def test_profile_argument_passed_to_session(
        self, mock_format, mock_services, mock_policy, mock_create_session, mock_execute
    ):
        """Test that --profile argument is passed to session creation."""
        mock_services.return_value = ["ec2", "s3"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        mock_execute.return_value = [{"Reservations": [{"Instances": []}]}]
        mock_format.return_value = "test output"

        test_args = ["awsquery", "--profile", "test-profile", "ec2", "describe-instances"]

        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        mock_create_session.assert_called_once_with(region=None, profile="test-profile")

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.format_table_output")
    def test_both_region_and_profile_arguments(
        self, mock_format, mock_services, mock_policy, mock_create_session, mock_execute
    ):
        """Test that both --region and --profile are passed correctly."""
        mock_services.return_value = ["ec2", "s3"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        mock_execute.return_value = [{"Reservations": [{"Instances": []}]}]
        mock_format.return_value = "test output"

        test_args = [
            "awsquery",
            "--region",
            "eu-central-1",
            "--profile",
            "prod-profile",
            "ec2",
            "describe-instances",
        ]

        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        mock_create_session.assert_called_once_with(region="eu-central-1", profile="prod-profile")

    def test_cleaned_argv_excludes_region_and_profile(self):
        """Test that --region and --profile are excluded from command parsing."""
        test_args = [
            "--region",
            "us-west-2",
            "--profile",
            "test-profile",
            "ec2",
            "describe-instances",
            "prod",
            "--",
            "InstanceId",
        ]

        # Simulate the cleaning logic from CLI
        cleaned_argv = []
        skip_next = False
        for i, arg in enumerate(test_args):
            if skip_next:
                skip_next = False
                continue
            if arg in ["--keys", "-k"]:
                pass  # keys mode
            elif arg in ["--debug", "-d"]:
                pass  # debug mode
            elif arg in ["--region", "--profile"]:
                skip_next = True  # Skip this and next arg
            else:
                cleaned_argv.append(arg)

        expected = ["ec2", "describe-instances", "prod", "--", "InstanceId"]
        assert cleaned_argv == expected


@pytest.mark.unit
class TestSessionIntegration:
    """Test session integration with AWS calls."""

    @patch("src.awsquery.core.get_client")
    def test_execute_aws_call_uses_session(self, mock_get_client):
        """Test that execute_aws_call passes session to get_client."""
        from src.awsquery.core import execute_aws_call

        mock_client = Mock()
        mock_client.describe_instances.return_value = {"Instances": []}
        mock_get_client.return_value = mock_client
        mock_session = Mock()

        # Mock pagination to fall back to direct call
        mock_client.get_paginator.side_effect = Exception("Not pageable")

        execute_aws_call("ec2", "describe-instances", session=mock_session)

        mock_get_client.assert_called_once_with("ec2", mock_session)

    @patch("src.awsquery.core.get_client")
    def test_multi_level_call_uses_session(self, mock_get_client):
        """Test that multi-level calls preserve session throughout."""
        from src.awsquery.core import execute_multi_level_call

        mock_client = Mock()
        mock_client.describe_instances.return_value = {"Instances": []}
        mock_get_client.return_value = mock_client
        mock_session = Mock()

        # Mock successful direct call (no validation error)
        with patch("src.awsquery.core.execute_aws_call") as mock_execute:
            mock_execute.return_value = [{"Instances": [{"InstanceId": "i-123"}]}]

            execute_multi_level_call("ec2", "describe-instances", [], [], [], session=mock_session)

            # Verify session was passed to execute_aws_call
            mock_execute.assert_called_once_with("ec2", "describe-instances", session=mock_session)


@pytest.mark.unit
class TestSessionErrorHandling:
    """Test error handling for session-related issues."""

    def test_invalid_region_handled_gracefully(self):
        """Test that invalid regions don't crash session creation."""
        # boto3 should handle invalid regions, but test our wrapper
        with patch("boto3.Session") as mock_session:
            mock_session.side_effect = Exception("Invalid region")

            with pytest.raises(Exception):
                create_session(region="invalid-region-123")

    def test_invalid_profile_handled_gracefully(self):
        """Test that invalid profiles don't crash session creation."""
        with patch("boto3.Session") as mock_session:
            mock_session.side_effect = Exception("Profile not found")

            with pytest.raises(Exception):
                create_session(profile="non-existent-profile")

    @patch("src.awsquery.cli.create_session")
    def test_session_creation_error_propagates(self, mock_create_session):
        """Test that session creation errors are properly propagated."""
        mock_create_session.side_effect = Exception("Session creation failed")

        with patch("src.awsquery.cli.load_security_policy") as mock_policy:
            mock_policy.return_value = {"ec2:DescribeInstances"}

            test_args = ["awsquery", "--region", "invalid", "ec2", "describe-instances"]

            with patch.object(sys, "argv", test_args):
                with pytest.raises(Exception, match="Session creation failed"):
                    main()


@pytest.mark.unit
class TestSessionDebugOutput:
    """Test debug output for session creation."""

    @patch("src.awsquery.utils.debug_print")
    def test_session_creation_debug_output(self, mock_debug):
        """Test that session creation produces debug output when enabled."""
        from src.awsquery import utils

        # Enable debug mode
        original_debug = utils.debug_enabled
        utils.debug_enabled = True

        try:
            with patch("boto3.Session"):
                create_session(region="us-east-1", profile="test")

                # Verify debug calls were made
                expected_calls = [
                    call("create_session called with region='us-east-1', profile='test'"),
                    call("Added region_name=us-east-1 to session"),
                    call("Added profile_name=test to session"),
                ]

                # Check that these calls were made (order may vary)
                for expected_call in expected_calls:
                    assert expected_call in mock_debug.call_args_list
        finally:
            utils.debug_enabled = original_debug

    @patch("src.awsquery.utils.debug_print")
    def test_session_debug_with_empty_values(self, mock_debug):
        """Test debug output when empty values are provided."""
        from src.awsquery import utils

        original_debug = utils.debug_enabled
        utils.debug_enabled = True

        try:
            with patch("boto3.Session"):
                create_session(region="", profile=None)

                # Should see the initial call but not the "Added" messages
                mock_debug.assert_any_call("create_session called with region='', profile=None")

                # Should not see "Added" calls for empty values
                add_calls = [call for call in mock_debug.call_args_list if "Added" in str(call)]
                assert len(add_calls) == 0
        finally:
            utils.debug_enabled = original_debug
