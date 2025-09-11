"""Core AWS operations for AWS Query Tool."""

import sys
import re
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from .utils import debug_print, normalize_action_name
from .filters import filter_resources, extract_parameter_values


def execute_aws_call(service, action, dry_run=False, parameters=None):
    """Execute AWS API call with pagination support and optional parameters"""
    normalized_action = normalize_action_name(action)

    if dry_run:
        params_str = f" with parameters {parameters}" if parameters else ""
        print(
            f"DRY RUN: Would execute {service}.{normalized_action}(){params_str}", file=sys.stderr
        )
        return []

    try:
        client = boto3.client(service)
        operation = getattr(client, normalized_action, None)

        if not operation:
            operation = getattr(client, action, None)
            if not operation:
                raise ValueError(
                    f"Action {action} (normalized: {normalized_action}) not available for service {service}"
                )

        call_params = parameters or {}

        try:
            paginator = client.get_paginator(normalized_action)
            results = []
            for page in paginator.paginate(**call_params):
                results.append(page)
            return results
        except Exception as e:
            exception_name = type(e).__name__
            debug_print(f"Pagination exception type: {exception_name}, message: {e}")

            if exception_name == "OperationNotPageableError":
                debug_print(f"Operation not pageable, falling back to direct call")
                return [operation(**call_params)]
            elif exception_name == "ParamValidationError":
                debug_print(f"ParamValidationError detected during pagination, re-raising")
                raise e
            elif isinstance(e, ClientError):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ["ValidationException", "ValidationError"]:
                    debug_print(
                        f"ValidationError ({error_code}) detected during pagination, re-raising"
                    )
                    raise e
                else:
                    debug_print(
                        f"ClientError ({error_code}) during pagination, falling back to direct call"
                    )
                    return [operation(**call_params)]
            else:
                debug_print(f"Unknown pagination error, falling back to direct call")
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


def execute_multi_level_call(
    service, action, resource_filters, value_filters, column_filters, dry_run=False
):
    """Handle multi-level API calls with automatic parameter resolution"""
    debug_print(f"Starting multi-level call for {service}.{action}")
    debug_print(
        f"Resource filters: {resource_filters}, Value filters: {value_filters}, Column filters: {column_filters}"
    )

    response = execute_aws_call(service, action, dry_run)

    if isinstance(response, dict) and "validation_error" in response:
        error_info = response["validation_error"]
        parameter_name = error_info["parameter_name"]

        debug_print(f"Validation error - missing parameter: {parameter_name}")

        print(f"Resolving required parameter '{parameter_name}'", file=sys.stderr)

        possible_operations = infer_list_operation(service, parameter_name, action)

        list_response = None
        successful_operation = None

        for operation in possible_operations:
            try:
                debug_print(f"Trying list operation: {operation}")

                print(f"Calling {operation} to find available resources...", file=sys.stderr)

                list_response = execute_aws_call(service, operation, dry_run)

                if isinstance(list_response, list) and list_response:
                    successful_operation = operation
                    debug_print(f"Successfully executed: {operation}")
                    break

            except Exception as e:
                debug_print(f"Operation {operation} failed: {e}")
                continue

        if not list_response or not successful_operation:
            print(
                f"ERROR: Could not find a working list operation for parameter '{parameter_name}'",
                file=sys.stderr,
            )
            print(f"ERROR: Tried operations: {possible_operations}", file=sys.stderr)
            sys.exit(1)

        from .formatters import flatten_response

        list_resources = flatten_response(list_response)
        debug_print(f"Got {len(list_resources)} resources from {successful_operation}")

        if resource_filters:
            filtered_list_resources = filter_resources(list_resources, resource_filters)
            debug_print(f"After resource filtering: {len(filtered_list_resources)} resources")
        else:
            filtered_list_resources = list_resources

        print(f"Found {len(filtered_list_resources)} resources matching filters", file=sys.stderr)

        if not filtered_list_resources:
            print(
                f"ERROR: No resources found matching resource filters: {resource_filters}",
                file=sys.stderr,
            )
            sys.exit(1)

        parameter_values = extract_parameter_values(filtered_list_resources, parameter_name)

        if not parameter_values:
            print(
                f"ERROR: Could not extract parameter '{parameter_name}' from filtered results",
                file=sys.stderr,
            )
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
                        f"... and {remaining} more (showing first 10 of {len(parameter_values)} total)",
                        file=sys.stderr,
                    )

                print(f"Using first match: {parameter_values[0]}", file=sys.stderr)
            elif len(parameter_values) == 1:
                print(f"Using: {parameter_values[0]}", file=sys.stderr)

            param_value = parameter_values[0]

        debug_print(f"Using parameter value(s): {param_value}")

        try:
            client = boto3.client(service)
            converted_parameter_name = get_correct_parameter_name(client, action, parameter_name)
            debug_print(
                f"Parameter name resolution: {parameter_name} -> {converted_parameter_name}"
            )
        except Exception as e:
            debug_print(f"Could not create client for parameter introspection: {e}")
            converted_parameter_name = convert_parameter_name(parameter_name)
            debug_print(
                f"Fallback parameter name conversion: {parameter_name} -> {converted_parameter_name}"
            )

        parameters = {converted_parameter_name: param_value}
        response = execute_aws_call(service, action, dry_run, parameters)

        if isinstance(response, dict) and "validation_error" in response:
            print(
                f"ERROR: Still getting validation error after parameter resolution: {response['validation_error']}",
                file=sys.stderr,
            )
            sys.exit(1)

    from .formatters import flatten_response

    resources = flatten_response(response)
    debug_print(f"Final call returned {len(resources)} resources")

    if value_filters:
        filtered_resources = filter_resources(resources, value_filters)
        debug_print(f"After value filtering: {len(filtered_resources)} resources")
    else:
        filtered_resources = resources

    return filtered_resources


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

    debug_print(f"Could not parse validation error: {error_message}")

    return None


