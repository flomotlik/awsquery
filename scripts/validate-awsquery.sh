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
    local expected_pattern="${3:-.*}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    [[ "$VERBOSE" == "true" ]] && log_info "Running: $test_name"

    local output
    local exit_code=0
    output=$(eval "$test_cmd" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 0 ]] || is_failure_output "$output" || ! echo "$output" | grep -qE "$expected_pattern"; then
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
echo "  awsquery Validation Script"
echo "========================================================================"
echo "Region: $REGION | Profile: $PROFILE | Verbose: $VERBOSE"
echo "========================================================================"
echo ""

command -v "$AWSQUERY_CMD" &> /dev/null || { log_error "awsquery not found"; exit 1; }
log_info "Starting validation tests..."
echo ""

echo "--- EC2 Tests ---"
run_test "EC2: describe-instances" "$BASE_CMD ec2 describe-instances" ".*"
run_test "EC2: describe-instances with columns" "$BASE_CMD ec2 describe-instances -- InstanceId State.Name" "(InstanceId|i-[a-f0-9]+)"
run_test "EC2: describe-instances filter" "$BASE_CMD ec2 describe-instances running" ".*"
run_test "EC2: describe-instances JSON" "$BASE_CMD ec2 describe-instances --json" "^\[.*\]$|^\{\}"
run_test "EC2: describe-instances --keys" "$BASE_CMD ec2 describe-instances --keys" "(InstanceId|State|LaunchTime)"
run_test "EC2: describe-network-interfaces" "$BASE_CMD ec2 describe-network-interfaces" ".*"
run_test "EC2: describe-security-groups" "$BASE_CMD ec2 describe-security-groups" "(GroupId|sg-[a-f0-9]+)"
run_test "EC2: describe-vpcs" "$BASE_CMD ec2 describe-vpcs" "(VpcId|vpc-[a-f0-9]+)"
run_test "EC2: describe-subnets" "$BASE_CMD ec2 describe-subnets" "(SubnetId|subnet-[a-f0-9]+)"
run_test "EC2: describe-volumes" "$BASE_CMD ec2 describe-volumes" ".*"
run_test "EC2: describe-snapshots" "$BASE_CMD ec2 describe-snapshots --owner self" ".*"
run_test "EC2: describe-images" "$BASE_CMD ec2 describe-images --owner self" ".*"
run_test "EC2: describe-key-pairs" "$BASE_CMD ec2 describe-key-pairs" ".*"
run_test "EC2: describe-addresses" "$BASE_CMD ec2 describe-addresses" ".*"
run_test "EC2: describe-nat-gateways" "$BASE_CMD ec2 describe-nat-gateways" ".*"
run_test "EC2: describe-internet-gateways" "$BASE_CMD ec2 describe-internet-gateways" ".*"
run_test "EC2: describe-route-tables" "$BASE_CMD ec2 describe-route-tables" ".*"
run_test "EC2: describe-vpc-peering-connections" "$BASE_CMD ec2 describe-vpc-peering-connections" ".*"
echo ""

echo "--- Auto Scaling Tests ---"
run_test "AutoScaling: describe-auto-scaling-groups" "$BASE_CMD autoscaling describe-auto-scaling-groups" ".*"
run_test "AutoScaling: describe-launch-configurations" "$BASE_CMD autoscaling describe-launch-configurations" ".*"
run_test "AutoScaling: describe-scaling-policies" "$BASE_CMD autoscaling describe-policies" ".*"
run_test "AutoScaling: describe-scheduled-actions" "$BASE_CMD autoscaling describe-scheduled-actions" ".*"
echo ""

echo "--- EKS Tests ---"
run_test "EKS: list-clusters" "$BASE_CMD eks list-clusters" ".*"
run_test "EKS: describe-nodegroup multi-step" "$BASE_CMD eks describe-nodegroup -i list-clus:cluster" ".*"
run_test "EKS: list-addons multi-step" "$BASE_CMD eks list-addons -i list-clus:cluster" ".*"
echo ""

echo "--- Lambda Tests ---"
run_test "Lambda: list-functions" "$BASE_CMD lambda list-functions" ".*"
run_test "Lambda: list-functions with columns" "$BASE_CMD lambda list-functions -- FunctionName Runtime" "(FunctionName|Runtime|python|nodejs|java)"
run_test "Lambda: list-layers" "$BASE_CMD lambda list-layers" ".*"
run_test "Lambda: list-event-source-mappings" "$BASE_CMD lambda list-event-source-mappings" ".*"
echo ""

