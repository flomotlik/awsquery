"""Unit tests for default column filters functionality."""

import os
import tempfile
from unittest.mock import patch

import pytest

from awsquery.cli import determine_column_filters
from awsquery.config import apply_default_filters, get_default_columns, load_default_filters

# Cache can be persistent since we use real config file


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
        assert columns == expected

    def test_existing_service_different_action(self):
        """Test retrieving columns for different action of same service."""
        columns = get_default_columns("ec2", "describe_security_groups")

        expected = ["GroupName$", "Description$", "GroupId$", "VpcId$"]
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

        assert s3_columns == ["Name$", "CreationDate$"]
        assert lambda_columns == [
            "FunctionName$",
            "Runtime$",
            "Timeout$",
            "MemorySize$",
            "Handler$",
            "LastModified$",
            "FunctionArn$",
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
        assert result == expected

    def test_empty_user_columns_returns_defaults(self):
        """Test that defaults are returned when empty user columns provided."""
        result = apply_default_filters("ec2", "describe_instances", [])

        expected = [
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
        assert result == expected

    def test_none_user_columns_gets_defaults(self):
        """Test that defaults are applied when user columns are None."""
        result = determine_column_filters(None, "s3", "list_buckets")

        expected = ["Name$", "CreationDate$"]
        assert result == expected

    def test_unknown_service_action_returns_none(self):
        """Test that None is returned for unknown service/action."""
        result = determine_column_filters(None, "unknown", "action")

        assert result is None


class TestApplyDefaultFiltersAdditive:

    def test_additive_true_merges_defaults_and_user_columns(self):
        result = apply_default_filters(
            "ec2", "describe_instances", user_columns=["OwnerId"], additive=True
        )
        defaults = get_default_columns("ec2", "describe_instances")
        assert result == list(defaults) + ["OwnerId"]

    def test_additive_true_preserves_defaults_order_first(self):
        result = apply_default_filters(
            "ec2", "describe_instances", user_columns=["X", "Y", "Z"], additive=True
        )
        defaults = get_default_columns("ec2", "describe_instances")
        assert result[: len(defaults)] == list(defaults)
        assert result[len(defaults) :] == ["X", "Y", "Z"]

    def test_additive_true_dedup_collapses_exact_string_duplicates(self):
        defaults = get_default_columns("ec2", "describe_instances")
        duplicate = defaults[0]
        result = apply_default_filters(
            "ec2", "describe_instances", user_columns=[duplicate, "NewCol"], additive=True
        )
        assert result.count(duplicate) == 1
        assert result.index(duplicate) == 0
        assert "NewCol" in result

    def test_additive_true_dedup_is_case_sensitive(self):
        defaults = get_default_columns("ec2", "describe_instances")
        first_default = defaults[0]
        lowered = first_default.lower()
        if lowered == first_default:
            pytest.skip("default already lowercase")
        result = apply_default_filters(
            "ec2", "describe_instances", user_columns=[lowered], additive=True
        )
        assert first_default in result
        assert lowered in result

    def test_additive_true_empty_user_returns_defaults(self):
        result = apply_default_filters("ec2", "describe_instances", user_columns=[], additive=True)
        assert result == get_default_columns("ec2", "describe_instances")

    def test_additive_true_none_user_returns_defaults(self):
        result = apply_default_filters(
            "ec2", "describe_instances", user_columns=None, additive=True
        )
        assert result == get_default_columns("ec2", "describe_instances")

    def test_additive_true_no_defaults_returns_user_columns(self):
        result = apply_default_filters(
            "nonexistent", "action", user_columns=["A", "B"], additive=True
        )
        assert result == ["A", "B"]

    def test_additive_false_byte_identical_to_today(self):
        result_default = apply_default_filters("ec2", "describe_instances", ["X"])
        result_explicit = apply_default_filters(
            "ec2", "describe_instances", user_columns=["X"], additive=False
        )
        assert result_default == ["X"]
        assert result_explicit == ["X"]


class TestDetermineColumnFiltersAdditive:

    def test_plus_prefix_triggers_additive_mode(self):
        result = determine_column_filters(
            ["+OwnerId"], "ec2", "describe_instances", json_output=True
        )
        defaults = get_default_columns("ec2", "describe_instances")
        assert result == list(defaults) + ["OwnerId"]
        assert not any(c.startswith("+") for c in result)

    def test_mixed_plus_and_bare_triggers_additive(self):
        result = determine_column_filters(
            ["Bar", "+Foo"], "ec2", "describe_instances", json_output=True
        )
        defaults = get_default_columns("ec2", "describe_instances")
        assert result == list(defaults) + ["Bar", "Foo"]

    def test_multiple_plus_columns(self):
        result = determine_column_filters(
            ["+A", "+B"], "ec2", "describe_instances", json_output=True
        )
        defaults = get_default_columns("ec2", "describe_instances")
        assert result == list(defaults) + ["A", "B"]

    def test_bare_only_replaces_defaults(self):
        result = determine_column_filters(["Foo"], "ec2", "describe_instances", json_output=True)
        assert result == ["Foo"]

    def test_additive_stderr_echo_renders_plus(self, capsys):
        determine_column_filters(["+OwnerId"], "ec2", "describe_instances", json_output=False)
        err = capsys.readouterr().err
        assert "Using default columns + additions:" in err
        assert "+OwnerId" in err

    def test_additive_no_validator_warnings_for_tag_columns(self, capsys):
        determine_column_filters(["+Tags.Name"], "ec2", "describe_instances", json_output=False)
        err = capsys.readouterr().err
        assert "WARNING: Some column filters may not match" not in err

    def test_additive_falls_back_to_user_when_no_defaults(self):
        result = determine_column_filters(
            ["+Foo"], "unknown_service", "unknown_action", json_output=True
        )
        assert result == ["Foo"]

    def test_plus_strip_happens_before_validator(self):
        # The validator short-circuits on 'tag' in filter.lower(); '+InstanceId'
        # has no 'tag' substring so without the upstream strip the validator
        # would receive a literal '+InstanceId' (which isn't a real field) and
        # warn. With the strip in place no warning fires.
        result = determine_column_filters(
            ["+InstanceId"], "ec2", "describe_instances", json_output=True
        )
        assert "InstanceId" in result
        assert "+InstanceId" not in result


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

    def test_descriptions_not_required(self):
        """Test that configurations work without descriptions."""
        config = load_default_filters()

        # Verify that configurations can exist without descriptions
        # (descriptions are optional in the YAML format)
        for service_name, service_config in config.items():
            for action_name, action_config in service_config.items():
                # Only check that columns exist if present
                if "columns" in action_config:
                    assert isinstance(action_config["columns"], list)

    def test_audit_clean_for_in_scope_fixes(self):
        import sys as _sys
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        _sys.path.insert(0, str(scripts_dir))
        try:
            from audit_default_filters import audit_default_filters
        finally:
            try:
                _sys.path.remove(str(scripts_dir))
            except ValueError:
                pass

        report = audit_default_filters()
        broken_keys = {(svc, op) for svc, op, *_ in report["broken"]}
        in_scope = {
            ("directconnect", "describe_direct_connect_gateways"),
            ("ec2", "describe_vpcs"),
            ("ecr", "describe_images"),
            ("redshift", "describe_cluster_parameter_groups"),
            ("redshift", "describe_cluster_security_groups"),
        }
        leaked = in_scope & broken_keys
        assert not leaked, f"audit regressed for in-scope fixes: {leaked}"
