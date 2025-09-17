"""Unit tests for filter matching with ^ and $ operators."""

import pytest

from awsquery.filters import (
    filter_resources,
    matches_pattern,
    parse_filter_pattern,
)
from awsquery.formatters import filter_columns


class TestParseFilterPattern:

    def test_prefix_match_pattern(self):
        pattern, mode = parse_filter_pattern("^Name")
        assert pattern == "Name"
        assert mode == "prefix"

    def test_suffix_match_pattern(self):
        pattern, mode = parse_filter_pattern("Name$")
        assert pattern == "Name"
        assert mode == "suffix"

    def test_exact_match_pattern(self):
        pattern, mode = parse_filter_pattern("^Name$")
        assert pattern == "Name"
        assert mode == "exact"

    def test_contains_match_pattern(self):
        pattern, mode = parse_filter_pattern("Name")
        assert pattern == "Name"
        assert mode == "contains"

    def test_special_char_in_middle(self):
        pattern, mode = parse_filter_pattern("Tags.^Name")
        assert pattern == "Tags.^Name"
        assert mode == "contains"

    def test_multiple_prefix_operators(self):
        pattern, mode = parse_filter_pattern("^^Name")
        assert pattern == "^Name"
        assert mode == "prefix"

    def test_multiple_suffix_operators(self):
        pattern, mode = parse_filter_pattern("Name$$")
        assert pattern == "Name$"
        assert mode == "suffix"

    def test_multiple_operators_both(self):
        pattern, mode = parse_filter_pattern("^^Name$$")
        assert pattern == "^Name$"
        assert mode == "exact"

    def test_empty_string(self):
        pattern, mode = parse_filter_pattern("")
        assert pattern == ""
        assert mode == "contains"

    def test_only_prefix_operator(self):
        pattern, mode = parse_filter_pattern("^")
        assert pattern == ""
        assert mode == "prefix"

    def test_modifier_circumflex_as_prefix(self):
        # Test U+02C6 (modifier letter circumflex) works same as ASCII ^
        pattern, mode = parse_filter_pattern("ˆName")
        assert pattern == "Name"
        assert mode == "prefix"

    def test_modifier_circumflex_with_suffix(self):
        # Test modifier circumflex with $ suffix
        pattern, mode = parse_filter_pattern("ˆName$")
        assert pattern == "Name"
        assert mode == "exact"


class TestMatchesPattern:

    def test_exact_match(self):
        assert matches_pattern("Name", "Name", "exact")
        assert matches_pattern("name", "Name", "exact")
        assert matches_pattern("NAME", "name", "exact")
        assert not matches_pattern("Names", "Name", "exact")
        assert not matches_pattern("Name1", "Name", "exact")

    def test_prefix_match(self):
        assert matches_pattern("NameField", "Name", "prefix")
        assert matches_pattern("Name123", "Name", "prefix")
        assert matches_pattern("Name", "Name", "prefix")
        assert not matches_pattern("FirstName", "Name", "prefix")
        assert not matches_pattern("MyName", "Name", "prefix")

    def test_suffix_match(self):
        assert matches_pattern("FirstName", "Name", "suffix")
        assert matches_pattern("UserName", "Name", "suffix")
        assert matches_pattern("Name", "Name", "suffix")
        assert not matches_pattern("NameField", "Name", "suffix")
        assert not matches_pattern("Names", "Name", "suffix")

    def test_contains_match(self):
        assert matches_pattern("FirstName", "Name", "contains")
        assert matches_pattern("NameField", "Name", "contains")
        assert matches_pattern("MyNameIs", "Name", "contains")
        assert matches_pattern("Name", "Name", "contains")
        assert not matches_pattern("Nothing", "Name", "contains")

    def test_case_insensitive(self):
        assert matches_pattern("instanceid", "InstanceId", "exact")
        assert matches_pattern("INSTANCEID", "instanceid", "exact")
        assert matches_pattern("InstanceType", "instance", "prefix")
        assert matches_pattern("GroupName", "name", "suffix")
        assert matches_pattern("MyNameField", "name", "contains")


