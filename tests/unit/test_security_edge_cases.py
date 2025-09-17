"""Edge case tests for security policy validation."""

import json
import tempfile
from unittest.mock import mock_open, patch

import pytest

from awsquery.security import load_security_policy, validate_security


class TestLoadSecurityPolicyEdgeCases:
    """Test load_security_policy with edge cases."""

    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    def test_empty_policy_file(self, mock_file):
        """Test loading empty policy file."""
        allowed = load_security_policy()
        assert allowed == set()

    @patch("builtins.open", new_callable=mock_open, read_data='{"Statement": []}')
    def test_empty_statements(self, mock_file):
        """Test policy with empty statements list."""
        allowed = load_security_policy()
        assert allowed == set()

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_with_deny_only(self, mock_file):
        """Test policy with only Deny statements."""
        policy = {"Statement": [{"Effect": "Deny", "Action": ["s3:*", "ec2:*"]}]}
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert allowed == set()

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_with_single_action_string(self, mock_file):
        """Test policy with Action as string instead of list."""
        policy = {"Statement": [{"Effect": "Allow", "Action": "ec2:DescribeInstances"}]}
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert "ec2:DescribeInstances" in allowed

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_version_structure(self, mock_file):
        """Test policy with PolicyVersion structure."""
        policy = {
            "PolicyVersion": {
                "Document": {
                    "Statement": [{"Effect": "Allow", "Action": ["s3:ListBuckets", "s3:GetObject"]}]
                }
            }
        }
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert "s3:ListBuckets" in allowed
        assert "s3:GetObject" in allowed

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_missing_effect(self, mock_file):
        """Test policy statement missing Effect field."""
        policy = {"Statement": [{"Action": ["ec2:DescribeInstances"]}]}
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        # Should not add actions without explicit Allow
        assert "ec2:DescribeInstances" not in allowed

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_missing_action(self, mock_file):
        """Test policy statement missing Action field."""
        policy = {"Statement": [{"Effect": "Allow"}]}
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert allowed == set()

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_with_wildcards(self, mock_file):
        """Test policy with wildcard actions."""
        policy = {
            "Statement": [{"Effect": "Allow", "Action": ["ec2:Describe*", "s3:Get*", "iam:List*"]}]
        }
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert "ec2:Describe*" in allowed
        assert "s3:Get*" in allowed
        assert "iam:List*" in allowed

    @patch("builtins.open", new_callable=mock_open)
    def test_policy_mixed_allow_deny(self, mock_file):
        """Test policy with mixed Allow and Deny statements."""
        policy = {
            "Statement": [
                {"Effect": "Allow", "Action": ["ec2:DescribeInstances", "ec2:DescribeVolumes"]},
                {"Effect": "Deny", "Action": ["ec2:TerminateInstances"]},
                {"Effect": "Allow", "Action": ["s3:ListBuckets"]},
            ]
        }
        mock_file.return_value.read.return_value = json.dumps(policy)

        allowed = load_security_policy()
        assert "ec2:DescribeInstances" in allowed
        assert "ec2:DescribeVolumes" in allowed
        assert "s3:ListBuckets" in allowed
        assert "ec2:TerminateInstances" not in allowed


class TestValidateSecurityEdgeCases:
    """Test validate_security with edge cases."""

    def test_empty_allowed_actions(self):
        """Test validation with empty allowed actions."""
        # Empty allowed actions should allow by default
        assert validate_security("ec2", "DescribeInstances", set())
        assert validate_security("s3", "ListBuckets", set())

    def test_none_allowed_actions(self):
        """Test validation with None allowed actions."""
        assert validate_security("ec2", "DescribeInstances", None)

    def test_exact_match(self):
        """Test exact action matching."""
        allowed = {"ec2:DescribeInstances", "s3:ListBuckets"}

        assert validate_security("ec2", "DescribeInstances", allowed)
        assert validate_security("s3", "ListBuckets", allowed)
        assert not validate_security("ec2", "TerminateInstances", allowed)

    def test_wildcard_service_match(self):
        """Test wildcard service matching."""
        allowed = {"*:DescribeInstances", "ec2:*"}

        assert validate_security("ec2", "DescribeInstances", allowed)
        assert validate_security("ec2", "TerminateInstances", allowed)
        assert validate_security("rds", "DescribeInstances", allowed)

    def test_wildcard_action_match(self):
        """Test wildcard action matching."""
        allowed = {"ec2:Describe*", "s3:Get*"}

        assert validate_security("ec2", "DescribeInstances", allowed)
        assert validate_security("ec2", "DescribeVolumes", allowed)
        assert validate_security("s3", "GetObject", allowed)
        assert not validate_security("ec2", "TerminateInstances", allowed)

    def test_full_wildcard(self):
        """Test full wildcard matching."""
        allowed = {"*:*", "*"}

        assert validate_security("ec2", "DescribeInstances", allowed)
        assert validate_security("s3", "DeleteBucket", allowed)
        assert validate_security("iam", "CreateUser", allowed)

    def test_case_sensitivity(self):
        """Test case sensitivity in matching."""
        allowed = {"ec2:DescribeInstances"}

        # Should handle matching case
        assert validate_security("ec2", "DescribeInstances", allowed)
        # May be case sensitive for service name
        # assert validate_security("EC2", "DescribeInstances", allowed)

    def test_special_characters_in_action(self):
        """Test actions with special characters."""
        allowed = {"service:Action-With-Dashes", "service:Action_With_Underscores"}

        assert validate_security("service", "Action-With-Dashes", allowed)
        assert validate_security("service", "Action_With_Underscores", allowed)

    def test_empty_service_or_action(self):
        """Test with empty service or action."""
        allowed = {"ec2:DescribeInstances"}

        assert not validate_security("", "DescribeInstances", allowed)
        assert not validate_security("ec2", "", allowed)
        assert not validate_security("", "", allowed)

    def test_complex_wildcard_patterns(self):
        """Test complex wildcard patterns."""
        allowed = {"ec2:Describe*Instances", "s3:*Bucket*", "*:List*"}

        assert validate_security("ec2", "DescribeInstances", allowed)
        assert validate_security("ec2", "DescribeSpotFleetInstances", allowed)
        assert validate_security("s3", "ListBuckets", allowed)
        assert validate_security("s3", "CreateBucketPolicy", allowed)
        assert validate_security("iam", "ListUsers", allowed)
