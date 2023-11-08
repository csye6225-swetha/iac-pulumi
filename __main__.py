import pulumi
import pulumi_aws as aws
from pulumi_aws import route53, ec2


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
    

application_security_group = ec2.SecurityGroup("applicationSecurityGroup",
    description="Security group for web application EC2 instances",
    vpc_id=vpc.id,
    ingress=[
      
        ec2.SecurityGroupIngressArgs(
            from_port=22,
            to_port=22,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
      
        ec2.SecurityGroupIngressArgs(
            from_port=80,
            to_port=80,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
       
        ec2.SecurityGroupIngressArgs(
            from_port=443,
            to_port=443,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
       
        ec2.SecurityGroupIngressArgs(
            from_port=8080,
            to_port=8080,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
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

rds_endpoint = rds_instance.endpoint.apply(lambda endpoint: endpoint)



user_data_script = pulumi.Output.all(rds_username, rds_password, rds_endpoint).apply(
    lambda vars: f"""#!/bin/bash
cat <<EOF > /home/admin/application.properties
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver


spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.datasource.username={vars[0]}
spring.datasource.password={vars[1]}
spring.datasource.url=jdbc:mysql://{vars[2]}/webapp_DB?createDatabaseIfNotExist=true

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

# Attach the CloudWatchAgentServerPolicy to the IAM role
policy_attachment = aws.iam.RolePolicyAttachment("my-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
    role=role.name,
)

hosted_zone_id = config.require("hosted_zoneid")
domain_name = config.require("hosted_zonename")


ec2_instance = ec2.Instance("myEC2Instance",
    ami=ami_id,
    instance_type="t2.micro",
    subnet_id=subnet_id_first,
    security_groups=[application_security_group.id],  
    root_block_device={
        "volume_size": 25,
        "volume_type": "gp2",  
        "delete_on_termination": True,  
    },
    #iam_instance_profile=role.name,
    user_data=user_data_script,
    key_name=key_pair_name,
    tags={
        "Name": "MyEC2Instance",
    })


record = aws.route53.Record("myARecord",
    name=domain_name,
    type="A",
    ttl=300,
    records=[ec2_instance.public_ip],
    zone_id=hosted_zone_id)

pulumi.export("ec2InstanceId", ec2_instance.id)
pulumi.export("vpcId", vpc.id)
pulumi.export("gatewayId", gateway.id)
pulumi.export("dbEndPoint", rds_instance.endpoint)


