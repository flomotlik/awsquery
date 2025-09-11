# awsquery

CLI tool to call the AWS API through boto3 with a flexible filtering approach similar to awsinfo.

* https://theserverlessway.com/tools/awsinfo/filters/

# Command structure

Following is the command structure that should be implemented:

awsquery AWS_SERVICE SERVICE_ACTION VALUE_FILTERS -- TABLE_OUTPUT_FILTERS

The parameters should be auto completable with argcomplete and implemented with argparse

The AWS_SERVICE and the corresponding SERVICE_ACTIONS should be listed through Code that is as an example implemented in ./awsquery.py

The example command:

awsquery ec2 describe-instances 0227 0cd2 -- Subnet vpcid InstanceId image

Should the run the boto3 action DescribeInstances for the ec2 service. The resulting response should be filtered by first flattening any meta list element like Reservations in the ec2-instances.json example I added to this folder. When we then have a list of of resources we check all values of that resource if it contains all of the VALUE_FILTERS we added, but we test each individually. In the example above the value filter is "0227 0cd2". This would match with the Subnet for 0227 and with the ami-id for 0cd2. Only if all separate values in the values filters match with a given list element then that list element is selected for output. The values don't have to match exactly, they just have to be contained in any value of the list.

The output should be a table and implemented with [tabulate](https://pypi.org/project/tabulate/). To select which fields to output take every word of the TABLE_OUTPUT_FILTERS and compare them to every key of the selected resources from the step before. Before stepping through all of the keys it might make sense to create a new dictionary where all the keys of the resource map are flattened and connected with a dot, e.g. '"{Operator": {"Managed": false}}' becomes '"{Operator.Managed": false}' for easier comparison. If any of the words match any part of the key that key/value is used in the resulting output table. This way we can have a flexible system to filter the resources we want to show and which fields for each resource should be shown.

# keys command

"awsquery keys ec2 describe-instances" for example should send that request to the api, get the response and then show all of the available keys in a flattened and sorted order. List items should get an indicator, e.g. instance.0.id and instance.1.id.

# Available commands

I only want commands that are part of the ReadOnly AWS policy to be available. I added the policy to policy.json file. Implement a filtering mechanism where the policy is read in, all the services are extracted from the statement by splitting each action and when a command is called it is checked against the list of commands in that readonly policy either by matching exactly or by using the wildcard matching implemented in that list. This increases security as no command that isn't part of this list should ever be called by awsquery.