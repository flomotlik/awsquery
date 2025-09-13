"""Integration tests for session management with regions and profiles."""

import os
from unittest.mock import Mock, call, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from src.awsquery.cli import main
from src.awsquery.core import execute_aws_call, execute_multi_level_call
from src.awsquery.utils import create_session, get_client


@pytest.mark.integration
class TestSessionManagementIntegration:
    """Integration tests for session management across the application."""

    @patch("boto3.Session")
    def test_end_to_end_session_with_region(self, mock_session_class):
        """Test end-to-end session usage with region specification."""
        # Setup mock session and client
        mock_session = Mock()
        mock_client = Mock()
        mock_session.client.return_value = mock_client
        mock_session_class.return_value = mock_session

        # Mock successful response
        mock_response = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "State": {"Name": "running"},
                            "Tags": [{"Key": "Name", "Value": "test-instance"}],
                        }
                    ]
                }
            ]
        }
        mock_client.get_paginator.side_effect = Exception("Not pageable")
        mock_client.describe_instances.return_value = mock_response

        # Test session creation and usage
        session = create_session(region="us-west-2")
        result = execute_aws_call("ec2", "describe-instances", session=session)

        # Verify session was created with correct region
        mock_session_class.assert_called_once_with(region_name="us-west-2")

        # Verify session was used to create client
        mock_session.client.assert_called_once_with("ec2")

        # Verify call was made and result returned
        assert result == [mock_response]

    @patch("boto3.Session")
    def test_end_to_end_session_with_profile(self, mock_session_class):
        """Test end-to-end session usage with profile specification."""
        mock_session = Mock()
        mock_client = Mock()
        mock_session.client.return_value = mock_client
        mock_session_class.return_value = mock_session

        # Mock S3 response
        mock_response = {
            "Buckets": [{"Name": "test-bucket", "CreationDate": "2023-01-01T00:00:00Z"}]
        }
        mock_client.get_paginator.side_effect = Exception("Not pageable")
        mock_client.list_buckets.return_value = mock_response

        # Test with profile
        session = create_session(profile="prod-profile")
        result = execute_aws_call("s3", "list-buckets", session=session)

        # Verify profile was used
        mock_session_class.assert_called_once_with(profile_name="prod-profile")
        assert result == [mock_response]

    @patch("boto3.Session")
    def test_multi_level_call_session_persistence(self, mock_session_class):
        """Test that session persists through multi-level call resolution."""
        mock_session = Mock()
        mock_client = Mock()
        mock_session.client.return_value = mock_client
        mock_session_class.return_value = mock_session

        # Mock validation error for initial call
        validation_error = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }

        # Mock successful list response
        list_response = {"clusters": [{"name": "test-cluster"}]}

        # Mock successful final response
        final_response = {"cluster": {"name": "test-cluster", "status": "ACTIVE"}}

        # Setup call sequence
        mock_client.get_paginator.side_effect = Exception("Not pageable")

        # Create separate clients for tracking calls
        list_client = Mock()
        final_client = Mock()
        list_client.list_clusters.return_value = list_response
        final_client.describe_cluster.return_value = final_response

        # Return different clients to track calls
        mock_session.client.side_effect = [mock_client, list_client, final_client]

        with patch("src.awsquery.core.execute_aws_call") as mock_execute:
            # Mock the call sequence
            mock_execute.side_effect = [
                validation_error,  # Initial call fails
                [list_response],  # List call succeeds
                [final_response],  # Final call succeeds
            ]

            session = create_session(region="us-east-1", profile="test-profile")

            result = execute_multi_level_call(
                "eks", "describe-cluster", [], [], [], session=session
            )

            # Verify session was created with both parameters
            mock_session_class.assert_called_once_with(
                region_name="us-east-1", profile_name="test-profile"
            )

            # Verify all execute_aws_call calls received the session
            calls = mock_execute.call_args_list
            for call_args in calls:
                if len(call_args[1]) > 0:  # Check kwargs
                    assert call_args[1]["session"] == session

    def test_cross_region_service_calls(self):
        """Test that different services can be called with different regions."""
        with patch("boto3.Session") as mock_session_class:
            # Create separate sessions for different regions
            us_east_session = Mock()
            eu_west_session = Mock()

            us_east_client = Mock()
            eu_west_client = Mock()

            us_east_session.client.return_value = us_east_client
            eu_west_session.client.return_value = eu_west_client

            mock_session_class.side_effect = [us_east_session, eu_west_session]

            # Mock responses for different regions
            us_response = {"Buckets": [{"Name": "us-bucket"}]}
            eu_response = {"Buckets": [{"Name": "eu-bucket"}]}

            us_east_client.get_paginator.side_effect = Exception("Not pageable")
            eu_west_client.get_paginator.side_effect = Exception("Not pageable")
            us_east_client.list_buckets.return_value = us_response
            eu_west_client.list_buckets.return_value = eu_response

            # Test US East region
            us_session = create_session(region="us-east-1")
            us_result = execute_aws_call("s3", "list-buckets", session=us_session)

            # Test EU West region
            eu_session = create_session(region="eu-west-1")
            eu_result = execute_aws_call("s3", "list-buckets", session=eu_session)

            # Verify different sessions were created
            expected_calls = [call(region_name="us-east-1"), call(region_name="eu-west-1")]
            mock_session_class.assert_has_calls(expected_calls)

            # Verify different results
            assert us_result == [us_response]
            assert eu_result == [eu_response]


