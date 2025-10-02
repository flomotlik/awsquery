import pytest

from awsquery.case_utils import to_kebab_case, to_pascal_case, to_snake_case


class TestToSnakeCase:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("DescribeInstances", "describe_instances"),
            ("HTTPSListener", "https_listener"),
            ("VPCId", "vpc_id"),
            ("DBInstance", "db_instance"),
            ("IAMRole", "iam_role"),
            ("S3Bucket", "s3_bucket"),
            ("EC2Instance", "ec2_instance"),
            ("RDSCluster", "rds_cluster"),
            ("EKSCluster", "eks_cluster"),
            ("APIGateway", "api_gateway"),
            ("SNSTopic", "sns_topic"),
            ("SQSQueue", "sqs_queue"),
            ("KMSKey", "kms_key"),
            ("DynamoDBTable", "dynamo_db_table"),
            ("CloudWatchAlarm", "cloud_watch_alarm"),
        ],
    )
    def test_converts_pascal_case(self, input_text, expected):
        assert to_snake_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("camelCase", "camel_case"),
            ("instanceId", "instance_id"),
            ("vpcId", "vpc_id"),
            ("httpListener", "http_listener"),
            ("myVariableName", "my_variable_name"),
        ],
    )
    def test_converts_camel_case(self, input_text, expected):
        assert to_snake_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("describe-instances", "describe_instances"),
            ("list-buckets", "list_buckets"),
            ("get-item", "get_item"),
            ("create-table", "create_table"),
            ("delete-cluster", "delete_cluster"),
        ],
    )
    def test_converts_kebab_case(self, input_text, expected):
        assert to_snake_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("", ""),
            ("A", "a"),
            ("ABC", "abc"),
            ("simple", "simple"),
            ("already_snake_case", "already_snake_case"),
            ("with_123_numbers", "with_123_numbers"),
            ("ALLCAPS", "allcaps"),
        ],
    )
    def test_handles_edge_cases(self, input_text, expected):
        assert to_snake_case(input_text) == expected


class TestToPascalCase:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("describe_instances", "DescribeInstances"),
            ("https_listener", "HttpsListener"),
            ("vpc_id", "VpcId"),
            ("db_instance", "DbInstance"),
            ("iam_role", "IamRole"),
            ("s3_bucket", "S3Bucket"),
            ("ec2_instance", "Ec2Instance"),
            ("rds_cluster", "RdsCluster"),
            ("eks_cluster", "EksCluster"),
            ("api_gateway", "ApiGateway"),
            ("sns_topic", "SnsTopic"),
            ("sqs_queue", "SqsQueue"),
            ("kms_key", "KmsKey"),
            ("dynamo_db_table", "DynamoDbTable"),
            ("cloud_watch_alarm", "CloudWatchAlarm"),
        ],
    )
    def test_converts_snake_case(self, input_text, expected):
        assert to_pascal_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("describe-instances", "DescribeInstances"),
            ("list-buckets", "ListBuckets"),
            ("get-item", "GetItem"),
            ("create-table", "CreateTable"),
            ("delete-cluster", "DeleteCluster"),
        ],
    )
    def test_converts_kebab_case(self, input_text, expected):
        assert to_pascal_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("", ""),
            ("single", "Single"),
            ("a", "A"),
            ("abc", "Abc"),
            ("with_numbers_123", "WithNumbers123"),
        ],
    )
    def test_handles_edge_cases(self, input_text, expected):
        assert to_pascal_case(input_text) == expected


class TestToKebabCase:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("DescribeInstances", "describe-instances"),
            ("HTTPSListener", "https-listener"),
            ("VPCId", "vpc-id"),
            ("DBInstance", "db-instance"),
            ("IAMRole", "iam-role"),
            ("S3Bucket", "s3-bucket"),
            ("EC2Instance", "ec2-instance"),
            ("RDSCluster", "rds-cluster"),
            ("EKSCluster", "eks-cluster"),
            ("APIGateway", "api-gateway"),
            ("SNSTopic", "sns-topic"),
            ("SQSQueue", "sqs-queue"),
            ("KMSKey", "kms-key"),
            ("DynamoDBTable", "dynamo-db-table"),
            ("CloudWatchAlarm", "cloud-watch-alarm"),
        ],
    )
    def test_converts_pascal_case(self, input_text, expected):
        assert to_kebab_case(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("", ""),
            ("Single", "single"),
            ("A", "a"),
            ("ABC", "abc"),
        ],
    )
    def test_handles_edge_cases(self, input_text, expected):
        assert to_kebab_case(input_text) == expected


class TestRoundTripConversions:
    @pytest.mark.parametrize(
        "original",
        [
            "describe_instances",
            "https_listener",
            "vpc_id",
            "db_instance",
            "iam_role",
            "api_gateway",
            "simple",
        ],
    )
    def test_snake_to_pascal_to_snake(self, original):
        assert to_snake_case(to_pascal_case(original)) == original

    @pytest.mark.parametrize(
        "original",
        [
            "describe-instances",
            "list-buckets",
            "get-item",
            "create-table",
            "simple",
        ],
    )
    def test_kebab_to_snake_to_kebab(self, original):
        assert to_kebab_case(to_snake_case(original)) == original

    @pytest.mark.parametrize(
        "original",
        [
            "describe_instances",
            "list_buckets",
            "get_item",
            "simple_name",
        ],
    )
    def test_snake_to_kebab_to_snake(self, original):
        snake_converted = to_snake_case(to_kebab_case(to_pascal_case(original)))
        assert snake_converted == original


class TestAcronymPreservation:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("HTTPSConnection", "https_connection"),
            ("VPCEndpoint", "vpc_endpoint"),
            ("IAMUser", "iam_user"),
            ("S3Object", "s3_object"),
            ("EC2AMI", "ec2_ami"),
        ],
    )
    def test_preserves_consecutive_capitals_as_acronyms(self, input_text, expected):
        assert to_snake_case(input_text) == expected


class TestMixedFormats:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("IAM-Role", "iam_role"),
            ("s3-bucket_name", "s3_bucket_name"),
            ("EC2-instance_Type", "ec2_instance_type"),
        ],
    )
    def test_handles_mixed_delimiters(self, input_text, expected):
        assert to_snake_case(input_text) == expected


class TestNumericHandling:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("IPv4Address", "i_pv4_address"),
            ("EC2Instance", "ec2_instance"),
            ("S3Bucket", "s3_bucket"),
            ("Version123", "version123"),
            ("Test123ABC", "test123_abc"),
        ],
    )
    def test_handles_numbers_in_text(self, input_text, expected):
        assert to_snake_case(input_text) == expected
