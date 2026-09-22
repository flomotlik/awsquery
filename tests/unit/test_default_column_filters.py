"""Unit tests for default column filters functionality."""

import os
import tempfile
from functools import lru_cache
from unittest.mock import patch

import pytest
from botocore.loaders import Loader
from botocore.model import ServiceModel

from awsquery.case_utils import to_kebab_case, to_pascal_case, to_snake_case
from awsquery.cli import determine_column_filters
from awsquery.config import (
    apply_default_filters,
    get_default_columns,
    load_data_fields,
    load_default_actions,
    load_default_filters,
)
from awsquery.filters import matches_pattern, parse_filter_pattern
from awsquery.formatters import flatten_dict_keys, flatten_response
from awsquery.security import is_readonly_operation
from awsquery.shapes import METADATA_FIELDS, ShapeCache, get_shape_cache

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
            "AvailabilityZone$",
            "PublicIpAddress$",
            "PrivateIpAddress$",
        ]
        assert columns == expected

    def test_existing_service_different_action(self):
        """Test retrieving columns for different action of same service."""
        columns = get_default_columns("ec2", "describe_security_groups")

        expected = ["^GroupName$", "^Description$", "^GroupId$", "^VpcId$"]
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
            "^Timeout$",
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


def _data_field_overrides():
    """Every entry of data_fields.yaml as (service, action, field)."""
    return sorted(
        (service, action, field)
        for service, actions in load_data_fields().items()
        for action, field in actions.items()
    )


class TestDataFieldOverrides:
    """Per-entry validation guard for src/awsquery/data_fields.yaml."""

    @pytest.mark.parametrize("service,action,field", _data_field_overrides())
    def test_override_names_a_list_member_of_the_service_model(self, service, action, field):
        shape = ShapeCache().get_operation_shape(service, action)

        assert shape is not None, f"{service} {action} has no output shape"
        assert field in shape.members, f"{service} {action} has no member {field}"
        assert shape.members[field].type_name == "list"

    @pytest.mark.parametrize("service,action,field", _data_field_overrides())
    def test_override_wins_over_the_shape_heuristic(self, service, action, field):
        data_field, _, _ = ShapeCache().get_response_fields(service, action)

        assert data_field == field

    @pytest.mark.parametrize("service,action,field", _data_field_overrides())
    def test_two_records_stay_two_resources(self, service, action, field):
        response = {field: [{"Probe": "first"}, {"Probe": "second"}], "Wrapper": "ignored"}

        result = flatten_response(response, service, action)

        assert [item["Probe"] for item in result] == ["first", "second"]

    @pytest.mark.parametrize("service,action", [(s, a) for s, a, _ in _data_field_overrides()])
    def test_override_key_matches_the_curated_filters(self, service, action):
        assert action in load_default_filters().get(service, {})

    def test_stale_override_falls_back_to_the_shape(self):
        cache = ShapeCache()
        shape = cache.get_operation_shape("s3", "get-bucket-acl")

        with patch("awsquery.shapes.get_data_field_override", return_value="RemovedMember"):
            assert cache.identify_data_field(shape, "s3", "get-bucket-acl") is None


class TestDefaultActionsMap:
    """Whole-map validation guard for src/awsquery/default_actions.yaml."""

    _loader = Loader()
    _models: dict = {}

    @classmethod
    def _get_model(cls, service):
        if service not in cls._models:
            versions = cls._loader.list_api_versions(service, "service-2")
            service_data = cls._loader.load_service_model(service, "service-2", versions[-1])
            cls._models[service] = ServiceModel(service_data)
        return cls._models[service]

    @pytest.mark.parametrize("service,action", sorted(load_default_actions().items()))
    def test_default_action_entry_is_valid(self, service, action):
        available_services = self._loader.list_available_services("service-2")
        assert service in available_services

        model = self._get_model(service)
        pascal_lower = to_pascal_case(to_snake_case(action)).lower()
        matched = next((op for op in model.operation_names if op.lower() == pascal_lower), None)
        assert matched is not None, f"{action} has no matching operation for {service}"

        operation = model.operation_model(matched)
        input_shape = operation.input_shape
        assert input_shape is None or not input_shape.required_members

        assert is_readonly_operation(action) is True
        assert action == to_kebab_case(to_snake_case(action))
        assert to_snake_case(action) in load_default_filters().get(service, {})

    def test_default_actions_are_subset_of_default_filters(self):
        assert set(load_default_actions()) <= set(load_default_filters())


