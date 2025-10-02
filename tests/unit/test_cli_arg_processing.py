"""Tests for CLI argument processing and helper functions."""

import argparse
import os
from unittest.mock import MagicMock, patch

import pytest

from awsquery.cli import (
    _enhanced_completion_validator,
    _extract_flag_and_value,
    _process_remaining_args,
    _process_remaining_args_after_separator,
    action_completer,
    service_completer,
)


class TestExtractFlagAndValue:

    def test_extract_region_flag_with_value(self):
        flags, consumed = _extract_flag_and_value(["--region", "us-east-1", "other"], 0)
        assert flags == ["--region", "us-east-1"]
        assert consumed == 2

    def test_extract_profile_flag_with_value(self):
        flags, consumed = _extract_flag_and_value(["--profile", "dev", "service"], 0)
        assert flags == ["--profile", "dev"]
        assert consumed == 2

    def test_extract_other_flag_no_value(self):
        flags, consumed = _extract_flag_and_value(["--debug", "service"], 0)
        assert flags == ["--debug"]
        assert consumed == 1

    def test_extract_region_flag_no_value(self):
        flags, consumed = _extract_flag_and_value(["--region"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_region_flag_dash_value(self):
        flags, consumed = _extract_flag_and_value(["--region", "--debug"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_region_flag_double_dash_value(self):
        flags, consumed = _extract_flag_and_value(["--region", "--"], 0)
        assert flags == ["--region"]
        assert consumed == 1

    def test_extract_profile_flag_no_next_arg(self):
        flags, consumed = _extract_flag_and_value(["--profile"], 0)
        assert flags == ["--profile"]
        assert consumed == 1

    def test_extract_normal_flag(self):
        flags, consumed = _extract_flag_and_value(["-d"], 0)
        assert flags == ["-d"]
        assert consumed == 1


class TestProcessRemainingArgsAfterSeparator:

    def test_process_no_flags(self):
        flags, non_flags = _process_remaining_args_after_separator(["filter1", "filter2"])
        assert flags == []
        assert non_flags == ["filter1", "filter2"]

    def test_process_debug_flag(self):
        flags, non_flags = _process_remaining_args_after_separator(["--debug", "filter1"])
        assert flags == ["--debug"]
        assert non_flags == ["filter1"]

    def test_process_region_flag_with_value(self):
        flags, non_flags = _process_remaining_args_after_separator(
            ["--region", "us-east-1", "filter"]
        )
        assert flags == ["--region", "us-east-1"]
        assert non_flags == ["filter"]

    def test_process_mixed_flags_and_args(self):
        args = ["filter1", "--debug", "filter2", "--json"]
        flags, non_flags = _process_remaining_args_after_separator(args)
        assert "--debug" in flags
        assert "--json" in flags
        assert non_flags == ["filter1", "filter2"]

    def test_process_profile_flag(self):
        flags, non_flags = _process_remaining_args_after_separator(["--profile", "dev", "service"])
        assert flags == ["--profile", "dev"]
        assert non_flags == ["service"]

    def test_process_keys_flag(self):
        flags, non_flags = _process_remaining_args_after_separator(["-k", "service"])
        assert flags == ["-k"]
        assert non_flags == ["service"]

    def test_process_empty_args(self):
        flags, non_flags = _process_remaining_args_after_separator([])
        assert flags == []
        assert non_flags == []

    def test_process_multiple_flags(self):
        args = ["-d", "-j", "--region", "us-west-2", "service"]
        flags, non_flags = _process_remaining_args_after_separator(args)
        assert "-d" in flags
        assert "-j" in flags
        assert "--region" in flags
        assert "us-west-2" in flags
        assert non_flags == ["service"]


class TestServiceCompleter:

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_service_completer_returns_services(self, mock_session_class):
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
        mock_session_class.side_effect = Exception("Botocore error")

        result = service_completer("", None)
        assert result == []

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {"AWS_PROFILE": "test"}, clear=True)
    def test_service_completer_preserves_profile(self, mock_session_class):
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_session_class.return_value = mock_session

        service_completer("", None)
        # Should restore AWS_PROFILE
        assert os.environ.get("AWS_PROFILE") == "test"


class TestActionCompleter:

    @patch("awsquery.cli.validate_readonly")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_returns_actions(self, mock_session_class, mock_validate):
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "RunInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)

        assert "describe-instances" in result
        assert "run-instances" not in result  # Unsafe operation is filtered out

    def test_action_completer_no_service(self):
        parsed_args = argparse.Namespace(service=None)
        result = action_completer("", parsed_args)
        assert result == []

    @patch("awsquery.cli.validate_readonly")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_with_prefix(self, mock_session_class, mock_validate):
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "RunInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("desc", parsed_args)

        # Only describe-instances should match "desc" prefix
        assert "describe-instances" in result
        assert "run-instances" not in result

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_exception(self, mock_session_class):

        mock_session_class.side_effect = Exception("Botocore error")

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)
        assert result == []

    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_service_not_available(self, mock_session_class):

        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["s3"]  # ec2 not available
        mock_session_class.return_value = mock_session

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)
        assert result == []

    @patch("awsquery.cli.validate_readonly")
    @patch("botocore.session.Session")
    @patch.dict("os.environ", {}, clear=True)
    def test_action_completer_security_policy_failure(self, mock_session_class, mock_validate):
        mock_session = MagicMock()
        mock_session.get_available_services.return_value = ["ec2"]
        mock_service_model = MagicMock()
        mock_service_model.operation_names = ["DescribeInstances", "CreateInstance"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_class.return_value = mock_session

        mock_validate.return_value = True

        parsed_args = argparse.Namespace(service="ec2")
        result = action_completer("", parsed_args)

        # Should include describe action but not create (fallback behavior)
        assert "describe-instances" in result


class TestActionCompleterEnhanced:

    def test_partial_string_match_middle(self):
        result = _enhanced_completion_validator("get-caller-identity", "caller")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "caller")
        assert result is False

    def test_partial_string_match_end(self):
        result = _enhanced_completion_validator("get-caller-identity", "identity")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "identity")
        assert result is False

    def test_split_match_basic(self):
        result = _enhanced_completion_validator("get-caller-identity", "call-ide")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "call-ide")
        assert result is False

    def test_split_match_multiple_parts(self):
        result = _enhanced_completion_validator("get-session-token", "ses-tok")
        assert result is True

        result = _enhanced_completion_validator("get-caller-identity", "ses-tok")
        assert result is False

    def test_split_match_partial_segments(self):
        result = _enhanced_completion_validator("get-caller-identity", "cal-iden")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "cal-iden")
        assert result is False

    def test_prefix_matching_priority(self):
        result = _enhanced_completion_validator("get-caller-identity", "get")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "get")
        assert result is True

        result = _enhanced_completion_validator("assume-role", "get")
        assert result is False

    def test_case_insensitive_matching(self):
        result = _enhanced_completion_validator("get-caller-identity", "caller")
        assert result is True

        result = _enhanced_completion_validator("get-caller-identity", "CALLER")
        assert result is True

        result = _enhanced_completion_validator("get-caller-identity", "CaLLer")
        assert result is True

        result = _enhanced_completion_validator("GET-CALLER-IDENTITY", "caller")
        assert result is True

    def test_empty_input_returns_true(self):
        result = _enhanced_completion_validator("get-caller-identity", "")
        assert result is True

        result = _enhanced_completion_validator("any-action", "")
        assert result is True

    def test_no_matches_returns_false(self):
        result = _enhanced_completion_validator("get-caller-identity", "xyz123")
        assert result is False

        result = _enhanced_completion_validator("get-session-token", "nonexistent")
        assert result is False

    def test_split_match_with_empty_parts(self):
        # Test split matching handles empty parts correctly (e.g., 'call--ide')
        result = _enhanced_completion_validator("get-caller-identity", "call--ide")
        assert result is True

        result = _enhanced_completion_validator("get-session-token", "call--ide")
        assert result is False

    def test_split_match_requires_multiple_parts(self):
        # Single part should use substring matching only
        result = _enhanced_completion_validator("get-caller-identity", "caller")
        assert result is True

        # Multi-part should use split matching
        result = _enhanced_completion_validator("get-caller-identity", "get-caller")
        assert result is True

        result = _enhanced_completion_validator("get-caller-identity", "caller-identity")
        assert result is True

    def test_action_completer_returns_all_operations(self):
        with patch("awsquery.cli.validate_readonly") as mock_validate, patch(
            "botocore.session.Session"
        ) as mock_session_class, patch.dict("os.environ", {}, clear=True):
            mock_session = MagicMock()
            mock_session.get_available_services.return_value = ["sts"]
            mock_service_model = MagicMock()
            mock_service_model.operation_names = ["GetCallerIdentity", "GetSessionToken"]
            mock_session.get_service_model.return_value = mock_service_model
            mock_session_class.return_value = mock_session
            mock_validate.return_value = True

            parsed_args = argparse.Namespace(service="sts")

            # Should return all operations regardless of prefix
            result_all = action_completer("", parsed_args)
            result_specific = action_completer("caller", parsed_args)
            result_nonmatch = action_completer("xyz123", parsed_args)

            # All should return the same complete list
            expected = ["get-caller-identity", "get-session-token"]
            assert result_all == expected
            assert result_specific == expected
            assert result_nonmatch == expected
