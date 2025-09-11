# awsquery - AWS API Query Tool

Advanced CLI tool to query AWS APIs through boto3 with flexible filtering, automatic parameter resolution, and comprehensive security validation.

## Features

- **Smart Multi-Level Calls**: Automatically resolves missing parameters by inferring and calling list operations
- **Flexible Filtering**: Multi-level filtering with `--` separators for resource, value, and column filters
- **Keys Discovery**: Show all available fields from any API response with `-k`/`--keys`
- **Debug Mode**: Comprehensive debug output with `-d`/`--debug` 
- **Security Validation**: Enforces ReadOnly AWS policy with wildcard pattern matching
- **Auto-completion**: Tab completion for AWS services and actions (filtered by security policy)
- **Smart Parameter Extraction**: Handles both specific fields and standard AWS field patterns (Name, Id, Arn)
- **Intelligent Response Processing**: Clean extraction of list data, ignoring metadata
- **Tabular Output**: Customizable column display with automatic filtering
- **Pagination Support**: Handles large AWS responses automatically
- **Dry-Run Mode**: Safe testing without making actual AWS calls

## Installation

### Via pip (Recommended)

```bash
pip install awsquery
```

### Development Installation

```bash
git clone https://github.com/yourusername/awsquery.git
cd awsquery
pip install -e ".[dev]"
```

## Usage

### Basic Query
```bash
# Query EC2 instances with filtering
awsquery ec2 describe-instances

# Filter by values (partial match, case-insensitive)
awsquery ec2 describe-instances prod web

# Specify output columns
awsquery ec2 describe-instances prod -- Name State InstanceId

# List S3 buckets containing "backup"
awsquery s3 list-buckets backup

# JSON output format
awsquery -j s3 list-buckets
```

### Keys Discovery
```bash
# Show available fields/keys from an API response
awsquery -k ec2 describe-instances
awsquery --keys s3 list-buckets
```

### Safety Features
```bash
# Dry run - shows what would be executed
awsquery --dry-run ec2 describe-instances

# List available services
awsquery

# Debug mode for troubleshooting
awsquery -d ec2 describe-instances
```

## Command Structure

```
awsquery [--dry-run] [-j|--json] [-k|--keys] [-d|--debug] SERVICE ACTION [VALUE_FILTERS...] [-- TABLE_OUTPUT_FILTERS...]
```

- **SERVICE**: AWS service name (ec2, s3, iam, etc.)
- **ACTION**: Service action (describe-instances, list-buckets, etc.)  
- **VALUE_FILTERS**: Space-separated filters (ALL must match any field)
- **TABLE_OUTPUT_FILTERS**: Column selection (partial name matching)
- **--dry-run**: Show what would be executed without making API calls
- **-j, --json**: Output results in JSON format instead of table
- **-k, --keys**: Show all available keys for the command
- **-d, --debug**: Enable debug output for troubleshooting

## Security

- Only ReadOnly AWS policy actions are permitted
- Input sanitization prevents injection attacks
- Actions validated against policy.json before execution
- All security validation relies on the included policy.json file

## Examples

```bash
# Find instances with "prod" and "web" in any field
awsquery ec2 describe-instances prod web

# Show only Name, State and InstanceId columns  
awsquery ec2 describe-instances prod web -- Name State InstanceId

# Find S3 buckets with "backup" in name
awsquery s3 list-buckets backup

# Multi-level CloudFormation query with parameter resolution
awsquery cloudformation describe-stack-events prod -- Created -- StackName

# Discover all available keys
awsquery -k ec2 describe-instances

# JSON output with filtering
awsquery -j ec2 describe-instances prod -- InstanceId State.Name

# Safe testing mode
awsquery --dry-run ec2 describe-instances

# Debug mode for troubleshooting
awsquery -d cloudformation describe-stack-resources workers -- EKS
```

## Configuration

Ensure AWS credentials are configured via:
- `~/.aws/credentials`
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (if running on EC2)

## Development

### Running Tests

```bash
# Install development dependencies
make install-dev

# Run all tests
make test

# Run tests with coverage
make coverage

# Run specific test categories
make test-unit
make test-integration

# Code formatting and linting
make format
make lint
make type-check
```

### Docker Usage

```bash
# Build development container
make docker-build

# Open interactive shell
make shell

# Run tests in Docker
make test-in-docker
```

## Requirements

The tool requires a `policy.json` file containing the AWS ReadOnly policy for security validation. This file is included automatically when installing via pip. The package dependencies are:

- boto3>=1.35.0
- botocore>=1.35.0  
- tabulate>=0.9.0
- argcomplete>=3.0.0

## License

MIT License - see LICENSE file for details.

## Contributing

Please see CONTRIBUTING.md for development guidelines and testing procedures.
