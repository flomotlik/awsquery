"""Tests for pattern matching and filtering in filters module."""

import pytest

from awsquery.filters import (
    extract_parameter_values,
    filter_resources,
    matches_pattern,
    parse_filter_pattern,
)


class TestPatternMatching:
    """Test pattern matching functionality."""

    def test_matches_pattern_none_handling(self):
        """Test None value handling in pattern matching."""
        # None text always returns False (unless pattern is also None/empty)
        assert matches_pattern(None, "pattern", "contains") is False
        assert matches_pattern(None, "pattern", "exact") is False
        assert matches_pattern(None, "pattern", "prefix") is False

        # None pattern
        assert matches_pattern("text", None, "contains") is False

        # Both None - special case
        assert matches_pattern(None, None, "contains") is True

        # Empty pattern with None text
        assert matches_pattern(None, "", "contains") is True

    def test_matches_pattern_case_insensitive(self):
        """Test case-insensitive matching."""
        # All modes should be case-insensitive
        assert matches_pattern("TEST", "test", "exact") is True
        assert matches_pattern("test", "TEST", "exact") is True

        assert matches_pattern("TESTING", "test", "contains") is True
        assert matches_pattern("testing", "TEST", "contains") is True

        assert matches_pattern("PREFIX_test", "prefix", "prefix") is True
        assert matches_pattern("prefix_test", "PREFIX", "prefix") is True

        assert matches_pattern("test_SUFFIX", "suffix", "suffix") is True
        assert matches_pattern("test_suffix", "SUFFIX", "suffix") is True

    def test_matches_pattern_exact_mode(self):
        """Test exact matching mode."""
        assert matches_pattern("test", "test", "exact") is True
        assert matches_pattern("test", "tes", "exact") is False
        assert matches_pattern("test", "tests", "exact") is False
        assert matches_pattern("test", "atest", "exact") is False

    def test_matches_pattern_contains_mode(self):
        """Test contains matching mode."""
        assert matches_pattern("testing", "test", "contains") is True
        assert matches_pattern("testing", "ing", "contains") is True
        assert matches_pattern("testing", "sti", "contains") is True
        assert matches_pattern("testing", "xyz", "contains") is False

    def test_matches_pattern_prefix_mode(self):
        """Test prefix matching mode."""
        assert matches_pattern("testing", "test", "prefix") is True
        assert matches_pattern("testing", "tes", "prefix") is True
        assert matches_pattern("testing", "ing", "prefix") is False
        assert matches_pattern("testing", "est", "prefix") is False

    def test_matches_pattern_suffix_mode(self):
        """Test suffix matching mode."""
        assert matches_pattern("testing", "ing", "suffix") is True
        assert matches_pattern("testing", "ting", "suffix") is True
        assert matches_pattern("testing", "test", "suffix") is False
        assert matches_pattern("testing", "est", "suffix") is False

    def test_matches_pattern_invalid_mode(self):
        """Test invalid mode defaults to contains."""
        # Invalid mode should default to contains
        assert matches_pattern("testing", "test", "invalid") is True
        assert matches_pattern("testing", "xyz", "invalid") is False


class TestFilterParsing:
    """Test filter pattern parsing."""

    def test_parse_filter_pattern_operators(self):
        """Test parsing of ^ and $ operators."""
        # Prefix operator
        pattern, mode = parse_filter_pattern("^Name")
        assert pattern == "Name"
        assert mode == "prefix"

        # Suffix operator
        pattern, mode = parse_filter_pattern("Status$")
        assert pattern == "Status"
        assert mode == "suffix"

        # Exact match (both operators)
        pattern, mode = parse_filter_pattern("^Id$")
        assert pattern == "Id"
        assert mode == "exact"

        # No operators (contains)
        pattern, mode = parse_filter_pattern("Instance")
        assert pattern == "Instance"
        assert mode == "contains"

    def test_parse_filter_pattern_unicode_circumflex(self):
        """Test Unicode circumflex (ˆ) is treated as ^."""
        # U+02C6 - Modifier letter circumflex
        pattern, mode = parse_filter_pattern("ˆName")
        assert pattern == "Name"
        assert mode == "prefix"

        pattern, mode = parse_filter_pattern("ˆName$")
        assert pattern == "Name"
        assert mode == "exact"

    def test_parse_filter_pattern_exact_string_literals(self):
        """Test exact string literals in pattern parsing."""
        # Test exact circumflex characters - both ASCII and Unicode
        pattern1, mode1 = parse_filter_pattern("^test")  # ASCII circumflex
        pattern2, mode2 = parse_filter_pattern("ˆtest")  # Unicode circumflex

        assert pattern1 == "test"
        assert mode1 == "prefix"
        assert pattern2 == "test"
        assert mode2 == "prefix"

        # Verify specific characters are detected correctly
        assert "^test".startswith("^")
        assert "ˆtest".startswith("ˆ")
        assert not "test^".startswith("^")
        assert not "test^".startswith("ˆ")

    def test_parse_filter_pattern_suffix_dollar_literal(self):
        """Test exact dollar sign detection."""
        # Test exact dollar character
        pattern, mode = parse_filter_pattern("test$")
        assert pattern == "test"
        assert mode == "suffix"

        # Verify dollar character specifically
        assert "test$".endswith("$")
        assert not "$test".endswith("$")
        assert not "te$st".endswith("$")

    def test_parse_filter_pattern_empty(self):
        """Test parsing empty patterns."""
        pattern, mode = parse_filter_pattern("")
        assert pattern == ""
        assert mode == "contains"

        # Only operators
        pattern, mode = parse_filter_pattern("^")
        assert pattern == ""
        assert mode == "prefix"

        pattern, mode = parse_filter_pattern("$")
        assert pattern == ""
        assert mode == "suffix"

        pattern, mode = parse_filter_pattern("^$")
        assert pattern == ""
        assert mode == "exact"


