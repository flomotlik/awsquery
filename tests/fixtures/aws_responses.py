"""AWS response fixtures for testing scenarios."""

import uuid
from datetime import datetime, timezone


def get_paginated_response(
    service="ec2", operation="describe_instances", num_pages=3, items_per_page=2
):
    """
    Generate multi-page AWS response for pagination testing.

    Args:
        service: AWS service name
        operation: Operation name
        num_pages: Number of pages to generate
        items_per_page: Number of items per page

    Returns:
        List of response pages simulating paginated AWS API response
    """
    pages = []

    if service == "ec2" and operation == "describe_instances":
        for page_num in range(num_pages):
            instances = []
            for item_num in range(items_per_page):
                instance_id = f"i-{page_num:02d}{item_num:02d}{uuid.uuid4().hex[:8]}"
                instances.append(
                    {
                        "InstanceId": instance_id,
                        "InstanceType": ["t2.micro", "t3.small", "t3.medium"][item_num % 3],
                        "State": {
                            "Name": ["running", "stopped", "pending"][item_num % 3],
                            "Code": [16, 80, 0][item_num % 3],
                        },
                        "PublicIpAddress": f"203.0.{page_num + 1}.{item_num + 10}",
                        "PrivateIpAddress": f"10.0.{page_num}.{item_num + 10}",
                        "Tags": [
                            {"Key": "Name", "Value": f"instance-page{page_num}-item{item_num}"},
                            {
                                "Key": "Environment",
                                "Value": ["production", "staging", "development"][page_num % 3],
                            },
                            {
                                "Key": "Team",
                                "Value": ["backend", "frontend", "devops"][item_num % 3],
                            },
                        ],
                        "SecurityGroups": [
                            {
                                "GroupId": f'sg-{page_num:02d}{item_num:02d}{"a" * 8}',
                                "GroupName": f"security-group-{page_num}-{item_num}",
                            }
                        ],
                        "NetworkInterfaces": [
                            {
                                "NetworkInterfaceId": f'eni-{page_num:02d}{item_num:02d}{"b" * 8}',
                                "SubnetId": f'subnet-{page_num:02d}{"c" * 10}',
                                "VpcId": f'vpc-{page_num:02d}{"d" * 10}',
                                "PrivateIpAddress": f"10.0.{page_num}.{item_num + 10}",
                                "Association": (
                                    {
                                        "PublicIp": f"203.0.{page_num + 1}.{item_num + 10}",
                                        "PublicDnsName": (
                                            f"ec2-203-0-{page_num + 1}-{item_num + 10}."
                                            "compute-1.amazonaws.com"
                                        ),
                                    }
                                    if item_num % 2 == 0
                                    else None
                                ),
                            }
                        ],
                    }
                )

            page = {
                "Reservations": [
                    {"ReservationId": f'r-{page_num:02d}{"e" * 15}', "Instances": instances}
                ]
            }

            # Add NextToken for all pages except the last
            if page_num < num_pages - 1:
                page["NextToken"] = f"page-{page_num + 1}-token-{uuid.uuid4().hex[:8]}"

            page["ResponseMetadata"] = {"RequestId": f"{uuid.uuid4()}", "HTTPStatusCode": 200}

            pages.append(page)

    elif service == "s3" and operation == "list_buckets":
        # S3 ListBuckets doesn't typically paginate, but simulate for testing
        for page_num in range(num_pages):
            buckets = []
            for item_num in range(items_per_page):
                bucket_name = f"bucket-page{page_num}-item{item_num}-{uuid.uuid4().hex[:8]}"
                buckets.append(
                    {
                        "Name": bucket_name,
                        "CreationDate": datetime(
                            2023, page_num + 1, item_num + 1, tzinfo=timezone.utc
                        ),
                    }
                )

            page = {
                "Buckets": buckets,
                "Owner": {"DisplayName": "test-user", "ID": f"owner-{uuid.uuid4().hex}"},
            }

            if page_num < num_pages - 1:
                page["NextToken"] = f"bucket-page-{page_num + 1}-token"

            page["ResponseMetadata"] = {"RequestId": f"{uuid.uuid4()}", "HTTPStatusCode": 200}

            pages.append(page)

    elif service == "cloudformation" and operation == "describe_stacks":
        for page_num in range(num_pages):
            stacks = []
            for item_num in range(items_per_page):
                stack_name = f"stack-page{page_num}-item{item_num}"
                stacks.append(
                    {
                        "StackName": stack_name,
                        "StackId": (
                            f"arn:aws:cloudformation:us-east-1:123456789012:stack/"
                            f"{stack_name}/{uuid.uuid4()}"
                        ),
                        "StackStatus": ["CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE"][
                            item_num % 3
                        ],
                        "CreationTime": datetime(
                            2023, page_num + 1, item_num + 1, tzinfo=timezone.utc
                        ),
                        "Parameters": [
                            {
                                "ParameterKey": "Environment",
                                "ParameterValue": ["prod", "staging", "dev"][page_num % 3],
                            },
                            {
                                "ParameterKey": "InstanceType",
                                "ParameterValue": ["t3.medium", "t3.small", "t2.micro"][
                                    item_num % 3
                                ],
                            },
                        ],
                        "Tags": [
                            {
                                "Key": "Environment",
                                "Value": ["production", "staging", "development"][page_num % 3],
                            },
                            {"Key": "Owner", "Value": f"team-{page_num}"},
                            {"Key": "CostCenter", "Value": f"{1000 + page_num * 100 + item_num}"},
                        ],
                    }
                )

            page = {"Stacks": stacks}

            if page_num < num_pages - 1:
                page["NextToken"] = f"stack-page-{page_num + 1}-token"

            page["ResponseMetadata"] = {"RequestId": f"{uuid.uuid4()}", "HTTPStatusCode": 200}

            pages.append(page)

    return pages


