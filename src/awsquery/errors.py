"""Exit codes and error reporting for AWS Query Tool.

Exit codes are the machine-readable contract for callers (agents, scripts, CI):

    0  success, including an empty result set
    1  general or unexpected error
    2  usage error, unknown service/action, unsafe operation refused non-interactively
    3  AWS API error
    4  credentials, region or authentication failure

Errors always go to stderr so stdout stays parseable. Under the machine-readable
output formats (json, ndjson) they are emitted as one compact JSON object.
"""

import json
import sys
from enum import IntEnum
from typing import NoReturn, Optional, Tuple

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
    ProfileNotFound,
    SSOError,
    TokenRetrievalError,
    UnknownServiceError,
)


class UnknownActionError(Exception):
    """A known service was asked for an operation it does not have."""

    def __init__(self, service: str, action: str) -> None:
        """Record which service and action failed to resolve."""
        super().__init__(f"Unknown action '{action}' for service '{service}'")
        self.service = service
        self.action = action


# Every botocore error class that means "fix your identity", not "retry the call"
AUTH_EXCEPTIONS = (
    NoCredentialsError,
    PartialCredentialsError,
    TokenRetrievalError,
    ProfileNotFound,
    SSOError,  # covers UnauthorizedSSOTokenError and SSOTokenLoadError
    CredentialRetrievalError,
)


class ExitCode(IntEnum):
    """Process exit codes used across the tool."""

    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    AWS_ERROR = 3
    AUTH_ERROR = 4


# ClientError codes that mean "your identity is the problem", not "your request is"
AUTH_CLIENT_ERROR_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "AuthFailure",
        "ExpiredToken",
        "ExpiredTokenException",
        "InvalidAccessKeyId",
        "InvalidClientTokenId",
        "RequestExpired",
        "SignatureDoesNotMatch",
        "UnauthorizedOperation",
        "UnrecognizedClientException",
    }
)

CREDENTIALS_HINT = "Configure AWS credentials, or pass --profile"
REGION_HINT = "Set AWS_DEFAULT_REGION or AWS_REGION, or pass --region"
SERVICE_LIST_HINT = "Run: awsquery --list-services"

_structured_errors = False


def set_structured_errors(enabled: bool) -> None:
    """Emit errors as compact JSON on stderr (json/ndjson output formats)."""
    global _structured_errors  # pylint: disable=global-statement
    _structured_errors = bool(enabled)


def structured_errors_enabled() -> bool:
    """Whether errors are emitted as JSON objects."""
    return _structured_errors


def _emit(
    envelope: str,
    code: "ExitCode",
    report_type: str,
    message: str,
    hint: Optional[str],
    prefix: str,
) -> None:
    """Write one report to stderr in the shape the selected output format expects."""
    if _structured_errors:
        payload = {"code": int(code), "type": report_type, "message": message}
        if hint:
            payload["hint"] = hint
        print(json.dumps({envelope: payload}, separators=(",", ":"), default=str), file=sys.stderr)
    else:
        print(f"{prefix}{message}", file=sys.stderr)
        if hint:
            print(f"Hint: {hint}", file=sys.stderr)


def emit_error(code: "ExitCode", error_type: str, message: str, hint: Optional[str] = None) -> None:
    """Report a failure. Always a non-zero code; successes use emit_notice."""
    _emit("error", code, error_type, message, hint, "ERROR: ")


def emit_notice(notice_type: str, message: str, hint: Optional[str] = None) -> None:
    """Report a non-failure condition, such as an empty result.

    Deliberately a separate envelope from emit_error: a consumer that branches
    on the presence of "error" must never see a successful run as a failure.
    """
    _emit("notice", ExitCode.SUCCESS, notice_type, message, hint, "")


def fail(code: "ExitCode", error_type: str, message: str, hint: Optional[str] = None) -> NoReturn:
    """Report an error and exit with its code."""
    emit_error(code, error_type, message, hint)
    sys.exit(int(code))


def first_sentence(text: str) -> str:
    """First sentence of an error message, dropping any appended catalogue."""
    head = text.split("\n", 1)[0].strip()
    stop = head.find(". ")
    return head[: stop + 1] if stop != -1 else head


def classify_exception(exc: BaseException) -> Tuple[ExitCode, str, str, Optional[str]]:
    """Map an exception to (exit code, type name, message, hint)."""
    error_type = type(exc).__name__

    if isinstance(exc, UnknownActionError):
        return (
            ExitCode.USAGE,
            "UnknownAction",
            str(exc),
            f"Run: awsquery {exc.service} --list-actions",
        )

    if isinstance(exc, NoRegionError):
        return ExitCode.AUTH_ERROR, error_type, str(exc), REGION_HINT

    if isinstance(exc, AUTH_EXCEPTIONS):
        return ExitCode.AUTH_ERROR, error_type, str(exc), CREDENTIALS_HINT

    if isinstance(exc, ClientError):
        # The AWS error code is the machine-readable discriminator, not the class name
        aws_code = exc.response.get("Error", {}).get("Code", "")
        error_type = aws_code or error_type
        if aws_code in AUTH_CLIENT_ERROR_CODES:
            return ExitCode.AUTH_ERROR, error_type, str(exc), CREDENTIALS_HINT
        return ExitCode.AWS_ERROR, error_type, str(exc), None

    if isinstance(exc, UnknownServiceError):
        # botocore appends every known service name; the first sentence is the useful part
        return ExitCode.USAGE, "UnknownService", first_sentence(str(exc)), SERVICE_LIST_HINT

    if isinstance(exc, BotoCoreError):
        return ExitCode.AWS_ERROR, error_type, str(exc), None

    return ExitCode.ERROR, error_type, str(exc), None


def looks_like_auth_failure(text: str) -> bool:
    """Heuristic for error strings collected from failed calls (keys mode)."""
    lowered = text.lower()
    markers = (
        "credential",
        "unable to locate credentials",
        "must specify a region",
        "noregionerror",
        "expiredtoken",
        "authfailure",
        "unauthorizedoperation",
        "invalidclienttokenid",
        "unrecognizedclient",
        "accessdenied",
        # Narrow SSO markers: a bare "sso" also matches "association", "ssodirectory", ...
        "sso session",
        "sso token",
        "ssooidc",
        "unauthorizedssotoken",
        # ProfileNotFound reads "The config profile (x) could not be found"
        "config profile",
        "token has expired",
    )
    return any(marker in lowered for marker in markers)
