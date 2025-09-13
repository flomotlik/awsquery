"""Core pytest fixtures for AWS Query Tool testing."""

import json
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

# Mock boto3 before any other imports
mock_boto3 = Mock()
mock_boto3.Session = Mock()
sys.modules["boto3"] = mock_boto3


@pytest.fixture(autouse=True)
def reset_boto3_mock():
    """Reset boto3 mock before each test."""
    mock_boto3.client.reset_mock()
    mock_boto3.Session.reset_mock()
    mock_boto3.client.side_effect = None
    mock_boto3.client.return_value = Mock()
    yield


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client with AWS operation responses."""
    mock_client = Mock()
    mock_client.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-1234567890abcdef0",
                        "InstanceType": "t2.micro",
                        "State": {"Name": "running"},
                        "Tags": [{"Key": "Name", "Value": "test-instance"}],
                        "PublicIpAddress": "203.0.113.12",
                        "PrivateIpAddress": "10.0.0.5",
                        "SecurityGroups": [{"GroupId": "sg-12345", "GroupName": "default"}],
                    }
                ]
            }
        ],
        "ResponseMetadata": {"RequestId": "test-request-id"},
    }

    mock_client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "test-bucket-1", "CreationDate": "2023-01-01T00:00:00Z"},
            {"Name": "test-bucket-2", "CreationDate": "2023-01-02T00:00:00Z"},
        ],
        "Owner": {"DisplayName": "test-user", "ID": "test-owner-id"},
        "ResponseMetadata": {"RequestId": "test-request-id"},
    }

    mock_client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "test-stack",
                "StackStatus": "CREATE_COMPLETE",
                "CreationTime": "2023-01-01T00:00:00Z",
                "Tags": [{"Key": "Environment", "Value": "test"}],
            }
        ],
        "ResponseMetadata": {"RequestId": "test-request-id"},
    }
    mock_paginator = Mock()
    mock_paginator.paginate.return_value = [mock_client.describe_instances.return_value]
    mock_client.get_paginator.return_value = mock_paginator
    mock_service_model = Mock()
    mock_operation_model = Mock()
    mock_input_shape = Mock()
    mock_input_shape.members = {
        "InstanceIds": Mock(),
        "Filters": Mock(),
        "MaxResults": Mock(),
        "NextToken": Mock(),
    }
    mock_operation_model.input_shape = mock_input_shape
    mock_service_model.operation_model.return_value = mock_operation_model
    mock_service_model.operation_names = ["DescribeInstances", "ListBuckets", "DescribeStacks"]
    mock_client.meta.service_model = mock_service_model

    return mock_client


@pytest.fixture
def sample_ec2_response():
    return {
        "Reservations": [
            {
                "ReservationId": "r-1234567890abcdef0",
                "Instances": [
                    {
                        "InstanceId": "i-1234567890abcdef0",
                        "InstanceType": "t2.micro",
                        "State": {"Name": "running", "Code": 16},
                        "PublicIpAddress": "203.0.113.12",
                        "PrivateIpAddress": "10.0.0.5",
                        "SecurityGroups": [{"GroupId": "sg-12345678", "GroupName": "default"}],
                        "Tags": [
                            {"Key": "Name", "Value": "web-server-01"},
                            {"Key": "Environment", "Value": "production"},
                            {"Key": "Project", "Value": "webapp"},
                        ],
                        "NetworkInterfaces": [
                            {
                                "NetworkInterfaceId": "eni-12345678",
                                "SubnetId": "subnet-12345678",
                                "VpcId": "vpc-12345678",
                                "PrivateIpAddress": "10.0.0.5",
                            }
                        ],
                    },
                    {
                        "InstanceId": "i-abcdef1234567890",
                        "InstanceType": "t3.small",
                        "State": {"Name": "stopped", "Code": 80},
                        "Tags": [
                            {"Key": "Name", "Value": "web-server-02"},
                            {"Key": "Environment", "Value": "staging"},
                        ],
                        "SecurityGroups": [{"GroupId": "sg-87654321", "GroupName": "web-sg"}],
                    },
                ],
            }
        ],
        "ResponseMetadata": {
            "RequestId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "HTTPStatusCode": 200,
        },
    }


@pytest.fixture
def sample_s3_response():
    return {
        "Buckets": [
            {"Name": "production-logs-bucket", "CreationDate": "2023-01-15T10:30:00Z"},
            {"Name": "staging-backup-bucket", "CreationDate": "2023-02-20T14:45:00Z"},
            {"Name": "development-assets", "CreationDate": "2023-03-10T09:15:00Z"},
        ],
        "Owner": {"DisplayName": "test-aws-user", "ID": "1234567890abcdef1234567890abcdef12345678"},
        "ResponseMetadata": {
            "RequestId": "b2c3d4e5-f6g7-8901-bcde-f23456789012",
            "HTTPStatusCode": 200,
        },
    }


@pytest.fixture
def sample_cloudformation_response():
    return {
        "Stacks": [
            {
                "StackName": "production-infrastructure",
                "StackStatus": "CREATE_COMPLETE",
                "CreationTime": "2023-01-01T12:00:00Z",
                "LastUpdatedTime": "2023-06-15T10:30:00Z",
                "StackStatusReason": "Stack successfully created",
                "Parameters": [
                    {"ParameterKey": "Environment", "ParameterValue": "production"},
                    {"ParameterKey": "InstanceType", "ParameterValue": "t3.medium"},
                ],
                "Tags": [
                    {"Key": "Owner", "Value": "infrastructure-team"},
                    {"Key": "Environment", "Value": "production"},
                    {"Key": "CostCenter", "Value": "1234"},
                ],
                "Outputs": [
                    {
                        "OutputKey": "VPCId",
                        "OutputValue": "vpc-1234567890abcdef0",
                        "Description": "VPC ID for the infrastructure",
                    }
                ],
            },
            {
                "StackName": "staging-webapp",
                "StackStatus": "UPDATE_COMPLETE",
                "CreationTime": "2023-02-10T08:00:00Z",
                "LastUpdatedTime": "2023-07-20T16:45:00Z",
                "Tags": [
                    {"Key": "Environment", "Value": "staging"},
                    {"Key": "Application", "Value": "webapp"},
                ],
            },
        ],
        "ResponseMetadata": {
            "RequestId": "c3d4e5f6-g7h8-9012-cdef-34567890123a",
            "HTTPStatusCode": 200,
        },
    }


@pytest.fixture
def mock_security_policy():
    return {
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeSecurityGroups",
        "s3:ListBuckets",
        "s3:GetBucketLocation",
        "cloudformation:DescribeStacks",
        "cloudformation:ListStacks",
        "cloudformation:DescribeStackResources",
        "iam:ListUsers",
        "iam:GetUser",
        "ec2:Describe*",
        "s3:List*",
        "s3:Get*",
        "cloudformation:Describe*",
        "cloudformation:List*",
        "iam:List*",
        "iam:Get*",
    }


@pytest.fixture
def validation_error_fixtures():
    return {
        "missing_parameter": ClientError(
            error_response={
                "Error": {
                    "Code": "ValidationException",
                    "Message": "Missing required parameter in input: 'clusterName'",
                }
            },
            operation_name="DescribeCluster",
        ),
        "null_parameter": ClientError(
            error_response={
                "Error": {
                    "Code": "ValidationException",
                    "Message": "Value null at 'stackName' failed to satisfy "
                    "constraint: Member must not be null",
                }
            },
            operation_name="DescribeStackResources",
        ),
        "either_parameter": ClientError(
            error_response={
                "Error": {
                    "Code": "ValidationException",
                    "Message": "Either StackName or PhysicalResourceId must be specified",
                }
            },
            operation_name="DescribeStackResource",
        ),
        "param_validation_error": Exception(
            "ParamValidationError: Parameter validation failed:\n"
            + 'Unknown parameter in input: "InvalidParam", must be one of: clusterName, include'
        ),
    }


@pytest.fixture(autouse=True)
def reset_debug_mode():
    """Auto-reset debug state for all tests to ensure isolation."""
    from src.awsquery import utils

    original_debug_state = getattr(utils, "debug_enabled", False)
    utils.debug_enabled = False

    yield

    # Ensure state is always restored even if test fails
    utils.debug_enabled = original_debug_state


@pytest.fixture
def debug_mode():
    """Fixture to temporarily enable debug mode for specific tests."""
    from src.awsquery import utils

    original_debug_state = getattr(utils, "debug_enabled", False)
    utils.debug_enabled = True

    yield

    # Restore original state
    utils.debug_enabled = original_debug_state


@pytest.fixture
def debug_disabled():
    """Fixture to explicitly disable debug mode for specific tests."""
    from src.awsquery import utils

    original_debug_state = getattr(utils, "debug_enabled", False)
    utils.debug_enabled = False

    yield

    # Restore original state
    utils.debug_enabled = original_debug_state


@pytest.fixture
def mock_no_credentials_error():
    return NoCredentialsError()


@pytest.fixture
def mock_client_error():
    return ClientError(
        error_response={
            "Error": {
                "Code": "AccessDenied",
                "Message": "User: arn:aws:iam::123456789012:user/test-user is not "
                "authorized to perform: ec2:DescribeInstances",
            }
        },
        operation_name="DescribeInstances",
    )


@pytest.fixture
def sample_paginated_responses():
    return [
        {
            "Instances": [
                {"InstanceId": "i-page1-instance1", "State": {"Name": "running"}},
                {"InstanceId": "i-page1-instance2", "State": {"Name": "stopped"}},
            ],
            "NextToken": "page2-token",
            "ResponseMetadata": {"RequestId": "page1-request"},
        },
        {
            "Instances": [
                {"InstanceId": "i-page2-instance1", "State": {"Name": "running"}},
                {"InstanceId": "i-page2-instance2", "State": {"Name": "pending"}},
            ],
            "ResponseMetadata": {"RequestId": "page2-request"},
        },
    ]


@pytest.fixture
def mock_boto3_session():
    mock_session = Mock()
    mock_session.get_available_services.return_value = [
        "ec2",
        "s3",
        "cloudformation",
        "iam",
        "lambda",
        "rds",
    ]
    return mock_session


@pytest.fixture
def sample_security_policy_file(tmp_path):
    policy_content = {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ec2:Describe*",
                            "s3:List*",
                            "s3:Get*",
                            "cloudformation:Describe*",
                            "cloudformation:List*",
                            "iam:List*",
                            "iam:Get*",
                        ],
                        "Resource": "*",
                    }
                ],
            }
        }
    }

    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy_content, indent=2))
    return policy_file


@pytest.fixture
def empty_response():
    return {"ResponseMetadata": {"RequestId": "empty-response-request", "HTTPStatusCode": 200}}


@pytest.fixture
def malformed_response():
    return "This is not a valid AWS response"


@pytest.fixture
def mock_aws_credentials():
    with patch.dict(
        "os.environ",
        {
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    ):
        yield


@pytest.fixture
def capture_stderr(capsys):
    def _capture():
        captured = capsys.readouterr()
        return captured.err

    return _capture


@pytest.fixture
def capture_stdout(capsys):
    def _capture():
        captured = capsys.readouterr()
        return captured.out

    return _capture


@pytest.fixture
def multi_level_validation_error():
    """Common validation error for multi-level tests."""
    return {
        "parameter_name": "clusterName",
        "is_required": True,
        "error_type": "missing_parameter",
    }


@pytest.fixture
def multi_level_mock_setup():
    """Factory for setting up common multi-level test mocks."""

    def _setup(validation_error, list_response, final_response):
        from unittest.mock import Mock

        mock_execute = Mock()
        mock_get_param = Mock()

        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            list_response,
            final_response,
        ]
        mock_get_param.return_value = "ClusterName"

        return mock_execute, mock_get_param

    return _setup


@pytest.fixture
def sample_cluster_list():
    """Sample cluster list response for testing."""
    return [
        {"Name": "production-cluster", "Status": "ACTIVE", "Version": "1.21"},
        {"Name": "staging-cluster", "Status": "ACTIVE", "Version": "1.20"},
        {"Name": "development-cluster", "Status": "CREATING", "Version": "1.21"},
    ]


@pytest.fixture
def sample_function_list():
    """Sample Lambda function list response for testing."""
    return [
        {
            "FunctionName": "production-api-handler",
            "Runtime": "python3.9",
            "Handler": "lambda_function.lambda_handler",
            "CodeSize": 1024,
            "Description": "Production API handler",
        },
        {
            "FunctionName": "staging-data-processor",
            "Runtime": "python3.8",
            "Handler": "app.handler",
            "CodeSize": 2048,
            "Description": "Staging data processor",
        },
    ]


@pytest.fixture
def workflow_validator():
    """Helper for validating common workflow patterns."""

    def _validate_parsing_workflow(argv, expected_base, expected_filters):
        """Validate command parsing workflow."""
        from src.awsquery.filters import parse_multi_level_filters_for_mode

        base_cmd, res_filters, val_filters, col_filters = parse_multi_level_filters_for_mode(
            argv, mode="single"
        )

        assert base_cmd == expected_base
        if "resource_filters" in expected_filters:
            assert res_filters == expected_filters["resource_filters"]
        if "value_filters" in expected_filters:
            assert val_filters == expected_filters["value_filters"]
        if "column_filters" in expected_filters:
            assert col_filters == expected_filters["column_filters"]

        return base_cmd, res_filters, val_filters, col_filters

    def _validate_security_workflow(service, action, policy):
        """Validate security workflow."""
        from src.awsquery.security import validate_security
        from src.awsquery.utils import normalize_action_name

        normalized = normalize_action_name(action)
        assert validate_security(service, action.replace("-", "").title().replace(" ", ""), policy)
        return normalized

    def _validate_formatting_workflow(response, filters, expected_content):
        """Validate response formatting workflow."""
        from src.awsquery.formatters import flatten_response, format_table_output

        flattened = flatten_response(response)
        assert len(flattened) > 0

        table_output = format_table_output(flattened, filters)
        for content in expected_content:
            assert content in table_output

        return flattened, table_output

    return type(
        "WorkflowValidator",
        (),
        {
            "validate_parsing": _validate_parsing_workflow,
            "validate_security": _validate_security_workflow,
            "validate_formatting": _validate_formatting_workflow,
        },
    )()
