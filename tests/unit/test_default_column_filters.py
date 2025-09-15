"""Unit tests for default column filters functionality."""

import os
import tempfile
from unittest.mock import patch

import pytest

from src.awsquery.cli import determine_column_filters
from src.awsquery.config import apply_default_filters, get_default_columns, load_default_filters


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear the configuration cache before each test."""
    load_default_filters.cache_clear()
    yield
    load_default_filters.cache_clear()


class TestLoadDefaultFilters:
    """Test the load_default_filters function."""

    def test_successful_yaml_loading(self):
        """Test successful loading of default filters YAML."""
        config = load_default_filters()

        assert config is not None
        assert isinstance(config, dict)
        assert "ec2" in config
        assert "describe_instances" in config["ec2"]
        assert "columns" in config["ec2"]["describe_instances"]

    @patch("src.awsquery.config.open")
    def test_file_not_found_returns_empty_dict(self, mock_open):
        """Test that missing YAML file returns empty dict."""
        mock_open.side_effect = FileNotFoundError("File not found")

        # Clear cache first
        load_default_filters.cache_clear()

        with patch("src.awsquery.config.debug_print") as mock_debug:
            config = load_default_filters()

            assert config == {}
            # Check that the warning message contains the expected text
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "not found, no defaults will be applied" in call_args

    @patch("src.awsquery.config.yaml.safe_load")
    @patch("builtins.open")
    def test_yaml_parse_error_returns_empty_dict(self, mock_open, mock_yaml):
        """Test that YAML parse error returns empty dict."""
        mock_yaml.side_effect = Exception("YAML parse error")

        # Clear cache first
        load_default_filters.cache_clear()

        with patch("src.awsquery.config.debug_print") as mock_debug:
            config = load_default_filters()

            assert config == {}
            # Check that the warning message contains the expected text
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "Could not load default filters" in call_args
            assert "YAML parse error" in call_args

    def test_caching_behavior(self):
        """Test that the function uses caching correctly."""
        # First call
        config1 = load_default_filters()

        # Second call should return same object due to caching
        config2 = load_default_filters()

        assert config1 is config2


class TestGetDefaultColumns:
    """Test the get_default_columns function."""

    def test_existing_service_action(self):
        """Test retrieving columns for existing service/action."""
        columns = get_default_columns("ec2", "describe_instances")

        expected = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert columns == expected

    def test_existing_service_different_action(self):
        """Test retrieving columns for different action of same service."""
        columns = get_default_columns("ec2", "describe_security_groups")

        expected = ["GroupName", "GroupId", "Description", "VpcId"]
        assert columns == expected

    def test_case_insensitive_service_action(self):
        """Test that service/action lookup is case-insensitive."""
        columns_lower = get_default_columns("ec2", "describe_instances")
        columns_upper = get_default_columns("EC2", "DESCRIBE_INSTANCES")
        columns_mixed = get_default_columns("Ec2", "Describe_Instances")

        assert columns_lower == columns_upper == columns_mixed

    def test_nonexistent_service(self):
        """Test retrieving columns for non-existent service."""
        columns = get_default_columns("nonexistent", "action")

        assert columns == []

    def test_nonexistent_action(self):
        """Test retrieving columns for non-existent action."""
        columns = get_default_columns("ec2", "nonexistent_action")

        assert columns == []

    def test_different_services(self):
        """Test retrieving columns for different services."""
        s3_columns = get_default_columns("s3", "list_buckets")
        lambda_columns = get_default_columns("lambda", "list_functions")

        assert s3_columns == ["Name", "CreationDate"]
        assert lambda_columns == [
            "FunctionName",
            "Runtime",
            "LastModified",
            "CodeSize",
            "Description",
        ]


class TestApplyDefaultFilters:
    """Test the apply_default_filters function."""

    def test_user_columns_provided_returns_user_columns(self):
        """Test that user columns are returned when provided."""
        user_columns = ["InstanceId", "State.Name"]
        result = apply_default_filters("ec2", "describe_instances", user_columns)

        assert result == user_columns

    def test_no_user_columns_returns_defaults(self):
        """Test that defaults are returned when no user columns provided."""
        result = apply_default_filters("ec2", "describe_instances", None)

        expected = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert result == expected

    def test_empty_user_columns_returns_defaults(self):
        """Test that defaults are returned when empty user columns provided."""
        result = apply_default_filters("ec2", "describe_instances", [])

        expected = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert result == expected

    def test_nonexistent_service_returns_none(self):
        """Test that None is returned for non-existent service."""
        result = apply_default_filters("nonexistent", "action", None)

        assert result is None

    def test_nonexistent_action_returns_none(self):
        """Test that None is returned for non-existent action."""
        result = apply_default_filters("ec2", "nonexistent_action", None)

        assert result is None


class TestDetermineColumnFilters:
    """Test the CLI determine_column_filters function."""

    def test_user_columns_provided(self):
        """Test that user columns are returned when provided."""
        user_columns = ["InstanceId", "State.Name"]
        result = determine_column_filters(user_columns, "ec2", "describe_instances")

        assert result == user_columns

    def test_empty_user_columns_gets_defaults(self):
        """Test that defaults are applied when user columns are empty."""
        result = determine_column_filters([], "ec2", "describe_instances")

        expected = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert result == expected

    def test_none_user_columns_gets_defaults(self):
        """Test that defaults are applied when user columns are None."""
        result = determine_column_filters(None, "s3", "list_buckets")

        expected = ["Name", "CreationDate"]
        assert result == expected

    def test_unknown_service_action_returns_none(self):
        """Test that None is returned for unknown service/action."""
        result = determine_column_filters(None, "unknown", "action")

        assert result is None


class TestYAMLConfigurationStructure:
    """Test the YAML configuration structure and content."""

    def test_expected_services_present(self):
        """Test that expected services are present in configuration."""
        config = load_default_filters()

        expected_services = ["ec2", "s3", "lambda", "rds", "cloudformation"]
        for service in expected_services:
            assert service in config, f"Service {service} should be in configuration"

    def test_ec2_actions_complete(self):
        """Test that EC2 actions are properly configured."""
        config = load_default_filters()
        ec2_config = config["ec2"]

        expected_actions = ["describe_instances", "describe_security_groups", "describe_volumes"]
        for action in expected_actions:
            assert action in ec2_config, f"Action {action} should be in EC2 configuration"
            assert "columns" in ec2_config[action], f"Action {action} should have columns"
            assert isinstance(
                ec2_config[action]["columns"], list
            ), f"Columns for {action} should be a list"

    def test_columns_are_strings(self):
        """Test that all column entries are strings."""
        config = load_default_filters()

        for service_name, service_config in config.items():
            for action_name, action_config in service_config.items():
                columns = action_config.get("columns", [])
                for column in columns:
                    assert isinstance(
                        column, str
                    ), f"Column {column} in {service_name}.{action_name} should be string"

    def test_descriptions_present(self):
        """Test that descriptions are present for all configurations."""
        config = load_default_filters()

        for service_name, service_config in config.items():
            for action_name, action_config in service_config.items():
                assert (
                    "description" in action_config
                ), f"Description missing for {service_name}.{action_name}"
                assert isinstance(
                    action_config["description"], str
                ), f"Description for {service_name}.{action_name} should be string"
                assert (
                    len(action_config["description"]) > 0
                ), f"Description for {service_name}.{action_name} should not be empty"