# Sentinels the synthetic response carries so that map keys and tag names - user
# data the service model knows nothing about - are recognisable in a flat key.
_MAP_KEY = "__awsquery_map_key__"
_STRING_VALUE = "__awsquery_string__"
_DYNAMIC_SEGMENTS = (_MAP_KEY, _STRING_VALUE)
_MAX_SAMPLE_DEPTH = 6


def _sample_for_shape(shape, depth=0, path=()):
    """Build one synthetic response member from a botocore shape."""
    kind = shape.type_name
    if kind == "structure":
        if shape.name in path or depth > _MAX_SAMPLE_DEPTH:
            return {}
        deeper = path + (shape.name,)
        return {
            name: _sample_for_shape(member, depth + 1, deeper)
            for name, member in shape.members.items()
        }
    if kind == "list":
        return (
            [] if depth > _MAX_SAMPLE_DEPTH else [_sample_for_shape(shape.member, depth + 1, path)]
        )
    if kind == "map":
        if depth > _MAX_SAMPLE_DEPTH:
            return {}
        return {_MAP_KEY: _sample_for_shape(shape.value, depth + 1, path)}
    if kind in ("integer", "long"):
        return 1
    if kind in ("float", "double"):
        return 1.0
    if kind == "boolean":
        return True
    if kind == "timestamp":
        return "1970-01-01T00:00:00Z"
    return _STRING_VALUE


def _runtime_shape(service, action):
    """What one rendered resource of service.action really looks like.

    Returns (kind, keys, map_containers) where kind is one of:
      "fields"  - a structure whose flat keys are `keys`
      "strings" - bare strings, which render under the single key `value`
      "map"     - a map whose keys are account data rather than model
                  (iam get-account-summary renders its columns out of SummaryMap)
      "unknown" - no output shape, or nothing the sampler can render

    `map_containers` names the members holding such a map. Their keys are
    unknowable, so a column drilling through one is left alone - but a column
    naming the container itself never reaches a key inside it.
    """
    shape = get_shape_cache().get_operation_shape(service, action)
    if shape is None:
        return "unknown", (), ()
    sample = _sample_for_shape(shape)
    if not isinstance(sample, dict):
        return "unknown", (), ()
    # Pagination state is stripped long before anything renders, so never a column.
    sample = {name: value for name, value in sample.items() if name not in METADATA_FIELDS}
    resources = flatten_response(sample, service, action)
    if not resources:
        return "unknown", (), ()
    if not isinstance(resources[0], dict):
        return "strings", ("value",), ()
    keys = list(flatten_dict_keys(resources[0]))
    if keys == ["value"]:
        return "strings", ("value",), ()

    static, containers = [], set()
    for key in keys:
        segments = key.split(".")
        dynamic = [i for i, segment in enumerate(segments) if segment in _DYNAMIC_SEGMENTS]
        if not dynamic:
            static.append(key)
            continue
        named = [segment for segment in segments[: dynamic[0]] if not segment.isdigit()]
        if not named:
            return "map", (), ()
        containers.add(named[-1])
    return "fields", tuple(static), tuple(sorted(containers))


def _column_complaint(column, keys, containers):
    """Say why this column filter is wrong for these runtime keys, or None."""
    pattern, mode = parse_filter_pattern(column)
    segments = pattern.split(".")
    if any(segment in containers for segment in segments[:-1]):
        return None  # drills into a map, whose keys are data rather than model
    if segments[-1] in containers:
        if mode in ("suffix", "exact"):
            return f"'{column}' names the map '{segments[-1]}', never a key inside it"
        return None  # unanchored, so it still reaches the keys inside that map

    matches = [key for key in keys if matches_pattern(key, pattern, mode)]
    if not matches:
        return f"'{column}' matches nothing in {list(keys)}"
    if len(matches) == 1 or mode == "exact":
        return None

    top_level = {key.lower(): key for key in keys if "." not in key}
    if pattern.lower() in top_level:
        return f"'{column}' matches {matches}; anchor it as '^{top_level[pattern.lower()]}$'"

    same_leaf = [key for key in matches if key.split(".")[-1].lower() == pattern.lower()]
    if not same_leaf:
        return None  # no field of this name; the extra hits are chance suffixes
    shallowest = min(same_leaf, key=lambda key: (key.count("."), key))
    depth = shallowest.count(".")
    if len([key for key in same_leaf if key.count(".") == depth]) > 1:
        return None  # equally shallow siblings, so no path is the obvious one
    if any(segment.isdigit() for segment in shallowest.split(".")):
        return None  # under a list, where an anchored index would pin item zero
    return f"'{column}' matches {matches}; anchor it as '^{shallowest}$'"


