"""Core AWS operations for AWS Query Tool."""

import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from .case_utils import to_pascal_case, to_snake_case
from .filters import extract_parameter_values, filter_resources
from .utils import (
    convert_parameter_name,
    create_session,
    debug_print,
    get_client,
    normalize_action_name,
)


class CallResult:
    """Track successful responses throughout call chain"""

    def __init__(self, service: str = "", operation: str = "") -> None:
        """Initialize CallResult with tracking lists."""
        self.successful_responses: List[Any] = []
        self.final_success: bool = False
        self.last_successful_response: Optional[Any] = None
        self.error_messages: List[str] = []
        self.service: str = service
        self.operation: str = operation


def check_parameter_requirements(
    service: str, action: str, provided_params: Dict[str, Any], session=None
) -> Dict[str, Any]:
    """Check if operation needs parameters that weren't provided.

    Uses boto3 service model to determine:
    1. Strict required parameters (always needed)
    2. Conditional requirements (either/or scenarios)
    3. Which required parameters are missing

    Args:
        service: AWS service name (e.g., 'ec2', 'ssm')
        action: Operation name (e.g., 'describe-instances', 'get-parameters')
        provided_params: Parameters provided by user via -p flag
        session: Optional boto3 session

    Returns:
        dict: {
            'needs_params': bool,           # True if missing required params
            'required': List[str],          # List of strict required param names
            'conditional': str or None,     # Conditional requirement hint from docs
            'missing_required': List[str]   # Required params not provided
        }
    """
    try:
        client = get_client(service, session)
        normalized_action = normalize_action_name(action)

        operation_model = client.meta.service_model.operation_model(normalized_action)
        input_shape = operation_model.input_shape

        required = []
        if input_shape and hasattr(input_shape, "required_members"):
            required = list(input_shape.required_members)

        missing_required = [p for p in required if p not in provided_params]

        conditional_hint = None
        if not required and not provided_params:
            doc = operation_model.documentation if hasattr(operation_model, "documentation") else ""
            conditional_hint = _extract_conditional_requirement(doc)

        debug_print(
            f"Parameter requirements check: required={required}, "
            f"missing={missing_required}, conditional={'Yes' if conditional_hint else 'No'}"
        )

        return {
            "needs_params": len(missing_required) > 0,
            "required": required,
            "conditional": conditional_hint,
            "missing_required": missing_required,
        }

    except Exception as e:
        debug_print(f"Error checking parameter requirements: {e}")
        return {
            "needs_params": False,
            "required": [],
            "conditional": None,
            "missing_required": [],
        }


def _extract_conditional_requirement(documentation: str) -> Optional[str]:
    """Extract conditional requirement hint from operation documentation.

    Looks for patterns like:
    - "must specify either X or Y"
    - "at least one of X, Y, or Z"
    - "required if"

    Args:
        documentation: Operation documentation string

    Returns:
        Extracted requirement sentence or None
    """
    if not documentation:
        return None

    patterns = [
        r"must specify (either|one of)",
        r"either .* or .*",
        r"at least one of",
        r"required if",
        r"one of the following",
    ]

    for pattern in patterns:
        if re.search(pattern, documentation, re.IGNORECASE):
            sentences = documentation.split(".")
            for sentence in sentences:
                if re.search(pattern, sentence, re.IGNORECASE):
                    clean_sentence = re.sub(r"<[^>]+>", "", sentence.strip())
                    return clean_sentence
            break

    return None


def execute_with_tracking(service, action, parameters=None, session=None):
    """Execute AWS call with tracking for keys mode"""
    result = CallResult()

    try:
        response = execute_aws_call(service, action, parameters, session)

        # Check if response indicates a validation error (for multi-level calls)
        if isinstance(response, dict) and "validation_error" in response:
            result.final_success = False
            result.error_messages.append(f"Validation error: {response['validation_error']}")
        else:
            # Successful response
            result.successful_responses.append(response)
            result.last_successful_response = response
            result.final_success = True
            debug_print(f"Tracking: Successful call to {service}.{action}")  # pragma: no mutate
    except Exception as e:
        result.final_success = False
        result.error_messages.append(f"Call failed: {str(e)}")
        debug_print(f"Tracking: Failed call to {service}.{action}: {e}")  # pragma: no mutate

    return result


