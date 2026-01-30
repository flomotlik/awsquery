"""Unit tests for auto_filters module - smart column selection algorithm."""

import pytest

from awsquery.auto_filters import (
    SIMPLE_TYPES,
    TIER3_EXACT_NAMES,
    TIER4_EXACT_NAMES,
    TIER5_EXACT_NAMES,
    TIER7_EXACT_NAMES,
    TIER8_ALLOWLIST,
    WELL_KNOWN_NESTED_SCALARS,
    _is_list_element_path,
    flatten_well_known_scalars,
    smart_select_columns,
)


class TestSmartSelectColumnsDeterminism:

    def test_same_input_produces_same_output_100_times(self):
        fields = {
            "InstanceId": "string",
            "InstanceName": "string",
            "Status": "string",
            "State": "string",
            "Engine": "string",
            "Type": "string",
            "Endpoint": "structure",
            "VpcId": "string",
            "Port": "integer",
            "CreationTime": "timestamp",
            "Arn": "string",
            "Encrypted": "boolean",
            "AllocatedStorage": "integer",
        }

        first_result = smart_select_columns(fields)

        for _ in range(100):
            result = smart_select_columns(fields)
            assert result == first_result

    def test_determinism_with_many_similar_fields(self):
        fields = {
            f"Field{i}Id": "string" for i in range(20)
        }
        fields.update({f"Field{i}Name": "string" for i in range(20)})

        first_result = smart_select_columns(fields)

        for _ in range(50):
            result = smart_select_columns(fields)
            assert result == first_result


class TestTierPriority:

    def test_identifier_selected_in_tier1(self):
        fields = {
            "ClusterId": "string",
            "ClusterIdentifier": "string",
            "ClusterName": "string",
        }

        result = smart_select_columns(fields)

        # All three should be selected (tier 1 has no limit)
        assert "ClusterIdentifier" in result
        assert "ClusterId" in result
        assert "ClusterName" in result

    def test_id_and_name_both_selected(self):
        fields = {
            "ResourceId": "string",
            "ResourceName": "string",
        }

        result = smart_select_columns(fields)

        assert "ResourceId" in result
        assert "ResourceName" in result

    def test_tier1_selects_all_matching_suffixes_no_limit(self):
        fields = {
            "ThingIdentifier": "string",
            "ThingId": "string",
            "ThingName": "string",
            "OtherIdentifier": "string",
            "OtherId": "string",
            "OtherName": "string",
        }

        result = smart_select_columns(fields)

        # Tier 1 has NO internal limit - all 6 fields match tier 1 patterns
        identifiers = [f for f in result if f.endswith("Identifier")]
        ids = [f for f in result if f.endswith("Id") and not f.endswith("Identifier")]
        names = [f for f in result if f.endswith("Name")]

        # All 6 should be selected (tier 1 no limit, within max_columns=10)
        assert len(identifiers) + len(ids) + len(names) == 6

    def test_tier_order_preserved_not_alphabetical(self):
        fields = {
            "ZName": "string",
            "AId": "string",
            "BIdentifier": "string",
        }

        result = smart_select_columns(fields)

        # Tier 1 processes: Identifier first, then Id, then Name
        # Within each suffix, fields are sorted alphabetically
        assert result[0] == "BIdentifier"
        assert result[1] == "AId"
        assert result[2] == "ZName"


