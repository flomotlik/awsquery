# Combined Makefile for awsquery: AWS API Response Sampling + Development Environment
OUTPUT_DIR := sample-responses

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

# Default target
.DEFAULT_GOAL := help

.PHONY: help clean install-dev test test-unit test-integration test-critical test-slow coverage \
        coverage-report lint format format-check type-check security-check ci build publish-test \
        publish watch-tests version release update-policy validate-policy all ec2-instances s3-buckets iam-users \
        iam-roles lambda-functions cloudformation-stacks dynamodb-tables ec2-volumes \
        ec2-security-groups s3-bucket-versioning cloudwatch-alarms route53-zones shell \
        docker-build docker-clean test-in-docker test-awsquery

help: ## Show this help message
	@echo '$(BLUE)awsquery Development & Sampling Commands:$(NC)'
	@echo ''
	@echo '$(YELLOW)Development Commands:$(NC)'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -v '(AWS)' | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ''
	@echo '$(YELLOW)AWS Sampling Commands:$(NC)'
	@grep -E '^[a-zA-Z_-]+:.*?## .*\(AWS\)$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# DEVELOPMENT TARGETS
# =============================================================================

install-dev: ## Install development dependencies
	pip3 install --user --break-system-packages -e ".[dev]" || pip3 install -e ".[dev]"

test: ## Run all tests
	python3 -m pytest tests/ -v

test-unit: ## Run unit tests only
	python3 -m pytest tests/unit/ -v -m "unit"

test-integration: ## Run integration tests only
	python3 -m pytest tests/integration/ -v -m "integration"

test-slow: ## Run slow tests
	python3 -m pytest tests/ -v -m "slow"

test-critical: ## Run critical path tests
	python3 -m pytest tests/ -v -m "critical"

coverage: ## Run tests with coverage report
	python3 -m pytest tests/ --cov=src/awsquery --cov-report=term-missing --cov-report=html

coverage-report: coverage ## Generate and show coverage report location
	@echo "$(GREEN)Coverage report available at: htmlcov/index.html$(NC)"

lint: ## Run linting checks
	flake8 src/ tests/ --count --statistics --show-source
	pylint src/awsquery

format: ## Format code with black and isort
	black src/ tests/
	isort src/ tests/

format-check: ## Check code formatting without changes
	black --check --diff src/ tests/
	isort --check-only --diff src/ tests/

type-check: ## Run mypy type checking
	mypy src/awsquery --ignore-missing-imports

security-check: ## Run security checks
	bandit -r src/ -ll

ci: ## Run all CI checks and tests (format-check, lint, type-check, test)
	@echo "$(BLUE)Running CI pipeline - all quality checks and tests$(NC)"
	@echo "$(YELLOW)Step 1/4: Checking code formatting...$(NC)"
	$(MAKE) format-check
	@echo "$(YELLOW)Step 2/4: Running lint checks...$(NC)"
	$(MAKE) lint
	@echo "$(YELLOW)Step 3/4: Running type checks...$(NC)"
	$(MAKE) type-check
	@echo "$(YELLOW)Step 4/4: Running all tests...$(NC)"
	$(MAKE) test
	@echo "$(GREEN)✓ All CI checks passed! Code is ready for push.$(NC)"

