"""Config loading tests."""

import os
from unittest.mock import Mock, mock_open, patch

import pytest
import yaml

from awsquery.config import load_default_filters


class TestDefaultFiltersConfig:
    """Test default filters configuration loading."""

    def test_load_default_filters_from_real_yaml(self):
        """Test loading default filters from the real YAML file."""
        result = load_default_filters()

        # Test that we get the real configuration
        assert "ec2" in result
        assert "describe_instances" in result["ec2"]
        assert "lambda" in result
        assert "s3" in result

        # Test actual values from the real config file
        ec2_columns = result["ec2"]["describe_instances"]["columns"]
        assert ec2_columns == [
            "Tags.Name$",
            "InstanceId$",
            "InstanceType$",
            "State.Name$",
            "InstanceLifecycle$",
            "LaunchTime$",
            "Placement$",
            "AvailabilityZone$",
            "PublicIpAddress$",
            "PrivateIpAddress$",
        ]
        assert result["s3"]["list_buckets"]["columns"] == ["Name$", "CreationDate$"]

    def test_get_default_columns_with_real_config(self):
        """Test get_default_columns function with real configuration."""
        from awsquery.config import get_default_columns

        # Test with real config - should work with actual EC2 describe_instances
        columns = get_default_columns("ec2", "describe_instances")
        assert isinstance(columns, list)
        assert len(columns) > 0

        # Test case insensitivity with real config
        columns_upper = get_default_columns("EC2", "DESCRIBE_INSTANCES")
        assert columns_upper == columns

        # Test non-existent service/action
        empty_columns = get_default_columns("nonexistent", "action")
        assert empty_columns == []
