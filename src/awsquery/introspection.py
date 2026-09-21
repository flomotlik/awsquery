"""Credential-free introspection of services, actions and operation schemas.

Everything here reads botocore's bundled service models from disk: no AWS API
call, no credentials, no region. This is what agents use to plan a query.
"""

import json
import os
import sys
from typing import Any, Dict, List, NoReturn, Optional

from .case_utils import to_kebab_case, to_pascal_case
from .config import get_default_columns
from .errors import ExitCode, fail
from .security import get_service_valid_operations, is_readonly_operation
from .shapes import get_shape_cache
from .utils import (
    _BotocoreSessionContext,
    get_aws_services,
    get_service_operations,
    normalize_action_name,
)

DOCS_FILENAME = "agent-reference.md"

MIN_NAME_WIDTH = 31
MAX_NAME_WIDTH = 60
MIN_TYPE_WIDTH = 16

# Printed field paths are structural; runtime column filters see indexed keys
FILTER_HINT = (
    "Filter columns by the trailing segments with a $ anchor (State.Name$) - list levels "
    "carry indices at runtime (Instances.0.State.Name), so full paths do not match; AWS Tags "
    "become Tags.<Key> columns (Tags.Name$) and are absent from the field list below."
)


def _fail_unknown_service(service: str) -> NoReturn:
    """Usage error for a service botocore does not ship a model for."""
    fail(
        ExitCode.USAGE,
        "UnknownService",
        f"Unknown service '{service}'",
        hint="Run: awsquery --list-services",
    )


def _fail_unknown_action(service: str, action: str) -> NoReturn:
    """Usage error for an action a known service does not have."""
    fail(
        ExitCode.USAGE,
        "UnknownAction",
        f"Unknown action '{action}' for service '{service}'",
        hint=f"Run: awsquery {service} --list-actions",
    )


def validate_service_action(service: str, action: Optional[str] = None) -> None:
    """Reject an unknown service or action offline, before any session is built.

    Existence is checked against the service model's full operation list, so an
    action that exists but is not read-only still reaches the safety refusal.
    """
    service_model = get_shape_cache().get_service_model(service)
    if service_model is None:
        _fail_unknown_service(service)

    if action and resolve_operation_name(service_model.operation_names, action) is None:
        _fail_unknown_action(service, action)


def list_services(as_json: bool = False) -> None:
    """Print every supported AWS service."""
    services = get_aws_services()
    if not services:
        fail(ExitCode.ERROR, "ServiceListUnavailable", "No AWS services available from botocore")
    if as_json:
        print(json.dumps(services, indent=2))
    else:
        print("\n".join(services))


def list_actions(service: str, as_json: bool = False) -> None:
    """Print a service's read-only actions in kebab-case."""
    operations = get_service_operations(service)
    if not operations:
        _fail_unknown_service(service)

    valid = get_service_valid_operations(service, operations)
    actions = sorted(to_kebab_case(op) for op in valid)

    if as_json:
        print(json.dumps(actions, indent=2))
    else:
        print("\n".join(actions))


def print_docs() -> None:
    """Print the packaged agent reference verbatim."""
    docs_path = os.path.join(os.path.dirname(__file__), DOCS_FILENAME)
    try:
        with open(docs_path, "r", encoding="utf-8") as handle:
            sys.stdout.write(handle.read())
    except OSError as e:
        fail(
            ExitCode.ERROR,
            "DocsUnavailable",
            f"Agent reference not available at {docs_path}: {e}",
        )


def resolve_operation_name(operation_names, action: str) -> Optional[str]:
    """Map a kebab/snake/Pascal action to a service's operation name, offline."""
    pascal_action = to_pascal_case(normalize_action_name(action))

    if pascal_action in operation_names:
        return str(pascal_action)

    # Case-insensitive fallback for AWS acronyms (SAML, MFA, DB, ...)
    lowered = pascal_action.lower()
    for name in operation_names:
        if name.lower() == lowered:
            return str(name)

    return None


def _is_paginated(service: str, operation_name: str) -> bool:
    """Whether botocore ships a paginator for this operation."""
    try:
        with _BotocoreSessionContext() as session:
            session.get_paginator_model(service).get_paginator(operation_name)
        return True
    except Exception:
        return False


def build_schema(service: str, action: str) -> Dict[str, Any]:
    """Build the operation contract: input parameters and output fields."""
    shape_cache = get_shape_cache()
    service_model = shape_cache.get_service_model(service)
    if service_model is None:
        _fail_unknown_service(service)

    operation_name = resolve_operation_name(service_model.operation_names, action)
    if operation_name is None:
        _fail_unknown_action(service, action)

    operation_model = service_model.operation_model(operation_name)
    input_shape = operation_model.input_shape

    parameters = {}
    required: List[str] = []
    if input_shape is not None:
        parameters = {name: shape.type_name for name, shape in sorted(input_shape.members.items())}
        required = sorted(input_shape.required_members)

    data_field, output_fields, _ = shape_cache.get_response_fields(service, operation_name)
    default_columns = get_default_columns(service, normalize_action_name(action)) or []

    return {
        "service": service,
        "action": to_kebab_case(operation_name),
        "operation": operation_name,
        "readonly": is_readonly_operation(operation_name),
        "paginated": _is_paginated(service, operation_name),
        "data_field": data_field,
        "input": {"required": required, "parameters": parameters},
        "default_columns": list(default_columns),
        "filter_hint": FILTER_HINT,
        "output_fields": dict(sorted(output_fields.items())),
    }


def _pad(text: str, width: int) -> str:
    """Pad to width, always keeping at least one space after an oversized value."""
    return text.ljust(width) if len(text) < width else text + " "


def _column_width(values, minimum: int, maximum: int = MAX_NAME_WIDTH) -> int:
    """Width that fits the longest value plus a separator, within bounds."""
    if not values:
        return minimum
    return max(minimum, min(max(len(value) for value in values) + 2, maximum))


def _format_schema_text(schema: Dict[str, Any]) -> str:
    """Render a schema dict as the human-readable text form."""
    flags = "readonly" if schema["readonly"] else "not readonly"
    flags += ", paginated" if schema["paginated"] else ", not paginated"
    lines = [f"{schema['service']} {schema['action']} ({flags})", ""]

    parameters = schema["input"]["parameters"]
    required = schema["input"]["required"]
    lines.append("Input parameters:")
    if parameters:
        name_width = _column_width(parameters.keys(), MIN_NAME_WIDTH)
        type_width = _column_width(parameters.values(), MIN_TYPE_WIDTH)
        for name, type_name in parameters.items():
            marker = "required" if name in required else "optional"
            lines.append(f"  {_pad(name, name_width)}{_pad(type_name, type_width)}{marker}")
    else:
        lines.append("  none")
    lines.append(f"Required: {', '.join(required) if required else 'none'}")

    if schema["default_columns"]:
        lines.extend(["", f"Default columns: {' '.join(schema['default_columns'])}"])

    output_fields = schema["output_fields"]
    lines.extend(["", schema["filter_hint"], f"Output fields ({len(output_fields)}):"])
    name_width = _column_width(output_fields.keys(), MIN_NAME_WIDTH)
    for name, type_name in output_fields.items():
        lines.append(f"  {_pad(name, name_width)}{type_name}")

    return "\n".join(lines)


def print_schema(service: str, action: str, as_json: bool = False) -> None:
    """Print an operation's input/output contract."""
    schema = build_schema(service, action)
    print(json.dumps(schema, indent=2) if as_json else _format_schema_text(schema))
