from unittest.mock import Mock, patch

import pytest
from botocore.model import ListShape, MapShape, ServiceModel, StringShape, StructureShape

from awsquery.shapes import ShapeCache


class TestShapeCacheInitialization:

    def test_initializes_with_empty_cache(self):
        cache = ShapeCache()
        assert cache._cache == {}
        assert cache._loader is not None

    def test_loader_is_botocore_loader(self):
        from botocore.loaders import Loader

        cache = ShapeCache()
        assert isinstance(cache._loader, Loader)


class TestServiceModelCaching:

    @patch("awsquery.shapes.Loader")
    def test_caches_service_model_on_first_access(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]
        mock_loader.load_service_model.return_value = {
            "metadata": {"serviceId": "EC2"},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        model = cache.get_service_model("ec2")

        assert model is not None
        assert "ec2" in cache._cache
        mock_loader.load_service_model.assert_called_once_with("ec2", "service-2", "2016-11-15")

    @patch("awsquery.shapes.Loader")
    def test_returns_cached_model_on_subsequent_access(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]
        mock_loader.load_service_model.return_value = {
            "metadata": {"serviceId": "EC2"},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        model1 = cache.get_service_model("ec2")
        model2 = cache.get_service_model("ec2")

        assert model1 is model2
        mock_loader.load_service_model.assert_called_once()

    @patch("awsquery.shapes.Loader")
    def test_uses_latest_api_version(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2014-06-15", "2015-10-01", "2016-11-15"]
        mock_loader.load_service_model.return_value = {
            "metadata": {"serviceId": "EC2"},
            "operations": {},
        }
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        cache.get_service_model("ec2")

        mock_loader.load_service_model.assert_called_with("ec2", "service-2", "2016-11-15")

    @patch("awsquery.shapes.Loader")
    def test_returns_none_when_no_api_versions(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = []
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        model = cache.get_service_model("nonexistent")

        assert model is None

    @patch("awsquery.shapes.Loader")
    def test_returns_none_on_loading_error(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]
        mock_loader.load_service_model.side_effect = Exception("Service not found")
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        model = cache.get_service_model("invalid-service")

        assert model is None


class TestOperationShapeLoading:

    @patch("awsquery.shapes.Loader")
    def test_converts_kebab_case_to_pascal_case(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.return_value = mock_operation_model

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("ec2", "describe-instances")

            mock_service_model.operation_model.assert_called_with("DescribeInstances")
            assert shape is mock_output_shape

    @patch("awsquery.shapes.Loader")
    def test_converts_snake_case_to_pascal_case(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.return_value = mock_operation_model

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("s3", "list_buckets")

            mock_service_model.operation_model.assert_called_with("ListBuckets")
            assert shape is mock_output_shape

    @patch("awsquery.shapes.Loader")
    def test_case_insensitive_fallback_for_aws_acronyms(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.side_effect = [
            Exception("Not found"),
            mock_operation_model,
        ]
        mock_service_model.operation_names = ["ListSAMLProviders", "GetSAMLProvider"]

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("iam", "list-saml-providers")

            assert shape is mock_output_shape

    @patch("awsquery.shapes.Loader")
    def test_handles_mfa_acronym(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.side_effect = [
            Exception("Not found"),
            mock_operation_model,
        ]
        mock_service_model.operation_names = ["EnableMFADevice", "ListMFADevices"]

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("iam", "list-mfa-devices")

            assert shape is mock_output_shape

    @patch("awsquery.shapes.Loader")
    def test_handles_db_acronym(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_output_shape = Mock()
        mock_operation_model = Mock()
        mock_operation_model.output_shape = mock_output_shape

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.side_effect = [
            Exception("Not found"),
            mock_operation_model,
        ]
        mock_service_model.operation_names = ["DescribeDBInstances", "ListDBClusters"]

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("rds", "describe-db-instances")

            assert shape is mock_output_shape

    @patch("awsquery.shapes.Loader")
    def test_returns_none_when_operation_not_found(self, mock_loader_class):
        mock_loader = Mock()
        mock_loader.list_api_versions.return_value = ["2016-11-15"]

        mock_service_model = Mock(spec=ServiceModel)
        mock_service_model.operation_model.side_effect = Exception("Operation not found")
        mock_service_model.operation_names = ["DescribeInstances", "ListBuckets"]

        mock_loader.load_service_model.return_value = {"metadata": {}, "operations": {}}
        mock_loader_class.return_value = mock_loader

        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=mock_service_model):
            shape = cache.get_operation_shape("ec2", "invalid-operation")

            assert shape is None

    def test_returns_none_when_service_model_unavailable(self):
        cache = ShapeCache()
        with patch.object(cache, "get_service_model", return_value=None):
            shape = cache.get_operation_shape("nonexistent", "describe-something")

            assert shape is None


class TestResponseFieldExtraction:

    def test_extracts_structure_fields(self):
        cache = ShapeCache()

        mock_member_shape = Mock()
        mock_member_shape.type_name = "string"

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {"FieldA": mock_member_shape, "FieldB": mock_member_shape}

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            data_field, simplified, full = cache.get_response_fields("ec2", "describe-test")

            assert "fielda" in simplified or "FieldA" in simplified
            assert "fieldb" in simplified or "FieldB" in simplified

    def test_extracts_list_fields_with_zero_notation(self):
        cache = ShapeCache()

        mock_list_item_shape = Mock()
        mock_list_item_shape.type_name = "structure"
        mock_list_item_shape.members = {
            "ItemId": Mock(type_name="string"),
            "ItemName": Mock(type_name="string"),
        }

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_list_item_shape

        mock_metadata_shape = Mock()
        mock_metadata_shape.type_name = "structure"
        mock_metadata_shape.members = {}

        mock_output_shape = Mock()
        mock_output_shape.type_name = "structure"
        mock_output_shape.members = {
            "Items": mock_list_shape,
            "ResponseMetadata": mock_metadata_shape,
        }

        with patch.object(cache, "get_operation_shape", return_value=mock_output_shape):
            with patch.object(cache, "identify_data_field", return_value="Items"):
                data_field, simplified, full = cache.get_response_fields("ec2", "describe-test")

                assert data_field == "Items"
                assert any("itemid" in k.lower() for k in simplified.keys())

    def test_extracts_map_fields(self):
        cache = ShapeCache()

        mock_value_shape = Mock()
        mock_value_shape.type_name = "string"

        mock_map_shape = Mock()
        mock_map_shape.type_name = "map"
        mock_map_shape.value = mock_value_shape

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

    def test_extracts_primitive_type_fields(self):
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
                assert "LocationConstraint" in full or "locationconstraint" in simplified

    def test_returns_empty_when_no_output_shape(self):
        cache = ShapeCache()

        with patch.object(cache, "get_operation_shape", return_value=None):
            data_field, simplified, full = cache.get_response_fields("ec2", "invalid-operation")

            assert data_field is None
            assert simplified == {}
            assert full == {}

    def test_simplifies_field_paths(self):
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

        mock_list_item_shape = Mock()
        mock_list_item_shape.type_name = "structure"
        mock_list_item_shape.members = {
            "NetworkInterfaces": mock_network_interfaces_shape,
            "InstanceId": Mock(type_name="string"),
        }

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_list_item_shape

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
            with patch.object(cache, "identify_data_field", return_value="Instances"):
                data_field, simplified, full = cache.get_response_fields(
                    "ec2", "describe-instances"
                )

                assert any("subnetid" in k.lower() for k in simplified.keys())
                assert any("vpcid" in k.lower() for k in simplified.keys())


class TestDataFieldIdentification:

    def test_identifies_single_list_field(self):
        cache = ShapeCache()

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"

        mock_shape = Mock()
        mock_shape.members = {
            "Items": mock_list_shape,
            "ResponseMetadata": Mock(type_name="structure"),
            "NextToken": Mock(type_name="string"),
        }

        result = cache.identify_data_field(mock_shape)
        assert result == "Items"

    def test_identifies_first_of_multiple_list_fields(self):
        cache = ShapeCache()

        mock_list_shape1 = Mock()
        mock_list_shape1.type_name = "list"

        mock_list_shape2 = Mock()
        mock_list_shape2.type_name = "list"

        mock_shape = Mock()
        mock_shape.members = {
            "Reservations": mock_list_shape1,
            "Instances": mock_list_shape2,
            "ResponseMetadata": Mock(type_name="structure"),
        }

        result = cache.identify_data_field(mock_shape)
        assert result in ["Reservations", "Instances"]

    def test_identifies_single_non_list_field(self):
        cache = ShapeCache()

        mock_string_shape = Mock()
        mock_string_shape.type_name = "string"

        mock_shape = Mock()
        mock_shape.members = {
            "LocationConstraint": mock_string_shape,
            "ResponseMetadata": Mock(type_name="structure"),
        }

        result = cache.identify_data_field(mock_shape)
        assert result == "LocationConstraint"

    def test_skips_known_metadata_fields(self):
        cache = ShapeCache()

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"

        mock_shape = Mock()
        mock_shape.members = {
            "ResponseMetadata": Mock(type_name="structure"),
            "NextToken": Mock(type_name="string"),
            "NextMarker": Mock(type_name="string"),
            "IsTruncated": Mock(type_name="boolean"),
            "Buckets": mock_list_shape,
        }

        result = cache.identify_data_field(mock_shape)
        assert result == "Buckets"

    def test_returns_none_when_no_members(self):
        cache = ShapeCache()

        mock_shape = Mock()
        mock_shape.members = {}

        result = cache.identify_data_field(mock_shape)
        assert result is None

    def test_returns_none_when_no_shape(self):
        cache = ShapeCache()

        result = cache.identify_data_field(None)
        assert result is None

    def test_returns_none_when_shape_has_no_members_attribute(self):
        cache = ShapeCache()

        mock_shape = Mock(spec=[])

        result = cache.identify_data_field(mock_shape)
        assert result is None


class TestShapeFlattening:

    def test_flattens_structure_members(self):
        cache = ShapeCache()

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {
            "FieldA": Mock(type_name="string"),
            "FieldB": Mock(type_name="integer"),
        }

        result = cache._flatten_shape(mock_shape)

        assert "FieldA" in result
        assert result["FieldA"] == "string"
        assert "FieldB" in result
        assert result["FieldB"] == "integer"

    def test_flattens_nested_structures(self):
        cache = ShapeCache()

        mock_nested_shape = Mock()
        mock_nested_shape.type_name = "structure"
        mock_nested_shape.members = {"NestedField": Mock(type_name="string")}

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {"ParentField": mock_nested_shape}

        result = cache._flatten_shape(mock_shape)

        assert "ParentField" in result
        assert "ParentField.NestedField" in result
        assert result["ParentField.NestedField"] == "string"

    def test_flattens_list_with_structure_members(self):
        cache = ShapeCache()

        mock_list_item = Mock()
        mock_list_item.type_name = "structure"
        mock_list_item.members = {
            "ItemId": Mock(type_name="string"),
            "ItemName": Mock(type_name="string"),
        }

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_list_item

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {"Items": mock_list_shape}

        result = cache._flatten_shape(mock_shape)

        assert "Items" in result
        assert "Items.0.ItemId" in result
        assert "Items.0.ItemName" in result

    def test_flattens_list_with_primitive_members(self):
        cache = ShapeCache()

        mock_list_shape = Mock()
        mock_list_shape.type_name = "list"
        mock_list_shape.member = Mock(type_name="string")

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {"Tags": mock_list_shape}

        result = cache._flatten_shape(mock_shape)

        assert "Tags" in result
        assert "Tags.0" in result
        assert result["Tags.0"] == "string"

    def test_flattens_map_type(self):
        cache = ShapeCache()

        mock_map_shape = Mock()
        mock_map_shape.type_name = "map"
        mock_map_shape.value = Mock(type_name="string")

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {"Attributes": mock_map_shape}

        result = cache._flatten_shape(mock_shape)

        assert "Attributes" in result
        assert result["Attributes"] == "map"

    def test_respects_max_depth(self):
        cache = ShapeCache()

        mock_deep_shape = Mock()
        mock_deep_shape.type_name = "structure"
        mock_deep_shape.members = {"DeepField": Mock(type_name="string")}

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {"Level1": mock_deep_shape}

        result = cache._flatten_shape(mock_shape, max_depth=0)

        assert "Level1" in result
        assert "Level1.DeepField" not in result

    def test_handles_none_shape(self):
        cache = ShapeCache()

        result = cache._flatten_shape(None)

        assert result == {}

    def test_handles_empty_structure(self):
        cache = ShapeCache()

        mock_shape = Mock()
        mock_shape.type_name = "structure"
        mock_shape.members = {}

        result = cache._flatten_shape(mock_shape)

        assert result == {}