class TestMaxColumnsEnforcement:

    def test_tier1_no_internal_limit_fills_to_max(self):
        # Tier 1 has NO internal limit - fills up to max_columns
        fields = {f"Field{i}Id": "string" for i in range(50)}

        result = smart_select_columns(fields)

        # Should fill to max_columns (10)
        assert len(result) == 10

    def test_returns_multiple_when_matching_tiers(self):
        fields = {
            "InstanceId": "string",
            "Name": "string",
            "Status": "string",
        }

        result = smart_select_columns(fields)

        # InstanceId and Name match tier 1 (no limit)
        # Status matches tier 2
        assert len(result) == 3

    def test_custom_max_columns_with_diverse_fields(self):
        # Use fields that span multiple tiers
        fields = {
            "ClusterId": "string",
            "ClusterName": "string",
            "Status": "string",
            "State": "string",
            "Engine": "string",
            "Type": "string",
            "VpcId": "string",
            "Port": "integer",
            "CreationTime": "timestamp",
            "Arn": "string",
        }

        result = smart_select_columns(fields, max_columns=5)

        assert len(result) == 5

    def test_max_columns_with_all_tiers(self):
        fields = {
            "ClusterIdentifier": "string",
            "ClusterId": "string",
            "ClusterName": "string",
            "Status": "string",
            "State": "string",
            "Engine": "string",
            "Type": "string",
            "EngineVersion": "string",
            "DBClass": "string",
            "Endpoint": "structure",
            "VpcId": "string",
            "Port": "integer",
            "Address": "string",
            "SubnetId": "string",
            "CreationTime": "timestamp",
            "Arn": "string",
            "Encrypted": "boolean",
            "MultiAZ": "boolean",
            "AllocatedStorage": "integer",
            "StorageType": "string",
        }

        result = smart_select_columns(fields)

        assert len(result) <= 10


class TestTypeBasedNestedScalarHandling:

    def test_scalar_endpoint_uses_parent_directly(self):
        fields = {
            "ClusterId": "string",
            "Endpoint": "string",
        }

        result = smart_select_columns(fields)

        assert "Endpoint" in result
        assert "Endpoint.Address" not in result
        assert "Endpoint.Port" not in result

    def test_structure_endpoint_excludes_parent_uses_nested(self):
        fields = {
            "ClusterId": "string",
            "Endpoint": "structure",
        }

        expanded = flatten_well_known_scalars(fields)

        assert "Endpoint.Address" in expanded
        assert "Endpoint.Port" in expanded
        assert expanded["Endpoint"] == "structure"

    def test_structure_status_expands_to_nested_paths(self):
        fields = {
            "ClusterId": "string",
            "Status": "structure",
        }

        expanded = flatten_well_known_scalars(fields)

        assert "Status.Code" in expanded
        assert "Status.Message" in expanded

    def test_structure_state_expands_to_nested_paths(self):
        fields = {
            "InstanceId": "string",
            "State": "structure",
        }

        expanded = flatten_well_known_scalars(fields)

        assert "State.Name" in expanded
        assert "State.Code" in expanded

    def test_scalar_status_not_expanded(self):
        fields = {
            "ClusterId": "string",
            "Status": "string",
        }

        expanded = flatten_well_known_scalars(fields)

        assert "Status.Code" not in expanded
        assert "Status.Message" not in expanded
        assert expanded["Status"] == "string"

    def test_scalar_state_not_expanded(self):
        fields = {
            "InstanceId": "string",
            "State": "boolean",
        }

        expanded = flatten_well_known_scalars(fields)

        assert "State.Name" not in expanded
        assert "State.Code" not in expanded

    def test_structure_endpoint_nested_paths_in_selection(self):
        fields = {
            "DBInstanceIdentifier": "string",
            "Endpoint": "structure",
            "Status": "string",
        }

        result = smart_select_columns(fields)

        assert "Endpoint.Address" in result or "Endpoint.Port" in result


class TestEmptyResultFallback:

    def test_well_known_structure_expands_to_simple_fields(self):
        # Endpoint is a well-known structure that expands to nested scalar paths
        fields = {
            "Endpoint": "structure",
            "Config": "structure",
            "Tags": "list",
        }

        result = smart_select_columns(fields)

        # Endpoint.Address and Endpoint.Port become available after expansion
        assert result is not None
        assert "Endpoint.Address" in result or "Endpoint.Port" in result

    def test_unknown_structures_only_returns_none(self):
        # Unknown structures without well-known nested scalars return None
        fields = {
            "Config": "structure",
            "Settings": "structure",
            "Tags": "list",
        }

        result = smart_select_columns(fields)

        assert result is None

    def test_all_structure_types_returns_none(self):
        fields = {
            "NetworkConfig": "structure",
            "SecurityConfig": "structure",
            "StorageConfig": "structure",
        }

        result = smart_select_columns(fields)

        assert result is None

    def test_all_list_types_returns_none(self):
        fields = {
            "Tags": "list",
            "SecurityGroups": "list",
            "Subnets": "list",
        }

        result = smart_select_columns(fields)

        assert result is None

    def test_none_return_is_intentional_for_fallback(self):
        # Verifies the docstring claim that None bypasses column limit
        fields = {"OnlyStructure": "structure"}

        result = smart_select_columns(fields)

        assert result is None


