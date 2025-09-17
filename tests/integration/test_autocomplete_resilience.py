"""Integration tests for autocomplete resilience without AWS credentials."""

import os
from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

from awsquery.cli import action_completer, service_completer


class TestAutocompleteWithoutCredentials:
    """Test that autocomplete works without AWS credentials using mocked botocore for speed."""

    def setup_method(self):
        """Clear AWS environment variables for each test."""
        self.original_env = {}
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_PROFILE",
        ]:
            self.original_env[key] = os.environ.pop(key, None)

    def teardown_method(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_service_completer_without_credentials(self):
        """Test service completer works without AWS credentials."""
        # Mock botocore.session at the module level where it's imported
        with patch('botocore.session.Session') as mock_session_class:
            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = [
                'ec2', 'ecs', 'ecr', 's3', 'lambda', 'iam', 'dynamodb'
            ]

            result = service_completer("ec", None)

            # Should return mocked AWS services
            assert len(result) > 0
            assert "ec2" in result
            assert "ecs" in result
            assert "ecr" in result
            assert all(s.startswith("ec") for s in result)

    def test_service_completer_various_prefixes(self):
        """Test service completer with different prefixes."""
        with patch('botocore.session.Session') as mock_session_class:
            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = [
                's3', 'sqs', 'sns', 'cloudformation', 'cloudwatch', 'cloudtrail'
            ]

            # Test single character
            result_s = service_completer("s", None)
            assert "s3" in result_s
            assert "sqs" in result_s
            assert "sns" in result_s

            # Test multi-character prefix
            result_cloud = service_completer("cloud", None)
            assert "cloudformation" in result_cloud
            assert "cloudwatch" in result_cloud
            assert "cloudtrail" in result_cloud

            # Test non-existent prefix
            result_xyz = service_completer("xyz", None)
            assert result_xyz == []

    def test_action_completer_without_credentials(self):
        """Test action completer works without AWS credentials."""
        with patch('awsquery.security.load_security_policy') as mock_load_security, \
             patch('botocore.session.Session') as mock_session_class:
            # Mock security policy
            mock_load_security.return_value = set(['ec2:Describe*'])

            # Mock botocore session and service model
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = ['ec2']

            # Create extensive describe operations list
            describe_ops = [f'Describe{x}' for x in range(110)]  # More than 100 operations
            describe_ops.extend(['DescribeInstances', 'DescribeVolumes', 'DescribeSecurityGroups'])

            mock_service_model = Mock()
            mock_service_model.operation_names = describe_ops
            mock_session.get_service_model.return_value = mock_service_model

            parsed_args = Namespace(service="ec2")
            result = action_completer("describe", parsed_args)

            # Should return mocked EC2 operations
            assert len(result) > 100  # EC2 has many describe operations
            assert "describe-instances" in result
            assert "describe-volumes" in result
            assert "describe-security-groups" in result
            assert all(a.startswith("describe") for a in result)

    def test_action_completer_different_services(self):
        """Test action completer for various AWS services."""
        with patch('awsquery.security.load_security_policy') as mock_load_security, \
             patch('botocore.session.Session') as mock_session_class:
            # Mock security policy
            mock_load_security.return_value = set(['s3:List*', 's3:Get*', 'iam:Get*', 'lambda:List*'])

            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = ['s3', 'iam', 'lambda']

            # Test S3
            mock_service_model_s3 = Mock()
            mock_service_model_s3.operation_names = [
                'ListBuckets', 'ListObjects', 'ListObjectsV2', 'GetBucketPolicy'
            ]
            mock_session.get_service_model.return_value = mock_service_model_s3

            parsed_args = Namespace(service="s3")
            result = action_completer("list", parsed_args)
            assert "list-buckets" in result
            assert "list-objects" in result
            assert "list-objects-v2" in result

            # Test IAM
            mock_service_model_iam = Mock()
            mock_service_model_iam.operation_names = [
                'GetUser', 'GetRole', 'GetPolicy', 'GetGroup'
            ]
            mock_session.get_service_model.return_value = mock_service_model_iam

            parsed_args = Namespace(service="iam")
            result = action_completer("get", parsed_args)
            assert "get-user" in result
            assert "get-role" in result
            assert "get-policy" in result

            # Test Lambda
            mock_service_model_lambda = Mock()
            mock_service_model_lambda.operation_names = [
                'ListFunctions', 'ListLayers', 'ListVersionsByFunction'
            ]
            mock_session.get_service_model.return_value = mock_service_model_lambda

            parsed_args = Namespace(service="lambda")
            result = action_completer("list", parsed_args)
            assert "list-functions" in result
            assert "list-layers" in result

    def test_action_completer_nonexistent_service(self):
        """Test action completer with non-existent service."""
        with patch('botocore.session.Session') as mock_session_class:
            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = ['ec2', 's3', 'iam']

            parsed_args = Namespace(service="nonexistent-service-12345")
            result = action_completer("describe", parsed_args)
            assert result == []

    def test_action_completer_no_service(self):
        """Test action completer when no service is specified."""
        with patch('botocore.session.Session') as mock_session_class:
            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            parsed_args = Namespace(service=None)
            result = action_completer("describe", parsed_args)
            assert result == []

    def test_autocomplete_with_invalid_profile(self):
        """Test autocomplete still works with invalid AWS_PROFILE."""
        os.environ["AWS_PROFILE"] = "nonexistent-profile-99999"

        with patch('awsquery.security.load_security_policy') as mock_load_security, \
             patch('botocore.session.Session') as mock_session_class:
            # Mock security policy
            mock_load_security.return_value = set(['dynamodb:Describe*'])

            # Mock botocore session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = ['rds', 'dynamodb', 's3']

            # Service completer should still work
            services = service_completer("rds", None)
            assert "rds" in services

            # Mock service model for DynamoDB
            mock_service_model = Mock()
            mock_service_model.operation_names = ['DescribeTable', 'DescribeBackup', 'ListTables']
            mock_session.get_service_model.return_value = mock_service_model

            # Action completer should still work
            parsed_args = Namespace(service="dynamodb")
            actions = action_completer("describe", parsed_args)
            assert "describe-table" in actions

    def test_autocomplete_filters_by_security_policy(self):
        """Test that autocomplete respects security policy filtering."""
        with patch('awsquery.security.load_security_policy') as mock_load_security, \
             patch('botocore.session.Session') as mock_session_class:
            # Mock security policy to allow only read operations
            mock_load_security.return_value = set(['ec2:Describe*', 'ec2:Get*'])

            # Mock botocore session and service model
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.get_available_services.return_value = ['ec2']

            # Include write operations that should be filtered out
            all_operations = (
                [f'Describe{x}' for x in range(55)] +  # 55 describe operations
                ['GetConsoleOutput', 'GetPasswordData'] +  # Some get operations
                ['CreateInstance', 'DeleteInstance', 'TerminateInstances']  # Write operations
            )
            mock_service_model = Mock()
            mock_service_model.operation_names = all_operations
            mock_session.get_service_model.return_value = mock_service_model

            parsed_args = Namespace(service="ec2")
            all_ops = action_completer("", parsed_args)

            # Should not include write operations
            assert "create-instance" not in all_ops
            assert "delete-instance" not in all_ops
            assert "terminate-instances" not in all_ops

            # Should include read operations
            describe_ops = [op for op in all_ops if op.startswith("describe")]
            get_ops = [op for op in all_ops if op.startswith("get")]

            assert len(describe_ops) > 50  # EC2 has many describe operations
            assert len(get_ops) > 0


class TestRealBotocoreIntegration:
    """Test with real botocore to ensure integration works correctly.

    These tests verify that our autocomplete actually works with real botocore data.
    Note: These tests may be slower on Python 3.8-3.10 due to botocore performance.
    """

    def setup_method(self):
        """Clear AWS environment variables for each test."""
        self.original_env = {}
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_PROFILE",
        ]:
            self.original_env[key] = os.environ.pop(key, None)

    def teardown_method(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_real_botocore_basic_operations(self):
        """Test basic operations with real botocore - combined for efficiency."""
        # Test service completer with real botocore
        all_services = service_completer("", None)
        assert len(all_services) > 100

        # Check core services exist
        assert "ec2" in all_services
        assert "s3" in all_services
        assert "iam" in all_services
        assert "sts" in all_services

        # Test prefix filtering
        st_services = service_completer("st", None)
        assert "sts" in st_services
        assert "storagegateway" in st_services
        assert all(s.startswith("st") for s in st_services)

        # Test that autocomplete works without credentials
        assert "AWS_ACCESS_KEY_ID" not in os.environ
        assert "AWS_PROFILE" not in os.environ

    @patch('awsquery.security.load_security_policy')
    def test_real_action_completer_small_service(self, mock_load_security):
        """Test action completer with real botocore using STS (smallest service)."""
        # Use STS - it has only 9 operations so loads very fast
        # This ensures we have at least one test that verifies real botocore integration
        mock_load_security.return_value = set(['sts:*'])

        parsed_args = Namespace(service="sts")
        result = action_completer("get", parsed_args)

        # STS should have get operations
        assert len(result) > 0
        assert "get-caller-identity" in result
        assert "get-session-token" in result
        assert all(a.startswith("get") or a.startswith("assume") or a.startswith("decode") for a in result)

    def test_real_botocore_full_integration(self):
        """Full integration test with real botocore - verifies the complete flow."""
        # This test ensures that our autocomplete actually works end-to-end
        # with real botocore data, not just mocked data

        # 1. Get services starting with 'st'
        services = service_completer("st", None)
        assert "sts" in services

        # 2. Test STS action completion (small service, fast)
        parsed_args = Namespace(service="sts")

        # Get all operations
        all_ops = action_completer("", parsed_args)
        assert len(all_ops) > 0  # STS has about 9 operations
        assert len(all_ops) < 20  # But not too many

        # Test specific prefixes
        get_ops = action_completer("get", parsed_args)
        assert "get-caller-identity" in get_ops
        assert "get-session-token" in get_ops
        assert "get-access-key-info" in get_ops

        # 3. Verify operation name conversion (PascalCase -> kebab-case)
        # The actual botocore operation names are in PascalCase
        # but our completer should return them in kebab-case
        assert all("-" in op for op in all_ops)
        assert all(op.islower() for op in all_ops)