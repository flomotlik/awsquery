# awsquery Validation Scripts

This directory contains scripts for validating awsquery functionality in real AWS environments.

## validate-awsquery.sh

Comprehensive validation script that tests awsquery across multiple AWS services with various options.

### Features

- **Comprehensive Coverage**: Tests 20+ AWS services including EC2, EKS, Lambda, S3, RDS, and more
- **Multiple Test Patterns**: Basic queries, multi-step calls, filtering, JSON output, parameter hints
- **Production-Ready**: Designed for real customer environments with actual resources
- **Detailed Reporting**: Color-coded output with pass/fail counts and success rate
- **Flexible Configuration**: Support for different regions and AWS profiles
- **Smart Skipping**: Skips tests when resources don't exist (won't fail unnecessarily)

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

### Test Categories

The script tests the following AWS services and features:

#### Core Services
- **EC2**: Instances, security groups, VPCs, subnets, volumes, network interfaces
- **S3**: Buckets with filtering and JSON output
- **IAM**: Users, roles, policies, groups
- **Lambda**: Functions with column filtering

#### Container & Orchestration
- **EKS**: Clusters, nodegroups (with multi-step resolution)
- **ECS**: Clusters, tasks (with field override hints)
- **ECR**: Repositories
- **Auto Scaling**: Groups and launch configurations

#### Database Services
- **RDS**: DB instances and clusters
- **DynamoDB**: Tables

#### Messaging & Queuing
- **SQS**: Queues
- **SNS**: Topics

#### Infrastructure & Management
- **CloudFormation**: Stacks and stack events (multi-step)
- **ELB/ALB**: Load balancers, target groups, tags (multi-step)
- **CloudWatch**: Alarms
- **SSM**: Parameters (with limit testing)
- **Secrets Manager**: Secrets
- **KMS**: Keys

#### Advanced Features Tested
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

The script provides color-coded output:
- 🔵 **[INFO]**: Informational messages
- 🟢 **[PASS]**: Test passed successfully
- 🔴 **[FAIL]**: Test failed
- 🟡 **[WARN]**: Warning (e.g., fewer results than expected)
- 🟡 **[SKIP]**: Test skipped (no resources found)

### Example Output

```
========================================================================
  awsquery Validation Script
========================================================================
Region:  us-east-1
Profile: production
Verbose: false
========================================================================

[INFO] Starting validation tests...

--- EC2 Tests ---
[PASS] EC2: List instances (basic)
[PASS] EC2: List instances with column filter
[PASS] EC2: List instances with value filter
[PASS] EC2: List instances with JSON output
[PASS] EC2: List instances with --keys flag
...

--- Lambda Tests ---
[PASS] Lambda: List functions
[PASS] Lambda: List functions with column filter
...

========================================================================
  Validation Summary
========================================================================
Total Tests:   75
Passed:        73
Failed:        0
Skipped:       2
========================================================================

Success Rate: 97%

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
   # In your CI pipeline
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

**Issue**: All tests are skipped
- **Solution**: The environment might not have resources - try in a region with active resources

### Contributing

To add new test cases:

1. Follow the existing test pattern using `run_test` function
2. Group related tests under service-specific sections
3. Use appropriate expected patterns for validation
4. Consider adding skip logic for services that might not have resources
5. Update this README with new services/features tested
