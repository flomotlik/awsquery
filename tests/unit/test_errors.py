"""Unit tests for exit codes and error reporting."""

import ast
import json
from pathlib import Path

import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    NoRegionError,
    ParamValidationError,
    PartialCredentialsError,
    TokenRetrievalError,
)

from awsquery.errors import (
    CREDENTIALS_HINT,
    REGION_HINT,
    ExitCode,
    classify_exception,
    emit_error,
    emit_notice,
    fail,
    looks_like_auth_failure,
    set_structured_errors,
    structured_errors_enabled,
)


def client_error(code):
    return ClientError(
        {"Error": {"Code": code, "Message": f"{code} happened"}}, "DescribeInstances"
    )


@pytest.fixture(autouse=True)
def reset_structured_errors():
    set_structured_errors(False)
    yield
    set_structured_errors(False)


class TestExitCode:

    def test_documented_values(self):
        assert ExitCode.SUCCESS == 0
        assert ExitCode.ERROR == 1
        assert ExitCode.USAGE == 2
        assert ExitCode.AWS_ERROR == 3
        assert ExitCode.AUTH_ERROR == 4

    def test_codes_are_usable_as_process_exit_status(self):
        assert [int(code) for code in ExitCode] == [0, 1, 2, 3, 4]


class TestClassifyException:

    @pytest.mark.parametrize(
        "exception,expected_code",
        [
            (NoCredentialsError(), ExitCode.AUTH_ERROR),
            (
                PartialCredentialsError(provider="env", cred_var="aws_secret_access_key"),
                ExitCode.AUTH_ERROR,
            ),
            (TokenRetrievalError(provider="sso", error_msg="token expired"), ExitCode.AUTH_ERROR),
            (NoRegionError(), ExitCode.AUTH_ERROR),
            (client_error("AuthFailure"), ExitCode.AUTH_ERROR),
            (client_error("UnauthorizedOperation"), ExitCode.AUTH_ERROR),
            (client_error("ExpiredToken"), ExitCode.AUTH_ERROR),
            (client_error("InvalidClientTokenId"), ExitCode.AUTH_ERROR),
            (client_error("Throttling"), ExitCode.AWS_ERROR),
            (client_error("InvalidParameterValue"), ExitCode.AWS_ERROR),
            (EndpointConnectionError(endpoint_url="https://ec2.eu-west-1.amazonaws.com"), 3),
            (ParamValidationError(report="missing required key"), ExitCode.AWS_ERROR),
            (ValueError("boom"), ExitCode.ERROR),
            (RuntimeError("unexpected"), ExitCode.ERROR),
        ],
    )
    def test_exit_code_mapping(self, exception, expected_code):
        code, _, _, _ = classify_exception(exception)

        assert code == expected_code

    def test_error_type_is_the_aws_error_code(self):
        _, error_type, _, _ = classify_exception(client_error("Throttling"))

        assert error_type == "Throttling"

    def test_message_carries_the_exception_text(self):
        _, _, message, _ = classify_exception(ValueError("boom"))

        assert message == "boom"

    def test_region_error_suggests_region_configuration(self):
        _, _, _, hint = classify_exception(NoRegionError())

        assert hint == REGION_HINT

    @pytest.mark.parametrize(
        "exception",
        [NoCredentialsError(), client_error("ExpiredToken")],
    )
    def test_auth_failures_suggest_credentials(self, exception):
        _, _, _, hint = classify_exception(exception)

        assert hint == CREDENTIALS_HINT

    def test_aws_errors_carry_no_hint(self):
        _, _, _, hint = classify_exception(client_error("Throttling"))

        assert hint is None

    def test_client_error_without_error_code_is_an_aws_error(self):
        code, _, _, _ = classify_exception(ClientError({}, "DescribeInstances"))

        assert code == ExitCode.AWS_ERROR


