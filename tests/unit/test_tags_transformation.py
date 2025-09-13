"""Unit tests for AWS Tags transformation functionality."""

from unittest.mock import patch

import pytest

from src.awsquery.formatters import detect_aws_tags, flatten_response, transform_tags_structure


@pytest.mark.unit
class TestDetectAwsTags:
    """Test AWS Tags structure detection."""

    def test_detect_valid_aws_tags(self):
        """Test detection of valid AWS Tags structure."""
        obj = {
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ]
        }

        assert detect_aws_tags(obj) is True

    def test_detect_empty_tags_list(self):
        """Test detection with empty Tags list."""
        obj = {"Tags": []}

        assert detect_aws_tags(obj) is False

    def test_detect_non_list_tags(self):
        """Test detection with Tags that's not a list."""
        obj = {"Tags": "not-a-list"}

        assert detect_aws_tags(obj) is False

    def test_detect_invalid_tag_structure(self):
        """Test detection with invalid tag structure."""
        obj = {
            "Tags": [
                {"Name": "web-server"},  # Missing Key/Value format
                {"Environment": "production"},
            ]
        }

        assert detect_aws_tags(obj) is False

    def test_detect_partial_valid_tags(self):
        """Test detection with first tag having Key/Value structure."""
        obj = {
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"InvalidFormat": "data"},  # Second tag is invalid but first is valid
            ]
        }

        assert detect_aws_tags(obj) is True

    def test_detect_no_tags_field(self):
        """Test detection when object has no Tags field."""
        obj = {"InstanceId": "i-123", "State": "running"}

        assert detect_aws_tags(obj) is False

    def test_detect_tags_with_missing_value(self):
        """Test detection with tags missing Value field."""
        obj = {"Tags": [{"Key": "Name"}]}  # Missing Value

        assert detect_aws_tags(obj) is False

    def test_detect_tags_with_missing_key(self):
        """Test detection with tags missing Key field."""
        obj = {"Tags": [{"Value": "web-server"}]}  # Missing Key

        assert detect_aws_tags(obj) is False

    def test_detect_nested_object_without_tags(self):
        """Test detection on nested object without Tags."""
        obj = {"Instance": {"InstanceId": "i-123", "State": "running"}}

        assert detect_aws_tags(obj) is False