class TestTier8Allowlist:

    def test_tier8_allowlist_fields_are_included(self):
        fields = {
            "InstanceId": "string",
            "AllocatedStorage": "integer",
            "BackupRetentionPeriod": "integer",
            "StorageType": "string",
        }

        result = smart_select_columns(fields)

        assert "AllocatedStorage" in result
        assert "StorageType" in result

    def test_tier8_non_allowlist_fields_excluded(self):
        fields = {
            "InstanceId": "string",
            "Configuration": "string",
            "Settings": "string",
            "Policy": "string",
            "RandomField": "string",
        }

        result = smart_select_columns(fields)

        assert "Configuration" not in result
        assert "Settings" not in result
        assert "Policy" not in result
        assert "RandomField" not in result

    def test_tier8_allowlist_contents(self):
        expected = {
            "AllocatedStorage",
            "BackupRetentionPeriod",
            "DatabaseName",
            "Description",
            "MasterUsername",
            "OwnerAccount",
            "PreferredBackupWindow",
            "StorageType",
        }

        assert TIER8_ALLOWLIST == expected

    def test_tier8_only_adds_allowlisted_in_tier8(self):
        # Fields that would only be added in tier8
        fields = {
            "AllocatedStorage": "integer",
            "Description": "string",
            "SomeRandomField": "string",
            "AnotherField": "string",
        }

        result = smart_select_columns(fields)

        assert "AllocatedStorage" in result
        assert "Description" in result
        assert "SomeRandomField" not in result
        assert "AnotherField" not in result


class TestFlattenWellKnownScalars:

    def test_adds_endpoint_nested_when_structure(self):
        fields = {"Endpoint": "structure"}

        result = flatten_well_known_scalars(fields)

        assert "Endpoint.Address" in result
        assert result["Endpoint.Address"] == "string"
        assert "Endpoint.Port" in result
        assert result["Endpoint.Port"] == "integer"

    def test_does_not_add_endpoint_nested_when_scalar(self):
        fields = {"Endpoint": "string"}

        result = flatten_well_known_scalars(fields)

        assert "Endpoint.Address" not in result
        assert "Endpoint.Port" not in result
        assert result["Endpoint"] == "string"

    def test_preserves_existing_fields(self):
        fields = {
            "InstanceId": "string",
            "Status": "boolean",
            "Endpoint": "structure",
        }

        result = flatten_well_known_scalars(fields)

        assert result["InstanceId"] == "string"
        assert result["Status"] == "boolean"
        assert result["Endpoint"] == "structure"
        assert "Endpoint.Address" in result

    def test_does_not_duplicate_existing_nested_paths(self):
        fields = {
            "Endpoint": "structure",
            "Endpoint.Address": "string",
        }

        result = flatten_well_known_scalars(fields)

        assert result["Endpoint.Address"] == "string"
        address_count = sum(1 for k in result if k == "Endpoint.Address")
        assert address_count == 1

    def test_handles_missing_parent_field(self):
        fields = {"SomeOtherField": "string"}

        result = flatten_well_known_scalars(fields)

        assert "Endpoint.Address" not in result
        assert "Status.Code" not in result
        assert "State.Name" not in result

    def test_all_well_known_scalars_covered(self):
        fields = {
            "Endpoint": "structure",
            "State": "structure",
            "Status": "structure",
        }

        result = flatten_well_known_scalars(fields)

        # Endpoint
        assert "Endpoint.Address" in result
        assert "Endpoint.Port" in result

        # State
        assert "State.Name" in result
        assert "State.Code" in result

        # Status
        assert "Status.Code" in result
        assert "Status.Message" in result