echo "--- S3 Tests ---"
run_test "S3: list-buckets" "$BASE_CMD s3 list-buckets" "(Name|CreationDate)"
run_test "S3: list-buckets filter" "$BASE_CMD s3 list-buckets backup" ".*"
run_test "S3: list-buckets JSON" "$BASE_CMD s3 list-buckets --json" "^\[.*\]$|^\{\}"
echo ""

echo "--- IAM Tests ---"
run_test "IAM: list-users" "$BASE_CMD iam list-users" ".*"
run_test "IAM: list-roles" "$BASE_CMD iam list-roles" "(RoleName|Arn)"
run_test "IAM: list-policies" "$BASE_CMD iam list-policies" ".*"
run_test "IAM: list-groups" "$BASE_CMD iam list-groups" ".*"
run_test "IAM: list-instance-profiles" "$BASE_CMD iam list-instance-profiles" ".*"
run_test "IAM: list-access-keys multi-step" "$BASE_CMD iam list-access-keys -i list-users:username" ".*"
echo ""

echo "--- SQS Tests ---"
run_test "SQS: list-queues" "$BASE_CMD sqs list-queues" ".*"
echo ""

echo "--- SNS Tests ---"
run_test "SNS: list-topics" "$BASE_CMD sns list-topics" ".*"
run_test "SNS: list-subscriptions" "$BASE_CMD sns list-subscriptions" ".*"
echo ""

echo "--- DynamoDB Tests ---"
run_test "DynamoDB: list-tables" "$BASE_CMD dynamodb list-tables" ".*"
run_test "DynamoDB: list-backups" "$BASE_CMD dynamodb list-backups" ".*"
run_test "DynamoDB: describe-table multi-step" "$BASE_CMD dynamodb describe-table -i list-tables:tablename" ".*"
echo ""

echo "--- CloudFormation Tests ---"
run_test "CloudFormation: list-stacks" "$BASE_CMD cloudformation list-stacks" ".*"
run_test "CloudFormation: describe-stacks" "$BASE_CMD cloudformation describe-stacks" ".*"
run_test "CloudFormation: describe-stack-events multi-step" "$BASE_CMD cloudformation describe-stack-events prod -- StackName ResourceStatus" ".*"
run_test "CloudFormation: list-stack-resources multi-step" "$BASE_CMD cloudformation list-stack-resources -i list-stacks:stackname" ".*"
echo ""

echo "--- ELB/ALB Tests ---"
run_test "ELBv2: describe-load-balancers" "$BASE_CMD elbv2 describe-load-balancers" ".*"
run_test "ELBv2: describe-target-groups" "$BASE_CMD elbv2 describe-target-groups" ".*"
run_test "ELBv2: describe-listeners multi-step" "$BASE_CMD elbv2 describe-listeners -i desc-load:arn" ".*"
run_test "ELBv2: describe-tags multi-step" "$BASE_CMD elbv2 describe-tags -i desc-load:arn:3" ".*"
echo ""

echo "--- RDS Tests ---"
run_test "RDS: describe-db-instances" "$BASE_CMD rds describe-db-instances" ".*"
run_test "RDS: describe-db-clusters" "$BASE_CMD rds describe-db-clusters" ".*"
run_test "RDS: describe-db-snapshots" "$BASE_CMD rds describe-db-snapshots" ".*"
run_test "RDS: describe-db-subnet-groups" "$BASE_CMD rds describe-db-subnet-groups" ".*"
run_test "RDS: describe-db-parameter-groups" "$BASE_CMD rds describe-db-parameter-groups" ".*"
echo ""

echo "--- CloudWatch Tests ---"
run_test "CloudWatch: describe-alarms" "$BASE_CMD cloudwatch describe-alarms" ".*"
run_test "CloudWatch: list-metrics" "$BASE_CMD cloudwatch list-metrics" ".*"
run_test "CloudWatch: describe-alarm-history multi-step" "$BASE_CMD cloudwatch describe-alarm-history -i desc-alarms:alarmname" ".*"
echo ""

echo "--- KMS Tests ---"
run_test "KMS: list-keys" "$BASE_CMD kms list-keys" ".*"
run_test "KMS: list-aliases" "$BASE_CMD kms list-aliases" ".*"
run_test "KMS: describe-key multi-step" "$BASE_CMD kms describe-key -i list-keys:keyid" ".*"
echo ""

echo "--- Secrets Manager Tests ---"
run_test "SecretsManager: list-secrets" "$BASE_CMD secretsmanager list-secrets" ".*"
echo ""