class TestEmitErrorHumanMode:

    def test_writes_error_to_stderr_only(self, capsys):
        emit_error(ExitCode.USAGE, "UnknownService", "Unknown service 'ec3'")

        captured = capsys.readouterr()
        assert captured.err == "ERROR: Unknown service 'ec3'\n"
        assert captured.out == ""

    def test_hint_follows_the_error_on_stderr(self, capsys):
        emit_error(
            ExitCode.USAGE,
            "UnknownService",
            "Unknown service 'ec3'",
            hint="Run: awsquery --list-services",
        )

        captured = capsys.readouterr()
        assert captured.err.splitlines() == [
            "ERROR: Unknown service 'ec3'",
            "Hint: Run: awsquery --list-services",
        ]
        assert captured.out == ""

    def test_no_hint_line_without_a_hint(self, capsys):
        emit_error(ExitCode.AWS_ERROR, "AwsApiError", "Throttling")

        assert "Hint:" not in capsys.readouterr().err


class TestEmitErrorStructuredMode:

    def test_single_compact_json_line_on_stderr(self, capsys):
        set_structured_errors(True)
        emit_error(ExitCode.USAGE, "UnknownService", "Unknown service 'ec3'")

        captured = capsys.readouterr()
        lines = captured.err.splitlines()
        payload = {
            "error": {"code": 2, "type": "UnknownService", "message": "Unknown service 'ec3'"}
        }
        assert len(lines) == 1
        assert json.loads(lines[0]) == payload
        assert lines[0] == json.dumps(payload, separators=(",", ":"))
        assert captured.out == ""

    def test_payload_shape_has_code_type_and_message(self, capsys):
        set_structured_errors(True)
        emit_error(ExitCode.AUTH_ERROR, "CredentialsError", "Unable to locate credentials")

        payload = json.loads(capsys.readouterr().err)
        assert set(payload) == {"error"}
        assert set(payload["error"]) == {"code", "type", "message"}
        assert isinstance(payload["error"]["code"], int)

    def test_hint_is_part_of_the_json_object(self, capsys):
        set_structured_errors(True)
        emit_error(
            ExitCode.USAGE,
            "MissingService",
            "--list-actions needs a service name",
            hint="Run: awsquery --list-services",
        )

        payload = json.loads(capsys.readouterr().err)
        assert payload["error"]["hint"] == "Run: awsquery --list-services"

    def test_disabling_returns_to_human_output(self, capsys):
        set_structured_errors(True)
        set_structured_errors(False)
        emit_error(ExitCode.ERROR, "Boom", "boom")

        assert capsys.readouterr().err == "ERROR: boom\n"

    def test_state_is_readable(self):
        assert structured_errors_enabled() is False
        set_structured_errors(True)
        assert structured_errors_enabled() is True


class TestFail:

    @pytest.mark.parametrize(
        "code", [ExitCode.ERROR, ExitCode.USAGE, ExitCode.AWS_ERROR, ExitCode.AUTH_ERROR]
    )
    def test_exits_with_the_given_code(self, code, capsys):
        with pytest.raises(SystemExit) as exc_info:
            fail(code, "SomeError", "something went wrong")

        assert exc_info.value.code == int(code)
        capsys.readouterr()

    def test_human_mode_message_and_hint_go_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            fail(ExitCode.USAGE, "InvalidLimit", "--limit must not be negative", hint="Use N >= 0")

        captured = capsys.readouterr()
        assert captured.err.splitlines() == [
            "ERROR: --limit must not be negative",
            "Hint: Use N >= 0",
        ]
        assert captured.out == ""

    def test_structured_mode_emits_one_json_line(self, capsys):
        set_structured_errors(True)

        with pytest.raises(SystemExit) as exc_info:
            fail(ExitCode.AWS_ERROR, "AwsApiError", "Throttling")

        captured = capsys.readouterr()
        assert exc_info.value.code == 3
        assert json.loads(captured.err) == {
            "error": {"code": 3, "type": "AwsApiError", "message": "Throttling"}
        }
        assert captured.out == ""


