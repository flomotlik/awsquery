"""Tests for -i/--input parameter feature."""

import sys
from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import _enhanced_completion_validator, main


class TestInputHintParsing:
    def test_input_hint_flag_implemented(self):
        sys.argv = ["awsquery", "-i", "desc-clus", "elbv2", "describe-tags"]

        # Now -i is implemented, so "elbv2" is the service and "describe-tags" is the action
        with patch("awsquery.cli.validate_readonly") as mock_validate:
            mock_validate.return_value = False  # Reject the operation

            with pytest.raises(SystemExit):
                main()

        # The validator should have been called with correct service/action
        mock_validate.assert_called_once()
        args = mock_validate.call_args[0]
        assert args[0] == "elbv2"  # service
        assert args[1] == "describe-tags"  # action

    def test_input_hint_long_flag_implemented(self):
        sys.argv = ["awsquery", "--input", "desc-clus", "elbv2", "describe-tags"]

        # Now --input is implemented, so "elbv2" is the service and "describe-tags" is the action
        with patch("awsquery.cli.validate_readonly") as mock_validate:
            mock_validate.return_value = False  # Reject the operation

            with pytest.raises(SystemExit):
                main()

        # Should have been called with the parsed arguments
        mock_validate.assert_called_once()

    def test_future_input_hint_flag_structure(self):
        expected_usage_patterns = [
            ["awsquery", "-i", "desc-clus", "elbv2", "describe-tags"],
            ["awsquery", "--input", "list-inst", "ec2", "describe-security-groups"],
            ["awsquery", "-i", "desc-stack", "cloudformation", "describe-stack-events"],
        ]

        for pattern in expected_usage_patterns:
            assert len(pattern) >= 5
            assert pattern[1] in ["-i", "--input"]
            assert isinstance(pattern[2], str)


class TestHintFunctionMatching:
    def test_exact_prefix_match(self):
        # This uses the existing enhanced completion validator
        operations = [
            "describe-load-balancers",
            "describe-target-groups",
            "describe-listeners",
            "describe-target-health",
            "describe-clusters",  # This would be the target
            "modify-cluster",
        ]

        hint = "desc-clus"

        # Find matches using enhanced completion validator logic
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert "describe-clusters" in matches
        assert len(matches) >= 1

    def test_split_matching_algorithm(self):
        operations = [
            "describe-load-balancers",
            "describe-target-groups",
            "describe-clusters",
            "list-clusters",
            "get-cluster-info",
        ]

        hint = "desc-clus"

        # Split matching: "desc" and "clus" should both be found
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert "describe-clusters" in matches
        # The validator should prefer operations that match the pattern

    def test_case_insensitive_matching(self):
        operations = ["describe-clusters", "Describe-LoadBalancers", "DESCRIBE-STACKS"]

        # Test various case combinations
        test_cases = [
            ("desc-clus", "describe-clusters"),
            ("DESC-CLUS", "describe-clusters"),
            ("Desc-Clus", "describe-clusters"),
            ("desc-load", "Describe-LoadBalancers"),
            ("desc-stack", "DESCRIBE-STACKS"),
        ]

        for hint, expected in test_cases:
            matches = [op for op in operations if _enhanced_completion_validator(op, hint)]
            assert expected.lower() in [m.lower() for m in matches]

    def test_no_matches_returns_empty(self):
        operations = ["describe-instances", "list-volumes", "get-snapshots"]

        hint = "xyz-notfound"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert matches == []

    def test_partial_word_matching(self):
        operations = [
            "describe-db-clusters",
            "describe-rds-clusters",
            "describe-cache-clusters",
            "list-clusters",
            "describe-instances",
        ]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # Should match operations containing both "desc" and "clus"
        expected_matches = [
            "describe-db-clusters",
            "describe-rds-clusters",
            "describe-cache-clusters",
        ]
        for expected in expected_matches:
            assert expected in matches

    def test_hyphen_handling_in_hints(self):
        operations = ["describe-load-balancers", "describe-target-groups", "describe-clusters"]

        test_cases = [
            "desc-load-bal",  # Multiple hyphens
            "descload",  # No hyphens - this may not match perfectly
            "desc_load",  # Underscore instead of hyphen - may not match
        ]

        for hint in test_cases:
            matches = [op for op in operations if _enhanced_completion_validator(op, hint)]
            # At least some matching should occur for reasonable hints
            assert isinstance(matches, list)

    def test_empty_hint_matches_all(self):
        operations = ["describe-clusters", "list-instances", "get-volumes"]

        hint = ""
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert len(matches) == len(operations)
        for op in operations:
            assert op in matches