def execute_aws_call(service, action, parameters=None, session=None):
    """Execute AWS API call with pagination support and optional parameters"""
    normalized_action = normalize_action_name(action)

    try:
        client = get_client(service, session)
        operation = getattr(client, normalized_action, None)

        if not operation:
            operation = getattr(client, action, None)
            if not operation:
                raise ValueError(
                    f"Action {action} (normalized: {normalized_action}) "
                    f"not available for service {service}"
                )

        call_params = parameters or {}

        # Try pagination first, fall back to direct call
        try:
            paginator = client.get_paginator(normalized_action)
            results = []
            for page in paginator.paginate(**call_params):
                results.append(page)
            return results
        except Exception as e:
            # Check for specific error types
            if "OperationNotPageableError" in str(type(e)):
                debug_print(
                    f"Operation not pageable, falling back to direct call"
                )  # pragma: no mutate
                return [operation(**call_params)]
            elif type(e).__name__ == "ParamValidationError" or (
                isinstance(e, ClientError)
                and hasattr(e, "response")
                and e.response.get("Error", {}).get("Code")  # pylint: disable=no-member
                in ["ValidationException", "ValidationError"]
            ):
                debug_print(
                    f"Validation error during pagination, re-raising: {e}"
                )  # pragma: no mutate
                raise e
            else:
                debug_print(
                    f"Pagination failed ({type(e).__name__}), falling back to direct call"
                )  # pragma: no mutate
                return [operation(**call_params)]

    except NoCredentialsError:
        print("ERROR: AWS credentials not found. Configure credentials first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if type(e).__name__ == "ParamValidationError":
            error_info = parse_validation_error(e)
            if error_info:
                return {"validation_error": error_info, "original_error": e}
            else:
                print(f"ERROR: Could not parse parameter validation error: {e}", file=sys.stderr)
                sys.exit(1)

        if isinstance(e, ClientError):
            error_info = parse_validation_error(e)
            if error_info:
                return {"validation_error": error_info, "original_error": e}
            else:
                print(f"ERROR: AWS API call failed: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def _execute_multi_level_call_internal(
    service: str,
    action: str,
    resource_filters: List[str],
    value_filters: List[str],
    column_filters: List[str],
    session: Optional[Any] = None,
    hint_function: Optional[str] = None,
    hint_field: Optional[str] = None,
    limit: Optional[int] = None,
    with_tracking: bool = False,
    user_parameters: Optional[dict] = None,
    hint_service: Optional[str] = None,
) -> Union[Tuple[Optional[CallResult], List[Any]], List[Any]]:
    """Unified implementation for multi-level calls with optional tracking"""
    debug_print(f"Starting multi-level call for {service}.{action}")  # pragma: no mutate
    debug_print(
        f"Resource filters: {resource_filters}, "  # pragma: no mutate
        f"Value filters: {value_filters}, Column filters: {column_filters}"  # pragma: no mutate
    )  # pragma: no mutate
    if user_parameters:
        debug_print(f"User-provided parameters: {user_parameters}")  # pragma: no mutate

    # Apply default limit if not specified
    if limit is None:
        limit = 10
        debug_print(f"Applying default multi-step result limit: {limit}")  # pragma: no mutate
    elif limit == 0:
        limit = None  # 0 means unlimited
        debug_print("Result limit set to unlimited (0)")  # pragma: no mutate
    else:
        debug_print(f"Using specified result limit: {limit}")  # pragma: no mutate

    call_result = CallResult(service, action) if with_tracking else None

    # First attempt - main call
    response = None
    try:
        response = execute_aws_call(service, action, parameters=None, session=session)

        if isinstance(response, dict) and "validation_error" in response:
            if with_tracking and call_result is not None:
                call_result.error_messages.append(
                    f"Initial call validation error: {response['validation_error']}"
                )
            error_info = response["validation_error"]
            parameter_name = error_info["parameter_name"]
            debug_print(
                f"Validation error - missing parameter: {parameter_name}"
            )  # pragma: no mutate
        else:
            # Initial call succeeded
            if with_tracking and call_result is not None:
                call_result.successful_responses.append(response)
                call_result.last_successful_response = response
                call_result.final_success = True
                debug_print(
                    f"Tracking: Initial call to {service}.{action} succeeded"
                )  # pragma: no mutate

            from .formatters import flatten_response

            resources = flatten_response(response, service, action)
            debug_print(f"Final call returned {len(resources)} resources")  # pragma: no mutate

            if value_filters:
                filtered_resources = filter_resources(resources, value_filters)
                debug_print(
                    f"After value filtering: {len(filtered_resources)} resources"
                )  # pragma: no mutate
            else:
                filtered_resources = resources

            return (call_result, filtered_resources) if with_tracking else filtered_resources

    except Exception as e:
        if with_tracking and call_result is not None:
            call_result.error_messages.append(f"Initial call failed: {str(e)}")
        debug_print(f"Initial call failed: {e}")  # pragma: no mutate

    # Multi-level resolution needed
    if response and isinstance(response, dict) and "validation_error" in response:
        error_info = response["validation_error"]
        parameter_name = error_info["parameter_name"]
        debug_print(f"Validation error - missing parameter: {parameter_name}")  # pragma: no mutate

        print(f"Resolving required parameter '{parameter_name}'", file=sys.stderr)

        # Determine which service to use for list operation
        list_service = hint_service if hint_service else service

        # Show cross-service message if using different service
        if hint_service and hint_service != service:
            debug_print(
                f"Cross-service resolution: using {hint_service} service for list operation "
                f"(target service is {service})"
            )  # pragma: no mutate

            if hint_function:
                from .case_utils import to_kebab_case

                hint_function_cli = to_kebab_case(hint_function)
                print(
                    f"Using cross-service hint: {hint_service}:{hint_function_cli}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Using service '{hint_service}' for parameter resolution "
                    "(operation will be inferred)",
                    file=sys.stderr,
                )

        # Use hint function if provided
        if hint_function:
            hint_normalized = normalize_action_name(hint_function)
            possible_operations = [hint_normalized]
            # Convert hint function to CLI format for display
            from .case_utils import to_kebab_case

            hint_function_cli = to_kebab_case(hint_function)
            if not hint_service or hint_service == service:
                print(
                    f"Using hint function '{hint_function_cli}' for parameter resolution",
                    file=sys.stderr,
                )
        else:
            # Infer operations from the hint_service (if provided) or current service
            possible_operations = infer_list_operation(
                list_service, parameter_name, action, session
            )

        list_response = None
        successful_operation = None

        for operation in possible_operations:
            try:
                debug_print(
                    f"Trying list operation: {list_service}.{operation}"
                )  # pragma: no mutate
                print(
                    f"Calling {list_service}.{operation} to find available resources...",
                    file=sys.stderr,
                )

                # Filter user parameters for this list operation
                list_params = filter_valid_parameters(
                    list_service, operation, user_parameters or {}, session
                )
                if list_params:
                    debug_print(
                        f"Applying user parameters to list operation {operation}: {list_params}"
                    )  # pragma: no mutate

                list_response = execute_aws_call(
                    list_service,
                    operation,
                    parameters=list_params if list_params else None,
                    session=session,
                )

                if isinstance(list_response, list) and list_response:
                    successful_operation = operation
                    debug_print(f"Successfully executed: {operation}")  # pragma: no mutate
                    if with_tracking and call_result is not None:
                        call_result.successful_responses.append(list_response)
                    break

            except Exception as e:
                debug_print(f"Operation {operation} failed: {e}")  # pragma: no mutate
                continue

        if not list_response or not successful_operation:
            error_msg = f"Could not find working list operation for parameter '{parameter_name}'"

            print(f"ERROR: {error_msg}", file=sys.stderr)
            print(f"Tried operations: {possible_operations}", file=sys.stderr)
            print("", file=sys.stderr)
            print(
                f"Suggestion: Use the -i/--input flag to specify a hint:",
                file=sys.stderr,
            )
            print(
                f"  Specify function: awsquery {service} {action} -i describe-param",
                file=sys.stderr,
            )
            print(
                f"  Use another service: awsquery {service} {action} -i ec2",
                file=sys.stderr,
            )
            print(
                f"  Cross-service with function: "
                f"awsquery {service} {action} -i ec2:describe-instances",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
            print(f"Available operations for '{service}' can be viewed with:", file=sys.stderr)
            print(f"  aws {service} help", file=sys.stderr)

            if with_tracking and call_result is not None:
                call_result.error_messages.append(error_msg)
                return call_result, []
            else:
                sys.exit(1)

        from .formatters import flatten_response

        list_resources = flatten_response(list_response, list_service, successful_operation)
        debug_print(
            f"Got {len(list_resources)} resources from {successful_operation}"
        )  # pragma: no mutate

        if resource_filters:
            filtered_list_resources = filter_resources(list_resources, resource_filters)
            debug_print(
                f"After resource filtering: {len(filtered_list_resources)} resources"
            )  # pragma: no mutate
        else:
            filtered_list_resources = list_resources

        # Apply result limit
        if limit and len(filtered_list_resources) > limit:
            debug_print(
                f"Limiting results from {len(filtered_list_resources)} to {limit}"
            )  # pragma: no mutate
            filtered_list_resources = filtered_list_resources[:limit]
            print(f"Limited to first {limit} resources (use -i ::N to adjust)", file=sys.stderr)

        print(f"Found {len(filtered_list_resources)} resources matching filters", file=sys.stderr)

        if not filtered_list_resources:
            error_msg = f"No resources found matching resource filters: {resource_filters}"
            if with_tracking and call_result is not None:
                call_result.error_messages.append(error_msg)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return call_result, []
            else:
                print(f"ERROR: {error_msg}", file=sys.stderr)
                sys.exit(1)

        # Singularize parameter name for better field matching
        singular_name = singularize_parameter_name(parameter_name)
        debug_print(
            f"Parameter '{parameter_name}' singularized to '{singular_name}' for field matching"
        )  # pragma: no mutate

        parameter_values = extract_parameter_values(
            filtered_list_resources, parameter_name, hint_field, singular_name
        )

        if not parameter_values:
            error_msg = f"Could not extract parameter '{parameter_name}' from filtered results"
            if with_tracking and call_result is not None:
                call_result.error_messages.append(error_msg)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return call_result, []
            else:
                print(f"ERROR: {error_msg}", file=sys.stderr)
                sys.exit(1)

        expects_list = parameter_expects_list(parameter_name)

        if expects_list:
            param_value = parameter_values
        else:
            if len(parameter_values) > 1:
                print(f"Multiple {parameter_name} values found matching filters:", file=sys.stderr)
                display_values = parameter_values[:10]
                for value in display_values:
                    print(f"- {value}", file=sys.stderr)

                if len(parameter_values) > 10:
                    remaining = len(parameter_values) - 10
                    print(
                        f"... and {remaining} more "
                        f"(showing first 10 of {len(parameter_values)} total)",
                        file=sys.stderr,
                    )

                print(f"Using first match: {parameter_values[0]}", file=sys.stderr)
            elif len(parameter_values) == 1:
                print(f"Using: {parameter_values[0]}", file=sys.stderr)

            param_value = parameter_values[0]

        debug_print(f"Using parameter value(s): {param_value}")  # pragma: no mutate

        try:
            client = get_client(service, session)
            converted_parameter_name = get_correct_parameter_name(client, action, parameter_name)
            debug_print(
                f"Parameter name resolution: {parameter_name} -> {converted_parameter_name}"
            )  # pragma: no mutate
        except Exception as e:
            debug_print(
                f"Could not create client for parameter introspection: {e}"
            )  # pragma: no mutate
            converted_parameter_name = convert_parameter_name(parameter_name)
            debug_print(
                f"Fallback parameter name conversion: "
                f"{parameter_name} -> {converted_parameter_name}"
            )  # pragma: no mutate

        parameters = {converted_parameter_name: param_value}

        # Merge user parameters with auto-resolved parameter
        if user_parameters:
            final_params = filter_valid_parameters(service, action, user_parameters, session)
            # User parameters should not override auto-resolved ones
            for key, value in final_params.items():
                if key not in parameters:
                    parameters[key] = value
            if final_params:
                debug_print(
                    f"Merged user parameters with resolved: {parameters}"
                )  # pragma: no mutate

        # Final call with resolved parameters
        try:
            final_response = execute_aws_call(service, action, parameters, session)

            if isinstance(final_response, dict) and "validation_error" in final_response:
                error_msg = (
                    f"Still getting validation error after parameter resolution: "
                    f"{final_response['validation_error']}"
                )
                if with_tracking and call_result is not None:
                    call_result.error_messages.append(error_msg)
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    return call_result, []
                else:
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    sys.exit(1)
            else:
                # Final call succeeded
                response = final_response
                if with_tracking and call_result is not None:
                    call_result.successful_responses.append(final_response)
                    call_result.last_successful_response = final_response
                    call_result.final_success = True
                    debug_print(
                        f"Tracking: Final call to {service}.{action} succeeded"
                    )  # pragma: no mutate

        except Exception as e:
            if with_tracking and call_result is not None:
                call_result.error_messages.append(f"Final call failed: {str(e)}")
                debug_print(f"Final call failed: {e}")  # pragma: no mutate
                return call_result, []
            else:
                debug_print(f"Final call failed: {e}")  # pragma: no mutate
                sys.exit(1)

    # Process final response
    final_response_to_use = (
        call_result.last_successful_response
        if with_tracking and call_result is not None
        else response
    )
    if final_response_to_use:
        from .formatters import flatten_response

        resources = flatten_response(final_response_to_use, service, action)
        debug_print(f"Final call returned {len(resources)} resources")  # pragma: no mutate

        if value_filters:
            filtered_resources = filter_resources(resources, value_filters)
            debug_print(
                f"After value filtering: {len(filtered_resources)} resources"
            )  # pragma: no mutate
        else:
            filtered_resources = resources

        return (call_result, filtered_resources) if with_tracking else filtered_resources
    else:
        return (call_result, []) if with_tracking else []


def execute_multi_level_call_with_tracking(
    service,
    action,
    resource_filters,
    value_filters,
    column_filters,
    session=None,
    hint_function=None,
    hint_field=None,
    limit=None,
    user_parameters=None,
    hint_service=None,
):
    """Handle multi-level API calls with automatic parameter resolution and tracking"""
    return _execute_multi_level_call_internal(
        service,
        action,
        resource_filters,
        value_filters,
        column_filters,
        session,
        hint_function,
        hint_field,
        limit,
        with_tracking=True,
        user_parameters=user_parameters,
        hint_service=hint_service,
    )


def execute_multi_level_call(
    service,
    action,
    resource_filters,
    value_filters,
    column_filters,
    session=None,
    hint_function=None,
    hint_field=None,
    limit=None,
    user_parameters=None,
    hint_service=None,
):
    """Handle multi-level API calls with automatic parameter resolution"""
    return _execute_multi_level_call_internal(
        service,
        action,
        resource_filters,
        value_filters,
        column_filters,
        session,
        hint_function,
        hint_field,
        limit,
        with_tracking=False,
        user_parameters=user_parameters,
        hint_service=hint_service,
    )


def parse_validation_error(error):
    """Extract missing parameter info from ValidationError"""
    error_message = str(error)

    pattern = r"Value null at '([^']+)'"
    match = re.search(pattern, error_message)

    if match:
        parameter_name = match.group(1)
        return {"parameter_name": parameter_name, "is_required": True, "error_type": "null_value"}

    pattern = r"'([^']+)'[^:]*: Member must not be null"
    match = re.search(pattern, error_message)

    if match:
        parameter_name = match.group(1)
        return {
            "parameter_name": parameter_name,
            "is_required": True,
            "error_type": "required_parameter",
        }

    pattern = r"Either (\w+) or \w+ must be specified"
    match = re.search(pattern, error_message)

    if match:
        parameter_name = match.group(1)
        return {
            "parameter_name": parameter_name,
            "is_required": True,
            "error_type": "either_parameter",
        }

    pattern = r"Missing required parameter in input: ['\"]([^'\"]+)['\"]"
    match = re.search(pattern, error_message)

    if match:
        parameter_name = match.group(1)
        return {
            "parameter_name": parameter_name,
            "is_required": True,
            "error_type": "missing_parameter",
        }

    debug_print(f"Could not parse validation error: {error_message}")  # pragma: no mutate

    return None


def infer_list_operation(service, parameter_name, action, session=None):
    """Infer the list operation from parameter name first, then action name as fallback.

    NEW: Now validates that inferred operations actually exist in the service.
    """
    possible_operations = []

    # Skip parameter-based inference for generic AWS parameter names
    # These are too ambiguous to infer specific resource types from
    if parameter_name.lower() not in [
        "name",
        "id",
        "arn",
        "identifier",
        "names",
        "ids",
        "arns",
        "identifiers",
    ]:
        resource_name = parameter_name
        # Try plural suffixes first (longer matches), then singular
        suffixes_to_remove = [
            "Identifiers",
            "Names",
            "Ids",
            "Arns",
            "ARNs",
            "Identifier",
            "Name",
            "Id",
            "Arn",
            "ARN",
        ]
        for suffix in suffixes_to_remove:
            if resource_name.endswith(suffix):
                resource_name = resource_name[: -len(suffix)]
                break

        # Convert camelCase to snake_case to preserve word boundaries
        resource_name = to_snake_case(resource_name)

        # Pluralization rules
        if resource_name.endswith("y"):
            # Check if preceded by a vowel
            if len(resource_name) >= 2 and resource_name[-2] in "aeiou":
                # vowel + y → add s (gateway → gateways)
                plural_name = resource_name + "s"
            else:
                # consonant + y → change to ies (policy → policies)
                plural_name = resource_name[:-1] + "ies"
        elif resource_name.endswith(("s", "sh", "ch", "x", "z")):
            plural_name = resource_name + "es"
        else:
            plural_name = resource_name + "s"

        possible_operations.extend(
            [
                f"list_{plural_name}",
                f"describe_{plural_name}",
                f"get_{plural_name}",
                f"list_{resource_name}",
                f"describe_{resource_name}",
                f"get_{resource_name}",
            ]
        )

        debug_print(
            f"Parameter-based inference: '{parameter_name}' -> '{resource_name}' -> "
            f"{len(possible_operations)} operations"
        )  # pragma: no mutate
    else:
        debug_print(
            f"Parameter '{parameter_name}' is too generic, skipping parameter-based inference"
        )  # pragma: no mutate

    prefixes = ["describe", "get", "read", "update", "delete", "create", "list"]
    # Convert action to snake_case if it's camelCase, or handle kebab-case
    if "-" in action:
        action_snake = action.lower().replace("-", "_")
    else:
        # CamelCase action - convert to snake_case
        action_snake = to_snake_case(action)

    action_resource = action_snake
    for prefix in prefixes:
        if action_snake.startswith(prefix + "_"):
            action_resource = action_snake[len(prefix) + 1 :]
            break

    # Pluralization (same rules as resource_name)
    if action_resource.endswith("s") and len(action_resource) > 1:
        action_plural = action_resource
    elif action_resource.endswith("y"):
        # Check if preceded by a vowel
        if len(action_resource) >= 2 and action_resource[-2] in "aeiou":
            action_plural = action_resource + "s"
        else:
            action_plural = action_resource[:-1] + "ies"
    elif action_resource.endswith(("sh", "ch", "x", "z")):
        action_plural = action_resource + "es"
    else:
        action_plural = action_resource + "s"

    action_operations = [
        f"list_{action_plural}",
        f"describe_{action_plural}",
        f"get_{action_plural}",
        f"list_{action_resource}",
        f"describe_{action_resource}",
        f"get_{action_resource}",
    ]

    for op in action_operations:
        if op not in possible_operations:
            possible_operations.append(op)

    debug_print(
        f"Action-based inference: '{action}' -> '{action_resource}' -> "
        f"added {len(action_operations)} operations"
    )  # pragma: no mutate

    validated_operations = []

    try:
        client = get_client(service, session)
        service_model = client.meta.service_model
        valid_operation_names = set(service_model.operation_names)

        for op in possible_operations:
            pascal_op = to_pascal_case(op)

            if pascal_op in valid_operation_names:
                validated_operations.append(op)
                debug_print(
                    f"✓ Validated operation exists: {op} -> {pascal_op}"
                )  # pragma: no mutate
            else:
                debug_print(f"✗ Operation does not exist: {op} -> {pascal_op}")  # pragma: no mutate

        if not validated_operations:
            debug_print(
                f"WARNING: None of the inferred operations exist in service '{service}'"
            )  # pragma: no mutate
            debug_print(f"Tried: {possible_operations}")  # pragma: no mutate
            debug_print(
                "Falling back to unvalidated list - will attempt execution anyway"
            )  # pragma: no mutate
            return possible_operations

    except Exception as e:
        debug_print(
            f"Could not validate operations: {e}. Returning all inferred operations."
        )  # pragma: no mutate
        return possible_operations

    debug_print(f"Validated operations: {validated_operations}")  # pragma: no mutate
    return validated_operations


def singularize_parameter_name(param_name):
    """Convert plural parameter name to singular form.

    Handles common AWS parameter name patterns:
    - Names -> Name, Ids -> Id, Arns -> Arn, etc.
    - Policies -> Policy, Entries -> Entry (ies -> y)
    - Addresses -> Address, Caches -> Cache (es -> "")

    Args:
        param_name: Parameter name (may be plural)

    Returns:
        Singularized parameter name
    """
    if not param_name:
        return param_name

    # Handle special plural suffixes
    # Check longer patterns first to avoid incorrect matches

    # sses -> ss (Addresses -> Address)
    if param_name.endswith("sses"):
        return param_name[:-2]

    # ies -> y (Policies -> Policy, Entries -> Entry)
    if param_name.endswith("ies") and len(param_name) > 3:
        return param_name[:-3] + "y"

    # Common AWS patterns: Names, Ids, Arns, Keys, Groups, Users
    # Check if ends with 's' but preserve acronyms like ARNs
    if param_name.endswith("ARNs"):
        return param_name[:-1]  # ARNs -> ARN

    # Standard plurals ending in 's'
    common_plurals = ["Names", "Ids", "Arns", "Keys", "Groups", "Users", "Items", "Values"]
    for plural in common_plurals:
        if param_name.endswith(plural):
            return param_name[:-1]

    # es -> e for words ending in specific patterns (ches, shes, xes, zes)
    if (
        param_name.endswith("ches")
        or param_name.endswith("shes")
        or param_name.endswith("xes")
        or param_name.endswith("zes")
    ):
        return param_name[:-1]  # Caches -> Cache, Boxes -> Boxe

    # es -> "" for other words ending in 'es'
    if param_name.endswith("es") and len(param_name) > 2 and not param_name.endswith("ies"):
        # Check if it's likely plural (Addresses -> Address, not Status -> Statu)
        # Simple heuristic: if penultimate char is not a vowel, remove 'es'
        if param_name[-3] not in "aeiou":
            return param_name[:-2]

    # Generic 's' removal for other standard plurals
    if param_name.endswith("s") and len(param_name) > 1:
        # Don't singularize words that end in 'ss' or 'us' (Status, Class, etc.)
        if not param_name.endswith("ss") and not param_name.endswith("us"):
            return param_name[:-1]

    return param_name


def parameter_expects_list(parameter_name):
    """Determine if parameter expects list or single value"""
    list_indicators = ["s", "Names", "Ids", "Arns", "ARNs"]

    for indicator in list_indicators:
        if parameter_name.endswith(indicator):
            return True

    return False


def filter_valid_parameters(service, action, parameters, session=None):
    """Filter parameters to only those valid for the given operation.

    Args:
        service: AWS service name (e.g., 'ssm', 'ec2')
        action: Operation name (e.g., 'describe-parameters')
        parameters: Dict of parameter names and values
        session: Optional boto3 session

    Returns:
        Dict containing only parameters valid for this operation
    """
    if not parameters:
        debug_print("filter_valid_parameters: No parameters to filter")  # pragma: no mutate
        return {}

    try:
        if session is None:
            session = create_session()

        client = session.client(service)

        # Convert kebab-case action to PascalCase for boto3
        pascal_case_action = to_pascal_case(action.replace("-", "_"))

        operation_model = client.meta.service_model.operation_model(pascal_case_action)
        input_shape = operation_model.input_shape

        if not input_shape:
            debug_print(
                f"filter_valid_parameters: No input shape for {service}.{action}"
            )  # pragma: no mutate
            return {}

        # Build case-insensitive lookup map once (O(m) instead of O(n*m))
        lowercase_member_map = {name.lower(): name for name in input_shape.members}

        valid_params = {}
        invalid_params = []

        for param_name, param_value in parameters.items():
            # Try exact match first (O(1))
            if param_name in input_shape.members:
                valid_params[param_name] = param_value
                debug_print(
                    f"filter_valid_parameters: '{param_name}' is valid for {action}"
                )  # pragma: no mutate
            # Try case-insensitive lookup (O(1))
            elif param_name.lower() in lowercase_member_map:
                correct_name = lowercase_member_map[param_name.lower()]
                debug_print(
                    f"Parameter case correction: '{param_name}' -> '{correct_name}'"
                )  # pragma: no mutate
                valid_params[correct_name] = param_value
                debug_print(
                    f"filter_valid_parameters: '{correct_name}' is valid for {action}"
                )  # pragma: no mutate
            else:
                invalid_params.append(param_name)
                debug_print(
                    f"filter_valid_parameters: '{param_name}' is NOT valid for {action}"
                )  # pragma: no mutate

        if invalid_params:
            debug_print(
                f"filter_valid_parameters: Filtered out invalid parameters for "
                f"{action}: {invalid_params}"
            )  # pragma: no mutate

        debug_print(
            f"filter_valid_parameters: Returning {len(valid_params)} valid parameters "
            f"for {action}"
        )  # pragma: no mutate

        return valid_params

    except Exception as e:
        debug_print(
            f"filter_valid_parameters: Error filtering parameters for " f"{service}.{action}: {e}"
        )  # pragma: no mutate
        return {}


def get_correct_parameter_name(client, action, parameter_name):
    """Get the correct case-sensitive parameter name for an operation.

    By introspecting the service model.
    """
    try:
        pascal_case_action = to_pascal_case(action.replace("-", "_"))

        operation_model = client.meta.service_model.operation_model(pascal_case_action)

        debug_print(
            f"Introspecting parameter name for {action} (PascalCase: {pascal_case_action})"
        )  # pragma: no mutate

        if operation_model.input_shape:
            members = operation_model.input_shape.members
            debug_print(f"Available parameters: {list(members.keys())}")  # pragma: no mutate

            if parameter_name in members:
                debug_print(f"Found exact match: {parameter_name}")  # pragma: no mutate
                return parameter_name

            for member_name in members:
                if member_name.lower() == parameter_name.lower():
                    debug_print(
                        f"Found case-insensitive match: {parameter_name} -> {member_name}"
                    )  # pragma: no mutate
                    return member_name

            pascal_case = parameter_name[0].upper() + parameter_name[1:]
            if pascal_case in members:
                debug_print(
                    f"Found PascalCase match: {parameter_name} -> {pascal_case}"
                )  # pragma: no mutate
                return pascal_case

            debug_print(
                f"No parameter match found for '{parameter_name}' in {list(members.keys())}"
            )  # pragma: no mutate
        else:
            debug_print(f"Operation {pascal_case_action} has no input shape")  # pragma: no mutate

        debug_print(f"Using original parameter name: {parameter_name}")  # pragma: no mutate
        return parameter_name

    except Exception as e:
        debug_print(f"Could not introspect parameter name: {e}")  # pragma: no mutate
        fallback = convert_parameter_name(parameter_name)
        debug_print(
            f"Falling back to PascalCase: {parameter_name} -> {fallback}"
        )  # pragma: no mutate
        return fallback


def show_keys_from_result(call_result):
    """Show keys only if final call succeeded"""
    if call_result.final_success and call_result.last_successful_response:
        from .formatters import extract_and_sort_keys, flatten_response

        resources = flatten_response(
            call_result.last_successful_response, call_result.service, call_result.operation
        )
        if not resources:
            return "Error: No data to extract keys from in successful response"

        # Use non-simplified keys to show full nested structure
        sorted_keys = extract_and_sort_keys(resources, simplify=False)
        return "\n".join(f"  {key}" for key in sorted_keys)
    else:
        if call_result.error_messages:
            error_msg = "; ".join(call_result.error_messages)
            return f"Error: No successful response to show keys from ({error_msg})"
        else:
            return "Error: No successful response to show keys from"