@pytest.mark.unit
class TestTransformTagsStructure:
    """Test AWS Tags structure transformation."""

    def test_transform_simple_tags(self):
        """Test transformation of simple tags structure."""
        data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }

        result = transform_tags_structure(data)

        assert result["InstanceId"] == "i-123"
        assert result["Tags"] == {"Name": "web-server", "Environment": "production"}
        assert result["Tags_Original"] == [
            {"Key": "Name", "Value": "web-server"},
            {"Key": "Environment", "Value": "production"},
        ]

    def test_transform_empty_tags_list(self):
        """Test transformation with empty tags list."""
        data = {"InstanceId": "i-123", "Tags": []}

        result = transform_tags_structure(data)

        assert result["InstanceId"] == "i-123"
        # Empty tags list should remain as empty list (not transformed to dict)
        assert result["Tags"] == []
        # No Tags_Original should be created for empty lists
        assert "Tags_Original" not in result

    def test_transform_non_tags_structure(self):
        """Test transformation preserves non-tags structures."""
        data = {"InstanceId": "i-123", "Tags": ["not", "key-value", "pairs"]}

        result = transform_tags_structure(data)

        assert result["InstanceId"] == "i-123"
        # Should not transform non-AWS-Tags structures
        assert result["Tags"] == ["not", "key-value", "pairs"]
        assert "Tags_Original" not in result

    def test_transform_nested_structures(self):
        """Test transformation works recursively on nested structures."""
        data = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "Tags": [
                                {"Key": "Name", "Value": "web-server-1"},
                                {"Key": "Project", "Value": "webapp"},
                            ],
                        },
                        {
                            "InstanceId": "i-456",
                            "Tags": [
                                {"Key": "Name", "Value": "web-server-2"},
                                {"Key": "Environment", "Value": "staging"},
                            ],
                        },
                    ]
                }
            ]
        }

        result = transform_tags_structure(data)

        # Check first instance tags
        first_instance = result["Reservations"][0]["Instances"][0]
        assert first_instance["Tags"] == {"Name": "web-server-1", "Project": "webapp"}
        assert "Tags_Original" in first_instance

        # Check second instance tags
        second_instance = result["Reservations"][0]["Instances"][1]
        assert second_instance["Tags"] == {"Name": "web-server-2", "Environment": "staging"}
        assert "Tags_Original" in second_instance

    def test_transform_list_of_objects(self):
        """Test transformation works on lists of objects."""
        data = [
            {
                "StackName": "stack1",
                "Tags": [
                    {"Key": "Owner", "Value": "team-alpha"},
                    {"Key": "CostCenter", "Value": "123"},
                ],
            },
            {
                "StackName": "stack2",
                "Tags": [
                    {"Key": "Owner", "Value": "team-beta"},
                    {"Key": "Environment", "Value": "prod"},
                ],
            },
        ]

        result = transform_tags_structure(data)

        assert len(result) == 2
        assert result[0]["Tags"] == {"Owner": "team-alpha", "CostCenter": "123"}
        assert result[1]["Tags"] == {"Owner": "team-beta", "Environment": "prod"}

    def test_transform_primitive_values(self):
        """Test transformation returns primitive values unchanged."""
        assert transform_tags_structure("string") == "string"
        assert transform_tags_structure(123) == 123
        assert transform_tags_structure(None) is None
        assert transform_tags_structure(True) is True

    def test_transform_mixed_tag_structure(self):
        """Test transformation with mixed valid/invalid tag entries."""
        data = {
            "InstanceId": "i-123",
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"InvalidEntry": "should-be-ignored"},
                {"Key": "Environment", "Value": "production"},
                {"Key": "Project"},  # Missing Value
            ],
        }

        result = transform_tags_structure(data)

        # Should only transform valid Key/Value pairs
        assert result["Tags"] == {"Name": "web-server", "Environment": "production"}
        assert "Tags_Original" in result

    def test_transform_special_characters_in_tags(self):
        """Test transformation handles special characters in tag values."""
        data = {
            "Tags": [
                {"Key": "Name", "Value": "web-server-01"},
                {"Key": "Description", "Value": "Web server for production (zone A)"},
                {"Key": "Email", "Value": "admin@company.com"},
                {"Key": "Path", "Value": "/app/data/logs"},
            ]
        }

        result = transform_tags_structure(data)

        assert result["Tags"]["Name"] == "web-server-01"
        assert result["Tags"]["Description"] == "Web server for production (zone A)"
        assert result["Tags"]["Email"] == "admin@company.com"
        assert result["Tags"]["Path"] == "/app/data/logs"

    def test_transform_duplicate_tag_keys(self):
        """Test transformation with duplicate tag keys (last one wins)."""
        data = {
            "Tags": [
                {"Key": "Environment", "Value": "staging"},
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},  # Duplicate key
            ]
        }

        result = transform_tags_structure(data)

        # Last value should win for duplicate keys
        assert result["Tags"]["Environment"] == "production"
        assert result["Tags"]["Name"] == "web-server"

    @patch("src.awsquery.formatters.debug_print")
    def test_transform_debug_output(self, mock_debug):
        """Test that transformation produces debug output."""
        from src.awsquery import utils

        original_debug = utils.debug_enabled
        utils.debug_enabled = True

        try:
            data = {
                "Tags": [{"Key": "Name", "Value": "test"}, {"Key": "Environment", "Value": "prod"}]
            }

            transform_tags_structure(data)

            # Verify debug output was called
            mock_debug.assert_called_with("Transformed 2 AWS Tags to map format")

        finally:
            utils.debug_enabled = original_debug