def get_complex_nested_response(depth=4, breadth=3):
    """
    Generate deeply nested AWS response for flattening tests.

    Args:
        depth: How many levels deep to nest
        breadth: How many items at each level

    Returns:
        Complex nested dictionary simulating AWS API response
    """

    def create_nested_structure(current_depth, max_depth, current_breadth):
        if current_depth >= max_depth:
            return f"value-at-depth-{current_depth}"

        structure = {}

        # Create nested objects
        for i in range(current_breadth):
            key = f"Level{current_depth}Object{i}"
            structure[key] = create_nested_structure(current_depth + 1, max_depth, current_breadth)

        # Add arrays with nested objects
        array_key = f"Level{current_depth}Array"
        structure[array_key] = []
        for j in range(current_breadth):
            array_item = {
                f"ArrayItem{j}Id": f"item-{current_depth}-{j}",
                f"ArrayItem{j}Name": f"Item {j} at Level {current_depth}",
                f"ArrayItem{j}Nested": create_nested_structure(
                    current_depth + 1, max_depth, max(1, current_breadth - 1)
                ),
            }
            structure[array_key].append(array_item)

        return structure

    # Create the main response structure
    response = {
        "ComplexResource": {
            "ResourceId": "complex-resource-12345",
            "ResourceName": "Test Complex Resource",
            "Metadata": {
                "CreatedBy": "test-user",
                "CreatedAt": "2023-01-01T12:00:00Z",
                "Region": "us-east-1",
                "Tags": [
                    {"Key": "Environment", "Value": "test"},
                    {"Key": "Application", "Value": "complex-app"},
                    {"Key": "Owner", "Value": "engineering-team"},
                ],
            },
            "Configuration": create_nested_structure(0, depth, breadth),
            "NetworkConfiguration": {
                "VPC": {
                    "VpcId": "vpc-12345678",
                    "CidrBlock": "10.0.0.0/16",
                    "Subnets": [
                        {
                            "SubnetId": f"subnet-{i:08d}",
                            "CidrBlock": f"10.0.{i}.0/24",
                            "AvailabilityZone": f'us-east-1{chr(ord("a") + i)}',
                            "RouteTable": {
                                "RouteTableId": f"rtb-{i:08d}",
                                "Routes": [
                                    {
                                        "DestinationCidrBlock": "0.0.0.0/0",
                                        "GatewayId": "igw-12345678",
                                        "State": "active",
                                    },
                                    {
                                        "DestinationCidrBlock": "10.0.0.0/16",
                                        "GatewayId": "local",
                                        "State": "active",
                                    },
                                ],
                            },
                        }
                        for i in range(breadth)
                    ],
                },
                "SecurityGroups": [
                    {
                        "GroupId": f"sg-{i:08d}",
                        "GroupName": f"security-group-{i}",
                        "Rules": {
                            "Ingress": [
                                {
                                    "FromPort": 80,
                                    "ToPort": 80,
                                    "Protocol": "tcp",
                                    "CidrBlocks": ["0.0.0.0/0"],
                                },
                                {
                                    "FromPort": 443,
                                    "ToPort": 443,
                                    "Protocol": "tcp",
                                    "CidrBlocks": ["0.0.0.0/0"],
                                },
                            ],
                            "Egress": [
                                {
                                    "FromPort": 0,
                                    "ToPort": 65535,
                                    "Protocol": "-1",
                                    "CidrBlocks": ["0.0.0.0/0"],
                                }
                            ],
                        },
                    }
                    for i in range(breadth)
                ],
            },
        },
        "RelatedResources": [
            {
                "ResourceType": "Instance",
                "ResourceId": f"i-{i:016d}",
                "DeepNesting": create_nested_structure(0, depth - 1, breadth),
            }
            for i in range(breadth)
        ],
        "ResponseMetadata": {"RequestId": f"{uuid.uuid4()}", "HTTPStatusCode": 200},
    }

    return response


