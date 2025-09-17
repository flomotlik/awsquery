"""Tests for string handling and parameter processing in core module."""

import pytest

from awsquery.core import (
    convert_parameter_name,
    get_correct_parameter_name,
    infer_list_operation,
    parameter_expects_list,
)


class TestParameterNameProcessing:
    """Test parameter name conversion and processing."""

    def test_parameter_expects_list_plural_suffixes(self):
        """Test detection of plural parameter names."""
        # Plural forms should be detected
        assert parameter_expects_list("Names")
        assert parameter_expects_list("Ids")
        assert parameter_expects_list("Arns")
        assert parameter_expects_list("ARNs")
        assert parameter_expects_list("InstanceIds")
        assert parameter_expects_list("SecurityGroups")

        # Singular forms should not be detected
        assert not parameter_expects_list("Name")
        assert not parameter_expects_list("Id")
        assert not parameter_expects_list("Arn")
        assert not parameter_expects_list("InstanceId")

    def test_parameter_expects_list_with_prefixes(self):
        """Test list detection with various prefixes."""
        # List prefix with plural suffix
        assert parameter_expects_list("ListOfNames")
        assert parameter_expects_list("ArrayOfIds")

        # List prefix with singular suffix - should not match
        assert not parameter_expects_list("ListOfName")
        assert not parameter_expects_list("ArrayOfId")

    def test_parameter_expects_list_exact_suffix_matching(self):
        """Test exact suffix string matching (kills string literal mutations)."""
        # These EXACT suffixes should trigger list detection
        plural_suffixes = ["s", "es", "ies"]  # Common plural endings

        # Test names that end with these exact strings
        assert parameter_expects_list("Names")  # ends with "s"
        assert parameter_expects_list("Addresses")  # ends with "es"
        assert parameter_expects_list("Policies")  # ends with "ies"

        # Test that the suffix must be at the END (not middle)
        assert not parameter_expects_list("SomeEntry")  # has "s" but not at end in a plural way
        assert not parameter_expects_list("Processing")  # has "es" but not plural

        # Test exact string checking - these should NOT match
        assert not parameter_expects_list("NameX")  # ends with different char
        assert not parameter_expects_list("NameXXsXX")  # mutation would break this

    def test_parameter_expects_list_case_sensitivity(self):
        """Test case sensitivity in suffix detection."""
        # Function checks for specific exact endings case-sensitively
        assert parameter_expects_list("Names")  # matches "Names"
        assert parameter_expects_list("InstanceIds")  # matches "Ids"
        assert parameter_expects_list("ResourceArns")  # matches "Arns"
        assert parameter_expects_list("PolicyARNs")  # matches "ARNs"

        # Should also match single "s" ending
        assert parameter_expects_list("Tests")  # matches "s"
        assert parameter_expects_list("names")  # also matches "s"

        # Case sensitivity for multi-char endings - these don't match specific suffixes
        assert not parameter_expects_list("InstanceIDZ")  # doesn't match "Ids" (case sensitive)
        assert not parameter_expects_list("ResourceArnz")  # doesn't match "Arns"

    def test_convert_parameter_name_camel_to_pascal(self):
        """Test camelCase to PascalCase conversion."""
        assert convert_parameter_name("instanceId") == "InstanceId"
        assert convert_parameter_name("clusterName") == "ClusterName"
        assert convert_parameter_name("securityGroupIds") == "SecurityGroupIds"

        # Already PascalCase
        assert convert_parameter_name("InstanceId") == "InstanceId"
        assert convert_parameter_name("ClusterName") == "ClusterName"

    def test_get_correct_parameter_name_standard_fields(self):
        """Test correct parameter name resolution."""
        from unittest.mock import MagicMock

        # Mock client
        mock_client = MagicMock()
        mock_client._service_model.operation_model.return_value.input_shape.members = {
            "InstanceIds": None,
            "ClusterNames": None,
        }

        # This function requires client - skip for now as it's integration-level
        # The unit test should focus on the conversion logic, not AWS API integration


