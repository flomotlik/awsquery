"""
Core AWS operations for AWS Query Tool.

This module contains the core functionality for executing AWS API calls,
handling pagination, parameter resolution, and multi-level API call orchestration.
"""

import sys
import re
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from .utils import debug_print, normalize_action_name
from .filters import filter_resources, extract_parameter_values


def execute_aws_call(service, action, dry_run=False, parameters=None):
    """Execute AWS API call with pagination support and optional parameters"""
    # Normalize the action name for boto3 compatibility
    normalized_action = normalize_action_name(action)
    
    if dry_run:
        params_str = f" with parameters {parameters}" if parameters else ""
        print(f"DRY RUN: Would execute {service}.{normalized_action}(){params_str}", file=sys.stderr)
        return []
    
    try:
        client = boto3.client(service)
        operation = getattr(client, normalized_action, None)
        
        if not operation:
            # Try the original action name as a fallback
            operation = getattr(client, action, None)
            if not operation:
                raise ValueError(f"Action {action} (normalized: {normalized_action}) not available for service {service}")
        
        # Prepare parameters
        call_params = parameters or {}
        
        # Try to get paginator first
        try:
            # Use normalized action for paginator too
            paginator = client.get_paginator(normalized_action)
            results = []
            for page in paginator.paginate(**call_params):
                results.append(page)
            return results
        except Exception as e:
            # Check the exception type
            exception_name = type(e).__name__
            debug_print(f"Pagination exception type: {exception_name}, message: {e}")
            
            # Handle specific exception types
            if exception_name == 'OperationNotPageableError':
                # This operation cannot be paginated - fall back to direct call
                debug_print(f"Operation not pageable, falling back to direct call")
                return [operation(**call_params)]
            elif exception_name == 'ParamValidationError':
                # This is a parameter validation error - let it bubble up to be handled by multi-level logic
                debug_print(f"ParamValidationError detected during pagination, re-raising")
                raise e
            elif isinstance(e, ClientError):
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ['ValidationException', 'ValidationError']:
                    # This is a validation error - let it bubble up to be handled by multi-level logic
                    debug_print(f"ValidationError ({error_code}) detected during pagination, re-raising")
                    raise e
                else:
                    # Other ClientError - fall back to direct call
                    debug_print(f"ClientError ({error_code}) during pagination, falling back to direct call")
                    return [operation(**call_params)]
            else:
                # Unknown exception type - fall back to direct call
                debug_print(f"Unknown pagination error, falling back to direct call")
                return [operation(**call_params)]
    
    except NoCredentialsError:
        print("ERROR: AWS credentials not found. Configure credentials first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Check for ParamValidationError specifically
        if type(e).__name__ == 'ParamValidationError':
            # This is a parameter validation error that we can handle
            error_info = parse_validation_error(e)
            if error_info:
                # Return a special result indicating we need parameter resolution
                return {'validation_error': error_info, 'original_error': e}
            else:
                print(f"ERROR: Could not parse parameter validation error: {e}", file=sys.stderr)
                sys.exit(1)
        # Fall through to other exception handlers
        
        # Check for ClientError
        if isinstance(e, ClientError):
            # Check if this is a validation error that we can handle
            error_info = parse_validation_error(e)
            if error_info:
                # Return a special result indicating we need parameter resolution
                return {'validation_error': error_info, 'original_error': e}
            else:
                print(f"ERROR: AWS API call failed: {e}", file=sys.stderr)
                sys.exit(1)
                
        # Unknown error type
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def execute_multi_level_call(service, action, resource_filters, value_filters, column_filters, dry_run=False):
    """Handle multi-level API calls with automatic parameter resolution"""
    debug_print(f"Starting multi-level call for {service}.{action}")
    debug_print(f"Resource filters: {resource_filters}, Value filters: {value_filters}, Column filters: {column_filters}")
    
    # Try initial call without parameters
    response = execute_aws_call(service, action, dry_run)
    
    # Check if we got a validation error
    if isinstance(response, dict) and 'validation_error' in response:
        error_info = response['validation_error']
        parameter_name = error_info['parameter_name']
        
        debug_print(f"Validation error - missing parameter: {parameter_name}")
        
        # Infer list operation using both parameter name and action name
        possible_operations = infer_list_operation(service, parameter_name, action)
        
        # Try each possible list operation
        list_response = None
        successful_operation = None
        
        for operation in possible_operations:
            try:
                debug_print(f"Trying list operation: {operation}")
                list_response = execute_aws_call(service, operation, dry_run)
                
                # Check if this returned actual data (not an error)
                if isinstance(list_response, list) and list_response:
                    successful_operation = operation
                    debug_print(f"Successfully executed: {operation}")
                    break
                    
            except Exception as e:
                debug_print(f"Operation {operation} failed: {e}")
                continue
        
        if not list_response or not successful_operation:
            print(f"ERROR: Could not find a working list operation for parameter '{parameter_name}'", file=sys.stderr)
            print(f"ERROR: Tried operations: {possible_operations}", file=sys.stderr)
            sys.exit(1)
        
        # Import here to avoid circular dependency
        from .formatters import flatten_response
        
        # Flatten and filter the list response
        list_resources = flatten_response(list_response)
        debug_print(f"Got {len(list_resources)} resources from {successful_operation}")
        
        # Apply resource filters to the list results
        if resource_filters:
            filtered_list_resources = filter_resources(list_resources, resource_filters)
            debug_print(f"After resource filtering: {len(filtered_list_resources)} resources")
        else:
            filtered_list_resources = list_resources
        
        if not filtered_list_resources:
            print(f"ERROR: No resources found matching resource filters: {resource_filters}", file=sys.stderr)
            sys.exit(1)
        
        # Extract parameter values from filtered results
        parameter_values = extract_parameter_values(filtered_list_resources, parameter_name)
        
        if not parameter_values:
            print(f"ERROR: Could not extract parameter '{parameter_name}' from filtered results", file=sys.stderr)
            sys.exit(1)
        
        # Determine if we need single value or list
        expects_list = parameter_expects_list(parameter_name)
        
        if expects_list:
            param_value = parameter_values
        else:
            # Show all options when multiple values found
            if len(parameter_values) > 1:
                print(f"Multiple {parameter_name} values found matching filters:", file=sys.stderr)
                for value in parameter_values:
                    print(f"- {value}", file=sys.stderr)
                print(f"Using first match: {parameter_values[0]}", file=sys.stderr)
            elif len(parameter_values) == 1:
                # Even for single values, show what was found for transparency
                print(f"Found {parameter_name}: {parameter_values[0]}", file=sys.stderr)
            
            param_value = parameter_values[0]  # Use first match
        
        debug_print(f"Using parameter value(s): {param_value}")
        
        # Create a client to introspect the correct parameter name
        try:
            client = boto3.client(service)
            # Get the correct case-sensitive parameter name using service model introspection
            converted_parameter_name = get_correct_parameter_name(client, action, parameter_name)
            debug_print(f"Parameter name resolution: {parameter_name} -> {converted_parameter_name}")
        except Exception as e:
            debug_print(f"Could not create client for parameter introspection: {e}")
            # Fallback to PascalCase conversion
            converted_parameter_name = convert_parameter_name(parameter_name)
            debug_print(f"Fallback parameter name conversion: {parameter_name} -> {converted_parameter_name}")
        
        # Retry the original call with the parameter
        parameters = {converted_parameter_name: param_value}
        response = execute_aws_call(service, action, dry_run, parameters)
        
        # Check for another validation error
        if isinstance(response, dict) and 'validation_error' in response:
            print(f"ERROR: Still getting validation error after parameter resolution: {response['validation_error']}", file=sys.stderr)
            sys.exit(1)
    
    # Import here to avoid circular dependency
    from .formatters import flatten_response
    
    # We now have a successful response - process it normally
    resources = flatten_response(response)
    debug_print(f"Final call returned {len(resources)} resources")
    
    # Apply value filters
    if value_filters:
        filtered_resources = filter_resources(resources, value_filters)
        debug_print(f"After value filtering: {len(filtered_resources)} resources")
    else:
        filtered_resources = resources
    
    return filtered_resources


def parse_validation_error(error):
    """Extract missing parameter info from ValidationError"""
    error_message = str(error)
    
    # Look for patterns like "Value null at 'parameterName'"
    pattern = r"Value null at '([^']+)'"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'null_value'
        }
    
    # Look for patterns like "Member must not be null" with parameter context
    pattern = r"'([^']+)'[^:]*: Member must not be null"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'required_parameter'
        }
    
    # Look for patterns like "Either StackName or PhysicalResourceId must be specified"
    pattern = r"Either (\w+) or \w+ must be specified"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'either_parameter'
        }
    
    # Look for patterns like "Missing required parameter in input: 'clusterName'"
    pattern = r"Missing required parameter in input: ['\"]([^'\"]+)['\"]"
    match = re.search(pattern, error_message)
    
    if match:
        parameter_name = match.group(1)
        return {
            'parameter_name': parameter_name,
            'is_required': True,
            'error_type': 'missing_parameter'
        }
    
    # Add debug output to help identify unmatched patterns
    debug_print(f"Could not parse validation error: {error_message}")
    
    return None


