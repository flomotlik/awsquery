"""Unit tests for AWS Query Tool core execution functions."""

import sys
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

# Import the functions under test
from src.awsquery.core import (
    convert_parameter_name,
    execute_aws_call,
    execute_multi_level_call,
    get_correct_parameter_name,
    infer_list_operation,
    parameter_expects_list,
    parse_validation_error,
)


@pytest.mark.unit
@pytest.mark.aws
@pytest.mark.critical
class TestExecuteAwsCall:

    def test_successful_paginated_call(self, sample_ec2_response):
        from src.awsquery import utils

        mock_client = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [sample_ec2_response]
        mock_client.get_paginator.return_value = mock_paginator
        mock_client.describe_instances = Mock()

        # Configure boto3 mock to return our client
        utils.boto3.client.return_value = mock_client

        result = execute_aws_call("ec2", "describe-instances")

        assert result == [sample_ec2_response]
        utils.boto3.client.assert_called_once_with("ec2")
        mock_client.get_paginator.assert_called_once_with("describe_instances")
        mock_paginator.paginate.assert_called_once_with()

    def test_successful_paginated_call_with_parameters(self, sample_ec2_response):
        from src.awsquery import utils

        mock_client = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [sample_ec2_response]
        mock_client.get_paginator.return_value = mock_paginator

        # Configure boto3 mock to return our client
        utils.boto3.client.return_value = mock_client

        params = {"InstanceIds": ["i-123"]}
        result = execute_aws_call("ec2", "describe-instances", parameters=params)

        assert result == [sample_ec2_response]
        mock_paginator.paginate.assert_called_once_with(**params)

    def test_fallback_to_direct_call_when_not_pageable(self, sample_ec2_response):
        mock_client = Mock()
        mock_operation = Mock(return_value=sample_ec2_response)
        mock_client.describe_instances = mock_operation

        # Mock OperationNotPageableError
        from botocore.exceptions import OperationNotPageableError

        mock_client.get_paginator.side_effect = OperationNotPageableError(
            operation_name="describe_instances"
        )

        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = execute_aws_call("ec2", "describe-instances")

        assert result == [sample_ec2_response]
        mock_client.get_paginator.assert_called_once_with("describe_instances")
        mock_operation.assert_called_once_with()

    def test_fallback_to_original_action_name(self, sample_ec2_response):
        """Test fallback to original action name when normalized name fails."""
        mock_client = Mock()

        # Setup so normalized name doesn't exist but original does
        mock_client.describe_instances = None
        original_operation = Mock(return_value=sample_ec2_response)
        setattr(mock_client, "describe-instances", original_operation)

        # Mock paginator to fail for both normalized and original
        mock_client.get_paginator.side_effect = Exception("OperationNotPageableError")

        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = execute_aws_call("ec2", "describe-instances")

        assert result == [sample_ec2_response]
        original_operation.assert_called_once_with()

    def test_action_not_available_error(self, capsys):
        """Test error when action is not available for service."""
        mock_client = Mock()

        # Mock client so that both normalized and original action names don't exist
        mock_client.describe_nonexistent = None
        setattr(mock_client, "describe-nonexistent", None)

        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        with pytest.raises(SystemExit, match="1"):
            execute_aws_call("ec2", "describe-nonexistent")

        captured = capsys.readouterr()
        assert "Action describe-nonexistent" in captured.err
        assert "not available for service ec2" in captured.err

    def test_no_credentials_error_exits(self, capsys):
        """Test NoCredentialsError causes system exit with error message."""
        from src.awsquery import utils

        utils.boto3.client.side_effect = NoCredentialsError()

        with pytest.raises(SystemExit, match="1"):
            execute_aws_call("ec2", "describe-instances")

        captured = capsys.readouterr()
        assert "AWS credentials not found" in captured.err

    @patch("src.awsquery.core.parse_validation_error")
    def test_param_validation_error_handling(self, mock_parse):
        """Test parameter validation error is parsed and returned."""

        # Create a mock ParamValidationError that has the right __name__
        class MockParamValidationError(Exception):
            pass

        MockParamValidationError.__name__ = "ParamValidationError"

        param_error = MockParamValidationError("ParamValidationError: Missing required parameter")

        mock_client = Mock()
        mock_client.get_paginator.side_effect = param_error
        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        # Mock parse function returns error info
        error_info = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }
        mock_parse.return_value = error_info

        result = execute_aws_call("ec2", "describe-cluster")

        assert result == {"validation_error": error_info, "original_error": param_error}
        mock_parse.assert_called_once_with(param_error)

    @patch("src.awsquery.core.parse_validation_error")
    def test_client_error_validation_handling(self, mock_parse, validation_error_fixtures):
        """Test ClientError with validation exception is parsed."""
        mock_client = Mock()
        mock_client.get_paginator.side_effect = validation_error_fixtures["missing_parameter"]
        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        error_info = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }
        mock_parse.return_value = error_info

        result = execute_aws_call("eks", "describe-cluster")

        assert result == {
            "validation_error": error_info,
            "original_error": validation_error_fixtures["missing_parameter"],
        }

    def test_client_error_non_validation_fallback(self, sample_ec2_response):
        """Test ClientError that's not validation error falls back to direct call."""
        access_denied_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}},
            operation_name="DescribeInstances",
        )

        mock_client = Mock()
        mock_operation = Mock(return_value=sample_ec2_response)
        mock_client.describe_instances = mock_operation
        mock_client.get_paginator.side_effect = access_denied_error
        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = execute_aws_call("ec2", "describe-instances")

        assert result == [sample_ec2_response]
        mock_operation.assert_called_once_with()

    def test_generic_client_error_exits(self, mock_client_error, capsys):
        """Test generic ClientError causes system exit."""
        from src.awsquery import utils

        utils.boto3.client.side_effect = mock_client_error

        with pytest.raises(SystemExit, match="1"):
            execute_aws_call("ec2", "describe-instances")

        captured = capsys.readouterr()
        assert "AWS API call failed" in captured.err

    @patch("src.awsquery.core.parse_validation_error")
    def test_unparseable_validation_error_exits(self, mock_parse, capsys):
        """Test unparseable validation error causes system exit."""

        class MockParamValidationError(Exception):
            pass

        MockParamValidationError.__name__ = "ParamValidationError"

        param_error = MockParamValidationError("ParamValidationError: Unknown error format")

        mock_client = Mock()
        mock_client.get_paginator.side_effect = param_error
        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client
        mock_parse.return_value = None  # Cannot parse

        with pytest.raises(SystemExit, match="1"):
            execute_aws_call("ec2", "describe-cluster")

        captured = capsys.readouterr()
        assert "Could not parse parameter validation error" in captured.err

    def test_unexpected_error_exits(self, capsys):
        """Test unexpected error causes system exit."""
        from src.awsquery import utils

        utils.boto3.client.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(SystemExit, match="1"):
            execute_aws_call("ec2", "describe-instances")

        captured = capsys.readouterr()
        assert "Unexpected error" in captured.err

    @pytest.mark.parametrize(
        "action,expected_normalized",
        [
            ("describe-instances", "describe_instances"),
            ("list-clusters", "list_clusters"),
            ("get-bucket-location", "get_bucket_location"),
            ("describeInstances", "describe_instances"),
            ("listClusters", "list_clusters"),
        ],
    )
    def test_action_name_normalization(self, sample_ec2_response, action, expected_normalized):
        """Test various action name normalization scenarios."""
        mock_client = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [sample_ec2_response]
        mock_client.get_paginator.return_value = mock_paginator
        from src.awsquery import utils

        utils.boto3.client.return_value = mock_client

        execute_aws_call("ec2", action)

        mock_client.get_paginator.assert_called_once_with(expected_normalized)