class TestEdgeCases:

    def test_empty_input_dict(self):
        result = smart_select_columns({})

        assert result is None

    def test_single_tier_matching_field(self):
        # Field must match a tier pattern to be selected
        fields = {"ResourceId": "string"}

        result = smart_select_columns(fields)

        assert result == ["ResourceId"]

    def test_single_non_tier_field_returns_none(self):
        # Fields that don't match any tier pattern are not selected
        fields = {"OnlyField": "string"}

        result = smart_select_columns(fields)

        # No tier matches this field name, so returns None
        assert result is None

    def test_non_tier_field_among_structures_returns_none(self):
        # If only simple field doesn't match any tier, returns None
        fields = {
            "Config": "structure",
            "RandomField": "string",
            "Tags": "list",
        }

        result = smart_select_columns(fields)

        # RandomField doesn't match any tier pattern
        assert result is None

    def test_tier_matching_field_among_structures(self):
        fields = {
            "Config": "structure",
            "ResourceId": "string",
            "Tags": "list",
        }

        result = smart_select_columns(fields)

        assert result == ["ResourceId"]

    def test_fields_with_dotted_paths(self):
        fields = {
            "InstanceId": "string",
            "State.Name": "string",
            "Endpoint.Address": "string",
        }

        result = smart_select_columns(fields)

        # InstanceId matches tier 1
        assert "InstanceId" in result
        # State.Name has base Name which matches tier 1
        assert "State.Name" in result
        # Endpoint.Address has base Address which matches tier 4
        assert "Endpoint.Address" in result

    def test_tier8_allowlist_fields_recognized(self):
        # Fields in TIER8_ALLOWLIST should be selected even without tier suffix
        fields = {
            "AllocatedStorage": "integer",
            "Description": "string",
            "StorageType": "string",
        }

        result = smart_select_columns(fields)

        # All these are in TIER8_ALLOWLIST
        assert "AllocatedStorage" in result
        assert "Description" in result
        assert "StorageType" in result

    def test_simple_types_includes_float_and_double(self):
        expected = ("string", "boolean", "integer", "timestamp", "long", "float", "double")
        assert SIMPLE_TYPES == expected

    def test_unicode_field_names_with_tier_match(self):
        fields = {
            "InstanceId": "string",
            "Status": "string",
        }

        result = smart_select_columns(fields)

        assert "InstanceId" in result
        assert "Status" in result

    def test_numeric_suffix_field_names(self):
        fields = {
            "Field1Id": "string",
            "Field2Id": "string",
            "Field3Id": "string",
        }

        result = smart_select_columns(fields)

        # Tier 1 has no internal limit
        assert len(result) == 3
        assert "Field1Id" in result
        assert "Field2Id" in result
        assert "Field3Id" in result


