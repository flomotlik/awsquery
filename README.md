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

## Requirements

```bash
pip install boto3 tabulate argcomplete
```

## Usage

### Basic Query
```bash
# Query EC2 instances with filtering
./awsquery.py ec2 describe_instances

# Filter by values (partial match, case-insensitive)
./awsquery.py ec2 describe_instances prod web

# Specify output columns
./awsquery.py ec2 describe_instances prod -- Name State InstanceId

# List S3 buckets containing "backup"
./awsquery.py s3 list_buckets backup
```

### Keys Discovery
```bash
# Show available fields/keys from an API response
./awsquery.py keys ec2 describe_instances
./awsquery.py keys s3 list_buckets
```

### Safety Features
```bash
# Dry run - shows what would be executed
./awsquery.py --dry-run ec2 describe_instances

# List available services
./awsquery.py
```

## Command Structure

```
awsquery [--dry-run] SERVICE ACTION [VALUE_FILTERS...] [-- TABLE_OUTPUT_FILTERS...]
awsquery keys SERVICE ACTION
```

- **SERVICE**: AWS service name (ec2, s3, iam, etc.)
- **ACTION**: Service action (describe_instances, list_buckets, etc.)  
- **VALUE_FILTERS**: Space-separated filters (ALL must match any field)
- **TABLE_OUTPUT_FILTERS**: Column selection (partial name matching)

## Security

- Only ReadOnly AWS policy actions are permitted
- Input sanitization prevents injection attacks
- Actions validated against policy.json before execution
- All security validation relies on the included policy.json file

## Examples

```bash
# Find instances with "prod" and "web" in any field
./awsquery.py ec2 describe_instances prod web

# Show only Name, State and InstanceId columns  
./awsquery.py ec2 describe_instances prod web -- Name State InstanceId

# Find S3 buckets with "backup" in name
./awsquery.py s3 list_buckets backup

# Discover all available keys
./awsquery.py keys ec2 describe_instances

# Safe testing mode
./awsquery.py --dry-run ec2 describe_instances
```

## Configuration

Ensure AWS credentials are configured via:
- `~/.aws/credentials`
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (if running on EC2)

## Requirements

The tool requires a `policy.json` file containing the AWS ReadOnly policy for security validation. This file will be included automatically when installing via pip. For manual installation, ensure the policy.json file is in the same directory as the script.
