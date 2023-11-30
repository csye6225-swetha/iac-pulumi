import pulumi
import pulumi_gcp as gcp
import pulumi_aws as aws
from pulumi_aws import route53, ec2
import base64
import json
from pulumi_gcp import storage

config = pulumi.Config()

vpc_cidr_block = config.require("vpc_cidr_block")


vpc = ec2.Vpc("my_vpc",
    cidr_block=vpc_cidr_block,
    enable_dns_hostnames=True)


gateway = ec2.InternetGateway("my_gateway",
    vpc_id=vpc.id)


public_route_table = ec2.RouteTable("public_route_table",
    vpc_id=vpc.id)


public_route = ec2.Route("public_route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=gateway.id)


private_route_table = ec2.RouteTable("private_route_table",
    vpc_id=vpc.id)

public_subnet_ids = []
private_subnet_ids = []

availability_zones = aws.get_availability_zones(state="available")
az_count = len(availability_zones.names)

first_available_zone = availability_zones.names[0] 

for i, zone in enumerate(availability_zones.names[:3]):


    public_subnet_cidr = f"{vpc_cidr_block.split('.')[0]}.{vpc_cidr_block.split('.')[1]}.{i}.0/24"
    private_subnet_cidr = f"{vpc_cidr_block.split('.')[0]}.{vpc_cidr_block.split('.')[1]}.{i+3}.0/24"

    az_name = availability_zones.names[i]  # Cyclic assignment of AZs

    subnet = ec2.Subnet(f"public_subnet_{i}",
        cidr_block= public_subnet_cidr,
        vpc_id=vpc.id,
        map_public_ip_on_launch=True,
        availability_zone=az_name, 
        tags={"Name": f"public-subnet-{i}"})
    
    public_subnet_ids.append(subnet.id)

    
    ec2.RouteTableAssociation(f"public_rta_{i}",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id)

    subnet = ec2.Subnet(f"private_subnet_{i}",
        cidr_block=private_subnet_cidr,
        vpc_id=vpc.id,
        map_public_ip_on_launch=False,
        availability_zone=az_name, 
        tags={"Name": f"private-subnet-{i}"})
    
    private_subnet_ids.append(subnet.id)

   
    ec2.RouteTableAssociation(f"private_rta_{i}",
        subnet_id=subnet.id,
        route_table_id=private_route_table.id)
    
load_balancer_security_group = aws.ec2.SecurityGroup(
    "loadBalancerSecurityGroup",
    description="Load Balancer Security Group",
    vpc_id=vpc.id,  # Replace with your VPC ID
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=80,
            to_port=80,
            cidr_blocks=["0.0.0.0/0"],  # Allowing traffic from anywhere (0.0.0.0/0)
        ),
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=443,
            to_port=443,
            cidr_blocks=["0.0.0.0/0"],  # Allowing traffic from anywhere (0.0.0.0/0)
        ),
    ],

    egress=[  
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol="-1",  
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
)

application_security_group = ec2.SecurityGroup("applicationSecurityGroup",
    description="Security group for web application EC2 instances",
    vpc_id=vpc.id,
    ingress=[
      
        ec2.SecurityGroupIngressArgs(
            from_port=22,
            to_port=22,
            protocol="tcp",
            security_groups=[load_balancer_security_group.id],
        ),
       
        ec2.SecurityGroupIngressArgs(
            from_port=8080,
            to_port=8080,
            protocol="tcp",
            security_groups=[load_balancer_security_group.id],
        ),
    ],

    egress=[  
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol="-1",  
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],

)

rds_security_group = ec2.SecurityGroup("rdsSecurityGroup",
    description="Security group for rds instances",
    vpc_id=vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            from_port=3306,  
            to_port=3306,   
            protocol="tcp",
            security_groups=[application_security_group.id],
        ),
    
    ],
    egress=[  
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol="-1",  
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],

)


key_pair_name = pulumi.Config().require("key_name")

ami_id = pulumi.Config().require("ami_id")

rds_username = pulumi.Config().require("db_username")
rds_password = pulumi.Config().require("db_password")

subnet_id_first = public_subnet_ids[0]

rds_subnet_group = aws.rds.SubnetGroup(
    "my-rds-subnet-group",
    subnet_ids=private_subnet_ids,
)

rds_parameter_group = aws.rds.ParameterGroup(
    "customparametergroup",
    family="mariadb10.6",
)

rds_instance = aws.rds.Instance(
    "my-rds-instance",
    allocated_storage=20,
    storage_type="gp2",
    engine="mariadb",
    instance_class="db.t3.micro",  
    multi_az=False,
    name="csye6225",
    username=rds_username,
    password=rds_password,  
    publicly_accessible=False,
    db_subnet_group_name=rds_subnet_group,
    vpc_security_group_ids=[rds_security_group.id],
    parameter_group_name=rds_parameter_group.name,
    skip_final_snapshot=True,
)

sns_topic = aws.sns.Topic("submissionTopic")

