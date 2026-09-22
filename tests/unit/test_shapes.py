from unittest.mock import Mock, patch

import pytest
from botocore.model import ListShape, MapShape, ServiceModel, StringShape, StructureShape

from awsquery.errors import set_structured_errors, structured_errors_enabled
from awsquery.shapes import (
    ShapeCache,
    _is_plural,
    _names_the_same_thing,
    _split_verb,
    get_shape_cache,
    reset_shape_cache,
)


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

        result = cache.identify_data_field(mock_shape, "ec2", "ListItems")
        assert result == "Items"

    def test_prefers_the_list_named_after_the_operation(self):
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

        result = cache.identify_data_field(mock_shape, "ec2", "DescribeInstances")
        assert result == "Instances"

    def test_identifies_single_non_list_field(self):
        cache = ShapeCache()

        mock_string_shape = Mock()
        mock_string_shape.type_name = "string"

        mock_shape = Mock()
        mock_shape.members = {
            "LocationConstraint": mock_string_shape,
            "ResponseMetadata": Mock(type_name="structure"),
        }

        result = cache.identify_data_field(mock_shape, "s3", "GetBucketLocation")
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

        result = cache.identify_data_field(mock_shape, "s3", "ListBuckets")
        assert result == "Buckets"

    def test_returns_none_when_no_members(self):
        cache = ShapeCache()

        mock_shape = Mock()
        mock_shape.members = {}

        result = cache.identify_data_field(mock_shape, "s3", "ListBuckets")
        assert result is None

    def test_returns_none_when_no_shape(self):
        cache = ShapeCache()

        result = cache.identify_data_field(None, "s3", "ListBuckets")
        assert result is None

    def test_returns_none_when_shape_has_no_members_attribute(self):
        cache = ShapeCache()

        mock_shape = Mock(spec=[])

        result = cache.identify_data_field(mock_shape, "s3", "ListBuckets")
        assert result is None


class TestCollectionVersusSingleObject:
    # Real botocore shapes: the rule has to hold against the service models, not mocks.

    @pytest.mark.parametrize(
        "service,operation,unrelated_list",
        [
            ("lambda", "GetFunctionConfiguration", "Layers"),
            ("sagemaker", "DescribeNotebookInstance", "SecurityGroups"),
            ("cloudformation", "DescribeChangeSet", "Parameters"),
            ("sagemaker", "DescribeEndpoint", "ProductionVariants"),
            ("sagemaker", "DescribeModel", "Containers"),
            ("elasticbeanstalk", "DescribeEnvironmentHealth", "Causes"),
            ("kafka", "DescribeConfiguration", "KafkaVersions"),
            ("iam", "GetSAMLProvider", "Tags"),
            ("apigatewayv2", "GetRoute", "AuthorizationScopes"),
            ("s3", "GetBucketWebsite", "RoutingRules"),
        ],
    )
    def test_single_object_response_has_no_data_field(self, service, operation, unrelated_list):
        cache = ShapeCache()
        shape = cache.get_operation_shape(service, operation)

        assert shape.members[unrelated_list].type_name == "list"
        assert cache.identify_data_field(shape, service, operation) is None

    @pytest.mark.parametrize(
        "service,operation,expected",
        [
            ("s3", "ListBuckets", "Buckets"),
            ("s3", "ListObjectsV2", "Contents"),
            ("s3", "ListMultipartUploads", "Uploads"),
            ("route53", "ListHostedZones", "HostedZones"),
            ("route53", "ListHealthChecks", "HealthChecks"),
            ("route53", "ListResourceRecordSets", "ResourceRecordSets"),
            ("ce", "GetRightsizingRecommendation", "RightsizingRecommendations"),
            ("ec2", "DescribeInstances", "Reservations"),
            ("ec2", "DescribeInstanceStatus", "InstanceStatuses"),
            ("cloudformation", "DescribeStacks", "Stacks"),
            ("apigateway", "GetRestApis", "items"),
            ("dynamodb", "Scan", "Items"),
            ("cloudtrail", "LookupEvents", "Events"),
        ],
    )
    def test_collection_response_keeps_its_list(self, service, operation, expected):
        cache = ShapeCache()
        shape = cache.get_operation_shape(service, operation)

        assert cache.identify_data_field(shape, service, operation) == expected

    def test_kebab_case_operation_names_resolve(self):
        cache = ShapeCache()

        data_field, _, _ = cache.get_response_fields("lambda", "get-function-configuration")

        assert data_field is None

    def test_object_fields_become_available_to_filters(self):
        cache = ShapeCache()

        _, simplified, _ = cache.get_response_fields("lambda", "GetFunctionConfiguration")

        assert simplified["FunctionName"] == "string"
        assert simplified["MemorySize"] == "integer"
        assert "Layers.Arn" in simplified

    def test_a_list_with_no_siblings_is_the_data(self):
        cache = ShapeCache()
        shape = cache.get_operation_shape("s3", "GetBucketTagging")

        assert cache.identify_data_field(shape, "s3", "GetBucketTagging") == "TagSet"


