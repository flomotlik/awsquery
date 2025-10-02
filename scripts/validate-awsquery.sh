#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"
VERBOSE=false
AWSQUERY_CMD="awsquery"

while [[ $# -gt 0 ]]; do
    case $1 in
        --region) REGION="$2"; shift 2 ;;
        --profile) PROFILE="$2"; shift 2 ;;
        --verbose) VERBOSE=true; shift ;;
        --help) echo "Usage: $0 [--region REGION] [--profile PROFILE] [--verbose]"; exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

BASE_CMD="$AWSQUERY_CMD --region $REGION --profile $PROFILE"

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_error() { echo -e "${RED}[FAIL]${NC} $*"; }

is_failure_output() {
    local output="$1"
    # Reject any error messages or empty result indicators
    echo "$output" | grep -qE "(^ERROR:|No results found|No matching columns found)"
}

run_test() {
    local test_name="$1"
    local test_cmd="$2"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    [[ "$VERBOSE" == "true" ]] && log_info "Running: $test_name"

    local output
    local exit_code=0
    output=$(eval "$test_cmd" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 0 ]] || is_failure_output "$output"; then
        log_error "$test_name"
        [[ "$VERBOSE" == "true" ]] && echo "Output: $output"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    log_success "$test_name"
    PASSED_TESTS=$((PASSED_TESTS + 1))
    [[ "$VERBOSE" == "true" ]] && echo "$output" | head -20 && echo ""
    return 0
}

echo ""
echo "========================================================================"
echo "  awsquery Validation Script - Comprehensive Feature Testing"
echo "========================================================================"
echo "Region: $REGION | Profile: $PROFILE | Verbose: $VERBOSE"
echo "========================================================================"
echo ""

command -v "$AWSQUERY_CMD" &> /dev/null || { log_error "awsquery not found"; exit 1; }
log_info "Starting validation tests..."
echo ""

# =============================================================================
# CORE FEATURE TESTS - Each test validates specific features
# =============================================================================

echo "--- Basic Query Tests (no filters) ---"
run_test "Basic: EC2 instances" "$BASE_CMD ec2 describe-instances"
run_test "Basic: S3 buckets" "$BASE_CMD s3 list-buckets"
run_test "Basic: IAM users" "$BASE_CMD iam list-users"
echo ""

echo "--- Column Filtering Tests (--) ---"
run_test "Columns: Single column" "$BASE_CMD ec2 describe-instances -- InstanceId"
run_test "Columns: Multiple columns" "$BASE_CMD ec2 describe-instances -- InstanceId State.Name InstanceType"
run_test "Columns: Nested fields" "$BASE_CMD s3 list-buckets -- Name CreationDate"
run_test "Columns: Deep nesting" "$BASE_CMD iam list-users -- UserName CreateDate Arn"
echo ""

echo "--- Value Filtering Tests (filter words) ---"
run_test "Filter: Single word" "$BASE_CMD ec2 describe-instances running"
run_test "Filter: Multiple words" "$BASE_CMD ec2 describe-instances running web"
run_test "Filter: With columns" "$BASE_CMD iam list-users admin -- UserName CreateDate"
echo ""

echo "--- Output Format Tests (--json) ---"
run_test "JSON: Simple output" "$BASE_CMD s3 list-buckets --json"
run_test "JSON: With columns" "$BASE_CMD ec2 describe-instances --json -- InstanceId State"
run_test "JSON: With filters" "$BASE_CMD iam list-users --json service"
echo ""

echo "--- Keys Mode Tests (--keys) ---"
run_test "Keys: Simple service" "$BASE_CMD s3 list-buckets --keys"
run_test "Keys: Complex service" "$BASE_CMD ec2 describe-instances --keys"
run_test "Keys: With filters" "$BASE_CMD iam list-users admin --keys"
echo ""

echo "--- Debug Mode Tests (--debug) ---"
run_test "Debug: Basic query" "$BASE_CMD ec2 describe-instances --debug"
run_test "Debug: With all features" "$BASE_CMD ec2 describe-instances running --debug -- InstanceId State"
echo ""