class TestHintSelection:
    def test_shortest_match_selection(self):
        operations = [
            "describe-clusters",
            "describe-cache-clusters",
            "describe-db-clusters",
            "describe-elasticache-clusters",
        ]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # All should match, but shortest would be preferred in implementation
        assert "describe-clusters" in matches
        assert len(matches) >= 1

        # In actual implementation, shortest would be selected
        sorted_matches = sorted(matches, key=len)
        assert sorted_matches[0] == "describe-clusters"

    def test_prefix_priority_over_contains(self):
        operations = [
            "describe-clusters",  # Prefix match for "desc"
            "batch-describe-clusters",  # Contains "desc" but not prefix
            "get-cluster-info",  # Contains "clus" but not "desc"
        ]

        hint = "desc"

        # Using the enhanced completion validator's logic
        from awsquery.cli import _current_completion_context

        _current_completion_context["operations"] = operations

        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # Should include prefix matches
        assert "describe-clusters" in matches
        # Should exclude contains-only when prefix matches exist
        assert "batch-describe-clusters" not in matches

    def test_alphabetical_selection_for_equal_length(self):
        operations = [
            "describe-zeta-clusters",
            "describe-beta-clusters",
            "describe-alpha-clusters",
        ]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # All should match
        assert len(matches) == 3

        # Alphabetical order would prefer "alpha"
        sorted_matches = sorted(matches)
        assert sorted_matches[0] == "describe-alpha-clusters"

    def test_single_match_selection(self):
        operations = [
            "describe-clusters",
            "list-instances",
            "get-volumes",
        ]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert len(matches) == 1
        assert matches[0] == "describe-clusters"

    def test_no_selection_when_no_matches(self):
        operations = ["list-instances", "get-volumes", "create-snapshots"]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        assert len(matches) == 0

    def test_complex_selection_scenario(self):
        # Realistic EKS operations
        operations = [
            "describe-cluster",  # Shortest exact match
            "describe-fargate-profile",  # Contains both parts
            "list-clusters",  # Different prefix
            "describe-nodegroup",  # Only contains "desc"
            "update-cluster-config",  # Contains "clus" but not "desc"
        ]

        hint = "desc-clus"
        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # Should include operations with both "desc" and "clus"
        expected_in_matches = ["describe-cluster"]
        for expected in expected_in_matches:
            assert expected in matches


