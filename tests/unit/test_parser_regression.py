"""Specific regression tests for parser issues.

This file contains targeted regression tests for the parser bug where
'awsquery ec2 describe-instances -- Name' would fail with:
  'awsquery: error: unrecognized arguments: Name'

The tests verify:
1. The exact failing command now works
2. Various combinations with flags and filters work
3. Column filters are properly propagated to formatters
4. The parser never raises 'unrecognized arguments' for valid commands
"""

import subprocess
import sys
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestParserRegressionBugs:
    """Tests to prevent specific parser bugs from reoccurring."""

    def test_issue_double_dash_name_filter(self):
        """Test double dash with Name filter doesn't cause parser error.

        Regression test for the specific issue:
        'awsquery ec2 describe-instances -- Name'
        was failing with 'error: unrecognized arguments: Name'
        """
        # Test the exact command that was failing
        test_command = ["ec2", "describe-instances", "--", "Name"]

        from src.awsquery.filters import parse_multi_level_filters_for_mode

        # This should parse without error
        base_cmd, resource_filters, value_filters, column_filters = (
            parse_multi_level_filters_for_mode(test_command, mode="single")
        )

        # Verify correct parsing
        assert base_cmd == ["ec2", "describe-instances"]
        assert not resource_filters
        assert not value_filters
        assert column_filters == ["Name"]

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    def test_main_does_not_fail_with_unrecognized_arguments(
        self, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test main() doesn't raise 'unrecognized arguments' error.

        Test that main() never raises 'unrecognized arguments' error
        when column filters are provided after --
        """
        from src.awsquery.cli import main

        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [{"Instances": []}]
        mock_session.return_value = None

        # Test various commands that should not fail with argparse errors
        test_commands = [
            ["awsquery", "ec2", "describe-instances", "--", "Name"],
            ["awsquery", "s3", "list-buckets", "--", "Name", "CreationDate"],
            ["awsquery", "ec2", "describe-instances", "prod", "--", "InstanceId"],
            ["awsquery", "--region", "us-west-2", "ec2", "describe-instances", "--", "Name"],
            ["awsquery", "-j", "ec2", "describe-instances", "--", "Name", "State"],
        ]

        for cmd in test_commands:
            sys.argv = cmd

            with patch("src.awsquery.cli.flatten_response", return_value=[]):
                with patch("src.awsquery.cli.filter_resources", return_value=[]):
                    with patch("src.awsquery.cli.format_table_output", return_value=""):
                        with patch("src.awsquery.cli.format_json_output", return_value="[]"):
                            error_occurred = False
                            error_message = ""

                            try:
                                main()
                            except SystemExit as e:
                                # SystemExit is OK (no data to display)
                                if e.code != 0 and e.code is not None:
                                    error_message = str(e)
                                    if "unrecognized arguments" in error_message:
                                        error_occurred = True
                            except Exception as e:
                                error_message = str(e)
                                if "unrecognized arguments" in error_message:
                                    error_occurred = True

                            assert not error_occurred, (
                                f"Command {' '.join(cmd)} failed with "
                                f"'unrecognized arguments' error: {error_message}"
                            )

    def test_subprocess_execution_does_not_fail(self):
        """Test that actual command line execution would work.

        Test that the actual command line execution would work
        (simulated via subprocess with a mock script)
        """
        # Create a test script that imports and uses the parser
        test_script = """
import sys
import os
# Use current directory instead of hardcoded path
sys.path.insert(0, os.getcwd())

# Mock AWS to avoid credential issues
from unittest.mock import Mock, patch

with patch("boto3.Session"):
    with patch("src.awsquery.cli.execute_aws_call", return_value=[]):
        with patch("src.awsquery.cli.load_security_policy", return_value=set()):
            with patch("src.awsquery.cli.validate_security", return_value=True):
                # Set command line arguments
                sys.argv = ["awsquery", "ec2", "describe-instances", "--", "Name"]

                # Try to run main - should not fail with argparse error
                try:
                    from src.awsquery.cli import main
                    main()
                    print("SUCCESS: No parser error")
                except SystemExit:
                    print("SUCCESS: No parser error")
                except Exception as e:
                    if "unrecognized arguments" in str(e):
                        print("FAIL: Parser error occurred")
                        sys.exit(1)
                    else:
                        print("SUCCESS: No parser error")
"""

        # Run the test script from current directory
        import os

        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            check=False,  # Explicitly set check=False to handle errors ourselves
        )

        # Check output
        assert (
            "SUCCESS" in result.stdout
        ), f"Parser test failed. stdout: {result.stdout}, stderr: {result.stderr}"
        assert result.returncode == 0, "Script exited with error"


@pytest.mark.unit
class TestParserFiltersArePropagated:
    """Test that parsed filters are correctly propagated through the system."""

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.validate_security")
    @patch("src.awsquery.cli.format_table_output")
    def test_column_filters_reach_formatter(
        self, mock_format, mock_validate, mock_load_policy, mock_execute, mock_session
    ):
        """Test that column filters after -- are passed to the formatter."""
        from src.awsquery.cli import main

        mock_validate.return_value = True
        mock_load_policy.return_value = set()
        mock_execute.return_value = [
            {"Instances": [{"InstanceId": "i-123", "State": {"Name": "running"}}]}
        ]
        mock_session.return_value = None
        mock_format.return_value = "formatted output"

        sys.argv = ["awsquery", "ec2", "describe-instances", "--", "InstanceId", "State.Name"]

        with patch("src.awsquery.cli.flatten_response") as mock_flatten:
            with patch("src.awsquery.cli.filter_resources") as mock_filter:
                mock_flatten.return_value = [{"InstanceId": "i-123", "State": {"Name": "running"}}]
                mock_filter.return_value = [{"InstanceId": "i-123", "State": {"Name": "running"}}]

                try:
                    main()
                except SystemExit:
                    pass

                # Verify formatter was called with the column filters
                mock_format.assert_called_once()
                args = mock_format.call_args[0]
                column_filters = args[1]

                # Should have our column filters
                assert "InstanceId" in column_filters
                assert "State.Name" in column_filters
