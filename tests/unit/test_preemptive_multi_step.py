"""Tests for preemptive multi-step detection functionality."""

from unittest.mock import Mock, patch

import pytest

from awsquery.core import (
    _extract_conditional_requirement,
    check_parameter_requirements,
    infer_list_operation,
)


class TestCheckParameterRequirements:

    def test_operation_with_strict_required_params(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.required_members = ["Names"]
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("ssm", "get-parameters", {})

        assert result["needs_params"] is True
        assert result["required"] == ["Names"]
        assert result["conditional"] is None
        assert result["missing_required"] == ["Names"]

    def test_operation_with_no_required_params(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.required_members = []
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("ec2", "describe-instances", {})

        assert result["needs_params"] is False
        assert result["required"] == []
        assert result["conditional"] is None
        assert result["missing_required"] == []

    def test_operation_with_conditional_requirements(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.required_members = []
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = (
            "You must specify either LoadBalancerArn or TargetGroupArn to identify the resource."
        )
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("elbv2", "describe-listeners", {})

        assert result["needs_params"] is False
        assert result["required"] == []
        assert result["conditional"] is not None
        assert "either" in result["conditional"].lower()
        assert result["missing_required"] == []

    def test_operation_with_provided_params(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.required_members = ["Names"]
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("ssm", "get-parameters", {"Names": ["param1"]})

        assert result["needs_params"] is False
        assert result["required"] == ["Names"]
        assert result["conditional"] is None
        assert result["missing_required"] == []

    def test_operation_missing_some_required_params(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_input_shape = Mock()

        mock_input_shape.required_members = ["ClusterName", "NodegroupName"]
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("eks", "describe-nodegroup", {"ClusterName": "test"})

        assert result["needs_params"] is True
        assert result["required"] == ["ClusterName", "NodegroupName"]
        assert result["conditional"] is None
        assert result["missing_required"] == ["NodegroupName"]

    def test_operation_with_no_input_shape(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_operation_model.documentation = ""
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("s3", "list-buckets", {})

        assert result["needs_params"] is False
        assert result["required"] == []
        assert result["conditional"] is None
        assert result["missing_required"] == []

    def test_handles_missing_operation_gracefully(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_model.side_effect = Exception("Operation not found")
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = check_parameter_requirements("service", "nonexistent-operation", {})

        assert result["needs_params"] is False
        assert result["required"] == []
        assert result["conditional"] is None
        assert result["missing_required"] == []


class TestExtractConditionalRequirement:

    @pytest.mark.parametrize(
        "doc,expected_match",
        [
            (
                "You must specify either LoadBalancerArn or TargetGroupArn.",
                "either LoadBalancerArn or TargetGroupArn",
            ),
            (
                "You must specify at least one of the following: ResourceArn, ResourceType.",
                "at least one of",
            ),
            (
                "The parameter is required if you specify AutoScaling.",
                "required if",
            ),
            (
                "You must specify one of the following parameters: StackName, StackId.",
                "one of the following",
            ),
        ],
    )
    def test_extracts_conditional_patterns(self, doc, expected_match):
        result = _extract_conditional_requirement(doc)
        assert result is not None
        assert expected_match.lower() in result.lower()

    def test_returns_none_for_empty_documentation(self):
        result = _extract_conditional_requirement("")
        assert result is None

    def test_returns_none_for_none_documentation(self):
        result = _extract_conditional_requirement(None)
        assert result is None

    def test_returns_none_for_no_conditional_patterns(self):
        doc = "This operation describes instances. You can filter the results."
        result = _extract_conditional_requirement(doc)
        assert result is None

    def test_cleans_html_tags_from_documentation(self):
        doc = "You must specify either LoadBalancerArn or TargetGroupArn. <code>Example</code>."
        result = _extract_conditional_requirement(doc)
        assert result is not None
        assert "<code>" not in result
        assert "either" in result.lower()

    def test_extracts_first_matching_sentence(self):
        doc = (
            "This operation describes listeners. "
            "You must specify either LoadBalancerArn or TargetGroupArn. "
            "The operation returns details about the listeners."
        )
        result = _extract_conditional_requirement(doc)
        assert result is not None
        assert "must specify either" in result.lower()
        assert "returns details" not in result.lower()


class TestInferListOperationValidation:

    def test_validates_operations_exist(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeInstances",
            "ListBuckets",
            "DescribeClusters",
        ]
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = infer_list_operation("ec2", "instanceId", "describe-instance-attribute")

        assert isinstance(result, list)
        for op in result:
            pascal_op = "".join(word.capitalize() for word in op.split("_"))
            assert pascal_op in mock_service_model.operation_names

    def test_filters_out_non_existent_operations(self):
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["DescribeInstances"]
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = infer_list_operation("ec2", "instanceId", "describe-instance-attribute")

        assert isinstance(result, list)
        assert "describe_instances" in result
        assert "list_instances" not in result

    def test_returns_unvalidated_list_when_no_operations_match(self):
        """When no operations validate, return unvalidated list as fallback."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["SomeOtherOperation"]
        mock_client.meta.service_model = mock_service_model

        from awsquery import utils

        utils.boto3.client.return_value = mock_client

        result = infer_list_operation("service", "resourceId", "describe-resource")

        assert isinstance(result, list)
        assert len(result) > 0
        assert "list_resources" in result
        assert "describe_resources" in result

    def test_works_with_session_parameter(self):
        mock_session = Mock()
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["DescribeClusters", "ListClusters"]
        mock_client.meta.service_model = mock_service_model

        with patch("awsquery.core.get_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            result = infer_list_operation(
                "eks", "clusterName", "describe-cluster", session=mock_session
            )

            assert isinstance(result, list)
            assert "describe_clusters" in result or "list_clusters" in result
            mock_get_client.assert_called_once_with("eks", mock_session)

    def test_handles_validation_error_gracefully(self):
        from awsquery import utils

        utils.boto3.client.side_effect = Exception("Service not found")

        result = infer_list_operation("nonexistent", "resourceId", "describe-resource")

        assert isinstance(result, list)


class TestMainPreemptiveDetection:

    @patch("awsquery.cli.execute_multi_level_call")
    @patch("awsquery.cli.check_parameter_requirements")
    def test_preemptive_multi_step_when_missing_required_params(
        self, mock_check_params, mock_multi_level, capsys
    ):
        mock_check_params.return_value = {
            "needs_params": True,
            "required": ["Names"],
            "conditional": None,
            "missing_required": ["Names"],
        }
        mock_multi_level.return_value = [{"Parameter": {"Name": "test"}}]

        from awsquery.cli import main

        with patch("sys.argv", ["awsquery", "ssm", "get-parameters"]):
            with patch("awsquery.cli.validate_readonly", return_value=True):
                with patch("awsquery.cli.create_session", return_value=None):
                    with patch("awsquery.cli.determine_column_filters", return_value=None):
                        with patch("awsquery.cli.format_table_output", return_value="output"):
                            main()

        mock_check_params.assert_called_once()
        mock_multi_level.assert_called_once()

    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.check_parameter_requirements")
    def test_conditional_warning_when_no_params_provided(
        self, mock_check_params, mock_execute, capsys
    ):
        mock_check_params.return_value = {
            "needs_params": False,
            "required": [],
            "conditional": "You must specify either LoadBalancerArn or TargetGroupArn",
            "missing_required": [],
        }
        mock_execute.return_value = [{"Listeners": []}]

        from awsquery.cli import main

        with patch("sys.argv", ["awsquery", "elbv2", "describe-listeners"]):
            with patch("awsquery.cli.validate_readonly", return_value=True):
                with patch("awsquery.cli.create_session", return_value=None):
                    with patch("awsquery.cli.determine_column_filters", return_value=None):
                        with patch("awsquery.cli.format_table_output", return_value="output"):
                            main()

        captured = capsys.readouterr()
        assert "Note:" in captured.err
        assert "either LoadBalancerArn or TargetGroupArn" in captured.err

    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.check_parameter_requirements")
    def test_normal_execution_when_no_requirements(self, mock_check_params, mock_execute):
        mock_check_params.return_value = {
            "needs_params": False,
            "required": [],
            "conditional": None,
            "missing_required": [],
        }
        mock_execute.return_value = [{"Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]}]

        from awsquery.cli import main

        with patch("sys.argv", ["awsquery", "ec2", "describe-instances"]):
            with patch("awsquery.cli.validate_readonly", return_value=True):
                with patch("awsquery.cli.create_session", return_value=None):
                    with patch("awsquery.cli.determine_column_filters", return_value=None):
                        with patch("awsquery.cli.format_table_output", return_value="output"):
                            main()

        mock_check_params.assert_called_once()
        mock_execute.assert_called_once()

    @patch("awsquery.cli.execute_multi_level_call")
    @patch("awsquery.cli.execute_aws_call")
    @patch("awsquery.cli.check_parameter_requirements")
    def test_fallback_to_multi_step_on_unexpected_validation_error(
        self, mock_check_params, mock_execute, mock_multi_level
    ):
        mock_check_params.return_value = {
            "needs_params": False,
            "required": [],
            "conditional": None,
            "missing_required": [],
        }
        mock_execute.return_value = {
            "validation_error": {
                "parameter_name": "clusterName",
                "is_required": True,
                "error_type": "missing_parameter",
            }
        }
        mock_multi_level.return_value = [{"Cluster": {"Name": "test"}}]

        from awsquery.cli import main

        with patch("sys.argv", ["awsquery", "eks", "describe-cluster"]):
            with patch("awsquery.cli.validate_readonly", return_value=True):
                with patch("awsquery.cli.create_session", return_value=None):
                    with patch("awsquery.cli.determine_column_filters", return_value=None):
                        with patch("awsquery.cli.format_table_output", return_value="output"):
                            main()

        mock_check_params.assert_called_once()
        mock_execute.assert_called_once()
        mock_multi_level.assert_called_once()

    @patch("awsquery.cli.execute_multi_level_call")
    @patch("awsquery.cli.check_parameter_requirements")
    def test_debug_output_shows_preemptive_detection(
        self, mock_check_params, mock_multi_level, debug_mode, capsys
    ):
        mock_check_params.return_value = {
            "needs_params": True,
            "required": ["ClusterName"],
            "conditional": None,
            "missing_required": ["ClusterName"],
        }
        mock_multi_level.return_value = [{"Cluster": {"Name": "test"}}]

        from awsquery.cli import main

        with patch("sys.argv", ["awsquery", "eks", "describe-cluster", "-d"]):
            with patch("awsquery.cli.validate_readonly", return_value=True):
                with patch("awsquery.cli.create_session", return_value=None):
                    with patch("awsquery.cli.determine_column_filters", return_value=None):
                        with patch("awsquery.cli.format_table_output", return_value="output"):
                            main()

        captured = capsys.readouterr()
        assert (
            "Preemptive multi-step" in captured.err or "missing required parameters" in captured.err
        )


class TestErrorMessageImprovements:

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_shows_tried_operations_when_none_found(self, mock_infer, mock_execute, capsys):
        validation_error = {
            "parameter_name": "clusterName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_infer.return_value = ["list_clusters", "describe_clusters"]
        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            Exception("Operation failed"),
            Exception("Operation failed"),
        ]

        from awsquery.core import execute_multi_level_call

        with pytest.raises(SystemExit):
            execute_multi_level_call("eks", "describe-cluster", [], [], [])

        captured = capsys.readouterr()
        assert "Tried operations:" in captured.err
        assert "list_clusters" in captured.err or "describe_clusters" in captured.err

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_suggests_using_input_flag(self, mock_infer, mock_execute, capsys):
        validation_error = {
            "parameter_name": "functionName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_infer.return_value = ["list_functions"]
        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            Exception("Operation failed"),
        ]

        from awsquery.core import execute_multi_level_call

        with pytest.raises(SystemExit):
            execute_multi_level_call("lambda", "get-function", [], [], [])

        captured = capsys.readouterr()
        assert "-i/--input" in captured.err or "--input" in captured.err
        assert "Specify function:" in captured.err

    @patch("awsquery.core.execute_aws_call")
    @patch("awsquery.core.infer_list_operation")
    def test_shows_how_to_find_available_operations(self, mock_infer, mock_execute, capsys):
        validation_error = {
            "parameter_name": "bucketName",
            "is_required": True,
            "error_type": "missing_parameter",
        }

        mock_infer.return_value = ["list_buckets"]
        mock_execute.side_effect = [
            {"validation_error": validation_error, "original_error": Exception()},
            Exception("Operation failed"),
        ]

        from awsquery.core import execute_multi_level_call

        with pytest.raises(SystemExit):
            execute_multi_level_call("s3", "get-bucket-policy", [], [], [])

        captured = capsys.readouterr()
        assert "Available operations" in captured.err or "can be viewed with" in captured.err
        assert "aws s3 help" in captured.err
