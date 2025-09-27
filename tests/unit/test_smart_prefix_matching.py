"""Unit tests for smart prefix matching priority in action completion.

These tests verify that when prefix matches exist, substring-only matches
are excluded to provide more relevant completions.
"""

from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import (
    _current_completion_context,
    _enhanced_completion_validator,
    action_completer,
)


class TestSmartPrefixMatching:
    """Test smart prefix matching behavior."""

    def test_prefix_match_excludes_contains_only(self):
        """When prefix matches exist, exclude contains-only matches."""
        # Set up context with both prefix and contains-only matches
        _current_completion_context["operations"] = [
            "describe-instances",
            "describe-volumes",
            "batch-describe-configs",
        ]

        assert _enhanced_completion_validator("describe-instances", "desc") is True  # prefix
        assert (
            _enhanced_completion_validator("batch-describe-configs", "desc") is False
        )  # contains only

    def test_no_prefix_match_allows_contains(self):
        """When no prefix matches exist, allow contains matches."""
        # Set up context with no actions starting with "xyz"
        _current_completion_context["operations"] = [
            "create-instance",
            "describe-xyz-config",
            "list-xyz-items",
        ]

        assert _enhanced_completion_validator("describe-xyz-config", "xyz") is True

    def test_empty_input_returns_all(self):
        """Empty input should match all actions."""
        assert _enhanced_completion_validator("any-action", "") is True
        assert _enhanced_completion_validator("describe-instances", "") is True

    def test_exact_match_priority(self):
        """Exact matches should always be included."""
        assert _enhanced_completion_validator("describe", "describe") is True

    def test_multiple_prefix_matches(self):
        """All prefix matches should be included when multiple exist."""
        # Set up context with multiple prefix matches
        _current_completion_context["operations"] = [
            "describe-instances",
            "describe-volumes",
            "describe-subnets",
            "batch-describe-configs",
        ]

        assert _enhanced_completion_validator("describe-instances", "desc") is True
        assert _enhanced_completion_validator("describe-volumes", "desc") is True
        assert _enhanced_completion_validator("describe-subnets", "desc") is True

    def test_cloudformation_desc_example(self):
        """Real-world test based on the cloudformation example in Todo.md."""
        # Set up context with CloudFormation operations
        prefix_matches = [
            "describe-account-limits",
            "describe-change-set",
            "describe-change-set-hooks",
            "describe-generated-template",
            "describe-organizations-access",
            "describe-publisher",
            "describe-resource-scan",
            "describe-stack-drift-detection-status",
            "describe-stack-events",
            "describe-stack-instance",
            "describe-stack-refactor",
            "describe-stack-resource",
            "describe-stack-resource-drifts",
            "describe-stack-resources",
            "describe-stack-set",
            "describe-stack-set-operation",
            "describe-stacks",
            "describe-type",
            "describe-type-registration",
        ]

        # This should be excluded (contains "desc" but doesn't start with it)
        contains_only = "batch-describe-type-configurations"

        # Set up context with all operations
        _current_completion_context["operations"] = prefix_matches + [contains_only]

        for action in prefix_matches:
            assert _enhanced_completion_validator(action, "desc") is True, f"{action} should match"

        assert (
            _enhanced_completion_validator(contains_only, "desc") is False
        ), f"{contains_only} should not match"

    def test_case_insensitive_matching(self):
        """Prefix matching should be case insensitive."""
        assert _enhanced_completion_validator("Describe-Instances", "desc") is True
        assert _enhanced_completion_validator("describe-instances", "DESC") is True
        assert _enhanced_completion_validator("DESCRIBE-INSTANCES", "Desc") is True

    def test_split_matching_with_prefix_priority(self):
        """Split matching should work but prefix should have priority."""
        # First test: split matching works when no prefix matches exist
        _current_completion_context["operations"] = ["get-caller-identity", "list-functions"]
        assert _enhanced_completion_validator("get-caller-identity", "call-ide") is True

        # Second test: prefix priority over contains matching
        _current_completion_context["operations"] = ["describe-instances", "batch-describe-configs"]
        # Since describe-instances has prefix match for "desc", batch-describe should be excluded
        assert _enhanced_completion_validator("describe-instances", "desc") is True
        assert _enhanced_completion_validator("batch-describe-configs", "desc") is False


class TestSmartPrefixIntegration:
    """Integration tests for smart prefix matching with action completer."""

    @patch("awsquery.security.get_service_valid_operations")
    @patch("botocore.session.Session")
    def test_action_completer_applies_smart_matching(self, mock_session_class, mock_get_valid_ops):
        """Test that action_completer applies smart prefix matching logic."""

        # Mock botocore session
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.get_available_services.return_value = ["cloudformation"]

        # Mock CloudFormation operations including the problematic ones from Todo.md
        cf_operations = [
            "BatchDescribeTypeConfigurations",  # This should be excluded for "desc"
            "DescribeAccountLimits",  # These should be included
            "DescribeChangeSet",
            "DescribeGeneratedTemplate",
            "DescribeOrganizationsAccess",
            "DescribePublisher",
            "DescribeResourceScan",
            "DescribeStackDriftDetectionStatus",
            "DescribeStackEvents",
            "DescribeStackInstance",
            "DescribeStackRefactor",
            "DescribeStackResource",
            "DescribeStackResourceDrifts",
            "DescribeStackResources",
            "DescribeStackSet",
            "DescribeStackSetOperation",
            "DescribeStacks",
            "DescribeType",
            "DescribeTypeRegistration",
        ]

        mock_service_model = Mock()
        mock_service_model.operation_names = cf_operations
        mock_session.get_service_model.return_value = mock_service_model

        # Mock security validation to return all operations as valid
        mock_get_valid_ops.return_value = set(cf_operations)

        parsed_args = Namespace(service="cloudformation")
        all_operations = action_completer("desc", parsed_args)

        # action_completer returns all operations, but we can test what the validator filters
        filtered_results = [
            op for op in all_operations if _enhanced_completion_validator(op, "desc")
        ]

        # Should include prefix matches
        assert "describe-account-limits" in filtered_results
        assert "describe-change-set" in filtered_results
        assert "describe-stacks" in filtered_results

        # Should exclude contains-only matches
        assert "batch-describe-type-configurations" not in filtered_results

    def test_validator_with_real_actions(self):
        """Test validator behavior with realistic AWS action names."""
        real_actions = [
            "describe-instances",
            "describe-volumes",
            "describe-subnets",
            "batch-describe-reserved-instances",
            "batch-describe-spot-fleet-requests",
        ]

        # Set up context
        _current_completion_context["operations"] = real_actions

        # For "desc" input, only prefix matches should be valid
        for action in real_actions:
            if action.startswith("describe-"):
                assert _enhanced_completion_validator(action, "desc") is True
            else:
                assert _enhanced_completion_validator(action, "desc") is False

    def test_no_prefix_matches_fallback_to_contains(self):
        """When no prefix matches exist, should fall back to contains matching."""
        actions = ["create-instance", "delete-instance", "run-instances", "terminate-instances"]

        # Set up context
        _current_completion_context["operations"] = actions

        # For "instance" input, no actions start with "instance"
        # so should fall back to contains matching
        for action in actions:
            if "instance" in action:
                assert _enhanced_completion_validator(action, "instance") is True
            else:
                assert _enhanced_completion_validator(action, "instance") is False
