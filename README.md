# awsquery - AWS API Query Tool

AWS CLI tool to run any awscli read command and filter the resulting Values and JSON for custom table output.

The following command will find all ec2 instances where `prod`and `web` are found somewhere in the Value
of any key of the whole response. For all matching resources it will extract all fields that match
any of the second filters, so anything that matches `Tags.Name`, `State`, `InstanceId` or `vpcid`.
```
awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId vpcid
```

This creates endless flexibility to shape your aws cli calls, filter any output and present exactly
the data you need during review, debugging or development.

## Features

- **Smart Multi-Level Calls**: Automatically resolves missing parameters by inferring and calling list operations
- **Flexible Filtering**: Multi-level filtering with `--` separators for resource, value, and column filters
- **Partial Matching**: All filters use case-insensitive partial matching (both value and column filters)
- **Keys Discovery**: Show all available fields from any API response with `-k`/`--keys` (fixed to show keys from successful responses)
- **Debug Mode**: Comprehensive debug output with `-d`/`--debug`
- **Security Validation**: Enforces ReadOnly AWS policy with wildcard pattern matching
- **Auto-completion**: Tab completion for AWS services and actions (filtered by security policy)
- **Smart Parameter Extraction**: Handles both specific fields and standard AWS field patterns (Name, Id, Arn)
- **Intelligent Response Processing**: Clean extraction of list data, ignoring metadata
- **Tabular Output**: Customizable column display with automatic filtering
- **Pagination Support**: Handles large AWS responses automatically
- **Region/Profile Support**: AWS CLI-compatible `--region` and `--profile` arguments for session management
- **Tag Transformation**: Automatic conversion of AWS Tags list to key-value pairs for better readability
- **Default Column Filters**: Configuration-based default columns for common AWS queries

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

# Filter by values (partial match, case-insensitive on ANY field)
awsquery ec2 describe-instances prod web

# Specify output columns (partial match, case-insensitive)
awsquery ec2 describe-instances prod -- Name State InstanceId

# List S3 buckets containing "backup" (matches if "backup" appears anywhere in any field)
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

### Discovery and Debug
```bash
# List available services
awsquery

# Debug mode for troubleshooting
awsquery -d ec2 describe-instances
```

## Command Structure

```
awsquery [-j|--json] [-k|--keys] [-d|--debug] [--region REGION] [--profile PROFILE] SERVICE ACTION [VALUE_FILTERS...] [-- TABLE_OUTPUT_FILTERS...]
```

- **SERVICE**: AWS service name (ec2, s3, iam, etc.)
- **ACTION**: Service action (describe-instances, list-buckets, etc.)
- **VALUE_FILTERS**: Space-separated filters - ALL must match, using case-insensitive partial matching on any field
- **TABLE_OUTPUT_FILTERS**: Column selection - partial, case-insensitive matching on column names
- **-j, --json**: Output results in JSON format instead of table
- **-k, --keys**: Show all available keys for the command
- **-d, --debug**: Enable debug output for troubleshooting
- **--region REGION**: AWS region to use for requests (e.g., us-west-2)
- **--profile PROFILE**: AWS profile to use from ~/.aws/credentials

## Security

- **ReadOnly Enforcement**: Only AWS ReadOnly policy actions are permitted
- **Input Sanitization**: Prevents injection attacks through parameter validation
- **Policy Validation**: All actions validated against policy.json before execution
- **Wildcard Matching**: Supports AWS IAM wildcard patterns (e.g., `ec2:Describe*`)
- **Session Isolation**: Each profile/region maintains separate boto3 sessions
- **Automatic Policy Updates**: Can fetch latest AWS ReadOnly policy via `make update-policy`
- **Security Testing**: Comprehensive test suite validates security constraints

## Examples

```bash
# Find instances with "prod" AND "web" in any field (partial match)
# e.g., matches "production-web-server", "web.prod.example.com"
awsquery ec2 describe-instances prod web

# Show only columns matching Name, State and InstanceId (partial match)
# e.g., "Name" matches "InstanceName", "Tags.Name", "SecurityGroupName"
awsquery ec2 describe-instances prod web -- Name State InstanceId

# Find S3 buckets with "backup" anywhere in the data
# e.g., matches "my-backup-bucket", "bucket-backup-2024", "backups"
awsquery s3 list-buckets backup

# Multi-level CloudFormation query with parameter resolution
# Filters: "prod" in stack data, columns containing "Created" or "StackName"
awsquery cloudformation describe-stack-events prod -- Created StackName

# Discover all available keys
awsquery -k ec2 describe-instances

# JSON output with filtering (partial column name matching)
awsquery -j ec2 describe-instances prod -- InstanceId State.Name

# Debug mode for troubleshooting
awsquery -d cloudformation describe-stack-resources workers -- EKS

# Use specific AWS region
awsquery --region eu-west-1 ec2 describe-instances

# Use specific AWS profile
awsquery --profile production s3 list-buckets

# Combine region and profile
awsquery --region us-east-2 --profile dev ec2 describe-vpcs

# View transformed tags (partial match on column names)
# Shows any column containing "Tags.Name" or "Tags.Environment"
awsquery ec2 describe-instances -- Tags.Name Tags.Environment
```