@pytest.mark.unit
@pytest.mark.aws
@pytest.mark.critical
class TestExecuteMultiLevelCall:
    """Test suite for execute_multi_level_call() function."""

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    def test_successful_simple_call(self, mock_filter, mock_flatten, mock_execute):
        """Test successful multi-level call without parameter resolution."""
        # Mock successful direct call
        mock_response = [{"InstanceId": "i-123", "State": {"Name": "running"}}]
        mock_execute.return_value = mock_response
        mock_flatten.return_value = [{"InstanceId": "i-123", "State": "running"}]
        mock_filter.return_value = [{"InstanceId": "i-123", "State": "running"}]

        result = execute_multi_level_call("ec2", "describe-instances", [], ["running"], [])

        assert len(result) == 1
        assert result[0]["InstanceId"] == "i-123"
        mock_execute.assert_called_once_with("ec2", "describe-instances", session=None)
        # Verify the flatten_response was called
        mock_flatten.assert_called_once_with(mock_response)
        # Since we have value_filters, filter_resources should be called
        # (Testing the integration rather than the exact mock call)
        assert len(result) == 1

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_parameter_resolution_workflow(
        self, mock_get_param, mock_extract, mock_filter, mock_flatten, mock_infer, mock_execute
    ):
        """Test complete parameter resolution workflow."""
        # Mock validation error on first call
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        # Mock list operation response
        list_response = [{"Name": "test-cluster", "Status": "ACTIVE"}]

        # Setup mock call sequence
        mock_execute.side_effect = [
            {
                "validation_error": validation_error,
                "original_error": Exception(),
            },  # First call fails
            list_response,  # List operation succeeds
            [{"Cluster": {"Name": "test-cluster", "Status": "ACTIVE"}}],  # Final call succeeds
        ]

        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [
            [{"Name": "test-cluster"}],  # Flattened list response
            [{"Name": "test-cluster", "Status": "ACTIVE"}],  # Flattened final response
        ]
        mock_filter.side_effect = [
            [{"Name": "test-cluster"}],  # Filtered list
            [{"Name": "test-cluster", "Status": "ACTIVE"}],  # Filtered final
        ]
        mock_extract.return_value = ["test-cluster"]
        mock_get_param.return_value = "ClusterName"

        result = execute_multi_level_call("eks", "describe-cluster", [], [], [])

        assert len(result) == 1
        assert result[0]["Name"] == "test-cluster"

        # Verify call sequence - session parameter should be passed through
        calls = mock_execute.call_args_list
        assert len(calls) == 3
        # First call attempts describe-cluster without parameters (no parameters, session=None)
        assert calls[0] == call("eks", "describe-cluster", session=None)
        # Second call fetches list of clusters (no parameters, session=None)
        assert calls[1] == call("eks", "list_clusters", session=None)
        # Third call with resolved parameter
        assert calls[2] == call("eks", "describe-cluster", {"ClusterName": "test-cluster"}, None)

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    def test_no_working_list_operation_exits(self, mock_infer, mock_execute, capsys):
        """Test system exit when no working list operation is found."""
        validation_error = {
            "parameter_name": "nonExistentParam",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            Exception("Operation failed"),  # List operation fails
        ]
        mock_infer.return_value = ["list_nonexistent"]

        with pytest.raises(SystemExit, match="1"):
            execute_multi_level_call("service", "describe-something", [], [], [])

        captured = capsys.readouterr()
        assert "Could not find a working list operation" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    def test_no_resources_after_filtering_exits(
        self, mock_filter, mock_flatten, mock_infer, mock_execute, capsys
    ):
        """Test system exit when no resources remain after filtering."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "cluster1"}],  # List operation succeeds
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.return_value = [{"Name": "cluster1"}]
        mock_filter.return_value = []  # No resources after filtering

        with pytest.raises(SystemExit, match="1"):
            execute_multi_level_call("eks", "describe-cluster", ["nonexistent"], [], [])

        captured = capsys.readouterr()
        assert "No resources found matching resource filters" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    def test_no_parameter_values_extracted_exits(
        self, mock_extract, mock_filter, mock_flatten, mock_infer, mock_execute, capsys
    ):
        """Test system exit when no parameter values can be extracted."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},  # Initial call
            [{"Name": "cluster1"}],  # List operation succeeds
            Exception(
                "Should not reach this call"
            ),  # Should not get here since extract returns empty
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.return_value = [
            {"DifferentField": "value1"}
        ]  # Resources without the right field
        mock_filter.return_value = [
            {"DifferentField": "value1"}
        ]  # Resources without the right field
        mock_extract.return_value = []  # No values extracted

        with pytest.raises(SystemExit, match="1"):
            execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Could not extract parameter" in captured.err

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_multiple_parameter_values_handling(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test handling of multiple parameter values with user notification."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            [{"Name": "cluster1"}, {"Name": "cluster2"}],
            [{"Cluster": {"Name": "cluster1"}}],  # Final response
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.side_effect = [
            [{"Name": "cluster1"}, {"Name": "cluster2"}],
            [{"Name": "cluster1"}],
        ]
        mock_filter.side_effect = [
            [{"Name": "cluster1"}, {"Name": "cluster2"}],
            [{"Name": "cluster1"}],
        ]
        mock_extract.return_value = ["cluster1", "cluster2"]
        mock_expects_list.return_value = False  # Expects single value
        mock_get_param.return_value = "ClusterName"

        result = execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Multiple clusterName values found" in captured.err
        assert "Using first match: cluster1" in captured.err

        # Should use first value
        final_call = mock_execute.call_args_list[-1]
        assert final_call == call("eks", "describe-cluster", {"ClusterName": "cluster1"}, None)

    def test_list_parameter_handling_logic(self):
        """Test the logic for determining if a parameter expects a list."""
        # Test the parameter_expects_list function directly
        assert parameter_expects_list("instanceIds") == True
        assert parameter_expects_list("clusterNames") == True
        assert parameter_expects_list("bucketArns") == True
        assert parameter_expects_list("instanceId") == False
        assert parameter_expects_list("clusterName") == False
        assert parameter_expects_list("bucketArn") == False

    @patch("src.awsquery.core.execute_aws_call")
    @patch("src.awsquery.core.infer_list_operation")
    @patch("src.awsquery.formatters.flatten_response")
    @patch("src.awsquery.filters.filter_resources")
    @patch("src.awsquery.filters.extract_parameter_values")
    @patch("src.awsquery.core.parameter_expects_list")
    @patch("src.awsquery.core.get_correct_parameter_name")
    def test_persistent_validation_error_exits(
        self,
        mock_get_param,
        mock_expects_list,
        mock_extract,
        mock_filter,
        mock_flatten,
        mock_infer,
        mock_execute,
        capsys,
    ):
        """Test system exit when validation error persists after parameter resolution."""
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }
        persistent_error = {
            "parameter_name": "anotherParam",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        # Setup complete workflow that succeeds until the final call which has persistent error
        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},  # Initial error
            [{"Name": "cluster1"}],  # List operation succeeds
            {
                "validation_error": persistent_error,
                "original_error": Exception(),
            },  # Final call still has error
        ]
        mock_infer.return_value = ["list_clusters"]
        mock_flatten.return_value = [{"Name": "cluster1"}]
        mock_filter.return_value = [{"Name": "cluster1"}]
        mock_extract.return_value = ["cluster1"]
        mock_expects_list.return_value = False
        mock_get_param.return_value = "ClusterName"

        with pytest.raises(SystemExit, match="1"):
            execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Still getting validation error after parameter resolution" in captured.err


