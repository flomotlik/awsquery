import json
from unittest.mock import Mock, patch

import pytest

from awsquery.filter_validator import FilterValidator
from awsquery.formatters import format_json_output, format_table_output
from awsquery.shapes import ShapeCache


class TestShapeAwareDataExtraction:

    def test_extracts_data_using_shape_information(self):
        cache = ShapeCache()

        mock_list_item = Mock()
        mock_list_item.type_name = "structure"
        mock_list_item.members = {
            "InstanceId": Mock(type_name="string"),
            "InstanceType": Mock(type_name="string"),
        }

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_list_item

        mock_metadata_shape = Mock()
        mock_metadata_shape.type_name = "structure"
        mock_metadata_shape.members = {}

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {
            "Instances": mock_list_shape,
            "ResponseMetadata": mock_metadata_shape,
        }

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            data_field, simplified, full = cache.get_response_fields("ec2", "describe-instances")

            assert data_field == "Instances"
            assert any("instanceid" in k.lower() for k in simplified.keys())

    def test_formats_output_with_shape_aware_fields(self):
        response_data = [
            {"InstanceId": "i-123", "InstanceType": "t2.micro", "State": {"Name": "running"}},
            {"InstanceId": "i-456", "InstanceType": "t3.small", "State": {"Name": "stopped"}},
        ]

        output = format_json_output(response_data, ["InstanceId", "InstanceType"])
        parsed = json.loads(output)

        if "results" in parsed:
            items = parsed["results"]
        else:
            items = parsed

        assert len(items) == 2
        assert all("InstanceId" in item for item in items)

    def test_table_output_with_filtered_columns(self):
        response_data = [
            {"InstanceId": "i-123", "InstanceType": "t2.micro"},
            {"InstanceId": "i-456", "InstanceType": "t3.small"},
        ]

        output = format_table_output(response_data, ["InstanceId"])

        assert "i-123" in output
        assert "i-456" in output


class TestWarningMessages:

    @patch("awsquery.filter_validator.debug_print")
    def test_prints_warning_to_stderr_for_invalid_filter(self, mock_debug):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["InvalidField"])

            assert len(results) == 1
            assert results[0][1] is not None

    @patch("awsquery.filter_validator.debug_print")
    def test_prints_suggestion_in_warning(self, mock_debug):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["Instx"])

            assert len(results) == 1
            assert results[0][1] is not None

    @patch("awsquery.filter_validator.debug_print")
    def test_no_warning_for_valid_filter(self, mock_debug):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["InstanceId"])

            assert len(results) == 1
            assert results[0][1] is None