clean: ## Remove build artifacts and cache files
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf src/*.egg-info
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .tox/
	rm -rf $(OUTPUT_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*~" -delete
	@echo "$(GREEN)Cleanup complete!$(NC)"

build: clean ## Build distribution packages
	python3 -m build .

publish-test: build ## Publish to TestPyPI
	twine upload --repository testpypi dist/*

publish: build ## Publish to PyPI
	@echo "$(RED)Are you sure? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	twine upload dist/*


watch-tests: ## Run tests continuously on file changes
	ptw -- -vv

version: ## Show current version
	@python3 -c "import sys; sys.path.insert(0, 'src'); from awsquery import __version__; print(__version__)" 2>/dev/null || echo "1.0.0"

release: ## Create a new release (requires clean git state)
	@git status --porcelain | grep -q . && echo "$(RED)Git working directory not clean$(NC)" && exit 1 || true
	@echo "Current version: $$(make version)"
	@echo "Enter new version: " && read VERSION && \
		echo "version = '$$VERSION'" > src/awsquery/__version__.py && \
		git add src/awsquery/__version__.py && \
		git commit -m "Bump version to $$VERSION" && \
		git tag -a "v$$VERSION" -m "Release version $$VERSION" && \
		echo "$(GREEN)Tagged version $$VERSION. Run 'git push --tags' to push.$(NC)"

update-policy: ## Update policy.json with latest AWS ReadOnly managed policy
	@echo "$(BLUE)Fetching latest AWS ReadOnly managed policy...$(NC)"
	@aws iam get-policy --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess --query 'Policy.DefaultVersionId' --output text | \
		xargs -I {} aws iam get-policy-version \
			--policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess \
			--version-id {} \
			--query 'PolicyVersion.Document' \
			--output json > src/awsquery/policy.json.tmp && \
		python3 -c "import json, sys; \
			data = json.load(open('src/awsquery/policy.json.tmp')); \
			print(json.dumps(data, indent=2, sort_keys=True))" > src/awsquery/policy.json && \
		rm -f src/awsquery/policy.json.tmp && \
		echo "$(GREEN)✓ Updated src/awsquery/policy.json with latest AWS ReadOnly policy$(NC)" || \
		(rm -f src/awsquery/policy.json.tmp && echo "$(RED)✗ Failed to update policy.json$(NC)" && exit 1)

validate-policy: ## Validate that policy.json is a valid AWS policy document
	@echo "$(BLUE)Validating policy.json...$(NC)"
	@python3 -c "import json; \
		policy = json.load(open('src/awsquery/policy.json')); \
		assert 'Statement' in policy or 'PolicyVersion' in policy, 'Invalid policy structure'; \
		print('✓ policy.json is valid')" && \
		echo "$(GREEN)✓ policy.json validation passed$(NC)" || \
		echo "$(RED)✗ policy.json validation failed$(NC)"

# =============================================================================
# AWS API RESPONSE SAMPLING TARGETS (PRESERVED)
# =============================================================================

all: $(OUTPUT_DIR) ec2-instances s3-buckets iam-users iam-roles lambda-functions \
     cloudformation-stacks dynamodb-tables ec2-volumes ec2-security-groups \
     s3-bucket-versioning cloudwatch-alarms route53-zones ## Generate all AWS API samples (AWS)

$(OUTPUT_DIR):
	mkdir -p $(OUTPUT_DIR)

ec2-instances: $(OUTPUT_DIR) ## Sample EC2 instances API response (AWS)
	-aws ec2 describe-instances --output json > $(OUTPUT_DIR)/ec2-instances.json

s3-buckets: $(OUTPUT_DIR) ## Sample S3 buckets API response (AWS)
	-aws s3api list-buckets --output json > $(OUTPUT_DIR)/s3-buckets.json

iam-users: $(OUTPUT_DIR) ## Sample IAM users API response (AWS)
	-aws iam list-users --output json > $(OUTPUT_DIR)/iam-users.json

iam-roles: $(OUTPUT_DIR) ## Sample IAM roles API response (AWS)
	-aws iam list-roles --output json > $(OUTPUT_DIR)/iam-roles.json

lambda-functions: $(OUTPUT_DIR) ## Sample Lambda functions API response (AWS)
	-aws lambda list-functions --output json > $(OUTPUT_DIR)/lambda-functions.json

cloudformation-stacks: $(OUTPUT_DIR) ## Sample CloudFormation stacks API response (AWS)
	-aws cloudformation list-stacks --output json > $(OUTPUT_DIR)/cloudformation-stacks.json

dynamodb-tables: $(OUTPUT_DIR) ## Sample DynamoDB tables API response (AWS)
	-aws dynamodb list-tables --output json > $(OUTPUT_DIR)/dynamodb-tables.json

ec2-volumes: $(OUTPUT_DIR) ## Sample EC2 volumes API response (AWS)
	-aws ec2 describe-volumes --output json > $(OUTPUT_DIR)/ec2-volumes.json

ec2-security-groups: $(OUTPUT_DIR) ## Sample EC2 security groups API response (AWS)
	-aws ec2 describe-security-groups --output json > $(OUTPUT_DIR)/ec2-security-groups.json

s3-bucket-versioning: $(OUTPUT_DIR) ## Sample S3 bucket versioning API response (AWS)
	-@bucket=$$(aws s3api list-buckets --query 'Buckets[0].Name' --output text 2>/dev/null); \
	if [ -n "$$bucket" ]; then \
		aws s3api get-bucket-versioning --bucket $$bucket --output json > $(OUTPUT_DIR)/s3-bucket-versioning.json; \
	else \
		echo '{}' > $(OUTPUT_DIR)/s3-bucket-versioning.json; \
	fi

cloudwatch-alarms: $(OUTPUT_DIR) ## Sample CloudWatch alarms API response (AWS)
	-aws cloudwatch describe-alarms --output json > $(OUTPUT_DIR)/cloudwatch-alarms.json

route53-zones: $(OUTPUT_DIR) ## Sample Route53 hosted zones API response (AWS)
	-aws route53 list-hosted-zones --output json > $(OUTPUT_DIR)/route53-zones.json

# Docker commands
shell: docker-build ## Open shell in Docker container (AWS)
	docker-compose run --rm awsquery-dev

docker-build: ## Build Docker container (AWS)
	docker-compose build awsquery-dev

docker-build-prod: ## Build production Docker container (AWS)
	docker-compose build awsquery-prod

docker-clean: ## Clean up Docker resources (AWS)
	docker-compose down --rmi all --volumes --remove-orphans

test-in-docker: docker-build ## Test awsquery in Docker container (AWS)
	@echo "Testing awsquery in Docker container..."
	docker-compose run --rm awsquery-dev python awsquery.py --help
	@echo ""
	@echo "Testing modular CLI..."
	docker-compose run --rm awsquery-dev awsquery --help
	@echo ""
	@echo "Testing AWS CLI access..."
	-docker-compose run --rm awsquery-dev aws sts get-caller-identity
	@echo ""
	@echo "Testing awsquery command..."
	-docker-compose run --rm awsquery-dev python awsquery.py ec2 describe_instances
	@echo ""
	@echo "Running tests in Docker..."
	-docker-compose run --rm awsquery-dev make test

test-in-docker-prod: docker-build-prod ## Test production Docker container (AWS)
	@echo "Testing production awsquery in Docker container..."
	docker-compose run --rm awsquery-prod --help
	@echo ""
	@echo "Testing production command..."
	-docker-compose run --rm awsquery-prod ec2 describe-instances

# Comprehensive awsquery testing target
test-awsquery: ## Run comprehensive awsquery functional tests (AWS)
	@echo "Running comprehensive awsquery tests..."
	@echo "=========================================="
	@echo
	@echo "Test 1: EC2 instances with basic column filters"
	python3 awsquery.py ec2 describe-instances -- InstanceId State.Name
	@echo
	@echo "Test 2: EC2 instances with JSON output and multiple columns"
	python3 awsquery.py -j ec2 describe-instances -- InstanceId SubnetId VpcId InstanceType
	@echo
	@echo "Test 3: S3 buckets with basic listing"
	python3 awsquery.py s3 list-buckets -- Name CreationDate
	@echo
	@echo "Test 4: S3 buckets with JSON output"
	python3 awsquery.py s3 -j list-buckets dcsand -- Name CreationDate
	@echo
	@echo "Test 5: IAM users with value filter"
	python3 awsquery.py iam list-users prod -- UserName CreateDate
	@echo
	@echo "Test 6: IAM users with different column order"
	python3 awsquery.py iam list-users -- CreateDate UserName Path
	@echo
	@echo "Test 7: Lambda functions with value filter"
	python3 awsquery.py lambda list-functions python3 -- FunctionName Runtime LastModified
	@echo
	@echo "Test 9: RDS instances with basic filters"
	python3 awsquery.py rds describe-db-instances -- DBInstanceIdentifier DBInstanceStatus Engine
	@echo
	@echo "Test 10: RDS instances with value filter"
	python3 awsquery.py rds describe-db-instances mysql -- DBInstanceIdentifier AllocatedStorage
	@echo
	@echo "Test 11: EC2 security groups with multiple filters"
	python3 awsquery.py ec2 describe-security-groups -- GroupName GroupId VpcId
	@echo
	@echo "Test 12: EC2 security groups with value filter and JSON"
	python3 awsquery.py ec2 describe-security-groups web -- GroupName Description
	@echo
	@echo "Test 13: ELB load balancers basic listing"
	python3 awsquery.py elbv2 describe-load-balancers -- LoadBalancerName State.Code Type
	@echo
	@echo "Test 14: ELB target groups with filters"
	python3 awsquery.py elbv2 describe-target-groups -- TargetGroupName Protocol Port
	@echo
	@echo "Test 15: IAM roles with value filter"
	python3 awsquery.py iam list-roles service -- RoleName CreateDate
	@echo
	@echo "Test 16: CloudWatch alarms with basic filters"
	python3 awsquery.py cloudwatch describe-alarms -- AlarmName StateValue
	@echo
	@echo "Test 17: Route53 hosted zones listing"
	python3 awsquery.py route53 list-hosted-zones -- Name ResourceRecordSetCount
	@echo
	@echo "Test 18: EC2 volumes with multiple column filters"
	python3 awsquery.py ec2 describe-volumes -- VolumeId Size State VolumeType
	@echo
	@echo "Test 19: SNS topics with JSON output"
	python3 awsquery.py sns list-topics -- TopicArn
	@echo
	@echo "Test 20: SQS queues basic listing"
	python3 awsquery.py sqs list-queues -- QueueUrl
	@echo
	@echo "=========================================="
	@echo "All awsquery tests completed!"