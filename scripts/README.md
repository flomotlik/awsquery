# awsquery Validation Scripts

This directory contains production validation scripts for testing awsquery in real AWS environments.

## validate-awsquery.sh

Comprehensive validation script that tests awsquery across 30+ AWS services with 120+ operations.

### Features

- **Comprehensive Coverage**: Tests EC2, EKS, Lambda, S3, RDS, DynamoDB, IAM, and 25+ other services
- **Multiple Test Patterns**: Basic queries, multi-step calls, filtering, JSON output, parameter hints
- **Production-Ready**: Designed for real customer environments with actual resources
- **Detailed Reporting**: Color-coded output with pass/fail counts and success rate
- **Flexible Configuration**: Support for different regions and AWS profiles

### Usage

Basic usage (uses default region and profile):
```bash
./scripts/validate-awsquery.sh
```

Specify region and profile:
```bash
./scripts/validate-awsquery.sh --region us-west-2 --profile production
```

Verbose output (shows command details and output previews):
```bash
./scripts/validate-awsquery.sh --verbose
```

Show help:
```bash
./scripts/validate-awsquery.sh --help
```

### Services Tested

The script validates awsquery across these AWS services:

#### Compute & Containers
- **EC2**: Instances, security groups, VPCs, subnets, volumes, snapshots, images, key pairs, addresses, NAT gateways, internet gateways, route tables, VPC peering
- **EKS**: Clusters, nodegroups, addons (multi-step)
- **ECS**: Clusters, services, tasks, task definitions (multi-step)
- **ECR**: Repositories, images (multi-step)
- **Lambda**: Functions, layers, event source mappings
- **Auto Scaling**: Groups, launch configurations, policies, scheduled actions

#### Database Services
- **RDS**: DB instances, clusters, snapshots, subnet groups, parameter groups
- **DynamoDB**: Tables, backups, describe-table (multi-step)
- **ElastiCache**: Cache clusters, replication groups
- **Redshift**: Clusters

#### Storage & Content
- **S3**: Buckets with filtering and JSON output

#### Networking & API
- **ELB/ALB**: Load balancers, target groups, listeners, tags (multi-step)
- **Route53**: Hosted zones, health checks
- **API Gateway**: REST APIs, resources (multi-step)
- **API Gateway v2**: HTTP APIs

#### Security & Identity
- **IAM**: Users, roles, policies, groups, instance profiles, access keys (multi-step)
- **KMS**: Keys, aliases, describe-key (multi-step)
- **Secrets Manager**: Secrets
- **ACM**: Certificates

#### Management & Governance
- **CloudFormation**: Stacks, stack events, stack resources (multi-step)
- **CloudWatch**: Alarms, metrics, alarm history (multi-step)
- **CloudTrail**: Trails
- **Config**: Configuration recorders, delivery channels
- **SSM**: Parameters, patch baselines, maintenance windows
- **Backup**: Backup vaults, plans

#### Application Integration
- **SQS**: Queues
- **SNS**: Topics, subscriptions
- **EventBridge**: Event buses, rules
- **Step Functions**: State machines

#### Analytics & Data
- **Glue**: Databases, jobs
- **Athena**: Work groups, data catalogs

### Advanced Features Tested

- Parameter propagation (`-p` flag)
- Multi-step resolution with hints (`-i` flag)
- Field override (`:field` syntax)
- Result limiting (`::N` syntax)
- Column filtering (`--` separator)
- Value filtering (resource name patterns)
- JSON output (`--json`)
- Keys mode (`--keys`)
- Debug mode (`--debug`)

### Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed

### Output Format

Color-coded output:
- 🔵 **[INFO]**: Informational messages
- 🟢 **[PASS]**: Test passed successfully
- 🔴 **[FAIL]**: Test failed

### Example Output

```
========================================================================
  awsquery Validation Script
========================================================================
Region: us-east-1 | Profile: production | Verbose: false
========================================================================

[INFO] Starting validation tests...

--- EC2 Tests ---
[PASS] EC2: describe-instances
[PASS] EC2: describe-instances with columns
[PASS] EC2: describe-instances filter
[PASS] EC2: describe-instances JSON
[PASS] EC2: describe-instances --keys
[PASS] EC2: describe-security-groups
...

--- Lambda Tests ---
[PASS] Lambda: list-functions
[PASS] Lambda: list-functions with columns
[PASS] Lambda: list-layers
...

========================================================================
  Validation Summary
========================================================================
Total Tests: 120
Passed: 120
Failed: 0
Success Rate: 100%
========================================================================

[PASS] Validation PASSED - All tests succeeded!
```

### Requirements

- `awsquery` installed and in PATH
- Valid AWS credentials configured
- Appropriate IAM permissions for read-only operations across tested services
- `bash` 4.0 or higher

### Tips for Production Use

1. **Start with verbose mode** to see what commands are being run:
   ```bash
   ./scripts/validate-awsquery.sh --verbose | tee validation.log
   ```

2. **Test in multiple regions** to ensure cross-region functionality:
   ```bash
   for region in us-east-1 us-west-2 eu-west-1; do
       echo "Testing $region..."
       ./scripts/validate-awsquery.sh --region $region
   done
   ```

3. **Use with CI/CD** - The script exits with non-zero on failure:
   ```bash
   ./scripts/validate-awsquery.sh || exit 1
   ```

4. **Save results** for later analysis:
   ```bash
   ./scripts/validate-awsquery.sh --verbose > validation-$(date +%Y%m%d).log 2>&1
   ```

### Troubleshooting

**Issue**: Script reports "awsquery command not found"
- **Solution**: Install awsquery with `pip install -e .` from the project root

**Issue**: Many tests fail with authentication errors
- **Solution**: Check your AWS credentials and profile configuration

**Issue**: Tests fail for specific services
- **Solution**: Verify IAM permissions for those services (script only needs read permissions)

**Issue**: Tests fail due to missing resources
- **Solution**: The script expects resources to exist; test in environments with active AWS resources
