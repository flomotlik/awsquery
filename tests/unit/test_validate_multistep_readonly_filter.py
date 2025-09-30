"""Tests for readonly filtering in validate_multistep_functions.py script."""

import sys
from datetime import datetime
from unittest.mock import MagicMock, Mock, call, patch

import pytest

sys.path.insert(0, "scripts")
from validate_multistep_functions import (  # noqa: E402
    _get_most_broken_services,
    _get_most_problematic_params,
    generate_report,
    scan_service,
    to_pascal_case,
)


class TestToPascalCase:
    def test_single_word(self):
        assert to_pascal_case("describe") == "Describe"

    def test_two_words(self):
        assert to_pascal_case("describe_instances") == "DescribeInstances"

    def test_multiple_words(self):
        assert to_pascal_case("get_bucket_policy_status") == "GetBucketPolicyStatus"

    def test_already_uppercase(self):
        assert to_pascal_case("DESCRIBE_INSTANCES") == "DescribeInstances"

    def test_empty_string(self):
        assert to_pascal_case("") == ""


class TestScanServiceReadonlyFilter:
    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_skips_non_readonly_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["CreateVolume", "DeleteSnapshot"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.side_effect = lambda op: op not in ["CreateVolume", "DeleteSnapshot"]

        results = scan_service("ec2")

        assert len(results["no_required"]) == 2
        for item in results["no_required"]:
            assert item["reason"] == "Not a readonly operation (skipped)"
            assert item["operation"] in ["CreateVolume", "DeleteSnapshot"]
            assert item["service"] == "ec2"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.infer_list_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_processes_readonly_operations_with_required_params(
        self, mock_session_class, mock_infer, mock_is_readonly
    ):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_input_shape = Mock()
        mock_input_shape.required_members = ["VolumeId"]

        mock_operation_model = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""

        mock_service_model = Mock()
        mock_service_model.operation_names = ["DescribeVolumes"]
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True
        mock_infer.return_value = ["list_volumes"]

        results = scan_service("ec2")

        assert len(results["broken"]) + len(results["valid"]) >= 1
        mock_is_readonly.assert_called_with("DescribeVolumes")

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_processes_readonly_operations_without_required_params(
        self, mock_session_class, mock_is_readonly
    ):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_input_shape = Mock()
        mock_input_shape.required_members = []

        mock_operation_model = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""

        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListBuckets"]
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True

        results = scan_service("s3")

        no_required_items = [
            item
            for item in results["no_required"]
            if item.get("reason") == "No required parameters"
        ]
        assert len(no_required_items) == 1
        assert no_required_items[0]["operation"] == "ListBuckets"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_mixed_readonly_and_nonreadonly_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = [
            "DescribeInstances",
            "CreateVolume",
            "ListBuckets",
            "DeleteSnapshot",
            "GetObject",
        ]
        mock_session.get_service_model.return_value = mock_service_model

        readonly_ops = ["DescribeInstances", "ListBuckets", "GetObject"]
        mock_is_readonly.side_effect = lambda op: op in readonly_ops

        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model

        results = scan_service("test-service")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 2

        skipped_ops = [item["operation"] for item in skipped]
        assert "CreateVolume" in skipped_ops
        assert "DeleteSnapshot" in skipped_ops

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.infer_list_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_batch_operations_are_processed(self, mock_session_class, mock_infer, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_input_shape = Mock()
        mock_input_shape.required_members = ["RequestItems"]

        mock_operation_model = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_operation_model.documentation = ""

        mock_service_model = Mock()
        mock_service_model.operation_names = ["BatchGetItem"]
        mock_service_model.operation_model.return_value = mock_operation_model
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True
        mock_infer.return_value = ["list_items"]

        results = scan_service("dynamodb")

        assert len(results["broken"]) + len(results["valid"]) >= 1
        mock_is_readonly.assert_called_with("BatchGetItem")


class TestGenerateReport:
    def test_readonly_filtering_enabled_flag(self):
        all_results = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {
                "ec2": {
                    "total_operations": 5,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 5,
                    "no_required_details": [],
                }
            },
        }

        report_json = generate_report(all_results)
        import json

        report = json.loads(report_json)

        assert report["statistics"]["readonly_filtering_enabled"] is True

    def test_readonly_operations_scanned_count(self):
        all_results = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {
                "ec2": {
                    "total_operations": 10,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 5,
                    "no_required_details": [],
                },
                "s3": {
                    "total_operations": 15,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 10,
                    "no_required_details": [],
                },
            },
        }

        report_json = generate_report(all_results)
        import json

        report = json.loads(report_json)

        assert report["statistics"]["readonly_operations_scanned"] == 25

    def test_non_readonly_operations_skipped_count(self):
        all_results = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {
                "ec2": {
                    "total_operations": 10,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 5,
                    "no_required_details": [
                        {
                            "operation": "CreateVolume",
                            "reason": "Not a readonly operation (skipped)",
                        },
                        {
                            "operation": "DeleteSnapshot",
                            "reason": "Not a readonly operation (skipped)",
                        },
                        {"operation": "DescribeInstances", "reason": "No required parameters"},
                    ],
                },
                "s3": {
                    "total_operations": 8,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 3,
                    "no_required_details": [
                        {
                            "operation": "DeleteBucket",
                            "reason": "Not a readonly operation (skipped)",
                        },
                        {"operation": "ListBuckets", "reason": "No required parameters"},
                    ],
                },
            },
        }

        report_json = generate_report(all_results)
        import json

        report = json.loads(report_json)

        assert report["statistics"]["non_readonly_operations_skipped"] == 3

    def test_report_structure_includes_readonly_fields(self):
        all_results = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {
                "test": {
                    "total_operations": 1,
                    "broken": [],
                    "valid": [],
                    "conditional": [],
                    "no_required": 1,
                    "no_required_details": [],
                }
            },
        }

        report_json = generate_report(all_results)
        import json

        report = json.loads(report_json)

        stats = report["statistics"]
        assert "readonly_filtering_enabled" in stats
        assert "readonly_operations_scanned" in stats
        assert "non_readonly_operations_skipped" in stats

    def test_statistics_calculation_with_mixed_results(self):
        all_results = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {
                "ec2": {
                    "total_operations": 20,
                    "broken": [
                        {"operation": "Op1", "required_param": "P1"},
                        {"operation": "Op2", "required_param": "P2"},
                    ],
                    "valid": [
                        {"operation": "Op3", "required_param": "P3"},
                    ],
                    "conditional": [],
                    "no_required": 17,
                    "no_required_details": [
                        {"operation": "CreateOp1", "reason": "Not a readonly operation (skipped)"},
                        {"operation": "DeleteOp1", "reason": "Not a readonly operation (skipped)"},
                    ]
                    + [
                        {"operation": f"Op{i}", "reason": "No required parameters"}
                        for i in range(15)
                    ],
                }
            },
        }

        report_json = generate_report(all_results)
        import json

        report = json.loads(report_json)

        stats = report["statistics"]
        assert stats["total_services_scanned"] == 1
        assert stats["total_operations_analyzed"] == 20
        assert stats["readonly_operations_scanned"] == 20
        assert stats["non_readonly_operations_skipped"] == 2
        assert stats["multi_step_scenarios"]["broken"] == 2
        assert stats["multi_step_scenarios"]["valid"] == 1