@pytest.mark.unit
class TestTagsIntegrationWithFormatters:
    """Test tags transformation integration with response formatting."""

    @patch("src.awsquery.formatters.transform_tags_structure")
    def test_flatten_response_calls_transform_tags(self, mock_transform):
        """Test that flatten_response calls transform_tags_structure."""
        from src.awsquery.formatters import flatten_response

        mock_response = [{"Instances": [{"InstanceId": "i-123"}]}]
        mock_transform.return_value = mock_response

        flatten_response(mock_response)

        mock_transform.assert_called_once_with(mock_response)

    def test_tags_transformation_in_flatten_response(self):
        """Test end-to-end tags transformation through flatten_response."""
        response = [
            {
                "Instances": [
                    {
                        "InstanceId": "i-123",
                        "State": {"Name": "running"},
                        "Tags": [
                            {"Key": "Name", "Value": "web-server"},
                            {"Key": "Environment", "Value": "production"},
                        ],
                    }
                ]
            }
        ]

        result = flatten_response(response)

        # Verify tags were transformed
        assert len(result) == 1
        instance = result[0]
        assert instance["Tags"] == {"Name": "web-server", "Environment": "production"}
        assert "Tags_Original" in instance

    def test_tags_column_selection_after_transformation(self):
        """Test that tag-based column selection works after transformation."""
        from src.awsquery.formatters import format_table_output

        resources = [
            {
                "InstanceId": "i-123",
                "State": "running",
                "Tags": {"Name": "web-server-1", "Environment": "production"},
            },
            {
                "InstanceId": "i-456",
                "State": "stopped",
                "Tags": {"Name": "web-server-2", "Environment": "staging"},
            },
        ]

        # Test column selection with transformed tags
        column_filters = ["InstanceId", "Tags.Name", "Tags.Environment"]
        output = format_table_output(resources, column_filters)

        # Verify output contains tag values
        assert "web-server-1" in output
        assert "web-server-2" in output
        assert "production" in output
        assert "staging" in output

    def test_nested_tags_flattening(self):
        """Test flattening of nested tag structures."""
        response = [
            {
                "Stacks": [
                    {
                        "StackName": "my-stack",
                        "StackStatus": "CREATE_COMPLETE",
                        "Tags": [
                            {"Key": "Owner", "Value": "infrastructure-team"},
                            {"Key": "Environment", "Value": "production"},
                            {"Key": "CostCenter", "Value": "1234"},
                        ],
                    }
                ]
            }
        ]

        result = flatten_response(response)

        assert len(result) == 1
        stack = result[0]
        assert stack["Tags"]["Owner"] == "infrastructure-team"
        assert stack["Tags"]["Environment"] == "production"
        assert stack["Tags"]["CostCenter"] == "1234"


