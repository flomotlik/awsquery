from unittest.mock import Mock, patch

import pytest

from awsquery.filter_validator import FilterValidator


class TestFilterValidatorInitialization:

    def test_initializes_with_default_shape_cache(self):
        validator = FilterValidator()
        assert validator.shape_cache is not None

    def test_initializes_with_provided_shape_cache(self):
        from awsquery.shapes import ShapeCache

        custom_cache = ShapeCache()
        validator = FilterValidator(shape_cache=custom_cache)
        assert validator.shape_cache is custom_cache


class TestColumnFilterValidation:

    def test_validates_exact_match_filter(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["^InstanceId$"])

            assert len(results) == 1
            assert results[0][0] == "^InstanceId$"
            assert results[0][1] is None

    def test_validates_prefix_match_filter(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string", "InstanceState": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["^Instance"])

            assert len(results) == 1
            assert results[0][0] == "^Instance"
            assert results[0][1] is None

    def test_validates_suffix_match_filter(self):
        validator = FilterValidator()

        mock_fields = {
            "PublicIpAddress": "string",
            "PrivateIpAddress": "string",
            "MacAddress": "string",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["Address$"])

            assert len(results) == 1
            assert results[0][0] == "Address$"
            assert results[0][1] is None

    def test_validates_contains_match_filter(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "SubnetId": "string", "VpcId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["Id"])

            assert len(results) == 1
            assert results[0][0] == "Id"
            assert results[0][1] is None

    def test_validates_exclude_filter(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string", "State": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["!ResponseMetadata"])

            assert len(results) == 1
            assert results[0][0] == "!ResponseMetadata"

    def test_fails_validation_for_non_matching_filter(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["InvalidField"])

            assert len(results) == 1
            assert results[0][0] == "InvalidField"
            assert results[0][1] is not None
            assert "matches no fields" in results[0][1]

    def test_validates_multiple_filters(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string", "State": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns(
                "ec2", "describe-instances", ["^InstanceId$", "Type", "InvalidField"]
            )

            assert len(results) == 3
            assert results[0][1] is None
            assert results[1][1] is None
            assert results[2][1] is not None

    def test_validates_case_insensitive(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "instancetype": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["instanceid"])

            assert len(results) == 1
            assert results[0][1] is None


class TestMapWildcardHandling:

    def test_accepts_any_field_for_map_wildcard(self):
        validator = FilterValidator()

        mock_fields = {"*": "map-wildcard"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Attributes", mock_fields, mock_fields),
        ):
            results = validator.validate_columns(
                "sns", "get-topic-attributes", ["Policy", "DisplayName", "AnyField"]
            )

            assert len(results) == 3
            assert all(r[1] is None for r in results)

    def test_map_wildcard_accepts_prefix_filters(self):
        validator = FilterValidator()

        mock_fields = {"*": "map-wildcard"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Attributes", mock_fields, mock_fields),
        ):
            results = validator.validate_columns("sns", "get-topic-attributes", ["^Display"])

            assert len(results) == 1
            assert results[0][1] is None

    def test_map_wildcard_accepts_exact_match(self):
        validator = FilterValidator()

        mock_fields = {"*": "map-wildcard"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Attributes", mock_fields, mock_fields),
        ):
            results = validator.validate_columns("sns", "get-topic-attributes", ["^Policy$"])

            assert len(results) == 1
            assert results[0][1] is None


class TestSimilarityBasedSuggestions:

    def test_suggests_exact_substring_match(self):
        validator = FilterValidator()

        mock_fields = {
            "InstanceId": "string",
            "InstanceType": "string",
            "PublicIpAddress": "string",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["Instx"])

            assert len(results) == 1
            assert results[0][1] is not None
            assert "Did you mean" in results[0][1] or "matches no fields" in results[0][1]

    def test_suggests_partial_word_match(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "NetworkInterfaceId": "string", "SubnetId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["netwrk"])

            assert len(results) == 1
            assert results[0][1] is not None
            assert "Did you mean" in results[0][1] or "matches no fields" in results[0][1]

    def test_no_suggestion_when_no_similar_field(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string", "InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["xyz"])

            assert len(results) == 1
            assert results[0][1] is not None
            assert "Did you mean" not in results[0][1]
            assert "matches no fields" in results[0][1]

    def test_case_insensitive_suggestions(self):
        validator = FilterValidator()

        mock_fields = {"PublicIpAddress": "string", "PrivateIpAddress": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["PUBLICIP"])

            assert len(results) == 1
            assert results[0][1] is not None or results[0][1] is None


class TestRealAWSServiceExamples:

    def test_validates_ec2_describe_instances_filters(self):
        validator = FilterValidator()

        mock_fields = {
            "instanceid": "string",
            "instancetype": "string",
            "state": "structure",
            "publicipaddress": "string",
            "privateipaddress": "string",
            "subnetid": "string",
            "vpcid": "string",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_fields, {}),
        ):
            results = validator.validate_columns(
                "ec2", "describe-instances", ["InstanceId", "State", "^PublicIp"]
            )

            assert len(results) == 3
            assert all(r[1] is None for r in results)

    def test_validates_s3_list_buckets_filters(self):
        validator = FilterValidator()

        mock_fields = {"name": "string", "creationdate": "timestamp"}

        with patch.object(
            validator.shape_cache, "get_response_fields", return_value=("Buckets", mock_fields, {})
        ):
            results = validator.validate_columns("s3", "list-buckets", ["Name", "CreationDate"])

            assert len(results) == 2
            assert all(r[1] is None for r in results)

    def test_validates_iam_list_users_filters(self):
        validator = FilterValidator()

        mock_fields = {
            "username": "string",
            "userid": "string",
            "arn": "string",
            "createdate": "timestamp",
        }

        with patch.object(
            validator.shape_cache, "get_response_fields", return_value=("Users", mock_fields, {})
        ):
            results = validator.validate_columns(
                "iam", "list-users", ["UserName", "Arn", "CreateDate"]
            )

            assert len(results) == 3
            assert all(r[1] is None for r in results)

    def test_validates_lambda_list_functions_filters(self):
        validator = FilterValidator()

        mock_fields = {
            "functionname": "string",
            "functionarn": "string",
            "runtime": "string",
            "handler": "string",
            "codesize": "long",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Functions", mock_fields, {}),
        ):
            results = validator.validate_columns(
                "lambda", "list-functions", ["FunctionName", "Runtime", "^Function"]
            )

            assert len(results) == 3
            assert all(r[1] is None for r in results)


class TestErrorHandling:

    def test_fails_fast_when_shape_unavailable(self):
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

    def test_graceful_degradation_on_cache_error(self):
        validator = FilterValidator()

        with patch.object(
            validator.shape_cache, "get_response_fields", side_effect=Exception("Cache error")
        ):
            with pytest.raises(Exception):
                validator.validate_columns("ec2", "describe-instances", ["InstanceId"])

    def test_handles_empty_filter_list(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", [])

            assert results == []

    def test_handles_none_filter_pattern(self):
        validator = FilterValidator()

        mock_fields = {"InstanceId": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", [""])

            assert len(results) == 1


class TestGetAvailableFields:

    def test_returns_simplified_fields(self):
        validator = FilterValidator()

        mock_simplified = {"instanceid": "string", "instancetype": "string"}
        mock_full = {"Instances.0.InstanceId": "string", "Instances.0.InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_simplified, mock_full),
        ):
            fields = validator.get_available_fields("ec2", "describe-instances")

            assert fields == mock_simplified

    def test_returns_empty_dict_when_no_fields(self):
        validator = FilterValidator()

        with patch.object(
            validator.shape_cache, "get_response_fields", return_value=(None, {}, {})
        ):
            fields = validator.get_available_fields("unknown", "unknown-operation")

            assert fields == {}


class TestFilterPatternEdgeCases:

    def test_handles_unicode_circumflex(self):
        validator = FilterValidator()

        mock_fields = {"instanceid": "string", "instancetype": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["ˆInstance"])

            assert len(results) == 1
            assert results[0][1] is None

    def test_handles_multiple_operators(self):
        validator = FilterValidator()

        mock_fields = {"instanceid": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["^InstanceId$"])

            assert len(results) == 1
            assert results[0][1] is None

    def test_handles_special_characters_in_pattern(self):
        validator = FilterValidator()

        mock_fields = {"state.name": "string", "state.code": "integer"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["State.Name"])

            assert len(results) == 1
            assert results[0][1] is None

    def test_handles_empty_pattern(self):
        validator = FilterValidator()

        mock_fields = {"instanceid": "string", "instancetype": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=(None, mock_fields, mock_fields),
        ):
            results = validator.validate_columns("ec2", "describe-instances", [""])

            assert len(results) == 1


class TestValidationWithDataFieldExtraction:

    def test_validates_against_extracted_data_fields(self):
        validator = FilterValidator()

        mock_simplified = {"instanceid": "string", "instancetype": "string"}
        mock_full = {"InstanceId": "string", "InstanceType": "string"}

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_simplified, mock_full),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["InstanceId"])

            assert len(results) == 1
            assert results[0][1] is None

    def test_validates_nested_field_paths(self):
        validator = FilterValidator()

        mock_simplified = {"subnetid": "string", "vpcid": "string"}
        mock_full = {
            "NetworkInterfaces.0.SubnetId": "string",
            "NetworkInterfaces.0.VpcId": "string",
        }

        with patch.object(
            validator.shape_cache,
            "get_response_fields",
            return_value=("Instances", mock_simplified, mock_full),
        ):
            results = validator.validate_columns("ec2", "describe-instances", ["SubnetId"])

            assert len(results) == 1
            assert results[0][1] is None