class TestMostBrokenServices:
    def test_empty_services(self):
        result = _get_most_broken_services({})
        assert result == []

    def test_services_with_no_broken(self):
        services = {
            "ec2": {"broken": []},
            "s3": {"broken": []},
        }
        result = _get_most_broken_services(services)
        assert result == []

    def test_services_with_broken_scenarios(self):
        services = {
            "ec2": {"broken": [{"op": 1}, {"op": 2}, {"op": 3}]},
            "s3": {"broken": [{"op": 1}]},
            "dynamodb": {"broken": [{"op": 1}, {"op": 2}]},
        }
        result = _get_most_broken_services(services)

        assert len(result) == 3
        assert result[0]["service"] == "ec2"
        assert result[0]["broken_count"] == 3
        assert result[1]["service"] == "dynamodb"
        assert result[1]["broken_count"] == 2
        assert result[2]["service"] == "s3"
        assert result[2]["broken_count"] == 1

    def test_top_limit(self):
        services = {f"service{i}": {"broken": [{"op": j} for j in range(i)]} for i in range(1, 15)}
        result = _get_most_broken_services(services, top=5)

        assert len(result) == 5
        assert result[0]["broken_count"] == 14


class TestMostProblematicParams:
    def test_empty_services(self):
        result = _get_most_problematic_params({})
        assert result == []

    def test_services_with_no_broken(self):
        services = {
            "ec2": {"broken": []},
            "s3": {"broken": []},
        }
        result = _get_most_problematic_params(services)
        assert result == []

    def test_count_problematic_params(self):
        services = {
            "ec2": {
                "broken": [
                    {"operation": "Op1", "parameters": {"VolumeId": {"valid_operations": []}}},
                    {"operation": "Op2", "parameters": {"InstanceId": {"valid_operations": []}}},
                    {"operation": "Op3", "parameters": {"VolumeId": {"valid_operations": []}}},
                ]
            },
            "s3": {
                "broken": [
                    {"operation": "Op4", "parameters": {"BucketName": {"valid_operations": []}}},
                    {"operation": "Op5", "parameters": {"VolumeId": {"valid_operations": []}}},
                ]
            },
        }

        result = _get_most_problematic_params(services)

        assert len(result) == 3
        assert result[0]["param_name"] == "VolumeId"
        assert result[0]["count"] == 3
        assert len(result[0]["examples"]) <= 3

    def test_examples_limit(self):
        services = {
            "ec2": {
                "broken": [
                    {"operation": f"Op{i}", "parameters": {"TestParam": {"valid_operations": []}}}
                    for i in range(10)
                ]
            }
        }

        result = _get_most_problematic_params(services)

        assert len(result[0]["examples"]) == 3

    def test_top_limit(self):
        services = {
            f"service{i}": {
                "broken": [
                    {"operation": "Op1", "parameters": {f"Param{i}": {"valid_operations": []}}}
                ]
            }
            for i in range(20)
        }

        result = _get_most_problematic_params(services, top=5)
        assert len(result) == 5


