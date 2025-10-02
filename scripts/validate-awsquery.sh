#!/usr/bin/env bash
#
# Comprehensive validation script for awsquery in production AWS environments
#
# This script tests awsquery across multiple AWS services with various options
# to ensure all functionality works correctly with real resources.
#
# Usage:
#   ./scripts/validate-awsquery.sh [--region REGION] [--profile PROFILE] [--verbose]
#
# Options:
#   --region REGION    AWS region to test (default: uses AWS_REGION or us-east-1)
#   --profile PROFILE  AWS profile to use (default: uses AWS_PROFILE or default)
#   --verbose          Show detailed output for each test
#   --help             Show this help message
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Configuration
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"
VERBOSE=false
AWSQUERY_CMD="awsquery"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            head -n 20 "$0" | tail -n +2 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build base awsquery command with region/profile
BASE_CMD="$AWSQUERY_CMD --region $REGION --profile $PROFILE"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $*"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $*"
}

# Test execution function
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    local expected_pattern="${3:-.*}"  # Default: any output
    local min_results="${4:-0}"        # Default: no minimum

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [[ "$VERBOSE" == "true" ]]; then
        log_info "Running: $test_name"
        log_info "Command: $test_cmd"
    fi

    local output
    local exit_code=0

    # Run command and capture output
    output=$(eval "$test_cmd" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_error "$test_name"
        if [[ "$VERBOSE" == "true" ]]; then
            echo "Exit code: $exit_code"
            echo "Output: $output"
        fi
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    # Check if output matches expected pattern
    if ! echo "$output" | grep -qE "$expected_pattern"; then
        log_error "$test_name - Output doesn't match expected pattern"
        if [[ "$VERBOSE" == "true" ]]; then
            echo "Expected pattern: $expected_pattern"
            echo "Output: $output"
        fi
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    # Check minimum number of results (count lines, excluding headers)
    if [[ $min_results -gt 0 ]]; then
        local line_count
        line_count=$(echo "$output" | grep -v "^Available services:" | wc -l | tr -d ' ')
        if [[ $line_count -lt $min_results ]]; then
            log_warning "$test_name - Expected at least $min_results results, got $line_count"
            # Don't fail, just warn - might be legitimately empty
        fi
    fi

    log_success "$test_name"
    PASSED_TESTS=$((PASSED_TESTS + 1))

    if [[ "$VERBOSE" == "true" ]]; then
        echo "Output preview:"
        echo "$output" | head -20
        echo ""
    fi

    return 0
}

# Skip test if service has no resources
skip_if_empty() {
    local test_name="$1"
    local check_cmd="$2"

    if ! eval "$check_cmd" > /dev/null 2>&1; then
        log_skip "$test_name - No resources found"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
        return 0
    fi
    return 1
}

# Print header
echo ""
echo "========================================================================"
echo "  awsquery Validation Script"
echo "========================================================================"
echo "Region:  $REGION"
echo "Profile: $PROFILE"
echo "Verbose: $VERBOSE"
echo "========================================================================"
echo ""

# Verify awsquery is available
if ! command -v "$AWSQUERY_CMD" &> /dev/null; then
    log_error "awsquery command not found in PATH"
    log_info "Install with: pip install -e ."
    exit 1
fi

log_info "Starting validation tests..."
echo ""

# ============================================================================
# EC2 Tests
# ============================================================================
echo "--- EC2 Tests ---"

run_test "EC2: List instances (basic)" \
    "$BASE_CMD ec2 describe-instances" \
    ".*"

run_test "EC2: List instances with column filter" \
    "$BASE_CMD ec2 describe-instances -- InstanceId State.Name" \
    "(InstanceId|i-[a-f0-9]+)"

run_test "EC2: List instances with value filter" \
    "$BASE_CMD ec2 describe-instances running" \
    ".*"

run_test "EC2: List instances with JSON output" \
    "$BASE_CMD ec2 describe-instances --json" \
    "^\[.*\]$|^\{\}"

run_test "EC2: List instances with --keys flag" \
    "$BASE_CMD ec2 describe-instances --keys" \
    "(InstanceId|State|LaunchTime)"

run_test "EC2: Multi-step - describe network interfaces" \
    "$BASE_CMD ec2 describe-network-interfaces" \
    ".*"