@pytest.mark.unit
class TestTagsPerformance:
    """Test performance characteristics of tags transformation."""

    def test_large_tag_set_transformation(self):
        """Test transformation performance with large tag sets."""
        # Create a large tag set
        large_tags = [{"Key": f"Tag{i:04d}", "Value": f"Value{i:04d}"} for i in range(1000)]

        data = {"ResourceId": "resource-123", "Tags": large_tags}

        # Should complete without issues
        result = transform_tags_structure(data)

        assert len(result["Tags"]) == 1000
        assert result["Tags"]["Tag0001"] == "Value0001"
        assert result["Tags"]["Tag0999"] == "Value0999"

    def test_deep_nesting_transformation(self):
        """Test transformation with deeply nested structures."""
        # Create deeply nested structure with tags at various levels
        data = {
            "Level1": {
                "Level2": {
                    "Level3": {
                        "Level4": {
                            "Resources": [
                                {
                                    "ResourceId": "resource-123",
                                    "Tags": [
                                        {"Key": "Name", "Value": "deep-resource"},
                                        {"Key": "Level", "Value": "4"},
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }

        result = transform_tags_structure(data)

        # Verify deep transformation worked
        deep_resource = result["Level1"]["Level2"]["Level3"]["Level4"]["Resources"][0]
        assert deep_resource["Tags"]["Name"] == "deep-resource"
        assert deep_resource["Tags"]["Level"] == "4"

    def test_wide_structure_transformation(self):
        """Test transformation with wide structures (many siblings)."""
        # Create structure with many instances, each with tags
        instances = []
        for i in range(100):
            instances.append(
                {
                    "InstanceId": f"i-{i:03d}",
                    "Tags": [
                        {"Key": "Name", "Value": f"instance-{i:03d}"},
                        {"Key": "Batch", "Value": "performance-test"},
                    ],
                }
            )

        data = {"Instances": instances}
        result = transform_tags_structure(data)

        # Verify all instances were transformed
        assert len(result["Instances"]) == 100
        for i, instance in enumerate(result["Instances"]):
            assert instance["Tags"]["Name"] == f"instance-{i:03d}"
            assert instance["Tags"]["Batch"] == "performance-test"


@pytest.mark.unit
class TestTagsErrorHandling:
    """Test error handling in tags transformation."""

    def test_malformed_tag_entries(self):
        """Test handling of malformed tag entries."""
        data = {
            "Tags": [
                {"Key": "ValidTag", "Value": "ValidValue"},
                None,  # Null entry
                "string-entry",  # String instead of dict
                {"Key": "OnlyKey"},  # Missing Value
                {"Value": "OnlyValue"},  # Missing Key
                {},  # Empty dict
                {"Key": "", "Value": "EmptyKey"},  # Empty key
                {"Key": "EmptyValue", "Value": ""},  # Empty value
            ]
        }

        # Should not raise exception
        result = transform_tags_structure(data)

        # Should only include valid entries
        expected_tags = {"ValidTag": "ValidValue", "EmptyValue": ""}  # Empty values are allowed
        # Empty keys are not allowed, so EmptyKey tag should be excluded
        assert result["Tags"] == expected_tags

    def test_non_string_tag_values(self):
        """Test handling of non-string tag values."""
        data = {
            "Tags": [
                {"Key": "StringValue", "Value": "string"},
                {"Key": "IntValue", "Value": 123},
                {"Key": "BoolValue", "Value": True},
                {"Key": "NoneValue", "Value": None},
                {"Key": "ListValue", "Value": ["a", "b"]},
                {"Key": "DictValue", "Value": {"nested": "dict"}},
            ]
        }

        result = transform_tags_structure(data)

        # All values should be preserved as-is
        assert result["Tags"]["StringValue"] == "string"
        assert result["Tags"]["IntValue"] == 123
        assert result["Tags"]["BoolValue"] is True
        assert result["Tags"]["NoneValue"] is None
        assert result["Tags"]["ListValue"] == ["a", "b"]
        assert result["Tags"]["DictValue"] == {"nested": "dict"}

    def test_circular_reference_protection(self):
        """Test that transformation doesn't get stuck in circular references."""
        # Create a structure with circular reference
        data = {"ResourceId": "test"}
        data["Self"] = data  # Circular reference

        # Should handle gracefully without infinite recursion
        # Note: This test is mainly to ensure we don't hang
        try:
            result = transform_tags_structure(data)
            # If we get here, the function handled it (may or may not transform correctly)
            assert "ResourceId" in result
        except RecursionError:
            pytest.fail("Transform function should handle circular references")

    def test_extremely_deep_nesting(self):
        """Test transformation with extremely deep nesting."""
        # Create very deep nesting
        data = {"level": 0}
        current = data
        for i in range(1, 50):  # 50 levels deep
            current["next"] = {"level": i}
            current = current["next"]

        # Add tags at the deepest level
        current["Tags"] = [{"Key": "DeepTag", "Value": "DeepValue"}]

        # Should handle deep nesting without stack overflow
        result = transform_tags_structure(data)

        # Navigate to deepest level and verify transformation
        current_result = result
        for i in range(49):
            current_result = current_result["next"]

        assert current_result["Tags"]["DeepTag"] == "DeepValue"