class TestEmitNotice:

    def test_human_text_drops_the_error_prefix(self, capsys):
        emit_notice("EmptyResult", "No data to extract keys from")

        captured = capsys.readouterr()
        assert captured.err == "No data to extract keys from\n"
        assert "ERROR" not in captured.err
        assert captured.out == ""

    def test_failure_codes_keep_the_error_prefix(self, capsys):
        emit_error(ExitCode.AWS_ERROR, "Throttling", "slow down")

        assert capsys.readouterr().err.startswith("ERROR: ")

    def test_hint_still_follows_a_success_notice(self, capsys):
        emit_notice("EmptyResult", "nothing here", hint="widen the filters")

        assert capsys.readouterr().err.splitlines() == ["nothing here", "Hint: widen the filters"]

    def test_structured_notice_uses_its_own_envelope(self, capsys):
        set_structured_errors(True)

        emit_notice("EmptyResult", "nothing here")

        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload == {"notice": {"code": 0, "type": "EmptyResult", "message": "nothing here"}}
        assert "error" not in payload
        assert captured.out == ""

    def test_structured_failure_keeps_the_error_envelope(self, capsys):
        set_structured_errors(True)

        emit_error(ExitCode.AWS_ERROR, "Throttling", "slow down")

        payload = json.loads(capsys.readouterr().err)
        assert payload == {"error": {"code": 3, "type": "Throttling", "message": "slow down"}}
        assert "notice" not in payload


class TestLooksLikeAuthFailure:

    @pytest.mark.parametrize(
        "text",
        [
            "Unable to locate credentials",
            "You must specify a region.",
            "NoRegionError: no region",
            "An error occurred (ExpiredToken) when calling DescribeInstances",
            "An error occurred (AuthFailure) when calling DescribeInstances",
            "An error occurred (UnauthorizedOperation)",
            "An error occurred (InvalidClientTokenId)",
            "The security token has expired",
            "Error loading SSO Token: Token for sso-session has expired",
            "The SSO session associated with this profile has expired",
            "Error when retrieving token from sso: Token has expired",
            "UnauthorizedSSOTokenError: the SSO token is invalid",
            "The config profile (dev) could not be found",
        ],
    )
    def test_auth_related_messages_match(self, text):
        assert looks_like_auth_failure(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "An error occurred (Throttling) when calling DescribeInstances",
            "ParamValidationError: missing required key",
            "connection reset by peer",
            # "sso" is a substring of "association"; a bare marker misfires here
            "InvalidAssociationID.NotFound: association not found",
            "An error occurred (InvalidAssociationID.NotFound) when calling DescribeAssociation",
            "Stack with id foo could not be found",
            "The SSO directory has no matching user",
        ],
    )
    def test_unrelated_messages_do_not_match(self, text):
        assert looks_like_auth_failure(text) is False

    def test_matching_is_case_insensitive(self):
        assert looks_like_auth_failure("UNABLE TO LOCATE CREDENTIALS") is True


SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "awsquery"


def sys_exit_calls(tree):
    for node in ast.walk(tree):
        func = getattr(node, "func", None)
        if (
            isinstance(node, ast.Call)
            and isinstance(func, ast.Attribute)
            and func.attr == "exit"
            and isinstance(func.value, ast.Name)
            and func.value.id == "sys"
        ):
            yield node


def stray_exits(path):
    """sys.exit() calls that neither live in errors.fail nor exit successfully."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sanctioned = set()
    if path.name == "errors.py":
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "fail":
                sanctioned.update(id(call) for call in sys_exit_calls(node))

    stray = []
    for call in sys_exit_calls(tree):
        if id(call) in sanctioned:
            continue
        argument = ast.unparse(call.args[0]) if call.args else ""
        if argument == "ExitCode.SUCCESS":
            continue
        stray.append(f"{path.name}:{call.lineno}: sys.exit({argument})")
    return stray


class TestExitDiscipline:

    def test_scan_covers_the_modules_that_exit(self):
        scanned = {path.name for path in SRC_DIR.rglob("*.py")}

        assert {"cli.py", "core.py", "errors.py", "introspection.py"} <= scanned

    def test_failure_exits_go_through_fail(self):
        stray = [entry for path in sorted(SRC_DIR.rglob("*.py")) for entry in stray_exits(path)]

        assert stray == []

    def test_scanner_reports_a_planted_bare_exit(self, tmp_path):
        planted = tmp_path / "planted.py"
        planted.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")

        assert stray_exits(planted) == ["planted.py:2: sys.exit(1)"]

    def test_scanner_accepts_success_exits(self, tmp_path):
        planted = tmp_path / "planted.py"
        planted.write_text("import sys\nsys.exit(ExitCode.SUCCESS)\n", encoding="utf-8")

        assert stray_exits(planted) == []
