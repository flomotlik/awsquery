"""Test security validation."""

from unittest.mock import MagicMock, patch

import pytest

from awsquery.security import (
    action_to_policy_format,
    get_service_valid_operations,
    is_readonly_operation,
    prompt_unsafe_operation,
    validate_readonly,
)


class TestReadOnlyOperations:
    """Test read-only operation detection."""

    def test_common_readonly_prefixes(self):
        """Test that common read-only prefixes are detected."""
        readonly_ops = [
            "describe-instances",
            "list-buckets",
            "get-object",
            "DescribeInstances",
            "ListBuckets",
            "GetObject",
            "query-table",
            "scan-table",
            "search-resources",
            "batch-get-item",
            "view-dashboard",
            "lookup-records",
            "read-data",
            "check-status",
            "validate-policy",
            "test-connection",
        ]

        for op in readonly_ops:
            assert is_readonly_operation(op) is True, f"{op} should be read-only"

    def test_unsafe_operations(self):
        """Test that unsafe operations are detected."""
        unsafe_ops = [
            "run-instances",
            "terminate-instances",
            "delete-bucket",
            "put-object",
            "create-stack",
            "update-stack",
            "delete-stack",
            "modify-db-instance",
            "CreateStack",
            "UpdateStack",
            "DeleteStack",
        ]

        for op in unsafe_ops:
            assert is_readonly_operation(op) is False, f"{op} should not be read-only"

    def test_kebab_to_pascal_conversion(self):
        """Test kebab-case to PascalCase conversion."""
        assert is_readonly_operation("describe-instances") is True
        assert is_readonly_operation("list-buckets") is True
        assert is_readonly_operation("get-bucket-policy") is True

    def test_case_sensitivity(self):
        """Test case handling in operation names."""
        assert is_readonly_operation("DescribeInstances") is True
        assert is_readonly_operation("describeInstances") is False  # Lowercase 'd' doesn't match
        assert (
            is_readonly_operation("DESCRIBE-INSTANCES") is True
        )  # All caps gets converted to Describe-Instances


class TestValidateReadonly:
    """Test the main validation function."""

    def test_allow_unsafe_flag(self):
        """Test that allow_unsafe flag bypasses all checks."""
        assert validate_readonly("ec2", "terminate-instances", allow_unsafe=True) is True
        assert validate_readonly("s3", "delete-bucket", allow_unsafe=True) is True

    def test_readonly_operations_allowed(self):
        """Test that read-only operations are allowed without prompting."""
        assert validate_readonly("ec2", "describe-instances", allow_unsafe=False) is True
        assert validate_readonly("s3", "list-buckets", allow_unsafe=False) is True
        assert validate_readonly("dynamodb", "get-item", allow_unsafe=False) is True

    @patch("awsquery.security.prompt_unsafe_operation")
    def test_unsafe_operations_prompt(self, mock_prompt):
        """Test that unsafe operations trigger a prompt."""
        mock_prompt.return_value = True

        result = validate_readonly("ec2", "terminate-instances", allow_unsafe=False)
        assert result is True
        mock_prompt.assert_called_once_with("ec2", "terminate-instances")

    @patch("awsquery.security.prompt_unsafe_operation")
    def test_unsafe_operations_denied(self, mock_prompt):
        """Test that unsafe operations can be denied."""
        mock_prompt.return_value = False

        result = validate_readonly("ec2", "terminate-instances", allow_unsafe=False)
        assert result is False
        mock_prompt.assert_called_once_with("ec2", "terminate-instances")


class TestPromptUnsafeOperation:
    """Test the interactive prompt for unsafe operations."""

    @patch("builtins.input")
    def test_prompt_yes(self, mock_input):
        """Test accepting an unsafe operation."""
        mock_input.return_value = "yes"
        assert prompt_unsafe_operation("ec2", "terminate-instances") is True

    @patch("builtins.input")
    def test_prompt_no(self, mock_input):
        """Test declining an unsafe operation."""
        mock_input.return_value = "no"
        assert prompt_unsafe_operation("ec2", "terminate-instances") is False

    @patch("builtins.input")
    def test_prompt_y(self, mock_input):
        """Test accepting with 'y'."""
        mock_input.return_value = "y"
        assert prompt_unsafe_operation("ec2", "terminate-instances") is True

    @patch("builtins.input")
    def test_prompt_n(self, mock_input):
        """Test declining with 'n'."""
        mock_input.return_value = "n"
        assert prompt_unsafe_operation("ec2", "terminate-instances") is False

    @patch("builtins.input")
    def test_prompt_retry_invalid(self, mock_input):
        """Test that invalid input causes retry."""
        mock_input.side_effect = ["maybe", "yes"]
        assert prompt_unsafe_operation("ec2", "terminate-instances") is True
        assert mock_input.call_count == 2


class TestGetServiceValidOperations:
    """Test filtering operations by read-only status."""

    def test_filter_operations(self):
        """Test that operations are correctly filtered."""
        operations = [
            "DescribeInstances",
            "RunInstances",
            "ListBuckets",
            "DeleteBucket",
            "GetObject",
            "PutObject",
        ]

        valid = get_service_valid_operations("ec2", operations)

        assert "DescribeInstances" in valid
        assert "ListBuckets" in valid
        assert "GetObject" in valid
        assert "RunInstances" not in valid
        assert "DeleteBucket" not in valid
        assert "PutObject" not in valid


class TestActionToPolicyFormat:
    """Test action name format conversion."""

    def test_kebab_to_pascal(self):
        """Test converting kebab-case to PascalCase."""
        assert action_to_policy_format("describe-instances") == "DescribeInstances"
        assert action_to_policy_format("list-buckets") == "ListBuckets"
        assert action_to_policy_format("get-bucket-policy") == "GetBucketPolicy"

    def test_already_pascal(self):
        """Test that PascalCase is preserved."""
        assert action_to_policy_format("DescribeInstances") == "DescribeInstances"