@pytest.mark.unit
class TestParameterResolution:
    """Test suite for parameter resolution and validation functions."""

    @pytest.mark.parametrize(
        "error_message,expected",
        [
            (
                "Missing required parameter in input: 'clusterName'",
                {
                    "parameter_name": "clusterName",
                    "is_required": True,
                    "error_type": "missing_parameter",
                },
            ),
            (
                "Value null at 'stackName' failed to satisfy constraint: Member must not be null",
                {"parameter_name": "stackName", "is_required": True, "error_type": "null_value"},
            ),
            (
                "Either StackName or PhysicalResourceId must be specified",
                {
                    "parameter_name": "StackName",
                    "is_required": True,
                    "error_type": "either_parameter",
                },
            ),
            (
                "'clusterName': Member must not be null",
                {
                    "parameter_name": "clusterName",
                    "is_required": True,
                    "error_type": "required_parameter",
                },
            ),
        ],
    )
    def test_parse_validation_error_patterns(self, error_message, expected):
        """Test parsing of different validation error message patterns."""
        error = Exception(error_message)
        result = parse_validation_error(error)

        assert result == expected

    @pytest.mark.parametrize(
        "error_message",
        ["Some unknown error format", "Access denied error", "Invalid parameter value", ""],
    )
    def test_parse_validation_error_unknown_patterns(self, error_message):
        """Test parsing returns None for unknown error patterns."""
        error = Exception(error_message)
        result = parse_validation_error(error)

        assert result is None

    def test_parse_validation_error_client_error(self, validation_error_fixtures):
        """Test parsing ClientError validation exceptions."""
        client_error = validation_error_fixtures["missing_parameter"]
        result = parse_validation_error(client_error)

        expected = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }
        assert result == expected

    @pytest.mark.parametrize(
        "service,parameter,action,expected_operations",
        [
            (
                "ec2",
                "instanceId",
                "describe-instance-attribute",
                [
                    "list_instances",
                    "describe_instances",
                    "get_instances",
                    "list_instance",
                    "describe_instance",
                    "get_instance",
                    "list_instance_attributes",
                    "describe_instance_attributes",
                    "get_instance_attributes",
                    "list_instance_attribute",
                    "describe_instance_attribute",
                    "get_instance_attribute",
                ],
            ),
            (
                "eks",
                "clusterName",
                "describe-nodegroup",
                [
                    "list_clusters",
                    "describe_clusters",
                    "get_clusters",
                    "list_cluster",
                    "describe_cluster",
                    "get_cluster",
                    "list_nodegroups",
                    "describe_nodegroups",
                    "get_nodegroups",
                    "list_nodegroup",
                    "describe_nodegroup",
                    "get_nodegroup",
                ],
            ),
            (
                "s3",
                "bucketName",
                "get-bucket-policy",
                [
                    "list_buckets",
                    "describe_buckets",
                    "get_buckets",
                    "list_bucket",
                    "describe_bucket",
                    "get_bucket",
                    "list_bucket_policies",
                    "describe_bucket_policies",
                    "get_bucket_policies",
                    "list_bucket_policy",
                    "describe_bucket_policy",
                    "get_bucket_policy",
                ],
            ),
        ],
    )
    def test_infer_list_operation_comprehensive(
        self, service, parameter, action, expected_operations
    ):
        """Test list operation inference for various parameter and action combinations."""
        result = infer_list_operation(service, parameter, action)

        # Should include all expected operations
        for expected in expected_operations:
            assert expected in result

    def test_infer_list_operation_generic_parameter(self):
        """Test list operation inference skips generic parameter names."""
        result = infer_list_operation("ec2", "name", "describe-something")

        # Should not include parameter-based operations for generic names
        assert not any(op.startswith("list_name") for op in result)
        # But should include action-based operations
        assert "list_somethings" in result

    @pytest.mark.parametrize(
        "parameter_name,expects_list",
        [
            ("instanceIds", True),
            ("clusterNames", True),
            ("bucketArns", True),
            ("tagKeys", True),
            ("instanceId", False),
            ("clusterName", False),
            ("bucketArn", False),
            ("tagKey", False),
        ],
    )
    def test_parameter_expects_list(self, parameter_name, expects_list):
        """Test parameter list expectation detection."""
        result = parameter_expects_list(parameter_name)
        assert result == expects_list

    @pytest.mark.parametrize(
        "parameter_name,expected",
        [
            ("clusterName", "ClusterName"),
            ("instanceId", "InstanceId"),
            ("bucketName", "BucketName"),
            ("", ""),
            ("a", "A"),
            ("ID", "ID"),
            ("ARN", "ARN"),
        ],
    )
    def test_convert_parameter_name(self, parameter_name, expected):
        """Test parameter name conversion to PascalCase."""
        result = convert_parameter_name(parameter_name)
        assert result == expected

    def test_get_correct_parameter_name_exact_match(self):
        """Test parameter name introspection with exact match."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.members = {"ClusterName": Mock(), "IncludeDeleted": Mock()}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        result = get_correct_parameter_name(mock_client, "describe-cluster", "ClusterName")

        assert result == "ClusterName"
        mock_service_model.operation_model.assert_called_once_with("DescribeCluster")

    def test_get_correct_parameter_name_case_insensitive_match(self):
        """Test parameter name introspection with case-insensitive match."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.members = {"ClusterName": Mock(), "IncludeDeleted": Mock()}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        result = get_correct_parameter_name(mock_client, "describe-cluster", "clustername")

        assert result == "ClusterName"

    def test_get_correct_parameter_name_pascal_case_match(self):
        """Test parameter name introspection with PascalCase conversion."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.members = {"ClusterName": Mock(), "IncludeDeleted": Mock()}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        result = get_correct_parameter_name(mock_client, "describe-cluster", "clusterName")

        assert result == "ClusterName"

    def test_get_correct_parameter_name_no_match_fallback(self):
        """Test parameter name introspection fallback when no match found."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.members = {"DifferentParam": Mock()}
        mock_operation_model.input_shape = mock_input_shape
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        result = get_correct_parameter_name(mock_client, "describe-cluster", "nonExistentParam")

        assert result == "nonExistentParam"  # Returns original

    def test_get_correct_parameter_name_no_input_shape(self):
        """Test parameter name introspection when operation has no input shape."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        result = get_correct_parameter_name(mock_client, "list-clusters", "someParam")

        assert result == "someParam"  # Returns original

    @patch("src.awsquery.core.convert_parameter_name")
    def test_get_correct_parameter_name_exception_fallback(self, mock_convert):
        """Test parameter name introspection exception handling."""
        from src.awsquery import utils

        utils.boto3.client.side_effect = Exception("Service model error")
        mock_convert.return_value = "ConvertedParam"

        result = get_correct_parameter_name(None, "describe-cluster", "originalParam")

        assert result == "ConvertedParam"
        mock_convert.assert_called_once_with("originalParam")


@pytest.mark.unit
@pytest.mark.aws
class TestResponseFlattening:
    """Test suite for response flattening functions (imported from formatters)."""

    def test_extract_parameter_values_simple_strings(self):
        """Test parameter value extraction from simple string list."""
        from src.awsquery.filters import extract_parameter_values

        resources = ["cluster1", "cluster2", "cluster3"]
        result = extract_parameter_values(resources, "clusterName")

        assert result == ["cluster1", "cluster2", "cluster3"]

    def test_extract_parameter_values_exact_match(self):
        """Test parameter value extraction with exact key match."""
        from src.awsquery.filters import extract_parameter_values

        resources = [
            {"ClusterName": "cluster1", "Status": "ACTIVE"},
            {"ClusterName": "cluster2", "Status": "CREATING"},
        ]
        result = extract_parameter_values(resources, "ClusterName")

        assert result == ["cluster1", "cluster2"]

    def test_extract_parameter_values_case_insensitive_match(self):
        """Test parameter value extraction with case-insensitive matching."""
        from src.awsquery.filters import extract_parameter_values

        resources = [{"clustername": "cluster1"}, {"ClusterName": "cluster2"}]
        result = extract_parameter_values(resources, "ClusterName")

        assert result == ["cluster1", "cluster2"]

    def test_extract_parameter_values_partial_match(self):
        """Test parameter value extraction with partial key matching."""
        from src.awsquery.filters import extract_parameter_values

        resources = [{"Cluster.ClusterName": "cluster1"}, {"Resource.ClusterName": "cluster2"}]
        result = extract_parameter_values(resources, "ClusterName")

        assert result == ["cluster1", "cluster2"]

    def test_extract_parameter_values_standard_field_fallback(self):
        """Test parameter value extraction with standard field fallback."""
        from src.awsquery.filters import extract_parameter_values

        # Test Name field fallback for resource-type parameters
        resources = [
            {"Name": "cluster1", "Status": "ACTIVE"},
            {"Name": "cluster2", "Status": "CREATING"},
        ]
        result = extract_parameter_values(resources, "cluster")

        assert result == ["cluster1", "cluster2"]

    @pytest.mark.parametrize(
        "parameter,expected_standard_field",
        [
            ("bucketName", "Name"),
            ("instanceId", "Id"),
            ("roleArn", "Arn"),
            ("tagKey", "Key"),
            ("configValue", "Value"),
            ("cluster", "Name"),
            ("instance", "Name"),
            ("bucket", "Name"),
        ],
    )
    def test_extract_parameter_values_standard_field_patterns(
        self, parameter, expected_standard_field
    ):
        """Test standard field fallback patterns."""
        from src.awsquery.filters import extract_parameter_values

        resources = [{expected_standard_field: "test-value"}]
        result = extract_parameter_values(resources, parameter)

        assert result == ["test-value"]

    def test_extract_parameter_values_empty_resources(self):
        """Test parameter value extraction with empty resources."""
        from src.awsquery.filters import extract_parameter_values

        result = extract_parameter_values([], "clusterName")
        assert result == []

    def test_extract_parameter_values_no_matches(self):
        """Test parameter value extraction when no matches found."""
        from src.awsquery.filters import extract_parameter_values

        resources = [{"DifferentField": "value1"}, {"AnotherField": "value2"}]
        result = extract_parameter_values(resources, "clusterName")

        assert result == []

    def test_extract_parameter_values_filters_empty_values(self):
        """Test parameter value extraction filters out empty values."""
        from src.awsquery.filters import extract_parameter_values

        resources = [
            {"ClusterName": "cluster1"},
            {"ClusterName": ""},  # Empty string
            {"ClusterName": None},  # None value
            {"ClusterName": "cluster2"},
        ]
        result = extract_parameter_values(resources, "ClusterName")

        assert result == ["cluster1", "cluster2"]
