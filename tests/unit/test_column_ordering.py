"""Test column ordering consistency in formatters."""

import pytest

from awsquery.formatters import filter_columns, format_json_output, format_table_output


class TestColumnOrderingConsistency:
    """Test that column ordering is consistent across runs."""

    def test_default_filter_order_preserved_in_table(self):
        """Test that default filter order from config is preserved in table output."""
        resources = [
            {
                "InstanceId": "i-123",
                "Tags": {"Name": "web-server"},
                "InstanceType": "t2.micro",
                "State": {"Name": "running"},
                "PublicIpAddress": "1.2.3.4",
                "PrivateIpAddress": "10.0.0.1",
                "ExtraField": "value1",
            },
            {
                "InstanceId": "i-456",
                "Tags": {"Name": "db-server"},
                "InstanceType": "t2.small",
                "State": {"Name": "stopped"},
                "PublicIpAddress": None,
                "PrivateIpAddress": "10.0.0.2",
                "ExtraField": "value2",
            },
        ]

        # Default EC2 column order from default_filters.yaml
        column_filters = [
            "Tags.Name",
            "InstanceId",
            "InstanceType",
            "State.Name",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]

        # Run multiple times to check consistency
        outputs = []
        for _ in range(5):
            output = format_table_output(resources, column_filters)
            outputs.append(output)

        # All outputs should be identical
        for output in outputs[1:]:
            assert output == outputs[0]

        # Check that columns appear in the specified order
        lines = outputs[0].split("\n")
        header_line = lines[1]  # Second line contains headers

        # Extract headers from table
        # Split by | and filter out empty strings
        headers = [h.strip() for h in header_line.split("|") if h.strip()]

        # Headers are simplified (e.g., "Tags.Name" becomes "Name", "State.Name" becomes "Name")
        # Since both are "Name", they get merged, so we check the order of unique simplified headers
        expected_order = [
            "Name",
            "InstanceId",
            "InstanceType",
            "PublicIpAddress",
            "PrivateIpAddress",
        ]
        assert headers == expected_order

    def test_user_specified_filter_order_preserved(self):
        """Test that user-specified column filter order is preserved."""
        resources = [
            {"Name": "bucket1", "CreationDate": "2024-01-01", "Region": "us-east-1", "Size": 1000},
            {"Name": "bucket2", "CreationDate": "2024-01-02", "Region": "us-west-2", "Size": 2000},
        ]

        # User specifies columns in a specific order
        column_filters = ["Size", "Name", "Region", "CreationDate"]

        # Run multiple times
        outputs = []
        for _ in range(5):
            output = format_table_output(resources, column_filters)
            outputs.append(output)

        # All outputs should be identical
        for output in outputs[1:]:
            assert output == outputs[0]

        # Verify column order matches user specification
        lines = outputs[0].split("\n")
        header_line = lines[1]

        # Split by | and filter out empty strings
        headers = [h.strip() for h in header_line.split("|") if h.strip()]

        assert headers == ["Size", "Name", "Region", "CreationDate"]

    def test_no_filters_consistent_alphabetical_order(self):
        """Test that without filters, columns are in consistent alphabetical order."""
        resources = [{"Zebra": "z1", "Alpha": "a1", "Charlie": "c1", "Bravo": "b1"}]

        # No column filters
        outputs = []
        for _ in range(5):
            output = format_table_output(resources, None)
            outputs.append(output)

        # All outputs should be identical
        for output in outputs[1:]:
            assert output == outputs[0]

        # Columns should be in alphabetical order
        lines = outputs[0].split("\n")
        header_line = lines[1]

        # Split by | and filter out empty strings
        headers = [h.strip() for h in header_line.split("|") if h.strip()]

        assert headers == ["Alpha", "Bravo", "Charlie", "Zebra"]

    def test_filter_columns_preserves_order(self):
        """Test that filter_columns function preserves the order of filters."""
        data = {
            "field4": "val4",
            "field1": "val1",
            "field3": "val3",
            "field2": "val2",
            "field5": "val5",
        }

        # Filters in specific order
        column_filters = ["field2", "field4", "field1"]

        # Run multiple times
        results = []
        for _ in range(5):
            result = filter_columns(data, column_filters)
            results.append(list(result.keys()))

        # All results should have same order
        for result in results[1:]:
            assert result == results[0]

        # Order should match filter order
        assert results[0] == ["field2", "field4", "field1"]

    def test_json_output_preserves_filter_order(self):
        """Test that JSON output preserves column filter order."""
        resources = [{"Name": "item1", "Status": "active", "Id": "123", "Type": "A"}]

        column_filters = ["Type", "Id", "Name", "Status"]

        import json

        # Run multiple times
        outputs = []
        for _ in range(5):
            output = format_json_output(resources, column_filters)
            parsed = json.loads(output)
            outputs.append(list(parsed["results"][0].keys()))

        # All outputs should have same key order
        for output in outputs[1:]:
            assert output == outputs[0]

        # Order should match filter order
        assert outputs[0] == ["Type", "Id", "Name", "Status"]

    def test_pattern_filters_preserve_order(self):
        """Test that pattern-based filters preserve order."""
        resources = [
            {
                "InstanceId": "i-123",
                "InstanceType": "t2.micro",
                "SecurityGroupIds": ["sg-1", "sg-2"],
                "State": {"Name": "running"},
                "Tags": {"Name": "server", "Env": "prod"},
            }
        ]

        # Filters with patterns
        column_filters = ["^Instance", "State", "Tags"]

        outputs = []
        for _ in range(5):
            output = format_table_output(resources, column_filters)
            outputs.append(output)

        # All outputs should be identical
        for output in outputs[1:]:
            assert output == outputs[0]

        # Extract headers and verify they maintain consistent order
        lines = outputs[0].split("\n")
        header_line = lines[1]

        # Split by | and filter out empty strings
        headers = [h.strip() for h in header_line.split("|") if h.strip()]

        # Headers are simplified, but order should be preserved
        # "InstanceId" and "InstanceType" match "^Instance" pattern
        # "State.Name" gets simplified to "Name"
        # "Tags.Name" and "Tags.Env" get simplified to "Name" and "Env"
        # Since "Name" appears in both State and Tags, they get merged
        assert "Instance" in headers[0]  # Either InstanceId or InstanceType
        assert "Instance" in headers[1]  # The other Instance field
        # The remaining headers would be simplified versions of State and Tags fields
        assert len(headers) >= 4  # Should have at least 4 columns