run_test "EC2: List security groups" \
    "$BASE_CMD ec2 describe-security-groups" \
    "(GroupId|sg-[a-f0-9]+|GroupName)"

run_test "EC2: List VPCs" \
    "$BASE_CMD ec2 describe-vpcs" \
    "(VpcId|vpc-[a-f0-9]+)"

run_test "EC2: List subnets" \
    "$BASE_CMD ec2 describe-subnets" \
    "(SubnetId|subnet-[a-f0-9]+)"

run_test "EC2: List volumes" \
    "$BASE_CMD ec2 describe-volumes" \
    ".*"

echo ""

# ============================================================================
# Auto Scaling Tests
# ============================================================================
echo "--- Auto Scaling Tests ---"

run_test "AutoScaling: List auto scaling groups" \
    "$BASE_CMD autoscaling describe-auto-scaling-groups" \
    ".*"

run_test "AutoScaling: List launch configurations" \
    "$BASE_CMD autoscaling describe-launch-configurations" \
    ".*"

echo ""

# ============================================================================
# EKS Tests
# ============================================================================
echo "--- EKS Tests ---"

run_test "EKS: List clusters" \
    "$BASE_CMD eks list-clusters" \
    ".*"

# Only run nodegroup test if clusters exist
if $BASE_CMD eks list-clusters 2>&1 | grep -q "\S"; then
    run_test "EKS: Multi-step - describe nodegroups (with -i hint)" \
        "$BASE_CMD eks describe-nodegroup -i list-clus:cluster" \
        ".*"
fi

echo ""

# ============================================================================
# Lambda Tests
# ============================================================================
echo "--- Lambda Tests ---"

run_test "Lambda: List functions" \
    "$BASE_CMD lambda list-functions" \
    ".*"

run_test "Lambda: List functions with column filter" \
    "$BASE_CMD lambda list-functions -- FunctionName Runtime" \
    "(FunctionName|Runtime|python|nodejs|java)"

echo ""

# ============================================================================
# S3 Tests
# ============================================================================
echo "--- S3 Tests ---"

run_test "S3: List buckets" \
    "$BASE_CMD s3 list-buckets" \
    "(Name|CreationDate)"

run_test "S3: List buckets with filter" \
    "$BASE_CMD s3 list-buckets backup" \
    ".*"

run_test "S3: List buckets with JSON output" \
    "$BASE_CMD s3 list-buckets --json" \
    "^\[.*\]$|^\{\}"

echo ""

# ============================================================================
# IAM Tests
# ============================================================================
echo "--- IAM Tests ---"

run_test "IAM: List users" \
    "$BASE_CMD iam list-users" \
    ".*"

run_test "IAM: List roles" \
    "$BASE_CMD iam list-roles" \
    "(RoleName|Arn)"

run_test "IAM: List policies" \
    "$BASE_CMD iam list-policies" \
    ".*"

run_test "IAM: List groups" \
    "$BASE_CMD iam list-groups" \
    ".*"

echo ""

# ============================================================================
# SQS Tests
# ============================================================================
echo "--- SQS Tests ---"

run_test "SQS: List queues" \
    "$BASE_CMD sqs list-queues" \
    ".*"

echo ""

# ============================================================================
# SNS Tests
# ============================================================================
echo "--- SNS Tests ---"

run_test "SNS: List topics" \
    "$BASE_CMD sns list-topics" \
    ".*"

echo ""

# ============================================================================
# DynamoDB Tests
# ============================================================================
echo "--- DynamoDB Tests ---"

run_test "DynamoDB: List tables" \
    "$BASE_CMD dynamodb list-tables" \
    ".*"

echo ""

# ============================================================================
# CloudFormation Tests
# ============================================================================
echo "--- CloudFormation Tests ---"

run_test "CloudFormation: List stacks" \
    "$BASE_CMD cloudformation list-stacks" \
    ".*"

run_test "CloudFormation: Describe stacks" \
    "$BASE_CMD cloudformation describe-stacks" \
    ".*"

# Only run stack events test if stacks exist
if $BASE_CMD cloudformation list-stacks 2>&1 | grep -q "StackName"; then
    run_test "CloudFormation: Multi-step - describe stack events" \
        "$BASE_CMD cloudformation describe-stack-events prod -- StackName ResourceStatus" \
        ".*"
fi

echo ""

