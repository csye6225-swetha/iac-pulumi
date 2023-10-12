import pulumi
import pulumi_aws as aws
from pulumi_aws import ec2


vpc = ec2.Vpc("my_vpc",
    cidr_block="172.16.0.0/16",
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



availability_zones = aws.get_availability_zones(state="available")

for i, zone in enumerate(availability_zones.names[:3]):
    subnet = ec2.Subnet(f"public_subnet_{i}",
        cidr_block=f"172.16.{i}.0/24",
        vpc_id=vpc.id,
        map_public_ip_on_launch=True,
        tags={"Name": f"public-subnet-{i}"})

    
    ec2.RouteTableAssociation(f"public_rta_{i}",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id)

    subnet = ec2.Subnet(f"private_subnet_{i}",
        cidr_block=f"172.16.{i+3}.0/24",
        vpc_id=vpc.id,
        map_public_ip_on_launch=False,
        tags={"Name": f"private-subnet-{i}"})

   
    ec2.RouteTableAssociation(f"private_rta_{i}",
        subnet_id=subnet.id,
        route_table_id=private_route_table.id)

pulumi.export("vpcId", vpc.id)
pulumi.export("gatewayId", gateway.id)

