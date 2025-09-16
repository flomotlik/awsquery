"""Integration tests for autocomplete resilience without AWS credentials."""

import os
from argparse import Namespace

import pytest

from awsquery.cli import action_completer, service_completer


class TestAutocompleteWithoutCredentials:
    """Test that autocomplete works without AWS credentials using botocore's local data."""

    def setup_method(self):
        """Clear AWS environment variables for each test."""
        self.original_env = {}
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_PROFILE",
        ]:
            self.original_env[key] = os.environ.pop(key, None)

    def teardown_method(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_service_completer_without_credentials(self):
        """Test service completer works without AWS credentials."""
        # This uses botocore's local service definitions
        result = service_completer("ec", None)

        # Should return real AWS services from botocore's data
        assert len(result) > 0
        assert "ec2" in result
        assert "ecs" in result
        assert "ecr" in result
        assert all(s.startswith("ec") for s in result)

    def test_service_completer_various_prefixes(self):
        """Test service completer with different prefixes."""
        # Test single character
        result_s = service_completer("s", None)
        assert "s3" in result_s
        assert "sqs" in result_s
        assert "sns" in result_s

        # Test multi-character prefix
        result_cloud = service_completer("cloud", None)
        assert "cloudformation" in result_cloud
        assert "cloudwatch" in result_cloud
        assert "cloudtrail" in result_cloud

        # Test non-existent prefix
        result_xyz = service_completer("xyz", None)
        assert result_xyz == []

    def test_action_completer_without_credentials(self):
        """Test action completer works without AWS credentials."""
        parsed_args = Namespace(service="ec2")
        result = action_completer("describe", parsed_args)

        # Should return real EC2 operations from botocore's service model
        assert len(result) > 100  # EC2 has many describe operations
        assert "describe-instances" in result
        assert "describe-volumes" in result
        assert "describe-security-groups" in result
        assert all(a.startswith("describe") for a in result)

    def test_action_completer_different_services(self):
        """Test action completer for various AWS services."""
        # Test S3
        parsed_args = Namespace(service="s3")
        result = action_completer("list", parsed_args)
        assert "list-buckets" in result
        assert "list-objects" in result
        assert "list-objects-v2" in result

        # Test IAM
        parsed_args = Namespace(service="iam")
        result = action_completer("get", parsed_args)
        assert "get-user" in result
        assert "get-role" in result
        assert "get-policy" in result

        # Test Lambda
        parsed_args = Namespace(service="lambda")
        result = action_completer("list", parsed_args)
        assert "list-functions" in result
        assert "list-layers" in result

    def test_action_completer_nonexistent_service(self):
        """Test action completer with non-existent service."""
        parsed_args = Namespace(service="nonexistent-service-12345")
        result = action_completer("describe", parsed_args)
        assert result == []

    def test_action_completer_no_service(self):
        """Test action completer when no service is specified."""
        parsed_args = Namespace(service=None)
        result = action_completer("describe", parsed_args)
        assert result == []

    def test_autocomplete_with_invalid_profile(self):
        """Test autocomplete still works with invalid AWS_PROFILE."""
        os.environ["AWS_PROFILE"] = "nonexistent-profile-99999"

        # Service completer should still work
        services = service_completer("rds", None)
        assert "rds" in services

        # Action completer should still work
        parsed_args = Namespace(service="dynamodb")
        actions = action_completer("describe", parsed_args)
        assert "describe-table" in actions

    def test_autocomplete_filters_by_security_policy(self):
        """Test that autocomplete respects security policy filtering."""
        parsed_args = Namespace(service="ec2")

        # Get all operations
        all_ops = action_completer("", parsed_args)

        # Should not include write operations
        assert "create-instance" not in all_ops
        assert "delete-instance" not in all_ops
        assert "terminate-instances" not in all_ops

        # Should include read operations
        describe_ops = [op for op in all_ops if op.startswith("describe")]
        list_ops = [op for op in all_ops if op.startswith("list")]
        get_ops = [op for op in all_ops if op.startswith("get")]

        assert len(describe_ops) > 50  # EC2 has many describe operations
        assert len(list_ops) > 0
        assert len(get_ops) > 0
