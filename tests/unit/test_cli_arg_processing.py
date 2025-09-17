"""Tests for CLI argument processing and helper functions."""

import argparse
import os
from unittest.mock import MagicMock, patch

import pytest

from awsquery.cli import (
    _extract_flag_and_value,
    _extract_flags_from_args,
    _preserve_parsed_flags,
    _process_remaining_args,
    _process_remaining_args_after_separator,
    action_completer,
    service_completer,
)


class TestExtractFlagsFromArgs:
    """Test _extract_flags_from_args function."""

    def test_extract_no_flags(self):
        """Test extraction with no flags."""
        flags, non_flags = _extract_flags_from_args(["service", "action", "filter"])
        assert flags == []
        assert non_flags == ["service", "action", "filter"]

    def test_extract_single_flag_with_value(self):
        """Test extraction of single flag with value."""
        flags, non_flags = _extract_flags_from_args(["--region", "us-east-1", "service"])
        assert flags == ["--region", "us-east-1"]
        assert non_flags == ["service"]

    def test_extract_flag_without_value(self):
        """Test extraction of boolean flag."""
        flags, non_flags = _extract_flags_from_args(["--debug", "service", "action"])
        assert flags == ["--debug"]
        assert non_flags == ["service", "action"]

    def test_extract_multiple_flags(self):
        """Test extraction of multiple flags."""
        args = ["--region", "us-west-2", "--profile", "dev", "service"]
        flags, non_flags = _extract_flags_from_args(args)
        assert flags == ["--region", "us-west-2", "--profile", "dev"]
        assert non_flags == ["service"]

    def test_extract_mixed_flags_and_args(self):
        """Test mixed flags and arguments."""
        args = ["service", "--debug", "action", "--json", "filter"]
        flags, non_flags = _extract_flags_from_args(args)
        assert "--debug" in flags
        assert "--json" in flags
        assert non_flags == ["service", "action", "filter"]

    def test_extract_short_flags(self):
        """Test extraction of short flags."""
        flags, non_flags = _extract_flags_from_args(["-j", "-d", "service"])
        assert flags == ["-j", "-d"]
        assert non_flags == ["service"]

    def test_extract_profile_flag_no_value(self):
        """Test profile flag with no following value."""
        flags, non_flags = _extract_flags_from_args(["--profile", "service"])
        # Since "service" doesn't start with -, it's consumed as the profile value
        assert flags == ["--profile", "service"]
        assert non_flags == []

    def test_extract_profile_flag_with_dash_value(self):
        """Test profile flag followed by another flag."""
        flags, non_flags = _extract_flags_from_args(["--profile", "--debug", "service"])
        # --debug starts with -, so it's not consumed as profile value
        assert "--profile" in flags
        assert "--debug" in flags
        assert non_flags == ["service"]

    def test_extract_empty_args(self):
        """Test empty argument list."""
        flags, non_flags = _extract_flags_from_args([])
        assert flags == []
        assert non_flags == []

    def test_extract_keys_flag(self):
        """Test keys flag extraction."""
        flags, non_flags = _extract_flags_from_args(["service", "--keys", "action"])
        assert "--keys" in flags
        assert non_flags == ["service", "action"]


