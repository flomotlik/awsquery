"""Tests for infer_list_operation function."""

import pytest

from awsquery.core import infer_list_operation


class TestInferListOperation:
    """Comprehensive tests for operation inference logic."""

    def test_parameter_based_inference_simple(self):
        """Test parameter-based inference with simple parameter names."""
        # ClusterName -> clusters
        operations = infer_list_operation("eks", "ClusterName", "describe-cluster")
        assert "list_clusters" in operations
        assert "describe_clusters" in operations

        # StackName -> stacks
        operations = infer_list_operation("cloudformation", "StackName", "describe-stack")
        assert "list_stacks" in operations
        assert "describe_stacks" in operations

        # BucketName -> buckets
        operations = infer_list_operation("s3", "BucketName", "get-bucket-acl")
        assert "list_buckets" in operations

    def test_parameter_based_inference_with_suffixes(self):
        """Test parameter-based inference removes Name/Id/Arn suffixes."""
        # InstanceId -> instances
        operations = infer_list_operation("ec2", "InstanceId", "describe-instance-attribute")
        assert "list_instances" in operations
        assert "describe_instances" in operations

        # RoleArn -> roles
        operations = infer_list_operation("iam", "RoleArn", "get-role")
        assert "list_roles" in operations
        assert "get_roles" in operations

        # FunctionARN -> functions
        operations = infer_list_operation("lambda", "FunctionARN", "get-function")
        assert "list_functions" in operations

    def test_parameter_pluralization_rules(self):
        """Test correct pluralization of resource names."""
        # policy -> policies (y -> ies)
        operations = infer_list_operation("iam", "PolicyArn", "get-policy")
        assert "list_policies" in operations

        # instance -> instances (regular plural)
        operations = infer_list_operation("ec2", "InstanceId", "describe-instance")
        assert "list_instances" in operations

        # box -> boxes (x -> xes)
        operations = infer_list_operation("service", "BoxId", "describe-box")
        assert "list_boxes" in operations

        # bus -> buses (s -> ses)
        operations = infer_list_operation("events", "BusName", "describe-bus")
        assert "list_buses" in operations

        # match -> matches (ch -> ches)
        operations = infer_list_operation("service", "MatchId", "describe-match")
        assert "list_matches" in operations

    def test_generic_parameter_names_skip_inference(self):
        """Test that generic parameters like Name/Id/Arn skip parameter inference."""
        operations = infer_list_operation("service", "Name", "describe-something")
        # Should not have parameter-based operations, only action-based
        assert "list_somethings" in operations  # From action inference
        assert "list_names" not in operations  # Should not infer from generic "Name"

        operations = infer_list_operation("service", "Id", "get-resource")
        assert "list_resources" in operations  # From action inference
        assert "list_ids" not in operations  # Should not infer from generic "Id"

    def test_action_based_inference(self):
        """Test action-based inference as fallback."""
        # describe-instances -> instances
        operations = infer_list_operation("ec2", "Name", "describe-instances")
        assert "list_instances" in operations
        assert "describe_instances" in operations

        # get-function -> functions
        operations = infer_list_operation("lambda", "Arn", "get-function")
        assert "list_functions" in operations
        assert "get_functions" in operations

    def test_action_with_prefixes(self):
        """Test action inference handles various prefixes."""
        # create-stack -> stacks
        operations = infer_list_operation("cf", "Id", "create-stack")
        assert "list_stacks" in operations

        # update-item -> items
        operations = infer_list_operation("dynamodb", "Id", "update-item")
        assert "list_items" in operations

        # delete-bucket -> buckets
        operations = infer_list_operation("s3", "Id", "delete-bucket")
        assert "list_buckets" in operations

    def test_combined_inference_priority(self):
        """Test that parameter-based operations come before action-based."""
        operations = infer_list_operation("ec2", "VolumeId", "describe-instances")

        # Parameter-based (VolumeId -> volumes) should come first
        volume_idx = operations.index("list_volumes")
        instance_idx = operations.index("list_instances")
        assert volume_idx < instance_idx

    def test_no_duplicate_operations(self):
        """Test that operations list doesn't have duplicates."""
        operations = infer_list_operation("ec2", "InstanceId", "describe-instance")

        # Both parameter and action inference might produce "list_instances"
        # but it should appear only once
        assert operations.count("list_instances") == 1
        assert operations.count("describe_instances") == 1

    def test_edge_case_empty_parameter(self):
        """Test with empty parameter name."""
        operations = infer_list_operation("ec2", "", "describe-instances")
        # Should still get action-based operations
        assert "list_instances" in operations

    def test_edge_case_hyphenated_action(self):
        """Test actions with multiple hyphens."""
        operations = infer_list_operation("ec2", "Id", "describe-vpc-endpoints")
        assert "list_vpc_endpoints" in operations
        assert "describe_vpc_endpoints" in operations

    def test_edge_case_underscored_action(self):
        """Test actions with underscores."""
        operations = infer_list_operation("service", "Id", "describe_some_resource")
        assert "list_some_resources" in operations
        assert "describe_some_resources" in operations

    def test_all_inference_patterns(self):
        """Test all operation patterns are generated."""
        operations = infer_list_operation("service", "ResourceName", "action")

        # Parameter-based patterns
        assert "list_resources" in operations
        assert "describe_resources" in operations
        assert "get_resources" in operations

        # Singular forms for parameter
        assert "list_resource" in operations
        assert "describe_resource" in operations
        assert "get_resource" in operations

        # Action-based patterns
        assert "list_actions" in operations
        assert "describe_actions" in operations
        assert "get_actions" in operations

    def test_camelcase_parameter_handling(self):
        """Test CamelCase parameters are handled correctly."""
        operations = infer_list_operation("rds", "DBInstanceIdentifier", "describe-db-instance")

        # Should extract "DBInstance" after removing "Identifier" suffix
        assert "list_dbinstances" in operations or "list_db_instances" in operations

    def test_already_plural_resource_names(self):
        """Test resources that are already plural."""
        # addresses -> addresses (already plural)
        operations = infer_list_operation("ec2", "AddressesId", "describe-address")
        assert "list_addresses" in operations

        # instances -> instances (already plural with 's')
        operations = infer_list_operation("ec2", "InstancesName", "describe-instance")
        assert "list_instances" in operations