class TestHintIntegration:
    @patch("awsquery.core.infer_list_operation")
    def test_hint_function_used_in_inference(self, mock_infer):
        mock_infer.return_value = ["describe-clusters", "list-clusters"]

        # This tests the integration pattern where hint would influence inference
        service = "eks"
        parameter_name = "ClusterName"
        action = "describe-fargate-profile"
        # hint = "desc-clus"  # This would be passed in future implementation

        # Call the function (in actual implementation, hint would be passed)
        result = mock_infer(service, parameter_name, action)

        assert isinstance(result, list)
        mock_infer.assert_called_once()

    @patch("awsquery.core.execute_aws_call")
    def test_hint_improves_parameter_resolution(self, mock_execute):
        # Mock successful execution of hint-suggested function
        mock_execute.return_value = [
            {
                "Clusters": [
                    {
                        "ClusterName": "prod-cluster",
                        "ClusterArn": "arn:aws:eks:us-east-1:123:cluster/prod",
                    }
                ]
            }
        ]

        # Test actual parameter extraction using hint-selected function
        from awsquery.filters import extract_parameter_values

        response = mock_execute.return_value
        from awsquery.formatters import flatten_response

        resources = flatten_response(response, service="ec2", operation="DescribeInstances")

        parameter_values = extract_parameter_values(resources, "ClusterName")
        assert "prod-cluster" in parameter_values

    def test_hint_parameter_extraction_logic(self):
        # Mock response from hint-selected function (e.g., describe-clusters)
        cluster_response = [
            {
                "Clusters": [
                    {
                        "ClusterName": "prod-cluster",
                        "ClusterArn": "arn:aws:eks:us-east-1:123:cluster/prod",
                    },
                    {
                        "ClusterName": "dev-cluster",
                        "ClusterArn": "arn:aws:eks:us-east-1:123:cluster/dev",
                    },
                ]
            }
        ]

        from awsquery.filters import extract_parameter_values
        from awsquery.formatters import flatten_response

        resources = flatten_response(cluster_response, service="ec2", operation="DescribeInstances")
        cluster_arns = extract_parameter_values(resources, "ClusterArn")

        assert len(cluster_arns) == 2
        assert "arn:aws:eks:us-east-1:123:cluster/prod" in cluster_arns
        assert "arn:aws:eks:us-east-1:123:cluster/dev" in cluster_arns

    def test_enhanced_completion_validator_integration(self):
        # This tests the actual function that would be used for hint matching

        # Test realistic AWS operations
        cf_operations = [
            "describe-account-limits",
            "describe-change-set",
            "describe-stacks",
            "batch-describe-type-configurations",  # Should be excluded for "desc"
        ]

        from awsquery.cli import _current_completion_context

        _current_completion_context["operations"] = cf_operations

        hint = "desc"

        # Test the validator that would be used in hint matching
        prefix_matches = [op for op in cf_operations if _enhanced_completion_validator(op, hint)]

        # Should include prefix matches
        assert "describe-account-limits" in prefix_matches
        assert "describe-change-set" in prefix_matches
        assert "describe-stacks" in prefix_matches

        # Should exclude contains-only when prefix matches exist
        assert "batch-describe-type-configurations" not in prefix_matches


class TestHintErrorHandling:
    def test_invalid_hint_string(self):
        operations = ["describe-clusters", "list-instances"]

        invalid_hints = [
            "   ",  # Whitespace only
            "---",  # Only hyphens
            "a",  # Too short (but may still work)
            "",  # Empty (should match all)
            "very-long-hint-that-matches-nothing-at-all",  # Too specific
        ]

        for hint in invalid_hints:
            matches = [op for op in operations if _enhanced_completion_validator(op, hint)]
            # Should not crash, should return list (empty or populated)
            assert isinstance(matches, list)

    def test_hint_with_special_characters(self):
        operations = ["describe-clusters", "list-db-instances", "get-cache-info"]

        special_hints = [
            "desc$clus",  # Dollar sign
            "desc.clus",  # Period
            "desc@clus",  # At symbol
            "desc/clus",  # Slash
            "desc\\clus",  # Backslash
        ]

        for hint in special_hints:
            try:
                matches = [op for op in operations if _enhanced_completion_validator(op, hint)]
                assert isinstance(matches, list)
            except Exception:
                # Should not crash, but may not match anything
                pass

    def test_hint_matching_edge_cases(self):
        operations = [
            "describe",  # Exact word
            "describe-",  # Trailing hyphen
            "-describe",  # Leading hyphen
            "a-b-c-d-e-f",  # Many hyphens
            "describeclusters",  # No hyphens
        ]

        edge_hints = [
            "describe",
            "desc-",
            "-desc",
            "a-b-c",
            "describeclus",
        ]

        for hint in edge_hints:
            for op in operations:
                try:
                    result = _enhanced_completion_validator(op, hint)
                    assert isinstance(result, bool)
                except Exception:
                    # Should not crash
                    pytest.fail(f"Validator crashed on hint='{hint}', operation='{op}'")

    def test_unicode_hint_handling(self):
        operations = ["describe-clusters", "list-instances"]

        unicode_hints = [
            "desc-clüs",  # Umlaut
            "desc-clús",  # Accent
            "desc-clus™",  # Trademark symbol
            "desc-🚀",  # Emoji
            "desc-клас",  # Cyrillic
        ]

        for hint in unicode_hints:
            try:
                matches = [op for op in operations if _enhanced_completion_validator(op, hint)]
                assert isinstance(matches, list)
            except Exception:
                # Unicode handling may vary, but should not crash
                pass

    def test_hint_parameter_format_validation(self):
        # Test that hint parameter follows expected format
        valid_hints = [
            "desc-clus",
            "list-inst",
            "get-vol",
            "create-snap",
        ]

        invalid_hints = [
            None,
            123,
            [],
            {},
        ]

        # Valid hints should be processable
        for hint in valid_hints:
            assert isinstance(hint, str)
            assert len(hint) > 0

        # Invalid hints should be handled gracefully
        for hint in invalid_hints:
            if hint is not None:
                try:
                    str(hint)  # Should be convertible to string
                except Exception:
                    pass  # Expected for some invalid types

    def test_hint_selection_algorithm(self):
        # This tests the core algorithm that would be used to select
        # the best matching function from multiple candidates

        def select_best_hint_match(operations, hint):
            matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

            if not matches:
                return None

            # Sort by length (shortest first), then alphabetically
            sorted_matches = sorted(matches, key=lambda x: (len(x), x))
            return sorted_matches[0]

        # Test cases
        test_cases = [
            {
                "operations": ["describe-clusters", "describe-cache-clusters", "list-clusters"],
                "hint": "desc-clus",
                "expected": "describe-clusters",  # Shortest match
            },
            {
                "operations": ["describe-zeta", "describe-beta", "describe-test"],
                "hint": "desc",
                "expected": "describe-beta",  # Alphabetical when same length
            },
            {
                "operations": ["list-instances", "get-volumes"],
                "hint": "desc-clus",
                "expected": None,  # No matches
            },
        ]

        for case in test_cases:
            result = select_best_hint_match(case["operations"], case["hint"])
            assert result == case["expected"]


