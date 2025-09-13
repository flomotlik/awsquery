"""Unit tests for security validation functions."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.awsquery.security import action_to_policy_format, load_security_policy, validate_security
from tests.fixtures.policy_samples import (
    get_deny_policy,
    get_legacy_policy_formats,
    get_malformed_policies,
    get_readonly_policy,
    get_restrictive_policy,
    get_wildcard_policy,
)


class TestLoadSecurityPolicy:

    @pytest.mark.unit
    @pytest.mark.critical
    def test_load_policy_with_policyversion_structure(self):
        policy_content = get_readonly_policy()
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()
        assert len(allowed_actions) > 0
        assert "ec2:Describe*" in allowed_actions
        assert "s3:List*" in allowed_actions
        assert "iam:Get*" in allowed_actions
        assert "cloudformation:Describe*" in allowed_actions

    @pytest.mark.unit
    @pytest.mark.critical
    def test_load_policy_with_direct_statement_structure(self):
        policy_content = get_legacy_policy_formats()["direct_statement"]
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert len(allowed_actions) == 2
        assert "ec2:DescribeInstances" in allowed_actions
        assert "s3:ListBuckets" in allowed_actions

    @pytest.mark.unit
    def test_load_policy_with_single_action_string(self):
        policy_content = get_legacy_policy_formats()["single_action_string"]
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert len(allowed_actions) == 1
        assert "ec2:DescribeInstances" in allowed_actions

    @pytest.mark.unit
    def test_load_policy_with_multiple_statements(self):
        policy_content = get_legacy_policy_formats()["multiple_statements"]
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()
        assert "ec2:Describe*" in allowed_actions
        assert "s3:List*" in allowed_actions
        assert "s3:Get*" in allowed_actions
        assert "ec2:TerminateInstances" not in allowed_actions

    @pytest.mark.unit
    def test_load_policy_ignores_deny_statements(self):
        policy_content = {
            "Statement": [
                {"Effect": "Allow", "Action": ["ec2:DescribeInstances"]},
                {"Effect": "Deny", "Action": ["ec2:TerminateInstances"]},
            ]
        }
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert "ec2:DescribeInstances" in allowed_actions
        assert "ec2:TerminateInstances" not in allowed_actions

    @pytest.mark.unit
    def test_load_policy_with_empty_statements(self):
        policy_content = get_malformed_policies()["empty_statement"]
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert len(allowed_actions) == 0

    @pytest.mark.unit
    def test_load_policy_with_missing_statement(self):
        policy_content = {"PolicyVersion": {"Document": {"Version": "2012-10-17"}}}
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert len(allowed_actions) == 0

    @pytest.mark.unit
    def test_load_policy_with_missing_action_field(self):
        """Test loading policy statement with missing Action field."""
        policy_content = {
            "Statement": [
                {
                    "Effect": "Allow"
                    # Missing Action field
                }
            ]
        }
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        assert len(allowed_actions) == 0

    @pytest.mark.unit
    @pytest.mark.critical
    def test_load_policy_file_not_found_error(self):
        """Test proper error handling when policy.json file is not found."""
        with patch("builtins.open", side_effect=FileNotFoundError()):
            with pytest.raises(SystemExit):
                load_security_policy()

    @pytest.mark.unit
    @pytest.mark.critical
    def test_load_policy_invalid_json_error(self):
        """Test proper error handling when policy.json contains invalid JSON."""
        invalid_json = '{"PolicyVersion": {"Document": {invalid json}'

        with patch("builtins.open", mock_open(read_data=invalid_json)):
            with pytest.raises(SystemExit):
                load_security_policy()

    @pytest.mark.unit
    def test_load_policy_empty_file(self):
        """Test loading completely empty policy file."""
        with patch("builtins.open", mock_open(read_data="")):
            with pytest.raises(SystemExit):
                load_security_policy()

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "policy_scenario,expected_actions",
        [
            ("readonly", ["ec2:Describe*", "s3:List*", "iam:Get*"]),
            ("restrictive", ["ec2:DescribeInstances", "s3:ListBuckets", "iam:GetUser"]),
            ("wildcard", ["*:Describe*", "*:List*", "ec2:Get*"]),
        ],
    )
    def test_load_various_policy_formats(self, policy_scenario, expected_actions):
        """Test loading various policy format scenarios."""
        policy_functions = {
            "readonly": get_readonly_policy,
            "restrictive": get_restrictive_policy,
            "wildcard": get_wildcard_policy,
        }

        policy_content = policy_functions[policy_scenario]()
        policy_json = json.dumps(policy_content)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        for expected_action in expected_actions:
            assert expected_action in allowed_actions

    @pytest.mark.unit
    def test_load_policy_debug_output(self, capsys):
        """Test debug output during policy loading."""
        # Enable debug mode
        with patch("src.awsquery.utils.debug_enabled", True):
            policy_content = get_restrictive_policy()
            policy_json = json.dumps(policy_content)

            with patch("builtins.open", mock_open(read_data=policy_json)):
                allowed_actions = load_security_policy()

        captured = capsys.readouterr()
        assert "DEBUG: Loaded policy with keys:" in captured.err
        assert "DEBUG: Found PolicyVersion structure" in captured.err
        assert "DEBUG: Total allowed actions loaded:" in captured.err


class TestValidateSecurity:
    """Test security validation with different policy patterns."""

    @pytest.mark.unit
    @pytest.mark.critical
    def test_validate_security_direct_match(self, mock_security_policy):
        """Test validation with direct action matches."""
        # Test exact matches from the mock policy
        assert validate_security("ec2", "DescribeInstances", mock_security_policy) is True
        assert validate_security("s3", "ListBuckets", mock_security_policy) is True
        assert validate_security("iam", "GetUser", mock_security_policy) is True

    @pytest.mark.unit
    @pytest.mark.critical
    def test_validate_security_wildcard_service_match(self, mock_security_policy):
        """Test validation with service-level wildcard patterns."""
        # These should match wildcard patterns like "ec2:Describe*"
        assert validate_security("ec2", "DescribeImages", mock_security_policy) is True
        assert validate_security("ec2", "DescribeSecurityGroups", mock_security_policy) is True
        assert validate_security("s3", "ListObjects", mock_security_policy) is True

    @pytest.mark.unit
    @pytest.mark.critical
    def test_validate_security_wildcard_action_match(self, mock_security_policy):
        """Test validation with action-level wildcard patterns."""
        # These should match service-specific patterns like "s3:List*", "iam:List*"
        assert validate_security("s3", "ListObjects", mock_security_policy) is True
        assert validate_security("iam", "ListRoles", mock_security_policy) is True

        # These should NOT match because there's no "*:List*" pattern in mock_security_policy
        assert validate_security("rds", "ListDatabases", mock_security_policy) is False
        assert validate_security("lambda", "ListFunctions", mock_security_policy) is False

    @pytest.mark.unit
    @pytest.mark.critical
    def test_validate_security_case_sensitivity(self, mock_security_policy):
        """Test case sensitivity in security validation."""
        # Should be case-sensitive
        assert validate_security("ec2", "describeinstances", mock_security_policy) is False
        assert validate_security("EC2", "DescribeInstances", mock_security_policy) is False

        # Correct case should work
        assert validate_security("ec2", "DescribeInstances", mock_security_policy) is True

    @pytest.mark.unit
    def test_validate_security_empty_allowed_actions(self):
        """Test validation with empty allowed_actions set (default allow behavior)."""
        empty_actions = set()

        # Should return True for any action when allowed_actions is empty
        assert validate_security("ec2", "DescribeInstances", empty_actions) is True
        assert validate_security("s3", "DeleteBucket", empty_actions) is True
        assert validate_security("iam", "CreateUser", empty_actions) is True

    @pytest.mark.unit
    def test_validate_security_none_allowed_actions(self):
        """Test validation with None allowed_actions (default allow behavior)."""
        # Should return True for any action when allowed_actions is None
        assert validate_security("ec2", "DescribeInstances", None) is True
        assert validate_security("s3", "DeleteBucket", None) is True

    @pytest.mark.unit
    @pytest.mark.critical
    def test_validate_security_no_matches(self, mock_security_policy):
        """Test validation when no policy matches are found (should deny)."""
        # These actions should not match any patterns in the mock policy
        assert validate_security("ec2", "TerminateInstances", mock_security_policy) is False
        assert validate_security("s3", "DeleteBucket", mock_security_policy) is False
        assert validate_security("iam", "CreateUser", mock_security_policy) is False
        assert validate_security("unknown", "SomeAction", mock_security_policy) is False

    @pytest.mark.unit
    def test_validate_security_complex_wildcard_patterns(self):
        """Test validation with complex wildcard patterns."""
        complex_policy = {
            "s3:*Bucket*",  # Should match anything with "Bucket" in it
            "ec2:*Instance*",  # Should match anything with "Instance" in it
            "*:List*",  # Should match any service with List* actions
            "cloudformation:*Stack*",  # Should match anything with "Stack" in it
        }

        # Test complex pattern matching
        assert validate_security("s3", "CreateBucket", complex_policy) is True
        assert validate_security("s3", "DeleteBucketPolicy", complex_policy) is True
        assert validate_security("ec2", "TerminateInstances", complex_policy) is True
        assert validate_security("rds", "ListDatabases", complex_policy) is True
        assert validate_security("cloudformation", "CreateStackSet", complex_policy) is True

        # These should not match
        assert validate_security("ec2", "CreateVolume", complex_policy) is False
        assert validate_security("s3", "GetObject", complex_policy) is False

    @pytest.mark.unit
    def test_validate_security_service_action_format_validation(self, mock_security_policy):
        """Test that service:action format is properly constructed."""
        # These tests ensure the service:action string is built correctly
        assert validate_security("ec2", "DescribeInstances", mock_security_policy) is True
        assert (
            validate_security("", "DescribeInstances", mock_security_policy) is False
        )  # Empty service
        assert validate_security("ec2", "", mock_security_policy) is False  # Empty action

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "service,action,expected",
        [
            ("ec2", "DescribeInstances", True),  # Direct match
            ("ec2", "DescribeImages", True),  # Wildcard match
            ("s3", "ListBuckets", True),  # Direct match
            ("s3", "ListObjects", True),  # Wildcard match
            ("ec2", "TerminateInstances", False),  # No match
            ("s3", "DeleteBucket", False),  # No match
            ("unknown", "SomeAction", False),  # Unknown service
            ("", "DescribeInstances", False),  # Empty service
            ("ec2", "", False),  # Empty action
        ],
    )
    def test_validate_security_parametrized_scenarios(
        self, mock_security_policy, service, action, expected
    ):
        """Parametrized tests for various validation scenarios."""
        result = validate_security(service, action, mock_security_policy)
        assert result is expected

    @pytest.mark.unit
    def test_validate_security_debug_output(self, mock_security_policy, capsys):
        """Test debug output during security validation."""
        with patch("src.awsquery.utils.debug_enabled", True):
            # Test successful validation
            validate_security("ec2", "DescribeInstances", mock_security_policy)

            # Test failed validation
            validate_security("ec2", "TerminateInstances", mock_security_policy)

        captured = capsys.readouterr()
        assert "DEBUG: Validating ec2:DescribeInstances against" in captured.err
        assert "DEBUG: Direct match found for ec2:DescribeInstances" in captured.err
        assert "DEBUG: No match found for ec2:TerminateInstances" in captured.err


class TestActionToPolicyFormat:
    """Test action name conversion to PascalCase."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "input_action,expected_output",
        [
            # Kebab-case to PascalCase
            ("describe-instances", "DescribeInstances"),
            ("list-buckets", "ListBuckets"),
            ("get-user", "GetUser"),
            ("create-capacity-provider", "CreateCapacityProvider"),
            ("describe-security-groups", "DescribeSecurityGroups"),
            # Snake_case to PascalCase
            ("describe_instances", "DescribeInstances"),
            ("list_buckets", "ListBuckets"),
            ("get_user", "GetUser"),
            ("create_capacity_provider", "CreateCapacityProvider"),
            # Mixed case
            ("describe-stack_resources", "DescribeStackResources"),
            ("list_bucket-policies", "ListBucketPolicies"),
            # Single words
            ("describe", "Describe"),
            ("list", "List"),
            ("get", "Get"),
            # Already PascalCase (gets split and re-joined)
            ("DescribeInstances", "Describeinstances"),
            ("ListBuckets", "Listbuckets"),
            # Multiple consecutive separators
            ("describe--instances", "DescribeInstances"),
            ("list__buckets", "ListBuckets"),
            ("get-_user", "GetUser"),
            # Leading/trailing separators
            ("-describe-instances", "DescribeInstances"),
            ("list-buckets-", "ListBuckets"),
            ("_get_user_", "GetUser"),
        ],
    )
    def test_action_to_policy_format_standard_cases(self, input_action, expected_output):
        """Test standard action name conversion scenarios."""
        result = action_to_policy_format(input_action)
        assert result == expected_output

    @pytest.mark.unit
    def test_action_to_policy_format_empty_string(self):
        """Test conversion of empty string."""
        result = action_to_policy_format("")
        assert result == ""

    @pytest.mark.unit
    def test_action_to_policy_format_single_character(self):
        """Test conversion of single characters."""
        assert action_to_policy_format("a") == "A"
        assert action_to_policy_format("-") == ""
        assert action_to_policy_format("_") == ""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "special_input,expected",
        [
            # Numbers in action names
            ("describe-db-instances-2", "DescribeDbInstances2"),
            ("list-s3-buckets", "ListS3Buckets"),
            ("get-ec2-info", "GetEc2Info"),
            # Special characters (only - and _ are treated as separators, others preserved)
            ("describe.instances", "Describe.instances"),  # Dots not treated as separators
            ("list@buckets", "List@buckets"),  # @ not treated as separators
            ("get+user", "Get+user"),  # + not treated as separators
            # Whitespace handling
            ("describe instances", "DescribeInstances"),
            ("list  buckets", "ListBuckets"),
            (" get user ", "GetUser"),
        ],
    )
    def test_action_to_policy_format_special_cases(self, special_input, expected):
        """Test conversion with special characters and numbers."""
        result = action_to_policy_format(special_input)
        assert result == expected

    @pytest.mark.unit
    def test_action_to_policy_format_complex_real_world_examples(self):
        """Test conversion with real-world AWS action names."""
        test_cases = [
            # Real AWS action patterns
            ("create-launch-template", "CreateLaunchTemplate"),
            ("describe-vpc-endpoints", "DescribeVpcEndpoints"),
            ("list-hosted-zones", "ListHostedZones"),
            ("get-bucket-acl", "GetBucketAcl"),
            ("describe-db-subnet-groups", "DescribeDbSubnetGroups"),
            ("list-identity-providers", "ListIdentityProviders"),
            ("get-queue-attributes", "GetQueueAttributes"),
            ("describe-auto-scaling-groups", "DescribeAutoScalingGroups"),
            # Edge cases with AWS service prefixes
            ("ec2-describe-instances", "Ec2DescribeInstances"),
            ("s3-list-buckets", "S3ListBuckets"),
            ("iam-get-user", "IamGetUser"),
        ]

        for input_action, expected in test_cases:
            result = action_to_policy_format(input_action)
            assert result == expected, f"Expected {expected}, got {result} for input {input_action}"

    @pytest.mark.unit
    def test_action_to_policy_format_idempotency(self):
        """Test that converting already converted names gives consistent results."""
        # Note: PascalCase gets split by the function, so it's not truly idempotent
        already_pascal = "DescribeInstances"
        result = action_to_policy_format(already_pascal)
        assert result == "Describeinstances"  # Gets split and rejoined

        # Test double conversion - should be stable after first conversion
        kebab_input = "describe-instances"
        first_conversion = action_to_policy_format(kebab_input)
        second_conversion = action_to_policy_format(first_conversion)
        assert first_conversion == "DescribeInstances"
        assert second_conversion == "Describeinstances"  # Gets split again

    @pytest.mark.unit
    def test_action_to_policy_format_case_preservation(self):
        """Test that case is properly handled in various scenarios."""
        test_cases = [
            # Mixed case inputs (each word gets capitalized)
            ("Describe-Instances", "DescribeInstances"),
            ("LIST-buckets", "ListBuckets"),
            ("Get-User", "GetUser"),
            ("camelCase-action", "CamelcaseAction"),
            ("UPPER-CASE", "UpperCase"),
            # All lowercase
            ("describe-instances", "DescribeInstances"),
            ("list_buckets", "ListBuckets"),
        ]

        for input_action, expected in test_cases:
            result = action_to_policy_format(input_action)
            assert result == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "input_str",
        [
            "describe-instances",
            "list_buckets",
            "get-user",
            "create-capacity-provider",
            "describe_security_groups",
            "",
            "single",
            "DescribeInstances",
        ],
    )
    def test_action_to_policy_format_returns_string(self, input_str):
        """Test that function always returns a string."""
        result = action_to_policy_format(input_str)
        assert isinstance(result, str)