## Configuration

### AWS Credentials

Ensure AWS credentials are configured via:
- `~/.aws/credentials` (supports multiple profiles)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (if running on EC2/ECS/Lambda)
- AWS SSO profiles

### Default Filters Configuration

The tool uses `default_filters.yaml` to define default columns for common queries. This file is loaded from the package directory and will
provide you with standard columns if you don't add any.

Example configuration:
```yaml
ec2:
  describe_instances:
    columns:
      - InstanceId
      - Tags.Name
      - State.Name
      - InstanceType
      - PrivateIpAddress

s3:
  list_buckets:
    columns:
      - Name
      - CreationDate
```

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
make test-critical  # Run critical path tests only

# Code formatting and linting
make format
make format-check  # Check without modifying
make lint
make type-check
make security-check  # Run security analysis

# Pre-commit hooks
make pre-commit  # Run all pre-commit hooks

# Continuous Integration
make ci  # Run all CI checks
```

### Policy Management

```bash
# Update policy.json with latest AWS ReadOnly managed policy
make update-policy

# Validate policy.json structure
make validate-policy
```

### Docker Usage

```bash
# Build development container
make docker-build

# Open interactive shell
make shell

# Run tests in Docker
make test-in-docker

# Clean Docker artifacts
make docker-clean
```

### Development Workflow

```bash
# Watch tests (auto-run on file changes)
make watch-tests

# Build distribution packages
make build

# Clean build artifacts
make clean

# Publish to Test PyPI
make publish-test

# Publish to PyPI (production)
make publish

# Version management
make version  # Show current version
make release  # Create a new release with version bump
```

## Advanced Usage

### Partial Matching Behavior

All filters in awsquery use **case-insensitive partial matching**:

#### Value Filters (before `--`)
- Match against ANY field in the response data
- ALL specified filters must match (AND logic)
- Case-insensitive substring matching

```bash
# "prod" matches: "production", "prod-server", "my-prod-app"
awsquery ec2 describe-instances prod

# Both "prod" AND "web" must appear (in any fields)
awsquery ec2 describe-instances prod web

# "i-123" matches any instance ID starting with "i-123"
awsquery ec2 describe-instances i-123
```

#### Column Filters (after `--`)
- Match against column/field names in the output
- Partial, case-insensitive matching on column names
- Multiple columns can be specified

```bash
# "Instance" matches: "InstanceId", "InstanceType", "InstanceName"
awsquery ec2 describe-instances -- Instance

# Shows columns containing "Tag", "State", or "IP"
awsquery ec2 describe-instances -- Tag State IP

# Nested field matching
awsquery ec2 describe-instances -- State.Name Tags.Environment
```

### Multi-Level API Calls

The tool automatically handles parameter resolution for nested API calls:

```bash
# Automatically fetches stack list, then events for matching stacks
awsquery cloudformation describe-stack-events production

# Three-level call: list stacks → get resources → filter results
awsquery cloudformation describe-stack-resources prod -- Lambda
```

### Filtering Strategies

```bash
# All filters must match (AND logic), each using partial matching
# Finds instances where ALL three terms appear somewhere in the data
awsquery ec2 describe-instances production web database

# Column filters use partial, case-insensitive matching
# Shows columns containing "Instance", "State", or "Private" in their names
awsquery ec2 describe-instances -- Instance State Private

# Combine value and column filters
# Finds buckets with "backup" in any field, shows Name and Creation columns
awsquery s3 list-buckets backup -- Name Creation

# Partial matching examples:
# "prod" matches "production", "prod-server", "myproduct"
# "PROD" matches "production" (case-insensitive)
# "i-123" matches "i-1234567890abcdef0"
```

### Performance Tips

- Use specific filters to reduce API calls
- Column filters (`--`) don't affect API calls, only display
- Use `--region` to avoid cross-region latency
- Keys mode (`-k`) adds overhead; use only for discovery

## Troubleshooting

### Common Issues

**"No matching resources found"**
- Check your filters are not too restrictive
- Use debug mode (`-d`) to see actual API responses
- Verify you have permissions in the target region/account

**"Access Denied" errors**
- Ensure your AWS credentials have ReadOnly permissions
- Check if using the correct profile with `--profile`
- Verify the action is in the ReadOnly policy

**"Parameter validation failed"**
- Some APIs require specific parameters
- The tool attempts automatic resolution but may need manual input
- Use debug mode to see the parameter resolution process

**Performance issues**
- Large result sets may take time to process
- Use more specific filters to reduce data volume
- Consider using `--region` to target specific regions

## Requirements

The tool requires a `policy.json` file containing the AWS ReadOnly policy for security validation. This file is included automatically when installing via pip. The package dependencies are:

- boto3>=1.35.0
- botocore>=1.35.0
- tabulate>=0.9.0
- argcomplete>=3.0.0
- PyYAML>=6.0.0

## License

MIT License - see LICENSE file for details.

## Contributing

Please see CONTRIBUTING.md for development guidelines and testing procedures.
