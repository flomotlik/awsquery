"""Edge case tests for security validation."""

import json
import tempfile
from unittest.mock import mock_open, patch

import pytest

from awsquery.security import is_readonly_operation, validate_readonly


class TestReadOnlyEdgeCases:
    """Test edge cases for read-only operation detection."""

    def test_empty_operation(self):
        """Test with empty operation string."""
        assert not is_readonly_operation("")

    def test_none_operation(self):
        """Test with None operation."""
        with pytest.raises((TypeError, AttributeError)):
            is_readonly_operation(None)

    def test_mixed_case_operations(self):
        """Test operations with mixed case."""
        # PascalCase should work
        assert is_readonly_operation("DescribeInstances")
        assert is_readonly_operation("ListBuckets")
        assert is_readonly_operation("GetObject")

        # kebab-case should work
        assert is_readonly_operation("describe-instances")
        assert is_readonly_operation("list-buckets")
        assert is_readonly_operation("get-object")

        # camelCase might not work (starts with lowercase)
        assert not is_readonly_operation("describeInstances")

    def test_operations_with_numbers(self):
        """Test operations containing numbers."""
        assert is_readonly_operation("GetObjectV2")
        assert is_readonly_operation("describe-instances-v2")
        assert not is_readonly_operation("v2-describe-instances")

    def test_operations_with_special_chars(self):
        """Test operations with special characters."""
        assert is_readonly_operation("Get-Object")
        assert is_readonly_operation("Get_Object")
        assert is_readonly_operation("Get.Object")

    def test_very_long_operation_names(self):
        """Test with very long operation names."""
        long_op = "Describe" + "A" * 100 + "Resource"
        assert is_readonly_operation(long_op)

        long_unsafe_op = "Create" + "A" * 100 + "Resource"
        assert not is_readonly_operation(long_unsafe_op)


class TestValidateReadonlyEdgeCases:
    """Test edge cases for validate_readonly function."""

    def test_with_allow_unsafe_flag(self):
        """Test that allow_unsafe bypasses all checks."""
        # Should allow everything
        assert validate_readonly("ec2", "terminate-instances", allow_unsafe=True)
        assert validate_readonly("s3", "delete-bucket", allow_unsafe=True)
        assert validate_readonly("iam", "delete-user", allow_unsafe=True)
        assert validate_readonly("", "", allow_unsafe=True)

    @patch("awsquery.security.prompt_unsafe_operation")
    def test_prompt_called_for_unsafe(self, mock_prompt):
        """Test that prompt is called for unsafe operations."""
        mock_prompt.return_value = True

        result = validate_readonly("ec2", "terminate-instances", allow_unsafe=False)
        assert result is True
        mock_prompt.assert_called_once_with("ec2", "terminate-instances")

    @patch("awsquery.security.prompt_unsafe_operation")
    def test_prompt_not_called_for_safe(self, mock_prompt):
        """Test that prompt is not called for safe operations."""
        result = validate_readonly("ec2", "describe-instances", allow_unsafe=False)
        assert result is True
        mock_prompt.assert_not_called()

    def test_empty_service_or_action(self):
        """Test with empty service or action strings."""
        # Empty strings should be considered unsafe
        assert not is_readonly_operation("")

        # With allow_unsafe, should still work
        assert validate_readonly("", "", allow_unsafe=True)

    def test_whitespace_in_names(self):
        """Test with whitespace in service/action names."""
        assert not is_readonly_operation("  describe-instances  ")
        assert not is_readonly_operation("describe instances")
        assert not is_readonly_operation("describe\tinstances")

    @patch("builtins.input")
    def test_interactive_prompt_loop(self, mock_input):
        """Test interactive prompt with invalid responses."""
        # Mock the actual input function to return invalid then valid
        mock_input.side_effect = ["maybe", "perhaps", "yes"]

        # Call prompt directly
        from awsquery.security import prompt_unsafe_operation

        result = prompt_unsafe_operation("ec2", "terminate-instances")
        assert result is True
        assert mock_input.call_count == 3

    def test_batch_operations(self):
        """Test batch operations are detected as readonly."""
        batch_ops = [
            "BatchGet",
            "BatchDescribe",
            "batch-get",
            "batch-describe",
            "BatchGetItem",
            "batch-get-item",
        ]

        for op in batch_ops:
            assert is_readonly_operation(op), f"{op} should be readonly"

    def test_scan_and_query_operations(self):
        """Test scan and query operations are detected as readonly."""
        # Note: lowercase operations won't match as they don't follow AWS naming
        ops = ["Scan", "Query", "ScanTable", "QueryIndex", "scan-table", "query-index"]

        for op in ops:
            assert is_readonly_operation(op), f"{op} should be readonly"


class TestCompatibility:
    """Test compatibility functions."""

    def test_action_to_policy_format_legacy(self):
        """Test action_to_policy_format function exists for compatibility."""
        from awsquery.security import action_to_policy_format

        # Test PascalCase conversion
        assert action_to_policy_format("describe-instances") == "DescribeInstances"
        assert action_to_policy_format("get-bucket-policy") == "GetBucketPolicy"
        assert action_to_policy_format("list-objects-v2") == "ListObjectsV2"
        assert action_to_policy_format("DescribeInstances") == "DescribeInstances"

    def test_action_to_policy_format(self):
        """Test action format conversion."""
        from awsquery.security import action_to_policy_format

        assert action_to_policy_format("describe-instances") == "DescribeInstances"
        assert action_to_policy_format("list-buckets") == "ListBuckets"
        assert action_to_policy_format("get-object-acl") == "GetObjectAcl"
        assert action_to_policy_format("DescribeInstances") == "DescribeInstances"


class TestGetServiceValidOperations:
    """Test get_service_valid_operations function."""

    def test_filters_operations(self):
        """Test that operations are filtered by readonly status."""
        from awsquery.security import get_service_valid_operations

        operations = [
            "DescribeInstances",
            "RunInstances",
            "TerminateInstances",
            "ListBuckets",
            "CreateBucket",
            "DeleteBucket",
            "GetObject",
            "PutObject",
            "DeleteObject",
        ]

        valid = get_service_valid_operations("ec2", operations)

        # Should include read operations
        assert "DescribeInstances" in valid
        assert "ListBuckets" in valid
        assert "GetObject" in valid

        # Should exclude write operations
        assert "RunInstances" not in valid
        assert "TerminateInstances" not in valid
        assert "CreateBucket" not in valid
        assert "DeleteBucket" not in valid
        assert "PutObject" not in valid
        assert "DeleteObject" not in valid

    def test_handles_various_formats(self):
        """Test that it handles various operation name formats."""
        from awsquery.security import get_service_valid_operations

        operations = [
            "describe-instances",  # kebab-case
            "DescribeVolumes",  # PascalCase
            "list_buckets",  # snake_case (shouldn't match)
            "get-object",  # kebab-case
            "terminate-instances",  # unsafe kebab
            "CreateStack",  # unsafe Pascal
        ]

        valid = get_service_valid_operations("ec2", operations)

        assert "describe-instances" in valid
        assert "DescribeVolumes" in valid
        assert "get-object" in valid
        assert "list_buckets" not in valid  # wrong format
        assert "terminate-instances" not in valid
        assert "CreateStack" not in valid