class TestReadonlyOperationPrefixes:
    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_get_prefix_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["GetObject"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True

        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model

        results = scan_service("s3")

        mock_is_readonly.assert_called_with("GetObject")

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_list_prefix_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListBuckets"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True

        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model

        results = scan_service("s3")

        mock_is_readonly.assert_called_with("ListBuckets")

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_describe_prefix_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["DescribeInstances"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True

        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model

        results = scan_service("ec2")

        mock_is_readonly.assert_called_with("DescribeInstances")

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_search_prefix_operations(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["SearchResources"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = True

        mock_operation_model = Mock()
        mock_operation_model.input_shape = None
        mock_service_model.operation_model.return_value = mock_operation_model

        results = scan_service("resource-explorer")

        mock_is_readonly.assert_called_with("SearchResources")


class TestWriteOperationPrefixes:
    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_create_prefix_operations_skipped(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["CreateVolume"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = False

        results = scan_service("ec2")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 1
        assert skipped[0]["operation"] == "CreateVolume"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_delete_prefix_operations_skipped(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["DeleteSnapshot"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = False

        results = scan_service("ec2")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 1
        assert skipped[0]["operation"] == "DeleteSnapshot"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_modify_prefix_operations_skipped(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["ModifyInstanceAttribute"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = False

        results = scan_service("ec2")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 1
        assert skipped[0]["operation"] == "ModifyInstanceAttribute"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_accept_prefix_operations_skipped(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["AcceptAddressTransfer"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = False

        results = scan_service("ec2")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 1
        assert skipped[0]["operation"] == "AcceptAddressTransfer"

    @patch("validate_multistep_functions.is_readonly_operation")
    @patch("validate_multistep_functions.botocore.session.Session")
    def test_allocate_prefix_operations_skipped(self, mock_session_class, mock_is_readonly):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_service_model = Mock()
        mock_service_model.operation_names = ["AllocateAddress"]
        mock_session.get_service_model.return_value = mock_service_model

        mock_is_readonly.return_value = False

        results = scan_service("ec2")

        skipped = [
            item
            for item in results["no_required"]
            if item.get("reason") == "Not a readonly operation (skipped)"
        ]
        assert len(skipped) == 1
        assert skipped[0]["operation"] == "AllocateAddress"