# Integration tests combining all functions
class TestSecurityIntegration:
    """Integration tests combining policy loading and validation."""

    @pytest.mark.unit
    @pytest.mark.critical
    def test_end_to_end_security_validation_workflow(self, tmp_path):
        """Test complete workflow from policy loading to validation."""
        # Create a test policy file
        policy_content = get_restrictive_policy()
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_content))

        # Mock the file path
        with patch("src.awsquery.security.open", mock_open(read_data=json.dumps(policy_content))):
            # Load the policy
            allowed_actions = load_security_policy()

            # Test validation with loaded policy
            assert validate_security("ec2", "DescribeInstances", allowed_actions) is True
            assert validate_security("s3", "ListBuckets", allowed_actions) is True
            assert validate_security("iam", "GetUser", allowed_actions) is True

            # These should fail with restrictive policy
            assert validate_security("ec2", "TerminateInstances", allowed_actions) is False
            assert validate_security("s3", "DeleteBucket", allowed_actions) is False

    @pytest.mark.unit
    def test_action_conversion_with_validation(self, mock_security_policy):
        """Test action name conversion integrated with validation."""
        # Convert kebab-case action to policy format
        converted_action = action_to_policy_format("describe-instances")
        assert converted_action == "DescribeInstances"

        # Use converted action in validation
        assert validate_security("ec2", converted_action, mock_security_policy) is True

        # Test with action that needs conversion but won't match policy
        converted_deny_action = action_to_policy_format("terminate-instances")
        assert converted_deny_action == "TerminateInstances"
        assert validate_security("ec2", converted_deny_action, mock_security_policy) is False

    @pytest.mark.unit
    @pytest.mark.critical
    def test_policy_loading_error_recovery(self):
        """Test error recovery scenarios in policy loading."""
        # Test that system exits on policy load failure don't crash validation
        with patch("builtins.open", side_effect=FileNotFoundError()):
            with pytest.raises(SystemExit):
                load_security_policy()

        # Validation should still work with empty policy set
        empty_policy = set()
        assert validate_security("ec2", "DescribeInstances", empty_policy) is True

    @pytest.mark.unit
    def test_comprehensive_wildcard_scenarios(self):
        """Test comprehensive wildcard matching scenarios."""
        wildcard_policy = get_wildcard_policy()
        policy_json = json.dumps(wildcard_policy)

        with patch("builtins.open", mock_open(read_data=policy_json)):
            allowed_actions = load_security_policy()

        # Test various wildcard patterns
        test_cases = [
            ("ec2", "DescribeInstances", True),  # *:Describe*
            ("s3", "ListBuckets", True),  # *:List*
            ("rds", "DescribeDBInstances", True),  # *:Describe*
            ("lambda", "ListFunctions", True),  # *:List*
            ("ec2", "GetConsoleOutput", True),  # ec2:Get*
            ("s3", "GetBucketPolicy", True),  # s3:*Bucket*
            ("cloudformation", "DescribeStacks", True),  # cloudformation:*Stack*
            ("iam", "GetUser", True),  # iam:*User*
            # These should not match
            ("ec2", "CreateInstances", False),  # No Create* pattern
            ("s3", "DeleteObject", False),  # No Delete* pattern
        ]

        for service, action, expected in test_cases:
            result = validate_security(service, action, allowed_actions)
            assert result is expected, f"Expected {expected} for {service}:{action}"