class TestResourceFiltering:

    def test_value_filter_prefix_match(self):
        resources = [
            {"InstanceId": "i-12345", "State": "running"},
            {"InstanceId": "i-67890", "State": "stopped"},
            {"InstanceId": "prod-123", "State": "running"},
        ]

        filtered = filter_resources(resources, ["^i-123"])
        assert len(filtered) == 1
        assert filtered[0]["InstanceId"] == "i-12345"

    def test_value_filter_suffix_match(self):
        resources = [
            {"Domain": "example.com", "Status": "active"},
            {"Domain": "test.org", "Status": "active"},
            {"Domain": "demo.com", "Status": "inactive"},
        ]

        filtered = filter_resources(resources, [".com$"])
        assert len(filtered) == 2
        assert all(r["Domain"].endswith(".com") for r in filtered)

    def test_value_filter_exact_match(self):
        resources = [
            {"State": {"Name": "running"}, "Type": "t2.micro"},
            {"State": {"Name": "stopped"}, "Type": "t2.micro"},
            {"State": {"Name": "running-setup"}, "Type": "t2.small"},
        ]

        filtered = filter_resources(resources, ["^running$"])
        assert len(filtered) == 1
        assert filtered[0]["State"]["Name"] == "running"

    def test_multiple_filters_with_operators(self):
        resources = [
            {"Name": "prod-web-01", "Type": "t2.micro", "State": "running"},
            {"Name": "prod-db-01", "Type": "t3.large", "State": "running"},
            {"Name": "dev-web-01", "Type": "t2.micro", "State": "stopped"},
            {"Name": "test-web-01", "Type": "t2.nano", "State": "running"},
        ]

        filtered = filter_resources(resources, ["^prod", "running"])
        assert len(filtered) == 2
        assert all(r["Name"].startswith("prod") for r in filtered)
        assert all("running" in str(r).lower() for r in filtered)


class TestColumnFiltering:

    def test_column_filter_prefix_match(self):
        flattened_data = {
            "InstanceId": "i-123456",
            "InstanceType": "t2.micro",
            "State.Name": "running",
            "PublicIpAddress": "1.2.3.4",
        }

        columns = filter_columns(flattened_data, ["^Instance"])
        assert "InstanceId" in columns
        assert "InstanceType" in columns
        assert "State.Name" not in columns
        assert "PublicIpAddress" not in columns

    def test_column_filter_suffix_match(self):
        flattened_data = {
            "GroupName": "my-group",
            "UserName": "admin",
            "State.Name": "active",
            "InstanceId": "i-123",
        }

        columns = filter_columns(flattened_data, ["Name$"])
        assert "GroupName" in columns
        assert "UserName" in columns
        assert "State.Name" in columns
        assert "InstanceId" not in columns

    def test_column_filter_exact_match(self):
        flattened_data = {
            "State": "running",
            "State.Name": "active",
            "State.Code": "16",
            "States": "multiple",
        }

        columns = filter_columns(flattened_data, ["^State$"])
        assert "State" in columns
        assert "State.Name" not in columns
        assert "State.Code" not in columns
        assert "States" not in columns

    def test_column_filter_mixed_operators(self):
        flattened_data = {
            "InstanceId": "i-123",
            "InstanceType": "t2.micro",
            "GroupName": "web",
            "SecurityGroupIds": ["sg-123"],
            "State.Name": "running",
            "PublicIpAddress": "1.2.3.4",
        }

        columns = filter_columns(flattened_data, ["^Instance", "Name$", "^PublicIpAddress$"])
        assert "InstanceId" in columns
        assert "InstanceType" in columns
        assert "GroupName" in columns
        assert "State.Name" in columns
        assert "PublicIpAddress" in columns
        assert "SecurityGroupIds" not in columns

    def test_column_filter_with_modifier_circumflex(self):
        # Test that modifier circumflex (ˆ) works for column filtering
        flattened_data = {
            "StackName": "my-stack",
            "StackStatus": "CREATE_COMPLETE",
            "StackStatusReason": "Success",
            "CreationTime": "2024-01-01",
        }

        # Use modifier circumflex instead of ASCII ^
        columns = filter_columns(flattened_data, ["ˆStackStatus"])
        assert "StackStatus" in columns
        assert "StackStatusReason" in columns
        assert "StackName" not in columns
        assert "CreationTime" not in columns


class TestEdgeCases:

    def test_empty_filter_string(self):
        resources = [
            {"Name": "test1"},
            {"Name": "test2"},
        ]

        filtered = filter_resources(resources, [""])
        assert len(filtered) == 2

    def test_only_exclamation_marks(self):
        resources = [
            {"Name": "test1"},
            {"Name": "test2"},
        ]

        # "^" alone means prefix match with empty string, which matches everything
        filtered = filter_resources(resources, ["^"])
        assert len(filtered) == 2  # Empty pattern matches everything

    def test_special_characters_in_filter(self):
        resources = [
            {"Path": "/usr"},
            {"Path": "/usr/local/bin"},
            {"Path": "/home/user"},
        ]

        # Exact match for "/usr"
        filtered = filter_resources(resources, ["^/usr$"])
        assert len(filtered) == 1
        assert filtered[0]["Path"] == "/usr"

        # Prefix match for paths starting with "/usr"
        filtered = filter_resources(resources, ["^/usr"])
        assert len(filtered) == 2
        assert all(r["Path"].startswith("/usr") for r in filtered)
