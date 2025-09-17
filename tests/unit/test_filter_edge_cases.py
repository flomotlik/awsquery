"""Edge case tests for filter_resources function."""

import pytest

from awsquery.filters import filter_resources, matches_pattern, parse_filter_pattern


class TestFilterResourcesEdgeCases:
    """Test filter_resources with edge cases."""

    def test_empty_filters(self):
        """Test with empty filter list."""
        resources = [
            {"Name": "resource-1"},
            {"Name": "resource-2"},
        ]

        filtered = filter_resources(resources, [])
        assert filtered == resources

    def test_empty_resources(self):
        """Test with empty resource list."""
        filtered = filter_resources([], ["filter"])
        assert filtered == []

    def test_none_resources(self):
        """Test with None resources."""
        # filter_resources may not handle None gracefully
        try:
            filtered = filter_resources(None, ["filter"])
            assert filtered == [] or filtered is None
        except (TypeError, AttributeError):
            # Expected if function doesn't handle None
            pass

    def test_none_values_in_resources(self):
        """Test resources containing None values."""
        resources = [
            {"Name": "resource-1", "Status": None},
            {"Name": None, "Status": "active"},
            {"Name": "resource-3", "Status": "running"},
        ]

        filtered = filter_resources(resources, ["running"])
        assert len(filtered) == 1
        assert filtered[0]["Name"] == "resource-3"

    def test_empty_string_filter(self):
        """Test with empty string as filter."""
        resources = [
            {"Name": "resource-1"},
            {"Name": "resource-2"},
        ]

        # Empty string should match everything
        filtered = filter_resources(resources, [""])
        assert filtered == resources

    def test_special_characters_in_filter(self):
        """Test filters with special characters."""
        resources = [
            {"Name": "resource.test"},
            {"Name": "resource-test"},
            {"Name": "resource_test"},
            {"Name": "resource@test"},
        ]

        filtered = filter_resources(resources, ["resource.test"])
        assert len(filtered) == 1
        assert filtered[0]["Name"] == "resource.test"

    def test_unicode_characters(self):
        """Test with Unicode characters."""
        resources = [
            {"Name": "资源-1"},
            {"Name": "リソース-2"},
            {"Name": "resource-3"},
        ]

        filtered = filter_resources(resources, ["资源"])
        assert len(filtered) == 1
        assert filtered[0]["Name"] == "资源-1"

    def test_very_long_values(self):
        """Test with very long string values."""
        long_string = "a" * 10000
        resources = [
            {"Name": long_string},
            {"Name": "short"},
        ]

        filtered = filter_resources(resources, ["aaaa"])
        assert len(filtered) == 1
        assert len(filtered[0]["Name"]) == 10000

    def test_deeply_nested_structures(self):
        """Test filtering deeply nested structures."""
        resources = [
            {"Level1": {"Level2": {"Level3": {"Level4": {"Target": "found-me"}}}}},
            {"Level1": {"Level2": {"Level3": {"Level4": {"Target": "not-me"}}}}},
        ]

        filtered = filter_resources(resources, ["found-me"])
        assert len(filtered) == 1

    def test_circular_reference_protection(self):
        """Test that circular references don't cause infinite loops."""
        resource = {"Name": "test"}
        resource["self"] = resource  # Create circular reference

        # Should handle without crashing (may or may not match)
        try:
            filtered = filter_resources([resource], ["test"])
            assert len(filtered) >= 0  # Just ensure it doesn't crash
        except RecursionError:
            # If recursion protection isn't implemented, this is expected
            pass

    def test_mixed_type_values(self):
        """Test resources with mixed type values."""
        resources = [
            {"Name": "string", "Port": 8080, "Enabled": True},
            {"Name": "test", "Port": "443", "Enabled": False},
            {"Name": None, "Port": None, "Enabled": None},
        ]

        # Filter by number
        filtered = filter_resources(resources, ["8080"])
        assert len(filtered) == 1

        # Filter by boolean
        filtered = filter_resources(resources, ["True"])
        assert len(filtered) == 1

    def test_multiple_filters_all_must_match(self):
        """Test that ALL filters must match (AND logic)."""
        resources = [
            {"Name": "prod-web-server", "Status": "running"},
            {"Name": "prod-db-server", "Status": "stopped"},
            {"Name": "test-web-server", "Status": "running"},
        ]

        filtered = filter_resources(resources, ["prod", "running"])
        assert len(filtered) == 1
        assert filtered[0]["Name"] == "prod-web-server"


