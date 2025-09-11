# awsquery - AWS API Query Tool

CLI tool to call the AWS API through boto3 with flexible filtering similar to awsinfo.

## Features

- Query AWS APIs with flexible value-based filtering
- Security validation against ReadOnly AWS policy
- Tabular output with customizable columns  
- Auto-completion support (with argcomplete)
- Pagination support for large responses
- Dry-run mode for safe testing
- Keys discovery command

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