# ============================================================================
# ELB/ALB Tests
# ============================================================================
echo "--- ELB/ALB Tests ---"

run_test "ELBv2: List load balancers" \
    "$BASE_CMD elbv2 describe-load-balancers" \
    ".*"

run_test "ELBv2: List target groups" \
    "$BASE_CMD elbv2 describe-target-groups" \
    ".*"

# Only run tags test if load balancers exist
if $BASE_CMD elbv2 describe-load-balancers 2>&1 | grep -q "LoadBalancerArn"; then
    run_test "ELBv2: Multi-step - describe tags with hint" \
        "$BASE_CMD elbv2 describe-tags -i desc-load:arn:3" \
        ".*"
fi

echo ""

# ============================================================================
# RDS Tests
# ============================================================================
echo "--- RDS Tests ---"

run_test "RDS: List DB instances" \
    "$BASE_CMD rds describe-db-instances" \
    ".*"

run_test "RDS: List DB clusters" \
    "$BASE_CMD rds describe-db-clusters" \
    ".*"

echo ""

# ============================================================================
# CloudWatch Tests
# ============================================================================
echo "--- CloudWatch Tests ---"

run_test "CloudWatch: List alarms" \
    "$BASE_CMD cloudwatch describe-alarms" \
    ".*"

echo ""

# ============================================================================
# KMS Tests
# ============================================================================
echo "--- KMS Tests ---"

run_test "KMS: List keys" \
    "$BASE_CMD kms list-keys" \
    ".*"

echo ""

# ============================================================================
# Secrets Manager Tests
# ============================================================================
echo "--- Secrets Manager Tests ---"

run_test "SecretsManager: List secrets" \
    "$BASE_CMD secretsmanager list-secrets" \
    ".*"

echo ""

# ============================================================================
# Systems Manager (SSM) Tests
# ============================================================================
echo "--- SSM Tests ---"

run_test "SSM: List parameters" \
    "$BASE_CMD ssm describe-parameters" \
    ".*"

# Test parameter retrieval with limit
run_test "SSM: Get parameters with limit" \
    "$BASE_CMD ssm get-parameters -i ::5" \
    ".*"

echo ""

# ============================================================================
# ECR Tests
# ============================================================================
echo "--- ECR Tests ---"

run_test "ECR: List repositories" \
    "$BASE_CMD ecr describe-repositories" \
    ".*"

echo ""

# ============================================================================
# ECS Tests
# ============================================================================
echo "--- ECS Tests ---"

run_test "ECS: List clusters" \
    "$BASE_CMD ecs list-clusters" \
    ".*"

# Only run task tests if clusters exist
if $BASE_CMD ecs list-clusters 2>&1 | grep -q "clusterArn"; then
    run_test "ECS: Multi-step - describe tasks with field override" \
        "$BASE_CMD ecs describe-tasks -i :clusterarn" \
        ".*"
fi

echo ""

# ============================================================================
# Advanced Feature Tests
# ============================================================================
echo "--- Advanced Features Tests ---"

run_test "Advanced: Parameter propagation (-p flag)" \
    "$BASE_CMD ec2 describe-instances -p MaxResults=5" \
    ".*"

run_test "Advanced: Debug mode" \
    "$BASE_CMD ec2 describe-instances --debug" \
    "(DEBUG:|describe-instances)"

run_test "Advanced: Multiple filters with separator" \
    "$BASE_CMD ec2 describe-instances running web -- InstanceId State" \
    ".*"

echo ""

# ============================================================================
# Print Summary
# ============================================================================
echo ""
echo "========================================================================"
echo "  Validation Summary"
echo "========================================================================"
echo "Total Tests:   $TOTAL_TESTS"
echo -e "Passed:        ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed:        ${RED}$FAILED_TESTS${NC}"
echo -e "Skipped:       ${YELLOW}$SKIPPED_TESTS${NC}"
echo "========================================================================"
echo ""

# Calculate success rate
if [[ $TOTAL_TESTS -gt 0 ]]; then
    SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo "Success Rate: $SUCCESS_RATE%"
    echo ""
fi

# Exit with appropriate code
if [[ $FAILED_TESTS -gt 0 ]]; then
    log_error "Validation FAILED - $FAILED_TESTS test(s) failed"
    exit 1
else
    log_success "Validation PASSED - All tests succeeded!"
    exit 0
fi