def _string_list_complaints(columns):
    """A response of bare strings renders one column, and it is always 'value'."""
    if columns == ["value$"]:
        return ()
    return (f"a list of bare strings renders ['value$'], not {columns}",)


@lru_cache(maxsize=1)
def _default_filter_complaints():
    """Audit every curated column against the response it will really render.

    One sweep for the whole file: the shared shape cache is reset between tests,
    so per-test sampling would reload each service model hundreds of times.
    """
    complaints = {}
    for service, actions in load_default_filters().items():
        for action, config in actions.items():
            kind, keys, containers = _runtime_shape(service, action)
            columns = config.get("columns") or []
            if kind == "strings":
                complaints[(service, action)] = _string_list_complaints(columns)
                continue
            if kind != "fields":
                continue
            complaints[(service, action)] = tuple(
                complaint
                for complaint in (_column_complaint(column, keys, containers) for column in columns)
                if complaint
            )
    return complaints


def _default_filter_entries():
    """Every entry of default_filters.yaml as (service, action)."""
    return sorted(
        (service, action)
        for service, actions in load_default_filters().items()
        for action in actions
    )


class TestDefaultColumnsSelectRealFields:
    """Per-entry validation guard for src/awsquery/default_filters.yaml."""

    @pytest.mark.parametrize("service,action", _default_filter_entries())
    def test_every_curated_column_picks_out_its_field(self, service, action):
        complaints = _default_filter_complaints().get((service, action), ())

        assert not complaints, f"{service} {action}\n  " + "\n  ".join(complaints)

    def test_the_sweep_covers_the_bulk_of_the_file(self):
        audited = len(_default_filter_complaints())
        total = len(_default_filter_entries())

        assert audited >= total * 0.95, f"only {audited} of {total} entries were sampled"

    def test_a_map_backed_response_is_left_alone(self):
        kind, keys, _ = _runtime_shape("iam", "get_account_summary")

        assert (kind, keys) == ("map", ())
        assert _default_filter_complaints().get(("iam", "get_account_summary")) is None

    def test_a_string_list_response_is_held_to_its_one_column(self):
        kind, keys, _ = _runtime_shape("ecs", "list_clusters")

        assert (kind, keys) == ("strings", ("value",))
        assert _string_list_complaints(["value$"]) == ()
        assert _string_list_complaints([]) != ()
        assert _string_list_complaints(["value$", "nextToken$"]) != ()

    def test_a_column_naming_no_field_is_reported(self):
        complaint = _column_complaint("NoSuchField$", ("StackName", "StackId"), ())

        assert complaint is not None
        assert "matches nothing" in complaint

    def test_a_column_shadowing_an_exact_field_is_reported(self):
        complaint = _column_complaint("Name$", ("Name", "Owner.Name"), ())

        assert complaint is not None
        assert "'^Name$'" in complaint

    def test_a_column_with_one_obvious_path_is_reported(self):
        complaint = _column_complaint("Name$", ("Owner.Name", "Owner.Group.0.Name"), ())

        assert complaint is not None
        assert "'^Owner.Name$'" in complaint

    def test_a_column_under_a_list_is_accepted(self):
        assert _column_complaint("Name$", ("Items.0.Name", "Items.0.Tag.Name"), ()) is None

    def test_a_column_drilling_into_a_map_is_accepted(self):
        assert _column_complaint("Tags.Name$", ("InstanceId",), ("Tags",)) is None

    def test_a_column_naming_a_map_container_is_reported(self):
        complaint = _column_complaint("Tags$", ("InstanceId",), ("Tags",))

        assert complaint is not None
        assert "names the map 'Tags'" in complaint

    def test_an_unanchored_map_container_is_accepted(self):
        assert _column_complaint("Tags", ("InstanceId",), ("Tags",)) is None


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
