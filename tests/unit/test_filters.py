"""
Comprehensive unit tests for AWS Query Tool filtering functions.

This module tests the filtering logic functions including:
- filter_resources() - Filter resources by value filters (ALL must match)
- parse_multi_level_filters() - Parse command line args with multiple -- separators
- extract_parameter_values() - Extract parameter values from resources (tested in test_core.py)

Test coverage target: 90% for filtering functions
Test count target: 20-25 tests
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Import the functions under test
from src.awsquery.filters import (
    filter_resources,
    parse_multi_level_filters
)


@pytest.mark.unit
class TestFilterResources:
    """Test suite for filter_resources() function."""
    
    def test_empty_filters_returns_all_resources(self):
        """Test that empty filters return all resources unchanged."""
        resources = [
            {'InstanceId': 'i-123', 'State': {'Name': 'running'}},
            {'InstanceId': 'i-456', 'State': {'Name': 'stopped'}}
        ]
        
        result = filter_resources(resources, [])
        
        assert result == resources
        assert len(result) == 2

    def test_empty_resources_returns_empty_list(self):
        """Test that empty resources with filters returns empty list."""
        result = filter_resources([], ['running'])
        
        assert result == []

    def test_none_filters_returns_all_resources(self):
        """Test that None filters return all resources unchanged."""
        resources = [
            {'InstanceId': 'i-123', 'State': {'Name': 'running'}},
            {'InstanceId': 'i-456', 'State': {'Name': 'stopped'}}
        ]
        
        result = filter_resources(resources, None)
        
        assert result == resources
        assert len(result) == 2

    def test_single_filter_matching_key(self):
        """Test filtering resources by a single filter matching flattened keys."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'running'},
                'Tags': [{'Key': 'Name', 'Value': 'web-server'}]
            },
            {
                'InstanceId': 'i-456', 
                'State': {'Name': 'stopped'},
                'Tags': [{'Key': 'Name', 'Value': 'db-server'}]
            }
        ]
        
        result = filter_resources(resources, ['instanceid'])
        
        # Should match both resources since both have InstanceId in flattened keys
        assert len(result) == 2
        assert all('InstanceId' in resource for resource in result)

    def test_single_filter_matching_value(self):
        """Test filtering resources by a single filter matching values."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'running'},
                'InstanceType': 't2.micro'
            },
            {
                'InstanceId': 'i-456',
                'State': {'Name': 'stopped'},
                'InstanceType': 't3.small'
            }
        ]
        
        result = filter_resources(resources, ['running'])
        
        # Should match only the first resource with 'running' state
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-123'

    def test_single_filter_case_insensitive(self):
        """Test that filtering is case insensitive."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'RUNNING'},
                'InstanceType': 't2.micro'
            },
            {
                'InstanceId': 'i-456',
                'State': {'Name': 'STOPPED'},
                'InstanceType': 't3.small'
            }
        ]
        
        result = filter_resources(resources, ['running'])
        
        # Should match despite case difference
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-123'

    def test_single_filter_partial_string_matching(self):
        """Test that filtering supports partial string matching."""
        resources = [
            {
                'InstanceId': 'i-webserver-123',
                'Tags': [{'Key': 'Name', 'Value': 'production-web-server'}]
            },
            {
                'InstanceId': 'i-database-456',
                'Tags': [{'Key': 'Name', 'Value': 'production-db-server'}]
            }
        ]
        
        result = filter_resources(resources, ['web'])
        
        # Should match resources containing 'web' in any field
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-webserver-123'

    def test_multiple_filters_all_must_match(self):
        """Test that multiple filters require ALL to match (AND logic)."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'running'},
                'InstanceType': 't2.micro',
                'Tags': [{'Key': 'Environment', 'Value': 'production'}]
            },
            {
                'InstanceId': 'i-456',
                'State': {'Name': 'running'},
                'InstanceType': 't3.small',
                'Tags': [{'Key': 'Environment', 'Value': 'staging'}]
            },
            {
                'InstanceId': 'i-789',
                'State': {'Name': 'stopped'},
                'InstanceType': 't2.micro',
                'Tags': [{'Key': 'Environment', 'Value': 'production'}]
            }
        ]
        
        result = filter_resources(resources, ['running', 'production'])
        
        # Only first resource matches both 'running' AND 'production'
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-123'

    def test_multiple_filters_no_matches(self):
        """Test multiple filters where no resource matches all filters."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'running'},
                'InstanceType': 't2.micro'
            },
            {
                'InstanceId': 'i-456',
                'State': {'Name': 'stopped'},
                'InstanceType': 't3.small'
            }
        ]
        
        result = filter_resources(resources, ['running', 'nonexistent'])
        
        # No resource matches both filters
        assert len(result) == 0

    def test_nested_resource_structures(self):
        """Test filtering works with complex nested AWS resource structures."""
        resources = [
            {
                'InstanceId': 'i-123',
                'NetworkInterfaces': [
                    {
                        'NetworkInterfaceId': 'eni-123',
                        'SubnetId': 'subnet-web-123',
                        'VpcId': 'vpc-main',
                        'Association': {
                            'PublicIp': '1.2.3.4',
                            'PublicDnsName': 'ec2-1-2-3-4.compute-1.amazonaws.com'
                        }
                    }
                ],
                'SecurityGroups': [
                    {'GroupId': 'sg-web-123', 'GroupName': 'web-security-group'}
                ]
            },
            {
                'InstanceId': 'i-456',
                'NetworkInterfaces': [
                    {
                        'NetworkInterfaceId': 'eni-456',
                        'SubnetId': 'subnet-db-456',
                        'VpcId': 'vpc-main'
                    }
                ],
                'SecurityGroups': [
                    {'GroupId': 'sg-db-456', 'GroupName': 'db-security-group'}
                ]
            }
        ]
        
        result = filter_resources(resources, ['web'])
        
        # Should match first resource that contains 'web' in various nested fields
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-123'

    def test_ec2_instances_realistic_filtering(self):
        """Test filtering with realistic EC2 instance data."""
        resources = [
            {
                'InstanceId': 'i-1234567890abcdef0',
                'InstanceType': 't2.micro',
                'State': {'Name': 'running', 'Code': 16},
                'PublicIpAddress': '203.0.113.12',
                'PrivateIpAddress': '10.0.0.5',
                'Tags': [
                    {'Key': 'Name', 'Value': 'web-server-01'},
                    {'Key': 'Environment', 'Value': 'production'},
                    {'Key': 'Team', 'Value': 'backend'}
                ],
                'SecurityGroups': [
                    {'GroupId': 'sg-12345678', 'GroupName': 'web-sg'}
                ]
            },
            {
                'InstanceId': 'i-abcdef1234567890',
                'InstanceType': 't3.small',
                'State': {'Name': 'stopped', 'Code': 80},
                'Tags': [
                    {'Key': 'Name', 'Value': 'api-server-02'},
                    {'Key': 'Environment', 'Value': 'staging'},
                    {'Key': 'Team', 'Value': 'backend'}
                ],
                'SecurityGroups': [
                    {'GroupId': 'sg-87654321', 'GroupName': 'api-sg'}
                ]
            }
        ]
        
        # Test filtering by environment
        result = filter_resources(resources, ['production'])
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-1234567890abcdef0'
        
        # Test filtering by team (should match both)
        result = filter_resources(resources, ['backend'])
        assert len(result) == 2
        
        # Test filtering by state and environment (should match one)
        result = filter_resources(resources, ['running', 'production'])
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-1234567890abcdef0'

    def test_s3_buckets_realistic_filtering(self):
        """Test filtering with realistic S3 bucket data."""
        resources = [
            {
                'Name': 'production-logs-bucket',
                'CreationDate': '2023-01-15T10:30:00Z'
            },
            {
                'Name': 'staging-backup-bucket',
                'CreationDate': '2023-02-20T14:45:00Z'
            },
            {
                'Name': 'development-assets',
                'CreationDate': '2023-03-10T09:15:00Z'
            }
        ]
        
        # Test filtering by environment prefix
        result = filter_resources(resources, ['staging'])
        assert len(result) == 1
        assert result[0]['Name'] == 'staging-backup-bucket'
        
        # Test filtering by bucket type
        result = filter_resources(resources, ['logs'])
        assert len(result) == 1
        assert result[0]['Name'] == 'production-logs-bucket'

    def test_cloudformation_stacks_realistic_filtering(self):
        """Test filtering with realistic CloudFormation stack data."""
        resources = [
            {
                'StackName': 'production-infrastructure',
                'StackStatus': 'CREATE_COMPLETE',
                'Parameters': [
                    {'ParameterKey': 'Environment', 'ParameterValue': 'production'},
                    {'ParameterKey': 'InstanceType', 'ParameterValue': 't3.medium'}
                ],
                'Tags': [
                    {'Key': 'Owner', 'Value': 'infrastructure-team'},
                    {'Key': 'CostCenter', 'Value': '1234'}
                ]
            },
            {
                'StackName': 'staging-webapp',
                'StackStatus': 'UPDATE_COMPLETE',
                'Parameters': [
                    {'ParameterKey': 'Environment', 'ParameterValue': 'staging'}
                ],
                'Tags': [
                    {'Key': 'Application', 'Value': 'webapp'},
                    {'Key': 'Owner', 'Value': 'dev-team'}
                ]
            }
        ]
        
        # Test filtering by stack status
        result = filter_resources(resources, ['CREATE_COMPLETE'])
        assert len(result) == 1
        assert result[0]['StackName'] == 'production-infrastructure'
        
        # Test filtering by owner team
        result = filter_resources(resources, ['dev-team'])
        assert len(result) == 1
        assert result[0]['StackName'] == 'staging-webapp'

    @patch('src.awsquery.utils.debug_enabled', True)
    def test_debug_output_validation(self, capsys):
        """Test that debug output is generated when debug mode is enabled."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Name': 'running'}
            }
        ]
        
        filter_resources(resources, ['running'])
        
        captured = capsys.readouterr()
        assert "Applying value filter: running" in captured.err
        assert "Found 1 resources matching filters" in captured.err

    def test_complex_aws_resource_with_arrays(self):
        """Test filtering resources with complex array structures."""
        resources = [
            {
                'LoadBalancerName': 'web-lb',
                'Instances': [
                    {'InstanceId': 'i-123'},
                    {'InstanceId': 'i-456'}
                ],
                'ListenerDescriptions': [
                    {
                        'Listener': {
                            'Protocol': 'HTTP',
                            'LoadBalancerPort': 80
                        }
                    },
                    {
                        'Listener': {
                            'Protocol': 'HTTPS', 
                            'LoadBalancerPort': 443
                        }
                    }
                ]
            },
            {
                'LoadBalancerName': 'api-lb',
                'Instances': [
                    {'InstanceId': 'i-789'}
                ],
                'ListenerDescriptions': [
                    {
                        'Listener': {
                            'Protocol': 'TCP',
                            'LoadBalancerPort': 3000
                        }
                    }
                ]
            }
        ]
        
        # Test filtering by protocol in nested array
        result = filter_resources(resources, ['HTTPS'])
        assert len(result) == 1
        assert result[0]['LoadBalancerName'] == 'web-lb'

    def test_filter_with_special_characters(self):
        """Test filtering with special characters in filter strings."""
        resources = [
            {
                'BucketName': 'test-bucket-2023',
                'Tags': [{'Key': 'Version', 'Value': 'v1.2.3'}]
            },
            {
                'BucketName': 'prod_bucket_main',
                'Tags': [{'Key': 'Version', 'Value': 'v2.0.0'}]
            }
        ]
        
        # Test filtering with hyphen
        result = filter_resources(resources, ['test-bucket'])
        assert len(result) == 1
        assert result[0]['BucketName'] == 'test-bucket-2023'
        
        # Test filtering with underscore
        result = filter_resources(resources, ['prod_bucket'])
        assert len(result) == 1
        assert result[0]['BucketName'] == 'prod_bucket_main'

    def test_filter_with_numeric_values(self):
        """Test filtering with numeric values in resources."""
        resources = [
            {
                'InstanceId': 'i-123',
                'State': {'Code': 16},
                'BlockDeviceMappings': [
                    {
                        'Ebs': {
                            'VolumeSize': 20,
                            'VolumeType': 'gp2'
                        }
                    }
                ]
            },
            {
                'InstanceId': 'i-456',
                'State': {'Code': 80},
                'BlockDeviceMappings': [
                    {
                        'Ebs': {
                            'VolumeSize': 100,
                            'VolumeType': 'gp3'
                        }
                    }
                ]
            }
        ]
        
        # Test filtering by numeric value (as string)
        result = filter_resources(resources, ['16'])
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-123'
        
        # Test filtering by volume size
        result = filter_resources(resources, ['100'])
        assert len(result) == 1
        assert result[0]['InstanceId'] == 'i-456'


@pytest.mark.unit
class TestParseMultiLevelFilters:
    """Test suite for parse_multi_level_filters() function."""

    def test_no_separators_base_command_only(self):
        """Test parsing command line with no -- separators."""
        argv = ['ec2', 'describe-instances', '--dry-run']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['ec2', 'describe-instances', '--dry-run']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == []

    def test_single_separator_simple_command(self):
        """Test parsing with single -- separator for simple commands."""
        argv = ['s3', 'list-buckets', '--', 'name', 'creationdate']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['s3', 'list-buckets']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == ['name', 'creationdate']

    def test_single_separator_with_flags(self):
        """Test parsing single -- separator with flags in base command."""
        argv = ['--dry-run', 'ec2', 'describe-instances', '--debug', '--', 'instanceid', 'state']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['--dry-run', 'ec2', 'describe-instances', '--debug']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == ['instanceid', 'state']

    def test_two_separators_resource_and_column_filters(self):
        """Test parsing with two -- separators (base + resource + column filters)."""
        argv = ['eks', 'describe-cluster', 'cluster-name-filter', '--', 'production', '--', 'name', 'status']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['eks', 'describe-cluster']
        assert resource_filters == ['cluster-name-filter']
        assert value_filters == ['production']
        assert column_filters == ['name', 'status']

    def test_three_separators_full_multi_level(self):
        """Test parsing with three -- separators for full multi-level filtering."""
        argv = ['cloudformation', 'describe-stacks', 'prod', 'infra', '--', 'CREATE_COMPLETE', 'production', '--', 'stackname', 'status']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['cloudformation', 'describe-stacks']
        assert resource_filters == ['prod', 'infra']
        assert value_filters == ['CREATE_COMPLETE', 'production']
        assert column_filters == ['stackname', 'status']

    def test_multiple_separators_with_flags(self):
        """Test parsing multiple separators with various flags."""
        argv = ['--debug', 'ec2', 'describe-instances', '--keys', 'web', '--', 'running', '--', 'instanceid', 'publicip']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['--debug', 'ec2', 'describe-instances', '--keys']
        assert resource_filters == ['web']
        assert value_filters == ['running']
        assert column_filters == ['instanceid', 'publicip']

    def test_service_and_action_identification(self):
        """Test proper identification of service and action vs resource filters."""
        argv = ['s3', 'list-objects-v2', 'bucket-name', 'prefix-filter', '--', 'size', '1024']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        # First non-flag is service, second is action, rest are resource filters
        assert base_command == ['s3', 'list-objects-v2']
        assert resource_filters == ['bucket-name', 'prefix-filter']
        assert value_filters == ['size', '1024']
        assert column_filters == []

    def test_flags_go_to_base_command(self):
        """Test that flags are properly routed to base command."""
        argv = ['-j', '--dry-run', 'ec2', '--debug', 'describe-instances', 'filter1', '--', 'value1']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['-j', '--dry-run', 'ec2', '--debug', 'describe-instances']
        assert resource_filters == ['filter1']
        assert value_filters == ['value1']
        assert column_filters == []

    def test_empty_segments_handling(self):
        """Test handling of empty segments between separators."""
        argv = ['ec2', 'describe-instances', '--', '--', 'instanceid']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['ec2', 'describe-instances']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == ['instanceid']

    def test_separator_at_start(self):
        """Test handling of -- separator at the start of argv."""
        argv = ['--', 'ec2', 'describe-instances']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == []
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == ['ec2', 'describe-instances']

    def test_separator_at_end(self):
        """Test handling of -- separator at the end of argv."""
        argv = ['ec2', 'describe-instances', '--']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['ec2', 'describe-instances']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == []

    def test_consecutive_separators(self):
        """Test handling of consecutive -- separators."""
        argv = ['ec2', 'describe-instances', '--', '--', '--', 'instanceid']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['ec2', 'describe-instances']
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == []

    def test_single_separator_logic_for_simple_commands(self):
        """Test special logic for single -- separator with simple commands."""
        # When there are no resource filters and only one separator,
        # treat content after -- as column filters instead of value filters
        argv = ['s3', 'list-buckets', '--', 'name', 'creationdate']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['s3', 'list-buckets']
        assert resource_filters == []
        assert value_filters == []  # Should be empty due to single separator logic
        assert column_filters == ['name', 'creationdate']

    def test_complex_command_parsing_scenario(self):
        """Test complex real-world command parsing scenario."""
        argv = [
            '--debug', 
            'eks', 'describe-cluster',
            '--keys',
            'production-cluster',
            '--',
            'ACTIVE', 'production',
            '--', 
            'name', 'status', 'version'
        ]
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == ['--debug', 'eks', 'describe-cluster', '--keys']
        assert resource_filters == ['production-cluster']
        assert value_filters == ['ACTIVE', 'production']
        assert column_filters == ['name', 'status', 'version']

    @patch('src.awsquery.utils.debug_enabled', True)
    def test_debug_output_for_parsing(self, capsys):
        """Test that debug output is generated during parsing."""
        argv = ['ec2', 'describe-instances', 'web', '--', 'running', '--', 'instanceid']
        
        parse_multi_level_filters(argv)
        
        captured = capsys.readouterr()
        assert "Multi-level parsing" in captured.err

    @pytest.mark.parametrize("argv,expected_base,expected_resource,expected_value,expected_column", [
        # Simple cases
        (['service', 'action'], ['service', 'action'], [], [], []),
        (['service', 'action', '--', 'col1'], ['service', 'action'], [], [], ['col1']),
        
        # With flags
        (['--flag', 'service', 'action'], ['--flag', 'service', 'action'], [], [], []),
        (['-j', 'service', 'action', 'res1', '--', 'val1'], ['-j', 'service', 'action'], ['res1'], ['val1'], []),
        
        # Complex multi-level
        (['svc', 'act', 'r1', 'r2', '--', 'v1', '--', 'c1', 'c2'], ['svc', 'act'], ['r1', 'r2'], ['v1'], ['c1', 'c2']),
        
        # Edge cases
        (['--', 'after-separator'], [], [], [], ['after-separator']),
        (['before', '--'], ['before'], [], [], []),
    ])
    def test_parsing_parametrized_scenarios(self, argv, expected_base, expected_resource, expected_value, expected_column):
        """Test various parsing scenarios with parametrized inputs."""
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == expected_base
        assert resource_filters == expected_resource
        assert value_filters == expected_value
        assert column_filters == expected_column

    def test_empty_argv(self):
        """Test parsing empty argv."""
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters([])
        
        assert base_command == []
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == []

    def test_only_separators(self):
        """Test parsing argv with only separators."""
        argv = ['--', '--', '--']
        
        base_command, resource_filters, value_filters, column_filters = parse_multi_level_filters(argv)
        
        assert base_command == []
        assert resource_filters == []
        assert value_filters == []
        assert column_filters == []