@pytest.mark.integration
class TestSessionErrorScenarios:
    """Integration tests for session error scenarios."""

    def test_invalid_region_error_handling(self):
        """Test handling of invalid AWS regions."""
        with patch("boto3.Session") as mock_session:
            # Simulate AWS SDK rejecting invalid region
            mock_session.side_effect = ClientError(
                error_response={
                    "Error": {
                        "Code": "InvalidRegion",
                        "Message": "The region invalid-region-123 does not exist",
                    }
                },
                operation_name="CreateSession",
            )

            with pytest.raises(ClientError, match="invalid-region-123"):
                create_session(region="invalid-region-123")

    def test_invalid_profile_error_handling(self):
        """Test handling of invalid AWS profiles."""
        with patch("boto3.Session") as mock_session:
            # Simulate profile not found error
            mock_session.side_effect = ProfileNotFound(profile="nonexistent-profile")

            with pytest.raises(ProfileNotFound, match="nonexistent-profile"):
                create_session(profile="nonexistent-profile")

    def test_no_credentials_with_profile(self):
        """Test handling when profile exists but has no credentials."""
        with patch("boto3.Session") as mock_session_class:
            mock_session = Mock()
            mock_session.client.side_effect = NoCredentialsError()
            mock_session_class.return_value = mock_session

            session = create_session(profile="empty-profile")

            # Should create session but fail when creating client
            with pytest.raises(SystemExit, match="1"):
                execute_aws_call("ec2", "describe-instances", session=session)

    def test_session_with_mixed_valid_invalid_params(self):
        """Test session creation with mix of valid and invalid parameters."""
        with patch("boto3.Session") as mock_session:
            # Only region is invalid, profile should still work
            mock_session.side_effect = [
                ClientError(
                    error_response={
                        "Error": {"Code": "InvalidRegion", "Message": "Invalid region"}
                    },
                    operation_name="CreateSession",
                ),
                Mock(),  # Successful session creation
            ]

            # First call should fail due to invalid region
            with pytest.raises(ClientError):
                create_session(region="invalid-region", profile="valid-profile")

            # Second call with only profile should work
            session = create_session(profile="valid-profile")
            assert session is not None