def infer_list_operation(service, parameter_name, action):
    """Infer the list operation from parameter name first, then action name as fallback"""
    
    possible_operations = []
    
    # FIRST: Try parameter-based inference (unless parameter is too generic)
    if parameter_name.lower() not in ['name', 'id', 'arn']:
        # Remove common suffixes from parameter name
        resource_name = parameter_name
        suffixes_to_remove = ['Name', 'Id', 'Arn', 'ARN']
        for suffix in suffixes_to_remove:
            if resource_name.endswith(suffix):
                resource_name = resource_name[:-len(suffix)]
                break
        
        # Convert to lowercase and pluralize
        resource_name = resource_name.lower()
        
        if resource_name.endswith('y'):
            plural_name = resource_name[:-1] + 'ies'
        elif resource_name.endswith(('s', 'sh', 'ch', 'x', 'z')):
            plural_name = resource_name + 'es'
        else:
            plural_name = resource_name + 's'
        
        # Add parameter-based operations
        possible_operations.extend([
            f'list_{plural_name}',
            f'describe_{plural_name}',
            f'get_{plural_name}',
            f'list_{resource_name}',
            f'describe_{resource_name}',
            f'get_{resource_name}'
        ])
        
        debug_print(f"Parameter-based inference: '{parameter_name}' -> '{resource_name}' -> {len(possible_operations)} operations")
    else:
        debug_print(f"Parameter '{parameter_name}' is too generic, skipping parameter-based inference")
    
    # SECOND: Add action-based inference as fallback
    # Extract resource name from action
    prefixes = ['describe', 'get', 'update', 'delete', 'create', 'list']
    action_lower = action.lower().replace('-', '_')
    
    action_resource = action_lower
    for prefix in prefixes:
        if action_lower.startswith(prefix + '_'):
            action_resource = action_lower[len(prefix) + 1:]
            break
    
    # Pluralize action-derived resource (if not already plural)
    if action_resource.endswith('s') and len(action_resource) > 1:
        # Likely already plural (instances, clusters, etc.)
        action_plural = action_resource
    elif action_resource.endswith('y'):
        action_plural = action_resource[:-1] + 'ies'
    elif action_resource.endswith(('sh', 'ch', 'x', 'z')):
        action_plural = action_resource + 'es'
    else:
        action_plural = action_resource + 's'
    
    # Add action-based operations (avoiding duplicates)
    action_operations = [
        f'list_{action_plural}',
        f'describe_{action_plural}',
        f'get_{action_plural}',
        f'list_{action_resource}',
        f'describe_{action_resource}',
        f'get_{action_resource}'
    ]
    
    for op in action_operations:
        if op not in possible_operations:
            possible_operations.append(op)
    
    debug_print(f"Action-based inference: '{action}' -> '{action_resource}' -> added {len(action_operations)} operations")
    debug_print(f"Total possible operations: {possible_operations}")
    
    return possible_operations