class TestOperationNameHeuristics:

    @pytest.mark.parametrize(
        "operation,expected",
        [
            ("ListBuckets", ("List", "Buckets")),
            ("BatchGetProfile", ("BatchGet", "Profile")),
            ("Scan", ("Scan", "")),
            ("DescribeStacks", ("Describe", "Stacks")),
        ],
    )
    def test_split_verb(self, operation, expected):
        assert _split_verb(operation) == expected

    @pytest.mark.parametrize(
        "word,expected",
        [
            ("Stacks", True),
            ("Policies", True),
            ("Addresses", True),
            ("RestApis", True),
            ("ObjectsV2", True),
            ("Status", False),
            ("Address", False),
            ("Analysis", False),
            ("EnvironmentHealth", False),
            ("ChangeSet", False),
        ],
    )
    def test_is_plural(self, word, expected):
        assert _is_plural(word) is expected

    @pytest.mark.parametrize(
        "noun,member,expected",
        [
            ("Buckets", "Buckets", True),
            ("InstanceStatus", "InstanceStatuses", True),
            ("DimensionKeys", "Keys", True),
            ("UserAuthFactors", "ConfiguredUserAuthFactors", True),
            ("FunctionConfiguration", "Layers", False),
            ("BucketWebsite", "RoutingRules", False),
            # A one-word noun is too weak to claim a longer member name
            ("Statement", "SubStatements", False),
            ("Type", "directParentTypes", False),
        ],
    )
    def test_names_the_same_thing(self, noun, member, expected):
        assert _names_the_same_thing(noun, member) is expected


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


class TestSharedShapeCache:

    def test_repeated_calls_return_the_same_instance(self):
        assert get_shape_cache() is get_shape_cache()

    def test_parsed_models_are_reused_across_call_sites(self):
        get_shape_cache().get_service_model("ec2")

        assert "ec2" in get_shape_cache()._cache

    def test_constructing_directly_gives_an_isolated_cache(self):
        get_shape_cache().get_service_model("ec2")
        isolated = ShapeCache()

        assert isolated is not get_shape_cache()
        assert isolated._cache == {}

    def test_reset_drops_the_parsed_models(self):
        shared = get_shape_cache()
        shared.get_service_model("ec2")

        reset_shape_cache()

        assert get_shape_cache() is not shared
        assert get_shape_cache()._cache == {}

    def test_reset_is_safe_before_anything_built_the_cache(self):
        reset_shape_cache()
        reset_shape_cache()

        assert get_shape_cache()._cache == {}


class TestAutouseFixtureIsolation:
    # Both tests dirty exactly the state they assert is clean, so they hold
    # whichever order they run in.

    def test_shared_state_starts_clean_first(self):
        assert get_shape_cache()._cache == {}
        assert structured_errors_enabled() is False

        get_shape_cache().get_service_model("ec2")
        set_structured_errors(True)

    def test_shared_state_starts_clean_second(self):
        assert get_shape_cache()._cache == {}
        assert structured_errors_enabled() is False

        get_shape_cache().get_service_model("s3")
        set_structured_errors(True)