@pytest.mark.integration
class TestSessionEnvironmentIntegration:
    """Integration tests for session interaction with environment variables."""

    def test_session_overrides_environment_region(self):
        """Test that session region overrides AWS_DEFAULT_REGION."""
        with patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-west-1"}):
            with patch("boto3.Session") as mock_session:
                create_session(region="us-east-1")

                # Should use explicit region, not environment
                mock_session.assert_called_once_with(region_name="us-east-1")

    def test_session_overrides_environment_profile(self):
        """Test that session profile overrides AWS_PROFILE."""
        with patch.dict(os.environ, {"AWS_PROFILE": "env-profile"}):
            with patch("boto3.Session") as mock_session:
                create_session(profile="explicit-profile")

                # Should use explicit profile, not environment
                mock_session.assert_called_once_with(profile_name="explicit-profile")

    def test_session_respects_environment_when_no_override(self):
        """Test that session respects environment when no explicit params given."""
        with patch("boto3.Session") as mock_session:
            create_session()

            # Should create session without explicit parameters
            # (boto3 will use environment variables internally)
            mock_session.assert_called_once_with()

    def test_partial_environment_override(self):
        """Test session with partial environment override."""
        with patch.dict(
            os.environ, {"AWS_DEFAULT_REGION": "us-west-1", "AWS_PROFILE": "env-profile"}
        ):
            with patch("boto3.Session") as mock_session:
                # Override only region, let profile come from environment
                create_session(region="us-east-1")

                mock_session.assert_called_once_with(region_name="us-east-1")