def infer_list_operation(service, parameter_name, action):
    """Infer the list operation from parameter name first, then action name as fallback"""

    possible_operations = []

    if parameter_name.lower() not in ["name", "id", "arn"]:
        resource_name = parameter_name
        suffixes_to_remove = ["Name", "Id", "Arn", "ARN"]
        for suffix in suffixes_to_remove:
            if resource_name.endswith(suffix):
                resource_name = resource_name[: -len(suffix)]
                break

        resource_name = resource_name.lower()

        if resource_name.endswith("y"):
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
            f"Parameter-based inference: '{parameter_name}' -> '{resource_name}' -> {len(possible_operations)} operations"
        )
    else:
        debug_print(
            f"Parameter '{parameter_name}' is too generic, skipping parameter-based inference"
        )

    prefixes = ["describe", "get", "update", "delete", "create", "list"]
    action_lower = action.lower().replace("-", "_")

    action_resource = action_lower
    for prefix in prefixes:
        if action_lower.startswith(prefix + "_"):
            action_resource = action_lower[len(prefix) + 1 :]
            break

    if action_resource.endswith("s") and len(action_resource) > 1:
        action_plural = action_resource
    elif action_resource.endswith("y"):
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
        f"Action-based inference: '{action}' -> '{action_resource}' -> added {len(action_operations)} operations"
    )
    debug_print(f"Total possible operations: {possible_operations}")

    return possible_operations


def parameter_expects_list(parameter_name):
    """Determine if parameter expects list or single value"""
    list_indicators = ["s", "Names", "Ids", "Arns", "ARNs"]

    for indicator in list_indicators:
        if parameter_name.endswith(indicator):
            return True

    return False


def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility"""
    if not parameter_name:
        return parameter_name

    return (
        parameter_name[0].upper() + parameter_name[1:]
        if len(parameter_name) > 0
        else parameter_name
    )


def get_correct_parameter_name(client, action, parameter_name):
    """Get the correct case-sensitive parameter name for an operation by introspecting the service model"""
    try:
        action_words = action.replace("-", "_").replace("_", " ").split()
        pascal_case_action = "".join(word.capitalize() for word in action_words)

        operation_model = client.meta.service_model.operation_model(pascal_case_action)

        debug_print(f"Introspecting parameter name for {action} (PascalCase: {pascal_case_action})")

        if operation_model.input_shape:
            members = operation_model.input_shape.members
            debug_print(f"Available parameters: {list(members.keys())}")

            if parameter_name in members:
                debug_print(f"Found exact match: {parameter_name}")
                return parameter_name

            for member_name in members:
                if member_name.lower() == parameter_name.lower():
                    debug_print(f"Found case-insensitive match: {parameter_name} -> {member_name}")
                    return member_name

            pascal_case = parameter_name[0].upper() + parameter_name[1:]
            if pascal_case in members:
                debug_print(f"Found PascalCase match: {parameter_name} -> {pascal_case}")
                return pascal_case

            debug_print(
                f"No parameter match found for '{parameter_name}' in {list(members.keys())}"
            )
        else:
            debug_print(f"Operation {pascal_case_action} has no input shape")

        debug_print(f"Using original parameter name: {parameter_name}")
        return parameter_name

    except Exception as e:
        debug_print(f"Could not introspect parameter name: {e}")
        fallback = convert_parameter_name(parameter_name)
        debug_print(f"Falling back to PascalCase: {parameter_name} -> {fallback}")
        return fallback
