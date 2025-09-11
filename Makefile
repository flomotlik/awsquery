# AWS API Response Sample Generator
OUTPUT_DIR := sample-responses

.PHONY: all clean ec2-instances s3-buckets iam-users iam-roles lambda-functions \
        cloudformation-stacks dynamodb-tables ec2-volumes ec2-security-groups \
        s3-bucket-versioning cloudwatch-alarms route53-zones \
        shell docker-build docker-clean test-in-docker test-awsquery

all: $(OUTPUT_DIR) ec2-instances s3-buckets iam-users iam-roles lambda-functions \
     cloudformation-stacks dynamodb-tables ec2-volumes ec2-security-groups \
     s3-bucket-versioning cloudwatch-alarms route53-zones

$(OUTPUT_DIR):
	mkdir -p $(OUTPUT_DIR)

ec2-instances: $(OUTPUT_DIR)
	-aws ec2 describe-instances --output json > $(OUTPUT_DIR)/ec2-instances.json

s3-buckets: $(OUTPUT_DIR)
	-aws s3api list-buckets --output json > $(OUTPUT_DIR)/s3-buckets.json

iam-users: $(OUTPUT_DIR)
	-aws iam list-users --output json > $(OUTPUT_DIR)/iam-users.json

iam-roles: $(OUTPUT_DIR)
	-aws iam list-roles --output json > $(OUTPUT_DIR)/iam-roles.json

lambda-functions: $(OUTPUT_DIR)
	-aws lambda list-functions --output json > $(OUTPUT_DIR)/lambda-functions.json

cloudformation-stacks: $(OUTPUT_DIR)
	-aws cloudformation list-stacks --output json > $(OUTPUT_DIR)/cloudformation-stacks.json

dynamodb-tables: $(OUTPUT_DIR)
	-aws dynamodb list-tables --output json > $(OUTPUT_DIR)/dynamodb-tables.json

ec2-volumes: $(OUTPUT_DIR)
	-aws ec2 describe-volumes --output json > $(OUTPUT_DIR)/ec2-volumes.json

ec2-security-groups: $(OUTPUT_DIR)
	-aws ec2 describe-security-groups --output json > $(OUTPUT_DIR)/ec2-security-groups.json

s3-bucket-versioning: $(OUTPUT_DIR)
	-@bucket=$$(aws s3api list-buckets --query 'Buckets[0].Name' --output text 2>/dev/null); \
	if [ -n "$$bucket" ]; then \
		aws s3api get-bucket-versioning --bucket $$bucket --output json > $(OUTPUT_DIR)/s3-bucket-versioning.json; \
	else \
		echo '{}' > $(OUTPUT_DIR)/s3-bucket-versioning.json; \
	fi

cloudwatch-alarms: $(OUTPUT_DIR)
	-aws cloudwatch describe-alarms --output json > $(OUTPUT_DIR)/cloudwatch-alarms.json

route53-zones: $(OUTPUT_DIR)
	-aws route53 list-hosted-zones --output json > $(OUTPUT_DIR)/route53-zones.json

clean:
	rm -rf $(OUTPUT_DIR)

# Docker commands
shell: docker-build
	docker-compose run --rm awsquery

docker-build:
	docker-compose build

docker-clean:
	docker-compose down --rmi all --volumes --remove-orphans

test-in-docker: docker-build
	@echo "Testing awsquery in Docker container..."
	docker-compose run --rm awsquery python awsquery.py --help
	@echo ""
	@echo "Testing AWS CLI access..."
	-docker-compose run --rm awsquery aws sts get-caller-identity
	@echo ""
	@echo "Testing awsquery command..."
	-docker-compose run --rm awsquery python awsquery.py --dry-run ec2 describe_instances

# Comprehensive awsquery testing target
test-awsquery:
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