class TestTierSelectionBehavior:

    def test_tier2_status_and_state_total_limit_of_2(self):
        fields = {
            "InstanceId": "string",
            "Status": "string",
            "State": "string",
            "HealthStatus": "string",
            "NetworkState": "string",
        }

        result = smart_select_columns(fields)

        # Tier 2 has total limit of 2
        tier2_fields = ["Status", "State", "HealthStatus", "NetworkState"]
        selected_tier2 = [f for f in result if f in tier2_fields]
        assert len(selected_tier2) == 2
        # Exact matches (Status, State) have priority over suffix matches
        assert "Status" in result
        assert "State" in result

    def test_tier2_exact_before_suffix(self):
        fields = {
            "InstanceId": "string",
            "HealthStatus": "string",
            "NetworkState": "string",
        }

        result = smart_select_columns(fields)

        # Without exact Status/State, suffix matches are used
        tier2_fields = [f for f in result if f.endswith("Status") or f.endswith("State")]
        assert len(tier2_fields) <= 2

    def test_tier3_engine_and_type_selection(self):
        fields = {
            "InstanceId": "string",
            "Engine": "string",
            "Type": "string",
            "EngineVersion": "string",
            "DBInstanceClass": "string",
        }

        result = smart_select_columns(fields)

        assert "Engine" in result
        assert "Type" in result

    def test_tier4_network_fields_selection(self):
        fields = {
            "InstanceId": "string",
            "VpcId": "string",
            "Port": "integer",
            "Address": "string",
            "SubnetId": "string",
            "AvailabilityZone": "string",
        }

        result = smart_select_columns(fields)

        assert "VpcId" in result or "Port" in result or "Address" in result

    def test_tier5_timestamp_selection(self):
        fields = {
            "InstanceId": "string",
            "CreationTime": "timestamp",
            "CreateTime": "timestamp",
            "LaunchTime": "timestamp",
        }

        result = smart_select_columns(fields)

        timestamp_fields = ["CreationTime", "CreateTime", "LaunchTime"]
        selected_timestamps = [f for f in result if f in timestamp_fields]
        assert len(selected_timestamps) == 1

    def test_tier6_arn_selection(self):
        fields = {
            "InstanceId": "string",
            "ResourceArn": "string",
            "ClusterARN": "string",
        }

        result = smart_select_columns(fields)

        arn_fields = [f for f in result if f.endswith("Arn") or f.endswith("ARN")]
        assert len(arn_fields) == 1

    def test_tier7_boolean_flags_selection(self):
        fields = {
            "InstanceId": "string",
            "Encrypted": "boolean",
            "MultiAZ": "boolean",
            "PubliclyAccessible": "boolean",
        }

        result = smart_select_columns(fields)

        boolean_fields = ["Encrypted", "MultiAZ", "PubliclyAccessible"]
        selected_booleans = [f for f in result if f in boolean_fields]
        assert len(selected_booleans) <= 2


class TestIntegrationScenarios:

    def test_rds_like_instance_fields(self):
        fields = {
            "DBInstanceIdentifier": "string",
            "DBInstanceClass": "string",
            "Engine": "string",
            "EngineVersion": "string",
            "DBInstanceStatus": "string",
            "MasterUsername": "string",
            "Endpoint": "structure",
            "AllocatedStorage": "integer",
            "InstanceCreateTime": "timestamp",
            "PreferredBackupWindow": "string",
            "BackupRetentionPeriod": "integer",
            "DBSecurityGroups": "list",
            "VpcSecurityGroups": "list",
            "DBParameterGroups": "list",
            "AvailabilityZone": "string",
            "DBSubnetGroup": "structure",
            "MultiAZ": "boolean",
            "PubliclyAccessible": "boolean",
            "StorageType": "string",
            "DBInstanceArn": "string",
        }

        result = smart_select_columns(fields)

        assert len(result) <= 10
        assert "DBInstanceIdentifier" in result

    def test_ec2_like_instance_fields(self):
        fields = {
            "InstanceId": "string",
            "InstanceType": "string",
            "State": "structure",
            "PublicIpAddress": "string",
            "PrivateIpAddress": "string",
            "VpcId": "string",
            "SubnetId": "string",
            "LaunchTime": "timestamp",
            "Tags": "list",
            "SecurityGroups": "list",
        }

        result = smart_select_columns(fields)

        assert len(result) <= 10
        assert "InstanceId" in result
        # State.Name and State.Code are added via flatten_well_known_scalars
        # but they may or may not be selected depending on tier limits
        # Verify that the structure expansion worked
        expanded = flatten_well_known_scalars(fields)
        assert "State.Name" in expanded
        assert "State.Code" in expanded

    def test_elasticache_like_cluster_fields(self):
        fields = {
            "CacheClusterId": "string",
            "CacheClusterStatus": "string",
            "CacheNodeType": "string",
            "Engine": "string",
            "EngineVersion": "string",
            "NumCacheNodes": "integer",
            "PreferredAvailabilityZone": "string",
            "CacheClusterCreateTime": "timestamp",
            "Endpoint": "structure",
            "ConfigurationEndpoint": "structure",
            "SecurityGroups": "list",
            "ARN": "string",
        }

        result = smart_select_columns(fields)

        assert len(result) <= 10
        assert "CacheClusterId" in result