class TestFallbackToHeuristicLogic:

    @patch("awsquery.shapes.Loader")
    def test_falls_back_when_shape_unavailable(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = []
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        data_field, simplified, full = cache.get_response_fields("unknown", "unknown-operation")

        assert data_field is None
        assert simplified == {}
        assert full == {}

    def test_validator_fails_fast_when_no_shape(self):
        validator = FilterValidator()

        with patch.object(
            validator.shape_cache, "get_response_fields", return_value=(None, {}, {})
        ):
            results = validator.validate_columns(
                "unknown", "unknown-operation", ["AnyField", "AnotherField"]
            )

            assert len(results) == 2
            # All filters should have errors when shape unavailable
            assert all(r[1] is not None for r in results)
            assert all("Could not load response shape" in r[1] for r in results)


class TestShapeCachePerformance:

    @patch("awsquery.shapes.Loader")
    def test_shape_cache_reuses_loaded_models(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]
        mock_loader.load_service_model.return_value = {
            "metadata": {"serviceId": "EC2"},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()

        cache.get_service_model("ec2")
        cache.get_service_model("ec2")
        cache.get_service_model("ec2")

        assert mock_loader.load_service_model.call_count == 1

    def test_validator_reuses_shape_cache(self):
        cache = ShapeCache()
        validator1 = FilterValidator(shape_cache=cache)
        validator2 = FilterValidator(shape_cache=cache)

        assert validator1.shape_cache is validator2.shape_cache


class TestRealWorldScenarios:

    @patch("awsquery.shapes.Loader")
    def test_ec2_describe_instances_with_nested_fields(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        cache = ShapeCache()

        mock_nested_shape = Mock()
        mock_nested_shape.type_name = "structure"
        mock_nested_shape.members = {
            "SubnetId": Mock(type_name="string"),
            "VpcId": Mock(type_name="string"),
        }

        mock_network_interfaces_shape = Mock()
        mock_network_interfaces_shape.type_name = "list"
        mock_network_interfaces_shape.member = mock_nested_shape

        mock_list_item = Mock()
        mock_list_item.type_name = "structure"
        mock_list_item.members = {
            "InstanceId": Mock(type_name="string"),
            "NetworkInterfaces": mock_network_interfaces_shape,
        }

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_list_item

        mock_metadata_shape = Mock()
        mock_metadata_shape.type_name = "structure"
        mock_metadata_shape.members = {}

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {
            "Reservations": mock_list_shape,
            "ResponseMetadata": mock_metadata_shape,
        }

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            data_field, simplified, full = cache.get_response_fields("ec2", "describe-instances")

            assert data_field == "Reservations"

    @patch("awsquery.shapes.Loader")
    def test_sns_get_topic_attributes_with_map(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2010-03-31"]

        cache = ShapeCache()

        mock_map_shape = Mock()
        mock_map_shape.type_name = "map"
        mock_map_shape.value = Mock(type_name="string")

        mock_metadata_shape = Mock()
        mock_metadata_shape.type_name = "structure"
        mock_metadata_shape.members = {}

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {
            "Attributes": mock_map_shape,
            "ResponseMetadata": mock_metadata_shape,
        }

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            with patch.object(cache, "identify_data_field", return_value="Attributes"):
                data_field, simplified, full = cache.get_response_fields(
                    "sns", "get-topic-attributes"
                )

                assert data_field == "Attributes"
                assert "*" in simplified
                assert simplified["*"] == "map-wildcard"

    @patch("awsquery.shapes.Loader")
    def test_s3_get_bucket_location_with_primitive(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2006-03-01"]

        cache = ShapeCache()

        mock_metadata_shape = Mock()
        mock_metadata_shape.type_name = "structure"
        mock_metadata_shape.members = {}

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {
            "LocationConstraint": Mock(type_name="string"),
            "ResponseMetadata": mock_metadata_shape,
        }

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            with patch.object(cache, "identify_data_field", return_value="LocationConstraint"):
                data_field, simplified, full = cache.get_response_fields(
                    "s3", "get-bucket-location"
                )

                assert data_field == "LocationConstraint"


class TestDebugMode:

    @patch("awsquery.utils.debug_print")
    @patch("awsquery.shapes.Loader")
    def test_debug_output_for_shape_loading(self, mock_loader_class, mock_debug):
        from awsquery.utils import set_debug_enabled

        set_debug_enabled(True)

        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]
        mock_loader.load_service_model.return_value = {
            "metadata": {"serviceId": "EC2"},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        cache.get_service_model("ec2")

        set_debug_enabled(False)

    @patch("awsquery.utils.debug_print")
    def test_debug_output_for_filter_validation(self, mock_debug):
        from awsquery.utils import set_debug_enabled

        set_debug_enabled(True)

        validator = FilterValidator()

        mock_fields = {"InstanceId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            validator.validate_columns("ec2", "describe-instances", ["InstanceId"])

        set_debug_enabled(False)


class TestFilterValidatorIntegration:

    def test_validates_and_suggests_similar_fields(self):
        validator = FilterValidator()

        mock_fields = {
            "instanceid": "string",
            "instancetype": "string",
            "publicipaddress": "string",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_fields, {}),
        ):
            results = validator.validate_columns(
                "ec2", "describe-instances", ["^InstanceId$", "Type", "Instx"]
            )

            assert len(results) == 3
            assert results[0][1] is None
            assert results[1][1] is None
            assert results[2][1] is not None

    def test_map_type_accepts_any_column_filter(self):
        validator = FilterValidator()

        mock_fields = {"*": "map-wildcard"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Attributes", mock_fields, {}),
        ):
            results = validator.validate_columns(
                "sns", "get-topic-attributes", ["Policy", "DisplayName", "SomeNewAttribute"]
            )

            assert len(results) == 3
            assert all(r[1] is None for r in results)

    def test_handles_nested_field_validation(self):
        validator = FilterValidator()

        mock_fields = {"instanceid": "string", "subnetid": "string", "vpcid": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_fields, {}),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["SubnetId", "VpcId"])

            assert len(results) == 2
            assert all(r[1] is None for r in results)


class TestShapeCacheIntegration:

    @patch("awsquery.shapes.Loader")
    def test_loads_and_caches_multiple_services(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.side_effect = lambda svc, *args: ["2016-11-15"]
        mock_loader.load_service_model.side_effect = lambda svc, *args: {
            "metadata": {"serviceId": svc.upper()},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()

        cache.get_service_model("ec2")
        cache.get_service_model("s3")
        cache.get_service_model("iam")

        assert "ec2" in cache._cache
        assert "s3" in cache._cache
        assert "iam" in cache._cache
        assert mock_loader.load_service_model.call_count == 3

    @patch("awsquery.shapes.Loader")
    def test_handles_different_operation_name_formats(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock()
        mock_service_model.operation_model.return_value = mock_operation_model

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()

        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape1 = cache.get_operation_shape("ec2", "describe-instances")
            shape2 = cache.get_operation_shape("ec2", "describe_instances")
            shape3 = cache.get_operation_shape("ec2", "DescribeInstances")

            assert shape1 is mock_output_shape
            assert shape2 is mock_output_shape
            assert shape3 is mock_output_shape