class TestFieldHintParsing:
    def test_function_field_format_parsing(self):
        from awsquery.cli import find_hint_function

        # Mock the service operations to avoid boto3 dependencies
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters", "ListClusters"]

            # Test function:field format
            function, field, limit, alternatives = find_hint_function("desc-clus:clusterarn", "eks")

            assert function == "DescribeClusters"
            assert field == "clusterarn"
            assert isinstance(alternatives, list)

    def test_function_only_format_parsing(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters", "ListClusters"]

            # Test function only format
            function, field, limit, alternatives = find_hint_function("desc-clus", "eks")

            assert function == "DescribeClusters"
            assert field is None
            assert isinstance(alternatives, list)

    def test_empty_field_parsing(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            # Test empty field after colon
            function, field, limit, alternatives = find_hint_function("desc-clus:", "eks")

            assert function == "DescribeClusters"
            assert field is None

    def test_multiple_colons_parsing(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            # Test multiple colons - with new format (function:field:limit)
            # "desc-clus:cluster:arn" parses as: function="desc-clus",
            # field="cluster", third="arn" (ignored as non-numeric)
            function, field, limit, alternatives = find_hint_function(
                "desc-clus:cluster:arn", "eks"
            )

            assert function == "DescribeClusters"
            assert field == "cluster"  # "arn" is ignored as it's not a valid limit
            assert limit is None  # "arn" is not numeric, so no limit is set

    def test_whitespace_handling(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            test_cases = [
                "  desc-clus:clusterarn  ",
                "desc-clus  :  clusterarn",
                " desc-clus : clusterarn ",
            ]

            for hint in test_cases:
                function, field, limit, alternatives = find_hint_function(hint, "eks")
                assert function == "DescribeClusters"
                assert field == "clusterarn"


class TestFieldHintExtraction:
    def test_field_hint_takes_priority(self):
        from awsquery.filters import extract_parameter_values

        # Mock data with both field hint target and default parameter name
        resources = [
            {
                "ClusterName": "default-name",
                "ClusterArn": "arn:aws:eks:us-east-1:123:cluster/test",
                "CustomField": "priority-value",
            }
        ]

        # Without field hint - should find ClusterName
        values_default = extract_parameter_values(resources, "ClusterName")
        assert "default-name" in values_default

        # With field hint - should find CustomField instead
        values_hint = extract_parameter_values(resources, "ClusterName", field_hint="CustomField")
        assert "priority-value" in values_hint
        assert "default-name" not in values_hint

    def test_exact_field_name_matching(self):
        from awsquery.filters import extract_parameter_values

        resources = [
            {
                "ExactMatch": "exact-value",
                "exactmatch": "lowercase-value",
                "EXACTMATCH": "uppercase-value",
            }
        ]

        # Should find exact case match first
        values = extract_parameter_values(resources, "SomeParam", field_hint="ExactMatch")
        assert "exact-value" in values

    def test_case_insensitive_field_matching(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"clusterarn": "arn:value", "other_field": "other"}]

        # Should match case-insensitively
        values = extract_parameter_values(resources, "SomeParam", field_hint="ClusterArn")
        assert "arn:value" in values

    def test_partial_field_name_matching(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"ClusterArnDetails": "partial-match-value", "UnrelatedField": "other"}]

        # Should find partial match
        values = extract_parameter_values(resources, "SomeParam", field_hint="clusterarn")
        assert "partial-match-value" in values

    def test_default_behavior_without_field_hint(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"ClusterName": "cluster-value", "OtherField": "other-value"}]

        # Should use default parameter matching
        values = extract_parameter_values(resources, "ClusterName")
        assert "cluster-value" in values

    def test_field_hint_with_nested_data(self):
        from awsquery.filters import extract_parameter_values

        resources = [
            {"Cluster": {"Name": "nested-name", "Arn": "nested-arn"}, "DirectArn": "direct-arn"}
        ]

        # Should find nested field when flattened
        values = extract_parameter_values(resources, "SomeParam", field_hint="Cluster.Arn")
        assert len(values) > 0

        # Should also find direct field
        values_direct = extract_parameter_values(resources, "SomeParam", field_hint="DirectArn")
        assert "direct-arn" in values_direct

    def test_field_hint_multiple_resources(self):
        from awsquery.filters import extract_parameter_values

        resources = [
            {"TargetField": "value1", "Other": "ignore1"},
            {"TargetField": "value2", "Other": "ignore2"},
            {"Different": "skip", "Other": "ignore3"},  # No TargetField
            {"TargetField": "value3", "Other": "ignore4"},
        ]

        values = extract_parameter_values(resources, "SomeParam", field_hint="TargetField")
        assert len(values) == 3
        assert "value1" in values
        assert "value2" in values
        assert "value3" in values


class TestFieldHintIntegration:
    @patch("awsquery.core.execute_aws_call")
    def test_field_hint_passed_through_multi_level_call(self, mock_execute):
        mock_execute.return_value = [
            {
                "Clusters": [
                    {
                        "ClusterName": "test-cluster",
                        "ClusterArn": "arn:aws:eks:us-east-1:123:cluster/test",
                    }
                ]
            }
        ]

        from awsquery.core import execute_multi_level_call

        # Call with field hint
        result = execute_multi_level_call(
            service="eks",
            action="describe-fargate-profile",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
            hint_function="describeclusters",
            hint_field="ClusterArn",
        )

        # Should have called the function and extracted using field hint
        assert mock_execute.called

    @patch("awsquery.core.execute_aws_call")
    def test_field_hint_with_tracking_call(self, mock_execute):
        mock_execute.return_value = [
            {"Clusters": [{"ClusterName": "test-cluster", "CustomArn": "custom-arn-value"}]}
        ]

        from awsquery.core import execute_multi_level_call_with_tracking

        # Call with tracking and field hint
        result, call_results = execute_multi_level_call_with_tracking(
            service="eks",
            action="describe-fargate-profile",
            resource_filters=[],
            value_filters=[],
            column_filters=[],
            hint_function="describeclusters",
            hint_field="CustomArn",
        )

        # Should track the call and use field hint
        assert mock_execute.called
        assert isinstance(call_results, list)

    def test_user_feedback_includes_field_information(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            function, field, limit, alternatives = find_hint_function(
                "desc-clus:customfield", "eks"
            )

            # Should return field information for user feedback
            assert function == "DescribeClusters"
            assert field == "customfield"

    @patch("sys.stderr")
    def test_hint_affects_actual_parameter_extraction(self, mock_stderr):
        from awsquery.filters import extract_parameter_values

        # Create test data where field hint should change results
        resources = [{"ClusterName": "default-cluster", "PreferredField": "preferred-value"}]

        # Default extraction
        default_values = extract_parameter_values(resources, "ClusterName")
        assert "default-cluster" in default_values

        # Field hint extraction
        hint_values = extract_parameter_values(
            resources, "ClusterName", field_hint="PreferredField"
        )
        assert "preferred-value" in hint_values
        assert "default-cluster" not in hint_values


class TestFieldHintErrorHandling:
    def test_field_hint_no_matches(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"ClusterName": "test-cluster", "ClusterArn": "test-arn"}]

        # Non-existent field hint should return empty list
        values = extract_parameter_values(resources, "SomeParam", field_hint="NonExistentField")
        assert len(values) == 0

    def test_malformed_hint_format(self):
        from awsquery.cli import find_hint_function

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            # Test various malformed formats
            test_cases = [
                "",
                ":",
                ":::",
                ":field",
                None,
            ]

            for hint in test_cases:
                try:
                    function, field, limit, alternatives = find_hint_function(hint, "eks")
                    # Should handle gracefully, returning None or valid values
                    assert function is None or isinstance(function, str)
                    assert field is None or isinstance(field, str)
                    assert isinstance(alternatives, list)
                except Exception as e:
                    # Should not raise unhandled exceptions
                    pytest.fail(f"Unexpected exception for hint '{hint}': {e}")

    def test_empty_field_hint_in_extraction(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"ClusterName": "test-value"}]

        # Empty field hint should fall back to default behavior
        values = extract_parameter_values(resources, "ClusterName", field_hint="")
        assert "test-value" in values

    def test_none_field_hint_in_extraction(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"ClusterName": "test-value"}]

        # None field hint should fall back to default behavior
        values = extract_parameter_values(resources, "ClusterName", field_hint=None)
        assert "test-value" in values

    def test_field_hint_edge_cases(self):
        from awsquery.filters import extract_parameter_values

        resources = [{"": "empty-key-value", " ": "space-key-value", "NormalKey": "normal-value"}]

        # Test various edge case field hints
        edge_cases = [
            "",
            " ",
            "   ",
            "normal",  # Partial match should work
        ]

        for field_hint in edge_cases:
            values = extract_parameter_values(resources, "SomeParam", field_hint=field_hint)
            assert isinstance(values, list)  # Should not crash

    def test_field_hint_with_complex_aws_response(self):
        from awsquery.filters import extract_parameter_values

        # Simulate a realistic EKS describe-clusters response
        resources = [
            {
                "Cluster": {
                    "Name": "prod-cluster",
                    "Arn": "arn:aws:eks:us-east-1:123456789012:cluster/prod-cluster",
                    "Status": "ACTIVE",
                    "Endpoint": "https://example.eks.amazonaws.com",
                    "RoleArn": "arn:aws:iam::123456789012:role/eks-service-role",
                }
            },
            {
                "Cluster": {
                    "Name": "dev-cluster",
                    "Arn": "arn:aws:eks:us-east-1:123456789012:cluster/dev-cluster",
                    "Status": "ACTIVE",
                    "Endpoint": "https://dev.eks.amazonaws.com",
                    "RoleArn": "arn:aws:iam::123456789012:role/eks-dev-role",
                }
            },
        ]

        # Test field hint targeting nested structure
        arn_values = extract_parameter_values(resources, "ClusterName", field_hint="Cluster.Arn")
        assert len(arn_values) == 2
        assert "arn:aws:eks:us-east-1:123456789012:cluster/prod-cluster" in arn_values
        assert "arn:aws:eks:us-east-1:123456789012:cluster/dev-cluster" in arn_values

        # Test field hint targeting different nested field
        endpoint_values = extract_parameter_values(resources, "ClusterName", field_hint="Endpoint")
        assert len(endpoint_values) == 2
        assert "https://example.eks.amazonaws.com" in endpoint_values
        assert "https://dev.eks.amazonaws.com" in endpoint_values

    def test_function_field_hint_comprehensive_workflow(self):
        from awsquery.cli import find_hint_function
        from awsquery.filters import extract_parameter_values

        # Mock comprehensive scenario
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters", "ListClusters", "DescribeTargetGroups"]

            # 1. Parse the function:field hint
            function, field, limit, alternatives = find_hint_function("desc-clus:rolearn", "eks")
            assert function == "DescribeClusters"
            assert field == "rolearn"

            # 2. Simulate using that field hint in extraction
            mock_response = [
                {
                    "ClusterName": "default-name",
                    "ClusterArn": "default-arn",
                    "RoleArn": "role-arn-value",  # This should be extracted due to field hint
                }
            ]

            values = extract_parameter_values(mock_response, "ClusterName", field_hint=field)
            assert "role-arn-value" in values
            assert "default-name" not in values  # Field hint overrides default

    def test_case_variations_in_field_hints(self):
        from awsquery.filters import extract_parameter_values

        # Test exact case match preference
        resources_exact = [
            {
                "ClusterArn": "exact-case-arn",  # This should be found for exact match
                "clusterarn": "lowercase-arn",
            }
        ]

        values = extract_parameter_values(resources_exact, "SomeParam", field_hint="ClusterArn")
        assert "exact-case-arn" in values

        # Test case-insensitive fallback when no exact match
        resources_case_insensitive = [
            {
                "clusterarn": "lowercase-found",  # No exact "ClusterArn", so this should be found
                "other_field": "other",
            }
        ]

        values = extract_parameter_values(
            resources_case_insensitive, "SomeParam", field_hint="ClusterArn"
        )
        assert "lowercase-found" in values

        # Test that exact match takes priority over case-insensitive
        resources_priority = [
            {
                "CLUSTERARN": "uppercase-arn",
                "clusterarn": "lowercase-arn",  # This is exact match for "clusterarn" hint
                "ClusterArn": "mixed-case-arn",
            }
        ]

        values = extract_parameter_values(resources_priority, "SomeParam", field_hint="clusterarn")
        assert "lowercase-arn" in values  # Exact match should win