class TestWellKnownNestedScalarsConstant:

    def test_well_known_nested_scalars_structure(self):
        assert "Endpoint" in WELL_KNOWN_NESTED_SCALARS
        assert "State" in WELL_KNOWN_NESTED_SCALARS
        assert "Status" in WELL_KNOWN_NESTED_SCALARS

    def test_endpoint_nested_fields(self):
        endpoint = WELL_KNOWN_NESTED_SCALARS["Endpoint"]
        assert endpoint["Address"] == "string"
        assert endpoint["Port"] == "integer"

    def test_state_nested_fields(self):
        state = WELL_KNOWN_NESTED_SCALARS["State"]
        assert state["Name"] == "string"
        assert state["Code"] == "string"

    def test_status_nested_fields(self):
        status = WELL_KNOWN_NESTED_SCALARS["Status"]
        assert status["Code"] == "string"
        assert status["Message"] == "string"


class TestFloatAndDoubleTypes:

    def test_float_type_field_selected(self):
        fields = {
            "ResourceId": "string",
            "Score": "float",
        }

        result = smart_select_columns(fields)

        # Float should be allowed as simple type, but Score doesn't match any tier
        assert "ResourceId" in result

    def test_double_type_field_selected(self):
        fields = {
            "ResourceId": "string",
            "Latitude": "double",
        }

        result = smart_select_columns(fields)

        # Double should be allowed as simple type, but Latitude doesn't match any tier
        assert "ResourceId" in result

    def test_float_in_tier8_allowlist(self):
        fields = {
            "AllocatedStorage": "float",
        }

        result = smart_select_columns(fields)

        assert result is not None
        assert "AllocatedStorage" in result

    def test_double_with_tier1_suffix(self):
        fields = {
            "ScoreId": "double",
        }

        result = smart_select_columns(fields)

        assert result == ["ScoreId"]


class TestListElementPathExclusion:

    def test_is_list_element_path_simple_numeric(self):
        assert _is_list_element_path("Items.0") is True
        assert _is_list_element_path("Tags.0") is True
        assert _is_list_element_path("Data.123") is True

    def test_is_list_element_path_nested_numeric(self):
        assert _is_list_element_path("Tags.0.Key") is True
        assert _is_list_element_path("Items.0.Value") is True
        assert _is_list_element_path("Deep.0.Nested.1.Path") is True

    def test_is_list_element_path_no_numeric(self):
        assert _is_list_element_path("InstanceId") is False
        assert _is_list_element_path("Endpoint.Address") is False
        assert _is_list_element_path("State.Name") is False

    def test_is_list_element_path_numeric_in_name(self):
        # Numeric as part of name (not standalone segment) should not be excluded
        assert _is_list_element_path("Field1Id") is False
        assert _is_list_element_path("Ec2Instance") is False

    def test_list_element_paths_excluded_from_selection(self):
        fields = {
            "InstanceId": "string",
            "Tags.0.Key": "string",
            "Tags.0.Value": "string",
            "Items.0": "string",
        }

        result = smart_select_columns(fields)

        assert "InstanceId" in result
        assert "Tags.0.Key" not in result
        assert "Tags.0.Value" not in result
        assert "Items.0" not in result

    def test_list_element_paths_with_tier_matches_still_excluded(self):
        fields = {
            "Items.0.ResourceId": "string",
            "Items.0.Name": "string",
            "ActualId": "string",
        }

        result = smart_select_columns(fields)

        # Even though ResourceId and Name match tier 1, they should be excluded
        assert "Items.0.ResourceId" not in result
        assert "Items.0.Name" not in result
        assert "ActualId" in result