class TestExtractFlagAndValue:
    """Test _extract_flag_and_value function."""

    def test_extract_region_flag_with_value(self):
        """Test region flag with value."""
        flags, consumed = _extract_flag_and_value(["--region", "us-east-1", "other"], 0)
        assert flags == ["--region", "us-east-1"]
        assert consumed == 2

    def test_extract_profile_flag_with_value(self):
        """Test profile flag with value."""
        flags, consumed = _extract_flag_and_value(["--profile", "dev", "service"], 0)
        assert flags == ["--profile", "dev"]
        assert consumed == 2

    def test_extract_other_flag_no_value(self):
        """Test non-region/profile flag."""
        flags, consumed = _extract_flag_and_value(["--debug", "service"], 0)
        assert flags == ["--debug"]
        assert consumed == 1

    def test_extract_region_flag_no_value(self):
        """Test region flag at end of list."""
        flags, consumed = _extract_flag_and_value(["--region"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_region_flag_dash_value(self):
        """Test region flag followed by dash argument."""
        flags, consumed = _extract_flag_and_value(["--region", "--debug"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_region_flag_double_dash_value(self):
        """Test region flag followed by double dash."""
        flags, consumed = _extract_flag_and_value(["--region", "--"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_profile_flag_no_next_arg(self):
        """Test profile flag with no next argument."""
        flags, consumed = _extract_flag_and_value(["--profile"], 0)
        assert flags == ["--profile"]
        assert consumed == 1

    def test_extract_normal_flag(self):
        """Test flag that doesn't take values."""
        flags, consumed = _extract_flag_and_value(["-d"], 0)
        assert flags == ["-d"]
        assert consumed == 1


class TestPreserveParsedFlags:
    """Test _preserve_parsed_flags function."""

    def test_preserve_no_flags(self):
        """Test with no flags to preserve."""
        args = argparse.Namespace(debug=False)
        result = _preserve_parsed_flags(args)
        assert result == []

    def test_preserve_debug_flag(self):
        """Test preserving debug flag."""
        args = argparse.Namespace(debug=True)
        result = _preserve_parsed_flags(args)
        assert "-d" in result

    def test_preserve_json_flag(self):
        """Test preserving json flag."""
        args = argparse.Namespace(debug=False, json=True)
        result = _preserve_parsed_flags(args)
        assert "-j" in result
        assert "-d" not in result

    def test_preserve_keys_flag(self):
        """Test preserving keys flag."""
        args = argparse.Namespace(debug=False, keys=True)
        result = _preserve_parsed_flags(args)
        assert "-k" in result

    def test_preserve_region_flag(self):
        """Test preserving region flag with value."""
        args = argparse.Namespace(debug=False, region="us-west-2")
        result = _preserve_parsed_flags(args)
        assert "--region" in result
        assert "us-west-2" in result

    def test_preserve_profile_flag(self):
        """Test preserving profile flag with value."""
        args = argparse.Namespace(debug=False, profile="dev")
        result = _preserve_parsed_flags(args)
        assert "--profile" in result
        assert "dev" in result

    def test_preserve_multiple_flags(self):
        """Test preserving multiple flags."""
        args = argparse.Namespace(debug=True, json=True, region="us-east-1")
        result = _preserve_parsed_flags(args)
        assert "-d" in result
        assert "-j" in result
        assert "--region" in result
        assert "us-east-1" in result

    def test_preserve_no_region_if_none(self):
        """Test not preserving region if None."""
        args = argparse.Namespace(debug=False, region=None)
        result = _preserve_parsed_flags(args)
        assert "--region" not in result

    def test_preserve_missing_attributes(self):
        """Test handling missing attributes with getattr."""
        args = argparse.Namespace(debug=True)
        # Missing json, keys, region, profile attributes
        result = _preserve_parsed_flags(args)
        assert "-d" in result
        assert len([f for f in result if f.startswith("-")]) == 1


class TestProcessRemainingArgsAfterSeparator:
    """Test _process_remaining_args_after_separator function."""

    def test_process_no_flags(self):
        """Test processing with no flags."""
        flags, non_flags = _process_remaining_args_after_separator(["filter1", "filter2"])
        assert flags == []
        assert non_flags == ["filter1", "filter2"]

    def test_process_debug_flag(self):
        """Test processing debug flag."""
        flags, non_flags = _process_remaining_args_after_separator(["--debug", "filter1"])
        assert flags == ["--debug"]
        assert non_flags == ["filter1"]

    def test_process_region_flag_with_value(self):
        """Test processing region flag with value."""
        flags, non_flags = _process_remaining_args_after_separator(
            ["--region", "us-east-1", "filter"]
        )
        assert flags == ["--region", "us-east-1"]
        assert non_flags == ["filter"]

    def test_process_mixed_flags_and_args(self):
        """Test processing mixed flags and arguments."""
        args = ["filter1", "--debug", "filter2", "--json"]
        flags, non_flags = _process_remaining_args_after_separator(args)
        assert "--debug" in flags
        assert "--json" in flags
        assert non_flags == ["filter1", "filter2"]

    def test_process_profile_flag(self):
        """Test processing profile flag."""
        flags, non_flags = _process_remaining_args_after_separator(["--profile", "dev", "service"])
        assert flags == ["--profile", "dev"]
        assert non_flags == ["service"]

    def test_process_keys_flag(self):
        """Test processing keys flag."""
        flags, non_flags = _process_remaining_args_after_separator(["-k", "service"])
        assert flags == ["-k"]
        assert non_flags == ["service"]

    def test_process_empty_args(self):
        """Test empty argument list."""
        flags, non_flags = _process_remaining_args_after_separator([])
        assert flags == []
        assert non_flags == []

    def test_process_multiple_flags(self):
        """Test multiple flags."""
        args = ["-d", "-j", "--region", "us-west-2", "service"]
        flags, non_flags = _process_remaining_args_after_separator(args)
        assert "-d" in flags
        assert "-j" in flags
        assert "--region" in flags
        assert "us-west-2" in flags
        assert non_flags == ["service"]


class TestServiceCompleter:
    """Test service_completer function."""

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_service_completer_returns_services(self, mock_session_class):
        """Test service completer returns available services."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2", "s3", "lambda"]
        mock_session_class.return_value = mock_session

        result = service_completer("", None)
        assert "ec2" in result
        assert "s3" in result
        assert "lambda" in result

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_service_completer_with_prefix(self, mock_session_class):
        """Test service completer with prefix filtering."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2", "ecs", "s3"]
        mock_session_class.return_value = mock_session

        result = service_completer("ec", None)
        assert "ec2" in result
        assert "ecs" in result
        assert "s3" not in result  # Filtered out by prefix

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_service_completer_exception(self, mock_session_class):
        """Test service completer handles exceptions."""
        mock_session_class.side_effect = Exception("Botocore error")

        result = service_completer("", None)
        assert result == []

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {"AWS_PROFILE": "test"}, clear=True)
    def test_service_completer_preserves_profile(self, mock_session_class):
        """Test service completer preserves AWS_PROFILE."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_session_class.return_value = mock_session

        service_completer("", None)
        # Should restore AWS_PROFILE
        assert os.environ.get("AWS_PROFILE") == "test"


class TestActionCompleter:
    """Test action_completer function."""

    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_returns_actions(self, mock_session_class, mock_validate, mock_policy):
        """Test action completer returns available actions."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "RunInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)

        assert "describe-instances" in result
        assert "run-instances" in result

    def test_action_completer_no_service(self):
        """Test action completer with no service."""
        parsed_args = argparse.Namespace(service=None)
        result = action_completer("", parsed_args)
        assert result == []

    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_with_prefix(self, mock_session_class, mock_validate, mock_policy):
        """Test action completer with prefix filtering."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "RunInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        mock_policy.return_value = set()
        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("desc", parsed_args)

        # Only describe-instances should match "desc" prefix
        assert "describe-instances" in result
        assert "run-instances" not in result

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_exception(self, mock_session_class):
        """Test action completer handles exceptions."""
        mock_session_class.side_effect = Exception("Botocore error")

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)
        assert result == []

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_service_not_available(self, mock_session_class):
        """Test action completer with unavailable service."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["s3"]  # ec2 not available
        mock_session_class.return_value = mock_session

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)
        assert result == []

    @patch("awsquery.cli.load_security_policy")
    @patch("awsquery.cli.validate_security")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_security_policy_failure(
        self, mock_session_class, mock_validate, mock_policy
    ):
        """Test action completer when security policy loading fails."""
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "CreateInstance"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        # Policy loading fails
        mock_policy.side_effect = Exception("Policy error")
        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)

        # Should include describe action but not create (fallback behavior)
        assert "describe-instances" in result