rds_endpoint = rds_instance.endpoint.apply(lambda endpoint: endpoint)

sns_topic_arn = sns_topic.arn

user_data_script = pulumi.Output.all(rds_username, rds_password, rds_endpoint,  sns_topic_arn).apply(
    lambda vars: f"""#!/bin/bash
cat <<EOF > /home/admin/application.properties
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver


spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.datasource.username={vars[0]}
spring.datasource.password={vars[1]}
spring.datasource.url=jdbc:mysql://{vars[2]}/webapp_DB?createDatabaseIfNotExist=true

sns.topic.arn={vars[3]}

logging.level.org.springframework.web=debug
logging.file.path=./
logging.file.name=log.txt

management.statsd.metrics.export.enabled=true
management.statsd.metrics.export.host=localhost
management.statsd.metrics.export.port=8125

EOF

sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c file:/home/admin/cloudwatch-config.json \
    -s

sudo systemctl restart webapp

"""
)



role = aws.iam.Role("cloudwatch-agent",
    assume_role_policy="""{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}""",
)

sns_publish_policy_arn = "arn:aws:iam::aws:policy/AmazonSNSFullAccess"  # Or use another relevant policy

# Attach the CloudWatchAgentServerPolicy to the IAM role
policy_attachment = aws.iam.RolePolicyAttachment("my-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
    role=role.name,
)


sns_policy_attachment = aws.iam.RolePolicyAttachment("snsPolicyAttachment",
    policy_arn=sns_publish_policy_arn,
    role=role.name,
)


instance_profile = aws.iam.InstanceProfile("instance_profile", role=role.name)


hosted_zone_id = config.require("hosted_zoneid")
domain_name = config.require("hosted_zonename")




encoded_user_data =  pulumi.Output.from_input(user_data_script).apply(lambda s: base64.b64encode(s.encode()).decode('utf-8'))

launch_template = aws.ec2.LaunchTemplate("launch_template",
    
        iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
        name=instance_profile.name,
    ),

      block_device_mappings=[
        {
            "deviceName": "/dev/xvda",  
            "ebs": {
                "volumeSize": 25,  
                "volumeType": "gp2",  
                "deleteOnTermination": True,  
            },
        },
    ],

    image_id=ami_id,
    instance_initiated_shutdown_behavior="terminate",
   
    instance_type="t2.micro",
    key_name=key_pair_name,

    monitoring=aws.ec2.LaunchTemplateMonitoringArgs(
        enabled=True,
    ),
    network_interfaces=[aws.ec2.LaunchTemplateNetworkInterfaceArgs(
        associate_public_ip_address="true",
        security_groups=[application_security_group.id],
        
    )],
    placement=aws.ec2.LaunchTemplatePlacementArgs(
        availability_zone=first_available_zone,
    ),
    tag_specifications=[aws.ec2.LaunchTemplateTagSpecificationArgs(
        resource_type="instance",
        tags={
            "Name": "instancesCSYE6225F23",
        },
    )],
    user_data=encoded_user_data,
    )

asg_parameters = {
    "cooldown": 60,
    "launchTemplate": {
        "id": launch_template.id,
        "version": launch_template.latest_version,
    },
    "minSize": 1,
    "maxSize": 3,
    "desiredCapacity": 1,
}


targetGroup = aws.lb.TargetGroup(
    "targetGroup",
    port=8080,  
    protocol="HTTP",  
    vpc_id=vpc.id,
    target_type="instance",  
    slow_start=60,  
    health_check= {
       "enabled": True,
       "unhealthy_threshold": 5,
       "healthy_threshold": 2,
       "timeout": 3,
       "interval": 30,
       "protocol": "HTTP",
       "path": "/healthz",
    },
)

applicationLoadBalancer = aws.lb.LoadBalancer(
    "Assignment8LoadBalancer",
    subnets=public_subnet_ids, 
    load_balancer_type="application", 
    security_groups=[load_balancer_security_group.id],  
    
)

httpListener = aws.lb.Listener(
    "http-listener",
    load_balancer_arn= applicationLoadBalancer.arn,
    port=80, 
    protocol="HTTP", 
    default_actions=[  
        {
            "type": "forward",  # Forward the request to a target group
            "target_group_arn": targetGroup.arn,  # ARN of the target group to forward traffic to
        }
    ]
)



auto_scaling_group = aws.autoscaling.Group(
    "my-auto-scaling-group",
    vpc_zone_identifiers=public_subnet_ids,
    launch_template=asg_parameters["launchTemplate"],
    min_size=asg_parameters["minSize"],
    max_size=asg_parameters["maxSize"],
    desired_capacity=asg_parameters["desiredCapacity"],
    default_cooldown=asg_parameters["cooldown"],
    health_check_type="EC2",
    target_group_arns=[targetGroup.arn],
    health_check_grace_period=300, 
)