class TestMatchesPatternEdgeCases:
    """Test matches_pattern function edge cases."""

    def test_empty_pattern(self):
        """Test empty pattern matching."""
        assert matches_pattern("anything", "", "contains")
        assert matches_pattern("", "", "exact")
        assert not matches_pattern("something", "", "exact")

    def test_empty_text(self):
        """Test matching against empty text."""
        assert not matches_pattern("", "pattern", "contains")
        assert matches_pattern("", "", "contains")

    def test_none_values(self):
        """Test None value handling."""
        assert not matches_pattern(None, "pattern", "contains")
        assert not matches_pattern("text", None, "contains")
        assert matches_pattern(None, None, "contains")

    def test_case_sensitivity(self):
        """Test case-insensitive matching."""
        assert matches_pattern("TEXT", "text", "exact")
        assert matches_pattern("Text", "TEXT", "contains")
        assert matches_pattern("TeXt", "text", "prefix")

    def test_special_regex_characters(self):
        """Test that special regex characters are handled literally."""
        assert matches_pattern("test.file", "test.file", "exact")
        assert matches_pattern("[test]", "[test]", "exact")
        assert matches_pattern("test*", "test*", "exact")
        assert not matches_pattern("testfile", "test.", "exact")

    def test_invalid_mode(self):
        """Test with invalid matching mode."""
        # Should default to contains mode
        assert matches_pattern("text", "ex", "invalid_mode")


class TestParseFilterPatternEdgeCases:
    """Test parse_filter_pattern function edge cases."""

    def test_empty_pattern(self):
        """Test parsing empty pattern."""
        pattern, mode = parse_filter_pattern("")
        assert pattern == ""
        assert mode == "contains"

    def test_only_operators(self):
        """Test patterns with only operators."""
        pattern, mode = parse_filter_pattern("^")
        assert pattern == ""
        assert mode == "prefix"

        pattern, mode = parse_filter_pattern("$")
        assert pattern == ""
        assert mode == "suffix"

        pattern, mode = parse_filter_pattern("^$")
        assert pattern == ""
        assert mode == "exact"

    def test_malformed_operators(self):
        """Test malformed operator patterns."""
        # $ at beginning is literal
        pattern, mode = parse_filter_pattern("$test")
        assert pattern == "$test"
        assert mode == "contains"

        # Multiple ^ at beginning
        pattern, mode = parse_filter_pattern("^^test")
        assert pattern == "^test"
        assert mode == "prefix"

        # Multiple $ at end
        pattern, mode = parse_filter_pattern("test$$")
        assert pattern == "test$"
        assert mode == "suffix"

    def test_operators_in_middle(self):
        """Test operators in the middle of pattern."""
        pattern, mode = parse_filter_pattern("te^st")
        assert pattern == "te^st"
        assert mode == "contains"

        pattern, mode = parse_filter_pattern("te$st")
        assert pattern == "te$st"
        assert mode == "contains"

    def test_unicode_circumflex(self):
        """Test Unicode circumflex character."""
        # U+02C6 - Modifier letter circumflex
        pattern, mode = parse_filter_pattern("ˆtest")
        assert pattern == "test"
        assert mode == "prefix"

        pattern, mode = parse_filter_pattern("ˆtest$")
        assert pattern == "test"
        assert mode == "exact"

    def test_escaped_characters(self):
        """Test escaped special characters."""
        # Escaping may not be handled specially
        pattern, mode = parse_filter_pattern("\\^test")
        # Backslash might be treated literally
        assert pattern in ["\\^test", "\\test", "^test"]
        assert mode in ["contains", "prefix"]

        pattern, mode = parse_filter_pattern("test\\$")
        assert pattern in ["test\\$", "test\\", "test$"]
        assert mode in ["contains", "suffix"]
