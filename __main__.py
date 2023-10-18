import pulumi
import pulumi_aws as aws
from pulumi_aws import ec2


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

availability_zones = aws.get_availability_zones(state="available")

for i, zone in enumerate(availability_zones.names[:3]):


    public_subnet_cidr = f"{vpc_cidr_block.split('.')[0]}.{vpc_cidr_block.split('.')[1]}.{i}.0/24"
    private_subnet_cidr = f"{vpc_cidr_block.split('.')[0]}.{vpc_cidr_block.split('.')[1]}.{i+3}.0/24"


    subnet = ec2.Subnet(f"public_subnet_{i}",
        cidr_block= public_subnet_cidr,
        vpc_id=vpc.id,
        map_public_ip_on_launch=True,
        tags={"Name": f"public-subnet-{i}"})
    
    public_subnet_ids.append(subnet.id)

    
    ec2.RouteTableAssociation(f"public_rta_{i}",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id)

    subnet = ec2.Subnet(f"private_subnet_{i}",
        cidr_block=private_subnet_cidr,
        vpc_id=vpc.id,
        map_public_ip_on_launch=False,
        tags={"Name": f"private-subnet-{i}"})

   
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
)


key_pair_name = pulumi.Config().require("key_name")


ami_id = pulumi.Config().require("ami_id")


subnet_id_first = public_subnet_ids[0]


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
    key_name=key_pair_name,
    tags={
        "Name": "MyEC2Instance",
    })


pulumi.export("ec2InstanceId", ec2_instance.id)
pulumi.export("vpcId", vpc.id)
pulumi.export("gatewayId", gateway.id)