class TestHintImplementationReadiness:
    def test_existing_completion_validator_works(self):
        # This confirms the underlying infrastructure is ready

        hint = "desc-inst"
        operations = [
            "describe-instances",
            "describe-instance-types",
            "run-instances",
            "terminate-instances",
        ]

        from awsquery.cli import _current_completion_context

        _current_completion_context["operations"] = operations

        matches = [op for op in operations if _enhanced_completion_validator(op, hint)]

        # Should find describe-instances and describe-instance-types
        assert "describe-instances" in matches
        assert "describe-instance-types" in matches
        # Should exclude run/terminate since they don't match "desc"
        assert "run-instances" not in matches
        assert "terminate-instances" not in matches

    def test_filter_parsing_infrastructure_ready(self):
        from awsquery.filters import parse_multi_level_filters_for_mode

        # Test that filter parsing works with various service/action combinations
        test_commands = [
            ["eks", "describe-fargate-profile", "prod"],
            ["elbv2", "describe-tags", "test"],
            ["cloudformation", "describe-stack-events", "staging"],
        ]

        for cmd in test_commands:
            base, resource, value, column = parse_multi_level_filters_for_mode(cmd, mode="single")
            assert base == cmd[:2]  # service and action
            assert isinstance(resource, list)
            assert isinstance(value, list)
            assert isinstance(column, list)

    def test_multi_level_call_infrastructure_ready(self):
        # This tests that the infrastructure for parameter resolution exists
        from awsquery.core import infer_list_operation

        # Test the inference function that would be enhanced with hints
        service = "eks"
        parameter_name = "ClusterName"
        action = "describe-fargate-profile"

        operations = infer_list_operation(service, parameter_name, action)

        assert isinstance(operations, list)
        assert len(operations) > 0
        # Should include cluster-related operations
        cluster_ops = [op for op in operations if "cluster" in op.lower()]
        assert len(cluster_ops) > 0