echo "--- Parameter Tests (-p/--parameter) ---"
run_test "Parameter: Single value auto-wrap" "$BASE_CMD ec2 describe-snapshots -p OwnerIds=self"
run_test "Parameter: List parameter" "$BASE_CMD ec2 describe-images -p Owners=self"
run_test "Parameter: MaxResults" "$BASE_CMD ec2 describe-instances -p MaxResults=5"
run_test "Parameter: Multiple params" "$BASE_CMD lambda list-functions -p MaxItems=10 -p FunctionVersion=ALL"
echo ""

echo "--- Multi-Level Resolution Tests (-i/--input hints) ---"
run_test "Multi-level: Function hint" "$BASE_CMD eks describe-nodegroup -i list-clus:cluster"
run_test "Multi-level: Field hint only" "$BASE_CMD iam list-access-keys -i :username"
run_test "Multi-level: Limit only" "$BASE_CMD ssm get-parameters -i ::5"
run_test "Multi-level: All hints" "$BASE_CMD elbv2 describe-tags -i desc-load:arn:3"
run_test "Multi-level: With filters" "$BASE_CMD cloudformation describe-stack-events prod -- StackName ResourceStatus"
echo ""

echo "--- Resource Filters (before --) ---"
run_test "Resource filter: Basic" "$BASE_CMD cloudformation list-stack-resources prod"
run_test "Resource filter: Multiple" "$BASE_CMD eks list-nodegroups prod web"
echo ""

echo "--- Combined Features Tests ---"
run_test "Combined: -p + columns" "$BASE_CMD ec2 describe-instances -p MaxResults=10 -- InstanceId State"
run_test "Combined: Filter + JSON + columns" "$BASE_CMD iam list-users admin --json -- UserName Arn"
run_test "Combined: -i + filter + columns" "$BASE_CMD cloudformation describe-stack-events prod -- StackName Timestamp"
run_test "Combined: -p + filter + JSON" "$BASE_CMD lambda list-functions --json -p MaxItems=5"
run_test "Combined: All features" "$BASE_CMD ec2 describe-instances running -p MaxResults=5 --debug -- InstanceId State"
echo ""

echo "--- Service Coverage Tests ---"
run_test "Service: Lambda functions" "$BASE_CMD lambda list-functions"
run_test "Service: DynamoDB tables" "$BASE_CMD dynamodb list-tables"
run_test "Service: CloudFormation stacks" "$BASE_CMD cloudformation list-stacks"
run_test "Service: EKS clusters" "$BASE_CMD eks list-clusters"
run_test "Service: RDS instances" "$BASE_CMD rds describe-db-instances"
run_test "Service: ELBv2 load balancers" "$BASE_CMD elbv2 describe-load-balancers"
run_test "Service: SNS topics" "$BASE_CMD sns list-topics"
run_test "Service: SQS queues" "$BASE_CMD sqs list-queues"
run_test "Service: KMS keys" "$BASE_CMD kms list-keys"
run_test "Service: SSM parameters" "$BASE_CMD ssm describe-parameters"
echo ""

echo "--- Edge Cases & Error Handling ---"
run_test "Edge: Empty filters" "$BASE_CMD s3 list-buckets --"
run_test "Edge: --region override" "$AWSQUERY_CMD --region us-west-2 s3 list-buckets"
run_test "Edge: --profile with --region" "$AWSQUERY_CMD --region $REGION --profile $PROFILE ec2 describe-vpcs"
echo ""

echo ""
echo "========================================================================"
echo "  Validation Summary"
echo "========================================================================"
echo "Total Tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
[[ $TOTAL_TESTS -gt 0 ]] && echo "Success Rate: $((PASSED_TESTS * 100 / TOTAL_TESTS))%"
echo "========================================================================"
echo ""

if [[ $FAILED_TESTS -gt 0 ]]; then
    log_error "Validation FAILED - $FAILED_TESTS test(s) failed"
    exit 1
else
    log_success "Validation PASSED - All tests succeeded!"
    exit 0
fi