scale_up_policy = aws.autoscaling.Policy(
    "scaleup",
    adjustment_type="ChangeInCapacity",
    autoscaling_group_name=auto_scaling_group.name,
    cooldown=60,
    scaling_adjustment=1,
)

# Create a scaling down policy
scale_down_policy = aws.autoscaling.Policy(
    "scaledown",
    adjustment_type="ChangeInCapacity",
    autoscaling_group_name=auto_scaling_group.name,
    cooldown=30,
    scaling_adjustment=-1,
)

# Create a CPU utilization high alarm
cpu_utilization_high_alarm = aws.cloudwatch.MetricAlarm(
    "cpuHigh",
    alarm_actions=[scale_up_policy.arn],
    comparison_operator="GreaterThanThreshold",
    evaluation_periods=2,
    metric_name="CPUUtilization",
    namespace="AWS/EC2",
    period=60,
    statistic="Average",
    threshold=5,
    alarm_description="This metric triggers when CPU Utilization is above 5%",
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
)

# Create a CPU utilization low alarm
cpu_utilization_low_alarm = aws.cloudwatch.MetricAlarm(
    "cpuLow",
    alarm_actions=[scale_down_policy.arn],
    comparison_operator="LessThanThreshold",
    evaluation_periods=2,
    metric_name="CPUUtilization",
    namespace="AWS/EC2",
    period=60,
    statistic="Average",
    threshold=3,
    alarm_description="This metric triggers when CPU Utilization is below 3%",
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
)

gcpproject_id = config.require("gcpproject_id")


bucket = storage.Bucket('my-bucket',
                        location='US',
                        project=gcpproject_id,
                        uniform_bucket_level_access=True)


service_account = gcp.serviceaccount.Account('my-service-account',account_id='my-service-account-id', project=gcpproject_id)

service_account_key = gcp.serviceaccount.Key('my-service-account-key',
    service_account_id=service_account.name  
)

bucket_iam_binding = gcp.storage.BucketIAMBinding('bucket-iam-binding',
    bucket=bucket.name,
    role='roles/storage.objectCreator',
     members=[service_account.email.apply(lambda email: f'serviceAccount:{email}')]
)

dynamodb_table = aws.dynamodb.Table("myDynamoDBTable",
    attributes=[
        aws.dynamodb.TableAttributeArgs(
            name="MessageId",
            type="S",
        ),
    ],
    hash_key="MessageId",
    billing_mode="PAY_PER_REQUEST",
)

lambda_role = aws.iam.Role("lambdaRole",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    })
)

policy_attachment_log = aws.iam.RolePolicyAttachment("lambdaLogPolicyAttachment",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
)

dynamodb_policy = aws.iam.Policy("lambdaDynamoDBPolicy",
    policy=dynamodb_table.arn.apply(lambda arn: json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Scan",
                "dynamodb:Query"
            ],
            "Resource": arn
        }]
    }))
)


policy_attachment_dynamodb = aws.iam.RolePolicyAttachment("lambdaDynamoDBPolicyAttachment",
    role=lambda_role.name,
    policy_arn=dynamodb_policy.arn,
)


mailgun_api = config.require("mailgun_api")
mailgun_domain = config.require("mailgun_domain")

lambda_function = aws.lambda_.Function("myLambdaFunction",
    runtime="python3.11",  
    handler="lambda_function.lambda_handler", 
    code=pulumi.FileArchive("/Users/swethapaturu/Desktop/cloud_assignments/lambda_project/lambda_function.zip"),
    environment={
        "variables": {
            "DYNAMODB_TABLE_NAME": dynamodb_table.name,
            "GCP_STORAGE_BUCKET_NAME": bucket.name,
            "GCP_SERVICE_ACCOUNT_KEY_JSON": service_account_key.private_key,
            "MAILGUN_API_KEY" : mailgun_api,
            "MAILGUN_DOMAIN"  : mailgun_domain,
        }
    },

    role=lambda_role.arn,
    timeout=30,
    memory_size=128
)

sns_subscription = aws.sns.TopicSubscription("mySnsSubscription",
    topic=sns_topic.arn,
    protocol="lambda",
    endpoint=lambda_function.arn
)

sns_invoke_permission = aws.lambda_.Permission("snsInvokePermission",
    action="lambda:InvokeFunction",
    function=lambda_function.name,
    principal="sns.amazonaws.com",
    source_arn=sns_topic.arn
)

alb_dns_name = applicationLoadBalancer.dns_name

a_record = aws.route53.Record("my-loadBalancer-record",
    zone_id=hosted_zone_id,
    name=domain_name,
    type="A",
    aliases=[
         aws.route53.RecordAliasArgs(
            name=alb_dns_name,
            zone_id=applicationLoadBalancer.zone_id,
            evaluate_target_health=True,
        ),
    ])




pulumi.export("vpcId", vpc.id)
pulumi.export("gatewayId", gateway.id)
pulumi.export("dbEndPoint", rds_instance.endpoint)
pulumi.export("key",service_account_key.private_key)