"""Sample security policy fixtures for testing scenarios."""

import json
import os
import tempfile
from pathlib import Path


def get_readonly_policy():
    return {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ec2:Describe*",
                            "ec2:List*",
                            "ec2:Get*",
                            "s3:List*",
                            "s3:Get*",
                            "s3:Head*",
                            "cloudformation:Describe*",
                            "cloudformation:List*",
                            "cloudformation:Get*",
                            "iam:List*",
                            "iam:Get*",
                            "lambda:List*",
                            "lambda:Get*",
                            "rds:Describe*",
                            "rds:List*",
                            "route53:List*",
                            "route53:Get*",
                            "elb:Describe*",
                            "elbv2:Describe*",
                            "autoscaling:Describe*",
                            "cloudwatch:Describe*",
                            "cloudwatch:List*",
                            "cloudwatch:Get*",
                            "logs:Describe*",
                            "logs:List*",
                            "logs:Get*",
                        ],
                        "Resource": "*",
                    }
                ],
            }
        }
    }


def get_restrictive_policy():
    """
    Highly restrictive policy allowing only specific operations.

    Returns:
        Dictionary representing a minimal IAM policy for testing denials
    """
    return {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ec2:DescribeInstances", "s3:ListBuckets", "iam:GetUser"],
                        "Resource": "*",
                    }
                ],
            }
        }
    }


def get_wildcard_policy():
    """
    Policy with various wildcard patterns for testing pattern matching.

    Returns:
        Dictionary representing an IAM policy with wildcard actions
    """
    return {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "*:Describe*",
                            "*:List*",
                            "ec2:Get*",
                            "s3:*Bucket*",
                            "cloudformation:*Stack*",
                            "iam:*User*",
                        ],
                        "Resource": "*",
                    }
                ],
            }
        }
    }


def get_deny_policy():
    """
    Policy with explicit denies for testing security validation.

    Returns:
        Dictionary representing an IAM policy with deny statements
    """
    return {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Action": "*", "Resource": "*"},
                    {
                        "Effect": "Deny",
                        "Action": [
                            "ec2:TerminateInstances",
                            "ec2:StopInstances",
                            "s3:DeleteBucket",
                            "s3:DeleteObject",
                            "cloudformation:DeleteStack",
                            "iam:Delete*",
                            "*:Create*",
                            "*:Update*",
                            "*:Modify*",
                        ],
                        "Resource": "*",
                    },
                ],
            }
        }
    }


def get_service_specific_policy(service):
    """
    Generate service-specific policy for targeted testing.

    Args:
        service: AWS service name (e.g., 'ec2', 's3', 'iam')

    Returns:
        Dictionary representing service-specific IAM policy
    """
    service_policies = {
        "ec2": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "ec2:DescribeInstances",
                                "ec2:DescribeImages",
                                "ec2:DescribeSecurityGroups",
                                "ec2:DescribeVpcs",
                                "ec2:DescribeSubnets",
                                "ec2:DescribeSnapshots",
                                "ec2:DescribeVolumes",
                            ],
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
        "s3": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "s3:ListBuckets",
                                "s3:ListAllMyBuckets",
                                "s3:GetBucketLocation",
                                "s3:GetBucketVersioning",
                                "s3:GetBucketPolicy",
                            ],
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
        "iam": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "iam:ListUsers",
                                "iam:ListRoles",
                                "iam:ListGroups",
                                "iam:ListPolicies",
                                "iam:GetUser",
                                "iam:GetRole",
                                "iam:GetPolicy",
                            ],
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
    }

    return service_policies.get(service, get_readonly_policy())


def get_malformed_policies():
    """
    Generate various malformed policy scenarios for error handling tests.

    Returns:
        Dictionary of malformed policy examples
    """
    return {
        "invalid_json": '{"PolicyVersion": {"Document": {invalid json}',
        "missing_statement": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17"
                    # Missing Statement array
                }
            }
        },
        "empty_statement": {
            "PolicyVersion": {"Document": {"Version": "2012-10-17", "Statement": []}}
        },
        "missing_effect": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            # Missing "Effect" field
                            "Action": ["ec2:DescribeInstances"],
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
        "invalid_effect": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "InvalidEffect",  # Should be Allow or Deny
                            "Action": ["ec2:DescribeInstances"],
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
    }