echo "--- SSM Tests ---"
run_test "SSM: describe-parameters" "$BASE_CMD ssm describe-parameters" ".*"
run_test "SSM: get-parameters with limit" "$BASE_CMD ssm get-parameters -i ::5" ".*"
run_test "SSM: describe-patch-baselines" "$BASE_CMD ssm describe-patch-baselines" ".*"
run_test "SSM: describe-maintenance-windows" "$BASE_CMD ssm describe-maintenance-windows" ".*"
echo ""

echo "--- ECR Tests ---"
run_test "ECR: describe-repositories" "$BASE_CMD ecr describe-repositories" ".*"
run_test "ECR: describe-images multi-step" "$BASE_CMD ecr describe-images -i desc-repos:repositoryname" ".*"
echo ""

echo "--- ECS Tests ---"
run_test "ECS: list-clusters" "$BASE_CMD ecs list-clusters" ".*"
run_test "ECS: list-services multi-step" "$BASE_CMD ecs list-services -i list-clus:cluster" ".*"
run_test "ECS: describe-tasks multi-step" "$BASE_CMD ecs describe-tasks -i :clusterarn" ".*"
run_test "ECS: list-task-definitions" "$BASE_CMD ecs list-task-definitions" ".*"
echo ""

echo "--- API Gateway Tests ---"
run_test "APIGateway: get-rest-apis" "$BASE_CMD apigateway get-rest-apis" ".*"
run_test "APIGateway: get-resources multi-step" "$BASE_CMD apigateway get-resources -i get-rest:id" ".*"
run_test "APIGatewayV2: get-apis" "$BASE_CMD apigatewayv2 get-apis" ".*"
echo ""

echo "--- Route53 Tests ---"
run_test "Route53: list-hosted-zones" "$BASE_CMD route53 list-hosted-zones" ".*"
run_test "Route53: list-health-checks" "$BASE_CMD route53 list-health-checks" ".*"
echo ""

echo "--- ACM Tests ---"
run_test "ACM: list-certificates" "$BASE_CMD acm list-certificates" ".*"
echo ""

echo "--- CloudTrail Tests ---"
run_test "CloudTrail: describe-trails" "$BASE_CMD cloudtrail describe-trails" ".*"
run_test "CloudTrail: list-trails" "$BASE_CMD cloudtrail list-trails" ".*"
echo ""

echo "--- Config Tests ---"
run_test "Config: describe-configuration-recorders" "$BASE_CMD configservice describe-configuration-recorders" ".*"
run_test "Config: describe-delivery-channels" "$BASE_CMD configservice describe-delivery-channels" ".*"
echo ""

echo "--- Backup Tests ---"
run_test "Backup: list-backup-vaults" "$BASE_CMD backup list-backup-vaults" ".*"
run_test "Backup: list-backup-plans" "$BASE_CMD backup list-backup-plans" ".*"
echo ""

echo "--- ElastiCache Tests ---"
run_test "ElastiCache: describe-cache-clusters" "$BASE_CMD elasticache describe-cache-clusters" ".*"
run_test "ElastiCache: describe-replication-groups" "$BASE_CMD elasticache describe-replication-groups" ".*"
echo ""

echo "--- Redshift Tests ---"
run_test "Redshift: describe-clusters" "$BASE_CMD redshift describe-clusters" ".*"
echo ""

echo "--- Glue Tests ---"
run_test "Glue: get-databases" "$BASE_CMD glue get-databases" ".*"
run_test "Glue: get-jobs" "$BASE_CMD glue get-jobs" ".*"
echo ""

echo "--- Athena Tests ---"
run_test "Athena: list-work-groups" "$BASE_CMD athena list-work-groups" ".*"
run_test "Athena: list-data-catalogs" "$BASE_CMD athena list-data-catalogs" ".*"
echo ""

echo "--- Step Functions Tests ---"
run_test "StepFunctions: list-state-machines" "$BASE_CMD stepfunctions list-state-machines" ".*"
echo ""

echo "--- EventBridge Tests ---"
run_test "EventBridge: list-event-buses" "$BASE_CMD events list-event-buses" ".*"
run_test "EventBridge: list-rules" "$BASE_CMD events list-rules" ".*"
echo ""

echo "--- Advanced Features Tests ---"
run_test "Advanced: parameter propagation" "$BASE_CMD ec2 describe-instances -p MaxResults=5" ".*"
run_test "Advanced: debug mode" "$BASE_CMD ec2 describe-instances --debug" "(DEBUG:|describe-instances)"
run_test "Advanced: multiple filters" "$BASE_CMD ec2 describe-instances running web -- InstanceId State" ".*"
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