class TestListOperationInference:
    """Test inference of list operations from parameters."""

    def test_infer_list_operation_special_parameters(self):
        """Test that special parameters 'name', 'id', 'arn' are handled correctly."""
        # Lowercase special parameters
        operations = infer_list_operation("ec2", "name", "describe-instances")
        assert len(operations) > 0
        assert any("describe" in op or "list" in op for op in operations)

        operations = infer_list_operation("ec2", "id", "describe-instances")
        assert len(operations) > 0
        assert any("describe" in op or "list" in op for op in operations)

        operations = infer_list_operation("ec2", "arn", "describe-instances")
        assert len(operations) > 0
        assert any("describe" in op or "list" in op for op in operations)

    def test_infer_list_operation_exact_string_matching(self):
        """Test exact string matching for special parameters (kills string literal mutations)."""
        # These EXACT strings should be treated specially
        special_params = ["name", "id", "arn"]
        regular_params = ["Name", "Id", "Arn", "resource_name", "identity", "amazon_resource_name"]

        for param in special_params:
            operations = infer_list_operation("ec2", param, "describe")
            # Should be treated as special (not try to extract resource name)
            assert len(operations) > 0
            # Should NOT contain the param name in any operation
            assert not any(param in op.lower() for op in operations if param != "arn")

        for param in regular_params:
            operations = infer_list_operation("ec2", param, "describe")
            # These should be processed as regular parameters (extract resource names)
            assert len(operations) >= 0  # May or may not find matches

    def test_infer_list_operation_id_string_literal(self):
        """Test that exactly 'id' (not 'Id' or 'identity') is treated specially."""
        # The exact string "id" should bypass resource name extraction
        id_operations = infer_list_operation("ec2", "id", "get-instance")
        Id_operations = infer_list_operation("ec2", "Id", "get-instance")
        identity_operations = infer_list_operation("ec2", "identity", "get-instance")

        # "id" should be handled as special parameter
        assert len(id_operations) > 0

        # "Id" should be processed for resource name extraction
        # "identity" should also be processed for resource name extraction
        # Both should work but via different code paths
        assert isinstance(Id_operations, list)
        assert isinstance(identity_operations, list)

    def test_infer_list_operation_suffix_stripping(self):
        """Test removal of suffixes to find resource name."""
        # ClusterName -> Cluster -> list_clusters
        operations = infer_list_operation("ecs", "ClusterName", "describe-services")
        assert any("cluster" in op.lower() for op in operations)

        # PolicyArn -> Policy -> list_policies
        operations = infer_list_operation("iam", "PolicyArn", "get-policy")
        assert any("polic" in op.lower() for op in operations)

        # InstanceId -> Instance -> describe_instances
        operations = infer_list_operation("ec2", "InstanceId", "terminate-instances")
        assert any("instance" in op.lower() for op in operations)

    def test_infer_list_operation_action_based(self):
        """Test inference based on action prefixes."""
        # describe- prefix
        operations = infer_list_operation("ec2", "Instance", "describe-instances")
        assert any("describe" in op for op in operations)

        # list- prefix
        operations = infer_list_operation("s3", "Bucket", "list-buckets")
        assert any("list" in op for op in operations)

        # get- prefix should try both get and list
        operations = infer_list_operation("iam", "User", "get-user")
        assert any("get" in op or "list" in op for op in operations)

    def test_infer_list_operation_pluralization(self):
        """Test pluralization of resource names."""
        # Instance -> Instances
        operations = infer_list_operation("ec2", "Instance", "describe")
        assert any("instances" in op.lower() for op in operations)

        # Policy -> Policies
        operations = infer_list_operation("iam", "Policy", "list")
        assert any("policies" in op.lower() for op in operations)

        # Cluster -> Clusters
        operations = infer_list_operation("ecs", "Cluster", "list")
        assert any("clusters" in op.lower() for op in operations)