def get_legacy_policy_formats():
    """
    Generate legacy/alternative policy formats for compatibility testing.

    Returns:
        Dictionary of different policy format examples
    """
    return {
        "direct_statement": {
            # No PolicyVersion wrapper
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ec2:DescribeInstances", "s3:ListBuckets"],
                    "Resource": "*",
                }
            ],
        },
        "single_action_string": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "ec2:DescribeInstances",  # Single string instead of array
                            "Resource": "*",
                        }
                    ],
                }
            }
        },
        "multiple_statements": {
            "PolicyVersion": {
                "Document": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {"Effect": "Allow", "Action": ["ec2:Describe*"], "Resource": "*"},
                        {"Effect": "Allow", "Action": ["s3:List*", "s3:Get*"], "Resource": "*"},
                        {"Effect": "Deny", "Action": ["ec2:TerminateInstances"], "Resource": "*"},
                    ],
                }
            }
        },
    }


def create_policy_file(policy_dict, file_path=None):
    """
    Create a temporary policy file for testing.

    Args:
        policy_dict: Policy dictionary to write to file
        file_path: Optional specific file path, otherwise creates temp file

    Returns:
        Path to the created policy file
    """
    if file_path is None:
        # Create temporary file
        fd, file_path = tempfile.mkstemp(suffix=".json", prefix="test_policy_")
        os.close(fd)

    with open(file_path, "w") as f:
        json.dump(policy_dict, f, indent=2)

    return file_path


def create_policy_test_scenarios():
    """
    Create a comprehensive set of policy test scenarios.

    Returns:
        Dictionary mapping scenario names to policy configurations
    """
    return {
        "readonly": get_readonly_policy(),
        "restrictive": get_restrictive_policy(),
        "wildcard": get_wildcard_policy(),
        "deny": get_deny_policy(),
        "ec2_only": get_service_specific_policy("ec2"),
        "s3_only": get_service_specific_policy("s3"),
        "iam_only": get_service_specific_policy("iam"),
        "direct_statement": get_legacy_policy_formats()["direct_statement"],
        "single_action": get_legacy_policy_formats()["single_action_string"],
        "multiple_statements": get_legacy_policy_formats()["multiple_statements"],
        "empty_statement": get_malformed_policies()["empty_statement"],
    }


class PolicyFileManager:
    """Context manager for creating and cleaning up policy files during tests."""

    def __init__(self, policy_dict):
        self.policy_dict = policy_dict
        self.file_path = None

    def __enter__(self):
        self.file_path = create_policy_file(self.policy_dict)
        return self.file_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_path and os.path.exists(self.file_path):
            os.unlink(self.file_path)


# Test helper functions
def assert_policy_allows(policy_dict, service, action):
    """
    Helper function to test if a policy allows a specific action.

    Args:
        policy_dict: Policy dictionary
        service: AWS service name
        action: Action name

    Returns:
        Boolean indicating if action is allowed
    """
    # This would integrate with the actual security validation logic
    # For now, return a simple check based on policy structure
    try:
        statements = policy_dict.get("PolicyVersion", {}).get("Document", {}).get("Statement", [])
        service_action = f"{service}:{action}"

        for statement in statements:
            if statement.get("Effect") == "Allow":
                actions = statement.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]

                for allowed_action in actions:
                    if service_action == allowed_action or allowed_action.endswith("*"):
                        return True
        return False
    except:
        return False


def get_test_policy_combinations():
    """
    Generate combinations of policies and actions for comprehensive testing.

    Returns:
        List of (policy_name, policy_dict, service, action, expected_result) tuples
    """
    test_cases = []
    policies = create_policy_test_scenarios()

    # Test cases: (policy_name, service, action, expected_allowed)
    test_scenarios = [
        ("readonly", "ec2", "DescribeInstances", True),
        ("readonly", "s3", "ListBuckets", True),
        ("readonly", "ec2", "TerminateInstances", False),  # Not in read-only
        ("restrictive", "ec2", "DescribeInstances", True),
        ("restrictive", "ec2", "DescribeImages", False),  # Not in restrictive
        ("wildcard", "ec2", "DescribeAnything", True),  # Wildcard match
        ("ec2_only", "ec2", "DescribeInstances", True),
        ("ec2_only", "s3", "ListBuckets", False),  # Wrong service
    ]

    for policy_name, service, action, expected in test_scenarios:
        if policy_name in policies:
            test_cases.append((policy_name, policies[policy_name], service, action, expected))

    return test_cases