def get_validation_error_responses():
    """
    Generate various validation error scenarios for testing.

    Returns:
        Dictionary of different validation error types
    """
    return {
        "missing_stack_name": {
            "error_type": "ParamValidationError",
            "message": "Missing required parameter in input: 'stackName'",
            "parameter": "stackName",
        },
        "null_cluster_name": {
            "error_type": "ValidationException",
            "message": "Value null at 'clusterName' failed to satisfy "
            "constraint: Member must not be null",
            "parameter": "clusterName",
        },
        "either_parameter": {
            "error_type": "ValidationException",
            "message": "Either StackName or PhysicalResourceId must be specified",
            "parameter": "StackName",
        },
        "invalid_instance_id": {
            "error_type": "InvalidInstanceID.NotFound",
            "message": "The instance ID 'i-invalid123' does not exist",
            "parameter": "InstanceIds",
        },
    }


def get_empty_responses():
    """
    Generate various empty response scenarios for edge case testing.

    Returns:
        Dictionary of different empty response types
    """
    return {
        "empty_list": {
            "Instances": [],
            "ResponseMetadata": {"RequestId": str(uuid.uuid4()), "HTTPStatusCode": 200},
        },
        "no_data_key": {
            "ResponseMetadata": {"RequestId": str(uuid.uuid4()), "HTTPStatusCode": 200}
        },
        "null_values": {
            "Instances": [
                {
                    "InstanceId": "i-nullvalues123",
                    "InstanceType": None,
                    "State": {"Name": None},
                    "Tags": [],
                }
            ],
            "ResponseMetadata": {"RequestId": str(uuid.uuid4()), "HTTPStatusCode": 200},
        },
    }


def get_mixed_type_response():
    """
    Generate response with mixed data types for robust parsing tests.

    Returns:
        Response containing strings, numbers, booleans, arrays, objects
    """
    return {
        "MixedTypeResource": {
            "StringField": "test-string-value",
            "NumberField": 12345,
            "FloatField": 123.45,
            "BooleanField": True,
            "NullField": None,
            "EmptyStringField": "",
            "ZeroField": 0,
            "FalseField": False,
            "ArrayField": ["string-item", 42, True, None, {"NestedObject": "in-array"}],
            "ObjectField": {
                "NestedString": "nested-value",
                "NestedNumber": 67890,
                "NestedBoolean": False,
                "NestedArray": [1, 2, 3],
            },
        },
        "ResponseMetadata": {"RequestId": str(uuid.uuid4()), "HTTPStatusCode": 200},
    }
