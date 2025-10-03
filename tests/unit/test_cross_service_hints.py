"""Tests for cross-service hint functionality."""

import os
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import find_hint_function


class TestServicePrefixParsing:
    def test_parse_service_prefix_from_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances", "RunInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst", "elbv2"
            )

            assert function == "DescribeInstances"
            assert field is None
            assert limit is None

    def test_parse_service_with_field(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst:instanceid", "elbv2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit is None

    def test_parse_service_with_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst::10", "elbv2"
            )

            assert function == "DescribeInstances"
            assert field is None
            assert limit == 10

    def test_parse_service_field_and_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst:instanceid:5", "elbv2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit == 5

    def test_backward_compat_no_service_prefix(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit is None

    def test_empty_service_prefix_uses_current_service(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeTargetGroups"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                ":arn:3", "elbv2"
            )

            assert function is None
            assert field == "arn"
            assert limit == 3

    def test_service_only_prefix_no_function(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2::instanceid:5", "elbv2"
            )

            assert hint_service == "ec2"
            assert function is None
            assert field == "instanceid"
            assert limit == 5

    def test_service_only_hint(self):
        """Test that just a service name (e.g., 'ec2') is recognized."""
        hint_service, function, field, limit, alternatives = find_hint_function(
            "ec2", "ssm"
        )

        assert hint_service == "ec2"
        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []

    def test_multiple_colons_in_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst:instanceid:10", "elbv2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit == 10


class TestCrossServiceResolution:
    @patch("botocore.session.Session")
    def test_resolve_function_in_different_service(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2", "elbv2", "eks"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeInstances",
            "DescribeSecurityGroups",
            "RunInstances",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances", "DescribeSecurityGroups"]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "ec2:desc-inst", "elbv2"
                )

                assert function == "DescribeInstances"
                assert field is None
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_resolve_eks_from_elbv2_service(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2", "elbv2", "eks"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeCluster",
            "ListClusters",
            "DescribeFargateProfile",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeCluster", "ListClusters"]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "eks:desc-clus:clusterarn:5", "elbv2"
                )

                assert function == "DescribeCluster"
                assert field == "clusterarn"
                assert limit == 5
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_multiple_matches_prefer_shortest(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeInstances",
            "DescribeInstanceTypes",
            "DescribeInstanceAttribute",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = [
                "DescribeInstances",
                "DescribeInstanceTypes",
                "DescribeInstanceAttribute",
            ]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "ec2:desc-inst", "elbv2"
                )

                assert function == "DescribeInstances"
                assert len(alternatives) >= 2
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_cross_service_with_alternatives(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["cloudformation"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeStacks",
            "DescribeStackEvents",
            "DescribeStackResources",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = [
                "DescribeStacks",
                "DescribeStackEvents",
                "DescribeStackResources",
            ]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "cloudformation:desc-stack", "ec2"
                )

                assert function == "DescribeStacks"
                assert isinstance(alternatives, list)
                assert (
                    "DescribeStackEvents" in alternatives
                    or "DescribeStackResources" in alternatives
                )
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile


class TestServiceFallbackBehavior:
    def test_no_service_prefix_uses_current_service(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"

    def test_current_service_used_when_no_service_specified(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeTargetGroups", "DescribeLoadBalancers"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-target", "elbv2"
            )

            assert function == "DescribeTargetGroups"

    def test_field_only_hint_no_function_resolution(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(
                ":instanceid:10", "ec2"
            )

            assert function is None
            assert field == "instanceid"
            assert limit == 10

    def test_limit_only_hint_no_function_or_field(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function("::5", "ec2")

            assert function is None
            assert field is None
            assert limit == 5


class TestServiceValidation:
    @patch("botocore.session.Session")
    def test_invalid_service_returns_none(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2", "elbv2", "eks"]

        mock_session_cls.return_value = mock_session

        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            hint_service, function, field, limit, alternatives = find_hint_function(
                "invalidservice:desc-inst", "elbv2"
            )

            assert function is None or function == "DescribeInstances"
        finally:
            if old_profile:
                os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_service_with_no_matching_operations(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2"]

        mock_service_model = Mock()
        mock_service_model.operation_names = ["RunInstances", "TerminateInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "ec2:desc-inst", "elbv2"
                )

                assert function is None
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    def test_empty_service_name_in_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                ":desc-inst:instanceid", "ec2"
            )

            assert function is None
            assert field == "desc-inst"
            assert limit is None

    def test_whitespace_service_name_in_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "  :desc-inst:instanceid", "ec2"
            )

            assert function is None
            assert field == "desc-inst"

    def test_none_service_input(self):
        hint_service, function, field, limit, alternatives = find_hint_function(
            "ec2:desc-inst", None
        )

        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []

    def test_empty_service_input(self):
        hint_service, function, field, limit, alternatives = find_hint_function("ec2:desc-inst", "")

        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []


class TestCrossServiceIntegration:
    @patch("botocore.session.Session")
    def test_complete_cross_service_workflow(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2", "elbv2"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeInstances",
            "DescribeSecurityGroups",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances", "DescribeSecurityGroups"]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "ec2:desc-inst:instanceid:10", "elbv2"
                )

                assert function == "DescribeInstances"
                assert field == "instanceid"
                assert limit == 10
                assert isinstance(alternatives, list)
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_cross_service_with_case_variations(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["ec2"]

        mock_service_model = Mock()
        mock_service_model.operation_names = ["DescribeInstances"]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "EC2:DESC-INST:InstanceId", "elbv2"
                )

                assert function == "DescribeInstances"
                assert field == "InstanceId"
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_cross_service_realistic_eks_scenario(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["eks"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeCluster",
            "ListClusters",
            "DescribeFargateProfile",
            "DescribeNodegroup",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = [
                "DescribeCluster",
                "ListClusters",
                "DescribeFargateProfile",
                "DescribeNodegroup",
            ]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "eks:desc-clus:arn:5", "elbv2"
                )

                assert function == "DescribeCluster"
                assert field == "arn"
                assert limit == 5
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    @patch("botocore.session.Session")
    def test_cross_service_cloudformation_scenario(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.return_value = ["cloudformation"]

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeStacks",
            "DescribeStackEvents",
            "DescribeStackResources",
            "ListStacks",
        ]
        mock_session.get_service_model.return_value = mock_service_model
        mock_session_cls.return_value = mock_session

        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = [
                "DescribeStacks",
                "DescribeStackEvents",
                "DescribeStackResources",
                "ListStacks",
            ]

            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                hint_service, function, field, limit, alternatives = find_hint_function(
                    "cloudformation:desc-stack:stackid", "ec2"
                )

                assert function == "DescribeStacks"
                assert field == "stackid"
                assert len(alternatives) >= 1
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile

    def test_service_only_cross_service(self):
        """Test service-only hint for cross-service resolution."""
        hint_service, function, field, limit, alternatives = find_hint_function(
            "ec2", "ssm"
        )

        assert hint_service == "ec2"
        assert function is None
        assert field is None
        assert limit is None
        # This will allow EC2 operations to be inferred for SSM parameters

    def test_service_only_with_field(self):
        """Test service-only hint with field specification."""
        hint_service, function, field, limit, alternatives = find_hint_function(
            "ec2::instanceid", "ssm"
        )

        assert hint_service == "ec2"
        assert function is None
        assert field == "instanceid"
        assert limit is None

    def test_backward_compatibility_existing_format(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeClusters"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-clus:arn:5", "eks"
            )

            assert function == "DescribeClusters"
            assert field == "arn"
            assert limit == 5

    def test_field_only_format_preserved(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(":arn:5", "eks")

            assert function is None
            assert field == "arn"
            assert limit == 5


class TestEdgeCasesAndErrorHandling:
    def test_none_hint(self):
        hint_service, function, field, limit, alternatives = find_hint_function(None, "ec2")

        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []

    def test_empty_hint(self):
        hint_service, function, field, limit, alternatives = find_hint_function("", "ec2")

        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []

    def test_whitespace_only_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function("   ", "ec2")

            assert function is None

    def test_colons_only_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(":::", "ec2")

            assert function is None
            assert field is None
            assert limit is None

    def test_non_numeric_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid:abc", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit is None

    def test_negative_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid:-5", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit is None

    def test_zero_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid:0", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit == 0

    def test_very_large_limit(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid:999999999", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit == 999999999

    def test_special_characters_in_service_name(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2-invalid:desc-inst", "ec2"
            )

            assert isinstance(alternatives, list)

    def test_special_characters_in_function_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc@inst:instanceid", "ec2"
            )

            assert isinstance(alternatives, list)

    def test_unicode_in_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst:ïnstanceid", "ec2"
            )

            assert field == "ïnstanceid"

    @patch("botocore.session.Session")
    def test_exception_during_service_resolution(self, mock_session_cls):
        mock_session = Mock()
        mock_session.get_available_services.side_effect = Exception("Service error")
        mock_session_cls.return_value = mock_session

        old_profile = os.environ.pop("AWS_PROFILE", None)
        try:
            hint_service, function, field, limit, alternatives = find_hint_function(
                "ec2:desc-inst", "elbv2"
            )

            assert function is None
            assert alternatives == []
        finally:
            if old_profile:
                os.environ["AWS_PROFILE"] = old_profile

    def test_limit_with_decimal(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid:5.5", "ec2"
            )

            assert function == "DescribeInstances"
            assert field == "instanceid"
            assert limit is None

    def test_empty_parts_in_hint(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function("::::", "ec2")

            assert function is None
            assert field is None
            assert limit is None


class TestReturnValueStructure:
    def test_return_tuple_structure(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            result = find_hint_function("desc-inst:instanceid:5", "ec2")

            assert isinstance(result, tuple)
            assert len(result) == 5
            hint_service, function, field, limit, alternatives = result
            assert isinstance(alternatives, list)

    def test_alternatives_list_structure(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = [
                "DescribeInstances",
                "DescribeInstanceTypes",
                "DescribeInstanceStatus",
            ]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst", "ec2"
            )

            assert isinstance(alternatives, list)
            for alt in alternatives:
                assert isinstance(alt, str)

    def test_none_values_in_return(self):
        hint_service, function, field, limit, alternatives = find_hint_function(None, None)

        assert function is None
        assert field is None
        assert limit is None
        assert alternatives == []

    def test_field_none_when_not_specified(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst", "ec2"
            )

            assert field is None

    def test_limit_none_when_not_specified(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = ["DescribeInstances"]

            hint_service, function, field, limit, alternatives = find_hint_function(
                "desc-inst:instanceid", "ec2"
            )

            assert limit is None

    def test_function_none_when_field_only(self):
        with patch("awsquery.cli.get_service_valid_operations") as mock_ops:
            mock_ops.return_value = []

            hint_service, function, field, limit, alternatives = find_hint_function(
                ":instanceid:5", "ec2"
            )

            assert function is None
            assert field == "instanceid"
            assert limit == 5