@pytest.mark.integration
class TestCLISessionIntegration:
    """Integration tests for CLI session argument handling."""

    @patch("src.awsquery.cli.execute_aws_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_cli_region_profile_integration(
        self, mock_create_session, mock_services, mock_policy, mock_execute
    ):
        """Test full CLI integration with region and profile arguments."""
        # Setup mocks
        mock_services.return_value = ["ec2", "s3"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        mock_execute.return_value = [{"Instances": []}]

        # Test CLI command with both region and profile
        import sys

        test_args = [
            "awsquery",
            "--region",
            "ap-southeast-2",
            "--profile",
            "production",
            "--debug",
            "ec2",
            "describe-instances",
        ]

        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass  # Expected for tests

        # Verify session was created with correct parameters
        mock_create_session.assert_called_once_with(region="ap-southeast-2", profile="production")

        # Verify AWS call was made with the session
        mock_execute.assert_called()
        call_args = mock_execute.call_args
        # Session should be passed as the last positional argument or as keyword
        if len(call_args[0]) >= 5:
            assert call_args[0][4] == mock_session
        elif "session" in call_args[1]:
            assert call_args[1]["session"] == mock_session

    @patch("src.awsquery.cli.execute_multi_level_call")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_cli_multi_level_session_passing(
        self, mock_create_session, mock_services, mock_policy, mock_multi_level
    ):
        """Test that CLI passes session to multi-level calls."""
        mock_services.return_value = ["eks"]
        mock_policy.return_value = {"eks:DescribeCluster"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Mock initial call failure to trigger multi-level
        validation_error = {"validation_error": {"parameter_name": "clusterName"}}

        with patch("src.awsquery.cli.execute_aws_call") as mock_execute:
            mock_execute.return_value = validation_error
            mock_multi_level.return_value = [{"Cluster": {"Name": "test"}}]

            test_args = ["awsquery", "--profile", "dev", "eks", "describe-cluster"]

            import sys

            with patch.object(sys, "argv", test_args):
                try:
                    main()
                except SystemExit:
                    pass

        # Verify session creation
        mock_create_session.assert_called_once_with(region=None, profile="dev")

        # Verify multi-level call received session
        mock_multi_level.assert_called_once()
        call_args = mock_multi_level.call_args
        # Session can be passed as last positional arg or as keyword
        if len(call_args[0]) >= 7:
            assert call_args[0][6] == mock_session
        elif "session" in call_args[1]:
            assert call_args[1]["session"] == mock_session

    @patch("src.awsquery.cli.create_session")
    def test_cli_session_creation_failure(self, mock_create_session):
        """Test CLI handling of session creation failures."""
        mock_create_session.side_effect = ProfileNotFound(profile="invalid-profile")

        test_args = ["awsquery", "--profile", "invalid-profile", "ec2", "describe-instances"]

        import sys

        with patch.object(sys, "argv", test_args):
            with pytest.raises(ProfileNotFound):
                main()


@pytest.mark.integration
class TestSessionMultiServiceIntegration:
    """Integration tests for session usage across multiple services."""

    def test_session_reuse_across_services(self):
        """Test that a single session can be reused for multiple services."""
        with patch("boto3.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock clients for different services
            ec2_client = Mock()
            s3_client = Mock()

            def client_side_effect(service_name):
                if service_name == "ec2":
                    return ec2_client
                elif service_name == "s3":
                    return s3_client
                else:
                    return Mock()

            mock_session.client.side_effect = client_side_effect

            # Mock responses
            ec2_response = {"Instances": [{"InstanceId": "i-123"}]}
            s3_response = {"Buckets": [{"Name": "test-bucket"}]}

            ec2_client.get_paginator.side_effect = Exception("Not pageable")
            s3_client.get_paginator.side_effect = Exception("Not pageable")
            ec2_client.describe_instances.return_value = ec2_response
            s3_client.list_buckets.return_value = s3_response

            # Create single session
            session = create_session(region="us-east-1", profile="multi-service")

            # Use session for multiple services
            ec2_result = execute_aws_call("ec2", "describe-instances", session=session)
            s3_result = execute_aws_call("s3", "list-buckets", session=session)

            # Verify single session creation
            mock_session_class.assert_called_once_with(
                region_name="us-east-1", profile_name="multi-service"
            )

            # Verify both services used the same session
            expected_client_calls = [call("ec2"), call("s3")]
            mock_session.client.assert_has_calls(expected_client_calls)

            # Verify results
            assert ec2_result == [ec2_response]
            assert s3_result == [s3_response]

    def test_service_specific_region_requirements(self):
        """Test handling services that may have region-specific requirements."""
        with patch("boto3.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Some services might fail in certain regions
            mock_client = Mock()
            mock_session.client.return_value = mock_client
            mock_client.get_paginator.side_effect = Exception("Not pageable")

            # Simulate region-specific service error
            mock_client.describe_something.side_effect = ClientError(
                error_response={
                    "Error": {
                        "Code": "UnsupportedOperation",
                        "Message": "This operation is not supported in this region",
                    }
                },
                operation_name="DescribeSomething",
            )

            session = create_session(region="us-gov-east-1")  # Government cloud region

            # Should propagate the region-specific error
            with pytest.raises(SystemExit):
                execute_aws_call("someservice", "describe-something", session=session)


@pytest.mark.integration
class TestSessionWithKeysModeIntegration:
    """Integration tests for session management with keys mode."""

    @patch("src.awsquery.cli.execute_with_tracking")
    @patch("src.awsquery.cli.load_security_policy")
    @patch("src.awsquery.cli.get_aws_services")
    @patch("src.awsquery.cli.create_session")
    def test_keys_mode_with_session(
        self, mock_create_session, mock_services, mock_policy, mock_tracking
    ):
        """Test that keys mode works correctly with session arguments."""
        from src.awsquery.core import CallResult

        mock_services.return_value = ["ec2"]
        mock_policy.return_value = {"ec2:DescribeInstances"}
        mock_session = Mock()
        mock_create_session.return_value = mock_session

        # Setup successful tracking result
        successful_result = CallResult()
        successful_result.final_success = True
        successful_result.last_successful_response = [
            {"Instances": [{"InstanceId": "i-123", "State": "running"}]}
        ]
        mock_tracking.return_value = successful_result

        test_args = ["awsquery", "--keys", "--region", "eu-central-1", "ec2", "describe-instances"]

        import sys

        with patch.object(sys, "argv", test_args), patch(
            "src.awsquery.cli.show_keys_from_result"
        ) as mock_show_keys:

            mock_show_keys.return_value = "  InstanceId\n  State"

            try:
                main()
            except SystemExit:
                pass

        # Verify session was created with region
        mock_create_session.assert_called_once_with(region="eu-central-1", profile=None)

        # Verify tracking call was made with session
        mock_tracking.assert_called_once()
        call_args = mock_tracking.call_args
        assert call_args[1]["session"] == mock_session
