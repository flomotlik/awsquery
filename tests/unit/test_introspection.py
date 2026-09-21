"""Unit tests for credential-free introspection of services, actions and schemas."""

import json
import re
from pathlib import Path

import pytest

from awsquery.introspection import (
    build_schema,
    list_actions,
    list_services,
    print_docs,
    print_schema,
    validate_service_action,
)
from awsquery.security import is_readonly_operation
from awsquery.utils import get_aws_services

REFERENCE_PATH = Path(__file__).resolve().parents[2] / "src" / "awsquery" / "agent-reference.md"

# "  Name        type" - a regression collapses these two columns into one token
FIELD_LINE = re.compile(r"^ {2}(\S+) +(\S+)$")


def output_field_lines(text):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Output fields ("))
    return lines[start + 1 :]


class TestListServices:

    def test_text_output_is_one_service_per_line(self, capsys):
        list_services()

        printed = capsys.readouterr().out.splitlines()
        assert printed == get_aws_services()
        assert all(line.strip() == line and line for line in printed)

    def test_json_output_round_trips(self, capsys):
        list_services(as_json=True)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed == get_aws_services()
        assert "ec2" in parsed

    def test_services_are_sorted_and_unique(self, capsys):
        list_services()

        printed = capsys.readouterr().out.splitlines()
        assert printed == sorted(printed)
        assert len(printed) == len(set(printed))


class TestListActions:

    def test_actions_are_kebab_case_and_sorted(self, capsys):
        list_actions("ec2")

        actions = capsys.readouterr().out.splitlines()
        assert actions == sorted(actions)
        assert all(action == action.lower() for action in actions)
        assert "describe-instances" in actions

    def test_only_readonly_actions_are_listed(self, capsys):
        list_actions("ec2")

        actions = capsys.readouterr().out.splitlines()
        assert "terminate-instances" not in actions
        assert "run-instances" not in actions
        assert [action for action in actions if not is_readonly_operation(action)] == []

    def test_json_output_round_trips(self, capsys):
        list_actions("s3", as_json=True)

        actions = json.loads(capsys.readouterr().out)
        assert isinstance(actions, list)
        assert "list-buckets" in actions
        assert "delete-bucket" not in actions

    def test_unknown_service_exits_with_usage_code(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            list_actions("not-a-service")

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Unknown service 'not-a-service'" in captured.err
        assert captured.out == ""


class TestBuildSchema:

    def test_ec2_describe_instances_contract(self):
        schema = build_schema("ec2", "describe-instances")

        assert schema["service"] == "ec2"
        assert schema["action"] == "describe-instances"
        assert schema["operation"] == "DescribeInstances"
        assert schema["readonly"] is True
        assert schema["paginated"] is True
        assert schema["data_field"] == "Reservations"
        assert schema["input"]["required"] == []
        assert "InstanceIds" in schema["input"]["parameters"]
        assert schema["input"]["parameters"]["InstanceIds"] == "list"

    def test_ec2_describe_instances_output_fields(self):
        schema = build_schema("ec2", "describe-instances")
        output_fields = schema["output_fields"]

        assert len(output_fields) > 100
        assert output_fields["Instances.InstanceId"] == "string"
        assert output_fields["Instances.State.Name"] == "string"
        assert list(output_fields) == sorted(output_fields)

    def test_filter_hint_is_present_and_non_empty(self):
        schema = build_schema("ec2", "describe-instances")

        assert schema["filter_hint"].strip()
        assert "$" in schema["filter_hint"]

    def test_required_parameters_are_reported(self):
        schema = build_schema("ec2", "describe-instance-attribute")

        assert schema["input"]["required"] == ["Attribute", "InstanceId"]
        assert set(schema["input"]["required"]) <= set(schema["input"]["parameters"])

    def test_cloudformation_describe_stack_events_requires_stack_name(self):
        schema = build_schema("cloudformation", "describe-stack-events")

        assert schema["input"]["required"] == ["StackName"]
        assert schema["data_field"] == "StackEvents"

    @pytest.mark.parametrize(
        "service,action",
        [
            ("ec2", "describe-instance-attribute"),
            ("sts", "get-caller-identity"),
            ("iam", "get-account-summary"),
        ],
    )
    def test_operations_without_paginator_are_not_paginated(self, service, action):
        assert build_schema(service, action)["paginated"] is False

    @pytest.mark.parametrize(
        "action", ["describe-instances", "DescribeInstances", "describe_instances"]
    )
    def test_action_spellings_resolve_to_same_operation(self, action):
        assert build_schema("ec2", action)["operation"] == "DescribeInstances"

    def test_acronym_operations_resolve_case_insensitively(self):
        assert build_schema("iam", "list-saml-providers")["operation"] == "ListSAMLProviders"

    def test_default_columns_are_included_when_configured(self):
        schema = build_schema("ec2", "describe-instances")

        assert "InstanceId$" in schema["default_columns"]

    def test_schema_is_json_serializable(self):
        schema = build_schema("ec2", "describe-instances")

        assert json.loads(json.dumps(schema)) == schema

    def test_unknown_service_exits_with_usage_code(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            build_schema("not-a-service", "describe-things")

        assert exc_info.value.code == 2
        assert "Unknown service 'not-a-service'" in capsys.readouterr().err

    def test_unknown_action_exits_with_usage_code(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            build_schema("ec2", "describe-unicorns")

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Unknown action 'describe-unicorns' for service 'ec2'" in captured.err
        assert "awsquery ec2 --list-actions" in captured.err
        assert captured.out == ""


class TestPrintSchemaText:

    def test_header_reports_service_action_and_flags(self, capsys):
        print_schema("ec2", "describe-instances")

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line == "ec2 describe-instances (readonly, paginated)"

    def test_header_reports_not_paginated(self, capsys):
        print_schema("ec2", "describe-instance-attribute")

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line == "ec2 describe-instance-attribute (readonly, not paginated)"

    def test_every_output_field_keeps_name_and_type_separated(self, capsys):
        schema = build_schema("ec2", "describe-instances")
        print_schema("ec2", "describe-instances")

        rendered = {}
        for line in output_field_lines(capsys.readouterr().out):
            match = FIELD_LINE.match(line)
            assert match is not None, f"name and type not separated: {line!r}"
            rendered[match.group(1)] = match.group(2)

        assert rendered == schema["output_fields"]

    def test_long_field_name_is_not_glued_to_its_type(self, capsys):
        print_schema("ec2", "describe-instances")

        long_name = "Instances.MetadataOptions.InstanceMetadataTags"
        lines = [line for line in capsys.readouterr().out.splitlines() if long_name in line]
        assert len(lines) == 1
        assert re.match(rf"^ {{2}}{re.escape(long_name)} +string$", lines[0])

    def test_input_parameters_are_marked_required_or_optional(self, capsys):
        print_schema("ec2", "describe-instance-attribute")

        out = capsys.readouterr().out
        parameter_lines = {
            line.split()[0]: line.split()[-1]
            for line in out.splitlines()
            if line.startswith("  ") and len(line.split()) == 3
        }
        assert parameter_lines["InstanceId"] == "required"
        assert parameter_lines["Attribute"] == "required"
        assert parameter_lines["DryRun"] == "optional"
        assert "Required: Attribute, InstanceId" in out

    def test_operation_without_input_shape_reports_none(self, capsys):
        print_schema("sts", "get-caller-identity")

        out = capsys.readouterr().out
        assert "Input parameters:\n  none" in out
        assert "Required: none" in out

    def test_field_count_matches_rendered_fields(self, capsys):
        schema = build_schema("ec2", "describe-instances")
        print_schema("ec2", "describe-instances")

        out = capsys.readouterr().out
        assert f"Output fields ({len(schema['output_fields'])}):" in out


class TestPrintSchemaJson:

    def test_json_output_matches_build_schema(self, capsys):
        print_schema("ec2", "describe-instances", as_json=True)

        assert json.loads(capsys.readouterr().out) == build_schema("ec2", "describe-instances")

    def test_unknown_action_exits_before_printing_json(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            print_schema("ec2", "describe-unicorns", as_json=True)

        assert exc_info.value.code == 2
        assert capsys.readouterr().out == ""


class TestPrintDocs:

    def test_prints_packaged_reference_verbatim(self, capsys):
        print_docs()

        out = capsys.readouterr().out
        assert out == REFERENCE_PATH.read_text(encoding="utf-8")

    def test_first_line_is_the_reference_heading(self, capsys):
        print_docs()

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("# ")
        assert first_line == REFERENCE_PATH.read_text(encoding="utf-8").splitlines()[0]


AWS_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
)


@pytest.fixture
def no_aws_environment(monkeypatch, tmp_path):
    for name in AWS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "absent-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "absent-credentials"))
    return tmp_path


class TestValidateServiceAction:

    @pytest.mark.parametrize(
        "service,action",
        [
            ("ec2", "describe-instances"),
            ("ec2", "describe_instances"),
            ("ec2", "DescribeInstances"),
            ("s3", "list-buckets"),
            ("cloudformation", "describe-stacks"),
            ("ec2", None),
        ],
    )
    def test_known_pairs_pass(self, service, action, capsys):
        validate_service_action(service, action)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_unknown_service_exits_with_usage_code(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            validate_service_action("not-a-service", "describe-things")

        captured = capsys.readouterr()
        assert exit_info.value.code == 2
        assert "Unknown service 'not-a-service'" in captured.err
        assert "Run: awsquery --list-services" in captured.err
        assert captured.out == ""

    def test_unknown_action_on_known_service_exits_with_usage_code(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            validate_service_action("ec2", "describe-unicorns")

        captured = capsys.readouterr()
        assert exit_info.value.code == 2
        assert "Unknown action 'describe-unicorns' for service 'ec2'" in captured.err
        assert "Run: awsquery ec2 --list-actions" in captured.err
        assert captured.out == ""

    def test_existing_but_unsafe_action_is_not_an_unknown_action(self, capsys):
        validate_service_action("ec2", "terminate-instances")

        assert not is_readonly_operation("TerminateInstances")
        assert capsys.readouterr().err == ""

    def test_unknown_service_wins_over_unknown_action(self, capsys):
        with pytest.raises(SystemExit):
            validate_service_action("not-a-service", "also-not-an-action")

        assert "Unknown service" in capsys.readouterr().err

    def test_known_pair_passes_without_credentials_or_region(self, no_aws_environment, capsys):
        validate_service_action("ec2", "describe-instances")

        assert capsys.readouterr().err == ""

    @pytest.mark.parametrize(
        "service,action",
        [
            ("ec2", "describe-unicorns"),
            ("not-a-service", None),
            ("not-a-service", "describe-things"),
        ],
    )
    def test_rejection_without_credentials_blames_the_name_not_the_identity(
        self, service, action, no_aws_environment, capsys
    ):
        with pytest.raises(SystemExit) as exit_info:
            validate_service_action(service, action)

        stderr = capsys.readouterr().err.lower()
        assert exit_info.value.code == 2
        assert "unknown" in stderr
        assert "credential" not in stderr
        assert "region" not in stderr