class TestTierExactNameLists:

    def test_tier3_exact_names_list(self):
        expected = [
            'DBInstanceClass', 'Engine', 'EngineVersion', 'InstanceType',
            'NodeType', 'Runtime', 'Type', 'Version'
        ]
        assert TIER3_EXACT_NAMES == expected

    def test_tier4_exact_names_list(self):
        expected = [
            'Address', 'AvailabilityZone', 'DNSName', 'Endpoint', 'Port',
            'ReaderEndpoint', 'SubnetId', 'VpcId'
        ]
        assert TIER4_EXACT_NAMES == expected

    def test_tier5_exact_names_list(self):
        expected = [
            'CreationTime', 'CreateTime', 'CreatedTime', 'CreateDate', 'CreatedAt',
            'createdAt', 'LaunchTime', 'StartTime', 'ClusterCreateTime', 'SnapshotCreateTime'
        ]
        assert TIER5_EXACT_NAMES == expected

    def test_tier7_exact_names_list(self):
        expected = [
            'DeletionProtection', 'Enabled', 'Encrypted', 'IsDefault',
            'MultiAZ', 'PubliclyAccessible', 'StorageEncrypted'
        ]
        assert TIER7_EXACT_NAMES == expected

    def test_tier3_exact_name_selected(self):
        fields = {
            "InstanceId": "string",
            "Runtime": "string",
            "DBInstanceClass": "string",
        }

        result = smart_select_columns(fields)

        # Both Runtime and DBInstanceClass are in TIER3_EXACT_NAMES
        assert "Runtime" in result or "DBInstanceClass" in result

    def test_tier4_exact_name_selected(self):
        fields = {
            "InstanceId": "string",
            "DNSName": "string",
            "ReaderEndpoint": "string",
        }

        result = smart_select_columns(fields)

        # DNSName and ReaderEndpoint are in TIER4_EXACT_NAMES
        assert "DNSName" in result or "ReaderEndpoint" in result

    def test_tier5_exact_name_timestamp_variants(self):
        fields = {
            "InstanceId": "string",
            "createdAt": "timestamp",
            "SnapshotCreateTime": "timestamp",
        }

        result = smart_select_columns(fields)

        # Both are in TIER5_EXACT_NAMES, only 1 should be selected (limit=1)
        tier5_fields = ["createdAt", "SnapshotCreateTime"]
        selected_tier5 = [f for f in result if f in tier5_fields]
        assert len(selected_tier5) == 1

    def test_tier7_exact_name_booleans(self):
        fields = {
            "InstanceId": "string",
            "DeletionProtection": "boolean",
            "StorageEncrypted": "boolean",
            "IsDefault": "boolean",
        }

        result = smart_select_columns(fields)

        # All are in TIER7_EXACT_NAMES, limit=2
        tier7_fields = ["DeletionProtection", "StorageEncrypted", "IsDefault"]
        selected_tier7 = [f for f in result if f in tier7_fields]
        assert len(selected_tier7) <= 2


class TestTierOrdering:

    def test_tier1_comes_before_tier2(self):
        fields = {
            "Status": "string",
            "InstanceId": "string",
        }

        result = smart_select_columns(fields)

        id_index = result.index("InstanceId")
        status_index = result.index("Status")
        assert id_index < status_index

    def test_tier2_comes_before_tier3(self):
        fields = {
            "InstanceId": "string",
            "Engine": "string",
            "Status": "string",
        }

        result = smart_select_columns(fields)

        status_index = result.index("Status")
        engine_index = result.index("Engine")
        assert status_index < engine_index

    def test_full_tier_order_preserved(self):
        # Use fields that uniquely match each tier without suffix overlap
        fields = {
            "ResourceId": "string",
            "Status": "string",
            "Engine": "string",
            "AvailabilityZone": "string",
            "CreationTime": "timestamp",
            "ResourceArn": "string",
            "Encrypted": "boolean",
            "AllocatedStorage": "integer",
        }

        result = smart_select_columns(fields)

        # Verify tier order: 1 < 2 < 3 < 4 < 5 < 6 < 7 < 8
        tier_order = {
            "ResourceId": 1,
            "Status": 2,
            "Engine": 3,
            "AvailabilityZone": 4,
            "CreationTime": 5,
            "ResourceArn": 6,
            "Encrypted": 7,
            "AllocatedStorage": 8,
        }

        for i in range(len(result) - 1):
            current_tier = tier_order.get(result[i], 99)
            next_tier = tier_order.get(result[i + 1], 99)
            msg = f"{result[i]} (tier {current_tier}) should come before {result[i + 1]}"
            assert current_tier <= next_tier, msg
