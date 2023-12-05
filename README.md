# Pulumi Python Infrastructure as Code (IAC) for AWS

This project uses Pulumi to create and manage AWS infrastructure resources using Python code. It sets up a typical web application environment with the following components:

- Amazon Virtual Private Cloud (VPC)
- Internet Gateway
- Public and Private Subnets
- Security Groups
- Amazon RDS (Relational Database Service) instance
- Amazon EC2 Instances
- Elastic Load Balancer (ELB)
- Auto Scaling Group
- CloudWatch Alarms

## Prerequisites

Before running this code, make sure you have the following prerequisites:

1. [Pulumi CLI](https://www.pulumi.com/docs/get-started/install/) installed on your machine.
2. AWS CLI configured with necessary credentials and region.

## Configuration

The code relies on configuration values provided through the `Pulumi.dev.yaml` file or environment variables. Ensure that you have the required configuration values set, including VPC CIDR blocks, hosted zone ID, and more, as specified in the `Pulumi.dev.yaml` file.

## Infrastructure Setup

### VPC and Networking

The code sets up a Virtual Private Cloud (VPC) with public and private subnets. It creates an Internet Gateway for public internet access and routes traffic accordingly.

### EC2 Instances

Amazon EC2 instances are launched within the public subnets. These instances serve as web application servers and are secured by security groups that control incoming and outgoing traffic. The instances are launched from an Amazon Machine Image (AMI) and use user data scripts to configure the application environment.

### Amazon RDS

An Amazon RDS instance is created as a managed relational database service. It uses the MariaDB engine, and you can configure the database username and password through the Pulumi configuration.

### Elastic Load Balancer (ELB)

An Elastic Load Balancer (ELB) is set up to distribute incoming web traffic to the EC2 instances. The load balancer is associated with security groups and target groups.

### Auto Scaling

Auto Scaling is configured to automatically adjust the number of EC2 instances based on CPU utilization. High and low CPU utilization CloudWatch alarms trigger scaling policies to add or remove instances.

### DNS Configuration

The code also configures Route 53 DNS records to map a custom domain name to the Elastic Load Balancer's DNS name. Ensure that your domain name is properly configured and linked to the Route 53 hosted zone.

## Deployment

To deploy this infrastructure, follow these steps:


2. Initialize your Pulumi project by running `pulumi stack init <your-project-name>`.

3. Set the required configuration values using `pulumi config set` for each value specified in `Pulumi.dev.yaml`.

4. Deploy the infrastructure by running `pulumi up`.

5. Review the changes, and if they look correct, confirm the deployment by typing `yes`.

6. Pulumi will provision the AWS resources as specified in the code.

Command Used to import Namecheap SSL certificate to ACM: 

aws acm import-certificate --certificate fileb://filepath/demo_swecsye6225_me.crt --private-key fileb://filepath/demo.swecsye6225.me.key --certificate-chain fileb://filepath/demo_swecsye6225_me.ca-bundle --profile demo



## Cleanup

To tear down the provisioned resources, run `pulumi destroy`. Confirm the destruction of resources when prompted.


---