class TestParameterValueExtraction:
    """Test parameter value extraction from resources."""

    def test_extract_parameter_values_none_handling(self):
        """Test extraction from None resources."""
        assert extract_parameter_values(None, "Id") == []
        assert extract_parameter_values(None, "") == []
        assert extract_parameter_values(None, None) == []

    def test_extract_parameter_values_string_resources(self):
        """Test extraction from simple string resources."""
        resources = ["instance-1", "instance-2", "instance-3"]
        result = extract_parameter_values(resources, "InstanceId")
        assert result == resources

    def test_extract_parameter_values_dict_resources(self):
        """Test extraction from dictionary resources."""
        resources = [
            {"InstanceId": "i-123", "Name": "server1"},
            {"InstanceId": "i-456", "Name": "server2"},
        ]

        # Direct field match
        values = extract_parameter_values(resources, "InstanceId")
        assert values == ["i-123", "i-456"]

        # Direct field match for Name
        values = extract_parameter_values(resources, "Name")
        assert values == ["server1", "server2"]

    def test_extract_parameter_values_case_conversion(self):
        """Test camelCase to PascalCase field matching."""
        resources = [{"ClusterName": "prod-cluster"}, {"ClusterName": "dev-cluster"}]

        # Looking for clusterName should find ClusterName
        values = extract_parameter_values(resources, "clusterName")
        assert "prod-cluster" in values
        assert "dev-cluster" in values

    def test_extract_parameter_values_none_and_empty(self):
        """Test handling of None and empty values."""
        resources = [{"Name": "valid"}, {"Name": None}, {"Name": ""}, {"Name": "another-valid"}]

        values = extract_parameter_values(resources, "Name")
        # Should skip None and empty values
        assert "valid" in values
        assert "another-valid" in values
        assert None not in values
        assert "" not in values

    def test_extract_parameter_values_missing_field(self):
        """Test extraction when field is missing."""
        resources = [
            {"Name": "server1"},
            {"Status": "active"},  # No Name field
            {"Name": "server2"},
        ]

        values = extract_parameter_values(resources, "Name")
        assert "server1" in values
        assert "server2" in values
        assert len(values) == 2  # Should not include the resource without Name


class TestResourceFiltering:
    """Test resource filtering with patterns."""

    def test_filter_resources_empty_filters(self):
        """Test filtering with empty filter list."""
        resources = [{"Name": "test1"}, {"Name": "test2"}]

        # Empty filters should return all resources
        result = filter_resources(resources, [])
        assert result == resources

    def test_filter_resources_none_values(self):
        """Test filtering resources with None values."""
        resources = [
            {"Name": "server1", "Status": "running"},
            {"Name": None, "Status": "stopped"},
            {"Name": "server2", "Status": None},
        ]

        # Filter by "running"
        result = filter_resources(resources, ["running"])
        assert len(result) == 1
        assert result[0]["Name"] == "server1"

        # Filter by "server"
        result = filter_resources(resources, ["server"])
        assert len(result) == 2

    def test_filter_resources_multiple_filters_and_logic(self):
        """Test multiple filters with AND logic."""
        resources = [
            {"Name": "prod-web-server", "Status": "running"},
            {"Name": "prod-db-server", "Status": "stopped"},
            {"Name": "dev-web-server", "Status": "running"},
        ]

        # Both filters must match (AND logic)
        result = filter_resources(resources, ["prod", "running"])
        assert len(result) == 1
        assert result[0]["Name"] == "prod-web-server"

    def test_filter_resources_nested_values(self):
        """Test filtering on nested dictionary values."""
        resources = [
            {"Name": "server1", "Config": {"Environment": "production"}},
            {"Name": "server2", "Config": {"Environment": "development"}},
        ]

        # Should find in nested structures
        result = filter_resources(resources, ["production"])
        assert len(result) == 1
        assert result[0]["Name"] == "server1"
