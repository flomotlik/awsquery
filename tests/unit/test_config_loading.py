"""Tests for configuration file loading from package directory."""

import os
import tempfile
from unittest.mock import Mock, mock_open, patch

import pytest
import yaml

from src.awsquery.config import load_default_filters
from src.awsquery.security import load_security_policy


@pytest.mark.unit
class TestConfigFileLoading:
    """Test that configuration files are loaded from package directory."""

    def test_policy_json_loads_from_package_directory(self):
        """Test that policy.json is loaded from the package directory, not cwd."""
        # Get the expected path
        import src.awsquery.security

        expected_path = os.path.join(os.path.dirname(src.awsquery.security.__file__), "policy.json")

        # Mock the file open to track what path is used
        mock_policy_content = """
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ec2:Describe*"]
                }
            ]
        }
        """

        with patch("builtins.open", mock_open(read_data=mock_policy_content)) as mock_file:
            with patch("os.path.exists", return_value=True):
                result = load_security_policy()

                # Verify the correct path was used
                mock_file.assert_called_once_with(expected_path, "r")

                # Verify the policy was loaded
                assert "ec2:Describe*" in result

    def test_policy_json_not_affected_by_cwd(self):
        """Test that changing cwd doesn't affect policy.json loading."""
        original_cwd = os.getcwd()

        try:
            # Create a temporary directory and change to it
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)

                # Mock successful file read
                mock_policy_content = """
                {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["s3:List*"]
                        }
                    ]
                }
                """

                with patch("builtins.open", mock_open(read_data=mock_policy_content)):
                    result = load_security_policy()

                    # Should still load successfully even though cwd changed
                    assert "s3:List*" in result

        finally:
            os.chdir(original_cwd)

    def test_default_filters_loads_from_package_directory(self):
        """Test that default_filters.yaml is loaded from the package directory."""
        # Get the expected path
        import src.awsquery.config

        expected_path = os.path.join(
            os.path.dirname(src.awsquery.config.__file__), "default_filters.yaml"
        )

        # Clear the cache first
        load_default_filters.cache_clear()

        mock_yaml_content = """
        ec2:
          describe_instances:
            columns:
              - InstanceId
              - State.Name
        """

        with patch("builtins.open", mock_open(read_data=mock_yaml_content)) as mock_file:
            with patch("yaml.safe_load") as mock_yaml:
                mock_yaml.return_value = {
                    "ec2": {"describe_instances": {"columns": ["InstanceId", "State.Name"]}}
                }

                result = load_default_filters()

                # Verify the correct path was used
                mock_file.assert_called_once_with(expected_path, "r")

                # Verify the config was loaded
                assert "ec2" in result
                assert result["ec2"]["describe_instances"]["columns"] == [
                    "InstanceId",
                    "State.Name",
                ]

    def test_default_filters_not_affected_by_cwd(self):
        """Test that changing cwd doesn't affect default_filters.yaml loading."""
        original_cwd = os.getcwd()

        # Clear the cache first
        load_default_filters.cache_clear()

        try:
            # Create a temporary directory and change to it
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)

                # Create a fake default_filters.yaml in the temp directory
                fake_config_path = os.path.join(tmpdir, "default_filters.yaml")
                with open(fake_config_path, "w") as f:
                    f.write("fake: config")

                # Mock the package directory file read
                mock_yaml_content = """
                s3:
                  list_buckets:
                    columns:
                      - Name
                      - CreationDate
                """

                import src.awsquery.config

                package_path = os.path.join(
                    os.path.dirname(src.awsquery.config.__file__), "default_filters.yaml"
                )

                def mock_open_func(path, mode):
                    if path == package_path:
                        return mock_open(read_data=mock_yaml_content)()
                    else:
                        raise FileNotFoundError(f"Should not open {path}")

                with patch("builtins.open", side_effect=mock_open_func):
                    with patch("yaml.safe_load") as mock_yaml:
                        mock_yaml.return_value = {
                            "s3": {"list_buckets": {"columns": ["Name", "CreationDate"]}}
                        }

                        result = load_default_filters()

                        # Should load from package directory, not cwd
                        assert "s3" in result
                        assert "fake" not in result

        finally:
            os.chdir(original_cwd)
            # Clear cache again to avoid affecting other tests
            load_default_filters.cache_clear()

    def test_policy_json_missing_handles_gracefully(self):
        """Test that missing policy.json is handled with proper error message."""
        import src.awsquery.security

        expected_path = os.path.join(os.path.dirname(src.awsquery.security.__file__), "policy.json")

        with patch("builtins.open", side_effect=FileNotFoundError()):
            with pytest.raises(SystemExit) as exc_info:
                with patch("sys.stderr", new_callable=Mock) as mock_stderr:
                    load_security_policy()

            # Should exit with error code
            assert exc_info.value.code == 1

    def test_default_filters_missing_returns_empty(self):
        """Test that missing default_filters.yaml returns empty config."""
        # Clear the cache first
        load_default_filters.cache_clear()

        with patch("builtins.open", side_effect=FileNotFoundError()):
            result = load_default_filters()

            # Should return empty dict, not fail
            assert result == {}

    def test_default_filters_caching(self):
        """Test that default_filters.yaml is cached after first load."""
        # Clear the cache first
        load_default_filters.cache_clear()

        mock_yaml_content = """
        ec2:
          describe_instances:
            columns: [InstanceId]
        """

        open_count = 0

        def mock_open_counter(*args, **kwargs):
            nonlocal open_count
            open_count += 1
            return mock_open(read_data=mock_yaml_content)()

        with patch("builtins.open", side_effect=mock_open_counter):
            with patch("yaml.safe_load", return_value={"ec2": {}}):
                # First call should open file
                result1 = load_default_filters()
                assert open_count == 1

                # Second call should use cache
                result2 = load_default_filters()
                assert open_count == 1  # Should not increase

                # Results should be the same
                assert result1 == result2

        # Clear cache for other tests
        load_default_filters.cache_clear()

    def test_policy_json_malformed_json(self):
        """Test handling of malformed JSON in policy.json."""
        malformed_json = '{"Statement": ["incomplete'

        with patch("builtins.open", mock_open(read_data=malformed_json)):
            with pytest.raises(SystemExit) as exc_info:
                load_security_policy()

            assert exc_info.value.code == 1

    def test_policy_json_invalid_structure(self):
        """Test handling of invalid policy structure."""
        invalid_policy = """
        {
            "NotStatement": [
                {"Something": "else"}
            ]
        }
        """

        with patch("builtins.open", mock_open(read_data=invalid_policy)):
            result = load_security_policy()
            # Should return empty set when no valid statements found
            assert result == set()

    def test_policy_json_with_deny_statements(self):
        """Test that Deny statements are ignored."""
        policy_with_deny = """
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ec2:Describe*"]
                },
                {
                    "Effect": "Deny",
                    "Action": ["ec2:TerminateInstances"]
                }
            ]
        }
        """

        with patch("builtins.open", mock_open(read_data=policy_with_deny)):
            result = load_security_policy()
            # Should only include Allow actions
            assert "ec2:Describe*" in result
            assert "ec2:TerminateInstances" not in result

    def test_policy_json_with_string_action(self):
        """Test handling of single string action instead of array."""
        policy_string_action = """
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "s3:ListBucket"
                }
            ]
        }
        """

        with patch("builtins.open", mock_open(read_data=policy_string_action)):
            result = load_security_policy()
            assert "s3:ListBucket" in result

    def test_default_filters_malformed_yaml(self):
        """Test handling of malformed YAML in default_filters.yaml."""
        load_default_filters.cache_clear()

        malformed_yaml = "ec2:\n  - incomplete: [\n"

        with patch("builtins.open", mock_open(read_data=malformed_yaml)):
            with patch("yaml.safe_load", side_effect=yaml.YAMLError("Invalid YAML")):
                result = load_default_filters()
                # Should return empty dict on YAML error
                assert result == {}

        load_default_filters.cache_clear()

    def test_default_filters_invalid_structure(self):
        """Test handling of invalid structure in default_filters.yaml."""
        load_default_filters.cache_clear()

        with patch("builtins.open", mock_open(read_data="valid yaml")):
            with patch("yaml.safe_load", return_value="not a dict"):
                # This should be handled by the code, returning the value as-is
                result = load_default_filters()
                assert result == "not a dict"

        load_default_filters.cache_clear()

    def test_default_filters_empty_file(self):
        """Test handling of empty default_filters.yaml."""
        load_default_filters.cache_clear()

        with patch("builtins.open", mock_open(read_data="")):
            with patch("yaml.safe_load", return_value=None):
                result = load_default_filters()
                # Should handle None from yaml.safe_load
                assert result is None or result == {}

        load_default_filters.cache_clear()

    def test_policy_json_with_policy_version_structure(self):
        """Test loading policy with PolicyVersion structure."""
        policy_with_version = """
        {
            "PolicyVersion": {
                "Document": {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["rds:Describe*"]
                        }
                    ]
                }
            }
        }
        """

        with patch("builtins.open", mock_open(read_data=policy_with_version)):
            result = load_security_policy()
            assert "rds:Describe*" in result

    def test_get_default_columns_integration(self):
        """Test get_default_columns function."""
        from src.awsquery.config import get_default_columns

        load_default_filters.cache_clear()

        mock_config = {"ec2": {"describe_instances": {"columns": ["InstanceId", "State.Name"]}}}

        with patch("src.awsquery.config.load_default_filters", return_value=mock_config):
            # Test exact match
            columns = get_default_columns("ec2", "describe_instances")
            assert columns == ["InstanceId", "State.Name"]

            # Test case insensitivity
            columns = get_default_columns("EC2", "Describe_Instances")
            assert columns == ["InstanceId", "State.Name"]

            # Test missing service
            columns = get_default_columns("s3", "list_buckets")
            assert columns == []

            # Test missing action
            columns = get_default_columns("ec2", "describe_volumes")
            assert columns == []
