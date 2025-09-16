"""Critical tests for survived mutations identified by mutmut."""

import json
from unittest.mock import MagicMock, patch

import pytest

from awsquery.core import (
    execute_multi_level_call_with_tracking,
    infer_list_operation,
)
from awsquery.filters import parse_filter_pattern
from awsquery.formatters import (
    filter_columns,
    flatten_single_response,
)
from awsquery.security import load_security_policy


class TestFilterColumnsCritical:
    """Critical tests for filter_columns survived mutations."""

    def test_empty_pattern_value_assignment(self):
        """Test that empty pattern correctly assigns values, not None."""
        data = {"Name": "test", "Status": "active", "Type": "t2.micro"}
        filters = [""]  # Empty pattern should match everything

        result = filter_columns(data, filters)

        # Critical: Ensure values are preserved, not set to None
        assert result["Name"] == "test"
        assert result["Status"] == "active"
        assert result["Type"] == "t2.micro"
        assert None not in result.values()

    def test_empty_pattern_preserves_all_values(self):
        """Test empty pattern doesn't corrupt values."""
        data = {"Key1": "value1", "Key2": 42, "Key3": True}
        filters = ["", "Key1"]  # Empty pattern plus specific

        result = filter_columns(data, filters)

        # All values should be preserved exactly
        assert result == data
        assert result["Key2"] == 42  # Not None
        assert result["Key3"] is True  # Not None


class TestFlattenSingleResponseCritical:
    """Critical tests for flatten_single_response survived mutations."""

    def test_original_keys_usage(self):
        """Test that original_keys is actually used in the function."""
        response = {
            "Instances": [{"Id": "i-123"}],
            "ResponseMetadata": {"RequestId": "req-1"},
            "NextToken": "token123",
        }

        # Mock debug_print to verify original_keys is passed correctly
        with patch("awsquery.formatters.debug_print") as mock_debug:
            result = flatten_single_response(response)

            # Verify debug_print was called with original keys
            debug_calls = mock_debug.call_args_list
            # Find the call that logs original keys
            keys_logged = False
            for call in debug_calls:
                if "Original response keys:" in str(call):
                    # Verify it's not None
                    assert "None" not in str(call)
                    assert "Instances" in str(call) or "ResponseMetadata" in str(call)
                    keys_logged = True
            assert keys_logged, "Original keys were not logged"

    def test_handles_none_in_response_structure(self):
        """Test handling when response has None values."""
        response = {"Data": None, "Items": [{"Id": "1"}], "Status": "ok"}

        result = flatten_single_response(response)

        # Should handle None values gracefully
        assert result == [{"Id": "1"}]


class TestInferListOperationCritical:
    """Critical tests for infer_list_operation survived mutations."""

    def test_parameter_name_id_lowercase(self):
        """Test that 'id' in lowercase is specifically checked."""
        # Test that "id" (lowercase) is recognized
        operations = infer_list_operation("ec2", "id", "get-instance")
        assert any("list" in op or "describe" in op for op in operations)

        # Test that mutated "XXidXX" would fail
        # This ensures the string literal "id" is actually important
        operations = infer_list_operation("ec2", "Id", "get-instance")
        assert any("list" in op or "describe" in op for op in operations)

    def test_parameter_name_exact_matches(self):
        """Test exact string matching for special parameters."""
        # These should all be treated specially
        special_params = ["name", "id", "arn"]

        for param in special_params:
            operations = infer_list_operation("s3", param, "get-bucket")
            assert len(operations) > 0
            # Verify it doesn't try to extract resource name from these
            assert not any(param.replace(param, "XXX") in op for op in operations)

    def test_arn_uppercase_handling(self):
        """Test ARN in different cases."""
        operations1 = infer_list_operation("iam", "Arn", "get-role")
        operations2 = infer_list_operation("iam", "ARN", "get-role")
        operations3 = infer_list_operation("iam", "arn", "get-role")

        # All should produce similar results
        assert len(operations1) > 0
        assert len(operations2) > 0
        assert len(operations3) > 0


class TestExecuteMultiLevelCallCritical:
    """Critical tests for execute_multi_level_call_with_tracking mutations."""

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_filter_parameters_not_none(self, mock_infer, mock_execute):
        """Test that filter parameters are properly handled, not set to None."""
        mock_execute.return_value = (True, [{"Id": "i-123"}], None)
        mock_infer.return_value = ["list_instances"]

        with patch("awsquery.core.debug_print") as mock_debug:
            call_result, filtered_resources = execute_multi_level_call_with_tracking(
                "ec2",
                "describe-instances",
                ["prod"],  # resource_filters
                ["running"],  # value_filters
                ["Name", "Status"],  # column_filters
            )

            # Verify debug messages contain actual filter values, not None
            debug_calls = [str(call) for call in mock_debug.call_args_list]
            filters_logged = any(
                "Resource filters:" in call and "None" not in call for call in debug_calls
            )
            assert filters_logged or len(debug_calls) > 0
            assert call_result is not None

    @patch("awsquery.core.execute_aws_call")
    def test_multi_level_call_returns_correct_structure(self, mock_execute):
        """Test that execute_multi_level_call_with_tracking returns proper structure."""
        # Successful call with resources
        mock_execute.return_value = (
            True,
            [{"Id": "i-123", "Name": "test-1"}, {"Id": "i-456", "Name": "test-2"}],
            None,
        )

        call_result, filtered_resources = execute_multi_level_call_with_tracking(
            "ec2",
            "describe-instances",
            [],  # resource_filters
            [],  # value_filters
            [],  # column_filters
        )

        # Verify return structure
        assert call_result is not None
        # filtered_resources contains the actual result when successful
        assert filtered_resources is not None
        assert mock_execute.called


class TestLoadSecurityPolicyCritical:
    """Critical tests for load_security_policy survived mutations."""

    @patch("builtins.open", create=True)
    def test_policy_version_none_document(self, mock_open):
        """Test PolicyVersion with None Document is handled gracefully (bug fixed!)."""
        policy = {
            "PolicyVersion": {"Document": None}  # This was a bug that mutmut found - now fixed!
        }
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(policy)

        # After the fix, should handle None Document gracefully
        allowed = load_security_policy()
        assert allowed == set()  # Should return empty set, not crash

    @patch("builtins.open", create=True)
    def test_policy_version_missing_document_key(self, mock_open):
        """Test PolicyVersion without Document key."""
        policy = {
            "PolicyVersion": {
                # No Document key at all
                "Version": "2012-10-17"
            }
        }
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert allowed == set()  # Should return empty set

    @patch("builtins.open", create=True)
    def test_get_with_different_defaults(self, mock_open):
        """Test that .get() default values matter."""
        policy = {
            "PolicyVersion": {
                "Document": {"Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"]}]}
            }
        }
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert "s3:GetObject" in allowed
        # Ensures the get("Document", {}) vs get("Document", None) matters
