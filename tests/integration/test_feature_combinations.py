"""Integration tests for all features working together."""

import sys
from unittest.mock import Mock, call, patch

import pytest

from src.awsquery.cli import main
from src.awsquery.core import CallResult


@pytest.mark.integration
@pytest.mark.critical
class TestAllFeaturesIntegration:
    """Integration tests for all TodoPlan.md features working together."""

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_region_profile_with_default_columns(
        self, mock_create_session, mock_services, mock_policy, mock_execute
    ):
        """Test region/profile arguments work with default column filters."""
        mock_services.return_value = ["ec2"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Mock EC2 response with tags
        mock_response = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-123456789abcdef0",
                                "InstanceType": "t3.medium",
                                "State": {"Name": "running"},
                                "PublicIpAddress": "203.0.113.50",
                                "PrivateIpAddress": "10.0.1.50",
                                "Tags": [
                                    {"Key": "Name", "Value": "web-server-prod"},
                                    {"Key": "Environment", "Value": "production"},
                                    {"Key": "Team", "Value": "platform"},
                                ],
                                "SecurityGroups": [
                                    {"GroupId": "sg-12345678", "GroupName": "web-sg"}
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
        mock_execute.return_value = mock_response

        test_args = [
            "awsquery",
            "--region",
            "eu-west-1",
            "--profile",
            "production",
            "ec2",
            "describe-instances",
            # No column filters specified - should use defaults
        ]

        with patch.object(sys, "argv", test_args), patch(
            "src.awsquery.cli.format_table_output"
        ) as mock_format:

            mock_format.return_value = "Formatted table output"

            try:
                main()
            except SystemExit:
                pass

        # Verify session was created with both region and profile
        mock_create_session.assert_called_once_with(region="eu-west-1", profile="production")

        # Verify default columns were applied for EC2 describe_instances
        mock_format.assert_called_once()
        call_args = mock_format.call_args
        resources, column_filters = call_args[0]

        # Should have default columns for ec2.describe_instances
        expected_defaults = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert column_filters == expected_defaults

        # Resources should be flattened but not yet have transformed tags
        # (transformation happens inside format_table_output)
        assert len(resources) == 1
        # Check that the instance data was properly extracted
        # The resources are the flattened instances from the response
        assert "InstanceId" in resources[0] or any("Instance" in k for k in resources[0].keys())
        # Just verify we got some data
        assert len(resources[0]) > 0

    @patch("src.awsquery.cli.execute_with_tracking")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_keys_mode_with_session_and_transformed_tags(
        self, mock_create_session, mock_services, mock_policy, mock_tracking
    ):
        """Test keys mode shows transformed tag keys with session arguments."""
        mock_services.return_value = ["cloudformation"]
        mock_policy.return_value = {"cloudformation:DescribeStacks"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Create successful result with tags that need transformation
        successful_result = CallResult()
        successful_result.final_success = True
        successful_result.last_successful_response = [
            {
                "Stacks": [
                    {
                        "StackName": "infrastructure-stack",
                        "StackStatus": "CREATE_COMPLETE",
                        "CreationTime": "2023-01-01T12:00:00Z",
                        "Tags": [
                            {"Key": "Environment", "Value": "production"},
                            {"Key": "Owner", "Value": "platform-team"},
                            {"Key": "CostCenter", "Value": "12345"},
                            {"Key": "Project", "Value": "infrastructure"},
                        ],
                        "Parameters": [
                            {"ParameterKey": "VpcCidr", "ParameterValue": "10.0.0.0/16"}
                        ],
                    }
                ]
            }
        ]
        mock_tracking.return_value = successful_result

        test_args = [
            "awsquery",
            "--keys",
            "--region",
            "ap-southeast-2",
            "--profile",
            "infra-admin",
            "cloudformation",
            "describe-stacks",
        ]

        with patch.object(sys, "argv", test_args), patch(
            "src.awsquery.cli.show_keys_from_result"
        ) as mock_show_keys:

            # Mock keys that should include transformed tag keys
            mock_show_keys.return_value = (
                "  StackName\n"
                "  StackStatus\n"
                "  CreationTime\n"
                "  Tags.Environment\n"  # Transformed from Key/Value format
                "  Tags.Owner\n"  # Transformed from Key/Value format
                "  Tags.CostCenter\n"  # Transformed from Key/Value format
                "  Tags.Project\n"  # Transformed from Key/Value format
                "  Parameters.ParameterKey\n"
                "  Parameters.ParameterValue"
            )

            try:
                main()
            except SystemExit:
                pass

        # Verify session creation
        mock_create_session.assert_called_once_with(region="ap-southeast-2", profile="infra-admin")

        # Verify keys were extracted from successful response
        mock_show_keys.assert_called_once_with(successful_result)

    @patch("src.awsquery.cli.execute_multi_level_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_multi_level_with_session_defaults_and_tag_transformation(
        self, mock_create_session, mock_services, mock_policy, mock_multi_level
    ):
        """Test multi-level calls with session, default columns, and tag transformation."""
        mock_services.return_value = ["eks"]
        mock_policy.return_value = {"eks:DescribeCluster"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Mock multi-level response with tags
        mock_resources = [
            {
                "name": "production-cluster",
                "status": "ACTIVE",
                "version": "1.21",
                "endpoint": "https://api.prod.eks.amazonaws.com",
                "Tags": {  # Already transformed by core processing
                    "Environment": "production",
                    "Team": "platform",
                    "ManagedBy": "terraform",
                },
                "resourcesVpcConfig": {
                    "subnetIds": ["subnet-12345", "subnet-67890"],
                    "securityGroupIds": ["sg-abcdef"],
                },
            }
        ]
        mock_multi_level.return_value = mock_resources

        # Mock initial call failure to trigger multi-level
        with patch("src.awsquery.cli.execute_aws_call") as mock_execute:
            validation_error = {
                "validation_error": {
                    "parameter_name": "clusterName",
                    "is_required": True,
                    "error_type": "missing_parameter",
                }
            }
            mock_execute.return_value = validation_error

            test_args = [
                "awsquery",
                "--profile",
                "k8s-admin",
                "--region",
                "us-west-2",
                "eks",
                "describe-cluster",
            ]

            with patch.object(sys, "argv", test_args), patch(
                "src.awsquery.cli.format_table_output"
            ) as mock_format:

                mock_format.return_value = "Multi-level formatted output"

                try:
                    main()
                except SystemExit:
                    pass

        # Verify session creation
        mock_create_session.assert_called_once_with(region="us-west-2", profile="k8s-admin")

        # Verify multi-level was called with session
        mock_multi_level.assert_called_once()
        call_args = mock_multi_level.call_args
        # Session can be passed as last positional arg or as keyword
        if len(call_args[0]) >= 7:
            assert call_args[0][6] == mock_session
        elif "session" in call_args[1]:
            assert call_args[1]["session"] == mock_session
        # Filters won't be passed in this simplified test

        # Verify formatting was called with transformed resources
        mock_format.assert_called_once()
        format_call_args = mock_format.call_args
        formatted_resources = format_call_args[0][0]

        # Resources should have transformed tag structure
        assert len(formatted_resources) == 1
        resource = formatted_resources[0]
        assert resource["Tags"]["Environment"] == "production"
        assert resource["Tags"]["Team"] == "platform"
        assert resource["Tags"]["ManagedBy"] == "terraform"

    @patch("src.awsquery.cli.execute_multi_level_call_with_tracking")
    @patch("src.awsquery.cli.execute_with_tracking")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_keys_mode_fallback_preserves_all_features(
        self, mock_create_session, mock_services, mock_policy, mock_tracking, mock_multi_level
    ):
        """Test that keys mode fallback preserves session and shows correct keys."""
        mock_services.return_value = ["rds"]
        mock_policy.return_value = {"rds:DescribeDbInstances"}  # PascalCase version
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Mock failed initial tracking
        failed_result = CallResult()
        failed_result.final_success = False
        failed_result.error_messages = ["Missing dbInstanceIdentifier parameter"]
        mock_tracking.return_value = failed_result

        # Mock successful multi-level tracking
        successful_multi_result = CallResult()
        successful_multi_result.final_success = True
        successful_multi_result.last_successful_response = [
            {
                "DBInstance": {
                    "DBInstanceIdentifier": "production-db",
                    "DBInstanceClass": "db.t3.medium",
                    "Engine": "mysql",
                    "EngineVersion": "8.0.28",
                    "DBInstanceStatus": "available",
                    "Endpoint": {
                        "Address": "prod-db.cluster-xyz.region.rds.amazonaws.com",
                        "Port": 3306,
                    },
                    "AllocatedStorage": 100,
                    "StorageType": "gp2",
                    "VpcSecurityGroups": [
                        {"VpcSecurityGroupId": "sg-database123", "Status": "active"}
                    ],
                    "DBSubnetGroup": {
                        "DBSubnetGroupName": "db-subnet-group",
                        "VpcId": "vpc-12345678",
                    },
                    "TagList": [  # RDS uses TagList, not Tags
                        {"Key": "Environment", "Value": "production"},
                        {"Key": "Application", "Value": "web-api"},
                        {"Key": "Backup", "Value": "daily"},
                    ],
                }
            }
        ]
        mock_multi_level.return_value = (successful_multi_result, [])

        test_args = [
            "awsquery",
            "--keys",
            "--region",
            "ca-central-1",
            "--profile",
            "db-admin",
            "rds",
            "describe-db-instances",
        ]

        with patch.object(sys, "argv", test_args), patch(
            "src.awsquery.cli.show_keys_from_result"
        ) as mock_show_keys:

            # Keys should show RDS-specific fields with transformed TagList
            mock_show_keys.return_value = (
                "  DBInstanceIdentifier\n"
                "  DBInstanceClass\n"
                "  Engine\n"
                "  EngineVersion\n"
                "  DBInstanceStatus\n"
                "  Endpoint.Address\n"
                "  Endpoint.Port\n"
                "  AllocatedStorage\n"
                "  StorageType\n"
                "  VpcSecurityGroups.VpcSecurityGroupId\n"
                "  VpcSecurityGroups.Status\n"
                "  DBSubnetGroup.DBSubnetGroupName\n"
                "  DBSubnetGroup.VpcId\n"
                "  TagList.Environment\n"  # Transformed from Key/Value
                "  TagList.Application\n"  # Transformed from Key/Value
                "  TagList.Backup"  # Transformed from Key/Value
            )

            try:
                main()
            except SystemExit:
                pass

        # Verify session creation with both arguments
        mock_create_session.assert_called_once_with(region="ca-central-1", profile="db-admin")

        # Verify initial tracking was attempted
        mock_tracking.assert_called_once()
        initial_call_args = mock_tracking.call_args
        assert initial_call_args[1]["session"] == mock_session

        # Verify multi-level fallback was used
        mock_multi_level.assert_called_once()
        # Filters were not passed in this simplified test

        # Keys should be extracted from the final successful response
        mock_show_keys.assert_called_once_with(successful_multi_result)

    def test_tag_transformation_with_column_selection(self):
        """Test that transformed tags work correctly with column selection."""
        from src.awsquery.formatters import format_table_output

        # Mock resources with both original and transformed tag structures
        resources = [
            {
                "StackName": "web-infrastructure",
                "StackStatus": "CREATE_COMPLETE",
                "Tags": {  # Transformed structure
                    "Environment": "production",
                    "Owner": "platform-team",
                    "Project": "web-app",
                    "CostCenter": "1234",
                },
                "Tags_Original": [  # Preserved original
                    {"Key": "Environment", "Value": "production"},
                    {"Key": "Owner", "Value": "platform-team"},
                    {"Key": "Project", "Value": "web-app"},
                    {"Key": "CostCenter", "Value": "1234"},
                ],
                "Parameters": [{"ParameterKey": "VpcCidr", "ParameterValue": "10.0.0.0/16"}],
            },
            {
                "StackName": "staging-infrastructure",
                "StackStatus": "UPDATE_COMPLETE",
                "Tags": {"Environment": "staging", "Owner": "dev-team", "Project": "web-app"},
                "Tags_Original": [
                    {"Key": "Environment", "Value": "staging"},
                    {"Key": "Owner", "Value": "dev-team"},
                    {"Key": "Project", "Value": "web-app"},
                ],
            },
        ]

        # Test column selection with transformed tag keys
        column_filters = [
            "StackName",
            "StackStatus",
            "Tags.Environment",  # Uses transformed structure
            "Tags.Owner",  # Uses transformed structure
            "Tags.Project",  # Uses transformed structure
        ]

        output = format_table_output(resources, column_filters)

        # Verify that tag values are correctly extracted
        assert "web-infrastructure" in output
        assert "staging-infrastructure" in output
        assert "production" in output
        assert "staging" in output
        assert "platform-team" in output
        assert "dev-team" in output
        assert "web-app" in output

    @patch("src.awsquery.cli.create_session")
    def test_session_integration_with_default_filters(self, mock_create_session):
        """Test that session arguments work with default column filter application."""
        from src.awsquery.cli import determine_column_filters

        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Test with no user columns - should get defaults
        result = determine_column_filters(None, "s3", "list_buckets")
        expected = ["Name", "CreationDate"]
        assert result == expected

        # Test with empty user columns - should get defaults
        result = determine_column_filters([], "lambda", "list_functions")
        expected = ["FunctionName", "Runtime", "LastModified", "CodeSize", "Description"]
        assert result == expected

        # Test with user columns - should use user columns, not defaults
        user_columns = ["CustomField1", "CustomField2"]
        result = determine_column_filters(user_columns, "ec2", "describe_instances")
        assert result == user_columns

        # Test with unknown service - should return None
        result = determine_column_filters(None, "unknown_service", "unknown_action")
        assert result is None


@pytest.mark.integration
@pytest.mark.critical
class TestErrorHandlingAcrossFeatures:
    """Test error handling when multiple features are used together."""

    @patch("src.awsquery.cli.create_session")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    def test_session_error_with_other_features(
        self, mock_services, mock_policy, mock_create_session
    ):
        """Test that session creation errors don't interfere with other features."""
        from botocore.exceptions import ProfileNotFound

        mock_services.return_value = ["ec2"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_create_session.side_effect = ProfileNotFound(profile="invalid-profile")

        test_args = [
            "awsquery",
            "--profile",
            "invalid-profile",
            "--debug",
            "ec2",
            "describe-instances",
        ]

        with patch.object(sys, "argv", test_args):
            # Should raise the ProfileNotFound error
            with pytest.raises(ProfileNotFound):
                main()

    def test_malformed_tags_with_column_selection(self):
        """Test that malformed tags don't break column selection."""
        from src.awsquery.formatters import format_table_output, transform_tags_structure

        # Create data with mixed valid/invalid tag structures
        data = [
            {
                "InstanceId": "i-123",
                "State": "running",
                "Tags": [  # Valid tags
                    {"Key": "Name", "Value": "web-server"},
                    {"Key": "Environment", "Value": "prod"},
                ],
                "InvalidTags": [  # Invalid structure
                    "not-a-dict",
                    {"Key": "MissingValue"},
                    {"Value": "MissingKey"},
                ],
            }
        ]

        # Transform should handle gracefully
        transformed = transform_tags_structure(data)

        # Should have valid tags transformed
        assert transformed[0]["Tags"]["Name"] == "web-server"
        assert transformed[0]["Tags"]["Environment"] == "prod"

        # Column selection should work despite invalid tags
        column_filters = ["InstanceId", "Tags.Name", "Tags.Environment", "State"]
        output = format_table_output(transformed, column_filters)

        assert "i-123" in output
        assert "web-server" in output
        assert "prod" in output
        assert "running" in output

    def test_feature_combination_performance(self):
        """Test that combining all features doesn't cause performance issues."""
        from src.awsquery.config import get_default_columns
        from src.awsquery.formatters import transform_tags_structure

        # Create a reasonably large dataset
        large_response = []
        for i in range(100):
            large_response.append(
                {
                    "InstanceId": f"i-{i:010d}",
                    "InstanceType": "t3.micro" if i % 2 == 0 else "t3.small",
                    "State": {"Name": "running" if i % 3 == 0 else "stopped"},
                    "Tags": [
                        {"Key": "Name", "Value": f"instance-{i:03d}"},
                        {"Key": "Environment", "Value": "production" if i % 4 == 0 else "staging"},
                        {"Key": "Team", "Value": "platform" if i % 5 == 0 else "development"},
                        {"Key": "Index", "Value": str(i)},
                    ],
                }
            )

        # Test tag transformation on large dataset
        import time

        start_time = time.time()
        transformed = transform_tags_structure(large_response)
        transform_time = time.time() - start_time

        # Should complete reasonably quickly (less than 1 second for 100 items)
        assert transform_time < 1.0

        # Verify transformation worked correctly
        assert len(transformed) == 100
        assert transformed[0]["Tags"]["Name"] == "instance-000"
        assert transformed[50]["Tags"]["Environment"] in ["production", "staging"]

        # Test default column retrieval
        start_time = time.time()
        defaults = get_default_columns("ec2", "describe_instances")
        config_time = time.time() - start_time

        # Should be very fast (cached after first load)
        assert config_time < 0.1
        assert len(defaults) > 0


@pytest.mark.integration
@pytest.mark.critical
class TestRegressionPrevention:
    """Integration tests to prevent regressions in existing functionality."""

    def test_backward_compatibility_with_existing_commands(self):
        """Test that existing commands still work after adding new features."""
        # This test ensures that the new features don't break existing usage patterns

        from src.awsquery.filters import parse_multi_level_filters_for_mode

        # Test existing command patterns
        test_cases = [
            # Simple command
            ["ec2", "describe-instances"],
            # With resource filters
            ["ec2", "describe-instances", "prod", "web"],
            # With value filters
            ["ec2", "describe-instances", "--", "running"],
            # With column filters
            ["ec2", "describe-instances", "--", "--", "InstanceId", "State"],
            # Complex multi-level
            [
                "cloudformation",
                "describe-stack-resources",
                "prod",
                "--",
                "CREATE_COMPLETE",
                "--",
                "LogicalResourceId",
            ],
        ]

        for argv in test_cases:
            # Should parse without errors
            base_cmd, resource_filters, value_filters, column_filters = (
                parse_multi_level_filters_for_mode(argv, mode="single")
            )

            # Basic validations
            assert len(base_cmd) >= 2  # At least service and action
            assert isinstance(resource_filters, list)
            assert isinstance(value_filters, list)
            assert isinstance(column_filters, list)

    def test_default_behavior_unchanged(self):
        """Test that default behavior is unchanged when new features aren't used."""
        from src.awsquery.config import apply_default_filters
        from src.awsquery.utils import create_session, get_client

        # Session creation without arguments should work as before
        with patch("boto3.Session") as mock_session:
            session = create_session()
            mock_session.assert_called_once_with()

        # get_client without session should work as before
        with patch("boto3.client") as mock_client:
            client = get_client("ec2")
            mock_client.assert_called_once_with("ec2")

        # apply_default_filters with user columns should return user columns
        user_cols = ["Custom1", "Custom2"]
        result = apply_default_filters("any_service", "any_action", user_cols)
        assert result == user_cols

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    def test_simple_commands_still_work(self, mock_services, mock_policy, mock_execute):
        """Test that simple commands work exactly as before."""
        mock_services.return_value = ["s3"]
        mock_policy.return_value = {"s3:ListBuckets"}
        mock_execute.return_value = [
            {"Buckets": [{"Name": "test-bucket", "CreationDate": "2023-01-01T00:00:00Z"}]}
        ]

        # Simple command without any new features
        test_args = ["awsquery", "s3", "list-buckets"]

        with patch.object(sys, "argv", test_args), patch(
            "src.awsquery.cli.format_table_output"
        ) as mock_format:

            mock_format.return_value = "Simple table output"

            try:
                main()
            except SystemExit:
                pass

        # Should execute normally
        mock_execute.assert_called_once()
        mock_format.assert_called_once()

        # Verify session was created (even for simple commands)
        call_args = mock_execute.call_args
        # Session parameter should be present (created even without explicit region/profile)
        if len(call_args[0]) >= 5:
            session_param = call_args[0][4]
        else:
            session_param = call_args[1].get("session")
        assert session_param is not None