def parameter_expects_list(parameter_name):
    """Determine if parameter expects list or single value"""
    # Check if parameter name suggests it expects multiple values
    list_indicators = ['s', 'Names', 'Ids', 'Arns', 'ARNs']
    
    for indicator in list_indicators:
        if parameter_name.endswith(indicator):
            return True
    
    return False


def convert_parameter_name(parameter_name):
    """Convert parameter name from camelCase to PascalCase for AWS API compatibility"""
    if not parameter_name:
        return parameter_name
    
    # Convert camelCase to PascalCase (first letter uppercase)
    # stackName -> StackName
    # instanceId -> InstanceId
    # bucketName -> BucketName
    
    return parameter_name[0].upper() + parameter_name[1:] if len(parameter_name) > 0 else parameter_name


def get_correct_parameter_name(client, action, parameter_name):
    """Get the correct case-sensitive parameter name for an operation by introspecting the service model"""
    try:
        # Convert action name to PascalCase for service model lookup
        # list-nodegroups -> ListNodegroups  
        action_words = action.replace('-', '_').replace('_', ' ').split()
        pascal_case_action = ''.join(word.capitalize() for word in action_words)
        
        # Get the operation model from the service model
        operation_model = client.meta.service_model.operation_model(pascal_case_action)
        
        debug_print(f"Introspecting parameter name for {action} (PascalCase: {pascal_case_action})")
        
        # Get the input shape (parameters) for this operation
        if operation_model.input_shape:
            members = operation_model.input_shape.members
            debug_print(f"Available parameters: {list(members.keys())}")
            
            # Try exact match first
            if parameter_name in members:
                debug_print(f"Found exact match: {parameter_name}")
                return parameter_name
            
            # Try case-insensitive match
            for member_name in members:
                if member_name.lower() == parameter_name.lower():
                    debug_print(f"Found case-insensitive match: {parameter_name} -> {member_name}")
                    return member_name
            
            # Try PascalCase conversion as fallback
            pascal_case = parameter_name[0].upper() + parameter_name[1:]
            if pascal_case in members:
                debug_print(f"Found PascalCase match: {parameter_name} -> {pascal_case}")
                return pascal_case
            
            debug_print(f"No parameter match found for '{parameter_name}' in {list(members.keys())}")
        else:
            debug_print(f"Operation {pascal_case_action} has no input shape")
        
        # Default fallback to original parameter name
        debug_print(f"Using original parameter name: {parameter_name}")
        return parameter_name
        
    except Exception as e:
        debug_print(f"Could not introspect parameter name: {e}")
        # Fallback to PascalCase conversion
        fallback = convert_parameter_name(parameter_name)
        debug_print(f"Falling back to PascalCase: {parameter_name} -> {fallback}")
        return fallback